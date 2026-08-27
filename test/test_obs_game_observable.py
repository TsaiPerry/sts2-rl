"""SpireBot game-observable schema bump: combat v6 -> v7 (Task 3), run v9 ->
v10 (Task 4).

Per ``docs/superpowers/specs/2026-08-04-spirebot-schema-audit.md``: the audit
found ZERO DROP rows for combat v6 — every segment has a game source. So v7
is a version bump plus the audit's REDEFINE rows implemented exactly as their
proxy states; KEEP/ACCUMULATE segments are unchanged, no segment is added or
removed, and no width changes.

The audit's only REDEFINE row with an actual behavioral consequence in
``sts2_rl/full_env.py`` is ``cards.f``'s ``effective_cost`` field (§1.2,
"cards.f | effective_cost"): out of a live hand, `UpdateDynamicVarPreview`'s
`runGlobalHooks` gate is FALSE, so the game-readable proxy is the card's
PLAIN printed cost — not the hook-modified preview `hand.f` uses. This
matches what ``run_env._run_card_row`` already does for out-of-combat cards.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import Encounter, make_card, make_relic
from sts2_rl.combat import CombatState
from sts2_rl.driver import DecisionKind, DecisionRequest
from sts2_rl.full_env import build_combat_obs, combat_obs_layout
from sts2_rl.probes import probe_dummy
from sts2_rl.run import RunState
from sts2_rl.run_env import RELIC_INDEX, RUN_OBS_SCHEMA_VERSION, STS2RunEnv, run_obs_layout


def _combat() -> CombatState:
    dummy = probe_dummy("V7Dummy", hp=20, damage=5)
    encounter = Encounter(id="v7_single", monster_classes=[dummy])
    return CombatState(
        starting_deck=[make_card("strike") for _ in range(5)] + [make_card("defend") for _ in range(4)],
        encounter=encounter,
    )


class _FlatCostDiscount:
    """A minimal hook listener discounting every card's energy cost by 1
    (floor 0) — stands in for a real Corruption/Tangled-style effect without
    depending on any specific power's port. Deliberately undeclared
    `hook_category` — bare test listeners are an explicitly supported case
    (see `HookSystem._merge_extras`'s docstring)."""

    def modify_card_energy_cost(self, card, cost: int) -> int:
        return max(0, cost - 1)


def test_combat_schema_v7_version():
    from sts2_rl import full_env
    assert full_env.OBS_SCHEMA_VERSION == 8


def test_combat_layout_widths_unchanged_from_v6():
    """The audit found zero DROP rows: v7 changes semantics, not widths."""
    layout = combat_obs_layout()
    total_f = sum(w for _, w in layout.f_segments)
    total_i = sum(w for _, w in layout.i_segments)
    assert total_f == layout.f_dim
    assert total_i == layout.i_dim
    names_f = {name for name, _ in layout.f_segments}
    names_i = {name for name, _ in layout.i_segments}
    assert "cards.f" in names_f
    assert "cards.ids" in names_i


def test_cards_f_effective_cost_is_plain_not_hook_modified():
    """REDEFINE (audit §1.2 `cards.f` / `effective_cost`): draw/discard/
    exhaust pile cards are not in Hand, so the game's `runGlobalHooks` gate
    is false for them — the proxy is the plain printed `energy_cost`, not
    the hook-modified preview `hand.f` legitimately uses for cards actually
    in hand."""
    state = _combat()
    # Every card in the starting deck (strikes + defends) has plain cost 1 —
    # confirmed per-card below so the assertion doesn't rely on an assumed
    # constant.
    plain_costs = {card.energy_cost for card in state.player.draw_pile}
    assert plain_costs == {1}, "fixture assumption: all starting cards cost 1"

    state.hooks.register(_FlatCostDiscount())
    # Sanity: the hook really does discount (would make hand.f's
    # effective_cost 0, not 1) — proves the fixture is capable of catching
    # a regression to hook-modified reads.
    from sts2_rl.previews import preview_card_energy_cost
    assert preview_card_energy_cost(state, state.player.draw_pile[0]) == 0

    layout = combat_obs_layout()
    obs = build_combat_obs(state)
    sl = layout.f_slices["cards.f"]
    n_pile_cards = len(state.player.draw_pile) + len(state.player.discard_pile) + len(state.player.exhaust_pile)
    # cards.f row shape (OBS_SCHEMA.md §5.1/§5.2): (upgrade, effective_cost,
    # affliction_amount, exhaust_on_next_play), 4 floats/row.
    for row_i in range(n_pile_cards):
        base = sl.start + row_i * 4
        effective_cost = obs["f"][base + 1]
        assert effective_cost == 1.0 / 6.0, (
            f"cards.f row {row_i} effective_cost must be the PLAIN printed "
            "cost (REDEFINE, not hook-modified) for pile cards"
        )


def test_cards_f_effective_cost_ignores_live_combat_cost_modifier():
    """Round-4 diagnosis (diag4-combat.md finding 4): C#'s pile-card cost
    field is ``CardModel.EnergyCost.Canonical`` — the printed cost, FIXED at
    construction and immune to every ``LocalCostModifier`` including
    ``SetThisCombat`` (CardEnergyCost.cs). ``card.energy_cost``'s getter
    applies ``_cost_this_combat``/``_free_this_turn``/``_cost_delta_this_turn``
    on top of the printed value, so a card that picked up a whole-combat
    discount while in hand (e.g. Touch of Insanity's "make a card free this
    combat") keeps reading that live value even after moving to discard —
    where the game's Canonical proxy never reflected the discount at all.
    ``second_wind`` in discard reading effective_cost 0 instead of the
    printed 1 is exactly this: the pile-card row must bypass live per-card
    cost modifiers the same way it already bypasses hook modifiers (the test
    above)."""
    state = _combat()
    card = state.player.draw_pile[0]
    assert card.energy_cost == 1, "fixture assumption: plain cost 1"

    # Simulate a whole-combat discount (Touch of Insanity / Slither-style)
    # granted while the card was in hand, then the card is moved to discard —
    # the live modifier legitimately persists (only reset_combat_state clears
    # it), but the pile-card obs row must not read it.
    card.set_cost_this_combat(0)
    assert card.energy_cost == 0, "sanity: the live modifier really does stick"
    state.player.draw_pile.remove(card)
    state.player.discard_pile.append(card)

    layout = combat_obs_layout()
    obs = build_combat_obs(state)
    sl_f = layout.f_slices["cards.f"]
    sl_i = layout.i_slices["cards.ids"]
    ints = obs["i"][sl_i].reshape(-1, 4)
    # ints row = [pile_id, card_id, affliction_id, enchantment_id]; find the
    # one row whose pile_id is discard (2) — that is our modified card, sort
    # order (ascending on the ints tuple) puts every pile_id=1 draw-pile row
    # before it, so row 0 is NOT necessarily the card under test.
    discard_rows = [r for r in range(ints.shape[0]) if ints[r][0] == 2]
    assert len(discard_rows) == 1, "fixture assumption: exactly one discard-pile card"
    row_i = discard_rows[0]
    effective_cost = obs["f"][sl_f.start + row_i * 4 + 1]
    assert effective_cost == 1.0 / 6.0, (
        "cards.f effective_cost must read the PLAIN printed cost for pile "
        "cards, ignoring a live per-card cost modifier the same way it "
        "already ignores hook modifiers"
    )


def test_cards_f_effective_cost_tracks_upgrade_but_not_live_modifier():
    """Round-4 review correction: game source confirms `EnergyCost.Canonical`
    is frozen at construction and does NOT track upgrades — the game-side
    quantity matching `canonical_energy_cost` is actually
    `EnergyCost.GetWithModifiers(CostModifiers.None)` (upgrade-tracking,
    still modifier-immune), and the C# writer is being switched to that read.
    This locks in the chosen sim semantics: an UPGRADED card's reduced cost
    must show in a pile row (Body Slam upgrades 1 -> 0,
    ``sts2_rl/cards/body_slam.py``'s ``_on_upgrade``), while a live
    whole-combat cost modifier still must not."""
    state = _combat()
    card = make_card("body_slam")
    assert card.energy_cost == 1, "fixture assumption: Body Slam's plain cost is 1"
    card.upgrade()
    assert card.energy_cost == 0, "fixture assumption: upgraded Body Slam costs 0"

    # A live whole-combat modifier on top of the upgrade must still be
    # ignored by the pile-card row (same guarantee as the test above), even
    # though it happens to already agree with the upgraded value here — set
    # it to a DIFFERENT number so agreement can't hide a regression.
    card.set_cost_this_combat(3)
    assert card.energy_cost == 3, "sanity: the live modifier overrides the upgraded printed cost"
    assert card.canonical_energy_cost == 0, (
        "canonical_energy_cost must track the upgrade (0) and ignore the "
        "live combat modifier (3)"
    )

    state.player.discard_pile.append(card)
    layout = combat_obs_layout()
    obs = build_combat_obs(state)
    sl_f = layout.f_slices["cards.f"]
    sl_i = layout.i_slices["cards.ids"]
    ints = obs["i"][sl_i].reshape(-1, 4)
    discard_rows = [r for r in range(ints.shape[0]) if ints[r][0] == 2]
    assert len(discard_rows) == 1, "fixture assumption: exactly one discard-pile card"
    row_i = discard_rows[0]
    effective_cost = obs["f"][sl_f.start + row_i * 4 + 1]
    assert effective_cost == 0.0, (
        "cards.f effective_cost for an upgraded pile card must read the "
        "UPGRADED printed cost (0), not the live combat modifier (3)"
    )


# ── Run schema v9 -> v10 (Task 4) ───────────────────────────────────────────
#
# Per the same audit doc, Step "Run observation (v9)": ZERO DROP rows, and
# the two REDEFINE rows (`phase`, `select.purpose.ids`) are BOTH
# documentation-only for this sim — their proxy language describes how a
# future C# `ObsBuilder` will SOURCE the value from live game state, not a
# change to what `sts2_rl/run_env.py` computes today (see
# `RUN_OBS_SCHEMA_VERSION`'s own v10 comment in run_env.py for the full
# reasoning). So there is no behavioral test to write for either REDEFINE —
# v10 is a pure version bump with the embedded combat block moving to v7
# alongside it, EXCEPT for the one real content gap the audit flagged as
# "also noted, out of scope": no `reward.relic.*` segment for the
# `REWARD_RELIC` offer's identity (audit doc, "Net width-change summary" §
# Run schema, item 1). Task B (2026-08-04, Perry-approved, same day as this
# bump) closes that gap as an AMENDMENT to v10 in place — see
# `RUN_OBS_SCHEMA_VERSION`'s own "v10 amendment" comment in run_env.py — so
# `test_run_layout_no_segment_added_removed_or_resized_for_v10` below now
# pins the widths INCLUDING that one amendment, and a new behavioral test
# below drives a `REWARD_RELIC` decision the same way
# `test_reward_relic_block` in `test/test_run_obs_v4.py` does. These tests
# otherwise still pin: the version number, that no OTHER run segment was
# added/removed/resized, and that the embedded `combat.*` block matches
# `full_env.combat_obs_layout()` (the v7 layout) exactly, name-for-name and
# width-for-width, without hard-coding any of the numbers.


def test_run_schema_version():
    assert RUN_OBS_SCHEMA_VERSION == 13


def test_run_layout_embedded_combat_block_matches_v7_layout():
    """The run env folds `full_env.combat_obs_segments_{f,i}()` in verbatim
    under a `"combat."` prefix (`run_obs_layout`'s own docstring) — confirm
    that embedded block is byte-for-byte the v7 combat layout, computed
    programmatically rather than pinned as literal widths."""
    run_layout = run_obs_layout()
    combat_layout = combat_obs_layout()

    embedded_f = [
        (name[len("combat."):], w)
        for name, w in run_layout.f_segments
        if name.startswith("combat.")
    ]
    embedded_i = [
        (name[len("combat."):], w)
        for name, w in run_layout.i_segments
        if name.startswith("combat.")
    ]
    assert embedded_f == combat_layout.f_segments
    assert embedded_i == combat_layout.i_segments
    assert sum(w for _, w in embedded_f) == combat_layout.f_dim
    assert sum(w for _, w in embedded_i) == combat_layout.i_dim


def test_run_layout_no_segment_added_removed_or_resized_beyond_the_ledger():
    """The audit found zero DROP rows and no field additions for run v10
    itself — confirm the FULL segment list (run-only + embedded combat) is
    exactly what v9 already had, PLUS the two deltas since, each of which is
    its own recorded decision rather than a silent drift:

      * v10's Task B amendment — `reward.relic.f`/`reward.relic.ids`, width 1
        each (run_env.py's "v10 amendment" comment): 4710/1464 -> 4711/1465.
      * v11 — `REWARD_CARD_SLOTS` 3 -> 4, one 4-wide row added to each half of
        `reward.cards` (Lasting Candy appends a fourth option; see the
        constant's comment): 4711/1465 -> 4715/1469.
      * v12 — full_env's hand.f row grows by 2 fields (f[29] glow_gold,
        f[30] block_preview_move); MAX_HAND (10) x 2 = +20 f_dim, i_dim
        unchanged: 4715/1469 -> 4735/1469.
      * v13 — `event.options.cards.ids`, the card each event option previews,
        four 16-wide blocks on the INT half only (the event block carried
        just (present, locked) per option, so nothing card-dependent could be
        learned): 4735/1469 -> 4735/1533.
      * v13: event.options.ids + run.ascension (v24 fold). `run.ascension`
        adds a 1-wide float segment: 4735/1533 -> 4736/1533.
    """
    layout = run_obs_layout()
    total_f = sum(w for _, w in layout.f_segments)
    total_i = sum(w for _, w in layout.i_segments)
    assert total_f == layout.f_dim == 4736
    assert total_i == layout.i_dim == 1533
    names_f = {name for name, _ in layout.f_segments}
    names_i = {name for name, _ in layout.i_segments}
    # Spot-check the two REDEFINE segments and a handful of others are still
    # present, unwidened.
    assert "phase" in names_f
    assert "select.purpose.ids" in names_i


def test_run_layout_has_reward_relic_segment_width_1():
    """Task B: the new segment exists, is a sibling of `reward.potion`
    (single scalar id + presence float, NOT a multi-slot block like
    `reward.cards`) because `RunState.offer_relic`/`DecisionRequest.relic`
    always offers exactly one relic at a time, take-or-skip, even when a
    reward set holds several `RelicReward`s (`CombatRewards.relics`)."""
    layout = run_obs_layout()
    names_f = dict(layout.f_segments)
    names_i = dict(layout.i_segments)
    assert names_f["reward.relic.f"] == 1
    assert names_i["reward.relic.ids"] == 1


def test_reward_relic_screen_populates_the_offered_relic_identity():
    """Behavioral (task brief step 1): drive a REWARD_RELIC decision
    offering a known relic and confirm its oid lands in slot 0 of the new
    segment — the SAME slot 0 the take/skip `CHOICE` action (action 0 =
    take) addresses, so identity and action stay index-aligned (task brief
    requirement 2)."""
    relic = make_relic("kunai")
    run = RunState(rng=random.Random(0))
    request = DecisionRequest(kind=DecisionKind.REWARD_RELIC, run=run, relic=relic)
    env = STS2RunEnv()
    env._run = run
    env._request = request
    obs = env._build_obs()
    layout = run_obs_layout()
    assert obs["i"][layout.i_slices["reward.relic.ids"]][0] == RELIC_INDEX["kunai"] + 1
    assert obs["f"][layout.f_slices["reward.relic.f"]][0] == pytest.approx(1.0)
