"""Task 27 / Task 20 — `card/_is_dead_early_return`: dependency-check pins.

Five cards (Blood Wall, Bloodletting, Brand, Hemokinesis, Offering) all deal
self HP loss and then check `if ctx.player.is_dead: return` before continuing
to the rest of their effect. The 2026-07-26 audit records assumed C# has no
such return (true) and that the sim's death-prevention path "floors a saved
creature at 1 HP" so the check is dormant. That premise is now STALE: two
things changed underneath it since (both already staged, both already
covered by `test_combat_ending_command_guards.py`, `power_cmd G6` /
`creature_card_cmds G14`):

  1. `cmds.py:_resolve_death`'s prevented-death arm no longer floors at 1 HP
     -- a prevented death now leaves the creature at 0 HP exactly as
     `CreatureCmd.cs:565-570` does, and the preventer (Lizard Tail, Fairy in
     a Bottle) heals it back up SYNCHRONOUSLY, before `DamageCmd.deal`
     returns to the card. So `ctx.player.is_dead` is only ever True, by the
     time a card checks it, on a genuinely unprevented death.
  2. On an unprevented death, `CombatState.is_over_or_ending` (and
     `.is_ending`) go True IMMEDIATELY -- `player.is_dead` is folded directly
     into `_has_pending_loss` (combat.py) as C#'s stand-in for
     `CreatureCmd.Damage`'s own tail (`CreatureCmd.cs:409` `await
     Kill(killedCreatures)` -> `LoseCombat()`, which also runs SYNCHRONOUSLY
     before `Damage` returns to `OnPlay` in C#). And the commands each of
     these five cards calls next -- `BlockCmd.apply`, `PowerCmd.apply` (via
     `StrengthCmd.apply`), `combat.select_cards` (via `CardSelectCmd.from_hand`),
     `DamageCmd.deal` as attacker -- now ALL self-gate on
     `is_over_or_ending`/`is_ending`/`dealer.is_dead`, mirroring
     `CreatureCmd.GainBlock`'s `IsOverOrEnding` bail (CreatureCmd.cs:637-640),
     `PowerCmd.Apply<T>`'s `IsEnding` bail (PowerCmd.cs:69-72),
     `CardSelectCmd.FromHand`'s `IsOverOrEnding` bail (CardSelectCmd.cs:694),
     and `AttackCommand.Execute`'s `IsOverOrEnding`/`Attacker.IsDead` bails
     (AttackCommand.cs:520,528).

For BLOOD_WALL, BRAND and HEMOKINESIS this makes the `is_dead` guard a
now-redundant, provably-inert duplicate of a check the callee already makes
correctly -- deleting it changes NOTHING observable today (both arms produce
the identical no-op) and is what makes the sim's structure match C#'s (which
has no card-level check at all; the callee's own bail does the work). DELETED
below, pinned by the `*Deleted` test classes -- written and green BEFORE the
line was removed from the card file, and green identically AFTER.

For BLOODLETTING and OFFERING, Task 27 found the first (and, for
Bloodletting, only) downstream call is `EnergyCmd.gain` (cmds.py), which had
NO `is_ending` gate -- `PlayerCmd.GainEnergy`'s `CombatManager.Instance.
IsEnding` bail (PlayerCmd.cs:31) was unported. This is the exact mechanism
already recorded, dormant, at `relic/lantern/g1` ("PlayerCmd.GainEnergy does
five things: bail on amount <= 0, bail on CombatManager.Instance.IsEnding,
... the IsEnding guard is the combat-over guard family"). Deleting the guard
on these two cards WOULD have granted a dying player phantom energy C#
refuses -- a NEW divergence, not a fix -- so Task 27 left them KEPT, isolated
by `TestEnergyCmdGainHasNoEndingGuard`.

Task 20 fixed the root: `EnergyCmd.gain` (cmds.py) now carries the
`is_ending` bail (matching `CardCmd.downgrade`/`upgrade`/`PowerCmd.apply`'s
existing idiom). `TestEnergyCmdGainHasNoEndingGuard` is flipped below to pin
the FIXED behaviour (energy is now withheld, not granted, while the combat
is ending), and Bloodletting/Offering's card-level guards are DELETED --
joining BLOOD_WALL/BRAND/HEMOKINESIS's `*Deleted` pattern, since the callee
now self-gates just like theirs does.
"""
from __future__ import annotations

import random

from sts2_rl import CombatState
from sts2_rl.cards import (
    BloodlettingCard,
    BloodWallCard,
    BrandCard,
    HemokinesisCard,
    OfferingCard,
    StrikeCard,
)
from sts2_rl.cmds import EnergyCmd
from sts2_rl.combat import Phase


# ── Helpers ───────────────────────────────────────────────────────────────

def fresh(seed: int = 0) -> CombatState:
    return CombatState(rng=random.Random(seed))


def combat(deck, seed: int = 0) -> CombatState:
    return CombatState(starting_deck=deck, rng=random.Random(seed))


def play(cs: CombatState, card, target_idx=None, energy: int = 10) -> None:
    cs.player.energy = energy
    cs.player.hand.append(card)
    assert cs.play_card(len(cs.player.hand) - 1, target_idx)


def pick(*cards):
    return lambda purpose, candidates, count: list(cards)


def assert_combat_lost(cs: CombatState) -> None:
    """The shared witness (brief step 2): the killing self-damage really does
    end the fight lost, with `is_dead` genuinely permanent (not floored back
    to 1 -- re-derived, not assumed) -- so nothing downstream of this play
    could observe the skipped half even if it ran."""
    assert cs.player.hp == 0             # NOT floored to 1 -- the old premise
    assert cs.player.is_dead
    assert cs.phase == Phase.COMBAT_OVER
    assert cs.result is not None
    assert cs.result.player_won is False


# ══════════════════════════════════════════════════════════════════════════
# The dependency, isolated and now FIXED: EnergyCmd.gain has an IsEnding bail
# (relic/lantern/g1's mechanism, not power/_death_prevention_branch)
# ══════════════════════════════════════════════════════════════════════════

class TestEnergyCmdGainHasNoEndingGuard:
    def test_energy_is_withheld_while_the_combat_is_ending(self):
        """`PlayerCmd.GainEnergy` bails on `CombatManager.Instance.IsEnding`
        (PlayerCmd.cs:31); `EnergyCmd.gain` (cmds.py) now carries the same
        bail (Task 20), matching `CardCmd.downgrade`/`upgrade`/`PowerCmd.
        apply`'s existing `is_ending` idiom. Contrast with `BlockCmd.apply`/
        `PowerCmd.apply`/`_draw`/`select_cards`, which
        `test_combat_ending_command_guards.py` already pins as correctly
        refusing in this exact window -- EnergyCmd.gain now joins them. This
        is what let Bloodletting and Offering drop their own `is_dead` guard
        below without granting a dead player phantom energy."""
        cs = fresh()
        cs.player.hp = 0
        assert cs.is_over_or_ending
        assert cs.is_ending
        cs.player.energy = 0
        EnergyCmd.gain(cs.hooks, cs.player, 2)
        assert cs.player.energy == 0  # FIXED: was 2 before the is_ending bail


# ══════════════════════════════════════════════════════════════════════════
# DELETED — the guard was a redundant duplicate of a callee-side check
# ══════════════════════════════════════════════════════════════════════════

class TestBloodWallGuardDeleted:
    def test_dying_from_the_hp_loss_still_grants_no_block(self):
        """BlockCmd.apply's own `is_over_or_ending` bail (mirrors
        CreatureCmd.GainBlock's IsOverOrEnding bail, CreatureCmd.cs:637-640)
        makes this a no-op with or without the card's own guard."""
        cs = fresh()
        cs.player.hp = 2          # BloodWallCard._hp_loss
        cs.player.block = 0
        play(cs, BloodWallCard())
        assert_combat_lost(cs)
        assert cs.player.block == 0

    def test_nonlethal_play_is_unaffected(self):
        """Sanity: the ordinary, non-death path (already covered by
        test_ironclad_cards.py::TestBloodWall) still grants block."""
        cs = fresh()
        before = cs.player.hp
        play(cs, BloodWallCard())
        assert cs.player.hp == before - 2
        assert cs.player.block == 16


class TestBrandGuardDeleted:
    def test_dying_from_the_hp_loss_skips_exhaust_and_strength(self):
        """`combat.select_cards`'s own `is_over_or_ending` bail (mirrors
        CardSelectCmd.FromHand's IsOverOrEnding bail, CardSelectCmd.cs:694)
        returns an empty pick before the card ever calls ExhaustCmd.exhaust,
        and `PowerCmd.apply`'s `is_ending` bail (PowerCmd.cs:69-72) refuses
        the Strength -- both with or without the card's own guard."""
        cs = fresh()
        cs.player.hp = 1          # BrandCard._hp_loss
        victim = cs.player.hand[0]
        cs.card_selector = pick(victim)
        play(cs, BrandCard())
        assert_combat_lost(cs)
        assert victim not in cs.player.exhaust_pile
        assert "strength" not in cs.player.powers

    def test_nonlethal_play_is_unaffected(self):
        cs = fresh()
        victim = cs.player.hand[0]
        cs.card_selector = pick(victim)
        play(cs, BrandCard())
        assert victim in cs.player.exhaust_pile
        assert cs.player.powers["strength"].amount == 1


class TestHemokinesisGuardDeleted:
    def test_dying_from_the_hp_loss_lands_no_attack(self):
        """`DamageCmd.deal`'s own `dealer.is_dead` bail (mirrors
        AttackCommand.Execute's Attacker.IsDead / IsOverOrEnding bails,
        AttackCommand.cs:520,528) makes the follow-up attack a no-op with or
        without the card's own guard."""
        cs = fresh()
        cs.player.hp = 2          # HemokinesisCard._hp_loss
        enemy_hp_before = cs.enemy.hp
        play(cs, HemokinesisCard())
        assert_combat_lost(cs)
        assert cs.enemy.hp == enemy_hp_before

    def test_nonlethal_play_is_unaffected(self):
        cs = fresh()
        p_before, e_before = cs.player.hp, cs.enemy.hp
        play(cs, HemokinesisCard())
        assert cs.player.hp == p_before - 2
        assert cs.enemy.hp == e_before - 15


# ══════════════════════════════════════════════════════════════════════════
# DELETED (Task 20) — EnergyCmd.gain's own is_ending bail, above, now makes
# these two a redundant duplicate of a callee-side check too, joining
# BLOOD_WALL/BRAND/HEMOKINESIS above. Assertions are UNCHANGED from the old
# `*GuardKept` classes -- deleting the card-level guard changes nothing
# observable, only WHERE the refusal happens.
# ══════════════════════════════════════════════════════════════════════════

class TestBloodlettingGuardDeleted:
    def test_dying_from_the_hp_loss_still_grants_no_energy(self):
        """EnergyCmd.gain's own is_ending bail (cmds.py, Task 20 -- mirrors
        PlayerCmd.GainEnergy's IsEnding bail, PlayerCmd.cs:31) makes this a
        no-op with or without the card's own guard."""
        cs = fresh()
        cs.player.hp = 3          # BloodlettingCard._hp_loss
        play(cs, BloodlettingCard(), energy=0)
        assert_combat_lost(cs)
        assert cs.player.energy == 0

    def test_nonlethal_play_is_unaffected(self):
        cs = fresh()
        before = cs.player.hp
        play(cs, BloodlettingCard(), energy=3)
        assert cs.player.hp == before - 3
        assert cs.player.energy == 5  # 3 - 0 cost + 2


class TestOfferingGuardDeleted:
    def test_dying_from_the_hp_loss_grants_no_energy_or_draw(self):
        """EnergyCmd.gain's own is_ending bail withholds the energy;
        DrawCmd.draw's pre-existing is_over_or_ending bail (player.py's
        _draw) withholds the draw -- both with or without the card's own
        guard."""
        cs = combat([OfferingCard()])
        cs.player.draw_pile = [StrikeCard(), StrikeCard(), StrikeCard(), StrikeCard()]
        cs.player.hp = 6          # OfferingCard._hp_loss
        cs.player.energy = 0
        hand_before = len(cs.player.hand) - 1  # OfferingCard itself leaves the hand on play
        assert cs.play_card(0)
        assert_combat_lost(cs)
        assert cs.player.energy == 0
        assert len(cs.player.hand) == hand_before

    def test_nonlethal_play_is_unaffected(self):
        cs = combat([OfferingCard()])
        cs.player.draw_pile = [StrikeCard(), StrikeCard(), StrikeCard(), StrikeCard()]
        before = cs.player.hp
        cs.player.energy = 3
        assert cs.play_card(0)
        assert cs.player.hp == before - 6
        assert cs.player.energy == 5
        assert len(cs.player.hand) == 3
