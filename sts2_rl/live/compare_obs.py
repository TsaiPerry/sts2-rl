"""Task 16 STEP 1 (SpireBot live bot): sim-vs-game obs diff tool.

``py -m sts2_rl.live.compare_obs sim_dump.jsonl game_dump.jsonl --contract
contract.json`` joins a sim dump (``sts2_rl/live/sim_obs_dump.py``) and a
game dump (the future SpireBot ``DecisionDumper`` mod — not yet built, gated
on Perry) on ``(act, floor, kind, decision_index)``, the key both sides already
emit per that module's docstring, and reports:

  - per-joined-decision ``f`` (tolerance ``--tol``, default 1e-6) and ``i``
    (exact) mismatches, each named down to the SEGMENT and intra-segment
    FIELD OFFSET via the contract's ``layout`` block (``{"name", "offset",
    "width"}`` per array, see ``sts2_rl/live/contract.py:_seg_list``) —
    never a bare array index;
  - decisions present in only one dump;
  - summary counts (decisions compared, mismatching decisions, a
    ``segment:field`` mismatch histogram).

CARVE-OUT DESIGN: ``sim_obs_dump.py``'s own docstring ("OPEN QUESTION")
documents that in-combat ``SelectCards`` decisions (Headbutt's discard/draw
pick, Armaments' upgrade pick, ...) are resolved synchronously inside the
conformance replay driver and never raise a capturable decision, so the sim
dump can NEVER contain a ``SelectCards`` line for one — that is expected
behavior, not a fidelity gap. This tool therefore treats a ``(act, floor,
"SelectCards", idx)`` key present only in the GAME dump as a carve-out by
default (reported, but not a failure / does not affect the exit code) —
but ONLY at an ``(act, floor)`` where the sim dump has at least one
``Combat``-kind line, since the carve-out's premise requires the sim to
have actually been in a combat at that floor. A missing-in-sim
``SelectCards`` line at a floor with no sim combat at all is left uncarved
(a failure) — round-4 diagnosis found this exact blanket carve-out was
hiding a game-side stale-screen bug (a lingering `NCardGridSelectionScreen`
node mislabeling Map/Event/Shop/Rest decisions as `SelectCards`).
``--allow-missing-sim-kind KIND`` (repeatable) ADDS more kinds to that
carve-out list; it never removes the default, since the default reflects a
structural fact about the sim driver, not a preference. Every other
sim-only-missing decision is a failure.

EVERY game-only-missing decision (the sim raised a decision the game dump
never recorded) is ALSO a failure, with exactly ONE narrow, structural
exception: the sim's ``_run_shop`` driver always asks a final "leave the
shop" ``Shop`` decision, but leaving a shop in the game is IMPLICIT — the
next recorded command is a plain ``MapMoveCommand``, nothing dispatches a
"leave" click for `DecisionDumper` to record — so that one trailing sim
`Shop` line can structurally never have a game-dump counterpart. A
missing-in-game `Shop` key is carved out only when BOTH (a) its
`decision_index` equals the MAXIMUM sim `Shop` decision_index at that same
``(act, floor)`` (only the trailing "leave" ask, never an earlier one) and
(b) it is the ONLY missing-in-game `Shop` key at that ``(act, floor)`` — two
or more missing game-side Shop lines at one floor means a real purchase
(or something else) went undumped, which must stay a failure even if the
trailing "leave" is among them (e.g. act 2 floor 4 currently misses BOTH
idx1 and idx2 — that pair stays uncarved; idx2 alone, with idx1 present,
would qualify).

ROUND-7 ADDENDUM -- one more narrow, data-supported carve-out:

* missing-in-sim "beyond sim coverage": the sim dump's conformance-replay
  driver stops advancing once the recording's command list is exhausted
  (see ``sim_obs_dump.py``), so its last emitted ``(act, floor)`` can sit
  strictly before the game dump's true final room -- the game dump keeps
  replaying real recorded rooms (e.g. a trailing Event room) the sim can
  never reach. Every game-only key whose ``(act, floor)`` sorts strictly
  after the sim dump's maximum ``(act, floor)`` is carved out and reported
  under its own "beyond sim coverage" heading, separate from ordinary
  carved-out missing-in-sim keys, since it reflects a structural
  end-of-recording boundary rather than a fidelity question the sim could
  ever resolve.

Exit code is 0 only on full parity: no value mismatches, no dimension
mismatches, and no un-carved-out missing decisions on either side.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TOL = 1e-6
DEFAULT_MAX_REPORT = 20
# See the module docstring's "CARVE-OUT DESIGN" section.
DEFAULT_ALLOW_MISSING_SIM_KINDS = ("SelectCards",)

DecisionKey = tuple  # (act, floor, kind, decision_index)

# RewardScreen join: the game dump records reward-screen decisions in the
# order the player actually clicked (potion claim before card pick, say),
# while the sim's driver always asks in a FIXED sub-kind order (cards, then
# potion, then relic — see driver.py's DecisionKind declaration order,
# threaded through run_env.py's `phase` one-hot at PHASE_INDEX). Neither
# side's order is wrong, so for `kind == "RewardScreen"` we join by REWARD
# SUB-KIND (which `phase` one-hot slot is set) plus a per-sub-kind
# occurrence counter, instead of by raw decision_index. Local offsets into
# the `phase` segment (see driver.py DecisionKind / run_env.py PHASE_INDEX):
# 4 = reward_card, 5 = reward_potion, 9 = reward_relic.
_REWARD_SUBKIND_PHASE_OFFSETS = {
    4: "reward_card",
    5: "reward_potion",
    9: "reward_relic",
}
_REWARD_JOIN_KIND = "RewardScreen"

# ROUND-9 ADDENDUM -- click-order state artifact on RewardScreen lines.
#
# Even after the sub-kind rekey above lines up "this player's card pick"
# with "this player's card pick" across dumps, a RewardScreen line's RUN
# STATE (deck/potions/relics/gold) is NOT purely a function of (act, floor,
# sub-kind) -- it also depends on which OTHER rewards on the SAME screen the
# player had already clicked-through by the time this sub-kind was resolved.
# The game dump records whatever order the human actually clicked (e.g.
# potion before card); the sim's driver always asks in the fixed sub-kind
# order card -> potion -> relic (see `_REWARD_SUBKIND_PHASE_OFFSETS`). So a
# sim `reward_card#0` line can legitimately have an empty `run.potions`
# where the game's line already reflects a potion claimed moments earlier --
# that is not a fidelity gap, it is two snapshots of the same multi-step
# claim sequence taken at different steps. Round-9 decode of every
# RewardScreen mismatch (see round-9 diagnosis notes) confirmed: every
# run.deck / run.potions / run.relics / run.gold delta on these lines is
# EXACTLY the single item claimed via the OTHER sub-kind screens, and every
# reward.<other-subkind>.* delta is that other sub-kind's still-pending (or
# already-claimed) offer leaking across sub-kinds the same way. The reward.*
# block belonging to THIS line's own sub-kind (e.g. reward.relic.* on a
# `reward_relic#0` line) is NOT part of that artifact -- it is the actual
# offer being made and must stay strictly compared (round-9 decode found 5
# genuine reward.relic.ids divergences hiding under the old comparison,
# unrelated to click order -- see the round-9 report).
#
# ROUND-9 ADDENDUM 2 -- run.hp_abs / run.max_hp_abs: decode of the two
# remaining mismatches on these segments (act=1 floor=8 idx=1 and act=2
# floor=13 idx=1, both RewardScreen lines) found the same click-order
# mechanism: a relic claimed earlier on one side than the other (e.g. a
# max-HP-granting or heal-on-pickup relic) has already applied its HP
# effect on the side that claimed it first, and not yet on the other. Same
# artifact as run.deck/potions/relics, so excluded the same way.
#
# ROUND-9 ADDENDUM 3 -- run.hp_ratio: decode found its remaining 2
# mismatches sit at the EXACT SAME keys as the hp_abs pair above (act=1
# floor=8 reward_card#0, act=2 floor=13 reward_potion#0) -- it is the same
# derived-from-hp_abs artifact, just not yet excluded.
_REWARD_BLOCK_BY_SUBKIND = {
    "reward_card": "reward.cards",
    "reward_potion": "reward.potion",
    "reward_relic": "reward.relic",
}
# Run-state segments that vary with intra-screen claim order regardless of
# which sub-kind the joined line is -- always excluded on RewardScreen lines.
_REWARD_SCREEN_ALWAYS_EXCLUDED_PREFIXES = (
    "run.deck.", "run.potions.", "run.relics.", "run.gold",
    "run.hp_abs", "run.max_hp_abs", "run.hp_ratio",
)


def _reward_screen_excluded_segments(subkind: str) -> set[str]:
    """``reward.*`` segments to exclude on a RewardScreen line of the given
    sub-kind: every OTHER sub-kind's reward block (its offer may already be
    claimed, or not yet asked, depending on click order) -- never this
    sub-kind's own block, which is the actual offer and must stay compared."""
    own_block = _REWARD_BLOCK_BY_SUBKIND.get(subkind)
    excluded = set()
    for blk in _REWARD_BLOCK_BY_SUBKIND.values():
        if blk != own_block:
            excluded.add(blk + ".f")
            excluded.add(blk + ".ids")
    return excluded


def _reward_subkind(fvals: list, f_segments: list[dict]) -> str:
    """Which reward sub-kind an ``f`` array is (via its ``phase`` one-hot),
    independent of decision_index / which side of the join it's on."""
    phase_segs = [s for s in f_segments if s["name"] == "phase"]
    if not phase_segs:
        return "<unknown>"
    base = phase_segs[0]["offset"]
    for local_off, name in _REWARD_SUBKIND_PHASE_OFFSETS.items():
        idx = base + local_off
        if idx < len(fvals) and fvals[idx]:
            return name
    return "<unknown>"


def _rekey_reward_screens(lines: list[dict], layout: dict) -> list[dict]:
    """Return ``lines`` with RewardScreen decisions' ``decision_index``
    replaced by a per-(act, floor, sub-kind) occurrence counter, so the
    existing (act, floor, kind, decision_index) join lines up sub-kind to
    sub-kind regardless of each side's raw click/ask order. Non-RewardScreen
    lines pass through unchanged. Original ordering within the input list is
    preserved when assigning occurrence numbers."""
    f_segments = layout.get("f", [])
    if not any(s["name"] == "phase" for s in f_segments):
        return lines
    counters: dict[tuple, int] = {}
    out = []
    for line in lines:
        if line["kind"] != _REWARD_JOIN_KIND:
            out.append(line)
            continue
        subkind = _reward_subkind(line["f"], f_segments)
        ckey = (line["act"], line["floor"], subkind)
        occ = counters.get(ckey, 0)
        counters[ckey] = occ + 1
        new_line = dict(line)
        new_line["decision_index"] = f"{subkind}#{occ}"
        out.append(new_line)
    return out


@dataclass
class ComparisonResult:
    n_compared: int = 0
    mismatching_decisions: int = 0
    mismatches: list = field(default_factory=list)
    missing_in_sim: list = field(default_factory=list)
    missing_in_sim_carved_out: list = field(default_factory=list)
    missing_in_sim_beyond_coverage: list = field(default_factory=list)
    missing_in_game: list = field(default_factory=list)
    missing_in_game_carved_out: list = field(default_factory=list)
    dim_mismatches: list = field(default_factory=list)
    segment_histogram: Counter = field(default_factory=Counter)
    truncated: bool = False


def _key(line: dict) -> DecisionKey:
    return (line["act"], line["floor"], line["kind"], line["decision_index"])


def _index_by_key(lines: list[dict]) -> dict[DecisionKey, dict]:
    """Last line wins on a duplicate key (shouldn't happen per the sim
    dump's per-(act, floor, kind) counter, but a duplicate is not this tool's
    job to diagnose)."""
    return {_key(l): l for l in lines}


def _locate_field(segments: list[dict], index: int) -> tuple[str, int]:
    """``segments`` -> the ``(name, local_offset)`` of the segment
    containing global array ``index``. Raises ``ValueError`` if no segment
    covers it (an out-of-range index, e.g. a dim mismatch upstream)."""
    for seg in segments:
        off = seg["offset"]
        if off <= index < off + seg["width"]:
            return seg["name"], index - off
    raise ValueError(f"index {index} is not covered by any layout segment")


def _diff_array(
    array_name: str, sim_vals: list, game_vals: list, segments: list[dict], *, tol: float,
) -> list[dict]:
    out = []
    for idx, (sv, gv) in enumerate(zip(sim_vals, game_vals)):
        mismatch = (abs(sv - gv) > tol) if array_name == "f" else (sv != gv)
        if not mismatch:
            continue
        try:
            seg_name, local_off = _locate_field(segments, idx)
        except ValueError:
            seg_name, local_off = "<unknown>", idx
        out.append({
            "array": array_name,
            "index": idx,
            "segment": seg_name,
            "local_offset": local_off,
            "sim_value": sv,
            "game_value": gv,
        })
    return out


def compare_dumps(
    sim_lines: list[dict],
    game_lines: list[dict],
    layout: dict,
    *,
    tol: float = DEFAULT_TOL,
    allow_missing_sim_kinds: tuple[str, ...] = (),
    max_report: int = DEFAULT_MAX_REPORT,
) -> ComparisonResult:
    """Join ``sim_lines``/``game_lines`` on ``(act, floor, kind, decision_index)``
    and diff every joined pair's ``f``/``i`` arrays against ``layout``
    (a contract's ``{"f": [...], "i": [...]}`` block, or the whole loaded
    contract dict — either is accepted, see ``_layout_dict``).
    """
    layout = _layout_dict(layout)
    carve_out_kinds = set(DEFAULT_ALLOW_MISSING_SIM_KINDS) | set(allow_missing_sim_kinds)

    sim_lines = _rekey_reward_screens(sim_lines, layout)
    game_lines = _rekey_reward_screens(game_lines, layout)

    sim_by_key = _index_by_key(sim_lines)
    game_by_key = _index_by_key(game_lines)

    result = ComparisonResult()
    common_keys = sorted(k for k in sim_by_key if k in game_by_key)
    for key in common_keys:
        sim_line = sim_by_key[key]
        game_line = game_by_key[key]
        result.n_compared += 1

        decision_mismatches = []
        for array_name, tolerance in (("f", tol), ("i", 0)):
            sv, gv = sim_line[array_name], game_line[array_name]
            if len(sv) != len(gv):
                result.dim_mismatches.append({
                    "key": key, "array": array_name,
                    "sim_len": len(sv), "game_len": len(gv),
                })
                continue
            decision_mismatches.extend(
                _diff_array(array_name, sv, gv, layout[array_name], tol=tol)
            )

        if key[2] == _REWARD_JOIN_KIND:
            # See "ROUND-9 ADDENDUM -- click-order state artifact" above:
            # a RewardScreen line's run-state and other-subkind reward
            # blocks are not comparable across independently-ordered claim
            # sequences. `key[3]` is this line's rekeyed decision_index,
            # e.g. "reward_potion#0" -- strip the occurrence counter to get
            # the sub-kind.
            subkind = key[3].split("#")[0] if isinstance(key[3], str) else None
            excluded_segments = _reward_screen_excluded_segments(subkind)
            decision_mismatches = [
                m for m in decision_mismatches
                if m["segment"] not in excluded_segments
                and not m["segment"].startswith(_REWARD_SCREEN_ALWAYS_EXCLUDED_PREFIXES)
                # ROUND-15: the UPGRADE field (float 0 of each 4-float
                # reward-card row) is click-order-dependent even on the
                # line's OWN sub-kind block: an egg relic claimed earlier on
                # the SAME screen retroactively upgrades matching pending
                # offers in place (CardReward.cs:117 subscribes
                # RelicObtained; ToxicEgg -> EggRelicHelper.UpgradeValidCards
                # mutates the open card list — traced on 933T (0,15): Toxic
                # Egg was that elite's relic drop, Drum of Battle is its one
                # Skill offer). The sim's fixed card->potion->relic ask order
                # asks about the cards BEFORE its relic grant, so its offer
                # is un-upgraded — same artifact class as the run-state
                # exclusions above. Card IDENTITY (ids) and every other
                # float stay strictly compared.
                and not (m["segment"] == "reward.cards.f"
                         and m["local_offset"] % 4 == 0)
            ]

        if decision_mismatches:
            result.mismatching_decisions += 1
            for m in decision_mismatches:
                result.segment_histogram[f"{m['array']}:{m['segment']}"] += 1
                m_with_key = dict(m, key=key)
                if len(result.mismatches) < max_report:
                    result.mismatches.append(m_with_key)
                else:
                    result.truncated = True

    # Floors where the sim dump has at least one Combat-kind line — the
    # SelectCards carve-out's premise (in-combat SelectCards decisions
    # resolve synchronously inside the sim's combat driver and never raise a
    # capturable decision) only holds at a floor where the sim was actually
    # IN a combat. A missing-in-sim SelectCards line at a floor with no sim
    # Combat lines at all is not that structural gap — it's much more likely
    # a stale-screen mislabel on the game side (e.g. a Map/Event/Shop/Rest
    # decision misclassified as SelectCards by a lingering grid-screen node,
    # see diag4-structural.md finding 1) and must NOT be silently carved.
    combat_floors = {
        (act, floor) for (act, floor, kind, _idx) in sim_by_key if kind == "Combat"
    }

    # Shop/Rest "trailing leave" carve-out (see module docstring's addendum):
    # the sim's `_run_shop` driver always asks a final "leave" Shop decision,
    # and its rest-site driver asks a final "use the remaining action or
    # leave" Rest decision whenever actions remain (933T's Miniature Tent
    # grants an extra rest-site action, so every tent rest ends on one) —
    # neither has a game-side counterpart, since leaving a shop/rest site in
    # the game is implicit (the next command is a plain MapMoveCommand /
    # ProceedToMap, both PassiveDump interstitials). Only the SINGLE missing
    # line of that kind at a given (act, floor) that is also that floor's
    # MAXIMUM sim decision_index for the kind qualifies; two-or-more missing
    # lines at one floor signal a real undumped gap and stay uncarved.
    _LEAVE_KINDS = ("Shop", "Rest")
    leave_max_idx: dict[tuple, object] = {}
    for (act, floor, kind, idx) in sim_by_key:
        if kind in _LEAVE_KINDS:
            cur = leave_max_idx.get((act, floor, kind))
            if cur is None or idx > cur:
                leave_max_idx[(act, floor, kind)] = idx
    missing_leave_by_floor: dict[tuple, list] = {}

    for key in sorted(k for k in sim_by_key if k not in game_by_key):
        result.missing_in_game.append(key)
        act, floor, kind, idx = key
        if kind in _LEAVE_KINDS:
            missing_leave_by_floor.setdefault((act, floor, kind), []).append(key)

    for (act, floor, kind), keys in missing_leave_by_floor.items():
        if len(keys) != 1:
            continue
        only = keys[0]
        if only[3] == leave_max_idx.get((act, floor, kind)):
            result.missing_in_game_carved_out.append(only)

    # Round-13: out-of-combat MULTI-PICK grid carve-out. On a skippable
    # multi-pick grid (MinSelect 0, MaxSelect N > 1 — e.g. an ancient
    # shrine's "remove up to 5"), the sim's `_card_selector` asks ONCE PER
    # PICK (idx 0..k), but the game records the whole grid as ONE
    # SelectGridCardCommand carrying every pick, so PassiveDump can
    # structurally never emit more than the idx-0 line. A missing-in-game
    # SelectCards key with idx >= 1 is carved out iff (a) the game DID dump
    # idx 0 for the same (act, floor) — proving the grid itself was captured
    # — and (b) the floor has no sim Combat lines (out-of-combat; in-combat
    # multi-asks are a different, already-carved sim-side shape).
    for key in list(result.missing_in_game):
        act, floor, kind, idx = key
        if (kind == "SelectCards" and isinstance(idx, int) and idx >= 1
                and (act, floor, "SelectCards", 0) in game_by_key
                and (act, floor) not in combat_floors
                and key not in result.missing_in_game_carved_out):
            result.missing_in_game_carved_out.append(key)

    # Round-13: UNCLAIMED-reward carve-out. The sim's driver asks about
    # every reward PRESENT on the screen; the game dump only ever records
    # CLAIMS — a reward the player proceeds past (e.g. a potion left behind
    # on a full belt: the claim would fail TooFull, so the player skips it;
    # PotionReward.OnSkipped records it in the save with was_picked=false)
    # produces a SkipRewards interstitial, never a dumpable decision. A
    # missing-in-game RewardScreen key is carved out iff (a) it carries a
    # re-keyed sub-kind index (`reward_*#k` — the sub-kind join ran, so the
    # sim line is a genuine per-sub-kind ask), and (b) the game DID dump at
    # least one RewardScreen line at the same (act, floor) — proving the
    # screen was captured and only this sub-kind went unclaimed. A wholly
    # missing screen stays a failure.
    game_reward_floors = {
        (act, floor) for (act, floor, kind, _idx) in game_by_key
        if kind == _REWARD_JOIN_KIND
    }
    for key in list(result.missing_in_game):
        act, floor, kind, idx = key
        if (kind == _REWARD_JOIN_KIND and isinstance(idx, str)
                and "#" in idx
                and (act, floor) in game_reward_floors
                and key not in result.missing_in_game_carved_out):
            result.missing_in_game_carved_out.append(key)

    result.missing_in_game_carved_out.sort()

    # Round-7: "beyond sim coverage" carve-out. The sim dump's conformance
    # replay driver stops once the recording's command list is exhausted, so
    # its last emitted (act, floor) can precede the game dump's true final
    # room -- the game keeps replaying real recorded rooms the sim never
    # reaches. That tail can never be a sim-side fidelity gap.
    sim_max_act_floor = max(
        ((act, floor) for (act, floor, _kind, _idx) in sim_by_key), default=None,
    )

    for key in sorted(k for k in game_by_key if k not in sim_by_key):
        result.missing_in_sim.append(key)
        act, floor, kind, _idx = key
        if kind in carve_out_kinds and (
            kind != "SelectCards" or (act, floor) in combat_floors
        ):
            result.missing_in_sim_carved_out.append(key)
        elif sim_max_act_floor is not None and (act, floor) > sim_max_act_floor:
            result.missing_in_sim_carved_out.append(key)
            result.missing_in_sim_beyond_coverage.append(key)

    return result


def _layout_dict(layout: dict) -> dict:
    """Accept either a bare ``{"f": [...], "i": [...]}`` layout block or a
    whole loaded contract dict (which nests it under ``["layout"]``)."""
    if "layout" in layout:
        return layout["layout"]
    return layout


def exit_code(result: ComparisonResult) -> int:
    uncarved_missing_sim = [
        k for k in result.missing_in_sim if k not in result.missing_in_sim_carved_out
    ]
    uncarved_missing_game = [
        k for k in result.missing_in_game if k not in result.missing_in_game_carved_out
    ]
    if (
        result.mismatching_decisions
        or uncarved_missing_game
        or uncarved_missing_sim
        or result.dim_mismatches
    ):
        return 1
    return 0


def _fmt_key(key: DecisionKey) -> str:
    act, floor, kind, idx = key
    return f"act={act} floor={floor} kind={kind} idx={idx}"


def format_report(result: ComparisonResult, *, max_report: int = DEFAULT_MAX_REPORT) -> str:
    lines = []
    lines.append(
        f"compared {result.n_compared} decisions; "
        f"{result.mismatching_decisions} mismatching"
    )

    if result.dim_mismatches:
        lines.append("")
        lines.append("dimension mismatches (array length differs — cannot diff by field):")
        for dm in result.dim_mismatches:
            lines.append(
                f"  [{_fmt_key(dm['key'])}] {dm['array']}: "
                f"sim_len={dm['sim_len']} game_len={dm['game_len']}"
            )

    if result.mismatches:
        lines.append("")
        lines.append("value mismatches:")
        for m in result.mismatches:
            lines.append(
                f"  [{_fmt_key(m['key'])}] {m['array']}[{m['index']}] "
                f"segment='{m['segment']}'+{m['local_offset']}: "
                f"sim={m['sim_value']!r} game={m['game_value']!r}"
            )
        if result.truncated:
            lines.append(f"  ... truncated (--max-report {max_report})")

    if result.segment_histogram:
        lines.append("")
        lines.append("mismatching segment histogram:")
        for seg, count in result.segment_histogram.most_common():
            lines.append(f"  {seg}: {count}")

    if result.missing_in_game:
        carved_g = set(result.missing_in_game_carved_out)
        uncarved_g = [k for k in result.missing_in_game if k not in carved_g]
        if uncarved_g:
            lines.append("")
            lines.append(f"missing in game dump (FAILURE, {len(uncarved_g)}):")
            for key in uncarved_g:
                lines.append(f"  {_fmt_key(key)}")
        if result.missing_in_game_carved_out:
            lines.append("")
            lines.append(
                "missing in game dump (carved out, not a failure, "
                f"{len(result.missing_in_game_carved_out)}):"
            )
            for key in result.missing_in_game_carved_out:
                lines.append(f"  {_fmt_key(key)}")

    if result.missing_in_sim:
        carved = set(result.missing_in_sim_carved_out)
        beyond = set(result.missing_in_sim_beyond_coverage)
        uncarved = [k for k in result.missing_in_sim if k not in carved]
        other_carved = [k for k in result.missing_in_sim_carved_out if k not in beyond]
        if uncarved:
            lines.append("")
            lines.append(f"missing in sim dump (FAILURE, {len(uncarved)}):")
            for key in uncarved:
                lines.append(f"  {_fmt_key(key)}")
        if other_carved:
            lines.append("")
            lines.append(
                "missing in sim dump (carved out, not a failure, "
                f"{len(other_carved)}):"
            )
            for key in other_carved:
                lines.append(f"  {_fmt_key(key)}")
        if result.missing_in_sim_beyond_coverage:
            lines.append("")
            lines.append(
                "missing in sim (beyond sim coverage, not a failure, "
                f"{len(result.missing_in_sim_beyond_coverage)}):"
            )
            for key in result.missing_in_sim_beyond_coverage:
                lines.append(f"  {_fmt_key(key)}")

    lines.append("")
    code = exit_code(result)
    lines.append("RESULT: FULL PARITY" if code == 0 else "RESULT: MISMATCH")
    return "\n".join(lines)


def _load_jsonl(path) -> list[dict]:
    """Load one dump's JSONL lines, hard-failing (naming the file and line
    number) on an old-format line missing the ``"act"`` key — the join key
    is ``(act, floor, kind, decision_index)`` and a silent misjoin across
    acts is worse than a crash (see the module docstring)."""
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            rec = json.loads(raw)
            if "act" not in rec:
                raise ValueError(
                    f"{path}:{lineno}: line is missing the \"act\" field "
                    "(old-format dump — the join key is now "
                    "(act, floor, kind, decision_index); regenerate the "
                    "dump before comparing)"
                )
            out.append(rec)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sim_dump", help="path to sim_obs_dump.py's output .jsonl")
    parser.add_argument("game_dump", help="path to the game-side DecisionDumper .jsonl")
    parser.add_argument("--contract", required=True, help="path to contract.json")
    parser.add_argument(
        "--tol", type=float, default=DEFAULT_TOL,
        help=f"absolute tolerance for `f` (float) comparisons (default: {DEFAULT_TOL})",
    )
    parser.add_argument(
        "--max-report", type=int, default=DEFAULT_MAX_REPORT,
        help=f"cap on printed per-value mismatches (default: {DEFAULT_MAX_REPORT})",
    )
    parser.add_argument(
        "--allow-missing-sim-kind", action="append", default=[], metavar="KIND",
        help=(
            "kind (e.g. 'SelectCards') whose game-only decisions are not "
            "counted as a failure. 'SelectCards' is always included (see "
            "module docstring's CARVE-OUT DESIGN); this flag ADDS more, "
            "repeatable."
        ),
    )
    args = parser.parse_args(argv)

    sim_lines = _load_jsonl(args.sim_dump)
    game_lines = _load_jsonl(args.game_dump)
    with open(args.contract, "r", encoding="utf-8") as fh:
        contract = json.load(fh)

    result = compare_dumps(
        sim_lines, game_lines, contract,
        tol=args.tol,
        allow_missing_sim_kinds=tuple(args.allow_missing_sim_kind),
        max_report=args.max_report,
    )
    print(format_report(result, max_report=args.max_report))
    return exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
