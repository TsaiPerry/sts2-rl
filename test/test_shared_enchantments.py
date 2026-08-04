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


def test_nimble_accepts_a_skill_mad_science_only():
    """Mad Science's GainsBlock is TYPE-dependent — `TinkerTimeType ==
    CardType.Skill` (MadScience.cs:94) — because only the Skill configuration
    gains its 8 block. Nimble's CanEnchant reads exactly that flag, so the
    game accepts a Skill Mad Science and refuses the Attack and Power ones."""
    from sts2_rl.cards.base import CardType

    nimble = make_enchantment("nimble")
    skill = make_card("mad_science").configure(CardType.SKILL, "wisdom")
    attack = make_card("mad_science").configure(CardType.ATTACK, "violence")
    power = make_card("mad_science").configure(CardType.POWER, "curious")

    assert skill.gains_block
    assert nimble.can_enchant(skill)
    assert not attack.gains_block
    assert not nimble.can_enchant(attack)
    assert not power.gains_block
    assert not nimble.can_enchant(power)


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


# ── Royally Approved + Royal Stamp (relic/royal_stamp) ───────────────────


def test_royally_approved_grants_innate_and_retain():
    """RoyallyApproved.cs OnEnchant adds CardKeyword.Innate and
    CardKeyword.Retain."""
    strike = make_card("strike")
    assert not strike.innate and not strike.retain
    enchant("royally_approved", strike)
    assert strike.innate and strike.retain


def test_royally_approved_enchants_attacks_and_skills_only():
    """`CanEnchantCardType` compiles to `(uint)(cardType - 1) <= 1u`, i.e.
    exactly {Attack, Skill} of CardType's None/Attack/Skill/Power/Status/
    Curse/Quest."""
    e = make_enchantment("royally_approved")
    assert e.can_enchant(make_card("strike"))       # Attack
    assert e.can_enchant(make_card("defend"))       # Skill
    assert not e.can_enchant(make_card("inflame"))  # Power


def test_royal_stamp_enchants_a_deck_card_and_burns_the_niche_shuffle():
    """relic/royal_stamp. AfterObtained shuffles the candidates on
    RunState.Rng.Niche (RoyalStamp.cs:36) before the enchant screen, so the
    draw happens whether or not the player picks."""
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    run = RunState(string_seed="89U21BV1TZ")
    before = run.rng_set.niche.counter
    run.add_relic(make_relic("royal_stamp"))
    assert run.rng_set.niche.counter > before
    enchanted = [c for c in run.deck if c.enchantment is not None]
    assert len(enchanted) == 1
    assert enchanted[0].enchantment.id == "royally_approved"
    assert enchanted[0].innate and enchanted[0].retain


def test_a_clone_carries_the_source_s_this_combat_cost():
    """enchantment/EG2's Slither residue. CardModel.DeepCloneFields runs
    `_energyCost = _energyCost?.Clone(this)` (CardModel.cs:1202), and
    CardEnergyCost.Clone copies `_localModifiers` — where `SetThisCombat`
    parks its Absolute/EndOfCombat modifier (CardEnergyCost.cs:238-244). So a
    copy of a Slither card starts at the cost that was already rolled for the
    source; the sim rebuilt the card from its class and showed the printed
    cost instead."""
    from sts2_rl.cards.base import create_clone

    strike = make_card("strike")
    printed = strike.energy_cost
    strike.set_cost_this_combat(printed + 2)
    clone = create_clone(strike)
    assert clone.energy_cost == printed + 2
    assert clone.energy_cost == strike.energy_cost


def test_every_enchantment_answers_enchanted_replay_count():
    """`EnchantmentModel.EnchantPlayCount` is VIRTUAL with a default of
    `originalPlayCount` (EnchantmentModel.cs:456-459), and exactly two
    enchantments override it (Glam.cs, Spiral.cs). The sim shipped the two
    overrides without the base-class default, so `Card.enchanted_replay_count`
    (cards/base.py:310) raised AttributeError on a card carrying any of the
    other 18 — reachable in ordinary play through Hidden Gem's filter
    (`_has_replay_enchantment`, cards/colorless_skills.py:369), which calls it
    on every card in hand.

    Found by the phase-1 powers census, which crashed on it during
    masked-random run play.
    """
    from sts2_rl.enchantments import _ENCHANTMENT_CLASSES

    for eid in sorted(_ENCHANTMENT_CLASSES):
        card = make_card("strike")
        card.enchantment = make_enchantment(eid)
        # The default branch: base_replay_count passes straight through, so a
        # card that is not already replaying reports 0 rather than raising.
        assert card.enchanted_replay_count() == card.base_replay_count, eid
        card.base_replay_count = 1
        assert card.enchanted_replay_count() >= 1, eid


# ── Momentum: +amount damage per play, compounding, Attacks only ─────────
# Source: Momentum.cs — OnPlay adds Amount to a private ExtraDamage counter;
# EnchantDamageAdditive returns that counter on powered attacks;
# CanEnchantCardType restricts it to Attacks. Granted by Punch Dagger (5).

def test_momentum_only_enchants_attacks():
    """`CanEnchantCardType(cardType) => cardType == CardType.Attack`
    (Momentum.cs:31-34)."""
    momentum = make_enchantment("momentum")
    assert momentum.can_enchant(make_card("strike"))
    assert not momentum.can_enchant(make_card("defend"))


def test_momentum_pays_out_from_the_second_play_on():
    """The counter is raised in OnPlay, which CardModel.OnPlayWrapper runs
    AFTER the card's own OnPlay (CardModel.cs:1931 then :1937-1945) — so the
    play that raises it is not the play that benefits. Strike deals 6; with
    Momentum 5 the second play deals 11 and the third 16."""
    strike, second, third = (make_card("strike") for _ in range(3))
    enchant("momentum", strike, 5)
    combat = build([strike, second, third] + [make_card("defend") for _ in range(2)])
    combat.player.energy = 9
    enemy = combat.enemy
    dealt = []
    for _ in range(3):
        hp = enemy.hp
        combat.play_card(combat.player.hand.index(strike))
        dealt.append(hp - enemy.hp)
        combat.player.discard_pile.remove(strike)
        combat.player.hand.append(strike)
    assert dealt == [6, 11, 16]


def test_momentum_starts_each_combat_at_zero():
    """`PopulateCombatState` clones every deck card into the draw pile
    (Player.cs:802-811) and the deck copy never plays, so the counter a
    combat builds up dies with that combat."""
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(3))
    strike = next(c for c in run.deck if c.id == "strike")
    enchant("momentum", strike, 5)
    dealt = []
    for _ in range(2):
        combat = run.create_combat(WURM)
        played = next(c for c in combat.player.all_cards
                      if c.enchantment is not None)
        combat.player.hand.append(played)
        combat.player.energy = 9
        enemy = combat.enemy
        for _ in range(2):
            hp = enemy.hp
            combat.play_card(combat.player.hand.index(played))
            dealt.append(hp - enemy.hp)
            combat.player.discard_pile.remove(played)
            combat.player.hand.append(played)
    assert dealt == [6, 11, 6, 11]


def test_punch_dagger_enchants_a_deck_attack_with_momentum_5():
    """PunchDagger.cs:24-33 — AfterObtained puts up a one-card
    FromDeckForEnchantment screen over the deck's Momentum-eligible cards and
    enchants the pick with `DynamicVar("Momentum", 5)`."""
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(11))
    run.add_relic(make_relic("punch_dagger"))
    enchanted = [c for c in run.deck if c.enchantment is not None]
    assert len(enchanted) == 1
    assert enchanted[0].enchantment.id == "momentum"
    assert enchanted[0].enchantment.amount == 5
    assert enchanted[0].card_type.name == "ATTACK"


def test_a_card_copy_carries_momentums_accumulated_bonus():
    """`ClonePreservingMutability` is `AbstractModel.MutableClone`, a
    MemberwiseClone (CardModel.cs:1204-1209), so a copy made mid-combat —
    Anger's, Trash Heap's — inherits the private ExtraDamage counter, not just
    the Amount."""
    from sts2_rl.cards.base import create_clone

    anger = make_card("anger")
    momentum = enchant("momentum", anger, 5)
    momentum.on_play(anger)
    momentum.on_play(anger)
    clone = create_clone(anger)
    assert clone.enchantment.extra_damage == 10
