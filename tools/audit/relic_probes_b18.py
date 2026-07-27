"""Reproducible execution probes for relic content audit BATCH 18.

Batch 18 is the roster's tail: two units.

  wongos_mystery_ticket  yummy_cookie

Own module per the batch-18 concurrency contract (`tools/audit/relic_probes.py`
is READ-ONLY to this batch -- re-use it, do not edit it; in particular
`py tools/audit/relic_probes.py sweep-reset` / `sweep-reset-exec` /
`sweep-upgrade` are the pool-wide inputs these records confirm or refute, and
`py tools/audit/relic_probes.py turn-order` is the executed hook-order
reference -- neither batch-18 unit implements a turn-structure hook, so no
record here leans on it).

Binding rules 5 and 6: never justify `faithful` with an unreachability claim
you have not EXECUTED, and never label a gap LIVE without proving both sides
reachable with ported content. Everything an `audits/relic/*.json` record from
this batch asserts about reachability is produced here.

  py tools/audit/relic_probes_b18.py                  # every probe
  py tools/audit/relic_probes_b18.py b18-pool         # one probe

Probes:
  b18-pool          obtainability of both units (rule 6, first half)
  b18-ticket        Wongo's Mystery Ticket: the whole countdown/payout
                    lifecycle through REAL dispatch (run.finish_combat ->
                    after_combat_end, generate_combat_rewards ->
                    modify_combat_rewards), on Monster / Elite / Boss screens
  b18-ticket-persist  Sweep A resolution: `combats_finished` / `gave_relic`
                    are per-RUN on BOTH sides (C# marks both [SavedProperty]),
                    so the missing reset is correct, not a belt_buckle. Shows
                    what a wrongly-reset instance would do.
  b18-ticket-rng    the three RelicReward.Populate rarity rolls land on the
                    per-player Rewards stream, in the same position as C#'s
  b18-ticket-final  LIVE GAP: on the FINAL act's boss the sim returns from
                    generate_combat_rewards BEFORE the modify_combat_rewards
                    loop, so a ripe ticket pays nothing; C#'s
                    RewardsSet.WithRewardsFromRoom returns early too but
                    GenerateWithoutOffering still runs Hook.ModifyRewards, so
                    the ticket pays its 3 relics.
  b18-ticket-bag    DORMANT GAP: an exhausted grab bag makes the sim hand out
                    fewer than 3 relics where C# substitutes FallbackRelic.
  b18-cookie        Yummy Cookie: 4 upgrades, the IsUpgradable candidate
                    filter (bug class 14 / sweep D), the short-deck auto-take,
                    and a max-level card's exclusion.
  b18-cookie-undo   no `undo_after_obtained`: the 4 upgrades survive a
                    conformance-runner relic swap (operational, per PROMPT.md
                    v6 item 3 this is NOT a fidelity gap).
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

BATCH18 = ["wongos_mystery_ticket", "yummy_cookie"]


# ── b18-pool ──────────────────────────────────────────────────────────────
def probe_b18_pool() -> None:
    """Where each batch-18 relic can come from (binding rule 6, first half).

    Same method as `relic_probes.py pool`: grab-bag membership comes from
    relic_pools.py (the transcribed C# pools); every other grant path is a
    literal relic id somewhere else under sts2_rl/, so grep for it.
    """
    import subprocess

    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    for rid in BATCH18:
        srcs = subprocess.run(
            ["git", "grep", "-l", f'"{rid}"', "--", "sts2_rl"],
            capture_output=True, text=True, cwd=_REPO,
        ).stdout.split()
        srcs = [s for s in srcs if not s.endswith(f"relics/{rid}.py")]
        print(f"  {rid:<24} registered={rid in ALL_RELICS} "
              f"bag={bag.get(rid, '-'):<9} granted_by={srcs or ['(none)']}")
    print("  (both are non-grab-bag rarities -- EVENT and ANCIENT -- so the "
          "grant path IS the reachability argument.)")


# ── helpers ───────────────────────────────────────────────────────────────
def _run_with_ticket(seed: int = 0, string_seed: str | None = None):
    """A RunState holding a Wongo's Mystery Ticket, plus the instance."""
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(seed), string_seed=string_seed)
    run.add_relic("wongos_mystery_ticket")
    ticket = next(r for r in run.relics if r.id == "wongos_mystery_ticket")
    return run, ticket


def _finish_one_combat(run, room_type) -> None:
    """Dispatch after_combat_end the way RunState.finish_combat does."""
    from sts2_rl import CombatState

    cs = CombatState(rng=random.Random(1), relics=run.relics,
                     max_hp=run.max_hp, current_hp=run.hp)
    run.finish_combat(cs, room_type=room_type)


# ── b18-ticket ────────────────────────────────────────────────────────────
def probe_b18_ticket() -> None:
    """The whole lifecycle, through the real dispatch sites.

    C# order per combat: Hook.AfterCombatEnd (CombatManager.cs:988,
    CombatsFinished++) THEN the reward screen (CombatRoom.OfferRoomEndRewards
    -> RewardsSet.GenerateWithoutOffering -> Hook.ModifyRewards). So the payout
    lands on the FIFTH combat's own screen, not the sixth -- which contradicts
    the port's docstring ("after 5 combats, the NEXT combat's reward screen").
    Verdict the code, not the comment (PROMPT.md bug class 24).
    """
    from sts2_rl.rooms import RoomType

    run, ticket = _run_with_ticket()
    print(f"  bag at start={len(run.relic_grab_bag)} "
          f"relics={[r.id for r in run.relics]}")
    for n in range(1, 8):
        _finish_one_combat(run, RoomType.MONSTER)
        n_relics, n_bag = len(run.relics), len(run.relic_grab_bag)
        rewards = run.generate_combat_rewards(RoomType.MONSTER)
        print(f"    combat {n}: combats_finished={ticket.combats_finished} "
              f"screen relics={[r.id for r in rewards.relics]} "
              f"run.relics {n_relics}->{len(run.relics)} "
              f"bag {n_bag}->{len(run.relic_grab_bag)} "
              f"gave_relic={ticket.gave_relic} is_used_up={ticket.is_used_up}")
    print("  C#: identical -- 5-CombatsFinished > 0 bails on screens 1-4, "
          "screen 5 adds DynamicVars.Repeat.IntValue == 3 RelicRewards and "
          "AfterModifyingRewards latches GaveRelic; screens 6+ bail on "
          "GaveRelic.")

    # The room gate. C# is `!(room is CombatRoom) -> return false`; the port
    # tests rewards.room_type against MONSTER/ELITE/BOSS.
    print("\n  room gate (C#: `room is CombatRoom`; port: room_type in "
          "{MONSTER, ELITE, BOSS}):")
    for rt in (RoomType.MONSTER, RoomType.ELITE, RoomType.BOSS):
        run, ticket = _run_with_ticket()
        for _ in range(5):
            _finish_one_combat(run, rt)
        rewards = run.generate_combat_rewards(rt)
        print(f"    {rt.name:<8} screen relics={len(rewards.relics)}")
    for rt in (RoomType.TREASURE, RoomType.SHOP, RoomType.EVENT,
               RoomType.REST_SITE):
        run, ticket = _run_with_ticket()
        for _ in range(5):
            _finish_one_combat(run, RoomType.MONSTER)
        try:
            run.generate_combat_rewards(rt)
            outcome = "generated a screen"
        except ValueError as exc:
            outcome = f"ValueError({exc})"
        print(f"    {rt.name:<10} -> {outcome}")
    print("  => the port's room_type tuple is never the thing that rejects a "
          "screen: generate_combat_rewards refuses every non-combat room type "
          "before the hook loop is reached (rewards.py:438-439). The gate "
          "agrees with C# for the reachable inputs. Event-initiated fights "
          "(EventModel.EnterCombatWithoutExitingEvent builds a CombatRoom, so "
          "C# accepts them) reach the sim as RoomType.MONSTER "
          "(driver.py:410-420), so they are accepted on both sides.")


# ── b18-ticket-persist ────────────────────────────────────────────────────
def probe_b18_ticket_persist() -> None:
    """Sweep A flagged `combats_finished` / `gave_relic` as never reset.

    Settled here per PROMPT.md bug class 13's reader trace: BOTH fields are
    [SavedProperty] in C# (WongosMysteryTicket.cs:38-70), i.e. they are meant
    to survive save/load, so they are per-RUN on both sides and the port is
    correct. The current (rewritten) sweep-reset row agrees -- it prints
    `C# resets: NONE` for this relic, because the corrected census brace-
    matches the body and `CombatsFinished++` is not an assignment. The batch
    brief's pre-diagnosis ("C# resets at AfterCombatEnd") is the OLD override-
    census reading and is wrong.

    Shown two ways: (a) the carried instance is the only one that can ever
    reach 5; (b) a per-combat reset would make the relic dead code.
    """
    from sts2_rl.relics import make_relic
    from sts2_rl.rooms import RoomType

    run, ticket = _run_with_ticket()
    for n in range(1, 6):
        _finish_one_combat(run, RoomType.MONSTER)
        fresh = make_relic("wongos_mystery_ticket")
        print(f"    after combat {n}: carried.combats_finished="
              f"{ticket.combats_finished} fresh.combats_finished="
              f"{fresh.combats_finished}")
    rewards = run.generate_combat_rewards(RoomType.MONSTER)
    print(f"  carried instance pays out: {len(rewards.relics)} relics")

    run2, _ = _run_with_ticket(seed=1)
    for n in range(20):
        # Simulate the "reset every combat" reading the sweep's stale column
        # implies: a fresh instance each combat never accumulates.
        t = make_relic("wongos_mystery_ticket")
        t.after_combat_end(run2, RoomType.MONSTER)
    rewards2 = run2.generate_combat_rewards(RoomType.MONSTER)
    print(f"  a per-combat-reset ticket after 20 combats pays out: "
          f"{len(rewards2.relics)} relics  <- the relic would never fire, "
          f"which is why the missing reset is CORRECT here")


# ── b18-ticket-rng ────────────────────────────────────────────────────────
def probe_b18_ticket_rng() -> None:
    """The three relic pulls each burn one rarity roll on the Rewards stream.

    C#: `new RelicReward(player)` leaves _rarity == RelicRarity.None, so
    RelicReward.Populate takes `RelicFactory.PullNextRelicFromFront(player)`
    -> `RollRarity(player)` -> `player.PlayerRng.Rewards` (RelicFactory.cs:
    26-29, 80-83). The bag pull itself consumes nothing.

    Position: C# populates the pre-existing rewards, runs Hook.ModifyRewards,
    then populates the newly-added rewards (RewardsSet.cs:131-146). The sim
    rolls gold / potion / cards before the hook loop and pulls inside the hook
    (rewards.py:453-500). Same relative order -- the ticket's draws come last
    either way. (Same finding as audits/relic/lava_rock.json guard N3.)
    """
    from sts2_rl.rooms import RoomType

    for ripe in (False, True):
        run, ticket = _run_with_ticket(string_seed="B18TICKET")
        for _ in range(5 if ripe else 1):
            _finish_one_combat(run, RoomType.MONSTER)
        rew = run.rewards_rng
        before = rew.counter
        rewards = run.generate_combat_rewards(RoomType.MONSTER)
        print(f"    ripe={ripe!s:<5} Rewards-stream counter "
              f"{before} -> {rew.counter} (delta {rew.counter - before})  "
              f"relics={[r.id for r in rewards.relics]}")
    print("  delta difference == 3 => exactly one rarity NextFloat per relic, "
          "on the per-player Rewards stream, as C# does.")


# ── b18-ticket-final ──────────────────────────────────────────────────────
def probe_b18_ticket_final() -> None:
    """LIVE GAP: the final act's boss screen never reaches the hook loop.

    `generate_combat_rewards` returns an empty CombatRewards at
    rewards.py:440-441 when `room_type == BOSS and run.is_final_act` -- BEFORE
    the `modify_combat_rewards` dispatch at rewards.py:499-500.

    C# does the same early return in the WRONG PLACE for this to match:
    `RewardsSet.WithRewardsFromRoom` (RewardsSet.cs:85-89) returns before
    adding any GoldReward/CardReward/PotionReward, but `Room` is already set
    and `GenerateWithoutOffering` (RewardsSet.cs:125-146) still runs
    `Hook.ModifyRewards(runState, player, Rewards, Room)` on the empty list.
    So a ripe Wongo's ticket appends its 3 RelicRewards, they Populate, and
    `Offer()` shows them (`Rewards.Count <= 0 && !flag` cannot fire -- flag is
    `Room is CombatRoom`). CombatRoom.OfferRoomEndRewards is reached for the
    final boss like any other win (NCombatUi.OnCombatWon -> ShowRewards,
    NCombatUi.cs:181-226, gated only on Encounter.ShouldGiveRewards).
    """
    from sts2_rl.rooms import RoomType

    for final in (False, True):
        run, ticket = _run_with_ticket()
        run._is_final_act = final          # what start_act(is_final_act=) sets
        for _ in range(5):
            _finish_one_combat(run, RoomType.MONSTER)
        n_relics, n_bag = len(run.relics), len(run.relic_grab_bag)
        rewards = run.generate_combat_rewards(RoomType.BOSS)
        print(f"    is_final_act={final!s:<5} BOSS screen relics="
              f"{[r.id for r in rewards.relics]} run.relics "
              f"{n_relics}->{len(run.relics)} bag {n_bag}->"
              f"{len(run.relic_grab_bag)} gave_relic={ticket.gave_relic}")
    print("  C# on the final boss: 3 relics offered and GaveRelic latched. "
          "The sim: 0 relics, ticket still armed for a screen that will never "
          "come (the run ends).")
    print("  Reachable with ported content: the ticket is bought at the ported "
          "Welcome to Wongo's mystery box (events/welcome_to_wongos.py:82-83) "
          "and has NO act or room-type restriction, so any run whose 5th "
          "reward-giving combat after the purchase is the last act's boss hits "
          "this. The four other ported modify_combat_rewards implementers "
          "cannot: black_star is Elite-only, lava_rock is act-0-only, "
          "driftwood and paels_wing both gate on `rewards.cards`, which is "
          "empty on that screen.")


# ── b18-ticket-bag ────────────────────────────────────────────────────────
def probe_b18_ticket_bag() -> None:
    """DORMANT GAP: an exhausted grab bag yields fewer than 3 relics.

    C#: `RelicFactory.PullNextRelicFromFront` is
    `player.RelicGrabBag.PullFromFront(...) ?? FallbackRelic`
    (RelicFactory.cs:45-50), so all three RelicRewards always resolve to a
    relic. The port `break`s out of its loop when `run.pull_relic_from_front()`
    returns None (only when the bag is EMPTY -- a rarity miss falls back to the
    bag's front, run.py:585-595) and still latches gave_relic.
    """
    from sts2_rl.rooms import RoomType

    for left in (3, 2, 0):
        run, ticket = _run_with_ticket()
        del run.relic_grab_bag[left:]
        for _ in range(5):
            _finish_one_combat(run, RoomType.MONSTER)
        rewards = run.generate_combat_rewards(RoomType.MONSTER)
        print(f"    bag={left} -> screen relics={len(rewards.relics)} "
              f"gave_relic={ticket.gave_relic} (C#: 3, padding with "
              f"RelicFactory.FallbackRelic)")
    print("  DORMANT: the transcribed bag holds "
          f"{len(_run_with_ticket()[0].relic_grab_bag)} relics at run start "
          "and nothing in a ported run drains it. It becomes live only if the "
          "bag is exhausted, which needs far more relic pulls than a run has.")


# ── b18-cookie ────────────────────────────────────────────────────────────
def probe_b18_cookie() -> None:
    """Yummy Cookie: CardsVar(4) upgrades from the IsUpgradable deck cards.

    C#: `CardSelectCmd.FromDeckForUpgrade` filters
    `PileType.Deck.GetPile(player).Cards.Where(c => c.IsUpgradable)`
    (CardSelectCmd.cs:442) and auto-takes the whole list when
    `list.Count <= prefs.MinSelect` (CardSelectCmd.cs:448-451); then
    `CardCmd.Upgrade` skips `!IsUpgradable` again (CardCmd.cs:273-276).
    The sim's Card.upgrade() (cards/base.py:146-148) is unguarded, so the
    candidate list has to carry the filter -- run.upgradable_cards()
    (run.py:368-369) does. Sweep D's CURRENT output lists yummy_cookie under
    "guarded (for contrast)"; the batch brief's claim that it is in the
    unguarded list is the pre-correction reading (sweep D's own footnote names
    yummy_cookie as one of five over-reports).
    """
    from sts2_rl.cards import make_card
    from sts2_rl.run import RunState

    # (a) a normal starting deck: exactly 4 upgrades
    run = RunState(rng=random.Random(3))
    n_cand = len(run.upgradable_cards())
    run.add_relic("yummy_cookie")
    ups = sorted((c.id, c.upgrade_level) for c in run.deck
                 if c.upgrade_level > 0)
    print(f"    starting deck: candidates={n_cand} upgraded={len(ups)} {ups}")

    # (b) level-0-max cards are never offered and never touched
    run = RunState(rng=random.Random(3))
    curse = make_card("curse_of_the_bell")          # max_upgrade_level 0
    run.deck.append(curse)
    dazed = make_card("dazed")
    run.deck.append(dazed)
    cand_ids = sorted({c.id for c in run.upgradable_cards()})
    run.add_relic("yummy_cookie")
    print(f"    with a curse + a status: curse in candidates="
          f"{'curse_of_the_bell' in cand_ids} status in candidates="
          f"{'dazed' in cand_ids} curse_level={curse.upgrade_level} "
          f"status_level={dazed.upgrade_level} "
          f"(C#: CardCmd.Upgrade skips !IsUpgradable)")

    # (c) fewer than 4 candidates -> take them all (C#: the auto-take branch)
    for keep in (4, 3, 1, 0):
        run = RunState(rng=random.Random(3))
        del run.deck[keep:]
        for c in run.deck:
            pass
        run.add_relic("yummy_cookie")
        ups = [(c.id, c.upgrade_level) for c in run.deck
               if c.upgrade_level > 0]
        print(f"    deck of {keep} upgradable card(s) -> upgraded="
              f"{len(ups)} levels={sorted(l for _, l in ups)}")

    # (d) a card already at max level drops out of the candidate list
    run = RunState(rng=random.Random(3))
    del run.deck[2:]
    maxed = run.deck[0]
    while maxed.is_upgradable:
        maxed.upgrade()
    print(f"    {maxed.id} at level {maxed.upgrade_level}/"
          f"{maxed.max_upgrade_level}: is_upgradable={maxed.is_upgradable} "
          f"candidates={[c.id for c in run.upgradable_cards()]}")
    run.add_relic("yummy_cookie")
    print(f"    after the cookie: {maxed.id} level={maxed.upgrade_level} "
          f"(unchanged => no over-upgrade), other="
          f"{[(c.id, c.upgrade_level) for c in run.deck[1:]]}")

    # (e) the residual the C# screen forbids: a selector that returns the same
    # card twice. C#'s NDeckUpgradeSelectScreen returns a set of distinct
    # cards; run.select_cards only truncates to `count`.
    run = RunState(rng=random.Random(3))
    target = run.deck[0]
    run.card_selector = lambda purpose, cands, count: [target] * count
    run.add_relic("yummy_cookie")
    print(f"    duplicate-returning selector: {target.id} level="
          f"{target.upgrade_level} max={target.max_upgrade_level} "
          f"(C#: a selection screen cannot return the same card twice)")


# ── b18-cookie-undo ───────────────────────────────────────────────────────
def probe_b18_cookie_undo() -> None:
    """`undo_after_obtained` is not implemented, so the 4 upgrades stick.

    PROMPT.md v6 binding item 3: the ABSENCE of undo_after_obtained is
    `faithful` at every site -- the helper has no C# counterpart, nothing in
    the game un-picks a relic. The operational consequence still belongs in
    the record: the conformance runner grants a node's relic and then swaps it
    for the one the save says was really picked, and an unwound Yummy Cookie
    leaves 4 deck cards upgraded, which runner.py's deck comparison reads as a
    parity failure.
    """
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(3))
    before = sorted((c.id, c.upgrade_level) for c in run.deck)
    cookie = run.add_relic("yummy_cookie")
    mid = sorted((c.id, c.upgrade_level) for c in run.deck)
    cookie.undo_after_obtained(run)
    run.relics.remove(cookie)
    after = sorted((c.id, c.upgrade_level) for c in run.deck)
    print(f"    upgraded before={sum(1 for _, l in before if l)} "
          f"after pickup={sum(1 for _, l in mid if l)} "
          f"after undo+remove={sum(1 for _, l in after if l)}")
    print(f"    undo_after_obtained is the base no-op: "
          f"{type(cookie).undo_after_obtained is make_relic('yummy_cookie').__class__.__mro__[-2].undo_after_obtained}")


PROBES = {
    "b18-pool": probe_b18_pool,
    "b18-ticket": probe_b18_ticket,
    "b18-ticket-persist": probe_b18_ticket_persist,
    "b18-ticket-rng": probe_b18_ticket_rng,
    "b18-ticket-final": probe_b18_ticket_final,
    "b18-ticket-bag": probe_b18_ticket_bag,
    "b18-cookie": probe_b18_cookie,
    "b18-cookie-undo": probe_b18_cookie_undo,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("probe", nargs="?", choices=sorted(PROBES))
    args = ap.parse_args(argv)
    for name in ([args.probe] if args.probe else PROBES):
        print(f"\n== {name} ==")
        PROBES[name]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
