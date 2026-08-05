"""Round 13 (R8) — settling the `relic-2` unlabelled batch.

Each test below pins one of the report's executed claims: a re-confirmed
DORMANT reachability census, a STALE-ALREADY-FIXED behavioural check (the
mechanism the record's `issue` text still described has since been fixed by
other lanes in this round — mostly R1's `hooks.py` listener-derivation rework
and the tier-2 `seam/power_cmd` Task 17/18 rewrite), or a fresh-execution
demonstration of a guard's mechanism.
"""
from __future__ import annotations

import inspect
import pathlib
import random

from sts2_rl import CombatState, make_relic
from sts2_rl.cards import make_card
from sts2_rl.cards.base import _CARD_CLASSES
from sts2_rl.cmds import CreatureCmd, DamageCmd, PowerCmd
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
from sts2_rl.valueprops import DamageProps


def _combat(relic_ids=(), hand=(), seed: int = 0,
            enemy_count: int = 1) -> CombatState:
    cs = CombatState(rng=random.Random(seed),
                     starting_deck=[make_card("strike") for _ in range(10)],
                     encounter=Encounter("test", [LeafSlimeS] * enemy_count),
                     relics=[make_relic(r) for r in relic_ids])
    cs.player.hand.clear()
    for cid in hand:
        card = make_card(cid)
        card.combat = cs
        cs.hooks.register(card)
        cs.player.hand.append(card)
    return cs


# ══════════════════════════════════════════════════════════════════════════
# Shared foundation for bag_of_marbles/G2, charons_ashes/G1, festive_popper/G2
# and letter_opener/G2: all four relics build their target set from
# `Relic.living_enemies()` where the game reads `CombatState.HittableEnemies`.
# Fresh re-derivation (not inherited from R4's already-reviewed
# test_should_allow_hitting_false_always_coincides_with_is_dead): a creature
# `should_allow_hitting` refuses is ALREADY excluded from `living_enemies()`
# too, because every implementer's False case requires `is_reviving`, which
# is armed only from `on_death` and therefore never holds without `is_dead`
# (-> `is_gone`) also holding. Demonstrated here with IllusionPower, the
# implementer every one of this batch's relics is closest to (turn-1/
# any-turn AoE effects with no revival state of their own).
#
# CORRECTION (R8 fix pass, 2026-08-01): the first pass argued the four
# entries were ALSO backstopped on the damage side by `DamageCmd.deal`'s
# `if not hooks.should_allow_hitting(target): return 0`. That was WRONG --
# the line is dead code, dominated by the `if target.is_dead: return 0`
# above it, because the same `is_reviving` implication that makes the
# set-coincidence argument work also guarantees the earlier guard already
# returned. Set-coincidence is the ONLY surviving leg on the damage side.
# The POWER side is different: `PowerCmd.apply` has no `is_dead` guard (C#
# lets a corpse take debuffs -- Creature.cs:308-322), so
# `can_receive_powers`' `should_allow_hitting` half really is load-bearing
# there. See the two tests below.
# ══════════════════════════════════════════════════════════════════════════

def _make_reviving_enemy(cs: CombatState, index: int = 0):
    from sts2_rl.powers import IllusionPower
    enemy = cs.enemies[index]
    PowerCmd.apply(cs.hooks, enemy, IllusionPower, 1)
    DamageCmd.deal(cs.hooks, enemy, 9999, dealer=cs.player)
    assert enemy.is_dead is True
    assert enemy.powers["illusion"].is_reviving is True
    return enemy


def test_should_allow_hitting_false_still_coincides_with_is_gone():
    # A second, untouched enemy keeps combat alive past the reviving
    # enemy's death: with a solo Illusion/Minion-holder (IllusionPower
    # auto-grants MinionPower -> IsPrimaryEnemy false, Creature.cs:245-278),
    # killing it leaves zero living primary enemies, CombatManager.IsEnding
    # (CombatManager.cs:192) goes true, and should_allow_hitting's listener
    # walk is gated off entirely (Hook.cs:2131-2141 via
    # IterateCombatHookListeners, Hook.cs:53-63) -- returning the loop's
    # implicit-default True, not the False this test pins.
    cs = _combat(["bag_of_marbles"], seed=100, enemy_count=2)
    enemy = _make_reviving_enemy(cs)
    assert cs.hooks.should_allow_hitting(enemy) is False
    relic = cs.relics[0]
    # living_enemies() ALREADY excludes it via is_gone -- no observable
    # target-set difference exists for any currently-reachable creature.
    assert enemy not in relic.living_enemies()
    assert enemy not in relic.hittable_enemies()


def test_power_cmd_apply_backstops_bag_of_marbles_against_an_unhittable_target():
    """power_cmd/G6 (the CanReceivePowers backstop inside PowerCmd.apply)
    was FIXED 2026-07-29 (round 5), three days after this record's
    2026-07-26 audit; the record was never revisited. Its premise
    ("PowerCmd.apply does not apply [should_allow_hitting] either... that
    absence is power_cmd G6") is therefore stale. Direct demonstration: even
    a HAND-FED reviving enemy (bypassing living_enemies()'s own exclusion) is
    refused by PowerCmd.apply itself, via `can_receive_powers`
    (cmds.py:65-75, called at PowerCmd.apply's head).

    TWO enemies on purpose. With one enemy, killing it to arm the revive
    makes `is_ending(hooks)` true, and PowerCmd.apply's FIRST guard
    (`if is_ending(hooks): return`, PowerCmd.cs:69-72) returns before
    `can_receive_powers` is ever consulted -- the assertion would then pass
    with the backstop deleted. Mutation-verified in the R8 fix pass: with
    two enemies, replacing `can_receive_powers` with `lambda *_: True` makes
    this test FAIL (Vulnerable lands); with one enemy it passes either way.
    """
    from sts2_rl.powers import VulnerablePower

    cs = _combat(["bag_of_marbles"], seed=101, enemy_count=2)
    enemy = _make_reviving_enemy(cs)
    # The confound this test exists to avoid: the second enemy is untouched,
    # so the combat is NOT ending and PowerCmd.apply runs past its own head.
    assert cs.is_ending is False
    PowerCmd.apply(cs.hooks, enemy, VulnerablePower, 1, applier=cs.player)
    assert "vulnerable" not in enemy.powers


def test_damage_cmd_deal_refuses_the_damage_relics_at_the_is_dead_guard():
    """The damage side has NO independent `should_allow_hitting` backstop:
    `DamageCmd.deal`'s `if not hooks.should_allow_hitting(target): return 0`
    is DEAD CODE, dominated by the `if target.is_dead: return 0` immediately
    above it (CreatureCmd.cs:256-259). Every implementer of the hook
    (powers.py IllusionPower/ReattachPower/AdaptablePower -- `grep -rn "def
    should_allow_hitting" sts2_rl/` finds those three plus the dispatcher and
    nothing else) returns False only when `is_reviving`, which is armed ONLY
    from `on_death` and cleared before HP is restored at all three revive
    sites -- so False implies `is_dead`, and the earlier guard has already
    returned.

    So what this test pins is the guard that actually refuses for
    charons_ashes/festive_popper/letter_opener/forgotten_soul: the dead-target
    one. A plain corpse (dead, `should_allow_hitting` TRUE) takes 0 from the
    exact relic call shape. Mutation-verified in the R8 fix pass: forcing
    `Creature.is_dead` to False makes this FAIL (3 damage lands); neutering
    `should_allow_hitting` to always-True changes NOTHING, which is the
    dead-code fact asserted in the second half.
    """
    # Three enemies: index 0 dies first (the plain corpse under test), index
    # 1 is turned into the reviving enemy for the second half, and index 2
    # is a living primary companion that keeps combat from ending after
    # index 1 dies -- otherwise (as with only 2 enemies) killing index 1
    # would leave zero living primary enemies (IllusionPower auto-grants
    # MinionPower -> IsPrimaryEnemy false, Creature.cs:245-278), making
    # CombatManager.IsEnding true (CombatManager.cs:192) and gating off
    # should_allow_hitting's listener walk (Hook.cs:53-63, :2131-2141)
    # before IllusionPower.should_allow_hitting is ever consulted.
    cs = _combat(["charons_ashes"], seed=102, enemy_count=3)
    corpse = cs.enemies[0]
    DamageCmd.deal(cs.hooks, corpse, 9999, dealer=cs.player)
    assert corpse.is_dead is True
    # No revive power on this one -- the hook is not what refuses.
    assert cs.hooks.should_allow_hitting(corpse) is True
    dealt = DamageCmd.deal(cs.hooks, corpse, 3, dealer=cs.player,
                           props=DamageProps.NON_CARD_UNPOWERED)
    assert dealt == 0

    # The dead-code half: a reviving target (the only creature the hook ever
    # refuses) is refused identically whether or not the hook is consulted.
    reviving = _make_reviving_enemy(cs, index=1)
    assert cs.hooks.should_allow_hitting(reviving) is False
    assert reviving.is_dead is True          # <- why the hook line is dead
    import sts2_rl.hooks as _hooks_mod
    original = _hooks_mod.HookSystem.should_allow_hitting
    try:
        _hooks_mod.HookSystem.should_allow_hitting = lambda self, target: True
        neutered = DamageCmd.deal(cs.hooks, reviving, 3, dealer=cs.player,
                                  props=DamageProps.NON_CARD_UNPOWERED)
    finally:
        _hooks_mod.HookSystem.should_allow_hitting = original
    assert neutered == 0


# ══════════════════════════════════════════════════════════════════════════
# relic/festive_popper/AfterPlayerTurnStart — G3 still real, re-confirmed.
#
# turn_structure's G13 (CheckWinCondition recomputation) closed 2026-07-29,
# but every site it fixed is at TURN-END (after BeforeTurnEnd, closing
# EndPlayerTurnPhaseOneInternal, EndEnemyTurn) -- none of them sits between
# the turn-start hook dispatch and C#'s real CheckWinCondition call
# (CombatManager.cs:573, step 27, after AfterSideTurnStart/orb-tick/auto-
# pre-play). festive_popper's own `_check_win()` still ends combat INSIDE
# `on_player_turn_started`'s own dispatch, strictly earlier.
# ══════════════════════════════════════════════════════════════════════════

def test_festive_popper_check_win_still_ends_combat_inside_its_own_dispatch():
    cs = _combat(["festive_popper"], seed=103)
    relic = cs.relics[0]
    cs.enemies[0].hp = 1
    assert cs.is_over is False
    relic.on_player_turn_started(cs.player)
    # A listener dispatched AFTER the relic in the same walk would already
    # see Phase.COMBAT_OVER here, where C# is still mid AfterPlayerTurnStart
    # (step 22/23), long before its own CheckWinCondition (step 27).
    assert cs.is_over is True


# ══════════════════════════════════════════════════════════════════════════
# relic/gambling_chip/AfterPlayerTurnStart
# ══════════════════════════════════════════════════════════════════════════

def test_is_sly_this_turn_and_give_single_turn_sly_have_zero_consumers():
    """G1 re-confirmed dormant: the Sly-keyword MACHINERY exists
    (cards/base.py's `sly` attribute / `is_sly_this_turn` / `
    give_single_turn_sly`) but has ZERO consumers: no registered card sets
    `sly = True`, and `give_single_turn_sly(` is never called outside its
    own definition anywhere in the package."""
    assert not any(getattr(cls, "sly", False)
                   for cls in _CARD_CLASSES.values())

    pkg_dir = pathlib.Path(__file__).resolve().parents[1] / "sts2_rl"
    call_sites = []
    for path in pkg_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "give_single_turn_sly(" not in text:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if ("give_single_turn_sly(" in line
                    and "def give_single_turn_sly" not in line):
                call_sites.append((path.name, lineno))
    assert call_sites == []


def test_after_card_changed_piles_has_zero_ported_implementers():
    """G2 re-confirmed dormant, STRENGTHENED reasoning: the machinery this
    round's engine lanes wired (hooks.py's `after_card_changed_piles`, now
    dispatched at 6 real call sites, including `CardPileCmd.add_to_discard`
    -- exactly the C# verb `CardCmd.DiscardAndDraw` routes through and
    gambling_chip's raw list mutation does not) has ZERO listeners across
    every registered relic/power/card/potion/enchantment class today.
    book_of_five_rings/bing_bong/darkstone_periapt/lucky_fysh (the record's
    2026-07-26 citation for 'ported implementers') are actually
    `after_card_added_to_deck` listeners -- a DIFFERENT, run-deck-filtered
    hook -- not this one."""
    from sts2_rl.relics import ALL_RELICS
    from sts2_rl.powers import ALL_POWERS
    from sts2_rl.potions import ALL_POTIONS
    from sts2_rl.enchantments import ALL_ENCHANTMENTS

    registries = [ALL_RELICS, ALL_POWERS, _CARD_CLASSES, ALL_POTIONS,
                  ALL_ENCHANTMENTS]
    offenders = []
    for reg in registries:
        for cid, cls in reg.items():
            if (hasattr(cls, "after_card_changed_piles")
                    or hasattr(cls, "after_card_changed_piles_late")):
                offenders.append(cid)
    assert offenders == []


# ══════════════════════════════════════════════════════════════════════════
# relic/hefty_tablet/AfterObtained — G1 and G3 already faithful/closed
# (re-confirmed below). G2 was reported DORMANT; the R8 fix pass OVERTURNS
# that — see test_hefty_tablet_g2_a_reward_options_relic_is_reachable_
# before_its_screen. The census is also ten relics, not the reported seven.
# ══════════════════════════════════════════════════════════════════════════

def test_hefty_tablet_obtain_purpose_is_still_skippable():
    """G3 stays faithful: 'obtain' is still in driver.py's SKIPPABLE_
    PURPOSES, so the sim can still express a declined Hefty Tablet screen."""
    from sts2_rl.driver import SKIPPABLE_PURPOSES
    assert "obtain" in SKIPPABLE_PURPOSES


def test_hefty_tablet_after_obtained_calls_modify_card_reward_options():
    """CardFactory.cs:104-107 dispatches Hook.TryModifyCardRewardOptions
    unconditionally on the CreateForReward path Hefty Tablet uses (it sets
    NoUpgradeRoll, not NoModifyHooks — CardCreationFlags.cs, distinct bits).
    Any of the ten current modify_card_reward_options(_late) implementers
    sees a call when co-held with Hefty Tablet at AfterObtained time. Fixed
    in round 14 (R10, relic/hefty_tablet/AfterObtained) — see
    test/test_r14_hefty_tablet.py for the observable-content pin."""
    import random as _random
    from sts2_rl.run import RunState
    from sts2_rl.relics.base import Relic

    calls = []

    class _Spy(Relic):
        id = "_r8_spy"
        name = "Spy"
        rarity = None

        def modify_card_reward_options(self, run, cards, options=None):
            calls.append(("plain", cards))
            return False

        def modify_card_reward_options_late(self, run, cards, options=None):
            calls.append(("late", cards))
            return False

    run = RunState(rng=_random.Random(0))
    run.relics.append(_Spy())
    tablet = make_relic("hefty_tablet")
    tablet.after_obtained(run)
    assert calls, "Hefty Tablet's screen must dispatch the reward-options hooks"
    assert {kind for kind, _ in calls} == {"plain", "late"}


def _reward_option_implementers():
    """MRO-aware override census for `modify_card_reward_options(_late)`.

    `hasattr` is useless here -- `Relic` DECLARES both methods on the base, so
    `hasattr(cls, ...)` is True for all 258 relics. `cls.__dict__` alone is
    also wrong: the three eggs inherit their override from the intermediate
    `EggRelic` base (`_eggs.py`), so the walk has to stop at `Relic`."""
    from sts2_rl.relics import ALL_RELICS
    from sts2_rl.relics.base import Relic

    out = []
    for rid, cls in ALL_RELICS.items():
        for base in cls.__mro__:
            if base is Relic:
                break
            if ("modify_card_reward_options" in base.__dict__
                    or "modify_card_reward_options_late" in base.__dict__):
                out.append(rid)
                break
    return sorted(out)


def test_reward_option_census_is_ten_relics_not_four_or_seven():
    """The record's 2026-07-26 count was 4 and R8's first pass raised it to 7.
    Both undercount: the MRO-aware census is TEN relic ids across eight
    defining classes. The three eggs share `EggRelic` (invisible to a
    `cls.__dict__` scan) and `lasting_candy` is the only PLAIN-pass
    implementer, which a `_late`-only search misses entirely."""
    from sts2_rl.relics import ALL_RELICS
    from sts2_rl.relics.base import Relic

    # Why `hasattr` cannot be the predicate:
    assert hasattr(Relic, "modify_card_reward_options")
    assert hasattr(Relic, "modify_card_reward_options_late")
    assert all(hasattr(cls, "modify_card_reward_options")
               for cls in ALL_RELICS.values())

    assert _reward_option_implementers() == [
        "fresnel_lens", "frozen_egg", "glitter", "lasting_candy", "lava_lamp",
        "molten_egg", "silken_tress", "silver_crucible", "toxic_egg",
        "wing_charm",
    ]


def test_hefty_tablet_g2_a_reward_options_relic_is_reachable_before_its_screen():
    """**G2 IS NOT DORMANT** (found by the R8 fix pass, 2026-08-01, while
    rewriting the vacuous reachability test the review rejected).

    The report's reachability leg measured the wrong state: a bare
    `RunState()` holds no relics at all, so the loop over `run.relics` never
    ran. The state that matters is the one at the moment Hefty Tablet's
    screen opens, and `run.add_relic` (run.py:821-828) appends the relic and
    THEN calls `after_obtained`, so anything obtained EARLIER is co-held.

    Neow hands out one option, but one of the options is **Neow's Bones**,
    which shuffles the Neow pool and grants TWO of it through `run.add_relic`
    in order (`neows_bones.py:22-31`) -- and `large_capsule`, also in that
    pool, pulls TWO arbitrary grab-bag relics in its own `after_obtained`.
    Four of the ten reward-options implementers sit in the grab bag
    (frozen/molten/toxic egg, lasting_candy) and none of those four is gated
    on `CardCreationFlags.IsCardReward`: `ToxicEgg.cs:21-32` bails only on
    `NoHookUpgrades`, and `HeftyTablet.cs:29` sets `NoUpgradeRoll` -- a
    DIFFERENT flag (`CardCreationFlags.cs:24` vs `:29`). `CardFactory.
    CreateForReward` (`CardFactory.cs:104-107`) really does dispatch
    `Hook.TryModifyCardRewardOptions` on that path.

    Executed observable (scratch probe, R8 fix pass): with Toxic Egg held,
    the sim offers `brand`/`fiend_fire`/`thrash` all un-upgraded, where the
    dropped Late pass upgrades `brand` (the Rare SKILL) to +1.

    This test pins the PRECONDITION -- which stays true after the fix -- not
    the wrong answer."""
    import random as _random
    from sts2_rl.run import RunState
    from sts2_rl.events.neow import neow_relic_pool

    impls = set(_reward_option_implementers())

    run = RunState(rng=_random.Random(0))
    assert run.total_floor == 0
    # Two implementers are in the Neow pool directly (they decline: both gate
    # on IsCardReward, SilverCrucible.cs:104-107 / SilkenTress.cs:53-56)...
    assert sorted(impls & set(neow_relic_pool(run))) == [
        "silken_tress", "silver_crucible"]
    # ...and four are in the grab bag, reachable through Large Capsule, and
    # NONE of those four gates on IsCardReward.
    assert sorted(impls & set(run.relic_grab_bag)) == [
        "frozen_egg", "lasting_candy", "molten_egg", "toxic_egg"]
    assert "large_capsule" in neow_relic_pool(run)
    assert "hefty_tablet" in neow_relic_pool(run)

    # Executed: Large Capsule's own after_obtained really does put one of them
    # in play, so a Neow's Bones draw of [large_capsule, hefty_tablet] hands
    # Hefty Tablet a live reward-options listener.
    reached = []
    for seed in range(40):
        r = RunState(rng=_random.Random(seed))
        r.add_relic("large_capsule")
        landed = impls & {x.id for x in r.relics}
        if landed:
            reached.append((seed, sorted(landed)))
    assert reached, "no seed put a reward-options relic in play via large_capsule"


# ══════════════════════════════════════════════════════════════════════════
# relic/paper_phrog/ModifyVulnerableMultiplier
# ══════════════════════════════════════════════════════════════════════════

def test_paper_phrog_is_still_the_sole_modify_vulnerable_multiplier_implementer():
    """G1 re-confirmed dormant: the sim turns C#'s single direct lookup
    (VulnerablePower.cs:40-44's `dealer.Player?.GetRelic<PaperPhrog>()`)
    into a real hook CHAIN, which would double-apply the +0.25 with a
    second implementer. There is still exactly one.

    Widened per review: an `ALL_RELICS` scan alone would miss a power, card,
    potion, enchantment or monster implementer, so the census is now the
    package-wide `grep -rn "def modify_vulnerable_multiplier" sts2_rl/` the
    report claimed -- the dispatcher in hooks.py plus paper_phrog.py, and
    nothing else."""
    from sts2_rl.relics import ALL_RELICS
    impls = [rid for rid, cls in ALL_RELICS.items()
             if hasattr(cls, "modify_vulnerable_multiplier")]
    assert impls == ["paper_phrog"]

    pkg_dir = pathlib.Path(__file__).resolve().parents[1] / "sts2_rl"
    defs = []
    for path in sorted(pkg_dir.rglob("*.py")):
        for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1):
            if "def modify_vulnerable_multiplier" in line:
                defs.append(path.relative_to(pkg_dir).as_posix())
    assert defs == ["hooks.py", "relics/paper_phrog.py"]


def test_paper_phrog_n2_brand_self_damage_is_not_a_powered_attack():
    """N2 re-confirmed dormant: the one self-damage card whose source
    explicitly names the player as BOTH dealer and target with a real
    `props` argument (Brand: `dealer=ctx.player, props=DamageProps.
    CARD_HP_LOSS`) is still UNPOWERED (CARD_HP_LOSS carries UNPOWERED), so
    it cannot reach PaperPhrog's dormant target-check gap (a POWERED
    player-on-player self-attack). The other 12 self-damage sites (read
    directly: blood_wall/bloodletting/burn/decay/hemokinesis/infection/
    offering/regret/toxic/wither/bad_luck/beckon) each pass `dealer=None`
    or `DamageProps.CARD_HP_LOSS` too -- none combines a player dealer with
    powered props."""
    from sts2_rl.valueprops import is_powered_attack
    import sts2_rl.cmds as cmds_mod

    recorded = []
    # Do NOT reach into `DamageCmd.__dict__["deal"].__func__`: a sibling test
    # file (test_r13_relic1.py:301) restores its own spy with
    # `DamageCmd.deal = original_deal`, i.e. the UNWRAPPED function, so by the
    # time a full-suite run reaches this test the class-dict entry is a plain
    # function and `.__func__` raises AttributeError. Class-attribute access
    # yields the plain callable for BOTH shapes, and the raw entry is saved so
    # the restore is exact rather than lossy.
    raw_entry = cmds_mod.DamageCmd.__dict__["deal"]
    original_deal = cmds_mod.DamageCmd.deal

    def spy_deal(hooks, target, amount, dealer=None, card=None, props=None,
                 result=None):
        recorded.append((target, dealer, props))
        return original_deal(hooks, target, amount, dealer=dealer, card=card,
                             props=props, result=result)

    cmds_mod.DamageCmd.deal = staticmethod(spy_deal)
    try:
        cs = _combat(hand=["brand"], seed=104)
        cs.play_card(0)
    finally:
        cmds_mod.DamageCmd.deal = raw_entry

    player_self_hits = [(t, d, p) for (t, d, p) in recorded
                         if t is cs.player and d is cs.player]
    assert player_self_hits  # the census actually observed Brand's self-hit
    for _target, _dealer, props in player_self_hits:
        assert not is_powered_attack(props)


# ══════════════════════════════════════════════════════════════════════════
# relic/philosophers_stone/AfterCreatureAddedToCombat
# ══════════════════════════════════════════════════════════════════════════

def test_on_creature_added_only_ever_reaches_combat_enemies():
    """G1 re-confirmed dormant: C# skips creatures on the OWNER'S SIDE
    (PhilosophersStone.cs:43); the sim skips only the player OBJECT
    (philosophers_stone.py:39). The sim models exactly one player-side
    creature (the player itself) and `CreatureCmd.add`'s only destination is
    `combat.enemies` -- there is no code path that could add a second
    player-side creature for the side-vs-identity distinction to bite on."""
    cs = _combat(["philosophers_stone"], seed=105)
    before = len(cs.enemies)
    joiner = LeafSlimeS(cs.hooks, random.Random(6))
    CreatureCmd.add(cs.hooks, joiner)
    assert joiner in cs.enemies
    assert len(cs.enemies) == before + 1
    assert joiner.powers["strength"].amount == 1


# ══════════════════════════════════════════════════════════════════════════
# relic/ruined_helmet — BOTH entries flip DORMANT -> STALE-ALREADY-FIXED.
#
# seam/power_cmd.json's guards G3 ("C#'s three ordered phases... collapsed
# into one registration-order-dependent chain") and G4 ("No
# AfterModifyingPowerAmountGiven/Received companion-event machinery") both
# read "Closed 2026-07-31 (tier-2 campaign)" -- the exact two gaps
# ruined_helmet's own guards G2 and G3 cited by name ("This is audit/
# records/seam/power_cmd.json gap G3/G4 at the site that record already
# names"). ruined_helmet.py has been rewritten to match: it now implements
# `modify_power_amount_received` (a real single-pass override-or-decline
# listener on the RECEIVED chain, dispatched separately from the GIVEN
# chain) and `after_modify_power_amount_received` (a real companion event,
# fired only when the modifier actually changed something) instead of one
# collapsed method that both decided the doubling AND hand-inlined the
# "mark used" side effect.
# ══════════════════════════════════════════════════════════════════════════

def test_ruined_helmet_doubles_once_via_the_real_received_chain():
    from sts2_rl.powers import StrengthPower

    cs = _combat(["ruined_helmet"], seed=106)
    relic = cs.relics[0]
    assert relic._used is False
    PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 2, applier=cs.player)
    assert cs.player.powers["strength"].amount == 4
    assert relic._used is True
    # Second application: the received-chain now declines (already used),
    # matching the record's own already-executed probe (first +2 -> 4,
    # second +2 -> 2, total 6).
    PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 2, applier=cs.player)
    assert cs.player.powers["strength"].amount == 6


def test_ruined_helmet_mark_used_lives_in_the_companion_event_not_the_modifier():
    """Calling the MODIFIER alone must not spend the charge -- proving the
    'mark used' side effect really lives in `after_modify_power_amount_
    received` (RuinedHelmet.cs:55-60's own hook, fired only for listeners
    whose Try returned true), not folded into the modifier as it used to
    be. (`PowerCmd.cs:148-152`/`:238-242` are the two dispatch sites;
    `PowerCmd.cs:55-60` -- what this docstring used to cite -- is unrelated
    code.)"""
    from sts2_rl.powers import StrengthPower

    cs = _combat(["ruined_helmet"], seed=107)
    relic = cs.relics[0]
    result = relic.modify_power_amount_received(
        StrengthPower, cs.player, 2, cs.player,
    )
    assert result == 4
    assert relic._used is False
    relic.after_modify_power_amount_received(None)
    assert relic._used is True


# ══════════════════════════════════════════════════════════════════════════
# relic/spiked_gauntlets/TryModifyEnergyCostInCombat
#
# G1 (cross-listener order, Powers before Relics) was already reconciled
# faithful 2026-07-28 (Task 0), predating this round. G2 (the missing
# plain/Late two-pass structure) is a FRESH closure this round: `_each`
# generalized the phase machinery to EVERY hook a registered listener
# phases into (hooks.py `_PHASES`/`_phased`), not just the two hooks the sim
# used to hand-roll -- `modify_card_energy_cost` gets the plain-then-Late
# shape for free the moment any listener (BrilliantScarf) defines
# `modify_card_energy_cost_late`. G3 (X-cost bail / owner guard / final
# clamp) stays open, re-confirmed dormant below.
# ══════════════════════════════════════════════════════════════════════════

def test_spiked_gauntlets_g2_phase_machinery_now_generic_via_each():
    from sts2_rl.powers import CuriousPower

    cs = _combat(["spiked_gauntlets", "brilliant_scarf"], seed=108)
    PowerCmd.apply(cs.hooks, cs.player, CuriousPower, 2, applier=cs.player)
    scarf = next(r for r in cs.relics if r.id == "brilliant_scarf")
    scarf.cards_played_this_turn = scarf.CARDS - 1     # the 5th card this turn
    power_card = make_card("inflame")                  # 1-cost Power card
    # C#'s own worked example: plain pass gives 1+1=2 (Curious floors at 0,
    # Spiked Gauntlets then adds 1); Brilliant Scarf's Late pass zeroes it
    # regardless. Both engines now land on 0.
    assert cs.hooks.modify_card_energy_cost(
        power_card, power_card.energy_cost) == 0
    # Isolated (no Scarf, no phase): Curious floors 1-2 at 0, Spiked adds 1.
    cs2 = _combat(["spiked_gauntlets"], seed=109)
    PowerCmd.apply(cs2.hooks, cs2.player, CuriousPower, 2, applier=cs2.player)
    power_card2 = make_card("inflame")
    assert cs2.hooks.modify_card_energy_cost(
        power_card2, power_card2.energy_cost) == 1


def test_spiked_gauntlets_g3_x_cost_cards_are_still_never_powers():
    """G3 re-confirmed dormant: the sim's X-cost representation (a boolean
    flag, not a negative canonical cost) means `modify_card_energy_cost`'s
    missing `originalCost < 0` bail can only matter for a Power card that is
    also X-cost, and the three X-cost cards are still cascade/volley/
    whirlwind -- none a Power."""
    from sts2_rl.cards import CardType

    x_cost_powers = [
        cid for cid, cls in _CARD_CLASSES.items()
        if getattr(make_card(cid), "energy_cost_x", False)
        and cls.card_type == CardType.POWER
    ]
    assert x_cost_powers == []


# ══════════════════════════════════════════════════════════════════════════
# relic/stone_cracker/AfterRoomEntered and relic/sword_of_jade/AfterRoomEntered
#
# Both unaffected by this round's listener-DERIVATION rework (R1's `_derive`/
# `hook_contains` changes govern ORDER/membership WITHIN one dispatch; this
# guard is about WHICH dispatch the sim's `on_combat_start` stands in for --
# unrelated machinery, `combat.py:327`'s single `hooks.on_combat_start()`
# call is unchanged). Re-confirmed dormant with fresh execution/census below.
# ══════════════════════════════════════════════════════════════════════════

def test_stone_cracker_and_tea_of_discourtesy_are_order_independent():
    """G2 re-confirmed dormant: the only other on_combat_start listener that
    touches the draw pile (tea_of_discourtesy) cannot collide -- Dazed is
    never upgradable, and the two draw from different RNG streams
    (CombatCardSelection vs Shuffle). Demonstrated directly: the outcome is
    identical regardless of which relic registers first."""
    def _run(order):
        cs = CombatState(
            rng=random.Random(0),
            starting_deck=[make_card("strike") for _ in range(10)],
            encounter=Encounter("test", [LeafSlimeS]),
            relics=[make_relic(r) for r in order],
        )
        # Both relics' on_combat_start fires BEFORE the turn-1 opening draw
        # (combat.py:327 precedes the first start_turn), so the cards they
        # touch can land in either the draw pile OR the opening hand once
        # setup finishes -- count across all_cards, not just draw_pile.
        cards = cs.player.all_cards
        upgraded = sum(1 for c in cards if c.upgrade_level > 0)
        dazed = sum(1 for c in cards if c.id == "dazed")
        return upgraded, dazed

    a = _run(["stone_cracker", "tea_of_discourtesy"])
    b = _run(["tea_of_discourtesy", "stone_cracker"])
    assert a == b == (2, 2)


def test_sword_of_jade_g1_no_other_combat_start_listener_reads_strength():
    """G1 re-confirmed dormant: of the sim's on_combat_start implementers,
    none outside the twelve AfterRoomEntered-side relics READS an existing
    Strength amount (as opposed to merely also GRANTING its own, order-
    independent Strength like sling_of_courage's Elite-only +2, which is
    unaffected by WHEN it runs relative to sword_of_jade) -- re-executed
    census (source scan, not inherited from the 2026-07-26 audit).

    Widened per review, twice over. (1) The relic loop walks the MRO up to
    `Relic` instead of reading `cls.__dict__` alone, so an `on_combat_start`
    inherited from an intermediate relic base is visible. (2) The report
    claimed "every `on_combat_start` implementer"; the loop covered
    ALL_RELICS only. The second half below is the package-wide scan that
    claim needs -- it finds `powers.py`'s two implementers (vital_spark,
    galvanic), neither of which reads Strength (both afflict cards).

    Still narrow, and the close note says so: `read_patterns` is four literal
    substrings, so a Strength read through a helper or a `StrengthPower.id`
    constant would not match."""
    after_room_entered_side = {
        "bronze_scales", "ember_tea", "ghost_seed", "girya", "gorget",
        "oddly_smooth_stone", "philosophers_stone", "red_skull",
        "stone_cracker", "sword_of_jade", "throwing_axe", "vajra",
    }
    from sts2_rl.relics import ALL_RELICS
    from sts2_rl.relics.base import Relic

    read_patterns = ('.powers.get("strength"', '.powers["strength"',
                     "get('strength'", "['strength']")

    def _own_on_combat_start(cls):
        for base in cls.__mro__:
            if base is Relic:
                return None
            if "on_combat_start" in base.__dict__:
                return base.__dict__["on_combat_start"]
        return None

    offenders = []
    for rid, cls in ALL_RELICS.items():
        if rid in after_room_entered_side:
            continue
        fn = _own_on_combat_start(cls)
        if fn is None:
            continue
        src = inspect.getsource(fn)
        if any(p in src for p in read_patterns):
            offenders.append(rid)
    assert offenders == []

    # The package-wide half: every `on_combat_start` DEFINITION outside
    # relics/, read as source and checked for a Strength READ.
    pkg_dir = pathlib.Path(__file__).resolve().parents[1] / "sts2_rl"
    non_relic_impls, wider_offenders = [], []
    for path in sorted(pkg_dir.rglob("*.py")):
        if path.parent.name == "relics" or path.name == "hooks.py":
            continue                       # relics done above; hooks.py is the
        lines = path.read_text(encoding="utf-8").splitlines()  # dispatcher
        for i, line in enumerate(lines):
            if "def on_combat_start" not in line:
                continue
            indent = len(line) - len(line.lstrip())
            body = []
            for nxt in lines[i + 1:]:
                if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= indent:
                    break
                body.append(nxt)
            where = f"{path.relative_to(pkg_dir).as_posix()}:{i + 1}"
            non_relic_impls.append(where)
            if any(p in "\n".join(body) for p in read_patterns):
                wider_offenders.append(where)
    assert wider_offenders == []
    assert non_relic_impls, "the wider scan must not be vacuous"


# ══════════════════════════════════════════════════════════════════════════
# relic/vambrace/g6 — docstring fix (PROMPT.md bug class 24)
#
# The underlying behavioural divergence (G3) has been closed since round 7
# (2026-07-29); this entry's own subject is that the class docstring STILL
# misdescribes the (rewritten) port: it claims "The multiplier hook stays
# stateless (safe for previews); the one-shot flag is set from the real
# on_block_gained event" -- but `modify_block_multiplicative` reads
# `self._triggering_card`/`self._used` (not stateless), and there is no
# `on_block_gained` method anywhere in the current file (the split is
# `after_modify_block_amount` latches `_triggering_card`, `on_card_played`
# spends `_used`).
# ══════════════════════════════════════════════════════════════════════════

def test_vambrace_docstring_names_the_two_real_methods_and_scopes_the_hook_claim():
    """Absence assertions alone would pass against an empty docstring (the
    review's note), so this also pins what the text must SAY.

    And the replacement's own first draft shipped a second false sentence --
    "there is no `on_block_gained` method here or in the game". `AfterBlockGained`
    is real in BOTH engines: Hook.cs:143, dispatched from CreatureCmd.cs:662,
    overridden by JuggernautPower.cs:17 and BeaconOfHopePower.cs:36; and here
    hooks.py:138 maps `on_block_gained` -> `AfterBlockGained`, hooks.py:1712
    dispatches it, cmds.py:502 fires it and powers.py:1094 implements it. Only
    the VAMBRACE-scoped claim is true."""
    from sts2_rl.relics.vambrace import Vambrace
    doc = Vambrace.__doc__ or ""
    low = doc.lower()

    # The original bug (PROMPT.md class 24), both halves.
    assert "stays stateless" not in low
    assert "set from the real on_block_gained" not in low
    # The fix-pass bug: an unscoped claim about the engine's hook surface.
    assert "no `on_block_gained` method here or in the game" not in low
    # What the text must positively say: the two real writers, and the
    # AfterBlockGained claim scoped to Vambrace itself.
    assert "after_modify_block_amount" in low
    assert "on_card_played" in low
    assert "vambrace overrides no `afterblockgained` hook" in low

    # And the scoped claim has to be TRUE: neither the relic nor any relic
    # base below Relic defines on_block_gained.
    from sts2_rl.relics.base import Relic
    assert all("on_block_gained" not in b.__dict__
               for b in Vambrace.__mro__ if b is not Relic)
    # ...while the hook itself really does exist and really does have a
    # listener, which is why the unscoped version was false.
    from sts2_rl.hooks import HookSystem
    from sts2_rl.powers import ALL_POWERS
    assert callable(getattr(HookSystem, "on_block_gained", None))
    assert any("on_block_gained" in cls.__dict__
               for cls in ALL_POWERS.values())
