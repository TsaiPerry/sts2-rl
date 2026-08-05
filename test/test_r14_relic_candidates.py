"""Round 14 (R6-F) -- the coordinated `living_enemies()` vs `hittable_enemies()`
candidate-set fix R6 deferred to a follow-up lane.

C# ground truth: `Kusarigama.cs:115` and `LetterOpener.cs:118` both draw
their candidate set from `base.Owner.Creature.CombatState.HittableEnemies`
(NOT `Enemies`/`.Where(!IsDead)`), and `BagOfMarbles.cs:28` applies
Vulnerable to `combatState.HittableEnemies` for the same reason.
`CombatState.HittableEnemies` (CombatState.cs:142) is
`Enemies.Where(e => e.IsHittable)`, and `Creature.IsHittable`
(Creature.cs:285-299) is `!IsDead && Hook.ShouldAllowHitting`.

The sim's `Relic.living_enemies()` (sts2_rl/relics/base.py) is `not
e.is_gone` (`is_dead or escaped`) and `Relic.hittable_enemies()`
(sts2_rl/combat.py:351-363, via `is_hittable` in sts2_rl/cmds.py:118-123) is
the exact `HittableEnemies` port: `not is_gone and should_allow_hitting`.
Both helpers already existed; the gap R6 deferred was three relic call
sites reading the wrong one.

IMPORTANT dormancy note (matches R6's own finding, reproduced here rather
than trusted): every ported `should_allow_hitting` implementer
(IllusionPower, the segment/reattach power, AdaptablePower) only sets
`is_reviving = True` from `on_death`, which fires only once `hp <= 0` --
i.e. once `is_gone` is ALREADY True. So for every reachable state today,
`hittable_enemies() == living_enemies()` (hittable is provably a subset that
never actually loses a member). The fix below is therefore a genuine
semantic correction (matches HittableEnemies exactly, is defense-in-depth
against a future `should_allow_hitting` implementer that fires while
`hp > 0`, and is what the C# source literally reads) but is NOT observable
through today's ported content. `test_reviving_enemy_is_still_is_gone_today`
pins that dormancy fact directly so a future change to revival timing that
breaks the coincidence is caught here, not silently. The other three tests
use a synthetic `should_allow_hitting` refusal (a target with `hp > 0`) to
exercise the actual code-path difference the fix makes, since no ported
content can construct the C#-real case yet.
"""
from __future__ import annotations

import random

from sts2_rl import CombatState, make_relic
from sts2_rl.cards import make_card
from sts2_rl.cmds import DamageCmd, PowerCmd
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
from sts2_rl.powers import IllusionPower


def _combat(relic_ids=(), seed: int = 0, enemy_count: int = 2) -> CombatState:
    return CombatState(rng=random.Random(seed),
                        starting_deck=[make_card("strike") for _ in range(10)],
                        encounter=Encounter("test", [LeafSlimeS] * enemy_count),
                        relics=[make_relic(r) for r in relic_ids])


def test_reviving_enemy_is_still_is_gone_today():
    """Dormancy pin: IllusionPower.on_death only arms `is_reviving` after
    `hp <= 0` (powers.py:2055-2061), so a reviving enemy is always
    `is_gone` too -- `hittable_enemies()` and `living_enemies()` cannot
    observably diverge through this power. Re-run so a future change to
    revival timing (e.g. a power that keeps hp > 0 while reviving) is
    caught here rather than silently making the fix below newly live."""
    cs = _combat(enemy_count=1)
    reviver = cs.enemies[0]
    PowerCmd.apply(cs.hooks, reviver, IllusionPower, 1, applier=reviver)
    DamageCmd.deal(cs.hooks, reviver, 99999, dealer=cs.player)
    illusion = reviver.powers.get("illusion")
    assert illusion is not None and illusion.is_reviving is True
    assert reviver.is_gone is True, (
        "if this ever goes False the kusarigama/letter_opener/bag_of_marbles "
        "fix below becomes newly LIVE -- re-derive the reachability analysis"
    )


def _make_unhittable_but_alive(cs: CombatState, creature) -> None:
    """Synthetic discriminator: force `should_allow_hitting(creature)` False
    while `creature.hp > 0` (not `is_gone`). No ported power can reach this
    state today (see module docstring), but it is exactly the shape
    `Creature.IsHittable`'s `Hook.ShouldAllowHitting` clause exists to gate,
    and it is the only way to exercise the `hittable_enemies()` vs
    `living_enemies()` code-path difference the fix makes."""
    assert not creature.is_gone
    real = cs.hooks.should_allow_hitting

    def patched(target):
        if target is creature:
            return False
        return real(target)

    cs.hooks.should_allow_hitting = patched


# ══════════════════════════════════════════════════════════════════════════
# relic/kusarigama/AfterCardPlayed -- Kusarigama.cs:115 draws from
# HittableEnemies; an alive-but-unhittable enemy must never be the random
# target.
# ══════════════════════════════════════════════════════════════════════════

def test_kusarigama_never_targets_an_unhittable_enemy():
    cs = _combat(relic_ids=("kusarigama",), enemy_count=2)
    unhittable, spectator = cs.enemies
    _make_unhittable_but_alive(cs, unhittable)
    kusarigama = cs.relics[0]

    seen_candidates = []
    real_choice = cs.combat_rng.targets.choice

    def spy_choice(seq):
        seen_candidates.append(list(seq))
        return real_choice(seq)

    cs.combat_rng.targets.choice = spy_choice

    strike = make_card("strike")
    for _ in range(3):
        kusarigama.on_card_played(strike)

    assert len(seen_candidates) == 1, seen_candidates
    candidates = seen_candidates[0]
    assert unhittable not in candidates, candidates
    assert spectator in candidates, candidates


# ══════════════════════════════════════════════════════════════════════════
# relic/letter_opener/AfterCardPlayed -- LetterOpener.cs:118 hits
# HittableEnemies (an AoE call); an alive-but-unhittable enemy must take no
# damage while the spectator does.
# ══════════════════════════════════════════════════════════════════════════

def test_letter_opener_does_not_call_damage_on_an_unhittable_enemy():
    # `DamageCmd.deal` itself backstops `should_allow_hitting`
    # (sts2_rl/cmds.py:311-312, N1), so a raw hp-delta check would pass
    # whether or not the candidate-set fix lands (same coincidence R6
    # documented for bag_of_marbles' PowerCmd.apply backstop). Spy on the
    # DEAL CALLS instead, which is what the candidate-set change actually
    # controls: `for enemy in self.living_enemies()` iterates -- and calls
    # `DamageCmd.deal` -- for every "not dead" enemy regardless of
    # hittability; `hittable_enemies()` never puts the unhittable enemy in
    # that loop at all.
    cs = _combat(relic_ids=("letter_opener",), enemy_count=2)
    unhittable, spectator = cs.enemies
    _make_unhittable_but_alive(cs, unhittable)
    letter_opener = cs.relics[0]

    seen_targets = []
    real_deal = DamageCmd.deal

    def spy_deal(hooks, target, *a, **kw):
        seen_targets.append(target)
        return real_deal(hooks, target, *a, **kw)

    orig = DamageCmd.deal
    DamageCmd.deal = staticmethod(spy_deal)
    try:
        skill = make_card("defend")
        for _ in range(3):
            letter_opener.on_card_played(skill)
    finally:
        DamageCmd.deal = orig

    assert unhittable not in seen_targets, seen_targets
    assert spectator in seen_targets, seen_targets


# ══════════════════════════════════════════════════════════════════════════
# relic/bag_of_marbles/BeforeSideTurnStart -- BagOfMarbles.cs:28 applies
# Vulnerable to combatState.HittableEnemies.
# ══════════════════════════════════════════════════════════════════════════

def test_bag_of_marbles_candidate_set_excludes_an_unhittable_enemy():
    cs = _combat(enemy_count=2)
    unhittable, spectator = cs.enemies
    _make_unhittable_but_alive(cs, unhittable)
    bag = make_relic("bag_of_marbles")
    bag.combat = cs

    # `bag_of_marbles.py` imports `PowerCmd` inside the method body (`from
    # ..cmds import PowerCmd`), so patch the class attribute on the shared
    # `sts2_rl.cmds.PowerCmd` object -- that's what the fresh import binds to.
    from sts2_rl.cmds import PowerCmd as RealPowerCmd

    seen = []
    real_apply = RealPowerCmd.apply

    def spy_apply(hooks, targets, *a, **kw):
        seen.append(targets)
        return real_apply(hooks, targets, *a, **kw)

    orig = RealPowerCmd.apply
    RealPowerCmd.apply = staticmethod(spy_apply)
    try:
        bag.before_side_turn_start(cs.player)
    finally:
        RealPowerCmd.apply = orig

    assert unhittable not in seen, seen
    assert spectator in seen, seen
    assert spectator.powers.get("vulnerable") is not None
