"""Reproducible execution probes for the `seam/relic_pools` audit.

Companion to `audit/tools/relic_probes.py` (the relic CONTENT tier) and
`audit/tools/dormancy_probes.py` (the seam tier generally). Every reachability
claim `audit/records/seam/relic_pools.json` makes is produced here, so a later
auditor re-derives the number instead of trusting a throwaway script.

  py audit/tools/relic_pool_probes.py                    # every probe
  py audit/tools/relic_pool_probes.py back-pull-ladder    # one probe

Probes:
  back-pull-ladder     **CLOSED 2026-08-03**: `pull_relic_from_back` now
                        shares the escalation ladder + Circlet fallback with
                        `pull_relic_from_front`, matching
                        `RelicFactory.PullNextRelicFromBack` (which shares
                        `GetAvailableDeque` with `PullNextRelicFromFront` and
                        falls back to `FallbackRelic` the same way,
                        RelicFactory.cs:47,75). This probe now asserts the
                        FIXED behavior (an exhausted Rare deque climbs to a
                        Circlet, not `None`) -- kept as a regression witness.
  shop-rarity-misroute  **CLOSED 2026-08-03**: a shop's Shop-rarity relic
                        slot now draws from the real, UpFront-populated Shop
                        deque already sitting in `run.relic_grab_bag` /
                        `run.player_relic_bag["Shop"]`, instead of the
                        disconnected legacy `_get_shop_relic_bag()`. This
                        probe now asserts the FIXED behavior (the parity bag
                        shrinks by one and the pulled relic is gone from it)
                        -- kept as a regression witness.
  refresh-allowed-dead  RelicGrabBag's `_refreshAllowed` refill branch is
                        dead code in the WHOLE decompiled game, not merely
                        dormant pending an exhausted rarity (corrects
                        `relic/circlet/g4`'s framing -- see the seam record's
                        guards section for the full citation trail)
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def back_pull_ladder() -> None:
    from sts2_rl.relics import ALL_RELICS, RelicRarity
    from sts2_rl.run import RunState

    run = RunState(string_seed="PROBE_BACKPULL")
    rares = [r for r in list(run.relic_grab_bag)
             if ALL_RELICS[r].rarity == RelicRarity.RARE]
    for r in rares:
        run.relic_grab_bag.remove(r)
    assert not any(ALL_RELICS[r].rarity == RelicRarity.RARE
                   for r in run.relic_grab_bag), "Rare deque not actually drained"

    back = run.pull_relic_from_back(RelicRarity.RARE, set())
    front = run.pull_relic_from_front(rarity=RelicRarity.RARE)

    print("pull_relic_from_back(RARE) on an exhausted Rare deque:",
          back.id if back else None, "(C# PullNextRelicFromBack climbs "
          "Rare -> [ladder ends] -> FallbackRelic, RelicFactory.cs:75/47, "
          "and never returns nothing)")
    print("pull_relic_from_front(RARE) on the same exhausted deque:",
          front.id if front else None, "(also escalates/falls back)")
    assert back is not None and back.id == "circlet", (
        "expected the sim's back-pull to climb the ladder and fall back to "
        "Circlet, matching PullNextRelicFromBack (FIXED 2026-08-03)")
    assert front is not None and front.id == "circlet", (
        "expected the front-pull to fall back to Circlet")
    print("CLOSED 2026-08-03: pull_relic_from_back now shares the "
          "escalation ladder and Circlet fallback that pull_relic_from_front "
          "has, matching RelicFactory.PullNextRelicFromBack's C# (same "
          "GetAvailableDeque as PullNextRelicFromFront). Every shop visit's "
          "two rolled-rarity relic slots (MerchantRelicEntry, "
          "shop.py:_populate_relics) go through this path.")


def shop_rarity_misroute() -> None:
    from sts2_rl.relics import ALL_RELICS, RelicRarity
    from sts2_rl.run import RunState

    run = RunState(string_seed="PROBE_SHOPMISROUTE")
    assert run.rng_set is not None, "expected the parity RNG path"
    shop_deque = run.player_relic_bag.get("Shop", [])
    flat_shop_members = [r for r in run.relic_grab_bag
                          if ALL_RELICS[r].rarity == RelicRarity.SHOP]
    print(f"run.player_relic_bag['Shop'] (UpFront-populated, game-faithful "
          f"deque): {len(shop_deque)} relics, e.g. {shop_deque[:3]}")
    print(f"run.relic_grab_bag's Shop-rarity members (the SAME relics, "
          f"already flattened in): {len(flat_shop_members)}, "
          f"e.g. {flat_shop_members[:3]}")

    before = len(run.relic_grab_bag)
    pulled = run.pull_relic_from_back(RelicRarity.SHOP, set())
    after = len(run.relic_grab_bag)

    print(f"shop's Shop-rarity slot pulled: {pulled.id if pulled else None}")
    print(f"run.relic_grab_bag length before/after that pull: {before}/{after}")
    still_present = pulled is not None and pulled.id in run.relic_grab_bag
    print(f"the pulled relic is STILL sitting, unconsumed, in "
          f"run.relic_grab_bag: {still_present}")

    assert after == before - 1, (
        "expected the Shop pull to consume exactly one relic from the "
        "parity-populated bag (FIXED 2026-08-03)")
    assert not still_present, (
        "expected the pulled relic to be GONE from relic_grab_bag, proving "
        "the pull actually consumed that structure")
    assert run._shop_relic_bag is None, (
        "expected the disconnected legacy _get_shop_relic_bag() to never be "
        "built on the parity path")
    print("CLOSED 2026-08-03: RelicFactory.PullNextRelicFromBack(player, "
          "Shop, IsAllowedInShops) pulls from player.RelicGrabBag's OWN Shop "
          "deque -- the same object Populate(Player, Rng) filled alongside "
          "Common/Uncommon/Rare (RelicGrabBag.cs:69-92, MerchantRelicEntry.cs"
          ":39). run.pull_relic_from_back now routes a Shop-rarity pull (on "
          "the SP2 parity path) through the SAME run.relic_grab_bag / "
          "run.player_relic_bag['Shop'] deque that populate_relic_grab_bags "
          "seeded on the UpFront stream, instead of the disconnected, "
          "independently-shuffled RunState._get_shop_relic_bag(). The "
          "legacy (no string_seed) path still uses _get_shop_relic_bag() for "
          "Shop rarity specifically -- relic_pools/guard4 (its relic_grab_bag "
          "never contains Shop-rarity relics at all) is a separate, still-"
          "open, dormant gap in that path's run-init population step, left "
          "unfixed here to avoid changing every legacy run's RNG draw count.")


def refresh_allowed_dead() -> None:
    """Not a sim-side execution -- a documentation probe recording the C#-side
    census that shows RelicGrabBag's `_refreshAllowed` branch has no live
    caller anywhere in the decompiled game, corrected from `relic/circlet/g4`'s
    framing. Grep commands are printed so a later auditor can re-run them
    against a newer decompile rather than trust this file's prose."""
    checks = [
        ('only 2 Player-construction sites, both refreshAllowed=false '
         '(the parameterless RelicGrabBag() ctor)',
         'grep -n "new RelicGrabBag(" src/Core/Entities/Players/Player.cs'),
        ('the ONLY refreshAllowed:true instances are RunState.SharedRelicGrabBag '
         '(RunState.cs CreateShared, x2) -- there is no separate "shop" bag',
         'grep -rn "new RelicGrabBag(" src/'),
        ('SharedRelicGrabBag never has GetAvailableDeque/PullFromFront/'
         'PullFromBack/HasAvailableRelics called on it anywhere -- only '
         '.Remove()/.Populate()/serialization',
         'grep -rn "SharedRelicGrabBag\\.\\(PullFromFront\\|PullFromBack\\|'
         'GetAvailableDeque\\|HasAvailableRelics\\)" src/'),
    ]
    for finding, cmd in checks:
        print(f"- {finding}\n    ({cmd})")
    print("CONCLUSION: the `_refreshAllowed` branch (RelicGrabBag.cs:222-226) "
          "is unreachable from ANY code path in the whole decompiled game, "
          "not merely dormant pending an exhausted rarity as "
          "`relic/circlet/g4`'s guard entry frames it ('this only applies to "
          "the shop's own RelicGrabBag instance' -- no such instance exists; "
          "the true refreshAllowed:true object is the run-level "
          "SharedRelicGrabBag, and it is never queried for a pull). Reported "
          "as a cross-record disagreement in seam/relic_pools, not edited "
          "into relic/circlet.json directly (rule 3).")


PROBES = {
    "back-pull-ladder": back_pull_ladder,
    "shop-rarity-misroute": shop_rarity_misroute,
    "refresh-allowed-dead": refresh_allowed_dead,
}


def main() -> None:
    names = sys.argv[1:] or list(PROBES)
    for name in names:
        fn = PROBES.get(name)
        if fn is None:
            print(f"unknown probe {name!r}; choices: {list(PROBES)}")
            continue
        print(f"\n=== {name} ===")
        fn()


if __name__ == "__main__":
    main()
