"""Task 15 (SpireBot live bot): sim-side obs dump for converged replays.

``py -m sts2_rl.live.sim_obs_dump --seed <seed> --out sim_dump.jsonl`` drives
one of the two hard-gated conformance recordings (89U21BV1TZ / 933T39V18D —
see ``test/test_conformance_hard_gates.py``) through the parity sim via
``sts2_rl.conformance.runner.ReplayRunner`` — the SAME full-combat-replay
path the convergence gates assert, never the standalone force-win stub (both
seeds are hard-gated ``forced_combats == 0``, so every combat in scope is a
real, card-for-card ``ReplayCombatDriver`` replay) — and emits one JSON line
per decision point:

    {"act": a, "floor": n, "kind": "...", "decision_index": k, "f": [...], "i": [...]}

``f``/``i`` come straight from ``STS2RunEnv._build_obs()`` (the same builder
``sts2_rl.run_env`` uses for on-policy training/inference — combat v7 / run
v11, dims ``run_env.run_obs_layout().f_dim``/``.i_dim``, currently 4715 /
1469), fed the exact ``DecisionRequest`` the driver would raise for that
decision. This module never invents an observation shape of its own.

``decision_index`` is a running counter per ``(act, floor, kind)``, reset
once per run and incremented every time that exact triple recurs —
mirroring ``SpireBotCode/DecisionDumper.cs``'s ``_counters`` (read read-only
from ``c:\\Users\\Perry\\Desktop\\SpireBot``) exactly, so Task 16 can join
sim and game lines on ``(act, floor, kind, decision_index)``. ``act`` is the
0-based act index (``run.act_index``, the same value the run-obs "run.act"
one-hot writer uses) — the per-act ``floor``/``kind``/``decision_index``
triple alone is NOT globally unique across a multi-act run.

``floor`` mirrors ``DecisionDumper``'s ``ctx.Snapshot.Floor`` ==
``IRunState.ActFloor`` — NOT the sim's own cumulative ``run.total_floor``.
Per the decompiled source (``RunState.cs``: ``CurrentActIndex`` setter resets
``ActFloor = 0`` on every act change; ``RunManager.EnterMapCoordInternal``
sets ``ActFloor = coord.row + 1`` on every room entry, including the
act-entry Ancient node at row 0), ``ActFloor`` is exactly
``current_point.row + 1`` and is constant for every decision raised while
resolving that room (it only changes on the NEXT room's entry). The sim
exposes the identical quantity as ``run.current_point.row + 1`` with no
extra bookkeeping, so that is what this module reports as ``floor``.

KIND MAPPING (the sim's ``sts2_rl.driver.DecisionKind`` -> the C#
``SpireBotCode.DecisionKind`` names, from ``DecisionContext.Classify``):

    sim DecisionKind      -> "kind" string   (rationale)
    ------------------------------------------------------------------------
    MAP                   -> "Map"
    EVENT                 -> "Event"
    SHOP                  -> "Shop"
    REST                  -> "Rest"
    REWARD_CARD           -> "RewardScreen"  C# folds every reward/chest
    REWARD_POTION         -> "RewardScreen"  screen (TakeCard/ClaimReward/
    REWARD_RELIC          -> "RewardScreen"  SkipRewards/OpenChest/
                                              TakeChestRelic) into one kind;
                                              the sim keeps 3 finer kinds for
                                              its own action space but they
                                              all fold to the same C# label.
    COMBAT                -> "Combat"
    SELECT_CARDS           -> "SelectCards"  OUT-OF-COMBAT only (out-of-combat
                                              card-grid screens: rest-site
                                              SMITH, upgrade/transform/remove
                                              events — see the open question
                                              below for in-combat selections).
    SELECT_OPTION          -> "SelectOption" never fires on either fixture
                                              seed (Scroll Boxes); kept for
                                              forward parity with the C# enum.
    (none)                  -> "Unsupported" never emitted by this dump (the
                                              sim always classifies a live
                                              decision into one of the kinds
                                              above); kept only because the
                                              C# enum has it.

    C#'s standalone "bare Proceed" click (ProceedToMapCommand /
    ProceedToNextActCommand with nothing else pending) also folds into
    RewardScreen, but the sim has no decision point for it at all — the
    driver's post-resolution screens already terminate at the REWARD_CARD /
    REWARD_POTION / REWARD_RELIC decision, so no extra line is emitted for
    the "click through" step.

OPEN QUESTION (documented per the task brief rather than guessed): in-combat
SELECT_CARDS decisions (Headbutt's discard->draw pick, Armaments' upgrade
pick, Burning Pact's discard, …) are resolved SYNCHRONOUSLY inside
``CombatState.play_card`` by ``ReplayCombatDriver._grid_selector`` reading
straight off the recording cursor — the conformance replay path never raises
a ``DecisionKind.SELECT_CARDS`` request for them the way live/RL play does
(``RunDriver._card_selector``, driver.py:384), so this dump does not emit a
line for them. Task 16 should treat a missing ``(floor, "SelectCards")``
entry during an active combat as expected, not a gap.

DRIVING MACHINERY: this module does not reimplement ``ReplayRunner`` — it
monkeypatches two seams for the duration of one replay (restored in
``finally``, the same pattern ``test_conformance_hard_gates.py`` uses for
``RunState.__init__``):

  - ``sts2_rl.conformance.runner._ForceWinDriver`` (a module-global the
    runner's ``run()`` method resolves at call time) is swapped for a
    subclass that captures an obs line at every non-MAP decision
    (``_ask_decision``) and wraps annotated combats in a
    ``ReplayCombatDriver`` subclass that captures one before each
    PlayCard/EndTurn/UsePotion dispatch.
  - ``sts2_rl.run.RunState.enter_point`` is wrapped to capture a "Map" line
    right before each recorded room move — the conformance runner drives the
    map walk directly off the recording's ``MoveToMapCoord`` commands
    (``ReplayRunner.run()``), never through ``RunDriver.play()``'s own
    ``DecisionKind.MAP`` ask, so no such request exists to intercept
    upstream.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

_REC_ROOT = Path(__file__).resolve().parents[2].parent / "RunReplays" / "RunReplays" / "Resources"
_BACKUP_933T = Path(
    r"C:\Users\Perry\Desktop\sts2-run-backups\20260723-125401\933T39V18D-recording"
)

# sim DecisionKind -> C# DecisionKind name (see module docstring's mapping table).
_KIND_MAP = {
    "map": "Map",
    "event": "Event",
    "shop": "Shop",
    "rest": "Rest",
    "reward_card": "RewardScreen",
    "reward_potion": "RewardScreen",
    "reward_relic": "RewardScreen",
    "combat": "Combat",
    "select_cards": "SelectCards",
    "select_option": "SelectOption",
}


class _ObsSink:
    """Builds one obs (via a bare ``STS2RunEnv``'s own ``_build_obs()``) per
    recorded decision and appends its JSON line. Owns the per-(act, floor,
    kind) decision_index counters — reset once per ``_ObsSink`` instance,
    i.e. once per run, mirroring ``DecisionDumper.ResetRun``."""

    def __init__(self, fh) -> None:
        from sts2_rl.run_env import STS2RunEnv

        self._fh = fh
        self._env = STS2RunEnv()
        self._counters: dict[tuple[int, int, str], int] = {}
        self.n_written = 0

    def record(self, run, request) -> None:
        kind = _KIND_MAP[request.kind.value]
        point = run.current_point
        floor = (point.row + 1) if point is not None else 0
        # Same quantity the run-obs "run.act" one-hot writer reads
        # (run_env.py: `buf.f[F("run.act").start + run.act_index] = 1.0`) —
        # read here rather than tracked with a parallel counter so the dump
        # field and the obs it accompanies can never disagree.
        act = run.act_index
        key = (act, floor, kind)
        idx = self._counters.get(key, 0)
        self._counters[key] = idx + 1

        self._env._run = run
        self._env._request = request
        obs = self._env._build_obs()
        f = obs["f"]
        i = obs["i"]

        line = {
            "act": act,
            "floor": floor,
            "kind": kind,
            "decision_index": idx,
            "f": [float(x) for x in f.tolist()],
            "i": [int(x) for x in i.tolist()],
        }
        self._fh.write(json.dumps(line) + "\n")
        self.n_written += 1


def _make_dumping_driver_class(sink: _ObsSink):
    """A per-call ``_ForceWinDriver`` subclass (closes over ``sink``) that
    captures an obs line at every non-MAP decision and wraps combat replay in
    a matching ``ReplayCombatDriver`` subclass. See the module docstring's
    "DRIVING MACHINERY" section for why this has to be a monkeypatched
    subclass rather than a constructor argument."""
    from sts2_rl.conformance import combat_driver as combat_driver_mod
    from sts2_rl.conformance import runner as runner_mod

    class _DumpingCombatDriver(combat_driver_mod.ReplayCombatDriver):
        def __init__(self, combat, cursor, card_db, run) -> None:
            super().__init__(combat, cursor, card_db)
            self._dump_run = run

        def _dispatch(self, cmd) -> None:
            if cmd.name in ("PlayCard", "EndTurn", "UsePotion"):
                from sts2_rl.driver import DecisionKind, DecisionRequest

                request = DecisionRequest(
                    kind=DecisionKind.COMBAT, run=self._dump_run, combat=self.combat,
                )
                sink.record(self._dump_run, request)
            super()._dispatch(cmd)

    class _DumpingForceWinDriver(runner_mod._ForceWinDriver):
        def _ask_decision(self, request) -> int:
            # MAP never reaches here (ReplayRunner.run() drives the map walk
            # itself — see enter_point's patch in dump_seed below); every
            # other kind's request is already fully populated by the base
            # RunDriver machinery (_run_event / _run_shop / _run_rest /
            # _offer_card_group / …), so it can be recorded as-is — except a
            # REWARD_RELIC ask's `request.relic`, which `prepare_request`
            # relabels from the save's ground truth (the sim's own grab-bag
            # pull isn't draw-order-faithful yet). That has to run BEFORE
            # `sink.record` builds the obs, so call it directly here instead
            # of going through the base `_ask_decision` (which would run it
            # again and double-advance the per-node relic-offer counter).
            self.prepare_request(request)
            sink.record(self.run, request)
            return self._answer(request)

        def _run_combat(self, encounter, room_type):
            # A faithful copy of _ForceWinDriver._run_combat with ONE swap:
            # ReplayCombatDriver -> _DumpingCombatDriver, so every combat
            # decision inside an annotated fight is captured too. Duplicated
            # (not delegated) because the swap happens in the middle of the
            # method, not at either end.
            from sts2_rl.rewards import GOLD_REWARD_RANGES

            run = self.run
            combat = run.create_combat(encounter, room_type=room_type, track_card_ids=True)
            self._combat = combat
            try:
                nxt = self._cursor.peek()
                if nxt is not None and nxt.name in runner_mod._COMBAT_CMDS:
                    driver = _DumpingCombatDriver(combat, self._cursor, combat.card_db, run)
                    self.combat_divergences.extend(driver.play())
                    self.unresolved_play_card_ids.extend(driver.unresolved_play_card_ids)
                    self._cursor.skip_while(runner_mod._COMBAT_TAIL_CMDS)
                if not combat.is_over:
                    self.forced_combats += 1
                    for enemy in combat.enemies:
                        enemy.hp = 0
                    combat._end_combat(player_won=True)
            finally:
                self._combat = None
            run.finish_combat(combat, room_type=room_type)
            won = bool(combat.result and combat.result.player_won)
            if won and room_type in GOLD_REWARD_RANGES and encounter.should_give_rewards:
                self._offer_rewards(run.generate_combat_rewards(
                    room_type, encounter=encounter,
                    gold_proportion=encounter.calculate_gold_proportion(combat),
                ))
            return combat

    return _DumpingForceWinDriver


def _floor_saves_for(seed: str) -> dict:
    from sts2_rl.conformance.save import parse_save

    roots = {"933T39V18D": _BACKUP_933T, "89U21BV1TZ": _REC_ROOT / "89U21BV1TZ"}
    root = roots[seed]
    return {
        int(p.name.split("_")[1]): parse_save(p / "run.save")
        for p in root.glob("floor_*") if (p / "run.save").exists()
    }


def _act_checkpoints(seed: str) -> dict:
    from sts2_rl.conformance.save import parse_save

    ck = {}
    for act, fl in {0: "floor_18", 1: "floor_34", 2: "floor_49"}.items():
        f = _REC_ROOT / seed / fl / "run.save"
        if f.exists():
            o = parse_save(f)
            ck[act] = (o.player_current_hp, o.player_max_hp)
    return ck


def dump_seed(seed: str, out_path, *, stop_after_act: int = 2) -> int:
    """Drive `seed`'s recording (act 0..``stop_after_act`` inclusive) through
    the parity sim, writing one JSON line per decision to ``out_path``
    (truncated first). Returns the number of lines written.

    Mirrors ``test_conformance_hard_gates.py``'s ``_replay(seed,
    resync=True)`` — the resync-on arm of the hard gate — since both arms are
    equally "converged" but resync gives the more literal per-floor state
    (deck/relics/potions rebuilt from the oracle on any detected drift), the
    more useful ground truth for a dump meant to mirror exact game state.
    """
    import sts2_rl.run as run_mod
    from sts2_rl.conformance import runner as runner_mod
    from sts2_rl.conformance.recording import parse_recording
    from sts2_rl.conformance.save import parse_save
    from sts2_rl.driver import DecisionKind, DecisionRequest

    # Recording/oracle always come from REC (even for 933T39V18D — the
    # backup root is used only for the per-floor resync saves below),
    # mirroring test_conformance_hard_gates.py's `_replay` exactly.
    b = _REC_ROOT / seed / "floor_49"
    rec = parse_recording(b / "actions.sts2replay")
    oracle = parse_save(b / "run.save")

    out_path = Path(out_path)
    with out_path.open("w", encoding="utf-8") as fh:
        sink = _ObsSink(fh)
        dumping_driver_cls = _make_dumping_driver_class(sink)

        orig_enter_point = run_mod.RunState.enter_point

        def patched_enter_point(self, dest):
            request = DecisionRequest(
                kind=DecisionKind.MAP, run=self, points=self.travelable_points(),
            )
            sink.record(self, request)
            return orig_enter_point(self, dest)

        orig_driver_cls = runner_mod._ForceWinDriver
        run_mod.RunState.enter_point = patched_enter_point
        runner_mod._ForceWinDriver = dumping_driver_cls
        try:
            runner_mod.ReplayRunner(rec, oracle).run(
                stop_after_act=stop_after_act,
                player_checkpoints=_act_checkpoints(seed),
                resync_player=True,
                floor_saves=_floor_saves_for(seed),
                resync_floors=True,
                check_room_stats=True,
            )
        finally:
            run_mod.RunState.enter_point = orig_enter_point
            runner_mod._ForceWinDriver = orig_driver_cls

    return sink.n_written


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", required=True, choices=["89U21BV1TZ", "933T39V18D"])
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--stop-after-act", type=int, default=2,
        help="drive through this act index inclusive (default: 2, the whole run)",
    )
    args = parser.parse_args(argv)
    n = dump_seed(args.seed, args.out, stop_after_act=args.stop_after_act)
    print(f"wrote {n} decision lines to {args.out}")


if __name__ == "__main__":
    main()
