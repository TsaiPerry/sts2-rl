r"""Conformance coverage: which ported content has actually been exercised by
one of the reference Ironclad seeds' saves, which is ported-but-untested, and
which recorded content is unported.

CAVEAT (2026-07-23): neither reference seed is fully converged yet -- the SP3
per-seed convergence grind (Task 8) is in progress. "Seen" below means
"present in the seed's deepest available save", NOT "verified byte-for-byte
against the sim". Bucket (b) -- ported-but-untested -- is still a useful
shopping list for the next recording regardless of convergence status.

Three buckets, per content type (relics / potions / cards / encounters /
events):
  (a) seen    -- appears in a reference seed's save (trusted-ish exposure)
  (b) untested -- ported in the sim but never seen in a reference seed
                  (fidelity risk; the next recording should target these)
  (c) unmapped -- appears in ANY recording (all 6 seeds, any character) but
                  idmap/registry cross-reference can't place it in the sim
                  (known debt -- may include legitimately out-of-scope
                  non-Ironclad content, see the report)

Usage: py tools/conformance_coverage.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
REC = _REPO.parent / "RunReplays" / "RunReplays" / "Resources"

from sts2_rl.conformance import idmap                                # noqa: E402
from sts2_rl.conformance.ids import ENCOUNTER_GAME_IDS, event_game_id  # noqa: E402
from sts2_rl.conformance.save import parse_save                      # noqa: E402

# Ironclad-only reference seeds (the only fully-Ironclad recordings we have).
# Update as seeds go green -- see CAVEAT above about current convergence status.
REFERENCE_SEEDS = ["89U21BV1TZ", "933T39V18D"]


def _latest_save(seed_dir: Path) -> Path | None:
    """The deepest available run.save for a seed (floor_49 preferred)."""
    for floor in ("floor_49", "floor_34", "floor_18"):
        f = seed_dir / floor / "run.save"
        if f.exists():
            return f
    return None


def _act_encounter_game_ids(act: dict) -> list[str]:
    ids = list(act.get("normal", [])) + list(act.get("elite", []))
    if act.get("boss"):
        ids.append(act["boss"])
    if act.get("second_boss"):
        ids.append(act["second_boss"])
    return ids


def main() -> None:
    from sts2_rl.relics import ALL_RELICS
    from sts2_rl.potions import ALL_POTIONS
    from sts2_rl.events import ALL_EVENTS
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.monsters.overgrowth import ENCOUNTERS as OG_ENC
    from sts2_rl.monsters.underdocks import ENCOUNTERS as UD_ENC
    from sts2_rl.monsters.hive import ENCOUNTERS as HV_ENC
    from sts2_rl.monsters.glory import ENCOUNTERS as GL_ENC

    all_encounters = {**OG_ENC, **UD_ENC, **HV_ENC, **GL_ENC}
    game_id_to_encounter = {v: k for k, v in ENCOUNTER_GAME_IDS.items()}
    game_id_to_event = {event_game_id(k): k for k in ALL_EVENTS}

    # ------------------------------------------------------------------
    # Bucket (a)/(b): exposure in the reference Ironclad seeds.
    # ------------------------------------------------------------------
    seen_relics, seen_potions, seen_cards = set(), set(), set()
    seen_encounters, seen_events = set(), set()
    used_seeds = []
    for seed in REFERENCE_SEEDS:
        f = REC / seed / "floor_49" / "run.save"
        if not f.exists():
            print(f"  (skip {seed}: no floor_49/run.save found)")
            continue
        used_seeds.append(seed)
        o = parse_save(f)
        seen_relics |= {idmap.sim_relic_id(r) for r in o.relic_ids}
        seen_potions |= {idmap.sim_potion_id(p) for p in o.potion_slots.values()}
        seen_cards |= {idmap.sim_card_id(c) for c, _ in o.deck}
        for act in o.encounter_ids_by_act:
            seen_encounters |= {
                game_id_to_encounter.get(g) for g in _act_encounter_game_ids(act)
            }
            # act["ancient"] is an EVENT id (Neow/Orobas/Tanx), not an encounter.
            if act.get("ancient"):
                seen_events.add(game_id_to_event.get(act["ancient"]))
        seen_events |= {game_id_to_event.get(e) for e in o.events_seen}

    for s in (seen_relics, seen_potions, seen_cards, seen_encounters, seen_events):
        s.discard(None)

    untested_relics = sorted(set(ALL_RELICS) - seen_relics)
    untested_potions = sorted(set(ALL_POTIONS) - seen_potions)
    untested_encounters = sorted(set(all_encounters) - seen_encounters)
    untested_events = sorted(set(ALL_EVENTS) - seen_events)

    print("=" * 72)
    print("CONFORMANCE COVERAGE")
    print("=" * 72)
    print("Reference seeds used:", ", ".join(used_seeds) or "(none found)")
    print("NOTE: neither reference seed is fully converged yet (the SP3")
    print("per-seed convergence grind is in progress). 'seen' below means")
    print("'present in that seed's deepest available save', not 'verified")
    print("byte-for-byte against the sim'.\n")

    print(f"relics     seen {len(seen_relics):3d} / ported {len(ALL_RELICS):3d}")
    print(f"potions    seen {len(seen_potions):3d} / ported {len(ALL_POTIONS):3d}")
    print(f"cards      seen {len(seen_cards):3d} / ported {len(_CARD_CLASSES):3d}"
          "   (rough signal only -- deck composition is noisy/optional per brief)")
    print(f"encounters seen {len(seen_encounters):3d} / ported {len(all_encounters):3d}")
    print(f"events     seen {len(seen_events):3d} / ported {len(ALL_EVENTS):3d}")

    print("\n--- (b) UNTESTED relics (recording shopping list) ---")
    print("  " + (", ".join(untested_relics) or "(none)"))
    print("\n--- (b) UNTESTED potions ---")
    print("  " + (", ".join(untested_potions) or "(none)"))
    print("\n--- (b) UNTESTED encounters ---")
    print("  " + (", ".join(untested_encounters) or "(none)"))
    print("\n--- (b) UNTESTED events ---")
    print("  " + (", ".join(untested_events) or "(none)"))

    # ------------------------------------------------------------------
    # Bucket (c): content appearing in ANY recording (all 6 seeds, any
    # character) but not mapped to a sim id -- known debt. Deliberately a
    # broader scan than the reference seeds: the 4 non-Ironclad seeds are
    # exactly where off-class (out-of-scope) content shows up, alongside any
    # genuine Ironclad-pool gaps.
    # ------------------------------------------------------------------
    unmapped_relics, unmapped_potions, unmapped_cards = set(), set(), set()
    unmapped_encounters, unmapped_events = set(), set()
    scanned = []
    if REC.exists():
        for seed_dir in sorted(p for p in REC.iterdir() if p.is_dir()):
            f = _latest_save(seed_dir)
            if f is None:
                continue
            scanned.append(seed_dir.name)
            o = parse_save(f)
            for r in o.relic_ids:
                if idmap.sim_relic_id(r) is None:
                    unmapped_relics.add(r)
            for p in o.potion_slots.values():
                if idmap.sim_potion_id(p) is None:
                    unmapped_potions.add(p)
            for c, _ in o.deck:
                if idmap.sim_card_id(c) is None:
                    unmapped_cards.add(c)
            for act in o.encounter_ids_by_act:
                for g in _act_encounter_game_ids(act):
                    if g not in game_id_to_encounter:
                        unmapped_encounters.add(g)
                if act.get("ancient") and act["ancient"] not in game_id_to_event:
                    unmapped_events.add(act["ancient"])
            for e in o.events_seen:
                if e not in game_id_to_event:
                    unmapped_events.add(e)

    print("\n" + "=" * 72)
    print(f"(c) RECORDED BUT UNPORTED (known debt) -- scanned {len(scanned)} "
          f"seeds' deepest saves: {', '.join(scanned) or '(none found)'}")
    print("NOTE: these 6 seeds are 5 different characters (only 89U/933T are")
    print("Ironclad) -- most entries below are other classes' content, which")
    print("is out of scope for this Ironclad-only sim, not a real gap.")
    print("=" * 72)
    print("relics:     " + (", ".join(sorted(unmapped_relics)) or "(none)"))
    print("potions:    " + (", ".join(sorted(unmapped_potions)) or "(none)"))
    print("cards:      " + (f"{len(unmapped_cards)} unmapped ids (mostly other "
                             "classes' cards -- omitted, see script for the set)"))
    print("encounters: " + (", ".join(sorted(unmapped_encounters)) or "(none)"))
    print("events:     " + (", ".join(sorted(unmapped_events)) or "(none)"))


if __name__ == "__main__":
    main()
