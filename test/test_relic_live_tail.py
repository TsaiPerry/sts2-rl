"""Live relic residues from round 7's tail."""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, make_relic
from sts2_rl.cards import CardType, make_card
from sts2_rl.cmds import PowerCmd
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
from sts2_rl.run import RunState


def _combat(relic_ids=(), hand=(), seed: int = 0) -> CombatState:
    cs = CombatState(rng=random.Random(seed),
                     starting_deck=[make_card("strike") for _ in range(5)],
                     encounter=Encounter("test", [LeafSlimeS]),
                     relics=[make_relic(r) for r in relic_ids])
    cs.player.hand.clear()
    for cid in hand:
        card = make_card(cid)
        card.combat = cs
        cs.hooks.register(card)
        cs.player.hand.append(card)
    return cs


# ══════════════════════════════════════════════════════════════════════════
# relic/mummified_hand — the cost the player would actually pay, and the
# four fallback tiers
# ══════════════════════════════════════════════════════════════════════════

def test_mummified_hand_skips_a_card_a_global_modifier_already_freed():
    """MummifiedHand.cs:33/36 filter on `CostsEnergyOrStars(includeGlobal
    Modifiers: true)` = `!CostsX && EnergyCost.GetWithModifiers(All) > 0`
    (CardModel.cs:1578-1592) — the cost the player would pay RIGHT NOW.
    Corruption makes every Skill cost 0 globally, so tier 1 admits only the
    Bash and the game frees the Bash."""
    from sts2_rl.powers import CorruptionPower

    cs = _combat(["mummified_hand"], hand=["defend", "defend", "bash"])
    PowerCmd.apply(cs.hooks, cs.player, CorruptionPower, 1, applier=cs.player)
    relic = cs.relics[0]
    inflame = make_card("inflame")
    inflame.combat = cs
    relic.on_card_played(inflame)
    freed = [c for c in cs.player.hand if c.energy_cost == 0
             and c._free_this_turn]
    assert [c.id for c in freed] == ["bash"]


def test_mummified_hand_falls_back_to_any_hand_card():
    """MummifiedHand.cs:38-45 keeps falling back — tier 3 is `NextItem(list)`
    (BASE cost > 0, however cheap it is now) and tier 4 is `NextItem(cards)`,
    ANY hand card. So the game always picks when the hand is non-empty, and
    `Rng.NextItem` on an empty sequence takes NO draw (Rng.cs:255-265), which
    means exactly ONE card_selection draw from the first non-empty tier."""
    cs = _combat(["mummified_hand"], hand=["dazed", "dazed"])
    relic = cs.relics[0]
    inflame = make_card("inflame")
    inflame.combat = cs
    draws: list[int] = []
    inner = cs.combat_rng._accessors["card_selection"]

    class Counting:
        def choice(self, seq):
            draws.append(len(seq))
            return inner.choice(seq)

        def __getattr__(self, name):
            return getattr(inner, name)

    cs.combat_rng._accessors["card_selection"] = Counting()
    relic.on_card_played(inflame)
    assert len(draws) == 1, "exactly one NextItem, from the first non-empty tier"
    assert any(c._free_this_turn for c in cs.player.hand)


def test_mummified_hand_takes_no_draw_on_an_empty_hand():
    """Every tier is empty, so NextItem is called four times and takes nothing."""
    cs = _combat(["mummified_hand"])
    relic = cs.relics[0]
    inflame = make_card("inflame")
    inflame.combat = cs
    draws: list[int] = []
    inner = cs.combat_rng._accessors["card_selection"]

    class Counting:
        def choice(self, seq):
            draws.append(len(seq))
            return inner.choice(seq)

        def __getattr__(self, name):
            return getattr(inner, name)

    cs.combat_rng._accessors["card_selection"] = Counting()
    relic.on_card_played(inflame)
    assert draws == []


def test_mummified_hand_ignores_a_non_power_play():
    cs = _combat(["mummified_hand"], hand=["defend"])
    cs.relics[0].on_card_played(make_card("strike"))
    assert not any(c._free_this_turn for c in cs.player.hand)


def test_mummified_hand_prefers_a_base_costing_card():
    """Tier 1 is `list.Where(costs now)` where `list` is BASE cost > 0 — so a
    Dazed (base 0) is never the tier-1 pick while a Defend is available."""
    cs = _combat(["mummified_hand"], hand=["dazed", "defend", "dazed"])
    relic = cs.relics[0]
    inflame = make_card("inflame")
    inflame.combat = cs
    relic.on_card_played(inflame)
    freed = [c for c in cs.player.hand if c._free_this_turn]
    assert [c.id for c in freed] == ["defend"]


# ══════════════════════════════════════════════════════════════════════════
# relic/hefty_tablet — the REWARD pool, not the FilterForCombat pool
# ══════════════════════════════════════════════════════════════════════════

def test_hefty_tablet_can_offer_a_combat_ungeneratable_rare():
    """HeftyTablet.cs:29 goes through CardFactory.CreateForReward, whose
    candidate set is `options.GetPossibleCards(player)` =
    `CardPools.SelectMany(GetUnlockedCards)` (CardCreationOptions.cs:168-178) —
    there is NO FilterForCombat on that path (CardFactory.cs:214-224). The port
    used `pool_card_ids()`, the FilterForCombat mirror, so `feed` and `not_yet`
    (both Rare, both `can_be_generated_in_combat = False`) were unreachable AND
    every draw indexed a 23-item list where the game indexes 25."""
    from sts2_rl.cards import CardRarity
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.cards.pool import pool_card_ids, reward_pool_card_ids

    run = RunState(rng=random.Random(0))
    rare = lambda ids: [c for c in ids if _CARD_CLASSES[c].rarity == CardRarity.RARE]
    # The two pools really are different, and by exactly the two cards named.
    assert set(rare(reward_pool_card_ids(pool=run.card_pool))) - set(
        rare(pool_card_ids(pool=run.card_pool))) == {"feed", "not_yet"}

    # And the relic reaches them: over 40 seeds at least one offer is a card the
    # FilterForCombat pool cannot produce.
    seen: set = set()
    for seed in range(40):
        run = RunState(rng=random.Random(seed))
        offered: list = []
        run.card_selector = lambda purpose, cands, n: (offered.extend(cands) or [])
        run.add_relic("hefty_tablet")
        seen.update(c.id for c in offered)
    assert seen & {"feed", "not_yet"}, sorted(seen)


def test_hefty_tablet_offers_three_rares():
    from sts2_rl.cards import CardRarity

    run = RunState(rng=random.Random(0))
    seen: list = []
    run.card_selector = lambda purpose, cands, n: (seen.extend(cands) or [])
    run.add_relic("hefty_tablet")
    assert len(seen) == 3
    assert all(c.rarity == CardRarity.RARE for c in seen)


# ══════════════════════════════════════════════════════════════════════════
# relic/pen_nib — the AttackToDouble == null PREVIEW arm
# ══════════════════════════════════════════════════════════════════════════

def test_pen_nib_previews_the_tenth_attack_doubled():
    """PenNib.cs:120-128 — `if (AttackToDouble == null) { pile = cardSource.Pile;
    if ((pile == null || pile.Type != PileType.Play) && AttacksPlayed == 9)
    return 2m; }`. A card mid-OnPlay is in PileType.Play, so this arm can only be
    taken for a card that is NOT being played — the relic's promise made visible
    on the tenth Attack still sitting in hand. The sim consumes that number in
    its observation vector, not just in a sprite."""
    from sts2_rl.previews import preview_card_damage

    cs = _combat(["pen_nib"], hand=["strike"])
    relic = cs.relics[0]
    relic._attacks_played = 9
    strike = cs.player.hand[0]
    assert preview_card_damage(cs, strike, cs.enemies[0]) == 12


def test_pen_nib_previews_an_earlier_attack_undoubled():
    from sts2_rl.previews import preview_card_damage

    cs = _combat(["pen_nib"], hand=["strike"])
    cs.relics[0]._attacks_played = 3
    assert preview_card_damage(cs, cs.player.hand[0], cs.enemies[0]) == 6


def test_pen_nib_does_not_double_the_played_card_twice():
    """The pile clause is what stops it: the card being played IS in
    PileType.Play, so the null-AttackToDouble arm cannot fire for it and only the
    latched-card arm applies."""
    cs = _combat(["pen_nib"], hand=["strike"])
    relic = cs.relics[0]
    relic._attacks_played = 9
    cs.enemies[0].hp = cs.enemies[0].max_hp = 60
    before = cs.enemies[0].hp
    cs.play_card(0, target_idx=0)
    assert cs.enemies[0].hp == before - 12


# ══════════════════════════════════════════════════════════════════════════
# relic/leafy_poultice — the named Transformations stream
# ══════════════════════════════════════════════════════════════════════════

def test_leafy_poultice_draws_on_the_transformations_stream():
    """LeafyPoultice.cs:36 is `CardCmd.Transform([...], Owner.PlayerRng.
    Transformations)` and its CardTransformations carry no explicit Replacement
    (:30, :34 use the single-argument ctor), so GetReplacement falls through to
    CardFactory.CreateRandomCardForTransform and DOES draw — twice."""
    run = RunState(rng=random.Random(0), string_seed="POULTICE")
    assert run.player_rng is not None
    stream = run.player_rng.transformations
    before = stream.counter
    run.add_relic("leafy_poultice")
    assert stream.counter - before == 2


# ══════════════════════════════════════════════════════════════════════════
# relic/intimidating_helmet — ResourceInfo.EnergyValue is the card's COST
# ══════════════════════════════════════════════════════════════════════════

def test_intimidating_helmet_fires_on_an_auto_played_two_cost_card():
    """ResourceInfo's own doc comment (ResourceInfo.cs:9-16): 'if you auto-play a
    3-energy-cost card, this will be 3, while EnergySpent will be 0'.
    IntimidatingHelmet.cs:26 reads EnergyValue, and CardCmd.cs:123-128 sets it to
    `card.EnergyCost.GetAmountToSpend()` on the auto-play path."""
    cs = _combat(["intimidating_helmet"])
    card = make_card("dark_embrace")
    card.combat = cs
    cs.hooks.register(card)
    cs.player.draw_pile.append(card)
    assert card.energy_cost == 2
    cs.player.block = 0
    cs.auto_play_card(card)
    assert cs.player.block == 4


def test_intimidating_helmet_still_fires_on_a_manual_play():
    """PlayCardAction.cs:94-100 sets EnergySpent and EnergyValue to the same
    number, so the manual path is unchanged."""
    cs = _combat(["intimidating_helmet"], hand=["dark_embrace"])
    cs.player.energy = 3
    cs.player.block = 0
    assert cs.play_card(0)
    assert cs.player.block == 4


def test_intimidating_helmet_ignores_a_cheap_card():
    cs = _combat(["intimidating_helmet"], hand=["strike"])
    cs.player.block = 0
    assert cs.play_card(0, target_idx=0)
    assert cs.player.block == 0


def test_intimidating_helmet_pays_once_per_replay_iteration():
    """C# fires Hook.BeforeCardPlayed INSIDE the play-count loop
    (CardModel.cs:1929), so a Replayed 2-cost card grants the block once per
    iteration. `on_energy_spent` fires once, before the loop."""
    cs = _combat(["intimidating_helmet"], hand=["dark_embrace"])
    cs.player.hand[0].base_replay_count = 1
    cs.player.energy = 3
    cs.player.block = 0
    assert cs.play_card(0)
    assert cs.player.block == 8


# ══════════════════════════════════════════════════════════════════════════
# relic/fur_coat — no act check on the firing, and no Late map pass at all
# ══════════════════════════════════════════════════════════════════════════

def test_fur_coat_marks_still_fire_in_a_later_act():
    """FurCoat.cs has an act check in exactly ONE place — AddMarkedRooms (:64-67),
    which controls only whether the marks get ATTACHED to a map. BeforeCombatStart
    (:114-128) and AfterCreatureAddedToCombat (:130-142) test only
    `GetMarkedCoords().Contains(RunState.CurrentMapPoint.coord)`, and a MapCoord is
    a bare (col, row) pair with no act component. So a coord that recurs in a later
    act fires again, and the sim's `act_index == run.act_index` latch never did."""
    relic = make_relic("fur_coat")
    relic.act_index = 0
    relic.marked_coords = {(3, 5)}

    class _Point:
        coord = (3, 5)

    run = RunState(rng=random.Random(0))
    run.act_index = 1                      # a LATER act
    relic.after_room_entered(run, _Point(), None)
    assert relic._armed is True


def test_fur_coat_does_not_fire_on_an_unmarked_coord():
    relic = make_relic("fur_coat")
    relic.act_index = 0
    relic.marked_coords = {(3, 5)}

    class _Point:
        coord = (4, 5)

    run = RunState(rng=random.Random(0))
    relic.after_room_entered(run, _Point(), None)
    assert relic._armed is False


def test_fur_coat_only_ones_hittable_enemies():
    """FurCoat.cs:121-127 walks `CombatState.HittableEnemies`, not every enemy
    that is not gone."""
    relic = make_relic("fur_coat")
    cs = CombatState(rng=random.Random(0),
                     starting_deck=[make_card("strike") for _ in range(5)],
                     encounter=Encounter("t", [LeafSlimeS, LeafSlimeS]),
                     relics=[relic])
    relic._armed = True
    relic.on_combat_start()
    assert all(e.hp == 1 for e in cs.enemies)


def test_fur_coat_does_not_override_the_late_map_hook():
    """`Hook.ModifyGeneratedMapLate` has exactly ONE caller in the game — the
    SavedActMap branch of RunManager.GenerateMap (RunManager.cs:740, inside `if
    (SavedMapsToLoad != null && ...)`). The branch that GENERATES a map
    (:743-747) runs ModifyGeneratedMap and AfterMapGenerated only; the Late hook
    re-attaches quests to a DESERIALIZED map, and the sim has no save-load.

    So Fur Coat must not re-mark on a fresh generation. The sim still DISPATCHES
    the pass, because card/spoils_map folds its Treasure-coord recording into that
    hook — that mismatch is the card stream's entry, not this relic's."""
    from sts2_rl.relics.base import Relic
    from sts2_rl.relics.fur_coat import FurCoat

    assert "modify_generated_map_late" not in FurCoat.__dict__
    # And it still inherits the base no-op, so the dispatch is harmless.
    relic = make_relic("fur_coat")
    sentinel = object()
    assert relic.modify_generated_map_late(None, sentinel, 0) is sentinel


def test_fur_coat_marks_survive_a_map_regeneration():
    """The marks are set once, by `after_obtained`, and a later generation
    (Golden Compass) must not re-roll them — the game leaves the persisted
    FurCoatCoordCols/Rows arrays alone."""
    relic = make_relic("fur_coat")
    relic.act_index = 0
    relic.marked_coords = {(1, 2), (3, 4)}
    before = set(relic.marked_coords)
    relic.modify_generated_map_late(RunState(rng=random.Random(0)), None, 0)
    assert relic.marked_coords == before


# ══════════════════════════════════════════════════════════════════════════
# relic/tea_of_discourtesy — the pile-orientation bridge
# ══════════════════════════════════════════════════════════════════════════

def test_tea_of_discourtesy_inserts_through_the_shared_helper():
    """CardPileCmd.cs:514 resolves CardPilePosition.Random as
    `Rng.Shuffle.NextInt(targetPile.Cards.Count + 1)`, an index into a pile whose
    TOP is index 0; the sim keeps its top at the END of the list.
    `CardPileCmd.add_to_draw` is the port that carries the bridge (insert at
    `count - p` in a parity run) plus the `_enter_combat` registration, and seven
    other ported sites already call it. The relic hand-rolled the insert and used
    the raw game index as a sim index, so with the stream pinned to NextInt -> 1
    the two Dazed landed near the BOTTOM where the game puts them at the top.

    Pinned by equivalence with the helper rather than by absolute indices,
    because the bridge itself is parity-gated inside `add_to_draw`: what this
    relic got wrong was not calling it."""
    from sts2_rl.cmds import CardPileCmd
    from sts2_rl.rng import RunRngSet

    def _fresh(seed: str):
        relic = make_relic("tea_of_discourtesy")
        cs = CombatState(rng=random.Random(0), rng_set=RunRngSet(seed),
                         starting_deck=[make_card("strike") for _ in range(5)],
                         encounter=Encounter("t", [LeafSlimeS]),
                         relics=[relic])
        cs.player.draw_pile = [make_card("strike") for _ in range(5)]
        for c in cs.player.draw_pile:
            c.combat = cs
        return relic, cs

    # A: the relic does it.
    relic, cs = _fresh("TEAOFD")
    relic.combats_left = 1          # the charge was spent during real setup
    relic.on_combat_start()
    via_relic = [i for i, c in enumerate(cs.player.draw_pile) if c.id == "dazed"]

    # B: two direct add_to_draw calls, same seed, same starting pile.
    _relic2, cs2 = _fresh("TEAOFD")
    for _ in range(2):
        CardPileCmd.add_to_draw(cs2.hooks, cs2.player, make_card("dazed"))
    via_helper = [i for i, c in enumerate(cs2.player.draw_pile) if c.id == "dazed"]

    assert len(via_relic) == 2
    assert via_relic == via_helper
    # And the new cards went through `_enter_combat`.
    assert all(c.combat is cs for c in cs.player.draw_pile if c.id == "dazed")


# ══════════════════════════════════════════════════════════════════════════
# the last four: named streams, an explicit belt slot, and a turn-start slot
# ══════════════════════════════════════════════════════════════════════════

def test_slither_rolls_on_the_combat_energy_costs_stream():
    """Slither.cs:55-62 — `Owner.RunState.Rng.CombatEnergyCosts.NextInt(4)`. The
    port used `combat._rng`, the shared combat Random."""
    from sts2_rl.enchantments import make_enchantment

    cs = CombatState(rng=random.Random(0),
                     starting_deck=[make_card("strike") for _ in range(5)])
    card = make_card("strike")
    ench = make_enchantment("slither")
    ench.attach(card)
    ench.combat = cs
    drawn: list = []
    inner = cs.combat_rng._accessors["energy"]

    class Counting:
        def randrange(self, n):
            drawn.append(n)
            return inner.randrange(n)

        def __getattr__(self, name):
            return getattr(inner, name)

    cs.combat_rng._accessors["energy"] = Counting()
    ench.on_card_drawn(card)
    assert drawn == [4]


def test_phial_holster_draws_on_the_combat_potion_generation_stream():
    """PhialHolster.cs:29 — `CreateRandomPotionsOutOfCombat(Owner, 2,
    RunState.Rng.CombatPotionGeneration)`: per potion a NextFloat for the rarity
    band and a NextItem inside it (PotionFactory.cs:46-81), so FOUR draws."""
    run = RunState(rng=random.Random(0), string_seed="PHIAL")
    stream = run.rng_set.combat_potion_generation
    before = stream.counter
    run.add_relic("phial_holster")
    assert stream.counter - before == 4
    assert sum(1 for p in run.potions if p is not None) == 2


def test_alchemical_coffer_fills_the_new_slots_only():
    """AlchemicalCoffer.cs:22-27 snapshots `originalSlotCount` BEFORE growing the
    belt and procures each potion into `originalSlotCount + i`, so on a fresh
    belt slots 0-2 stay EMPTY and 3-6 fill."""
    run = RunState(rng=random.Random(0), string_seed="COFFER")
    assert run.max_potions == 3
    run.add_relic("alchemical_coffer")
    assert run.max_potions == 7
    assert run.potions[:3] == [None, None, None]
    assert all(p is not None for p in run.potions[3:7])


def test_self_forming_clay_pays_out_in_the_block_clear_pass():
    """SelfFormingClayPower.AfterBlockCleared (SelfFormingClayPower.cs:19-25) is
    turn_structure step ~11, before the energy reset, ModifyHandDraw and the whole
    AfterPlayerTurnStart region. Royal Poison damages its owner from
    AfterPlayerTurnStart (step 22), inside the window — so its damage must be
    banked for the NEXT turn, in either registration order."""
    for order in (["royal_poison", "self_forming_clay"],
                  ["self_forming_clay", "royal_poison"]):
        cs = CombatState(rng=random.Random(0),
                         starting_deck=[make_card("strike") for _ in range(5)],
                         encounter=Encounter("t", [LeafSlimeS]),
                         relics=[make_relic(r) for r in order])
        assert cs.player.block == 0, order


def test_whispering_earring_pushes_a_deterministic_selector():
    """WhisperingEarring.cs:54 wraps its auto-play loop in
    `using (CardSelectCmd.PushSelector(new VakuuCardSelector()))`, and
    VakuuCardSelector.GetSelectedCards is `options.Take(maxSelect)` in row-major
    order — deterministic, and it takes NO RNG draw. The port installed nothing
    and `select_cards` fell through to `self._rng.sample(...)`, so the Earring
    auto-playing Armaments upgraded a different card on every seed where the game
    always upgrades the FIRST option.

    The hand is pinned so the only thing that varies with the seed is the
    SELECTION.
    """
    seen: list = []
    for seed in range(5):
        relic = make_relic("whispering_earring")
        cs = CombatState(rng=random.Random(seed),
                         starting_deck=[make_card("strike") for _ in range(5)],
                         encounter=Encounter("t", [LeafSlimeS]),
                         relics=[relic])
        cs.player.hand.clear()
        for cid in ("armaments", "bash", "twin_strike"):
            card = make_card(cid)
            card.combat = cs
            cs.hooks.register(card)
            cs.player.hand.append(card)
        cs.player.energy = 9
        assert relic.turn == 1
        relic.after_auto_pre_play_phase_entered_late(cs.player)
        upgraded = sorted(c.id for c in cs.player.all_cards
                          if c.upgrade_level > 0)
        seen.append(tuple(upgraded))
    assert len(set(seen)) == 1, seen

    # And the selector the loop installs really is `options.Take(maxSelect)`.
    cs = CombatState(rng=random.Random(0),
                     starting_deck=[make_card("strike") for _ in range(5)],
                     encounter=Encounter("t", [LeafSlimeS]))
    options = [make_card(c) for c in ("bash", "twin_strike", "inflame")]
    cs.card_selector = (
        lambda purpose, candidates, count: list(candidates)[:count])
    assert [c.id for c in cs.select_cards("upgrade", options, 1)] == ["bash"]
    assert [c.id for c in cs.select_cards("upgrade", options, 2)] == [
        "bash", "twin_strike"]


def test_whispering_earring_restores_the_previous_selector():
    """PushSelector is a `using` block — the selector is popped on the way out."""
    marker = lambda purpose, candidates, count: list(candidates)[:count]
    cs = CombatState(rng=random.Random(0),
                     starting_deck=[make_card("strike") for _ in range(5)],
                     encounter=Encounter("t", [LeafSlimeS]),
                     card_selector=marker,
                     relics=[make_relic("whispering_earring")])
    assert cs.card_selector is marker
