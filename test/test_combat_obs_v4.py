"""Acceptance tests for the v4 combat observation (OBS_SCHEMA.md).

Written BEFORE full_env.py's v4 implementation (TDD) — every test here was
confirmed RED against the v3 tree before a single line of the new encoder was
written. These are "observation-content assertions": build a live
``CombatState``, read the facts directly off it, then decode the observation
and assert the two agree — never just "shape didn't change".

Layout is addressed through ``combat_obs_layout()``'s named slices, never by
magic index, mirroring ``test/test_obs_pins.py``'s convention for v3.
"""
from __future__ import annotations

import random

import numpy as np
import pytest

from sts2_rl import (
    FUZZY_WURM_ENCOUNTER,
    CombatState,
    CreatureCmd,
    DamageCmd,
    Encounter,
    PowerCmd,
    make_card,
    make_relic,
)
from sts2_rl.afflictions import AFFLICTION_INDEX, RingingAffliction
from sts2_rl.cards import Card
from sts2_rl.cmds import CardCmd
from sts2_rl.enchantments import ENCHANTMENT_INDEX, make_enchantment
from sts2_rl.full_env import (
    ABS_SCALE,
    CARD_INDEX,
    COMBAT_POTION_BASE,
    MAX_COMBAT_CARDS,
    MAX_ENEMIES,
    MAX_HAND,
    MAX_OBS_ID,
    MAX_POTION_ROWS,
    MAX_POTIONS,
    MAX_POWERS_PLAYER,
    MAX_RELIC_ROWS,
    MONSTER_INDEX,
    POTION_INDEX,
    POWER_INDEX,
    RELIC_INDEX,
    _N_ENEMY_SCALARS,
    AblatedObsEnv,
    STS2FullCombatEnv,
    _clip01,
    _signed,
    build_combat_obs,
    combat_obs_layout,
    combat_obs_segments_f,
    combat_obs_segments_i,
    decode_combat_action,
    write_combat_obs,
)
from sts2_rl.monsters import INKLETS_NORMAL, Intent, Monster, MoveType
from sts2_rl.monsters.underdocks import LivingFog, WaterfallGiant, WATERFALL_GIANT_BOSS
from sts2_rl.obs import ObsBuffer, ObsLayout
from sts2_rl.potions import make_potion
from sts2_rl.powers import (
    HardenedShellPower,
    SlothPower,
    SlowPower,
    StrengthPower,
    TenderPower,
    TheBombPower,
)
from sts2_rl.previews import preview_card_damage
from sts2_rl.probes import probe_dummy
from sts2_rl.relic_obs import EXCLUDED_RELIC_STATE


def _combat(*, deck=None, encounter=None, relics=None, potions=None) -> CombatState:
    deck_ids = deck if deck is not None else ["strike"] * 5 + ["defend"] * 4
    if encounter is None:
        dummy = probe_dummy("V4Dummy", hp=20, damage=5)
        encounter = Encounter(id="v4_single", monster_classes=[dummy])
    return CombatState(
        starting_deck=[make_card(cid) for cid in deck_ids],
        encounter=encounter,
        relics=relics,
        potions=potions,
    )


# ── 1. Layout self-consistency ───────────────────────────────────────────────


@pytest.mark.parametrize("card_obs", ["hybrid", "features"])
def test_layout_self_consistency(card_obs):
    layout = combat_obs_layout(card_obs)
    assert sum(w for _, w in combat_obs_segments_f(card_obs)) == layout.f_dim
    assert sum(w for _, w in combat_obs_segments_i(card_obs)) == layout.i_dim

    env = STS2FullCombatEnv(card_obs=card_obs)
    space = env.observation_space
    assert space["f"].shape == (layout.f_dim,)
    assert space["i"].shape == (layout.i_dim,)
    assert space["f"].dtype == np.float32
    assert space["i"].dtype == np.int32

    obs, _info = env.reset(seed=0)
    assert obs["f"].shape == (layout.f_dim,)
    assert obs["i"].shape == (layout.i_dim,)
    assert obs["f"].dtype == np.float32
    assert obs["i"].dtype == np.int32
    assert np.all(obs["f"] >= 0.0) and np.all(obs["f"] <= 1.0)
    assert np.all(obs["i"] >= 0) and np.all(obs["i"] <= MAX_OBS_ID)

    obs2, *_ = env.step(0)   # end turn — exercise step(), not just reset()
    assert np.all(obs2["f"] >= 0.0) and np.all(obs2["f"] <= 1.0)
    assert np.all(obs2["i"] >= 0) and np.all(obs2["i"] <= MAX_OBS_ID)


# ── 2. Content: powers (two `the_bomb` instances) ────────────────────────────


def test_the_bomb_two_instances_are_two_rows_with_distinct_aux():
    s = _combat()
    pw1 = PowerCmd.apply(s.hooks, s.player, TheBombPower, 3)
    pw1.set_damage(40)
    pw2 = PowerCmd.apply(s.hooks, s.player, TheBombPower, 5)
    pw2.set_damage(70)
    # Sanity on the engine side: phase 0's whole point is that these are two
    # real, independently-ticking instances, not one dict slot.
    assert len(s.player.powers.instances("the_bomb")) == 2

    obs = build_combat_obs(s)
    layout = combat_obs_layout()
    bomb_id = POWER_INDEX["the_bomb"] + 1
    ids = obs["i"][layout.i_slices["player.powers.ids"]]
    fs = obs["f"][layout.f_slices["player.powers.f"]].reshape(-1, 3)

    rows = [i for i, v in enumerate(ids) if v == bomb_id]
    assert len(rows) == 2, "both instances must appear as separate rows"
    r0, r1 = rows
    assert r0 < r1                                # oldest first
    assert fs[r0][0] == pytest.approx(_signed(3, 10))
    assert fs[r1][0] == pytest.approx(_signed(5, 10))
    assert fs[r0][2] == pytest.approx(_clip01(40 / 100.0)), "aux must be pw1's own damage"
    assert fs[r1][2] == pytest.approx(_clip01(70 / 100.0)), "aux must be pw2's own damage, not pw1's"


# ── 2b. Content: powers admitted via C# DisplayAmount, not the INSTANCED
#        sweep (review item 2) — each publishes the DISPLAYED value, not the
#        raw counter, verified against the four .cs files directly. ─────────


def test_hardened_shell_aux_publishes_the_remaining_absorb_cap():
    # HardenedShellPower.cs:25 — DisplayAmount = max(0, Amount -
    # damageReceivedThisTurn). The raw counter (5) must NOT appear; the
    # published aux is the REMAINING cap (12 - 5 = 7), in the ABS_SCALE
    # bucket (an HP-like quantity).
    s = _combat()
    pw = PowerCmd.apply(s.hooks, s.player, HardenedShellPower, 12)
    pw._damage_received_this_turn = 5   # direct surgery, mirrors test 10's precedent

    obs = build_combat_obs(s)
    layout = combat_obs_layout()
    ids = obs["i"][layout.i_slices["player.powers.ids"]]
    fs = obs["f"][layout.f_slices["player.powers.f"]].reshape(-1, 3)
    power_id = POWER_INDEX["hardened_shell"] + 1
    row = next(i for i, v in enumerate(ids) if v == power_id)
    assert fs[row][2] == pytest.approx(_clip01((12 - 5) / ABS_SCALE))


def test_sloth_aux_publishes_cards_played_this_turn():
    # SlothPower.cs:20 — DisplayAmount = _cardsPlayedThisTurn (a per-turn
    # counter, /10.0 bucket), independent of `amount` (the play-per-turn cap).
    s = _combat()
    pw = PowerCmd.apply(s.hooks, s.player, SlothPower, 3)
    pw._cards_played_this_turn = 2

    obs = build_combat_obs(s)
    layout = combat_obs_layout()
    ids = obs["i"][layout.i_slices["player.powers.ids"]]
    fs = obs["f"][layout.f_slices["player.powers.f"]].reshape(-1, 3)
    power_id = POWER_INDEX["sloth"] + 1
    row = next(i for i, v in enumerate(ids) if v == power_id)
    assert fs[row][2] == pytest.approx(_clip01(2 / 10.0))


def test_tender_aux_publishes_cards_played_this_turn():
    # TenderPower.cs:22 — DisplayAmount = CardsPlayedThisTurn (/10.0 bucket).
    s = _combat()
    pw = PowerCmd.apply(s.hooks, s.player, TenderPower, 1)
    pw._cards_played_this_turn = 4

    obs = build_combat_obs(s)
    layout = combat_obs_layout()
    ids = obs["i"][layout.i_slices["player.powers.ids"]]
    fs = obs["f"][layout.f_slices["player.powers.f"]].reshape(-1, 3)
    power_id = POWER_INDEX["tender"] + 1
    row = next(i for i, v in enumerate(ids) if v == power_id)
    assert fs[row][2] == pytest.approx(_clip01(4 / 10.0))


def test_slow_aux_publishes_the_displayed_slow_amount_not_the_raw_multiplier():
    # SlowPower.cs:22,26-30 — DisplayAmount = SlowAmount * 10, where
    # SlowAmount is the sim's `_cards_this_turn`. ABS_SCALE is 100, so
    # displayed/ABS_SCALE == raw/10.0 exactly — both land on the same float.
    s = _combat()
    pw = PowerCmd.apply(s.hooks, s.player, SlowPower, 1)
    pw._cards_this_turn = 4

    obs = build_combat_obs(s)
    layout = combat_obs_layout()
    ids = obs["i"][layout.i_slices["player.powers.ids"]]
    fs = obs["f"][layout.f_slices["player.powers.f"]].reshape(-1, 3)
    power_id = POWER_INDEX["slow"] + 1
    row = next(i for i, v in enumerate(ids) if v == power_id)
    assert fs[row][2] == pytest.approx(_clip01((4 * 10) / ABS_SCALE))
    assert fs[row][2] == pytest.approx(_clip01(4 / 10.0))


# ── 3. Content: hand (affliction + enchantment) ──────────────────────────────


def test_hand_affliction_and_enchantment_decode():
    s = _combat(deck=["strike", "defend", "bash"])
    h0, h1 = s.player.hand[0], s.player.hand[1]
    CardCmd.afflict(h0, RingingAffliction, 1)
    make_enchantment("sown").attach(h1)

    obs = build_combat_obs(s)
    layout = combat_obs_layout()
    ids = obs["i"][layout.i_slices["hand.ids"]].reshape(-1, 3)
    fs = obs["f"][layout.f_slices["hand.f"]].reshape(-1, 29)

    i0, i1 = s.player.hand.index(h0), s.player.hand.index(h1)
    assert ids[i0][0] == CARD_INDEX[h0.id] + 1
    assert ids[i0][1] == AFFLICTION_INDEX["ringing"] + 1
    assert ids[i0][2] == 0                         # no enchantment: PAD
    assert fs[i0][24] == pytest.approx(_clip01(1 / 10.0))   # affliction amount

    assert ids[i1][0] == CARD_INDEX[h1.id] + 1
    assert ids[i1][1] == 0                         # no affliction: PAD
    assert ids[i1][2] == ENCHANTMENT_INDEX["sown"] + 1


# ── 4. Content: enemies / potions / relics ───────────────────────────────────


def test_enemy_potion_relic_decode():
    relic = make_relic("girya")
    relic.times_lifted = 3                          # displayed 0-3, no flag
    potion = make_potion("fire_potion")              # targeted=True
    # A REAL registered monster (not a probes.py dummy, which is
    # deliberately excluded from the frozen monster vocabulary — see
    # sts2_rl/probes.py's module docstring) so the identity id is nonzero.
    s = _combat(encounter=FUZZY_WURM_ENCOUNTER, relics=[relic], potions=[None, potion, None])

    obs = build_combat_obs(s)
    layout = combat_obs_layout()

    eids = obs["i"][layout.i_slices["enemies.ids"]]
    assert eids[0] == MONSTER_INDEX[s.enemies[0].__class__.__name__] + 1
    assert eids[0] != 0

    pids = obs["i"][layout.i_slices["potions.ids"]]
    pf = obs["f"][layout.f_slices["potions.f"]]
    assert pids[0] == 0 and pids[2] == 0             # empty belt slots: PAD
    assert pids[1] == POTION_INDEX["fire_potion"] + 1
    assert pf[1] == pytest.approx(1.0)               # targeted flag

    rids = obs["i"][layout.i_slices["player.relics.ids"]]
    rf = obs["f"][layout.f_slices["player.relics.f"]].reshape(-1, 2)
    assert rids[0] == RELIC_INDEX["girya"] + 1
    assert rf[0][0] == pytest.approx(3 / 10.0)       # relic_row's counter / 10
    assert rf[0][1] == pytest.approx(0.0)            # girya has no flag


def _status_dummy(name: str, count: int | None) -> type[Monster]:
    """A fixed-stat enemy whose sole intent is a bare ``StatusIntent``
    (``MoveType.STATUS_CARD``) carrying ``count`` -- mirrors a real C#
    construction site (e.g. ``TheInsatiable.cs``'s LIQUIFY_GROUND_MOVE =
    ``StatusIntent(6)``). Not ``sts2_rl.probes.probe_dummy`` (ATTACK-only,
    fixed shape): this needs a controllable STATUS_CARD count, including the
    ``None`` case (the 13-of-18 sim sites that don't carry one yet --
    ``monster/_intent_count_lost``, ``sts2_rl/monsters/base.py``'s ``Intent``
    docstring)."""

    class _StatusDummy(Monster):
        min_hp = max_hp = 20

        @property
        def current_intent(self) -> Intent:
            return Intent(MoveType.STATUS_CARD, status_count=count)

        def take_turn(self, ctx) -> None:
            pass

    _StatusDummy.__name__ = _StatusDummy.__qualname__ = name
    return _StatusDummy


def test_enemy_status_intent_card_count_decodes():
    """StatusIntent's card count is a NUMBER the real game displays on the
    intent icon (``NIntent.cs:133-136``'s ``intent is StatusIntent`` branch;
    ``StatusIntent.cs``'s ``FORMAT_STATUS_CARD_COUNT`` labels it with
    ``CardCount``) -- the only *other* ``IntentType`` besides Attack that
    renders a number (OBS_SCHEMA.md §7's R3 discussion already cites this
    same renderer, but the enemy row never carried the count itself).

    Two different, non-degenerate counts (6 and 3 -- never 1, which a
    boolean-shaped bug could satisfy by accident) on two different enemy
    slots, so a test reading back "some flag fired" rather than "the actual
    number" would fail here. A third enemy pins the un-ported (``None``)
    case: the STATUS_CARD flag still fires, but the count field reads 0.0,
    not a fabricated number the sim was never told."""
    enc = Encounter(
        id="v4_status_count",
        monster_classes=[
            _status_dummy("StatusSix", 6),
            _status_dummy("StatusThree", 3),
            _status_dummy("StatusUnported", None),
        ],
    )
    s = _combat(encounter=enc)
    assert s.enemies[0].current_intent.status_count == 6
    assert s.enemies[1].current_intent.status_count == 3
    assert s.enemies[2].current_intent.status_count is None

    obs = build_combat_obs(s)
    layout = combat_obs_layout()
    ef = obs["f"][layout.f_slices["enemies.f"]].reshape(-1, _N_ENEMY_SCALARS)

    # The STATUS_CARD flag (index 13, unchanged from v3) fires for all three.
    assert ef[0][13] == 1.0 and ef[1][13] == 1.0 and ef[2][13] == 1.0
    # The new count field distinguishes 6 from 3 from "unknown" (0.0).
    assert ef[0][24] == pytest.approx(_clip01(6 / 10.0))
    assert ef[1][24] == pytest.approx(_clip01(3 / 10.0))
    assert ef[2][24] == pytest.approx(0.0)


def test_gas_bomb_death_blow_shows_as_attack_with_damage_preview():
    """DeathBlowIntent (src/Core/MonsterMoves/Intents/DeathBlowIntent.cs) is a
    SingleAttackIntent -> AttackIntent (AttackIntent.cs:17), so it renders a
    damage number exactly like any other attack (NIntent.cs:135's `intent is
    AttackIntent` check is a C# type test, unaffected by DeathBlowIntent's
    overridden `IntentType`) and `MonsterModel.IntendsToAttack`
    (MonsterModel.cs:241-245) explicitly ORs `IntentType.DeathBlow` in with
    `IntentType.Attack` for gameplay purposes. The sim's `Intent(MoveType.
    DEATH_BLOW, ...)` must therefore also carry `MoveType.ATTACK` in its
    `also` tuple so `Intent.has(MoveType.ATTACK)` -- which gates both the
    enemy row's attack flag (full_env.py's `_enemy_floats`, field 9) and
    `previews.preview_incoming_damage` -- fires for it, with NO change to the
    observation's width or field layout: this populates the EXISTING attack
    flag and damage-preview fields, the same ones any other attacking enemy
    populates.

    Uses a real registered monster (Living Fog's Gas Bomb minion, not a
    probes.py dummy) so the fixture is not degenerate."""
    enc = Encounter(id="v4_deathblow_fog", monster_classes=[LivingFog])
    cs = _combat(encounter=enc)
    cs.end_turn()  # ADVANCED_GAS
    cs.end_turn()  # BLOAT: spawns a Gas Bomb (sorts ahead of the fog -> slot 0)
    bomb = cs.enemies[0]
    assert bomb.current_intent.move_type == MoveType.DEATH_BLOW
    assert bomb.current_intent.damage == 8
    assert bomb.current_intent.has(MoveType.ATTACK), (
        "fixture regression: the death-blow intent must carry ATTACK in "
        "`also` for this test to exercise the gap at all")

    obs = build_combat_obs(cs)
    layout = combat_obs_layout()
    ef = obs["f"][layout.f_slices["enemies.f"]].reshape(-1, _N_ENEMY_SCALARS)
    bomb_row = ef[0]

    # Field 9 (fb=9 in _enemy_floats): the ATTACK intent flag.
    assert bomb_row[9] == 1.0
    # Fields 18-21: per_hit / hits / total (abs2) -- a nonzero damage preview,
    # not the "no attack at all" the sim showed before the also=(ATTACK,) fix.
    assert bomb_row[18] == pytest.approx(_clip01(8 / ABS_SCALE))
    assert bomb_row[19] == pytest.approx(_clip01(1 / 10.0))
    assert (bomb_row[20], bomb_row[21]) != (0.0, 0.0)


def test_waterfall_giant_explode_death_blow_shows_as_attack():
    """Same gap, second construction site (waterfall_giant.py's EXPLODE_MOVE)
    -- a different monster, a different (dynamic, banked-Steam-Eruption)
    damage value, confirming the fix is not special-cased to a fixed number.
    Drives the SAME path as test_underdocks.py's
    test_killing_blow_triggers_the_explosion (a real boss encounter, not a
    dummy)."""
    cs = CombatState(rng=random.Random(0), encounter=WATERFALL_GIANT_BOSS)
    giant = cs.enemies[0]
    cs.end_turn()  # PRESSURIZE: banks 15 Steam Eruption
    DamageCmd.deal(cs.hooks, giant, 999, dealer=cs.player)
    assert giant.is_about_to_blow
    cs.end_turn()  # ABOUT_TO_BLOW: banks the steam, lose the turn
    intent = giant.current_intent
    assert intent.move_type == MoveType.DEATH_BLOW
    assert intent.damage == 15
    assert intent.has(MoveType.ATTACK), (
        "fixture regression: the death-blow intent must carry ATTACK in "
        "`also` for this test to exercise the gap at all")

    obs = build_combat_obs(cs)
    layout = combat_obs_layout()
    ef = obs["f"][layout.f_slices["enemies.f"]].reshape(-1, _N_ENEMY_SCALARS)
    giant_row = ef[0]

    assert giant_row[9] == 1.0
    assert giant_row[18] == pytest.approx(_clip01(15 / ABS_SCALE))
    assert (giant_row[20], giant_row[21]) != (0.0, 0.0)


# ── 5. Content: piles (draw + discard + exhaust) ─────────────────────────────


def test_cards_block_is_exact_multiset_of_the_three_piles():
    # A deck bigger than the opening hand draw, so cards remain in draw_pile
    # to move around.
    s = _combat(deck=["strike"] * 6 + ["defend"] * 6)
    p = s.player
    moved_to_discard = p.draw_pile.pop()
    p.discard_pile.append(moved_to_discard)
    moved_to_exhaust = p.draw_pile.pop()
    p.exhaust_pile.append(moved_to_exhaust)

    obs = build_combat_obs(s)
    layout = combat_obs_layout()
    ids = obs["i"][layout.i_slices["cards.ids"]].reshape(-1, 4)

    expected = []
    for pile_id, pile in ((1, p.draw_pile), (2, p.discard_pile), (3, p.exhaust_pile)):
        for card in pile:
            expected.append((pile_id, CARD_INDEX[card.id] + 1, 0, 0))
    got = [tuple(int(x) for x in row) for row in ids if row[0] != 0]

    assert sorted(got) == sorted(expected)
    n_total = len(p.draw_pile) + len(p.discard_pile) + len(p.exhaust_pile)
    assert len(got) == n_total
    # Hand cards must NOT appear in this block.
    hand_ids = {CARD_INDEX[c.id] + 1 for c in p.hand}
    for pile_id, card_id, _aff, _ench in got:
        if card_id in hand_ids:
            # allowed only if the SAME id also legitimately sits in a pile
            assert any(CARD_INDEX[c.id] + 1 == card_id
                       for c in (p.draw_pile + p.discard_pile + p.exhaust_pile))


# ── 6. POSITIONAL alignment ───────────────────────────────────────────────────


def test_positional_alignment_survives_a_dead_enemy_and_empty_slots():
    # INKLETS_NORMAL: a REAL registered 3-monster encounter (all Inklet, one
    # `is_middle=True`), not a probes.py dummy — probes.py dummies are
    # deliberately outside the frozen monster vocabulary (see that module's
    # docstring), so an identity-equality assertion over them is `0 == 0` and
    # proves nothing. This encounter makes the identity id nonzero for all
    # three slots, so the equality checks below are checking real identity.
    s = _combat(encounter=INKLETS_NORMAL, potions=[None, make_potion("fire_potion"), None])
    layout = combat_obs_layout()
    before = build_combat_obs(s)
    eids_before = before["i"][layout.i_slices["enemies.ids"]]
    ef_before = before["f"][layout.f_slices["enemies.f"]].reshape(-1, _N_ENEMY_SCALARS)
    assert eids_before[1] != 0 and eids_before[2] != 0, (
        "fixture regression: the identity checks below are vacuous at id 0")

    CreatureCmd.kill(s.hooks, s.enemies[0])
    assert s.enemies[0].is_gone and not s.enemies[1].is_gone

    after = build_combat_obs(s)
    eids_after = after["i"][layout.i_slices["enemies.ids"]]
    ef_after = after["f"][layout.f_slices["enemies.f"]].reshape(-1, _N_ENEMY_SCALARS)

    # enemy 0's row is now an explicit PAD row.
    assert eids_after[0] == 0
    assert np.all(ef_after[0] == 0.0)
    # enemy 1 did NOT slide into row 0 — it is still at row 1, unchanged,
    # identified by its REAL nonzero monster id (not merely the "present"
    # float flag, which was the only signal available with probe dummies).
    assert eids_after[1] == eids_before[1]
    assert ef_before[1][0] == 1.0 and ef_after[1][0] == 1.0
    np.testing.assert_allclose(ef_after[1], ef_before[1])
    assert eids_after[2] == eids_before[2]
    assert ef_after[2][0] == 1.0

    # Empty potion belt slots are explicit PAD rows, not skipped.
    pids = after["i"][layout.i_slices["potions.ids"]]
    assert pids[0] == 0 and pids[2] == 0
    assert pids[1] == POTION_INDEX["fire_potion"] + 1

    # An empty trailing hand slot is an explicit PAD row.
    hids = after["i"][layout.i_slices["hand.ids"]].reshape(-1, 3)
    for h in range(len(s.player.hand), MAX_HAND):
        assert tuple(int(x) for x in hids[h]) == (0, 0, 0)


# ── 7. Non-leak: pile order is hidden ────────────────────────────────────────


_HETEROGENEOUS_CARD_IDS = ["strike", "defend", "bash", "pommel_strike"]


def _heterogeneous_pile(n: int) -> list[Card]:
    """``n`` cards spanning several ids and upgrade levels, with at least one
    afflicted, one enchanted and one ``exhaust_on_next_play`` card whenever
    ``n`` is large enough to hold them — so the block's sort key (which
    covers every field, OBS_SCHEMA.md §5.3) actually has heterogeneous input
    to discriminate, instead of N copies of one identical row."""
    cards = []
    for i in range(n):
        c = make_card(_HETEROGENEOUS_CARD_IDS[i % len(_HETEROGENEOUS_CARD_IDS)])
        if i % 3 == 1:
            c.upgrade()
        cards.append(c)
    if len(cards) > 0:
        CardCmd.afflict(cards[0], RingingAffliction, 1)
    if len(cards) > 1:
        make_enchantment("sown").attach(cards[1])
    if len(cards) > 2:
        cards[2].exhaust_on_next_play = True
    return cards


def _shuffled_cards_obs(s: CombatState, seed: int) -> dict[str, np.ndarray]:
    """Independently shuffle EACH of the three piles (not just one) with a
    fresh RNG, then rebuild the observation."""
    rng = random.Random(seed)
    rng.shuffle(s.player.draw_pile)
    rng.shuffle(s.player.discard_pile)
    rng.shuffle(s.player.exhaust_pile)
    return build_combat_obs(s)


def test_cards_block_is_shuffle_invariant_including_past_overflow():
    """The real non-leak property (OBS_SCHEMA.md §5.3): shuffling any of the
    three piles must not change the observation. This must be tested over a
    HETEROGENEOUS multiset — mixed card ids, mixed upgrade levels, an
    afflicted card, an enchanted card, an exhaust_on_next_play card — both
    under and OVER the cap, and over SEVERAL independent shuffles per pile.

    Wave 1 shipped a hidden-information leak (``write_rows`` truncating
    before sorting instead of after) whose own non-leak test never caught it
    because it only ever shuffled an EMPTY pile or a pile of IDENTICAL
    Strikes — permutations that can never change which rows a truncate-then-
    sort bug keeps. This version is proven to catch that exact defect by a
    runtime monkeypatch in ``scratchpad/t4_mutation_check.py`` (not checked
    in here — see the fix report for its output): patching
    ``ObsBuffer.write_rows`` to truncate-then-sort turns this test RED.
    """
    s = _combat(deck=["strike"] * 5)   # opening hand only; piles built below
    p = s.player

    # ── Phase 1: heterogeneous, UNDER the cap ─────────────────────────────
    p.draw_pile = _heterogeneous_pile(6)
    p.discard_pile = _heterogeneous_pile(4)
    p.exhaust_pile = _heterogeneous_pile(3)
    obs1 = build_combat_obs(s)
    for seed in (1, 2, 3):
        obs_n = _shuffled_cards_obs(s, seed)
        np.testing.assert_array_equal(obs1["f"], obs_n["f"])
        np.testing.assert_array_equal(obs1["i"], obs_n["i"])

    # ── Phase 2: heterogeneous, OVER the cap ──────────────────────────────
    # The surplus lives in the draw pile itself (the pile every shuffle
    # below reshuffles), so the truncation cutoff falls INSIDE the shuffled
    # region — a truncate-then-sort bug keeps a different subset of rows on
    # every shuffle, which is exactly what this phase must catch.
    p.draw_pile = _heterogeneous_pile(MAX_COMBAT_CARDS + 14)
    p.discard_pile = _heterogeneous_pile(4)
    p.exhaust_pile = _heterogeneous_pile(3)
    with pytest.warns(UserWarning, match="cards"):
        obs3 = build_combat_obs(s)
    layout = combat_obs_layout()
    assert obs3["f"][layout.f_slices["cards.overflow"]][0] == pytest.approx(1.0)
    for seed in (11, 12, 13):
        obs_n = _shuffled_cards_obs(s, seed)
        np.testing.assert_array_equal(obs3["f"], obs_n["f"])
        np.testing.assert_array_equal(obs3["i"], obs_n["i"])


# ── 8. Relic non-leak ─────────────────────────────────────────────────────────


def _mutate(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1_000_000
    if isinstance(value, float):
        return value + 1_000_000.0
    if isinstance(value, str):
        return value + "_mutated_probe"
    if isinstance(value, list):
        return value + ["mutated_probe"]
    if isinstance(value, tuple):
        return value + ("mutated_probe",)
    if isinstance(value, dict):
        d = dict(value)
        d["mutated_probe"] = True
        return d
    return "mutated_probe"          # None, or an object reference (e.g. a Card)


# Exactly two of the 29 EXCLUDED_RELIC_STATE entries are exempted from the
# WHOLE-observation invariance check below: their attribute is genuine
# damage/block-pipeline state that legitimately changes OTHER, admitted
# observation fields through the relic's real hooks (not through relic_row).
#   - beating_remnant._received_this_turn moves player.incoming_post_block
#     and enemies.f (the relic's real damage-received hook).
#   - vambrace._triggering_card moves hand.f (the relic's real block hook).
# Every other one of the 27 has NO such path (see relic_obs.py's own
# docstring: either the whole relic has no display path at all, or the
# attribute is purely the undisplayed half of an otherwise-admitted relic's
# bookkeeping), so mutating it must leave the ENTIRE observation untouched —
# scoping the assertion to just the relic's own row (as the weakened version
# of this test did for all 29) would miss a future leak of any of these 27
# into e.g. player.powers.f or another relic's row.
_RELIC_ROW_ONLY_EXEMPT = frozenset({"beating_remnant", "vambrace"})


@pytest.mark.parametrize("relic_id", sorted(EXCLUDED_RELIC_STATE))
def test_excluded_relic_state_never_leaks(relic_id):
    """``EXCLUDED_RELIC_STATE`` (relic_obs.py) is a contract about
    ``relic_row``'s own two floats — "must never influence relic_row's
    output" (see that module's docstring) — not necessarily a claim that the
    attribute has zero effect on the rest of the game. For the two relics in
    ``_RELIC_ROW_ONLY_EXEMPT`` that IS a real effect (genuine damage/block-
    pipeline state reaching other, admitted fields through the relic's real
    hooks), so those two scope the assertion to exactly the relic's own
    ``player.relics.f`` row. Every other relic here has no such path, so the
    assertion is the STRONG whole-observation invariant — mutating the
    attribute must not move so much as one bit anywhere in ``obs["f"]`` or
    ``obs["i"]``.
    """
    for attr in EXCLUDED_RELIC_STATE[relic_id]:
        relic = make_relic(relic_id)
        s = _combat(relics=[relic])
        layout = combat_obs_layout()
        row = s.relics.index(relic)

        before = build_combat_obs(s)
        setattr(relic, attr, _mutate(getattr(relic, attr)))
        after = build_combat_obs(s)

        if relic_id in _RELIC_ROW_ONLY_EXEMPT:
            before_row = before["f"][layout.f_slices["player.relics.f"]].reshape(-1, 2)[row]
            after_row = after["f"][layout.f_slices["player.relics.f"]].reshape(-1, 2)[row]
            np.testing.assert_array_equal(
                before_row, after_row,
                err_msg=f"{relic_id}.{attr} leaked into its own relic_row")
        else:
            np.testing.assert_array_equal(
                before["f"], after["f"],
                err_msg=f"{relic_id}.{attr} leaked into the observation (f)")
            np.testing.assert_array_equal(
                before["i"], after["i"],
                err_msg=f"{relic_id}.{attr} leaked into the observation (i)")


# ── 9. Overflow ────────────────────────────────────────────────────────────────


def test_player_powers_overflow_keeps_oldest_first_prefix():
    s = _combat()
    n_applied = MAX_POWERS_PLAYER + 8
    for turn_counter in range(1, n_applied + 1):
        PowerCmd.apply(s.hooks, s.player, TheBombPower, turn_counter)
    assert len(s.player.powers.instances("the_bomb")) == n_applied

    with pytest.warns(UserWarning, match="player.powers"):
        obs = build_combat_obs(s)
    layout = combat_obs_layout()
    ids = obs["i"][layout.i_slices["player.powers.ids"]]
    fs = obs["f"][layout.f_slices["player.powers.f"]].reshape(-1, 3)

    bomb_id = POWER_INDEX["the_bomb"] + 1
    assert list(ids) == [bomb_id] * MAX_POWERS_PLAYER      # no truncation crash; exactly cap rows
    for row, turn_counter in enumerate(range(1, MAX_POWERS_PLAYER + 1)):
        assert fs[row][0] == pytest.approx(_signed(turn_counter, 10)), (
            "overflow must keep the OLDEST instances (a prefix), not the newest")
    assert obs["f"][layout.f_slices["player.powers.overflow"]][0] == pytest.approx(1.0)


def test_hand_overflow_flag_fires_when_hand_exceeds_cap():
    """Before the fix, ``_hand_rows`` always built exactly ``MAX_HAND`` rows,
    so ``write_rows`` could never see an over-cap sequence and
    ``hand.overflow`` was structurally dead. A hand this large is not
    reachable through ``PlayerCombatState``'s own draw path (it enforces
    ``MAX_HAND_SIZE`` itself), so this uses the same direct-surgery approach
    test 10 uses: append past the cap directly, to exercise the ENCODER's
    response regardless of how the state is reached."""
    s = _combat()
    while len(s.player.hand) <= MAX_HAND:
        s.player.hand.append(make_card("strike"))
    assert len(s.player.hand) > MAX_HAND

    with pytest.warns(UserWarning, match="hand"):
        obs = build_combat_obs(s)
    layout = combat_obs_layout()
    assert obs["f"][layout.f_slices["hand.overflow"]][0] == pytest.approx(1.0)
    # the visible cap rows are still the positional prefix, unaffected.
    ids = obs["i"][layout.i_slices["hand.ids"]].reshape(-1, 3)
    assert len(ids) == MAX_HAND


def test_enemies_overflow_flag_fires_when_encounter_exceeds_cap():
    """A real (if exotic) game state, per the module docstring: "Living
    enemies past MAX_ENEMIES (only reachable via unusually spammy summons)".
    Before the fix this silently hid the extras with ``enemies.overflow``
    stuck at 0.0 — the reviewer's own example was an 8-enemy encounter."""
    dummy = probe_dummy("V4OverflowDummy", hp=5, damage=1)
    encounter = Encounter(id="v4_overflow", monster_classes=[dummy] * (MAX_ENEMIES + 2))
    s = _combat(encounter=encounter)
    assert len(s.enemies) == MAX_ENEMIES + 2

    with pytest.warns(UserWarning, match="enemies"):
        obs = build_combat_obs(s)
    layout = combat_obs_layout()
    assert obs["f"][layout.f_slices["enemies.overflow"]][0] == pytest.approx(1.0)
    eids = obs["i"][layout.i_slices["enemies.ids"]]
    assert len(eids) == MAX_ENEMIES


def test_potions_overflow_flag_fires_when_belt_exceeds_cap():
    """The reviewer's example: a belt grown past ``MAX_POTION_ROWS`` (e.g.
    Phial Holster's 4th slot, or a stacked Potion Belt/Alchemical Coffer —
    see ``MAX_POTION_ROWS``'s own comment in full_env.py for how far that can
    go) silently hid the extra slot with ``potions.overflow`` stuck at 0.0.

    T5a Task 0 widened the observation cap from ``MAX_POTIONS`` (3, the
    belt's DEFAULT size) to ``MAX_POTION_ROWS`` — T5b (Task A, review item 8
    correction) widened that further, from 4 (one belt-growing relic's worth
    of headroom, since found to be undersized) to 10, the true worst case:
    base 3 + Phial Holster's 1 + Potion Belt's 2 + Alchemical Coffer's 4 —
    specifically so a fully-grown belt is no longer silently hidden — so
    this test must overflow past the CURRENT cap, MAX_POTION_ROWS, not any
    stale prior value, to still exercise this flag at all."""
    s = _combat(potions=[make_potion("fire_potion")])
    while len(s.player.potions) <= MAX_POTION_ROWS:
        s.player.potions.append(make_potion("fire_potion"))
    assert len(s.player.potions) == MAX_POTION_ROWS + 1

    with pytest.warns(UserWarning, match="potions"):
        obs = build_combat_obs(s)
    layout = combat_obs_layout()
    assert obs["f"][layout.f_slices["potions.overflow"]][0] == pytest.approx(1.0)
    pids = obs["i"][layout.i_slices["potions.ids"]]
    assert len(pids) == MAX_POTION_ROWS


# ── 9b. Task 0 (T5a brief): the combat potion block vs. a grown belt ────────


def test_potions_block_has_a_row_for_a_grown_4th_belt_slot_matching_the_action_decode():
    """A run holding a belt-growing relic (Phial Holster/Potion Belt/
    Alchemical Coffer — see ``MAX_POTION_ROWS``'s comment) passes its OWN
    ``max_potions`` into ``CombatState`` (run.py:1601), and ``driver.py:267``
    masks combat actions with ``combat_action_masks(combat, run.max_potions)``
    — so a 4-slot belt has a LEGAL potion action for slot 3 the pre-fix
    ``potions`` block (3 rows) had no row for. This builds a `CombatState`
    directly with ``max_potions=4`` and a potion in slot 3 (not through
    ``STS2FullCombatEnv``, which never grows its own belt past 3) and checks
    two things: the observation shows slot 3's potion, and the row index it
    lands on (3) is the exact slot ``decode_combat_action`` maps the
    corresponding potion action onto — the same row-vs-action-index identity
    every other positional block (hand/enemies) is pinned on."""
    potion = make_potion("fire_potion")
    dummy = probe_dummy("V4Potion4SlotDummy", hp=20, damage=5)
    encounter = Encounter(id="v4_potion4", monster_classes=[dummy])
    s = CombatState(
        starting_deck=[make_card("strike") for _ in range(5)] + [make_card("defend") for _ in range(4)],
        encounter=encounter,
        potions=[None, None, None, potion],
        max_potions=4,
    )
    assert s.player.max_potions == 4
    assert len(s.player.potions) == 4
    assert s.player.potions[3] is potion, "fixture regression: potion must be in slot 3"

    obs = build_combat_obs(s)
    layout = combat_obs_layout()
    pids = obs["i"][layout.i_slices["potions.ids"]]
    pf = obs["f"][layout.f_slices["potions.f"]]
    assert len(pids) >= 4, "the block has no row 3 to hold a grown belt's 4th slot"
    assert pids[3] == POTION_INDEX["fire_potion"] + 1
    assert pf[3] == pytest.approx(1.0)   # fire_potion is targeted
    # Slots 0-2 are the explicit PAD rows they always were.
    assert list(pids[:3]) == [0, 0, 0]

    # The row index (3) must be the SAME slot decode_combat_action maps the
    # potion-use action for slot 3 onto — the row-vs-action identity the
    # positional blocks all depend on.
    action = COMBAT_POTION_BASE + 3 * MAX_ENEMIES
    kind, slot, _target = decode_combat_action(action)
    assert (kind, slot) == ("potion", 3)


# ── 10. Padding invariant ─────────────────────────────────────────────────────


def test_padding_invariant_present_at_zero_is_not_absent():
    s = _combat()
    # PowerCmd.apply's normal path REMOVES a power the instant its amount
    # nets to exactly 0 (PowerCmd.cs's ShouldRemoveDueToAmount — verified:
    # applying Strength +5 then -5 empties s.player.powers entirely, even
    # though StrengthPower.allow_negative is True). So a stable "present at
    # amount 0" instance cannot be reached through the command layer for any
    # power; construct one directly (Power.__init__ is pure attribute
    # assignment, no side effects — the same "surgery" probes.py's own
    # module docstring describes) purely to exercise the ENCODER's response
    # to that state, which the padding invariant is about regardless of how
    # a state arises.
    pw = StrengthPower(s.player, 0, s.hooks)
    s.player.powers.add(pw)
    assert s.player.powers["strength"].amount == 0

    obs = build_combat_obs(s)
    layout = combat_obs_layout()
    ids = obs["i"][layout.i_slices["player.powers.ids"]]
    fs = obs["f"][layout.f_slices["player.powers.f"]].reshape(-1, 3)

    strength_id = POWER_INDEX["strength"] + 1
    row = next(i for i, v in enumerate(ids) if v == strength_id)
    assert fs[row][0] == pytest.approx(_signed(0, 10))     # 0.5 ("present at 0")
    assert fs[row][0] != 0.0

    absent_rows = [i for i, v in enumerate(ids) if v == 0]
    assert absent_rows, "the player cannot have 32 real power instances here"
    for i in absent_rows:
        assert np.all(fs[i] == 0.0), "an absent row's floats must be exactly 0.0"


# ── 11. damage_matrix alignment (review item 4) ───────────────────────────────


def test_damage_matrix_cell_matches_decoded_action_with_a_dead_enemy_in_slot_0():
    """The v3 test that covered this (test_full_env.py::test_damage_matrix_
    alignment) is now uncollectable, so the property went dark. Rebuilt here
    directly against ``decode_combat_action``: a nonzero ``damage_matrix``
    cell at (h, e) must be the preview for exactly the card/enemy that action
    ``1 + h*MAX_ENEMIES + e`` decodes to — with a DEAD enemy in slot 0 so a
    packing bug (e.g. the dead slot's column silently absorbing a live
    enemy's data) would show up as a mismatch."""
    s = _combat(deck=["strike"] * 5 + ["defend"] * 4, encounter=INKLETS_NORMAL)
    CreatureCmd.kill(s.hooks, s.enemies[0])
    assert s.enemies[0].is_gone

    obs = build_combat_obs(s)
    layout = combat_obs_layout()
    dm = obs["f"][layout.f_slices["damage_matrix"]].reshape(MAX_HAND, MAX_ENEMIES)

    hand = s.player.hand
    enemies = s.enemies
    for h in range(MAX_HAND):
        for e_i in range(MAX_ENEMIES):
            action = 1 + h * MAX_ENEMIES + e_i
            kind, decoded_h, decoded_e = decode_combat_action(action)
            assert (kind, decoded_h, decoded_e) == ("play", h, e_i), (
                "the cell index must decode back to the SAME (h, e) it was built from")

            if h >= len(hand) or e_i >= len(enemies) or enemies[e_i].is_gone:
                assert dm[h][e_i] == 0.0, f"dead/absent slot ({h},{e_i}) must stay 0"
                continue

            dmg = preview_card_damage(s, hand[h], enemies[e_i])
            if dmg:
                expected = min(1.0, dmg / ABS_SCALE)
                assert dm[h][e_i] == pytest.approx(expected), (
                    f"cell ({h},{e_i}) must be THIS card/enemy pair's preview")
            else:
                assert dm[h][e_i] == 0.0

    # The dead enemy's whole column stays zero regardless of which card.
    assert np.all(dm[:, 0] == 0.0)


# ── 12. write_combat_obs's prefix= contract (review item 4) ──────────────────


def test_write_combat_obs_prefix_contract_matches_build_combat_obs_and_preserves_foreign_segment():
    """The entire reason ``write_combat_obs`` takes ``prefix=`` — so T5's run
    env can fold the combat half into a composite layout alongside its own
    (foreign) segments. Build exactly that composite: a foreign segment,
    then every combat segment name prefixed ``"combat."``, write the combat
    half with ``prefix="combat."``, and check (a) the combat sub-range
    byte-matches a standalone ``build_combat_obs`` call and (b) the foreign
    segment — written first with a sentinel — is completely untouched."""
    s = _combat(deck=["strike"] * 5 + ["defend"] * 4)
    plain = build_combat_obs(s)

    foreign_f_width, foreign_i_width = 7, 5
    composite_f = [("foreign.f", foreign_f_width)] + [
        (f"combat.{name}", width) for name, width in combat_obs_segments_f()
    ]
    composite_i = [("foreign.i", foreign_i_width)] + [
        (f"combat.{name}", width) for name, width in combat_obs_segments_i()
    ]
    layout = ObsLayout(composite_f, composite_i)
    buf = ObsBuffer(layout)
    buf.reset()

    sentinel_f = (np.arange(foreign_f_width, dtype=np.float32) + 1.0) * 0.01
    sentinel_i = np.arange(1, foreign_i_width + 1, dtype=np.int32)
    buf.f[layout.f_slices["foreign.f"]] = sentinel_f
    buf.i[layout.i_slices["foreign.i"]] = sentinel_i

    write_combat_obs(s, buf, prefix="combat.")

    # The combat sub-range (everything after the foreign prefix, since the
    # composite layout places every combat.* segment in the SAME relative
    # order combat_obs_segments_*() declares them) byte-matches a standalone
    # build_combat_obs call.
    np.testing.assert_array_equal(buf.f[foreign_f_width:], plain["f"])
    np.testing.assert_array_equal(buf.i[foreign_i_width:], plain["i"])

    # The foreign segment, written BEFORE write_combat_obs ran, is untouched.
    np.testing.assert_array_equal(buf.f[layout.f_slices["foreign.f"]], sentinel_f)
    np.testing.assert_array_equal(buf.i[layout.i_slices["foreign.i"]], sentinel_i)


# ── 13. card_obs="features" behavioral pin (review item 7) ───────────────────


def test_card_obs_features_blanks_hand_card_id_but_keeps_pile_identity_and_row_presence():
    """Only layout/bounds were parametrized over ``card_obs`` before — this
    pins the actual BEHAVIORAL difference the module docstring promises:
    ``"features"`` blanks ``hand.ids``' card_id column (PAD) while
    ``cards.ids`` (the pile block) keeps card identity in BOTH modes, and a
    present hand row stays distinguishable from a PAD row even with its id
    blanked (via its nonzero floats)."""
    # Bigger than the opening hand draw (5 cards; see item 1's brief note)
    # so cards genuinely remain in draw_pile for the pile-identity check.
    s = _combat(deck=["strike"] * 4 + ["defend"] * 4 + ["bash"] * 4)
    n_hand = len(s.player.hand)
    assert n_hand > 0
    assert len(s.player.draw_pile) > 0, "fixture regression: need a nonempty pile"

    obs_features = build_combat_obs(s, card_obs="features")
    obs_hybrid = build_combat_obs(s, card_obs="hybrid")
    layout_f = combat_obs_layout("features")
    layout_h = combat_obs_layout("hybrid")

    hand_ids_features = obs_features["i"][layout_f.i_slices["hand.ids"]].reshape(-1, 3)
    hand_ids_hybrid = obs_hybrid["i"][layout_h.i_slices["hand.ids"]].reshape(-1, 3)
    for h in range(n_hand):
        assert hand_ids_features[h][0] == 0, "features mode must blank the hand card_id"
        assert hand_ids_hybrid[h][0] != 0, "hybrid mode must keep the hand card_id"

    # The pile block keeps card identity in BOTH modes (never blanked).
    cards_ids_features = obs_features["i"][layout_f.i_slices["cards.ids"]].reshape(-1, 4)
    present = [row for row in cards_ids_features if row[0] != 0]
    assert present, "fixture regression: expect at least one pile card"
    assert all(row[1] != 0 for row in present), (
        "cards.ids must keep card identity even in features mode")

    # A present hand row is still distinguishable from a PAD row in features
    # mode: the id is blanked, but the float row is not all-zero.
    hand_f_features = obs_features["f"][layout_f.f_slices["hand.f"]].reshape(-1, 29)
    for h in range(n_hand):
        assert not np.all(hand_f_features[h] == 0.0), (
            "a present hand row must stay distinguishable from PAD even with id blanked")
    for h in range(n_hand, MAX_HAND):
        assert np.all(hand_f_features[h] == 0.0), "an empty slot is still all-zero"
        assert hand_ids_features[h][0] == 0


# ── 14. AblatedObsEnv copies both halves (review item 8) ──────────────────────


def test_ablated_obs_env_copies_both_halves_not_just_f():
    """full_env.py:1072-1075 copied ``"f"`` (mutated in place just below) but
    handed back ``"i"`` by reference. Safe only because ``build_combat_obs``
    always returns fresh copies today — this pins that a caller mutating a
    returned observation's ``"i"`` half can never retroactively corrupt a
    PREVIOUSLY returned observation from the same env."""
    env = AblatedObsEnv(STS2FullCombatEnv())
    obs1, _ = env.reset(seed=0)
    i1_snapshot = obs1["i"].copy()

    obs2, *_ = env.step(0)
    obs2["i"][:] = 999_999   # mutate the SECOND observation's int half

    # The first observation must be unaffected by mutating the second.
    np.testing.assert_array_equal(obs1["i"], i1_snapshot)
