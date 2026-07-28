"""Fuzz gate: N seeded random full runs must make ZERO in-combat draws on the
legacy shared rng. Every hit is a wrong-stream parity bug with an exact
file:line — fix by routing the site through the correct combat_rng stream
(see converge_triage.STREAM_SRC for the stream->source-of-truth table)."""
from __future__ import annotations

import pytest

# (file, line) pairs to skip: a genuine, currently-unfixable debt, OR a site
# that is provably not game content. Each entry must cite the specific reason
# — never add an entry just to make the gate pass.
_ALLOWLIST: set[tuple[str, int]] = {
    # driver.py:252 is RunDriver._ask's `self._ask_fn(request)` call — the
    # decision-relay seam. play_random_run's random_asker(rng) (driver.py:182)
    # answers every DecisionRequest (which card/target/discard/... to pick)
    # by drawing on the shared run.rng *by design* (driver.py "asker" is a
    # stand-in for a human player). The real game never rolls dice for which
    # legal action the player takes — those are literal UI/input events, not
    # a RunRngSet stream — so a draw made here, however deep inside a
    # combat.py frame, is not a wrong-stream content bug. (Confirmed: the
    # ReplayRunner conformance path — the thing converge_triage's DETECTOR 1
    # actually gates — never calls _ask at all; it replays recorded actions
    # directly, so this site is unique to the play_random_run smoke-test
    # harness used here.)
    ("sts2_rl\\driver.py", 252),
    ("sts2_rl/driver.py", 252),
}

_N_RUNS = 20


@pytest.mark.parametrize("i", range(_N_RUNS))
def test_no_wrong_stream_draws_in_random_run(i):
    from sts2_rl.conformance.tripwire import Tripwire
    from sts2_rl.driver import play_random_run
    import sts2_rl.run as run_mod

    tw = Tripwire()
    orig_init = run_mod.RunState.__init__

    def patched(self, *a, **kw):
        orig_init(self, *a, **kw)
        tw.install(self.rng)

    run_mod.RunState.__init__ = patched
    try:
        # string_seed seats the parity RNG streams (RunState.rng_set) so an
        # in-combat draw on the legacy shared rng is unambiguously wrong —
        # without it there is no parity stream to have drawn on instead.
        play_random_run(seed=i, string_seed=f"TRIPWIRE{i}")
    except NotImplementedError as e:
        # A handful of shop/reward potions are deliberately unimplemented
        # pool-membership placeholders (potion_pools.py: _ParityPotion.use) —
        # the conformance runner never consumes a generated potion, but the
        # random smoke-test policy can legally pick "use potion" on one. This
        # is a content-coverage gap, not an RNG-stream bug; it's orthogonal
        # to what this gate checks, so skip rather than fail or falsely pass.
        #
        # There are OTHER `raise NotImplementedError` stubs reachable from a
        # random run (monster/state-machine/event/shop base-class stubs,
        # powers.py) that ARE real regressions and must fail this gate, not
        # be silently skipped. Discriminate by inspecting the deepest
        # traceback frame — the one that actually executed the `raise` — and
        # only skip when it is _ParityPotion.use in potion_pools.py. Anything
        # else re-raises.
        tb = e.__traceback__
        while tb.tb_next is not None:
            tb = tb.tb_next
        frame = tb.tb_frame
        code = frame.f_code
        is_potion_gap = (
            code.co_name == "use"
            and code.co_filename.replace("\\", "/").endswith(
                "sts2_rl/potion_pools.py")
        )
        if not is_potion_gap:
            raise
        potion = frame.f_locals.get("self")
        potion_id = getattr(potion, "id", "?")
        pytest.skip(
            f"random run hit unimplemented potion placeholder "
            f"{potion_id!r} (_ParityPotion.use, potion_pools.py): {e}")
    finally:
        run_mod.RunState.__init__ = orig_init

    sites = {k: v for k, v in tw.bug_sites().items()
             if (k[0], k[1]) not in _ALLOWLIST}
    assert not sites, (
        "wrong-stream in-combat draws:\n" + "\n".join(
            f"  {n}x {f}:{ln} ({fn}) near={own or '?'}"
            for (f, ln, fn, own), n in sorted(
                sites.items(), key=lambda kv: -kv[1])))


class _CountingStream:
    """Counting proxy over one CombatRng accessor. Counts `random()` — the
    primitive every move roll bottoms out in (state_machine._weighted_roll) —
    and forwards everything else, including the `rng` attribute lookup that
    _weighted_roll uses to detect a parity adapter (absent here, so the
    AttributeError this raises is the correct answer)."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.draws = 0

    def random(self) -> float:
        self.draws += 1
        return self._inner.random()

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _monster_ai_draws_over_one_round(stun: bool) -> int:
    """One LeafSlimeS encounter; end the player's turn and count the MonsterAi
    draws that the enemy round plus the next player-turn setup takes."""
    import random

    from sts2_rl.cmds import CreatureCmd
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters import Encounter
    from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS

    enc = Encounter(id="stunned_draw_count", monster_classes=[LeafSlimeS])
    cs = CombatState(rng=random.Random(4), encounter=enc)
    # Install after construction so the combat-start telegraph (the game's
    # AfterCreatureAdded roll) is outside the window being measured.
    counter = _CountingStream(cs.combat_rng._accessors["monster_ai"])
    cs.combat_rng._accessors["monster_ai"] = counter
    if stun:
        CreatureCmd.stun(cs.hooks, cs.enemies[0])
    cs.end_turn()
    return counter.draws


def test_a_stunned_enemy_round_takes_the_same_monster_ai_draw():
    """turn_structure audit gap G9 (audit/records/seam/turn_structure.json
    steps 2, 11, 33, G9), FIXED — the one gap in that mechanism whose
    observable is a stream draw count rather than a hook order, which is why
    it lives here and not in test_hook_order.py.

    CombatManager.cs:478-484 rolls EVERY enemy's next move in one pass at the
    start of the player's turn (`foreach (Creature enemy in _state.Enemies)
    enemy.PrepareForNextTurn(...)`), so a monster that did not act because it
    was stunned still takes its RunRng.MonsterAi draw — the stun replaced its
    move with a synthetic STUNNED MoveState (Creature.cs:524-544), which
    MonsterModel.PerformMove performs like any other, so nothing pins the
    machine. The sim rolled inside each monster's own move instead, so a
    stunned enemy took ZERO draws where the game takes one, and every later
    draw in the combat shifted by one. Executed before the fix, with this
    exact encounter and proxy: normal enemy turn = 1, STUNNED enemy turn = 0.

    Player-reachable: cards/whistle.py (Tanx's Whistle) stuns with no
    next_move_key.
    """
    assert _monster_ai_draws_over_one_round(stun=False) == 1
    assert _monster_ai_draws_over_one_round(stun=True) == 1
