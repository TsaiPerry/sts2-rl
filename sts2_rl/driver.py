"""RunDriver — a whole STS2 run as straight-line code with every decision
delegated to one injectable callback.

The driver walks the run exactly like the game does:

    start_run → Neow → (travel → enter room → resolve it
        [combat turns → post-combat rewards / event pages / shop purchases /
         rest choice]) → act boss → advance_act → … → victory or death

and at every choice point calls ``ask(DecisionRequest) -> int``. That single
seam serves two callers:

  - tests / scripted play pass a plain function (e.g. ``random_asker`` picks
    uniformly among ``request.legal_actions()``) — no suspension machinery;
  - the run env (run_env.py) passes a greenlet switch, turning every request
    into a Gym step (RL.md's "two-phase env" design), fully on-policy.

Mid-resolution selections are the same seam: the driver installs itself as
``RunState.card_selector`` / ``option_selector`` (and, via create_combat, as
every combat's ``card_selector``), so a Pommel Strike discard choice or an
event's transform pick surfaces as a SELECT_CARDS request. Forced choices
(count ≥ candidates, non-skippable) short-circuit without asking, mirroring
test/run.py's interactive selector.

Combat actions reuse the flat combat block from full_env.py
(decode_combat_action / combat_action_masks), so a combat policy trained on
STS2FullCombatEnv speaks the same action language here.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Callable

import numpy as np

from .full_env import (
    apply_combat_action,
    combat_action_masks,
)
from .rewards import GOLD_REWARD_RANGES, CombatRewards
from .rooms import RoomType

if TYPE_CHECKING:
    from .actmap import MapPoint
    from .cards import Card
    from .combat import CombatState
    from .events.base import Event
    from .monsters import Encounter
    from .run import RunState
    from .shop import MerchantInventory


class DecisionKind(Enum):
    MAP = "map"                    # pick a travelable point
    EVENT = "event"                # pick an event option (locked = illegal)
    SHOP = "shop"                  # pick a purchasable entry, or leave
    REST = "rest"                  # heal / smith / leave
    REWARD_CARD = "reward_card"    # pick one of the reward cards, or skip
    REWARD_POTION = "reward_potion"  # take the potion, or skip
    COMBAT = "combat"              # a flat combat-block action (full_env.py)
    SELECT_CARDS = "select_cards"  # pick a candidate card (one per request)
    SELECT_OPTION = "select_option"  # pick a generic option (Scroll Boxes)


# Rest-site option order (RestSiteOption.Generate: Heal + Smith; leave last).
REST_HEAL, REST_SMITH, REST_LEAVE = 0, 1, 2
N_REST_OPTIONS = 3

# select_cards purposes where declining is a real choice (a card offer, not a
# mandatory selection): the action index == len(candidates) means "skip".
SKIPPABLE_PURPOSES = frozenset({"card_reward", "obtain"})


@dataclass
class DecisionRequest:
    """One pending decision. `kind` says which payload fields are set and how
    the integer answer is interpreted; `legal_actions()` is the ground truth
    the asker must pick from (the run env turns it into an action mask)."""

    kind: DecisionKind
    run: "RunState"
    combat: "CombatState | None" = None          # COMBAT, in-combat SELECT_*
    event: "Event | None" = None                 # EVENT
    shop: "MerchantInventory | None" = None      # SHOP
    rewards: "CombatRewards | None" = None       # REWARD_CARD / REWARD_POTION
    points: "list[MapPoint]" = field(default_factory=list)   # MAP
    purpose: str = ""                            # SELECT_CARDS / SELECT_OPTION
    candidates: "list[Card]" = field(default_factory=list)   # SELECT_CARDS
    count_remaining: int = 0                     # SELECT_CARDS (multi-pick)
    skippable: bool = False                      # SELECT_CARDS
    n_options: int = 0                           # SELECT_OPTION
    rest_options: "list | None" = None           # REST: this visit's option snapshot
    rest_heal_used: bool = False                 # REST
    rest_smith_used: bool = False                # REST

    def legal_actions(self) -> list[int]:
        kind = self.kind
        if kind == DecisionKind.MAP:
            return list(range(len(self.points)))
        if kind == DecisionKind.EVENT:
            return [
                i for i, opt in enumerate(self.event.options) if not opt.locked
            ]
        if kind == DecisionKind.SHOP:
            entries = self.shop.all_entries
            legal = [
                i for i, e in enumerate(entries)
                if e.is_stocked and e.enough_gold
            ]
            legal.append(len(entries))           # leaving is always legal
            return legal
        if kind == DecisionKind.REST:
            legal = []
            if not self.rest_heal_used:
                legal.append(REST_HEAL)
            if not self.rest_smith_used and self.run.upgradable_cards():
                legal.append(REST_SMITH)
            legal.append(REST_LEAVE)
            # Card/relic-provided extra options (Hook.TryModifyRestSiteOptions:
            # Byrdonis Egg's Hatch, Pael's Growth's Clone, Pumpkin Candle's
            # Kindle, Meat Cleaver's Cook, Shovel's Dig, Girya's Lift) at
            # indices 3+, drawn from this visit's snapshot (`rest_options`)
            # rather than recomputed, so a used-up option can't reappear
            # mid-visit (Miniature Tent).
            legal.extend(
                REST_LEAVE + 1 + i
                for i in range(len(self.rest_options or []))
            )
            return legal
        if kind == DecisionKind.REWARD_CARD:
            n = len(self.rewards.cards)
            legal = list(range(n + 1))               # last = skip
            if self.rewards.can_reroll:
                legal.append(n + 1)                  # Driftwood: reroll
            if self.rewards.sacrifice_relic is not None:
                legal.append(n + 2)                  # Pael's Wing: sacrifice
            return legal
        if kind == DecisionKind.REWARD_POTION:
            legal = []
            if len(self.run.potions) < self.run.max_potions:
                legal.append(0)                  # take (needs a free slot)
            legal.append(1)                      # skip
            return legal
        if kind == DecisionKind.COMBAT:
            mask = combat_action_masks(self.combat, self.run.max_potions)
            return [int(i) for i in np.flatnonzero(mask)]
        if kind == DecisionKind.SELECT_CARDS:
            legal = list(range(len(self.candidates)))
            if self.skippable:
                legal.append(len(self.candidates))
            return legal
        if kind == DecisionKind.SELECT_OPTION:
            return list(range(self.n_options))
        raise AssertionError(kind)

    def __repr__(self) -> str:
        return f"DecisionRequest({self.kind.value}, {len(self.legal_actions())} legal)"


def random_asker(rng: random.Random) -> Callable[[DecisionRequest], int]:
    """A masked-random policy over DecisionRequests (baseline / smoke tests)."""

    def ask(request: DecisionRequest) -> int:
        return rng.choice(request.legal_actions())

    return ask


@dataclass
class RunResult:
    victory: bool
    hp: int
    max_hp: int
    gold: int
    floor: int
    act_index: int
    deck_size: int
    decisions: int


# The Ancient shrine(s) each act rolls at its starting node (ActModel.
# GetUnlockedAncients). Act 1 (overgrowth/underdocks) is always Neow, fired at
# run start; Act 2 (Hive) and Act 3 (Glory) roll one uniformly at act entry.
# Source: Hive.cs / Glory.cs AllAncients.
ACT_ANCIENTS: dict[str, tuple[str, ...]] = {
    "hive": ("orobas", "pael", "tezcatara"),
    "glory": ("nonupeipe", "tanx", "vakuu"),
}

# UnlockState.SharedAncients — shrines that belong to no single act. At run
# start RunManager.GenerateRooms shuffles this list and hands each act after
# the first a random prefix of what's left (`NextInt(count + 1)` per act, in
# order), so a shared ancient can appear in at most one act of a run — see
# RunDriver._roll_shared_ancients. Each act then rolls its shrine uniformly
# from its own ancients plus its subset (ActModel.GenerateRooms).
SHARED_ANCIENTS: tuple[str, ...] = ("darv",)


class RunDriver:
    """Drives one full run over a RunState, asking `ask` for every decision."""

    def __init__(
        self,
        run: "RunState",
        ask: Callable[[DecisionRequest], int],
        acts: list[str] | None = None,
        ascension: int = 0,
        include_neow: bool = True,
        include_ancients: bool = True,
    ) -> None:
        self.run = run
        self._ask_fn = ask
        self._acts = acts
        self._ascension = ascension
        self._include_neow = include_neow
        self._include_ancients = include_ancients
        self.decisions = 0
        # act name -> the shared ancients allotted to it this run (filled by
        # play() via _roll_shared_ancients, mirroring GenerateRooms).
        self._shared_ancient_subsets: dict[str, tuple[str, ...]] = {}
        # The combat currently being resolved (context for SELECT_CARDS).
        self._combat: "CombatState | None" = None
        # Route every mid-resolution selection through the ask seam.
        run.card_selector = self._card_selector
        run.option_selector = self._option_selector

    # ── The single decision seam ─────────────────────────────────────────

    def _ask(self, request: DecisionRequest) -> int:
        self.decisions += 1
        action = int(self._ask_fn(request))
        if action not in request.legal_actions():
            raise ValueError(
                f"asker returned illegal action {action} for {request!r}"
            )
        return action

    # ── Selector adapters (RunState.card_selector / CombatState.card_selector
    #    via create_combat, RunState.option_selector) ─────────────────────

    def _card_selector(self, purpose: str, candidates: list, count: int):
        skippable = purpose in SKIPPABLE_PURPOSES
        remaining = list(candidates)
        if not skippable and count >= len(remaining):
            return remaining          # forced choice — don't ask
        picked = []
        for i in range(count):
            if not remaining:
                break
            idx = self._ask(DecisionRequest(
                kind=DecisionKind.SELECT_CARDS,
                run=self.run,
                combat=self._combat,
                purpose=purpose,
                candidates=list(remaining),
                count_remaining=count - i,
                skippable=skippable,
            ))
            if skippable and idx == len(remaining):
                break
            picked.append(remaining.pop(idx))
        return picked

    def _option_selector(self, purpose: str, count: int) -> int:
        return self._ask(DecisionRequest(
            kind=DecisionKind.SELECT_OPTION,
            run=self.run,
            purpose=purpose,
            n_options=count,
        ))

    # ── The run loop ─────────────────────────────────────────────────────

    def play(self) -> RunResult:
        run = self.run
        run.start_run(acts=self._acts, ascension=self._ascension)
        self._roll_shared_ancients()
        if self._include_neow:
            from .events import make_event

            self._run_event(make_event("neow", run))
        while not run.at_run_end:
            points = run.travelable_points()
            idx = self._ask(DecisionRequest(
                kind=DecisionKind.MAP, run=run, points=points,
            ))
            resolution = run.enter_point(points[idx])
            self._resolve_room(resolution)
            if run.is_dead:
                break
            if run.at_act_end:
                if run.is_final_act:
                    run.complete_run()
                else:
                    run.advance_act()
                    self._maybe_run_ancient()
        return RunResult(
            victory=run.victory,
            hp=max(0, run.hp),
            max_hp=run.max_hp,
            gold=run.gold,
            floor=run.total_floor,
            act_index=run.act_index,
            deck_size=len(run.deck),
            decisions=self.decisions,
        )

    # ── Room resolution ──────────────────────────────────────────────────

    def _resolve_room(self, resolution) -> None:
        room_type = resolution.room_type
        if room_type in (RoomType.MONSTER, RoomType.ELITE, RoomType.BOSS):
            self._run_combat(resolution.encounter, room_type)
        elif room_type == RoomType.EVENT:
            if resolution.event is not None:
                self._run_event(resolution.event)
        elif room_type == RoomType.SHOP:
            self._run_shop(resolution.shop)
        elif room_type == RoomType.REST_SITE:
            self._run_rest()
        # TREASURE resolved inside enter_point (chest gold + relic); MAP is
        # a no-op in the sim.

    def _run_combat(self, encounter: "Encounter", room_type) -> "CombatState":
        run = self.run
        combat = run.create_combat(encounter, room_type=room_type)
        self._combat = combat
        try:
            while not combat.is_over:
                action = self._ask(DecisionRequest(
                    kind=DecisionKind.COMBAT, run=run, combat=combat,
                ))
                apply_combat_action(combat, action)
        finally:
            self._combat = None
        run.finish_combat(combat, room_type=room_type)
        won = bool(combat.result and combat.result.player_won)
        if (won and room_type in GOLD_REWARD_RANGES
                and encounter.should_give_rewards):
            self._offer_rewards(
                run.generate_combat_rewards(room_type, encounter=encounter))
        return combat

    def _offer_rewards(self, rewards: "CombatRewards") -> None:
        run = self.run
        if rewards.cards:
            while True:
                idx = self._ask(DecisionRequest(
                    kind=DecisionKind.REWARD_CARD, run=run, rewards=rewards,
                ))
                if idx == len(rewards.cards) + 1:
                    # Driftwood's reroll: regenerate the options (one-shot —
                    # reroll() clears can_reroll) and re-ask.
                    rewards.reroll(run)
                    continue
                break
            if idx == len(rewards.cards) + 2:
                # Pael's Wing: sacrifice the card reward
                # (EndSelectionAndCompleteReward — no card is taken).
                rewards.sacrifice_relic.on_sacrifice(run)
            elif idx < len(rewards.cards):
                run.add_card(rewards.cards[idx])
        # Extra single-card rewards queued during combat (Thieving Hopper's
        # returned card; CombatRoom.ExtraRewards -> SpecialCardReward). Each
        # is its own take-or-skip choice (SpecialCardReward.OnSelect adds it
        # to the deck; skipping loses it), surfaced through the existing
        # REWARD_CARD decision as a one-card offer.
        for card in rewards.special_cards:
            offer = CombatRewards(room_type=rewards.room_type, cards=[card])
            idx = self._ask(DecisionRequest(
                kind=DecisionKind.REWARD_CARD, run=run, rewards=offer,
            ))
            if idx == 0:
                run.add_card(card)
        if rewards.potion is not None:
            take = self._ask(DecisionRequest(
                kind=DecisionKind.REWARD_POTION, run=run, rewards=rewards,
            )) == 0
            if take:
                run.add_potion(rewards.potion)
        # Extra potion offers (PotionReward extras: Punch-Off's fight purse).
        # Each is its own take-or-skip decision, like the pity potion above.
        for potion in rewards.special_potions:
            self._offer_potion(potion, rewards.room_type)

    def _offer_potion(self, potion, room_type) -> None:
        """One take-or-skip potion offer (PotionReward / RewardsCmd.
        OfferCustom), surfaced through the existing REWARD_POTION decision."""
        run = self.run
        offer = CombatRewards(room_type=room_type, potion=potion)
        take = self._ask(DecisionRequest(
            kind=DecisionKind.REWARD_POTION, run=run, rewards=offer,
        )) == 0
        if take:
            run.add_potion(potion)

    def _run_event(self, event: "Event") -> None:
        event.begin()
        while not event.finished:
            idx = self._ask(DecisionRequest(
                kind=DecisionKind.EVENT, run=self.run, event=event,
            ))
            chosen = event.choose(idx)
            assert chosen, f"locked/unknown option {idx} slipped past the mask"
        if event.pending_encounter is not None:
            # Event fights are real combat rooms (EventModel.
            # EnterCombatWithoutExitingEvent builds a CombatRoom): every
            # ported event encounter is RoomType.Monster, so victory shows
            # the normal Monster reward screen unless the encounter opts out
            # (EncounterModel.ShouldGiveRewards — Battleworn Dummy). The
            # event's extra rewards ride that screen (extraRewards →
            # CombatRoom.AddExtraReward).
            run = self.run
            run.pending_reward_extras.extend(event.pending_reward_extras)
            combat = self._run_combat(event.pending_encounter, RoomType.MONSTER)
            won = bool(combat.result and combat.result.player_won)
            if won:
                # EventModel.Resume (shouldResumeAfterCombat): the event
                # grants its post-fight rewards; returned potions are
                # take-or-skip offers (RewardsCmd.OfferCustom).
                for potion in event.resume_after_combat(combat):
                    self._offer_potion(potion, RoomType.MONSTER)

    def _roll_shared_ancients(self) -> None:
        """RunManager.GenerateRooms: shuffle UnlockState.SharedAncients, then
        walk the acts AFTER the first handing each one a random prefix of
        what's left (`NextInt(remaining + 1)`), consuming as it goes — so a
        shared ancient shows up in at most one act of a run, and often none."""
        self._shared_ancient_subsets = {}
        if not self._include_ancients:
            return
        from .events import ALL_EVENTS

        remaining = [a for a in SHARED_ANCIENTS if a in ALL_EVENTS]
        self.run.rng.shuffle(remaining)
        for act_name in self.run.act_list[1:]:
            take = self.run.rng.randrange(len(remaining) + 1)
            self._shared_ancient_subsets[act_name] = tuple(remaining[:take])
            remaining = remaining[take:]

    def _maybe_run_ancient(self) -> None:
        """Fire the Ancient shrine at act entry for acts that roll one (Hive,
        Glory). Act 1's Neow is fired at run start instead. The ancient is
        rolled uniformly from the act's own pool PLUS the shared ancients
        allotted to this act (ActModel.GenerateRooms:
        `NextItem(GetUnlockedAncients() ∪ _sharedAncientSubset)`), stands the
        player at the Ancient node, and offers relics."""
        if not self._include_ancients:
            return
        act_name = self.run.act_config.name
        pool = ACT_ANCIENTS.get(act_name, ())
        shared = self._shared_ancient_subsets.get(act_name, ())
        if not pool and not shared:
            return
        from .events import ALL_EVENTS, make_event

        # Mirror ActModel.GetUnlockedAncients: only ancients that exist in the
        # sim are offerable (an unported ancient is treated as not-yet-unlocked,
        # exactly like the epoch gating on Orobas/Neow). Falls away naturally
        # once all six are implemented.
        available = [a for a in (*pool, *shared) if a in ALL_EVENTS]
        if not available:
            return
        self._run_event(make_event(self.run.rng.choice(available), self.run))

    def _run_shop(self, shop: "MerchantInventory") -> None:
        while True:
            idx = self._ask(DecisionRequest(
                kind=DecisionKind.SHOP, run=self.run, shop=shop,
            ))
            entries = shop.all_entries
            if idx >= len(entries):
                return                            # leave
            entries[idx].purchase()

    def _run_rest(self) -> None:
        """RestSiteOption.Generate + RestSiteSynchronizer.ChooseOption: a
        visit takes one snapshot of the extra options up front (so a used-up
        one — e.g. Meat Cleaver's Cook — can't be picked twice even if its
        precondition would still allow it), then loops asking for an action
        until Leave or Hook.ShouldDisableRemainingRestSiteOptions says the
        visit is over (default: after the first action; Miniature Tent lets
        it continue)."""
        run = self.run
        options = run.rest_site_options()
        heal_used = False
        smith_used = False
        while True:
            idx = self._ask(DecisionRequest(
                kind=DecisionKind.REST, run=run,
                rest_options=options,
                rest_heal_used=heal_used,
                rest_smith_used=smith_used,
            ))
            if idx == REST_LEAVE:
                return
            if idx == REST_HEAL:
                run.rest_heal()
                # HealRestSiteOption.ExecuteRestSiteHeal: relics may add a
                # reward (Dream Catcher's 3-card choice) after the heal.
                self._offer_rewards(run.rest_heal_rewards())
                heal_used = True
            elif idx == REST_SMITH:
                run.rest_upgrade()
                smith_used = True
            else:
                # A card/relic-provided option (Hatch / Clone / Kindle /
                # Cook / Dig / Lift), picked from this visit's snapshot.
                options.pop(idx - REST_LEAVE - 1).on_select(run)
            if run.should_disable_remaining_rest_site_options():
                return


def play_random_run(
    seed: int = 0,
    acts: list[str] | None = None,
    **driver_kwargs,
) -> RunResult:
    """One full run with a masked-random policy (smoke tests / baselines)."""
    from .run import RunState

    rng = random.Random(seed)
    run = RunState(rng=rng)
    driver = RunDriver(run, random_asker(rng), acts=acts, **driver_kwargs)
    return driver.play()
