"""Extract every ``verdict == "gap"`` entry from the audit records.

This is the generator behind ``audit/GAP-QUEUE.md``.  Nothing here reads or
writes engine code; it only parses ``audit/records/<kind>/*.json`` plus the xfail
pins in ``test/test_hook_order.py`` so the queue's counts are reproducible
instead of transcribed.

Five kinds are read: the 6 engine-seam records and the four content tiers that
have landed (``power``, ``card``, ``event``, ``enchantment``).  ``relic`` and
``monster`` are **not audited** -- their record directories are empty and the
queue says so in its header rather than implying coverage it does not have.

Commands
--------
``counts``       summary header numbers (total / live / dormant / mechanisms / pinned)
``list``         one line per gap entry: id, liveness, mechanism, head of ``what``
``mechanisms``   the mechanism groups, largest first
``pins``         the strict xfail pins in test/test_hook_order.py and what they pin
``unpinned``     mechanisms with no pin
``refs``         raw cross-references found in gap text (grouping evidence)
``json``         the full structured dump
``cite-check``   every ``file:line`` in GAP-QUEUE.md resolves to a real line
``coverage``     every mechanism and every gap entry is locatable in GAP-QUEUE.md

Every gap entry is assigned to exactly one mechanism.

*Seam records* number their entries.  A step entry that names a guard ("see
guard G5", "gap G2 (cross-listener order)", "GAP G8 (clause a)") joins that
guard's mechanism; a guard entry anchors its own; the rest stand alone.

*Content records* have no step numbers.  Two tiers tag their guards with a
mechanism id of their own -- events write ``EV-3:``/``BR-G3:``, enchantments
write ``EG2:``/``BR-2:`` -- and those tags ARE the grouping, across every record
in the tier.  A ``BR-`` tag is a declared cross-reference to a seam mechanism
and is mapped to it by ``_TAG_MECHANISM``.  The power and card tiers tag
nothing, so their recurring families are recognised by ``_FAMILIES``: a regex
over the entry text, each pattern justified by the record text that names the
family.  Anything unmatched anchors its own mechanism, which is the safe
direction -- an over-split queue overstates the work, an over-merged one hides
a job.

``_CROSS_RECORD`` then merges mechanism keys that the records themselves declare
to be the same mechanism recorded in two places.

Usage:  py audit/tools/gap_queue.py <command>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# audit/tools/gap_queue.py -> parents[0]=audit/tools, [1]=audit, [2]=repo root.
ROOT = Path(__file__).resolve().parents[2]
RECORDS = ROOT / "audit" / "records"
RECORD_DIR = RECORDS / "seam"
# test_hook_order.py deliberately did NOT move into audit/ -- it is a pytest
# suite member and its strict-xfail gap pins must run with the normal suite.
PIN_FILE = ROOT / "test" / "test_hook_order.py"

SEAMS = [
    "damage_pipeline",
    "power_cmd",
    "creature_card_cmds",
    "turn_structure",
    "hook_dispatch",
    "monster_state_machine",
]

# Kinds with records on this branch, in queue order.  ``relic`` and ``monster``
# are deliberately absent: those streams have not run, and listing them here
# with 0 records would read as "audited, no gaps".
CONTENT_KINDS = ["power", "card", "event", "enchantment"]
KINDS = ["seam"] + CONTENT_KINDS
# Kinds the pipeline defines but has NOT audited -- reported by ``counts`` so a
# reader of the queue cannot mistake it for complete coverage.  The unit counts
# are ``py audit/tools/harness.py roster <kind>``'s "N sim units" line.
UNAUDITED_KINDS = ["relic", "monster"]
_UNAUDITED_UNITS = {"relic": 258, "monster": 109}

# --- mechanism merges the records themselves declare -------------------------
# key: mechanism key as auto-derived, value: canonical mechanism key.
# Each merge is asserted by text in at least one of the two records.
_CROSS_RECORD = {
    # "the same mechanism as damage_pipeline's guard N3, raised to gap in the
    # same pass" -- test_hook_order.py pin for G9; damage_pipeline N3 says the
    # same.  creature_card_cmds step 13 is the block-side site of it.
    "damage_pipeline/N3": "hook_dispatch/G9",
    # damage_pipeline G2 and power_cmd G4 are both the AfterModifyingXxx
    # companion-event machinery; power_cmd G4 cites damage_pipeline's finding
    # explicitly ("2 of the 13 AfterModifying* variants Task 5's
    # damage_pipeline audit found the sim implements only 1 of").
    "power_cmd/G4": "damage_pipeline/G2",
    # creature_card_cmds G2 is AfterModifyingBlockAmount -- the same missing
    # machinery at the block site.
    "creature_card_cmds/G2": "damage_pipeline/G2",
    # hook_dispatch step 38 is the same modifier-notification-list mechanism.
    # (auto-derived key for that step is its own; merged here.)
    "hook_dispatch/step38": "damage_pipeline/G2",
    # the pipeline-level is_powered_attack gate: damage side (damage_pipeline
    # G3) and block side (creature_card_cmds G1) are one mechanism at two
    # dispatch sites.
    "creature_card_cmds/G1": "damage_pipeline/G3",
    # the IsEnding / combat-over guard family: creature_card_cmds G14,
    # power_cmd G6 and hook_dispatch G8 are the same missing gate recorded on
    # three seams (G14's own text calls it "the combat-over / IsEnding guard
    # family ... no sim counterpart anywhere").
    "creature_card_cmds/G14": "hook_dispatch/G8",
    "power_cmd/G6": "hook_dispatch/G8",
    # within turn_structure the record states the precedence itself:
    # N1 "Carries G8's precedence (same missing phase model)",
    # N4 "carrying G3's precedence", N5 "this guard carries G10's verdict".
    "turn_structure/N1": "turn_structure/G8",
    "turn_structure/N4": "turn_structure/G3",
    "turn_structure/N5": "turn_structure/G10",
    # --- content tiers ------------------------------------------------------
    # enchantment BR-1: "ALREADY RECORDED, same verdict at every site (rule 3):
    # damage_pipeline.json guard N3 names this explicitly" -- N3 is itself
    # merged into hook_dispatch/G9 above.
    "enchantment/BR-1": "damage_pipeline/N3",
    # enchantment BR-2: "audit/records/seam/hook_dispatch.json gap G4".
    "enchantment/BR-2": "hook_dispatch/G4",
    # enchantment BR-3: "audit/records/seam/creature_card_cmds.json step 52".
    "enchantment/BR-3": "creature_card_cmds/step52",
    # enchantment BR-4: "audit/records/seam/turn_structure.json guard G8".
    "enchantment/BR-4": "turn_structure/G8",
    # enchantment BR-5: "turn_structure.json step 21 / guard G14".
    "enchantment/BR-5": "turn_structure/G14",
    # enchantment BR-6: "creature_card_cmds.json guard G1" -- itself merged
    # into damage_pipeline/G3 above.
    "enchantment/BR-6": "creature_card_cmds/G1",
    # event BR-G3: "audit/records/seam/creature_card_cmds.json ... G3", the
    # deck-transform-bypasses-the-deck-entry-pipeline mechanism.
    "event/BR-G3": "creature_card_cmds/G3",
    # event BR-38a: the rest-site heal hooks.  NOTE the event record cites this
    # as "turn_structure.json step 38a"; step 38a is in creature_card_cmds.json
    # (turn_structure's step 38 is EndOfTurnCleanup, a different gap).  The
    # mechanism is unambiguous from the text, the record's path is not --
    # reported as a record inconsistency, merged to the real home here.
    "event/BR-38a": "creature_card_cmds/step38a",
}


def _resolve(mech: str) -> str:
    """Follow a merge chain to its canonical key (BR-1 -> N3 -> G9)."""
    seen = set()
    while mech in _CROSS_RECORD and mech not in seen:
        seen.add(mech)
        mech = _CROSS_RECORD[mech]
    return mech

# Tier tags that are a declared cross-reference rather than a tier-local
# mechanism.  Everything else tagged ``EV-n``/``EG-n`` groups as ``<kind>/<tag>``.
_TAG_MECHANISM = {
    ("enchantment", "BR-1"): "enchantment/BR-1",
    ("enchantment", "BR-2"): "enchantment/BR-2",
    ("enchantment", "BR-3"): "enchantment/BR-3",
    ("enchantment", "BR-4"): "enchantment/BR-4",
    ("enchantment", "BR-5"): "enchantment/BR-5",
    ("enchantment", "BR-6"): "enchantment/BR-6",
    ("event", "BR-G3"): "event/BR-G3",
    ("event", "BR-38a"): "event/BR-38a",
}

# Recurring families in the untagged tiers (power, card).  A family is
# ``(kind, title-regex, head-regex, body-regex, mechanism)``: ``title`` matches
# the hook name or the guard's ``what``, ``head`` the first 200 characters of
# the issue (the record's own lead clause, which is where these tiers state
# which family an entry belongs to), ``body`` anywhere in the entry.  ``None``
# skips a leg; first match wins.  Every pattern is justified by the record text
# quoted above it, and a family the records explicitly call a seam gap is keyed
# on the seam mechanism so content and seam sites land in one group.
_FAMILIES = [
    # "SLOT. AbstractModel.AfterSideTurnEnd is dispatched by Hook.AfterTurnEnd
    #  (Hook.cs:1267-1292), called ONCE for the whole enemy side
    #  (CombatManager.cs:12..)" -- the ENEMY leg, which turn_structure G5 is the
    #  seam record of ("the enemy side is per-enemy in the sim, per-side in the
    #  game").  Several of these cite G5 by name.
    ("power", None, r"^SLOT|^PHASE, and LIVE|^WRONG SLOT|^Slot divergence|^SLOT and PHASE",
     r"ONCE for the whole enemy side|PER-CREATURE|per-creature enemy slot|"
     r"per-creature (?:enemy )?slot",
     "turn_structure/G5"),
    # the PLAYER leg of the same census: "The sim's on_player_turn_end is
    #  Hook.BeforeTurnEnd (combat.py:654) ... the sim's real AfterTurnEnd slot,
    #  after_player_turn_end (combat.py:665), is available and unused.  THE
    #  CONCRETE ROUTE, which applies to every unit in this group".
    #  Population: `py audit/tools/power_census.py slots`.
    ("power", None, r"^SLOT|^WRONG SLOT|^Slot divergence|^SLOT and PHASE", None,
     "power/_side_turn_slot"),
    # "PowerStackType.Single with the sim's on_stack overridden to `pass`
    #  citing it -- the settled census's 15-unit wrong-reasoning class
    #  (`py audit/tools/power_census.py stack`)"
    ("power", r"^StackType", None, r"PowerStackType", "power/_stack_type_single"),
    # "PowerInstanceType.Instanced -- the audit/records/seam/power_cmd.json G5
    #  mechanism, cross-referenced under rule 3"
    ("power", r"^InstanceType", None, r"PowerInstanceType", "power_cmd/G5"),
    # "PHASE LOSS.  This is a phase-suffixed C# hook and the sim has a single
    #  unphased dispatch, which is hook_dispatch gap G3"
    ("power", None, None,
     r"PHASE LOSS|phase-suffixed C# hook and the sim has a single unphased",
     "hook_dispatch/G3"),
    # the death mechanism: "THE HOOK IS THE WRONG ONE ... C# lets the death
    #  HAPPEN"; illusion's is "Same wrong-hook shape as AdaptablePower's, and
    #  not re-argued here"; the two shared guards are worded identically on both
    #  records.  Hook.AfterDeath fires on both C# branches and in the sim on
    #  neither.
    ("power", None, None,
     r"wrong-hook shape as AdaptablePower|THE HOOK IS THE WRONG ONE|"
     r"prevention branch's HP contract|non-damage kill path: CreatureCmd\.kill|"
     r"Same unused-hook finding as AdaptablePower",
     "power/_death_prevention_branch"),
    # "ENGINE-LEVEL HOME (added 2026-07-26): this mechanism now also carries
    #  `gap` at audit/records/seam/creature_card_cmds.json step 8c, which owns
    #  the missing hook surface itself; same verdict at every site per rule 3."
    ("power", r"^ShouldStopCombatFromEnding$", None, None,
     "creature_card_cmds/step8c"),
    # "LIVE, and it upgrades a seam gap that was recorded as un-demonstrated.
    #  C#'s PowerCmd.Apply<T> refuses to apply anything to a creature
    #  `CanReceivePowers == false` ... The same override exists on IllusionPower
    #  and ReattachPower, so all three carry it.  Verdict carried per rule 3"
    ("power", r"^ShouldAllowHitting$", None, None, "power/_should_allow_hitting"),
    # "WRONG HOOK.  C#'s `AfterDamageGiven(...)` is the DEALER-side after-damage
    #  event; the sim's counterpart is `on_damage_dealt` ... and this power uses
    #  `on_damage_received` instead" -- imbalanced and paper_cuts, identical text.
    ("power", r"^AfterDamageGiven$", r"^WRONG HOOK", None,
     "power/_after_damage_given_substitution"),
    # PROMPT.md bug class 2: "the sim's on_damage_received is skipped when the
    #  hit killed the victim (cmds.py:121, the CreatureCmd.cs:392 guard)".
    #  Narrowed to entries that LEAD with the finding or name the guard line, so
    #  an entry that merely mentions the class in passing keeps its own key.
    ("power", None, None,
     r"KILLING BLOW|[Kk]illing-blow (?:guard|class)|cmds\.py:121",
     "power/_killing_blow_guard"),
    # "the per-CardPlay bracket ... hook_dispatch's G4"
    ("power", None, None,
     r"per-CardPlay bracket|hook_dispatch(?:'s)? G4|once per Replay iteration",
     "hook_dispatch/G4"),
    # card tier, the `is_dead` early return: "the sim returns early on
    #  `if ctx.player.is_dead` between the HP loss and the block gain"
    ("card", None, None,
     r"returns early on `if ctx\.player\.is_dead|early return on `?ctx\.player\.is_dead",
     "card/_is_dead_early_return"),
    # card tier, the printed-var model: "`new HpLossVar(13m)` is a printed card
    #  var; the sim declares no `_hp_loss` in `_init_vars` ... Same mechanism and
    #  same verdict as card/bad_luck's CanonicalVars entry (rule 3)"
    ("card", r"^CanonicalVars$", None, None, "card/_printed_vars"),
    # card tier, the unplayable-cost model: "the canonical energy cost is -1 in
    #  C# and 0 in the sim.  `CardEnergyCost.GetWithModifiers` returns early on
    #  `_base < 0` (CardEnergyCost.cs:100-103) ... Same divergence as
    #  card/ascenders_bane's"
    ("card", r"^ctor$", None, r"energy cost is (?:\*\*)?-1|base\(-1", "card/_unplayable_cost"),
]

# Individual content entries whose family the regex table gets wrong, or which
# name a mechanism no pattern could infer.  Keyed on the full entry id.
_FAMILY_OVERRIDE = {
    # "the sim implements C#'s BEFORE-damage hook with the AFTER-damage one and
    # drops the powered-attack gate" -- that IS damage_pipeline G1 ("Thorns is
    # on the wrong hook"), which the seam record labels DORMANT and this record
    # labels LIVE with an executed witness.  Merged so the contradiction is
    # visible in one group rather than filed as two mechanisms.
    "power/thorns/BeforeDamageReceived": "damage_pipeline/G1",
    # "RE-VERDICTED 2026-07-26 ... see the Gremlin Horn witness on
    # power/adaptable's AfterDeath entry, which applies verbatim here"
    "power/steam_eruption/AfterDeath": "power/_death_prevention_branch",
    # creature_card_cmds step 8b: "CROSS-REFERENCED BY (rule 3, one verdict per
    # mechanism at every site): ... and power/illusion, which owns the
    # Hook.ShouldPowerBeRemovedOnDeath half of the predicate."
    "power/illusion/ShouldPowerBeRemovedOnDeath": "creature_card_cmds/step8b",
}

# Entries whose FIRST guard reference is not the finding the entry is about.
# Each is justified by the entry's own text or by the pin that names it.
_PRIMARY_OVERRIDE = {
    # step 52's lead clause is the IsEnding guard, but the finding the step
    # carries (and the one its pin asserts) is DowngradeInternal re-deriving
    # the card from its canonical model -- a one-level drop in the sim.
    "creature_card_cmds/step52": "creature_card_cmds/step52",
    # step 67's issue says "Same mechanism and same verdict as step 32".
    "turn_structure/step67": "turn_structure/step32",
}

# Additional mechanisms an entry is ALSO a site of (does not affect counts;
# each entry is counted once, under its primary mechanism).
_ALSO = {
    # "(c) AGGREGATION SHAPE -- this is gap G9 of audit/records/seam/hook_dispatch.json
    #  (step 31), the same mechanism as ... damage_pipeline.json guard N3,
    #  carried here at the third and last of its three sites"
    "creature_card_cmds/step13": ["hook_dispatch/G9"],
    # "See guards G3 and G8."
    "creature_card_cmds/step59": ["creature_card_cmds/G8"],
    # "See guard G14 ... See guard N3."
    "creature_card_cmds/step72": ["creature_card_cmds/N3"],
    # step 89's tail is the AfterCardChangedPiles-on-every-draw hole
    "creature_card_cmds/step89": ["creature_card_cmds/G8"],
}

# Mechanism keys are auto-derived; these are the display names.
MECHANISM_TITLES = {
    "hook_dispatch/G9": "multiplicative modifier hooks: parallel product vs sequential chain",
    "monster_state_machine/G1": "AddBranch integer arguments read as weights",
    "turn_structure/G13": "no CheckWinCondition after turn-1 setup",
    "creature_card_cmds/G3": "deck transform bypasses the deck-entry pipeline",
    "hook_dispatch/G2": "cross-listener dispatch order (Powers->Relics->Potions->Orbs->Cards)",
    "hook_dispatch/G3": "no Early/VeryEarly/Late phase passes",
    "hook_dispatch/G4": "one hook bracket per logical play instead of per CardPlay",
    "hook_dispatch/G8": "no IsEnding / IsOverOrEnding dispatch gate",
    "damage_pipeline/G2": "no AfterModifyingXxx(modifiers) companion events",
    "damage_pipeline/G3": "pipeline-level is_powered_attack gate",
    "damage_pipeline/G1": "Thorns is on the wrong hook (BeforeDamageReceived vs after)",
    "turn_structure/G5": "enemy side: per-creature in the sim, per-side in the game",
    "power/_side_turn_slot": "the sim's on_player_turn_end is C#'s BeforeTurnEnd, not AfterTurnEnd",
    "power/_stack_type_single": "PowerStackType.Single misread as 'do not stack' (census: 15 units)",
    "power/_death_prevention_branch": "death prevention: no AfterDeath, no corpse retention",
    "power/_killing_blow_guard": "on_damage_received skipped on the killing blow",
    "power/_should_allow_hitting": "PowerCmd.apply has no CanReceivePowers backstop",
    "power/_should_stop_combat_from_ending": "no ShouldStopCombatFromEnding in the win check",
    "power/_after_damage_given_substitution": "AfterDamageGiven ported onto on_damage_received",
    "power_cmd/G5": "no PowerInstanceType (Instanced / InstancedPerApplier)",
    "card/_unplayable_cost": "unplayable cards: canonical energy cost -1 in C#, 0 in the sim",
    "card/_printed_vars": "printed card vars with no _init_vars entry",
    "card/_is_dead_early_return": "a sim is_dead early return splits one card's effect in two",
    "event/EV-1": "event damage bypasses the death / death-prevention pass",
    "event/EV-2": "lose_max_hp: no overflow damage, floors max HP first",
    "event/EV-3": "the per-event Rng replaced by the shared run stream",
    "event/EV-4": "a take-or-skip reward screen collapsed into an auto-grant",
    "event/EV-5": "StableShuffle / UnstableShuffle replaced by a different pick",
    "event/EV-8": "CardFactory.CreateForReward's hook tail is missing",
    "event/EV-9": "random_potion draws on the shared run stream",
    "event/EV-10": "the transform screen reuses the removal predicate",
    "event/EV-12": "a Combat-layout event builds its encounter at the wrong moment",
    "enchantment/EG1": "EnchantmentModel.OnPlay is a direct in-loop call, not a hook",
    "enchantment/EG2": "CreateClone re-attaches the enchantment; five sim copy sites drop it",
}

# "1. Guard:", "17.4 Second loop:", "38a. PlayerCmd", "102b. CardPile" -- the
# trailing dot is optional because the sub-numbered steps do not carry one.
_ID_STEP = re.compile(r"^\s*(\d+(?:\.\d+)?[a-z]?)[.:]?\s+")
_ID_GUARD = re.compile(r"^\s*([GN]\d+)\b")
# a step that names the guard/gap it belongs to
_REF = re.compile(r"\b(?:gap|guard)s?\s+([GN]\d+)\b", re.IGNORECASE)
_ANY_REF = re.compile(r"\b(?:gap|guard|note)s?\s+((?:[GN]\d+)(?:\s*(?:,|and|/|or)\s*[GN]\d+)*)", re.IGNORECASE)
_FILELINE = re.compile(r"([\w./\\-]+\.(?:py|cs)):(\d+(?:-\d+)?)")

_LIVE = re.compile(r"\b(LIVE(?:NESS)?|live and (?:executed|reachable)|LIVE AND REACHABLE)\b")
_DORMANT = re.compile(r"\b(DORMANT|dormant)\b")

# An explicit label wins over a loose token: enchantment records write
# "LIVENESS: LIVE." / "LIVENESS: DORMANT".
_LIVENESS_LABEL = re.compile(r"\bLIVENESS\s*[:\-]\s*\**\s*(LIVE|DORMANT)\b")
# A "what would wake it" clause is NOT a liveness claim.  Scrubbed before the
# token scan, otherwise "DORMANT; it goes LIVE when X is ported" reads as live
# whenever the dormancy token happens to sit later in the sentence.
_WAKES = re.compile(
    r"\b(?:would\s+(?:be|go|become)|goes?|go|becomes?|turns?|makes?\s+(?:it|this|them|that)|"
    r"raises?\s+(?:it|this)\s+to|flips?\s+(?:it|this)\s+to)\s+LIVE\b"
    r"|\bLIVE\s+(?:if|once|the\s+moment|as\s+soon\s+as|only\s+when)\b"
    r"|\bto\s+make\s+(?:it|this)\s+LIVE\b"
)

# content tier guard tags: "EV-3:", "EG2:", "BR-2 (blast radius)", "BR-G3:",
# "BR-38a (blast radius)"
_ID_TAG = re.compile(r"^\s*((?:EV|EG|BR)-?[A-Z]?\d+[a-z]?)\b")


def load_records():
    out = {}
    for seam in SEAMS:
        path = RECORD_DIR / f"{seam}.json"
        out[seam] = json.loads(path.read_text(encoding="utf-8"))
    return out


def load_content(kind):
    """Every content record of one kind, sorted by unit id."""
    out = []
    d = RECORDS / kind
    if not d.is_dir():
        return out
    for path in sorted(d.glob("*.json")):
        out.append(json.loads(path.read_text(encoding="utf-8")))
    return sorted(out, key=lambda r: r.get("unit", path.stem))


def record_counts():
    """kind -> number of records on disk (audited units, gaps or not)."""
    out = {}
    for kind in KINDS + UNAUDITED_KINDS:
        d = RECORDS / kind
        out[kind] = len(list(d.glob("*.json"))) if d.is_dir() else 0
    return out


def _entry_id(section: str, what: str, ordinal: int) -> str:
    if section == "guards":
        m = _ID_GUARD.match(what)
        return m.group(1) if m else f"guard{ordinal}"
    m = _ID_STEP.match(what)
    return f"step{m.group(1)}" if m else f"step_i{ordinal}"


def _liveness(text: str) -> str:
    """LIVE / DORMANT read out of the record's own text.

    Records write the verdict in caps near the head of the issue, and the
    liveness argument later.  An explicit ``LIVENESS: X`` label wins outright;
    otherwise the first explicit token wins, so a guard headline like
    "G1 (LIVE) --" or "(dormant)" is authoritative.  Clauses that describe what
    would *wake* a dormant gap are scrubbed first -- they are not claims about
    today.
    """
    label = _LIVENESS_LABEL.search(text)
    if label:
        return label.group(1).lower()
    text = _WAKES.sub(" ", text)
    for scope in (text[:400], text):
        m_live = _LIVE.search(scope)
        m_dorm = _DORMANT.search(scope)
        if m_live and m_dorm:
            return "live" if m_live.start() < m_dorm.start() else "dormant"
        if m_live:
            return "live"
        if m_dorm:
            return "dormant"
    return "unlabelled"


def _family(kind: str, title: str, body: str):
    """The recurring-family mechanism for an untagged content entry, or None."""
    blob = title + " || " + body
    head = body.strip()[:200]
    for fkind, tpat, hpat, bpat, mech in _FAMILIES:
        if fkind != kind:
            continue
        if tpat and not re.search(tpat, title):
            continue
        if hpat and not re.search(hpat, head):
            continue
        if bpat and not re.search(bpat, blob):
            continue
        return mech
    return None


def _make_entry(key, kind, record, section, local_id, what, body, mech):
    text = what + " " + body
    return {
        "id": key,
        "kind": kind,
        "record": record,
        # ``seam`` kept for backwards compatibility with the pin mapper and the
        # per-seam breakdown; it is the record name for every kind.
        "seam": record,
        "section": section,
        "local_id": local_id,
        "liveness": _liveness(what + " || " + body),
        "mechanism": _resolve(mech),
        "what": what,
        "issue": body,
        "citations": sorted({f"{a}:{b}" for a, b in _FILELINE.findall(text)}),
        "refs": sorted(
            {t for g in _ANY_REF.findall(text) for t in re.findall(r"[GN]\d+", g)}
        ),
        "also": [_resolve(k) for k in _ALSO.get(key, [])],
    }


def extract():
    """Return the list of gap entries, each with id / liveness / mechanism."""
    records = load_records()
    entries = []
    for seam in SEAMS:
        rec = records[seam]
        for section in ("steps", "guards"):
            for i, e in enumerate(rec.get(section, [])):
                if e.get("verdict") != "gap":
                    continue
                what = e["what"]
                body = e.get("issue") or e.get("rationale") or ""
                eid = _entry_id(section, what, i)
                key = f"{seam}/{eid}"
                if key in _PRIMARY_OVERRIDE:
                    mech = _PRIMARY_OVERRIDE[key]
                elif section == "guards":
                    mech = key
                else:
                    m = _REF.search(body)
                    mech = f"{seam}/{m.group(1)}" if m else key
                entries.append(
                    _make_entry(key, "seam", seam, section, eid, what, body, mech)
                )

    for kind in CONTENT_KINDS:
        for rec in load_content(kind):
            unit = rec.get("unit", "?")
            seen = set()
            # hooks: a dict of hook-name -> verdict entry
            for hname, e in (rec.get("hooks") or {}).items():
                if not isinstance(e, dict) or e.get("verdict") != "gap":
                    continue
                # "AfterSideTurnEnd (inherited, TemporaryStrengthPower.cs:...)"
                local = hname.split(" ")[0].strip() or "hook"
                while local in seen:
                    local += "'"
                seen.add(local)
                body = e.get("issue") or e.get("rationale") or ""
                key = f"{unit}/{local}"
                mech = (
                    _FAMILY_OVERRIDE.get(key) or _family(kind, hname, body) or key
                )
                entries.append(
                    _make_entry(key, kind, unit, "hooks", local, hname, body, mech)
                )
            # guards: a list; a content guard may carry a tier tag as its id
            for i, e in enumerate(rec.get("guards") or []):
                if e.get("verdict") != "gap":
                    continue
                what = e.get("what", "")
                body = e.get("issue") or e.get("rationale") or ""
                m = _ID_TAG.match(what)
                tag = m.group(1) if m else None
                local = tag or f"g{i + 1}"
                while local in seen:
                    local += "'"
                seen.add(local)
                key = f"{unit}/{local}"
                if key in _FAMILY_OVERRIDE:
                    mech = _FAMILY_OVERRIDE[key]
                elif tag:
                    mech = _TAG_MECHANISM.get((kind, tag), f"{kind}/{tag}")
                else:
                    mech = _family(kind, what, body) or key
                entries.append(
                    _make_entry(key, kind, unit, "guards", local, what, body, mech)
                )

    # apply the cross-record merge to mechanism keys that are themselves gaps
    for e in entries:
        e["mechanism"] = _resolve(e["mechanism"])
    # an entry with no explicit liveness token inherits its mechanism's
    by_mech = {}
    for e in entries:
        by_mech.setdefault(e["mechanism"], []).append(e)
    for mech, es in by_mech.items():
        if any(x["liveness"] == "live" for x in es):
            group = "live"
        elif any(x["liveness"] == "dormant" for x in es):
            group = "dormant"
        else:
            group = "unlabelled"
        for e in es:
            e["mech_liveness"] = group
            if e["liveness"] == "unlabelled":
                e["liveness_effective"] = group + " (inherited)"
            else:
                e["liveness_effective"] = e["liveness"]
    return entries


# --- pins --------------------------------------------------------------------

_XFAIL = re.compile(r"@pytest\.mark\.xfail")


def pins():
    """Parse the strict xfail pins out of test/test_hook_order.py."""
    src = PIN_FILE.read_text(encoding="utf-8").splitlines()
    out = []
    cls = None
    i = 0
    while i < len(src):
        line = src[i]
        m = re.match(r"class (\w+)", line)
        if m:
            cls = m.group(1)
        if _XFAIL.search(line):
            j = i
            block = []
            while j < len(src) and not src[j].strip().startswith("def "):
                block.append(src[j].strip())
                j += 1
            fn = re.match(r"def (\w+)", src[j].strip()).group(1) if j < len(src) else "?"
            blob = " ".join(block)
            reason = re.sub(r'"\s+"', "", blob)
            strict = "strict=True" in blob
            # which record does this pin cite?  the EARLIEST seam name in the
            # reason -- pins open with "<seam> audit gap ..." and may name
            # other seams later in the prose.
            hits = [(reason.find(s), s) for s in SEAMS if s in reason]
            seam = min(hits)[1] if hits else None
            gid = None
            gm = re.search(r"\b(?:gap|guard) ([GN]\d+)", reason)
            if gm:
                gid = gm.group(1)
            # steps are only used to locate the mechanism when no gap id is named
            steps = (
                []
                if gid
                else re.findall(r"\bstep[s]? (\d+[a-z]?(?:\s*,\s*\d+[a-z]?)*)", reason)
            )
            out.append(
                {
                    "line": i + 1,
                    "test": f"test/test_hook_order.py::{cls}::{fn}",
                    "strict": strict,
                    "seam": seam,
                    "gap": gid,
                    "steps": steps,
                    "reason": reason[:400],
                }
            )
            i = j
        i += 1
    return out


def pin_map():
    """mechanism key -> list of pinning tests."""
    entries = extract()
    by_key = {}
    for e in entries:
        by_key.setdefault(e["id"], e["mechanism"])
    out = {}
    for p in pins():
        if not p["seam"]:
            continue
        keys = []
        if p["gap"]:
            keys.append(f"{p['seam']}/{p['gap']}")
        for s in p["steps"]:
            for tok in re.findall(r"\d+[a-z]?", s):
                keys.append(f"{p['seam']}/step{tok}")
        mechs = []
        for k in keys:
            k = _resolve(k)
            mechs.append(by_key.get(k, k))
        for m in dict.fromkeys(mechs):
            out.setdefault(m, []).append(p["test"])
    return out


# --- commands ----------------------------------------------------------------


def cmd_counts():
    entries = extract()
    mechs = {}
    for e in entries:
        mechs.setdefault(e["mechanism"], []).append(e)
    pm = pin_map()
    live_mechs = [m for m, es in mechs.items() if any(x["liveness"] == "live" for x in es)]
    eff_live = sum(1 for e in entries if e["mech_liveness"] == "live")
    print(f"gap entries        : {len(entries)}")
    print(f"  labelled live    : {sum(1 for e in entries if e['liveness'] == 'live')}")
    print(f"  labelled dormant : {sum(1 for e in entries if e['liveness'] == 'dormant')}")
    print(f"  unlabelled       : {sum(1 for e in entries if e['liveness'] == 'unlabelled')}"
          " (inherit their mechanism's liveness)")
    print(f"  in a LIVE mech   : {eff_live}")
    print(f"  in a dormant mech: {len(entries) - eff_live}")
    print(f"distinct mechanisms: {len(mechs)}")
    print(f"  with a live entry: {len(live_mechs)}")
    print(f"  pinned           : {sum(1 for m in mechs if m in pm)}")
    print(f"  unpinned         : {sum(1 for m in mechs if m not in pm)}")
    print(f"strict xfail pins  : {sum(1 for p in pins() if p['strict'])}"
          f" (of {len(pins())} xfail decorators in test/test_hook_order.py)")
    print()
    rc = record_counts()
    print("per kind (records / gap entries / mechanisms anchored / live entries):")
    for kind in KINDS:
        es = [e for e in entries if e["kind"] == kind]
        if kind == "seam":
            anchored = {m for m in mechs if m.split("/")[0] in SEAMS}
        else:
            anchored = {m for m in mechs if m.split("/")[0] == kind}
        print(
            f"  {kind:14s} {rc[kind]:4d} / {len(es):4d} / {len(anchored):4d} / "
            f"{sum(1 for e in es if e['liveness'] == 'live'):4d}"
        )
    print("  NOT AUDITED  : " + ", ".join(
        f"{k} ({_UNAUDITED_UNITS.get(k, '?')} C# units)" for k in UNAUDITED_KINDS))
    print()
    print("per seam record (entries / mechanisms anchored there / live entries):")
    for seam in SEAMS:
        es = [e for e in entries if e["seam"] == seam]
        anchored = {m for m in mechs if m.startswith(seam + "/")}
        print(
            f"  {seam:24s} {len(es):3d} / {len(anchored):3d} / "
            f"{sum(1 for e in es if e['liveness'] == 'live'):3d}"
        )
    print()
    print("largest mechanisms:")
    for m, es in sorted(mechs.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:12]:
        kinds = ",".join(sorted({e["kind"] for e in es}))
        live = "LIVE" if any(x["liveness"] == "live" for x in es) else "dormant"
        print(f"  {m:36s} n={len(es):3d} {live:8s} kinds={kinds}")


def cmd_list():
    for e in extract():
        head = re.sub(r"\s+", " ", e["what"])[:100]
        print(f"{e['id']:52s} {e['liveness']:9s} {e['mechanism']:36s} {head}")


def cmd_mechanisms():
    entries = extract()
    mechs = {}
    for e in entries:
        mechs.setdefault(e["mechanism"], []).append(e)
    pm = pin_map()
    for m, es in sorted(mechs.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        live = "LIVE" if any(x["liveness"] == "live" for x in es) else "dormant"
        title = MECHANISM_TITLES.get(m, "")
        pinstr = ("PINNED: " + ", ".join(t.split("::")[-1] for t in pm[m])) if m in pm else "unpinned"
        kinds = ",".join(sorted({e["kind"] for e in es}))
        print(f"{m:36s} n={len(es):3d} {live:8s} [{kinds}] {pinstr}")
        if title:
            print(f"    {title}")
        sites = [
            (x["local_id"] + "@" + x["seam"]) if x["kind"] == "seam" else x["id"]
            for x in es
        ]
        print("    sites: " + ", ".join(sites))


def cmd_pins():
    for p in pins():
        print(
            f"{p['line']:5d} strict={p['strict']} {p['test'].split('::', 1)[1]:70s} "
            f"{p['seam']}/{p['gap']} steps={p['steps']}"
        )


def cmd_unpinned():
    entries = extract()
    mechs = {}
    for e in entries:
        mechs.setdefault(e["mechanism"], []).append(e)
    pm = pin_map()
    for m, es in sorted(mechs.items()):
        if m in pm:
            continue
        live = "LIVE" if any(x["liveness"] == "live" for x in es) else "dormant"
        print(f"{m:34s} n={len(es):2d} {live}")


def cmd_refs():
    for e in extract():
        if e["refs"]:
            print(f"{e['id']:38s} -> {','.join(e['refs'])}")


def cmd_json():
    json.dump(extract(), sys.stdout, indent=1)


GAME_ROOT = Path(r"c:\Users\Perry\Desktop\Slay the Spire 2")
QUEUE_DOC = ROOT / "audit" / "GAP-QUEUE.md"
_CITE = re.compile(r"`?([\w][\w./-]*\.(?:py|cs)):(\d+)(?:-(\d+))?`?")

# Citations the queue quotes BECAUSE they are broken -- the two stale record
# citations reported in its "Record inconsistencies" section.  Quoting them is
# the point; they must not be silently repaired, and cite-check must not fail on
# them.  Remove an entry here only when the record itself is corrected.
_KNOWN_BAD_CITATIONS = {
    "relics/spiked_gauntlets.py:26-32",  # hook_dispatch G2 evidence; file ends at 31
    "relics/fiddle.py:26-31",  # creature_card_cmds G9 / step 84; file ends at 29
}


def _candidates(name: str):
    """Every file a citation could name, sim tree first.

    Citations are written the way the records write them: repo-relative for the
    sim (``sts2_rl/cmds.py``), often sim-relative (``relics/anchor.py``), and by
    bare filename or partial path for the game (``Hook.cs``,
    ``Events/DenseVegetation.cs``).  Some bare names are ambiguous -- the game
    has both ``Models/Monsters/PaelsLegion.cs`` and ``Models/Relics/PaelsLegion.cs``.
    """
    out = []
    for base, prefix in (
        (ROOT, ""),
        (ROOT, "sts2_rl/"),
        (GAME_ROOT, ""),
        (GAME_ROOT, "src/Core/"),
    ):
        p = base / (prefix + name)
        if p.exists():
            out.append(p)
    out += list(GAME_ROOT.glob(f"src/**/{name}"))
    out += list(ROOT.glob(f"sts2_rl/**/{name}"))
    return list(dict.fromkeys(out))


def cmd_cite_check():
    """Every file:line cited in GAP-QUEUE.md must resolve to a real line."""
    text = QUEUE_DOC.read_text(encoding="utf-8")
    seen = {}
    bad = []
    for name, a, b in _CITE.findall(text):
        lo, hi = int(a), int(b or a)
        cite = f"{name}:{a}-{b}" if b else f"{name}:{a}"
        if cite in _KNOWN_BAD_CITATIONS:
            continue
        cands = _candidates(name)
        if not cands:
            bad.append(f"UNRESOLVED FILE  {name}:{a}")
            continue
        for p in cands:
            if p not in seen:
                seen[p] = len(
                    p.read_text(encoding="utf-8", errors="replace").splitlines()
                )
        # a citation is good if ANY candidate file covers the range
        if not any(1 <= lo and hi <= seen[p] for p in cands):
            longest = max(seen[p] for p in cands)
            bad.append(f"OUT OF RANGE     {name}:{a}-{b} (longest candidate has {longest} lines)")
    total = len(_CITE.findall(text))
    print(f"citations in {QUEUE_DOC.name}: {total}, files resolved: {len(seen)}")
    for line in sorted(set(bad)):
        print("  " + line)
    print(f"{len(set(bad))} problem(s)")
    return 1 if bad else 0


def cmd_coverage():
    """Every mechanism, and every gap entry, must be locatable in GAP-QUEUE.md.

    Two levels, both enforced:

    * a **mechanism** is covered when its key appears verbatim in the prose;
    * an **entry** is covered when its own id appears, or when its mechanism is
      named and the entry is reachable from that group.  For a seam entry the
      site list must also carry the local id (``/step31``) -- that check is
      older than the content tiers and is kept at full strength.  For a content
      entry, naming the mechanism is enough: 788 entries cannot each be spelled
      out in prose, and ``py audit/tools/gap_queue.py mechanisms`` regenerates
      the site list for any group on demand.
    """
    text = QUEUE_DOC.read_text(encoding="utf-8")
    entries = extract()
    mechs = {}
    for e in entries:
        mechs.setdefault(e["mechanism"], []).append(e)
    missing_m = [m for m in mechs if m not in text]
    missing_e = []
    for e in entries:
        if e["id"] in text:
            continue
        if e["mechanism"] not in text:
            missing_e.append(e["id"])
            continue
        if e["kind"] == "seam" and ("/" + e["local_id"]) not in text:
            missing_e.append(e["id"])
    print(f"mechanisms: {len(mechs)}, not named in the queue: {len(missing_m)}")
    for m in sorted(missing_m):
        print("  MISSING MECHANISM " + m + f"  (n={len(mechs[m])}, {mechs[m][0]['mech_liveness']})")
    print(f"entries: {len(entries)}, not locatable in the queue: {len(missing_e)}")
    for e in sorted(missing_e):
        print("  unlisted site " + e)
    return 1 if (missing_m or missing_e) else 0


COMMANDS = {
    "counts": cmd_counts,
    "list": cmd_list,
    "mechanisms": cmd_mechanisms,
    "pins": cmd_pins,
    "unpinned": cmd_unpinned,
    "refs": cmd_refs,
    "json": cmd_json,
    "cite-check": cmd_cite_check,
    "coverage": cmd_coverage,
}


def main(argv):
    if len(argv) != 2 or argv[1] not in COMMANDS:
        print(__doc__)
        print("commands: " + ", ".join(COMMANDS))
        return 2
    COMMANDS[argv[1]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
