"""v14 glow-gold hook: mirrors CardModel.ShouldGlowGold (CardModel.cs:830-840).

Port list (Step 1): the game has 17 ShouldGlowGoldInternal overrides in
src\\Core\\Models\\Cards\\; intersected with the sim's Ironclad-reachable pools
(IRONCLAD_POOL | COLORLESS_POOL | CURSE_POOL | STATUS_POOL) that leaves:
dismantle, evil_eye, forgotten_ritual, impatience, pacts_end, restlessness,
spite. The other 10 (bubble_bubble, clash, deaths_door, eidolon, fetch,
flatten, ftl, go_for_the_eyes, grand_finale, heavenly_drill) belong to
characters/pools this sim does not port and are out of scope.

Enchantment side: no EnchantmentModel.ShouldGlowGold override exists anywhere
in src\\Core\\Models\\Enchantments\\*.cs (grep came back empty), so the
enchantment fallback stays the base-class default (False) for every ported
enchantment.
"""
from __future__ import annotations

import random

from sts2_rl import CombatState, make_card
from sts2_rl.monsters import FUZZY_WURM_ENCOUNTER
from sts2_rl.powers import VulnerablePower
from sts2_rl.cmds import PowerCmd


def _combat(deck, encounter=FUZZY_WURM_ENCOUNTER, seed=0):
    return CombatState(starting_deck=deck, rng=random.Random(seed), encounter=encounter)


def test_default_card_never_glows():
    combat = _combat([make_card("strike")])
    card = make_card("strike")
    assert card.should_glow_gold(combat._ctx()) is False


def test_pacts_end_glows_at_three_exhausted():
    # PactsEnd.cs:21-23: glow == exhaust pile count >= Cards var (3)
    combat = _combat([make_card("pacts_end")])
    card = make_card("pacts_end")
    ctx = combat._ctx()
    combat.player.exhaust_pile[:] = [make_card("strike"), make_card("strike")]
    assert card.should_glow_gold(ctx) is False
    combat.player.exhaust_pile.append(make_card("strike"))
    assert card.should_glow_gold(ctx) is True


def test_dismantle_glows_when_hittable_enemy_vulnerable():
    # Dismantle.cs:18: CombatState?.HittableEnemies.Any(e => e.HasPower<VulnerablePower>()) ?? false
    combat = _combat([make_card("dismantle")])
    card = make_card("dismantle")
    ctx = combat._ctx()
    assert card.should_glow_gold(ctx) is False
    PowerCmd.apply(ctx.hooks, ctx.enemies[0], VulnerablePower, 2, applier=ctx.player)
    assert card.should_glow_gold(ctx) is True


def test_evil_eye_glows_when_card_exhausted_this_turn():
    # EvilEye.cs:19,25: WasCardExhaustedThisTurn -- any CardExhaustedEntry this
    # turn belonging to the owner (ported as combat.history.card_exhausted_this_turn())
    combat = _combat([make_card("evil_eye")])
    card = make_card("evil_eye")
    ctx = combat._ctx()
    assert card.should_glow_gold(ctx) is False
    from sts2_rl.cmds import ExhaustCmd
    other = make_card("strike")
    ExhaustCmd.exhaust(ctx.hooks, ctx.player, other)
    assert card.should_glow_gold(ctx) is True


def test_forgotten_ritual_glows_when_card_exhausted_this_turn():
    # ForgottenRitual.cs:19,33: same WasCardExhaustedThisTurn condition as Evil Eye
    combat = _combat([make_card("forgotten_ritual")])
    card = make_card("forgotten_ritual")
    ctx = combat._ctx()
    assert card.should_glow_gold(ctx) is False
    from sts2_rl.cmds import ExhaustCmd
    other = make_card("strike")
    ExhaustCmd.exhaust(ctx.hooks, ctx.player, other)
    assert card.should_glow_gold(ctx) is True


def test_impatience_glows_when_no_attacks_in_hand():
    # Impatience.cs:13: Hand.Cards.All(c => c.Type != CardType.Attack)
    combat = _combat([make_card("impatience")])
    card = make_card("impatience")
    ctx = combat._ctx()
    ctx.player.hand[:] = [make_card("strike")]
    assert card.should_glow_gold(ctx) is False
    ctx.player.hand[:] = [make_card("defend")]
    assert card.should_glow_gold(ctx) is True


def test_restlessness_glows_when_only_card_in_hand():
    # Restlessness.cs:24,26: !Hand.Cards.Except(new[]{this}).Any()
    combat = _combat([make_card("restlessness")])
    card = make_card("restlessness")
    ctx = combat._ctx()
    ctx.player.hand[:] = [card, make_card("strike")]
    assert card.should_glow_gold(ctx) is False
    ctx.player.hand[:] = [card]
    assert card.should_glow_gold(ctx) is True


def test_spite_glows_when_lost_hp_this_turn():
    # Spite.cs:18,46: LostHpThisTurn(owner.creature) -- ported as
    # combat.history.lost_hp_this_turn(player)
    combat = _combat([make_card("spite")])
    card = make_card("spite")
    ctx = combat._ctx()
    assert card.should_glow_gold(ctx) is False
    from sts2_rl.cmds import DamageCmd
    DamageCmd.deal(ctx.hooks, ctx.player, 3, dealer=ctx.enemies[0])
    assert card.should_glow_gold(ctx) is True


def test_enchantment_fallback_defaults_false():
    # EnchantmentModel.ShouldGlowGold default (CardModel.cs:834-837 fallback);
    # no game enchantment overrides it (grep of src/Core/Models/Enchantments
    # for ShouldGlowGold returns nothing), so the base Enchantment class's
    # default must be consulted and return False.
    from sts2_rl.enchantments import Enchantment
    ench = Enchantment()
    card = make_card("strike")
    combat = _combat([make_card("strike")])
    assert ench.should_glow_gold(combat._ctx(), card) is False
