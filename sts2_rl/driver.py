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
from .rewards import (
    GOLD_REWARD_RANGES,
    CardRewardGroup,
    CombatRewards,
    apply_reward_modifiers,
)
from .rooms import SHARED_ANCIENTS, RoomType

if TYPE_CHECKING:
    from .actmap import MapPoint
    from .cards import Card
    from .combat import CombatState
    from .events.base import Event
    from .monsters import Encounter
    from .potions import Potion
    from .relics import Relic
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
    # RelicReward (RelicReward.cs:109-123): take the relic, or skip it. Every
    # relic offer in the source is declinable except Neow's Bones, the single
    # `WithSkippingDisallowed` caller (RewardsSet.cs:115 / NeowsBones.cs:43).
    REWARD_RELIC = "reward_relic"  # take the relic, or skip


# Rest-site option order (RestSiteOption.Generate: Heal + Smith; leave last).
REST_HEAL, REST_SMITH, REST_LEAVE = 0, 1, 2
N_REST_OPTIONS = 3

# select_cards purposes where declining is a real choice (a card offer, not a
# mandatory selection): the action index == len(candidates) means "skip".
# These are MinSelect-0 `CardSelectorPrefs` screens (RequireManualConfirmation),
# so 0 picks is a legal outcome that must never be force-filled:
#   - "choose_a_card_optional": FromChooseACardScreen(canSkip: true)
#     (CardSelectCmd.cs:216-261, the three-card generator potions). Same
#     underlying screen as "transform"/"transform_optional", but skippability
#     is per-site (Toolbox.cs:28, ChoicesParadox.cs:46 forbid the decline),
#     hence the separate purpose string.
#   - "enchant_optional": Kifuda.cs:26-29 and GnarledHammer.cs:30-34, both
#     `CardSelectorPrefs(prompt, 0, N) { Cancelable = false,
#     RequireManualConfirmation = true }`. Distinct from plain "enchant"
#     (exact-count MinSelect==MaxSelect sites — beautiful_bracelet/
#     electric_shrymp/paels_growth/royal_stamp/tri_boomerang and event
#     "enchant" sites), which must keep force-filling. Sim models the PREFS
#     range (0..3) rather than the shipped UI's true reachable floor of 1
#     (NDeckEnchantSelectScreen won't confirm 0 cards) — deliberate, since the
#     sim operates at the ICardSelector/driver level, same as
#     AutoSlayCardSelector. See relics/kifuda.py's docstring for detail.
#   - "gambling_chip": GamblingChip.cs:20, CardSelectorPrefs(prompt, 0,
#     999999999) — whole-hand offer, "discard nothing" is legal.
#   - "exhaust_any": Ashwater.cs:30. "discard_any": GamblersBrew.cs:26.
#     "from_discard": NeowsFury.cs:39. Same MinSelect-0 shape.
SKIPPABLE_PURPOSES = frozenset({
    "card_reward", "choose_a_card_optional", "discard_any",
    "enchant_optional", "exhaust_any", "from_discard",
    "gambling_chip", "obtain", "transform_optional",
})

# Answer namespace for "drink the belt potion in slot N" — see
# DecisionRequest.potion_actions. It is offset far past every decision's own
# option indices (a shop offers 15, a map row 7, a select screen
# len(candidates)) so the two can never collide and no kind needs to know the
# belt exists; `RunDriver._ask` intercepts the whole range.
POTION_ACTION_BASE = 1000

# `RunDriver._ask`'s "the screen you were answering resolved itself, there is
# nothing left to answer" result. Only reachable via the belt overlay: a drink
# that finishes the screen underneath (Foul Potion in the Fake Merchant event).
# Callers that can raise such a screen must handle it; every other decision
# returns a real option index.
NO_ANSWER = -1


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
    relic: "Relic | None" = None                 # REWARD_RELIC
    potion: "Potion | None" = None               # REWARD_POTION (bare offer)
    points: "list[MapPoint]" = field(default_factory=list)   # MAP
    purpose: str = ""                            # SELECT_CARDS / SELECT_OPTION
    candidates: "list[Card]" = field(default_factory=list)   # SELECT_CARDS
    count_remaining: int = 0                     # SELECT_CARDS (multi-pick)
    skippable: bool = False                      # SELECT_CARDS
    n_options: int = 0                           # SELECT_OPTION
    rest_options: "list | None" = None           # REST: this visit's option snapshot
    rest_heal_used: bool = False                 # REST
    rest_smith_used: bool = False                # REST
    # Whether a combat is live behind this decision. Stamped by
    # `RunDriver._ask` on every request (`self.combat is not None or the
    # driver's current combat`), because a request raised mid-combat does not
    # always carry the combat itself — `_reward_selector`'s offers don't. Only
    # `potion_actions` reads it.
    in_combat: bool = False

    def legal_actions(self) -> list[int]:
        return self.own_actions() + self.potion_actions()

    def potion_actions(self) -> list[int]:
        """`POTION_ACTION_BASE + slot` for every belt potion drinkable *from
        this screen* — i.e. every `PotionUsage.AnyTime` potion, whenever no
        combat is live.

        `NPotionPopup.RefreshButtons` (NPotionPopup.cs:322-325) enables the Use
        button for an AnyTime potion with no screen predicate whatsoever; the
        `IsInProgress && CurrentSide == Side && !InACardSelectScreen && ...`
        predicate is the `else if` arm that only CombatOnly potions reach. So
        the belt is live on the map, in a shop, at a rest site, mid-event and
        inside a card-select screen alike.

        In combat it is masked off instead: there the belt is the combat
        block's own potion actions, which target an enemy and run the whole of
        `OnUseWrapper`, where `RunState.use_potion` deliberately runs only its
        two combat-less steps.
        """
        if self.in_combat or self.combat is not None:
            return []
        # `Player.CanRemovePotions` gates the Use button itself
        # (NPotionPopup.cs:139-142) — three events lock the belt for their
        # whole duration. See `RunState.can_remove_potions`.
        if not self.run.can_remove_potions:
            return []
        from .potions import USAGE_ANY_TIME

        return [
            POTION_ACTION_BASE + slot
            for slot, potion in enumerate(self.run.potions)
            if potion is not None
            and potion.usage == USAGE_ANY_TIME
            # `PotionModel.PassesCustomUsabilityCheck` DISABLES the Use button
            # (NPotionPopup.cs:144-147) — a refused potion must not reach the
            # mask. Foul Potion is the only override (shop stall / Fake
            # Merchant only).
            and potion.passes_custom_usability_check(run=self.run)
        ]

    def own_actions(self) -> list[int]:
        """The decision's own options — what the answer means to the caller
        that raised it. `legal_actions` is this plus the belt."""
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
            if self.run.has_open_potion_slot:
                legal.append(0)                  # take (needs a free slot)
            legal.append(1)                      # skip
            return legal
        if kind == DecisionKind.REWARD_RELIC:
            return [0, 1]                        # take / skip
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

# UnlockState.SharedAncients (`SHARED_ANCIENTS`, imported from rooms) is shuffled
# and dealt to the acts after the first at run start; each act then rolls its
# shrine uniformly from its own ancients plus its subset (ActModel.GenerateRooms).
# The parity path pre-rolls all of this on UpFront in RunState._generate_all_act_rooms;
# the legacy path below rolls it on self.rng in _roll_shared_ancients.


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
        on_combat_start: "Callable[[RunState, Encounter], None] | None" = None,
    ) -> None:
        self.run = run
        self._ask_fn = ask
        self._acts = acts
        self._ascension = ascension
        self._include_neow = include_neow
        self._include_ancients = include_ancients
        # Fired in `_run_combat` right after `create_combat`, before the
        # first decision of that combat. `None` (default) is a no-op.
        self.on_combat_start = on_combat_start
        self.decisions = 0
        # act name -> the shared ancients allotted to it this run (filled by
        # play() via _roll_shared_ancients, mirroring GenerateRooms).
        self._shared_ancient_subsets: dict[str, tuple[str, ...]] = {}
        # The combat currently being resolved (context for SELECT_CARDS).
        self._combat: "CombatState | None" = None
        # Route every mid-resolution selection through the ask seam.
        run.card_selector = self._card_selector
        run.option_selector = self._option_selector
        run.reward_selector = self._reward_selector
        # RewardsCmd.OfferCustom for a whole set built outside a room (Glass
        # Eye's five CardRewards): every screen goes through the same
        # REWARD_CARD decision as a post-combat one.
        run.rewards_offerer = self._offer_rewards

    # ── The single decision seam ─────────────────────────────────────────

    def _ask(self, request: DecisionRequest) -> int:
        # Stamp the combat context the request may not carry itself, so
        # `potion_actions` can tell a map screen from a card-select screen
        # inside a fight (see DecisionRequest.in_combat).
        request.in_combat = request.combat is not None or self._combat is not None
        while True:
            # An asked decision must always have at least one legal action --
            # the RL env turns `legal_actions` straight into the policy's
            # action mask, and an all-False mask is not a choice the policy can
            # make (a masked categorical over -inf logits is NaN, and a
            # `flatnonzero` sampler picks from an empty array). Loudly here
            # beats silently there.
            if not request.legal_actions():
                raise RuntimeError(
                    f"decision with NO legal actions: {request!r} — the mask "
                    f"would be all-False")
            self.decisions += 1
            action = int(self._ask_fn(request))
            if action not in request.legal_actions():
                raise ValueError(
                    f"asker returned illegal action {action} for {request!r}"
                )
            if action < POTION_ACTION_BASE:
                return action
            # `NPotionPopup` is an overlay: drinking resolves the potion and
            # leaves you on the screen underneath, which still owes an answer.
            # Terminates — every drink empties a belt slot.
            drunk = self.run.use_potion(action - POTION_ACTION_BASE)
            assert drunk, "potion_actions offered a slot use_potion refused"
            # ...unless the drink RESOLVED the screen underneath. Foul Potion
            # is the one that can: drunk in the Fake Merchant event it runs
            # `FakeMerchant.FoulPotionThrown`, which blows up the stall and
            # finishes the event (FoulPotion.cs:89-108), so there is no page
            # left to answer. Re-asking there handed the policy an empty option
            # list -- an all-False mask, caught by the guard at the top of this
            # loop. Report it to the caller instead; `_run_event` re-checks
            # `event.finished` and stops. (SHOP cannot reach this: `leave` is
            # always in its own actions.)
            if not request.own_actions():
                return NO_ANSWER

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

    def _reward_selector(self, kind: str, item) -> bool:
        """RunState.offer_relic / offer_potion's take-or-skip seam — a
        RelicReward or PotionReward handed to `RewardsCmd.OfferCustom` outside
        a post-combat screen (Small Capsule's pull, Calling Bell's three, Toy
        Box's four wax relics, Lost Coffer's and Cauldron's potions). Returns
        whether the player takes it; the run state does the granting."""
        if kind == "relic":
            return self._ask(DecisionRequest(
                kind=DecisionKind.REWARD_RELIC, run=self.run, relic=item,
            )) == 0
        # The reward block of the run env reads `rewards.potion`, so wrap the
        # bare offer the same way _offer_potion does. There is no room behind
        # a pickup-effect screen; MONSTER is the neutral label rest-site
        # reward screens already use (RunState.rest_heal_rewards).
        offer = CombatRewards(room_type=RoomType.MONSTER, potions=[item])
        return self._ask(DecisionRequest(
            kind=DecisionKind.REWARD_POTION, run=self.run,
            rewards=offer, potion=item,
        )) == 0

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
        elif room_type == RoomType.TREASURE:
            self._offer_treasure_extra_rewards()
        # The chest's own gold + relic is resolved inside enter_point; MAP is
        # a no-op in the sim.

    def _offer_treasure_extra_rewards(self) -> None:
        """`TreasureRoom.DoExtraRewardsIfNeeded` (TreasureRoom.cs:75-97): after
        the chest's own direct gold+relic grant (`enter_point`'s TREASURE
        branch — matches `OneOffSynchronizer.DoTreasureRoomRewards`, which
        never touches a RewardsSet), the room ALSO dispatches
        `Hook.ModifyRewards` over an otherwise-empty, Room=Treasure reward
        set (`RunState.enter_point` builds and dispatches it, stashing the
        result only if a hook actually added something). Normally a no-op —
        no ported relic is Room==Treasure-sensitive today — but this is
        where a future one's screen would surface, offered the same way any
        other reward screen is."""
        extra = self.run.pending_treasure_extra_rewards
        if extra is not None:
            self.run.pending_treasure_extra_rewards = None
            self._offer_rewards(extra)

    def _run_combat(self, encounter: "Encounter", room_type) -> "CombatState":
        run = self.run
        combat = run.create_combat(encounter, room_type=room_type)
        if self.on_combat_start is not None:
            self.on_combat_start(run, encounter)
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
            self._offer_rewards(run.generate_combat_rewards(
                room_type, encounter=encounter,
                # `CombatRoom.OnCombatEnded` (CombatRoom.cs:233-236) reads the
                # encounter's gold proportion off the finished combat, and
                # `RewardsSet` scales the MONSTER gold range by it. The sim
                # always passed the 1.0 default, so an encounter that lets an
                # enemy escape still paid full gold.
                gold_proportion=encounter.calculate_gold_proportion(combat),
            ))
        return combat

    def _offer_rewards(self, rewards: "CombatRewards") -> None:
        run = self.run
        # Offer-time backstop: mirrors `RewardsSet.Offer` calling
        # `GenerateWithoutOffering` again at RewardsSet.cs:159 no matter how
        # the set was built. Real construction sites already call
        # `apply_reward_modifiers` themselves (`CombatRewards.generated`
        # guards the repeat), so a future site that forgets still gets
        # dispatched here instead of silently skipping reward-modifying relics.
        apply_reward_modifiers(run, rewards)
        # A reward set holds a LIST of Rewards, and each CardReward on it is
        # its own pick-one-of-N screen taken separately (RewardsSet.cs:49) —
        # Prayer Wheel puts a second one on every Monster room. Offer them in
        # list order, each through the same one-screen REWARD_CARD decision.
        for group in list(rewards.card_rewards):
            if group.cards:
                self._offer_card_group(rewards, group)
        # Extra single-card rewards queued during combat (Thieving Hopper's
        # returned card; CombatRoom.ExtraRewards -> SpecialCardReward). Each
        # is its own take-or-skip choice (SpecialCardReward.OnSelect adds it
        # to the deck; skipping loses it), surfaced through the existing
        # REWARD_CARD decision as a one-card offer.
        for card in rewards.special_cards:
            offer = CombatRewards(
                room_type=rewards.room_type,
                card_rewards=[CardRewardGroup(cards=[card],
                                              room_type=rewards.room_type)],
            )
            idx = self._ask(DecisionRequest(
                kind=DecisionKind.REWARD_CARD, run=run, rewards=offer,
            ))
            if idx == 0:
                run.add_card(card)
        # Every PotionReward on the set is its own take-or-skip row. Normally
        # there is one (the pity drop); a RewardsCmd.OfferCustom set can carry
        # several — Crystal Sphere reveals up to three. `rewards.potions[0]` is
        # what `rewards.potion` shows, so popping from the front keeps the
        # decision and the obs pointed at the potion actually being offered.
        pending = list(rewards.potions)
        for potion in pending:
            rewards.potions = [potion]
            take = self._ask(DecisionRequest(
                kind=DecisionKind.REWARD_POTION, run=run, rewards=rewards,
            )) == 0
            if take:
                run.add_potion(potion)
        rewards.potions = pending
        # Extra potion offers (PotionReward extras: Punch-Off's fight purse).
        # Each is its own take-or-skip decision, like the pity potion above.
        for potion in rewards.special_potions:
            self._offer_potion(potion, rewards.room_type)

    def _offer_card_group(self, rewards: "CombatRewards", group) -> None:
        """One CardReward: pick / skip / reroll (Driftwood) / sacrifice
        (Pael's Wing). The screen the policy sees describes THIS group, so a
        second group on the same set is a second, independent decision."""
        run = self.run
        offer = rewards if rewards.card_rewards[:1] == [group] else CombatRewards(
            room_type=group.room_type, room=rewards.room, card_rewards=[group],
        )
        while True:
            idx = self._ask(DecisionRequest(
                kind=DecisionKind.REWARD_CARD, run=run, rewards=offer,
            ))
            if idx == len(group.cards) + 1:
                # Driftwood's reroll: regenerate the options (one-shot —
                # reroll() clears can_reroll) and re-ask.
                group.reroll(run)
                continue
            break
        if idx == len(group.cards) + 2:
            # Pael's Wing: sacrifice the card reward
            # (EndSelectionAndCompleteReward — no card is taken).
            group.sacrifice_relic.on_sacrifice(run)
        elif idx < len(group.cards):
            run.add_card(group.cards[idx])

    def _offer_potion(self, potion, room_type) -> None:
        """One take-or-skip potion offer (PotionReward / RewardsCmd.
        OfferCustom), surfaced through the existing REWARD_POTION decision."""
        run = self.run
        offer = CombatRewards(room_type=room_type, potions=[potion])
        take = self._ask(DecisionRequest(
            kind=DecisionKind.REWARD_POTION, run=run, rewards=offer,
            potion=potion,
        )) == 0
        if take:
            run.add_potion(potion)

    def _run_event(self, event: "Event") -> None:
        event.begin()
        while not event.finished:
            idx = self._ask(DecisionRequest(
                kind=DecisionKind.EVENT, run=self.run, event=event,
            ))
            if idx == NO_ANSWER:
                # A belt drink finished the event out from under this page
                # (Foul Potion at the Fake Merchant). There is no option to
                # choose; the loop condition sees `finished` and exits.
                continue
            chosen = event.choose(idx)
            assert chosen, f"locked/unknown option {idx} slipped past the mask"
            if event.pending_rewards is not None:
                # A reward screen the option itself awaited, mid-event: the
                # `await RewardsCmd.OfferCustom(player, rewards)` that closes
                # HealRestSiteOption.ExecuteRestSiteHeal (HealRestSiteOption.
                # cs:112) on the path PlayerCmd.MimicRestSiteHeal takes for
                # Dense Vegetation's Rest. Offered here, between the option
                # returning and the next page being asked for, because that is
                # where the await sits (DenseVegetation.cs:88-99 puts its
                # SetEventState after it).
                pending, event.pending_rewards = event.pending_rewards, None
                self._offer_rewards(pending)
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
        if self.run.rng_set is not None:
            # Parity: start_run already shuffled + dealt the subsets on UpFront
            # (RunState._generate_all_act_rooms) and folded each act's ancient
            # into its pre-rolled RoomSet — nothing to draw on the legacy RNG.
            self._shared_ancient_subsets = dict(self.run._shared_ancient_subsets)
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
        from .events import ALL_EVENTS, make_event

        if self.run.rng_set is not None:
            # Parity: the shrine was pre-rolled into this act's RoomSet on the
            # UpFront stream (ActModel.GenerateRooms); fire exactly that one.
            room_set = self.run.room_set
            ancient = room_set.ancient_key if room_set is not None else None
            if ancient is not None:
                self._run_event(make_event(ancient, self.run))
            return
        act_name = self.run.act_config.name
        pool = ACT_ANCIENTS.get(act_name, ())
        shared = self._shared_ancient_subsets.get(act_name, ())
        if not pool and not shared:
            return

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
    string_seed: str | None = None,
    character: str = "ironclad",
    **driver_kwargs,
) -> RunResult:
    """One full run with a masked-random policy (smoke tests / baselines).

    `string_seed` additionally seats the game's parity RNG streams on the
    RunState (SP2); it does not affect the legacy random.Random decisions.
    """
    from .run import RunState

    rng = random.Random(seed)
    run = RunState(rng=rng, string_seed=string_seed, character=character)
    driver = RunDriver(run, random_asker(rng), acts=acts, **driver_kwargs)
    return driver.play()
