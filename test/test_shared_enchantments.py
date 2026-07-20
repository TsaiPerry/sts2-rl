"""The four enchantments the shared events grant: Sharp, Nimble, Vigorous
and Corrupted. Source: src/Core/Models/Enchantments/{Sharp,Nimble,Vigorous,
Corrupted}.cs (plan: docs/superpowers/plans/2026-07-19-shared-events.md)."""
import random

from sts2_rl.cards import make_card
from sts2_rl.combat import CombatState
from sts2_rl.enchantments import make_enchantment
from sts2_rl.monsters.overgrowth import ENCOUNTERS

WURM = ENCOUNTERS["fuzzy_wurm_weak"]


def build(deck, seed=0):
    return CombatState(starting_deck=deck, rng=random.Random(seed), encounter=WURM)


def enchant(eid, card, amount=1):
    """make_enchantment + amount, the idiom relics use (BeautifulBracelet)."""
    enchantment = make_enchantment(eid)
    enchantment.amount = amount
    enchantment.attach(card)
    return enchantment


# ── Sharp: +amount damage on Attacks ─────────────────────────────────────
def test_sharp_adds_flat_damage():
    strike = make_card("strike")
    enchant("sharp", strike, 2)
    combat = build([strike] + [make_card("defend") for _ in range(4)])
    enemy = combat.enemy
    hp = enemy.hp
    combat.play_card(combat.player.hand.index(strike))
    assert hp - enemy.hp == 8  # base 6 + 2


def test_sharp_only_enchants_attacks():
    sharp = make_enchantment("sharp")
    assert sharp.can_enchant(make_card("strike"))
    assert not sharp.can_enchant(make_card("defend"))


# ── Nimble: +amount Block on cards that gain block ───────────────────────
def test_nimble_adds_block():
    defend = make_card("defend")
    enchant("nimble", defend, 2)
    combat = build([defend] + [make_card("strike") for _ in range(4)])
    combat.play_card(combat.player.hand.index(defend))
    assert combat.player.block == 7  # base 5 + 2


def test_nimble_requires_gains_block():
    nimble = make_enchantment("nimble")
    assert nimble.can_enchant(make_card("defend"))
    assert nimble.can_enchant(make_card("iron_wave"))     # Attack that blocks
    assert not nimble.can_enchant(make_card("strike"))
    # Entrench gains block with no printed number — GainsBlock is a separate
    # declaration in the source, not derivable from base_block.
    assert make_card("entrench").gains_block
    # Feel No Pain's block belongs to its power, not the card.
    assert not make_card("feel_no_pain").gains_block


# ── Vigorous: +amount damage, once per combat ────────────────────────────
def test_vigorous_bonus_applies_once_then_spends():
    strike, second = make_card("strike"), make_card("strike")
    enchant("vigorous", strike, 8)
    combat = build([strike, second] + [make_card("defend") for _ in range(3)])
    enemy = combat.enemy
    enemy.hp = 200
    hp = enemy.hp
    combat.play_card(combat.player.hand.index(strike))
    assert hp - enemy.hp == 14  # base 6 + 8

    # Same card again (returned to hand via a fresh combat would reset it);
    # here the enchantment is spent for the rest of this combat.
    hp = enemy.hp
    combat.player.hand.append(strike)
    combat.play_card(combat.player.hand.index(strike))
    assert hp - enemy.hp == 6   # bonus spent


def test_vigorous_resets_between_combats():
    strike = make_card("strike")
    enchantment = enchant("vigorous", strike, 8)
    enchantment.disabled = True
    enchantment.reset()
    assert not enchantment.disabled


def test_vigorous_only_enchants_attacks():
    vigorous = make_enchantment("vigorous")
    assert vigorous.can_enchant(make_card("strike"))
    assert not vigorous.can_enchant(make_card("defend"))


# ── Corrupted: 1.5x damage, 2 self-damage per play ───────────────────────
def test_corrupted_multiplies_damage_and_costs_hp():
    strike = make_card("strike")
    enchant("corrupted", strike)
    combat = build([strike] + [make_card("defend") for _ in range(4)])
    enemy = combat.enemy
    hp, player_hp = enemy.hp, combat.player.hp
    combat.play_card(combat.player.hand.index(strike))
    assert hp - enemy.hp == 9                      # base 6 x 1.5
    assert player_hp - combat.player.hp == 2       # OnPlay self-damage


def test_corrupted_self_damage_ignores_block():
    strike = make_card("strike")
    enchant("corrupted", strike)
    combat = build([strike] + [make_card("defend") for _ in range(4)])
    combat.player.block = 20
    player_hp = combat.player.hp
    combat.play_card(combat.player.hand.index(strike))
    assert player_hp - combat.player.hp == 2       # Unblockable
    assert combat.player.block == 20


def test_corrupted_only_enchants_attacks():
    corrupted = make_enchantment("corrupted")
    assert corrupted.can_enchant(make_card("strike"))
    assert not corrupted.can_enchant(make_card("defend"))
