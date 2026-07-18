"""Phase-0 shared subsystems for the Act-2/3 ancients: the auto-play seam
(CombatState.auto_play) and the six enchantments granted by ancient relics
(Imbued, Goopy, Tezcatara's Ember, Swift, Instinct, Clone). Source:
src/Core/Models/Enchantments/{Imbued,Goopy,TezcatarasEmber,Swift,Instinct,
Clone}.cs."""
import random

from sts2_rl.cards import make_card
from sts2_rl.combat import CombatState
from sts2_rl.enchantments import make_enchantment
from sts2_rl.monsters.overgrowth import ENCOUNTERS

WURM = ENCOUNTERS["fuzzy_wurm_weak"]


def build(deck, seed=0):
    return CombatState(starting_deck=deck, rng=random.Random(seed), encounter=WURM)


# ── Instinct: double attack damage ───────────────────────────────────────
def test_instinct_doubles_attack_damage():
    strike = make_card("strike")
    make_enchantment("instinct").attach(strike)
    combat = build([strike] + [make_card("defend") for _ in range(4)])
    enemy = combat.enemy
    hp = enemy.hp
    combat.play_card(combat.player.hand.index(strike))
    assert hp - enemy.hp == 12  # base 6, ×2


def test_instinct_only_enchants_attacks():
    assert not make_enchantment("instinct").can_enchant(make_card("defend"))
    assert make_enchantment("instinct").can_enchant(make_card("strike"))


# ── Tezcatara's Ember: cost 0, Eternal, +3 damage ────────────────────────
def test_tezcataras_ember_zero_cost_eternal_bonus_damage():
    strike = make_card("strike")
    make_enchantment("tezcataras_ember").attach(strike)
    assert strike.energy_cost == 0
    assert strike.eternal
    combat = build([strike] + [make_card("defend") for _ in range(4)])
    enemy = combat.enemy
    hp = enemy.hp
    combat.play_card(combat.player.hand.index(strike))
    assert hp - enemy.hp == 9  # base 6 + 3


# ── Goopy: Defend gains Exhaust and grows block ──────────────────────────
def test_goopy_grows_block_and_exhausts():
    d = make_card("defend")
    ench = make_enchantment("goopy")
    ench.amount = 2
    ench.attach(d)
    assert d.exhausts
    combat = build([d] + [make_card("strike") for _ in range(4)])
    combat.play_card(combat.player.hand.index(d))
    assert combat.player.block == 6  # base 5 + (amount 2 - 1)
    assert ench.amount == 3          # grows on play
    assert d in combat.player.exhaust_pile


def test_goopy_only_enchants_defends():
    assert not make_enchantment("goopy").can_enchant(make_card("strike"))
    assert make_enchantment("goopy").can_enchant(make_card("defend"))


# ── Swift: draw N the first time the card is played ──────────────────────
def test_swift_draws_on_first_play():
    swift = make_card("strike")
    ench = make_enchantment("swift")
    ench.amount = 2
    ench.attach(swift)
    combat = build([swift] + [make_card("strike") for _ in range(4)])
    # Deterministic piles: only the swift card in hand, cards available to draw.
    combat.player.hand = [swift]
    combat.player.draw_pile = [make_card("strike") for _ in range(3)]
    combat.player.discard_pile = []
    combat.play_card(0)
    assert len(combat.player.hand) == 2  # drew 2 after the play
    assert ench.disabled                 # once per combat


# ── Imbued: the enchanted Skill auto-plays on turn 1 ─────────────────────
def test_imbued_autoplays_skill_on_turn_one():
    d = make_card("defend")
    make_enchantment("imbued").attach(d)
    # 5-card deck: the whole deck is drawn on turn 1, so the imbued Skill is in
    # hand when the post-draw slot fires and auto-plays it.
    combat = build([d] + [make_card("strike") for _ in range(4)])
    assert d in combat.player.discard_pile   # auto-played, not exhausted
    assert d not in combat.player.hand
    assert combat.player.block == 5          # its block resolved


def test_imbued_only_enchants_skills():
    assert not make_enchantment("imbued").can_enchant(make_card("strike"))
    assert make_enchantment("imbued").can_enchant(make_card("defend"))


# ── auto_play seam ───────────────────────────────────────────────────────
def test_auto_play_resolves_without_spending_energy():
    combat = build([make_card("strike") for _ in range(5)])
    energy = combat.player.energy
    strike = combat.player.hand[0]
    enemy = combat.enemy
    hp = enemy.hp
    assert combat.auto_play(strike)
    assert combat.player.energy == energy    # no energy spent
    assert hp - enemy.hp == 6
    assert strike not in combat.player.hand


# ── Clone: inert marker ──────────────────────────────────────────────────
def test_clone_is_inert():
    strike = make_card("strike")
    make_enchantment("clone").attach(strike)
    combat = build([strike] + [make_card("defend") for _ in range(4)])
    enemy = combat.enemy
    hp = enemy.hp
    combat.play_card(combat.player.hand.index(strike))
    assert hp - enemy.hp == 6  # no effect on damage
