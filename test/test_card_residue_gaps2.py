"""Four single-cause card residues from round 7's live tail.

card/breakthrough/OnPlay, card/catastrophe/g1, card/debt/OnTurnEndInHand,
card/drum_of_battle/AfterCardExhausted.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState
from sts2_rl.cards import make_card
from sts2_rl.cmds import ExhaustCmd, PowerCmd
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
from sts2_rl.run import RunState


def _combat(hand=(), draw=(), seed: int = 0) -> CombatState:
    cs = CombatState(rng=random.Random(seed),
                     starting_deck=[make_card("strike") for _ in range(5)],
                     encounter=Encounter("test", [LeafSlimeS, LeafSlimeS]))
    cs.player.hand.clear()
    cs.player.draw_pile.clear()
    cs.player.discard_pile.clear()
    for pile, ids in ((cs.player.hand, hand), (cs.player.draw_pile, draw)):
        for cid in ids:
            card = make_card(cid)
            card.combat = cs
            cs.hooks.register(card)
            pile.append(card)
    return cs


# ══════════════════════════════════════════════════════════════════════════
# card/breakthrough — the self-damage goes through the damage pipeline
# ══════════════════════════════════════════════════════════════════════════

def test_breakthrough_self_damage_fires_after_damage_received():
    """Breakthrough.cs:27 is `CreatureCmd.Damage(..., Unblockable | Unpowered |
    Move, this)` — the full pipeline. Rupture gains Strength off any unblocked
    damage its owner receives (RupturePower.cs:44-57), so it is the witness."""
    from sts2_rl.powers import RupturePower
    cs = _combat(hand=["breakthrough"])
    PowerCmd.apply(cs.hooks, cs.player, RupturePower, 1, applier=cs.player)
    cs.play_card(0)
    assert cs.player.strength == 1


def test_breakthrough_self_damage_ignores_block():
    """ValueProp.Unblockable — the 1 HP goes through even behind block."""
    cs = _combat(hand=["breakthrough"])
    cs.player.block = 20
    hp = cs.player.hp
    cs.play_card(0)
    assert cs.player.hp == hp - 1
    assert cs.player.block == 20


def test_breakthrough_self_damage_is_unpowered():
    """ValueProp.Unpowered — Strength must not scale the 1 HP loss, while the
    AoE half (a plain Move attack) does scale."""
    from sts2_rl.powers import StrengthPower
    cs = _combat(hand=["breakthrough"])
    PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 5, applier=cs.player)
    hp = cs.player.hp
    for e in cs.enemies:
        e.hp = e.max_hp = 60
    before = sum(e.hp for e in cs.enemies)
    cs.play_card(0)
    assert cs.player.hp == hp - 1
    assert sum(e.hp for e in cs.enemies) == before - 2 * (9 + 5)


def test_breakthrough_still_deals_the_aoe_after_the_self_damage():
    cs = _combat(hand=["breakthrough"])
    for e in cs.enemies:
        e.hp = e.max_hp = 60
    cs.play_card(0)
    assert all(e.hp == 51 for e in cs.enemies)


# ══════════════════════════════════════════════════════════════════════════
# card/debt — the sim DOES have gold
# ══════════════════════════════════════════════════════════════════════════

def _debt_combat(player_gold: int) -> tuple[CombatState, object]:
    cs = CombatState(rng=random.Random(0), player_gold=player_gold,
                     starting_deck=[make_card("strike") for _ in range(5)],
                     encounter=Encounter("test", [LeafSlimeS]))
    cs.player.hand.clear()
    debt = make_card("debt")
    debt.combat = cs
    cs.hooks.register(debt)
    cs.player.hand.append(debt)
    return cs, debt


def test_debt_costs_gold_at_end_of_turn():
    """Debt.cs:26-30 — `Mathf.Min(DynamicVars.Gold.IntValue, Owner.Gold)` then
    PlayerCmd.LoseGold. The port's "the sim has no gold" was false: the balance
    lives on the combat and RunState.finish_combat settles it."""
    cs, debt = _debt_combat(55)
    debt.on_turn_end_in_hand(cs._ctx())
    assert cs.gold_spent == 10


def test_debt_is_floored_at_the_gold_you_have():
    """`Mathf.Min(10, Owner.Gold)` — you cannot go into the red."""
    cs, debt = _debt_combat(3)
    debt.on_turn_end_in_hand(cs._ctx())
    assert cs.gold_spent == 3


def test_debt_sees_gold_won_this_combat():
    """`Owner.Gold` is the LIVE balance (PlayerCmd.cs:141-170), the same
    four-term ledger SealOfGold.cs:27 reads."""
    cs, debt = _debt_combat(0)
    cs.gold_gained = 25
    debt.on_turn_end_in_hand(cs._ctx())
    assert cs.gold_spent == 10


def test_debt_with_no_gold_is_a_no_op():
    cs, debt = _debt_combat(0)
    debt.on_turn_end_in_hand(cs._ctx())
    assert cs.gold_spent == 0


def test_debt_settles_into_the_run_at_combat_end():
    """The whole point of the ledger: the loss must actually reach the run."""
    run = RunState(rng=random.Random(0))
    run.gold = 55
    cs = run.create_combat(Encounter("test", [LeafSlimeS]))
    cs.player.hand.clear()
    debt = make_card("debt")
    debt.combat = cs
    cs.hooks.register(debt)
    cs.player.hand.append(debt)
    debt.on_turn_end_in_hand(cs._ctx())
    for e in cs.enemies:
        e.hp = 0
    run.finish_combat(cs)
    assert run.gold == 45


# ══════════════════════════════════════════════════════════════════════════
# card/catastrophe — no loop-level combat-over bail
# ══════════════════════════════════════════════════════════════════════════

def test_catastrophe_burns_a_shuffle_for_every_iteration():
    """Catastrophe.cs has NO loop-level bail: the combat-over check lives one
    level down in CardCmd.AutoPlay (CardCmd.cs:53-56), AFTER the StableShuffle
    pick. So a first pick that ends the combat still costs the remaining
    iterations their full shuffle."""
    cs = CombatState(rng=random.Random(0),
                     starting_deck=[make_card("strike") for _ in range(5)],
                     encounter=Encounter("test", [LeafSlimeS]))
    cs.player.hand.clear()
    cs.player.draw_pile.clear()
    cs.player.discard_pile.clear()
    for pile, ids in ((cs.player.hand, ["catastrophe"]),
                      (cs.player.draw_pile, ["strike", "strike", "strike"])):
        for cid in ids:
            card = make_card(cid)
            card.combat = cs
            cs.hooks.register(card)
            pile.append(card)
    cs.enemies[0].hp = 1        # the FIRST auto-played Strike ends the combat
    shuffles: list[int] = []

    class Counting:
        """Wraps the shuffle stream and counts StableShuffle calls."""

        def __init__(self, inner):
            self._inner = inner

        def shuffle(self, seq):
            shuffles.append(len(seq))
            return self._inner.shuffle(seq)

        def __getattr__(self, name):
            return getattr(self._inner, name)

    cs.combat_rng._accessors["shuffle"] = Counting(cs.combat_rng.shuffle)
    cs.play_card(0)
    assert cs.is_over
    # Two iterations of CardsVar(2): the second pick's StableShuffle must still
    # be paid for even though the first auto-play ended the combat.
    assert len(shuffles) == 2


# ══════════════════════════════════════════════════════════════════════════
# card/drum_of_battle — the play count starts from BaseReplayCount
# ══════════════════════════════════════════════════════════════════════════

def test_drum_of_battle_pays_out_once_per_play_count():
    """DrumOfBattle.cs:35 calls `GeneratePlayCount(CombatState, null)`, which is
    `GetEnchantedReplayCount() + 1` (CardModel.cs:1129-1132, :2015-2021) — so
    Hidden Gem's `BaseReplayCount` doubles the payout. The sim passed a bare 1."""
    cs = _combat(hand=["drum_of_battle"])
    drum = cs.player.hand[0]
    drum.base_replay_count = 1
    cs.player.energy = 0
    ExhaustCmd.exhaust(cs.hooks, cs.player, drum)
    assert cs.player.energy == 4          # 2 twice


def test_drum_of_battle_pays_out_once_normally():
    cs = _combat(hand=["drum_of_battle"])
    drum = cs.player.hand[0]
    cs.player.energy = 0
    ExhaustCmd.exhaust(cs.hooks, cs.player, drum)
    assert cs.player.energy == 2


def test_drum_of_battle_ignores_another_cards_exhaust():
    """`if (card == this ...)` (DrumOfBattle.cs:33)."""
    cs = _combat(hand=["drum_of_battle", "strike"])
    cs.player.energy = 0
    ExhaustCmd.exhaust(cs.hooks, cs.player, cs.player.hand[1])
    assert cs.player.energy == 0
