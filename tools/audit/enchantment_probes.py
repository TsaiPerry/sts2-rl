"""Reproducible probes for the enchantment content audits (audits/enchantment/**).

Every "executed evidence" number an enchantment record states is produced here,
so a later auditor can re-derive it instead of trusting a throwaway script
(the pattern set by tools/audit/dormancy_probes.py). Each probe prints the sim's
observed value AND the value C# would produce, with the C# line numbers the
expectation is read off.

  py tools/audit/enchantment_probes.py              # every probe
  py tools/audit/enchantment_probes.py order        # one probe

Probes:
  order        gap E1  Enchant*Additive/Multiplicative run BEFORE the two
                       listener loops in C# (Hook.cs:1314-1319 block,
                       Hook.cs:1490-1500 damage); the sim registers the
                       enchantment as an ordinary listener, so its factor is
                       pooled into the same product as everyone else's.
  onplay-slot  gap E2  EnchantmentModel.OnPlay runs AFTER the card's own OnPlay
                       (CardModel.cs:1931 then 1939); Sown/Corrupted are wired
                       to the sim's before_card_played, which fires first.
  replay       gap E3  Enchantment.OnPlay is inside the per-Replay loop
                       (CardModel.cs:1904-1965), so it fires once per replay;
                       the sim's before_card_played / on_card_played fire once
                       per card play.
  imbued       gap E4  Imbued.cs:20-25 auto-plays with no pile check, and
                       CombatManager.cs:657-664 deliberately sinks the card to
                       the BOTTOM of the draw pile first; the sim instead
                       requires it to be in HAND (enchantments.py:261-267).
  goopy        control Goopy.cs:36-40 bumps base.Amount AND
                       base.Card.DeckVersion.Enchantment.Amount, so the growth
                       is permanent -- does the sim's single object match?
  eternal      guard   is the Eternal keyword Tezcatara's Ember grants read by
                       anything in the sim?
  grants       rule 6  every enchantment's ported grant path (reachability).
"""
from __future__ import annotations

import argparse
import random
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from sts2_rl.cards import make_card                                  # noqa: E402
from sts2_rl.cmds import PowerCmd                                    # noqa: E402
from sts2_rl.combat import CombatState                               # noqa: E402
from sts2_rl.enchantments import ALL_ENCHANTMENTS, make_enchantment  # noqa: E402
from sts2_rl.monsters.overgrowth import ENCOUNTERS                   # noqa: E402
from sts2_rl.powers import RupturePower, StrengthPower               # noqa: E402

WURM = ENCOUNTERS["fuzzy_wurm_weak"]


def build(deck, relics=None, seed=0):
    return CombatState(starting_deck=deck, rng=random.Random(seed),
                       encounter=WURM, relics=relics or [])


def enchant(eid, card, amount=1):
    e = make_enchantment(eid)
    e.amount = amount
    e.attach(card)
    return e


def _say(label, observed, expected_cs):
    flag = "MATCH  " if observed == expected_cs else "DIVERGE"
    print(f"  {flag}  {label}: sim={observed!r}  C#={expected_cs!r}")


# -- order: Enchant* runs before the listener loops -----------------------
def probe_order() -> None:
    print("order -- Hook.ModifyDamage applies the enchantment's additive AND "
          "multiplicative before the two listener loops (Hook.cs:1490-1500)")

    def strike_damage(eid, amount, str_stacks):
        strike = make_card("strike")
        enchant(eid, strike, amount)
        combat = build([strike] + [make_card("defend") for _ in range(4)])
        PowerCmd.apply(combat.hooks, combat.player, StrengthPower, str_stacks)
        combat.enemy.hp = 400
        hp = combat.enemy.hp
        combat.play_card(combat.player.hand.index(strike))
        return hp - combat.enemy.hp

    # Instinct x2 on a 6-damage Strike with Strength +3.
    #   C#:  (6 + 0) * 2 = 12, then the additive loop adds Strength 3 -> 15
    #   sim: 6 + (0 + 3) = 9,  then the multiplicative product x2     -> 18
    _say("Instinct(x2) + Strength(+3) on Strike(6)", strike_damage("instinct", 1, 3), 15)
    #   C#:  6 * 1.5 = 9, + 3 -> 12      sim: (6 + 3) * 1.5 = 13.5 -> int 13
    _say("Corrupted(x1.5) + Strength(+3) on Strike(6)", strike_damage("corrupted", 1, 3), 12)
    # Additive-only enchantments are order-insensitive: sum-then-product is the
    # same fold either way, so this control MUST match.
    _say("Sharp(+2) + Strength(+3) on Strike(6) [control]", strike_damage("sharp", 2, 3), 11)


# -- onplay-slot: Enchantment.OnPlay runs after the card's OnPlay ---------
def probe_onplay_slot() -> None:
    print("onplay-slot -- CardModel.cs:1931 `await OnPlay(...)` runs the CARD's "
          "effect; only then does 1939 `await Enchantment.OnPlay(...)` run")

    # Rupture ("gain Strength whenever you lose HP", powers.py:272-289, from the
    # ported Ironclad card cards/rupture_card.py) turns the ordering into a
    # damage number on the SAME play:
    #   C#:  Strike resolves at Strength 0 -> 6 * 1.5 = 9; only afterwards does
    #        Corrupted's 2 self-damage land and Rupture grant +1 Strength.
    #   sim: the self-damage fires from before_card_played, Rupture grants the
    #        Strength first, and the Strike is dealt at Strength 1.
    strike = make_card("strike")
    enchant("corrupted", strike)
    combat = build([strike] + [make_card("defend") for _ in range(4)])
    PowerCmd.apply(combat.hooks, combat.player, RupturePower, 1)
    combat.enemy.hp = 400
    hp = combat.enemy.hp
    combat.play_card(combat.player.hand.index(strike))
    _say("Corrupted Strike with Rupture 1: damage dealt", hp - combat.enemy.hp, 9)

    # Same shape without Corrupted's own multiplier, to show the slot (not the
    # E1 aggregation order) is what moves the number: Sharp's +2 is additive, so
    # E1 cannot contribute, yet Rupture's Strength still lands too early.
    strike = make_card("strike")
    enchant("sharp", strike, 2)
    combat = build([strike] + [make_card("defend") for _ in range(4)])
    PowerCmd.apply(combat.hooks, combat.player, RupturePower, 1)
    combat.enemy.hp = 400
    hp = combat.enemy.hp
    combat.play_card(combat.player.hand.index(strike))
    print(f"  INFO     Sharp Strike with Rupture 1 (no self-damage source): "
          f"{hp - combat.enemy.hp} -- control, Sharp has no OnPlay")


# -- replay: OnPlay is per-Replay-iteration in C# ------------------------
def probe_replay() -> None:
    print("replay -- CardModel.cs:1904 `for (i < playCount)` wraps 1939 "
          "`Enchantment.OnPlay`, so OnPlay fires once PER replay")
    from sts2_rl.relics.throwing_axe import ThrowingAxe

    # Throwing Axe (relics/throwing_axe.py:30-36) replays the combat's first
    # card once more, so playCount == 2 with no enchantment stacking involved.
    strike = make_card("strike")
    enchant("corrupted", strike)
    combat = build([strike] + [make_card("defend") for _ in range(4)],
                   relics=[ThrowingAxe()])
    combat.enemy.hp = 400
    player_hp = combat.player.hp
    combat.play_card(combat.player.hand.index(strike))
    _say("Corrupted + Throwing Axe (2 plays): self-damage taken",
         player_hp - combat.player.hp, 4)

    # Vigorous flips Status in AfterCardPlayed, which C# fires per replay
    # (Vigorous.cs:31-38 + CardModel.cs:1959): iteration 1 gets +8, iteration 2
    # gets nothing. The sim's on_card_played runs once, AFTER the whole loop.
    strike = make_card("strike")
    enchant("vigorous", strike, 8)
    combat = build([strike] + [make_card("defend") for _ in range(4)],
                   relics=[ThrowingAxe()])
    combat.enemy.hp = 400
    hp = combat.enemy.hp
    combat.play_card(combat.player.hand.index(strike))
    _say("Vigorous(8) + Throwing Axe (2 plays): total damage",
         hp - combat.enemy.hp, 6 + 8 + 6)

    # Goopy bumps Amount in AfterCardPlayed, also per replay in C#.
    defend = make_card("defend")
    e = enchant("goopy", defend, 1)
    combat = build([defend] + [make_card("strike") for _ in range(4)],
                   relics=[ThrowingAxe()])
    combat.play_card(combat.player.hand.index(defend))
    _say("Goopy(1) + Throwing Axe (2 plays): Amount after", e.amount, 3)
    _say("Goopy(1) + Throwing Axe (2 plays): block gained",
         combat.player.block, 5 + 6)

    # Swift's Status flips inside OnPlay on the FIRST C# iteration, so both
    # engines draw exactly once -- control.
    strike = make_card("strike")
    enchant("swift", strike, 3)
    combat = build([strike] + [make_card("defend") for _ in range(9)],
                   relics=[ThrowingAxe()])
    combat.enemy.hp = 400
    before = len(combat.player.hand)
    combat.play_card(combat.player.hand.index(strike))
    _say("Swift(3) + Throwing Axe: cards gained [control]",
         len(combat.player.hand) - (before - 1), 3)


# -- imbued: the auto-play has no pile check in C# -----------------------
def probe_imbued() -> None:
    print("imbued -- Imbued.cs:20-25 auto-plays base.Card with NO pile check; "
          "CombatManager.cs:657-664 sinks it to the bottom of the draw pile")
    # A 10-card deck with one Imbued Defend. In C# the Imbued card is moved to
    # the BOTTOM of the draw pile on turn 1 and then auto-played from there, so
    # it ALWAYS resolves. In the sim it resolves only when it happens to be
    # dealt into the opening 5 -- and being in the opening hand is exactly what
    # the C# bottom-of-pile pass exists to prevent.
    fired = 0
    for seed in range(20):
        defend = make_card("defend")
        enchant("imbued", defend)
        combat = build([defend] + [make_card("strike") for _ in range(9)],
                       seed=seed)
        if combat.player.block > 0:      # the Defend resolved
            fired += 1
    _say("Imbued auto-play fired on N of 20 opening hands", fired, 20)


# -- goopy: the deck-version Amount sync ---------------------------------
def probe_goopy() -> None:
    print("goopy -- Goopy.cs:36-40 bumps base.Amount AND "
          "base.Card.DeckVersion.Enchantment.Amount, so the growth is permanent")
    defend = make_card("defend")
    e = enchant("goopy", defend, 1)
    combat = build([defend] + [make_card("strike") for _ in range(4)])
    block_first = combat.player.block
    combat.play_card(combat.player.hand.index(defend))
    block_first = combat.player.block - block_first
    after_one_play = e.amount
    e.reset()                       # what CombatState does at the next combat
    _say("Goopy(1) first-play block (base 5 + Amount-1 = 5)", block_first, 5)
    _say("Goopy Amount surviving the next combat's reset()", e.amount,
         after_one_play)


# -- eternal: is Tezcatara's Ember's keyword modelled? -------------------
def probe_eternal() -> None:
    print("eternal -- TezcatarasEmber.cs:17-18 zeroes the cost and "
          "AddKeyword(CardKeyword.Eternal)")
    strike = make_card("strike")
    enchant("tezcataras_ember", strike)
    print(f"  INFO     card.eternal={getattr(strike, 'eternal', '<no attr>')}, "
          f"cost={strike._energy_cost}")
    out = subprocess.run(["git", "grep", "-n", "-w", "eternal", "--", "sts2_rl"],  # noqa: E501
                         cwd=_REPO, capture_output=True, text=True).stdout
    readers = [ln for ln in out.splitlines()
               if "enchantments.py" not in ln and "= False" not in ln
               and "eternal = True" not in ln]
    print("  non-declaration readers of `eternal` in sts2_rl:")
    for line in readers:
        print("   ", line)


# -- grants: reachability of every enchantment (rule 6) ------------------
def probe_grants() -> None:
    print("grants -- every sim enchantment's ported grant path "
          "(class-name construction OR make_enchantment(id))")
    for eid in sorted(ALL_ENCHANTMENTS):
        cls = ALL_ENCHANTMENTS[eid].__name__
        # A grant is either a direct construction or the id appearing in a
        # choice table the event/relic feeds to make_enchantment (Self Help
        # Book's _CHOICES is the only table form).
        pat = f'make_enchantment\\("{eid}"\\)|{cls}\\(|"{eid}"'
        out = subprocess.run(["git", "grep", "-l", "-E", pat,
                              "--", "sts2_rl/events", "sts2_rl/relics",
                              "sts2_rl/cards"],
                             cwd=_REPO, capture_output=True, text=True).stdout.split()
        srcs = [p for p in out if not p.endswith("enchantments.py")]
        print(f"  {eid:20s} <- {srcs or 'NO GRANT FOUND'}")


# -- slither-rng: which stream does the cost roll come off? ---------------
def probe_slither_rng() -> None:
    print("slither-rng -- Slither.cs:61 rolls on "
          "`Owner.RunState.Rng.CombatEnergyCosts.NextInt(4)`")
    src = (_REPO / "sts2_rl" / "enchantments.py").read_text(encoding="utf-8")
    line = next(ln.strip() for ln in src.splitlines()
                if "set_cost_this_combat" in ln)
    print(f"  sim rolls on: {line}")
    # The sim HAS the stream; potions.py:1049 already uses it for Snecko Oil.
    pot = (_REPO / "sts2_rl" / "potions.py").read_text(encoding="utf-8")
    ref = next(ln.strip() for ln in pot.splitlines()
               if "combat_rng.energy" in ln)
    print(f"  the correct accessor exists and is used elsewhere: {ref}")
    _say("Slither draws off combat_rng.energy", "combat_rng.energy" in line,
         True)


# -- souls-reset: cross-record note on creature_card_cmds step 52 --------
def probe_souls_reset() -> None:
    print("souls-reset -- creature_card_cmds step 52 says the sim never "
          "re-applies the enchantment after a downgrade; does the next "
          "combat's Enchantment.reset() heal it?")
    card = make_card("discovery")
    e = enchant("souls", card)
    after_attach = card.exhausts
    card.upgrade()
    card.downgrade()
    after_downgrade = card.exhausts
    e.reset()                     # what CombatState.__init__ does, combat.py:131
    after_reset = card.exhausts
    print(f"  exhausts after attach={after_attach}, "
          f"after upgrade+downgrade={after_downgrade}, "
          f"after the next combat's reset()={after_reset}")


PROBES = {
    "order": probe_order,
    "onplay-slot": probe_onplay_slot,
    "replay": probe_replay,
    "imbued": probe_imbued,
    "goopy": probe_goopy,
    "eternal": probe_eternal,
    "slither-rng": probe_slither_rng,
    "souls-reset": probe_souls_reset,
    "grants": probe_grants,
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("probe", nargs="?", choices=sorted(PROBES))
    args = ap.parse_args(argv)
    for name in ([args.probe] if args.probe else list(PROBES)):
        print(f"\n=== {name} ===")
        PROBES[name]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
