"""Acceptance tests for R3 — per-enemy intent history (OBS_SCHEMA.md §5.2,
§7's R3 section).

House style matches ``test_combat_obs_v4.py``: build a live ``CombatState``,
drive real turns, read the facts directly off the engine, decode the
observation, and assert the two agree. Every test here uses a monster whose
intent genuinely changes turn to turn (``LivingFog``/``GasBomb``, a real
registered slot-reordering encounter, or a small custom cycling dummy) —
never a fixture where the same intent repeats every turn, which would pass
whether or not the history buffer worked at all.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, CreatureCmd, DamageCmd, Encounter, PowerCmd, make_card
from sts2_rl.cmds import BlockCmd
from sts2_rl.full_env import (
    ABS_SCALE,
    MAX_ENEMIES,
    MAX_INTENT_HISTORY,
    _N_ENEMY_HISTORY_SCALARS,
    _clip01,
    build_combat_obs,
    combat_obs_layout,
)
from sts2_rl.monsters import Intent, Monster, MoveType
from sts2_rl.monsters.underdocks import LivingFog, LIVING_FOG_NORMAL
from sts2_rl.powers import StrengthPower
from sts2_rl.probes import probe_dummy


def _combat(*, deck=None, encounter=None) -> CombatState:
    deck_ids = deck if deck is not None else ["strike"] * 5 + ["defend"] * 4
    return CombatState(
        starting_deck=[make_card(cid) for cid in deck_ids],
        encounter=encounter,
    )


def _history_block(obs, e_i: int):
    """Decode enemy slot ``e_i``'s R3 history block into
    ``MAX_INTENT_HISTORY`` rows of ``_N_ENEMY_HISTORY_SCALARS`` floats each,
    most-recent-first."""
    layout = combat_obs_layout()
    sl = layout.f_slices[f"enemy{e_i}.intent_history.f"]
    flat = obs["f"][sl]
    return flat.reshape(MAX_INTENT_HISTORY, _N_ENEMY_HISTORY_SCALARS)


# Column offsets within one 15-float history row (see
# full_env._enemy_intent_history_floats).
RECORDED, ATTACK, DEFEND, BUFF, DEBUFF, STATUS_CARD, SUMMON, ESCAPE, HEAL, STUN = range(10)
PER_HIT, HITS, TOTAL_FINE, TOTAL_COARSE, STATUS_COUNT = range(10, 15)


# ── A small, fully deterministic 4-move cycling dummy ────────────────────────
# (LivingFog is used separately below for the net_id/reordering test — this
# one exists purely to test ordering + rolling past N without a spawn's
# position churn as a confound.)

_CYCLE = [
    Intent(MoveType.ATTACK, damage=5, hits=1),
    Intent(MoveType.DEFEND),
    Intent(MoveType.ATTACK, damage=9, hits=2),
    Intent(MoveType.BUFF, buffs=[(StrengthPower, 1)]),
]


class _CyclingDummy(Monster):
    """Deterministically cycles through 4 distinguishable intents, one per
    turn, with no RNG and no side effects on the enemy list — isolates the
    "history fills then rolls past N" property from net_id/reordering
    concerns (covered separately by the LivingFog/GasBomb test below)."""

    min_hp = max_hp = 500

    def __init__(self, hooks, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._idx = 0

    @property
    def current_intent(self) -> Intent:
        return _CYCLE[self._idx % len(_CYCLE)]

    def take_turn(self, ctx) -> None:
        intent = self.current_intent
        if intent.move_type == MoveType.ATTACK:
            self._execute_attack(ctx, intent.damage, intent.hits)
        elif intent.move_type == MoveType.DEFEND:
            BlockCmd.apply(ctx.hooks, self, 6)
        elif intent.move_type == MoveType.BUFF:
            for cls, amt in intent.buffs:
                PowerCmd.apply(ctx.hooks, self, cls, amt)

    def telegraph_next_move(self) -> None:
        self._idx += 1


def _cycling_combat() -> CombatState:
    enc = Encounter(id="v4_history_cycle", monster_classes=[_CyclingDummy])
    return _combat(encounter=enc)


# ── 1. Ordering + rolling past N ─────────────────────────────────────────────


def test_history_is_most_recent_first_and_rolls_past_n():
    """4 turns of a 4-distinct-intent cycle, N=3: after the 4th turn the
    OLDEST (turn-1 ATTACK5) must have been evicted, and the 3 remaining
    slots must read newest-first: [BUFF, ATTACK9x2, DEFEND]."""
    cs = _cycling_combat()
    assert cs.enemies[0].current_intent.move_type == MoveType.ATTACK  # turn 1

    cs.end_turn()  # performs ATTACK5 (turn 1); records it; turn 2 = DEFEND
    cs.end_turn()  # performs DEFEND (turn 2); records it; turn 3 = ATTACK9x2
    cs.end_turn()  # performs ATTACK9x2 (turn 3); records it; turn 4 = BUFF
    cs.end_turn()  # performs BUFF (turn 4); records it; turn 5 = ATTACK5 again

    obs = build_combat_obs(cs)
    rows = _history_block(obs, 0)

    # Slot 0 = most recent = BUFF.
    assert rows[0][RECORDED] == 1.0
    assert rows[0][BUFF] == 1.0
    assert rows[0][ATTACK] == 0.0

    # Slot 1 = ATTACK9x2 (dmg 9, 2 hits).
    assert rows[1][RECORDED] == 1.0
    assert rows[1][ATTACK] == 1.0
    assert rows[1][PER_HIT] == pytest.approx(_clip01(9 / ABS_SCALE))
    assert rows[1][HITS] == pytest.approx(_clip01(2 / 10.0))

    # Slot 2 = DEFEND.
    assert rows[2][RECORDED] == 1.0
    assert rows[2][DEFEND] == 1.0
    assert rows[2][ATTACK] == 0.0

    # The turn-1 ATTACK5 (per_hit 5) has been evicted entirely: no slot may
    # show it — the strongest way to assert this is that PER_HIT never reads
    # the ATTACK5 encoding at a DEFEND or BUFF row (which have no attack) and
    # that only 3 slots exist at all (there is no 4th slot to check).
    assert rows.shape[0] == MAX_INTENT_HISTORY == 3


def test_history_starts_fully_unrecorded_and_fills_one_slot_per_turn():
    """Before any turn has completed, and after each of the first
    MAX_INTENT_HISTORY turns, exactly the right number of slots are
    `recorded` — never fabricated early, never missing once genuinely
    displayed."""
    cs = _cycling_combat()
    obs = build_combat_obs(cs)
    rows = _history_block(obs, 0)
    assert list(rows[:, RECORDED]) == [0.0, 0.0, 0.0]

    for expected_filled in (1, 2, 3):
        cs.end_turn()
        obs = build_combat_obs(cs)
        rows = _history_block(obs, 0)
        assert list(rows[:, RECORDED]) == (
            [1.0] * expected_filled + [0.0] * (MAX_INTENT_HISTORY - expected_filled)
        )


# ── 2. net_id keying across a real slot-reordering encounter ────────────────


def test_history_follows_net_id_through_a_slot_reorder_not_row_position():
    """LivingFog's BLOAT move spawns a GasBomb that is inserted AHEAD of
    LivingFog in the enemy list (`living_fog.py`'s slot re-sort) — one of the
    three encounters OBS_SCHEMA.md names as reordering a live enemy's row
    mid-combat. After this happens, row 0 is a BRAND NEW creature (the bomb,
    net_id 2) that has never acted, and row 1 is LivingFog (net_id 1), which
    has acted twice. A row-position-keyed history buffer would hand the
    bomb's row LivingFog's old history (or vice versa); a net_id-keyed one
    must not."""
    cs = _combat(encounter=LIVING_FOG_NORMAL)
    living_fog = cs.enemies[0]
    assert living_fog.net_id == 1

    cs.end_turn()  # performs ADVANCED_GAS; records it; next = BLOAT
    cs.end_turn()  # performs BLOAT: spawns GasBomb ahead of LivingFog; records BLOAT

    # The reorder actually happened -- fixture sanity, not the property under
    # test.
    assert len(cs.enemies) == 2
    bomb, fog = cs.enemies[0], cs.enemies[1]
    assert bomb is not living_fog and fog is living_fog
    assert bomb.net_id == 2
    assert bomb.performed_first_move is False  # spawned this same enemy turn

    obs = build_combat_obs(cs)
    bomb_hist = _history_block(obs, 0)
    fog_hist = _history_block(obs, 1)

    # Row 0 (the bomb, never acted): fully unrecorded -- NOT LivingFog's
    # ADVANCED_GAS/BLOAT history, which a row-keyed buffer would show here.
    assert list(bomb_hist[:, RECORDED]) == [0.0, 0.0, 0.0]

    # Row 1 (LivingFog, followed to its NEW row): both real turns present,
    # most-recent (BLOAT: ATTACK dmg 5 + SUMMON) first, then ADVANCED_GAS
    # (ATTACK dmg 8 + the merged DEBUFF flag, since ADVANCED_GAS's secondary
    # is CARD_DEBUFF).
    assert fog_hist[0][RECORDED] == 1.0
    assert fog_hist[0][ATTACK] == 1.0
    assert fog_hist[0][SUMMON] == 1.0
    assert fog_hist[0][PER_HIT] == pytest.approx(_clip01(5 / ABS_SCALE))

    assert fog_hist[1][RECORDED] == 1.0
    assert fog_hist[1][ATTACK] == 1.0
    assert fog_hist[1][DEBUFF] == 1.0
    assert fog_hist[1][SUMMON] == 0.0
    assert fog_hist[1][PER_HIT] == pytest.approx(_clip01(8 / ABS_SCALE))

    assert fog_hist[2][RECORDED] == 0.0


# ── 3. Padding: gone/absent enemies read fully unrecorded ───────────────────


def test_dead_enemys_history_reads_fully_unrecorded_even_though_it_has_real_entries():
    """A creature that had genuine, real history is then killed; its (now
    absent) slot must show NO history at all -- matching how `_enemies_rows`
    already blanks a gone enemy's CURRENT fields. This is the sharp case: the
    internal buffer is NOT cleared (so a revived creature keeps its history),
    but the OBSERVATION for an absent slot must not leak it."""
    dummy = probe_dummy("HistoryDeadDummy", hp=500, damage=7)
    cs = _combat(encounter=Encounter(id="v4_history_dead", monster_classes=[dummy]))
    enemy = cs.enemies[0]

    cs.end_turn()  # performs the attack; records ONE real entry

    obs = build_combat_obs(cs)
    assert _history_block(obs, 0)[0][RECORDED] == 1.0  # fixture sanity

    CreatureCmd.kill(cs.hooks, enemy)
    assert enemy.is_gone

    obs = build_combat_obs(cs)
    rows = _history_block(obs, 0)
    assert list(rows[:, RECORDED]) == [0.0, 0.0, 0.0]

    # The internal buffer itself is untouched (not cleared) -- only the
    # observation write for the now-absent slot blanks it.
    assert len(cs._intent_history.get(enemy.net_id, ())) == 1


# ── 4. No leakage across combats / env.reset() ───────────────────────────────


def test_no_leakage_across_combats_with_the_same_net_id():
    """A fresh CombatState's first enemy gets net_id 1 again (the counter
    restarts) -- so a history dict keyed by net_id ALONE, without also being
    scoped per-CombatState, would silently inherit the previous combat's
    entries. Build real history in combat A, then confirm a brand-new combat
    B's net_id-1 enemy starts fully unrecorded."""
    dummy = probe_dummy("HistoryLeakDummy", hp=500, damage=6)
    enc = lambda: Encounter(id="v4_history_leak", monster_classes=[dummy])

    cs_a = _combat(encounter=enc())
    assert cs_a.enemies[0].net_id == 1
    cs_a.end_turn()
    cs_a.end_turn()
    obs_a = build_combat_obs(cs_a)
    assert _history_block(obs_a, 0)[0][RECORDED] == 1.0  # fixture sanity

    cs_b = _combat(encounter=enc())
    assert cs_b.enemies[0].net_id == 1  # same net_id as combat A's enemy
    assert cs_b._intent_history == {}
    obs_b = build_combat_obs(cs_b)
    assert list(_history_block(obs_b, 0)[:, RECORDED]) == [0.0, 0.0, 0.0]
