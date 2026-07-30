"""The card tier's residue after round 7's eight batches.

Four shared causes and four singletons, each named by its own queue entry:

* `ShouldOwnerDeathTriggerFatal` — card/feed, card/hand_of_greed,
  power/minion, power/reattach.
* `DamageResult.TotalDamage + OverkillDamage` — card/fisticuffs,
  card/omnislice.
* the return-to-hand pile search — card/bolas, card/thrumming_hatchet.
* the named RNG streams — card/hidden_gem, card/jack_of_all_trades,
  card/jackpot, card/metamorphosis, card/seeker_strike, card/volley.
* card/clash/IsPlayable, card/enlightenment/OnPlay,
  card/frantic_escape/OnPlay.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, DamageCmd, PowerCmd
from sts2_rl.cards import make_card
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
from sts2_rl.powers import MinionPower


def _fresh(deck=None, seed: int = 0, **kw) -> CombatState:
    return CombatState(rng=random.Random(seed), starting_deck=deck, **kw)


def _two(seed: int = 0) -> CombatState:
    return CombatState(rng=random.Random(seed),
                       encounter=Encounter("test", [LeafSlimeS, LeafSlimeS]))


# ══════════════════════════════════════════════════════════════════════════
# ShouldOwnerDeathTriggerFatal
# ══════════════════════════════════════════════════════════════════════════

def test_minion_power_vetoes_the_fatal_trigger():
    """MinionPower.cs:20-23, unconditionally."""
    from sts2_rl.cmds import should_trigger_fatal

    cs = _two()
    victim = cs.enemies[0]
    assert should_trigger_fatal(victim) is True
    PowerCmd.apply(cs.hooks, victim, MinionPower, 1)
    assert should_trigger_fatal(victim) is False


def test_feed_grants_no_max_hp_for_a_minion():
    """Feed.cs:38+42 — Fatal needs BOTH `WasTargetKilled` and the power veto.
    The minion really dies; only the Max HP is suppressed."""
    cs = _two()
    victim = cs.enemies[0]
    victim.hp = 1
    PowerCmd.apply(cs.hooks, victim, MinionPower, 1)
    before = cs.player.max_hp
    make_card("feed").on_play(cs._ctx(), target_idx=0)
    assert victim.is_dead
    assert cs.player.max_hp == before


def test_feed_still_grants_max_hp_for_an_ordinary_enemy():
    cs = _two()
    cs.enemies[0].hp = 1
    before = cs.player.max_hp
    make_card("feed").on_play(cs._ctx(), target_idx=0)
    assert cs.player.max_hp == before + 3


def test_hand_of_greed_grants_no_gold_for_a_minion():
    """HandOfGreed.cs:49 — the same veto."""
    cs = _two()
    victim = cs.enemies[0]
    victim.hp = 1
    PowerCmd.apply(cs.hooks, victim, MinionPower, 1)
    before = cs.gold_gained
    make_card("hand_of_greed").on_play(cs._ctx(), target_idx=0)
    assert victim.is_dead
    assert cs.gold_gained == before


def test_hand_of_greed_still_grants_gold_for_an_ordinary_enemy():
    cs = _two()
    cs.enemies[0].hp = 1
    before = cs.gold_gained
    make_card("hand_of_greed").on_play(cs._ctx(), target_idx=0)
    assert cs.gold_gained == before + 20


# ══════════════════════════════════════════════════════════════════════════
# DamageResult.TotalDamage + OverkillDamage
# ══════════════════════════════════════════════════════════════════════════

def test_fisticuffs_counts_the_blocked_damage():
    """Fisticuffs.cs:32 sums `TotalDamage + OverkillDamage`, and
    `TotalDamage == BlockedDamage + UnblockedDamage` (DamageResult.cs:63)."""
    cs = _two()
    cs.enemies[0].block = 20
    before = cs.player.block
    make_card("fisticuffs").on_play(cs._ctx(), target_idx=0)
    assert cs.player.block == before + 7   # was 0: the block ate the whole hit


def test_fisticuffs_counts_the_overkill():
    cs = _two()
    cs.enemies[0].hp = 5
    before = cs.player.block
    make_card("fisticuffs").on_play(cs._ctx(), target_idx=0)
    assert cs.player.block == before + 7   # 5 unblocked + 2 overkill


def test_omnislice_splashes_the_blocked_damage():
    """Omnislice.cs:39 splashes the same quantity."""
    cs = _two()
    cs.enemies[0].block = 20
    other_hp = cs.enemies[1].hp
    make_card("omnislice").on_play(cs._ctx(), target_idx=0)
    assert other_hp - cs.enemies[1].hp == 8


# ══════════════════════════════════════════════════════════════════════════
# The return-to-hand pile search
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("card_id", ["bolas", "thrumming_hatchet"])
def test_an_exhausted_card_still_returns_to_hand(card_id):
    """Bolas.cs:43-47 tests only `pile.Type != PileType.Hand` and then
    `CardPileCmd.Add(this, PileType.Hand)` — from wherever the card is."""
    card = make_card(card_id)
    cs = _fresh(deck=[card] + [make_card("defend") for _ in range(4)])
    card.combat = cs
    cs.history.on_card_played(card)
    cs.turn += 1
    for pile in (cs.player.hand, cs.player.draw_pile, cs.player.discard_pile):
        if card in pile:
            pile.remove(card)
    cs.player.exhaust_pile.append(card)
    card.on_player_turn_start(cs.player)
    assert card in cs.player.hand
    assert card not in cs.player.exhaust_pile


# ══════════════════════════════════════════════════════════════════════════
# The remaining named streams
# ══════════════════════════════════════════════════════════════════════════

def test_no_card_in_the_pool_draws_on_the_shared_combat_rng():
    """`card_probes.py shared-rng` counts sim card classes that touch
    `combat._rng`. Every one that remains is behind an explicit
    `crng.is_parity` legacy branch, which is the sanctioned shape."""
    import subprocess

    out = subprocess.run(
        ["py", "audit/tools/card_probes.py", "shared-rng"],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
    ).stdout
    listed = {line.split(":")[1].strip()
              for line in out.splitlines() if line.startswith("  ")}
    listed = {c.strip() for entry in listed for c in entry.split(",")}
    # The six this round routed to their named accessors must be gone.
    for card_id in ("hidden_gem", "jack_of_all_trades", "jackpot",
                    "metamorphosis", "seeker_strike", "volley",
                    "anointed", "beat_down", "discovery", "distraction",
                    "splash"):
        assert card_id not in listed, f"{card_id} still draws on combat._rng"


def test_hidden_gem_will_not_stack_on_an_already_replaying_card():
    """`c.GetEnchantedReplayCount() < 1` (CardModel.cs:1129-1132), whose null
    branch returns BaseReplayCount — so a previous Hidden Gem's target is
    excluded, not just a Spiral/Glam-enchanted one."""
    cs = _fresh()
    a, b = make_card("strike"), make_card("defend")
    cs.player.draw_pile = [a, b]
    make_card("hidden_gem").on_play(cs._ctx())
    make_card("hidden_gem").on_play(cs._ctx())
    assert sorted([a.base_replay_count, b.base_replay_count]) == [2, 2]


# ══════════════════════════════════════════════════════════════════════════
# Singletons
# ══════════════════════════════════════════════════════════════════════════

def test_an_auto_played_clash_fires_with_a_mixed_hand():
    """`IsPlayable` is consulted only by `CardModel.CanPlay`, the MANUAL path
    (CardModel.cs:1759-1762). `CardCmd.AutoPlay` checks the Unplayable keyword
    and `Hook.ShouldPlay` alone (CardCmd.cs:57-71), and Clash implements
    neither."""
    clash = make_card("clash")
    cs = _two()
    cs.player.hand = [make_card("defend")]        # a non-Attack in hand
    cs.player.draw_pile = [clash]
    clash.combat = cs
    cs.hooks.register(clash)
    for enemy in cs.enemies:
        enemy.hp = enemy.max_hp = 50   # no overkill, so the number is exact
    hp = sum(e.hp for e in cs.enemies)
    cs.auto_play_card(clash)
    assert hp - sum(e.hp for e in cs.enemies) == 14


def test_a_manually_played_clash_is_still_blocked_by_a_mixed_hand():
    clash = make_card("clash")
    cs = _fresh(deck=[clash] + [make_card("defend") for _ in range(4)])
    assert not cs.hooks.should_play_card(clash)


def test_enlightenment_sets_an_absolute_cost():
    """Enlightenment.cs:21-24 registers an ABSOLUTE LocalCostModifier of 1
    (CardEnergyCost.cs:197-203). A relative delta computed from the cost at
    that instant drifts the moment the card's base cost changes."""
    cs = _fresh()
    victim = make_card("bludgeon")                 # base cost 3
    cs.player.hand = [victim]
    make_card("enlightenment").on_play(cs._ctx())
    assert victim.energy_cost == 1
    victim.upgrade()                               # base cost drops to 2
    assert victim.energy_cost == 1                 # was 0 under a -2 delta


def test_frantic_escapes_cost_bump_ends_with_the_combat():
    """FranticEscape.cs:45 is `EnergyCost.AddThisCombat(1)`, a
    LocalCostModifier with EndOfCombat expiration."""
    card = make_card("frantic_escape")
    cs = _two()
    card.combat = cs
    card.on_play(cs._ctx())
    card.on_play(cs._ctx())
    assert card.energy_cost == 3
    card.reset_combat_state()
    assert card.energy_cost == 1
