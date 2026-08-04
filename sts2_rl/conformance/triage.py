"""The single definition of `converged` for a conformance replay.

`tools/converge_triage.py` prints this verdict; `test/test_conformance_hard_gates.py`
asserts it. Change it in ONE place or the tool and the suite start disagreeing
again — which is the historical failure this module closes.

`player_` only ever prefixes `player_hp`/`player_max_hp` in `Divergence.stream`
(no other stream shares the prefix); map/nav streams (`map_point_type`,
`runner`) are covered transitively, since a map desync either forces a combat
(caught by `forced_combats`) or stops the run early (caught by
`reached_act_end`/`stopped_reason`, surfaced upstream of `assess`), never
silently — verified by reading `comparators.py`'s stream name usages rather
than added here as an explicit check.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Verdict:
    clean: bool
    reasons: list[str] = field(default_factory=list)


def assess(result, tripwire_bug_sites=None) -> Verdict:
    reasons: list[str] = []
    if result.forced_combats:
        reasons.append(f"forced_combats={result.forced_combats}")
    if result.unresolved_play_card_ids:
        reasons.append(f"unresolved_play_card_ids={result.unresolved_play_card_ids}")
    stream = [d for d in result.combat_divergences if d.command_index == -1]
    moves = [d for d in result.combat_divergences if d.command_index != -1]
    if stream:
        reasons.append(f"{len(stream)} stream counter diff(s): "
                       + ", ".join(d.stream for d in stream))
    if moves:
        reasons.append(f"{len(moves)} per-command mismatch(es), first: {moves[0]}")
    for prefix, label in (("player_", "act-boundary player state"),
                          ("floor_", "per-floor state"),
                          ("room_", "per-room state")):
        divs = [d for d in result.divergences if d.stream.startswith(prefix)]
        if divs:
            reasons.append(f"{len(divs)} {label} delta(s), first: {divs[0]}")
    if tripwire_bug_sites:
        reasons.append(f"{len(tripwire_bug_sites)} unseeded in-combat draw site(s)")
    return Verdict(not reasons, reasons)
