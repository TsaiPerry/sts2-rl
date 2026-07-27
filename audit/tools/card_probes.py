"""Reproducible probes for the `audit/records/card/**` content stream.

Every "executed evidence" number the card records state about a *pool-wide*
property is produced here, so a later auditor can re-derive it instead of
trusting a throwaway script.

  py audit/tools/card_probes.py                  # every probe
  py audit/tools/card_probes.py downgrade        # one probe

Probes:
  downgrade      Which sim cards fail to restore their printed state after
                 upgrade->downgrade. `Card.downgrade` rebuilds from
                 `_init_vars` and re-applies upgrades (cards/base.py:150-165),
                 so any `_on_upgrade` that mutates a CLASS attribute the card's
                 `_init_vars` does not re-seed is sticky. C# `CardCmd.Downgrade`
                 (CardCmd.cs:212-260) rebuilds keywords from CanonicalKeywords,
                 so the game always restores them.
  unpowered-block  Gap G1's blast radius: the C# cards that gain block with a
                 `ValueProp.Unpowered` block var (BlockCmd.apply skips the whole
                 block-modifier dispatch for those, so Vambrace/Pael's Legion
                 never double them in the sim), intersected with the ported set.
  replay         Gap G4's blast radius: the sim cards/sources that can produce a
                 play count > 1, where C# rebuilds the CardPlay bracket per
                 iteration and the sim fires it once.
  shared-rng     Card `on_play` bodies that reach for the unseeded shared
                 `combat._rng` instead of a named `rng_set` stream — a replay
                 divergence wherever the game names a stream.
"""
from __future__ import annotations

import argparse
import inspect
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audit.tools.harness import DEFAULT_GAME_ROOT  # noqa: E402

# Printed state a player can see on the card face or feel in play.
_FLAGS = (
    "is_playable", "is_ethereal", "innate", "retain", "exhausts", "eternal",
    "is_unpowered", "has_turn_end_in_hand_effect", "energy_cost_x",
    "max_upgrade_level", "can_be_generated_in_combat",
    "can_be_generated_by_modifiers", "handles_own_routing", "gains_block",
    "tags", "target_type", "card_type", "rarity",
)
_NUMBERS = ("energy_cost", "base_damage", "base_hits", "base_block",
            "base_hp_loss", "magic_number")


def _snapshot(card) -> dict:
    out = {k: getattr(card, k, None) for k in _FLAGS}
    for k in _NUMBERS:
        try:
            out[k] = getattr(card, k, None)
        except Exception as exc:  # pragma: no cover - defensive
            out[k] = f"<{type(exc).__name__}>"
    return out


def _cards() -> dict:
    import sts2_rl.cards  # noqa: F401 - triggers registration
    from sts2_rl.cards.base import _CARD_CLASSES
    return dict(sorted(_CARD_CLASSES.items()))


def probe_downgrade() -> None:
    """upgrade()xN then downgrade()xN must equal a fresh instance."""
    bad = []
    for cid, cls in _cards().items():
        fresh = _snapshot(cls())
        card = cls()
        levels = max(1, card.max_upgrade_level)
        for _ in range(levels):
            card.upgrade()
        for _ in range(levels):
            card.downgrade()
        after = _snapshot(card)
        diff = {k: (fresh[k], after[k]) for k in fresh if fresh[k] != after[k]}
        if diff or card.upgrade_level != 0:
            bad.append((cid, diff))
    print(f"downgrade: {len(bad)} of {len(_cards())} sim cards do not restore")
    for cid, diff in bad:
        parts = ", ".join(f"{k}: {a!r} -> {b!r}" for k, (a, b) in diff.items())
        print(f"  {cid}: {parts}")


_BLOCKVAR_RE = re.compile(r"new BlockVar\(([^)]*)\)")


def probe_unpowered_block() -> None:
    """C# cards whose BlockVar carries ValueProp.Unpowered, and whether the
    sim ports them (gap G1's blast radius)."""
    ported = _cards()
    game_dir = DEFAULT_GAME_ROOT / "src/Core/Models/Cards"
    from audit.tools.harness import _pascal
    by_pascal = {_pascal(cid): cid for cid in ported}
    hits = []
    for cs in sorted(game_dir.glob("*.cs")):
        text = cs.read_text(encoding="utf-8-sig", errors="replace")
        args = _BLOCKVAR_RE.findall(text)
        unpowered = [a for a in args if "Unpowered" in a]
        # GainBlock calls that pass an explicit ValueProp set instead of a var.
        raw = re.findall(r"GainBlock\([^;]*Unpowered[^;]*\)", text)
        if unpowered or raw:
            stem = cs.stem
            hits.append((stem, by_pascal.get(stem), unpowered + raw))
    print(f"unpowered-block: {len(hits)} C# card(s) gain block with Unpowered")
    for stem, cid, args in hits:
        mark = f"PORTED as card/{cid}" if cid else "not ported"
        print(f"  {stem}.cs [{mark}]: {'; '.join(a.strip() for a in args)}")


def probe_replay() -> None:
    """Sim sources that can raise a card's play count above 1 (gap G4)."""
    import sts2_rl
    root = Path(sts2_rl.__file__).parent
    pat = re.compile(r"base_replay_count|modify_card_play_count")
    for py in sorted(root.rglob("*.py")):
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if pat.search(line):
                rel = py.relative_to(root.parent).as_posix()
                print(f"  {rel}:{i}: {line.strip()}")


def probe_shared_rng() -> None:
    """Card modules that use the unseeded shared combat rng."""
    from sts2_rl.cards.base import _CARD_CLASSES
    import sts2_rl.cards  # noqa: F401
    seen = {}
    for cid, cls in sorted(_CARD_CLASSES.items()):
        src_file = Path(inspect.getsourcefile(cls))
        try:
            body = inspect.getsource(cls)
        except OSError:  # pragma: no cover
            continue
        if re.search(r"combat\._rng|ctx\.combat\._rng", body):
            seen.setdefault(src_file.name, []).append(cid)
    total = sum(len(v) for v in seen.values())
    print(f"shared-rng: {total} sim card class(es) touch combat._rng")
    for fname, cids in sorted(seen.items()):
        print(f"  {fname}: {', '.join(cids)}")


def probe_dead_target_guards() -> None:
    """Card `on_play` bodies that skip an effect on a dead/escaped target.

    C# `Creature.CanReceivePowers` (Creature.cs:308-321) explicitly allows
    powers on DEAD creatures -- "dead creatures can still have powers applied
    to them" -- and only refuses when `CombatState == null` (i.e. the corpse was
    REMOVED) or `Hook.ShouldAllowHitting` says no. A normally-killed monster is
    removed inside `CreatureCmd.Kill` (CreatureCmd.cs:523-525) before the
    caller's next statement, so a sim `is_gone` guard agrees there -- but a
    corpse whose removal was vetoed (ReattachPower / Decimillipede,
    powers.py:2360; cmds.py:102) stays in combat in C# and still receives the
    power, while an `is_gone` guard skips it.
    """
    import sts2_rl.cards  # noqa: F401
    from sts2_rl.cards.base import _CARD_CLASSES
    pat = re.compile(r"is_gone|is_dead")
    hits = []
    for cid, cls in sorted(_CARD_CLASSES.items()):
        try:
            body = inspect.getsource(cls)
        except OSError:  # pragma: no cover
            continue
        lines = [l.strip() for l in body.splitlines() if pat.search(l)]
        if lines:
            hits.append((cid, lines))
    print(f"dead-target-guards: {len(hits)} sim card class(es) test liveness")
    for cid, lines in hits:
        print(f"  {cid}: {' | '.join(lines)}")


PROBES = {
    "downgrade": probe_downgrade,
    "dead-target-guards": probe_dead_target_guards,
    "unpowered-block": probe_unpowered_block,
    "replay": probe_replay,
    "shared-rng": probe_shared_rng,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("probe", nargs="?", choices=sorted(PROBES))
    args = ap.parse_args(argv)
    names = [args.probe] if args.probe else list(PROBES)
    for name in names:
        print(f"-- {name} " + "-" * (60 - len(name)))
        PROBES[name]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
