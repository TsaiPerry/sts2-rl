"""Event base classes and registry, mirroring STS2's EventModel/EventOption
(src/Core/Models/EventModel.cs, src/Core/Events/EventOption.cs).

An Event is constructed over a RunState and driven headlessly:

    run = RunState(rng=random.Random(0))
    event = make_event("wellspring", run)
    event.begin()                 # CalculateVars + initial options
    event.choose("BOTTLE")        # option keys mirror the source loc keys
    assert event.finished

Pages mirror the game's loc structure: every event starts on the "INITIAL"
page; choosing an option either finishes the event on a result page
(SetEventFinished) or moves to a new page with new options (SetEventState).
`event.page` always names the page whose description the player would be
reading. Locked options (a null onChosen in the game, e.g. Luminous Choir's
unaffordable tribute) are present but cannot be chosen.

Events that start a fight (Dense Vegetation) set `pending_encounter`; the
caller runs it via `run.create_combat(event.pending_encounter)` — mirroring
EnterCombatWithoutExitingEvent, which hands the encounter to the room system.

Deck choices go through `run.select_cards(purpose, candidates, count)` — the
headless stand-in for the game's card selection screens (CardSelectCmd),
random by default and overridable via RunState.card_selector.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ..combat import CombatState
    from ..monsters import Encounter
    from ..potions import Potion
    from ..rewards import CombatRewards, RewardExtra
    from ..run import RunState


_EVENT_CLASSES: dict[str, type[Event]] = {}


def register_event(cls: type[Event]) -> type[Event]:
    _EVENT_CLASSES[cls.id] = cls
    return cls


def make_event(event_id: str, run: RunState) -> Event:
    return _EVENT_CLASSES[event_id](run)


class EventOption:
    """One choice on an event page (mirrors EventOption).

    key mirrors the source's loc option name ("EAT", "TRUDGE_ON", ...).
    on_chosen is None for locked options (EventOption with a null onChosen).
    """

    def __init__(self, key: str, on_chosen: Callable[[], None] | None) -> None:
        self.key = key
        self.on_chosen = on_chosen

    @property
    def locked(self) -> bool:
        return self.on_chosen is None

    def __repr__(self) -> str:
        return f"{self.key}{' (locked)' if self.locked else ''}"


class Event:
    """Base class for all events (mirrors EventModel)."""

    id: str
    name: str

    # EventModel.LayoutType == EventLayoutType.Combat: the encounter stands
    # behind the event text, so EventRoom.EnterInternal builds the whole combat
    # state when the ROOM IS ENTERED (EventRoom.cs:69-72) and the fight option
    # reuses it. The source's three are PunchOff, TheLanternKey and
    # TheArchitect (unported).
    is_combat_layout: bool = False
    # EventModel.CanonicalEncounter — what a Combat-layout event pre-generates
    # at room entry and its fight option then hands to the driver.
    canonical_encounter: "Encounter | None" = None
    # `Player.CanRemovePotions = false` for the whole event
    # (`BeforeEventStarted` -> `OnEventFinished`). The source's only three are
    # TheFutureOfPotions.cs:92, RanwidTheElder.cs:42 and StoneOfAllTime.cs:66,
    # and `NPotionPopup` reads the flag to DISABLE the Use and Discard buttons
    # (NPotionPopup.cs:139-142) -- so the belt is not usable while one of them
    # is open. All three ports used to record this as "UI-only and not
    # modeled", which was true only until `DecisionRequest.potion_actions`
    # made the out-of-combat belt reachable at all. It is load-bearing now:
    # these events hand out options that NAME held potions, and draining a
    # named slot mid-event left an option referring to a potion no longer held
    # (`RunState.discard_potion` -> `ValueError: ... is not in list`).
    locks_potion_belt: bool = False

    def __init__(self, run: RunState) -> None:
        self.run = run
        # The game gives each event its own RNG seeded from the run seed +
        # event id (EventModel ctor). The legacy path keeps the sim's single-
        # RNG-stream convention (`self.rng`); the SP3 parity path also exposes
        # the per-event game Rng as `self.event_rng` for events whose random
        # draws must reproduce the recording (e.g. Tablet of Truth's upgrade
        # pick). None in legacy runs.
        self.rng = run.rng
        self.event_rng = None
        if run.rng_set is not None:
            from ..rng import make_event_rng
            self.event_rng = make_event_rng(run.rng_set.seed, type(self).id.upper())
        self.page = "INITIAL"
        self.finished = False
        self._options: list[EventOption] = []
        # Set when an option starts a combat (EnterCombatWithoutExitingEvent);
        # the caller enters it with run.create_combat(pending_encounter).
        self.pending_encounter: Encounter | None = None
        # Extra rewards the event attaches to that fight's reward screen
        # (EnterCombatWithoutExitingEvent's extraRewards; Punch-Off's
        # relic + potion, The Lantern Key's card). The driver transfers them
        # to run.pending_reward_extras when it runs the fight.
        self.pending_reward_extras: list["RewardExtra"] = []
        # A reward screen the option itself awaits, in the middle of the event
        # rather than after a fight: `await RewardsCmd.OfferCustom(player,
        # rewards)` at the end of HealRestSiteOption.ExecuteRestSiteHeal
        # (HealRestSiteOption.cs:112), which PlayerCmd.MimicRestSiteHeal
        # (PlayerCmd.cs:264-271) routes Dense Vegetation's Rest through. The
        # driver offers and clears it as soon as the option returns, which is
        # where the await sits -- before DenseVegetation.Rest's SetEventState
        # puts up the FIGHT page (DenseVegetation.cs:88-99).
        self.pending_rewards: "CombatRewards | None" = None
        # Creature.SetUniqueMonsterHpValue's results for a Combat-layout
        # event's encounter, rolled at room entry by
        # generate_internal_combat_state. Empty for every other event (and in
        # legacy runs, which have no Niche stream).
        self.pregenerated_hp: list[int] = []

    # ── Subclass surface ─────────────────────────────────────────────────

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        """Whether this event may be entered (mirrors EventModel.IsAllowed).
        Gates use the same canonical values as the source."""
        return True

    def calculate_vars(self) -> None:
        """Roll per-visit dynamic values (mirrors EventModel.CalculateVars)."""

    def initial_options(self) -> list[EventOption]:
        """The INITIAL page's options (mirrors GenerateInitialOptions)."""
        raise NotImplementedError

    def offer_pool_potion(self) -> "Potion":
        """`Owner.PlayerRng.Rewards.NextItem(Character.PotionPool ∪
        SharedPotionPool)` — the verbatim potion-offer idiom of
        BattlewornDummy.cs:84-90, EndlessConveyor.cs:152-158,
        TheLegendsWereTrue.cs:52-59 and Wellspring.cs:32-38.

        ONE draw on the per-player Rewards stream over the whole unlocked pool
        in pool order (NOT the event's own Rng, and NOT PotionFactory's
        rarity-then-item pair). The legacy RL path keeps the old shared-rng
        pick over the sim's implemented reward pool."""
        if self.run.rng_set is not None:
            from ..potion_pools import make_pool_potion
            pid = self.run.rewards_rng.next_item(
                [p for p, _ in self.run.potion_pool])
            return make_pool_potion(pid)
        return self.run.random_potion()

    def resume_after_combat(self, combat: "CombatState") -> "list[Potion]":
        """Called by the driver after this event's pending_encounter fight is
        won (mirrors EventModel.Resume for events entered with
        shouldResumeAfterCombat). Grants any immediate rewards itself and
        returns potions to surface as take-or-skip offers (RewardsCmd.
        OfferCustom). Default: nothing (most combat events don't resume)."""
        return []

    # ── Lifecycle ────────────────────────────────────────────────────────

    def begin(self) -> Event:
        """Mirrors EventRoom.EnterInternal: BeginEvent (roll vars, then present
        the initial page — EventModel.cs:239-251), followed by
        GenerateInternalCombatState for a Combat-layout event
        (EventRoom.cs:68-72)."""
        self.calculate_vars()
        self._set_state("INITIAL", self.initial_options())
        if self.is_combat_layout:
            self.generate_internal_combat_state()
        return self

    # ── Combat-layout events (EventLayoutType.Combat) ────────────────────

    def generate_internal_combat_state(self) -> None:
        """Port of EventModel.GenerateInternalCombatState (EventModel.cs:383-403).

        Called from the room-entry path for every Combat-layout event, before
        any option is chosen, so the monster HP rolls are spent even by a
        player who declines the fight."""
        from ._combat_layout import pregenerate_monster_hp
        self.pregenerated_hp = pregenerate_monster_hp(
            self.run, self.canonical_encounter)

    def internal_combat_encounter(self) -> "Encounter":
        """The encounter a Combat-layout event's fight option hands to the
        driver: the state generated at room entry when there is one (mirroring
        EnterCombatWithoutExitingEvent reusing _combatStateForCombatLayout),
        otherwise the canonical encounter itself."""
        if not self.pregenerated_hp:
            return self.canonical_encounter
        from ._combat_layout import PregeneratedEncounter
        return PregeneratedEncounter.of(
            self.canonical_encounter, self.pregenerated_hp)

    # ── Reward offers (RewardsCmd.OfferCustom) ───────────────────────────

    def _accept_offer(self, purpose: str, payload) -> bool:
        """Present one take-or-skip reward screen and report whether the player
        took it.

        `RewardsCmd.OfferCustom` (RewardsCmd.cs:47-50) is a CANCELABLE screen —
        the source sets `Cancelable = false` explicitly when a pick is forced
        (BrainLeech.cs:67-70) — so an event's payout is an offer, not a grant:
        a potion can be declined to keep the belt slot and a card reward can be
        skipped to keep the deck lean.

        Resolution order: (1) `run.reward_offer_selector` if installed —
        finest-grained, sees `purpose`, used by
        test_event_offer_screens.py to unit-test one event in isolation;
        (2) for `purpose == "potion"` only, fall back to `run.reward_selector`
        — the seam a real `RunDriver` already wires for offer_relic/
        offer_potion (driver.py -> _reward_selector -> REWARD_POTION);
        (3) `purpose == "card_reward"` is dead code (no caller since
        `offer_card_reward` was removed in favor of `pending_rewards` ->
        REWARD_CARD -> `_offer_card_group`, which models C#'s single
        CardReward/CardRewardAlternative screen instead of asking twice) —
        left un-wired intentionally, kept only for a future OfferCustom-style
        caller; (4) with nothing installed, every offer is taken."""
        selector = getattr(self.run, "reward_offer_selector", None)
        if selector is not None:
            return bool(selector(purpose, payload))
        if purpose == "potion":
            reward_selector = getattr(self.run, "reward_selector", None)
            if reward_selector is not None:
                return bool(reward_selector("potion", payload))
        return True

    def offer_potion(self, potion: "Potion") -> bool:
        """`RewardsCmd.OfferCustom` with a single `PotionReward`
        (DrowningBeacon.cs:39-46). Returns whether it reached the belt."""
        if not self._accept_offer("potion", potion):
            return False
        return self.run.add_potion(potion)

    # `offer_card_reward` (formerly RewardsCmd.OfferCustom with a single
    # CardReward, TheFutureOfPotions.cs:127-130) was removed: its take-or-skip
    # protocol had no reroll/sacrifice slot, unlike C#'s single CardReward/
    # CardRewardAlternative screen. Card-reward events now build their own
    # CardRewardGroup and set `self.pending_rewards` directly (same channel as
    # brain_leech.py's Rip and trial.py's Nondescript Guilty).

    @property
    def options(self) -> list[EventOption]:
        return list(self._options)

    def option_keys(self) -> list[str]:
        return [opt.key for opt in self._options]

    def choose(self, option: int | str) -> bool:
        """Choose an option by index or key. Returns False for unknown or
        locked options (the game renders those unclickable)."""
        if self.finished:
            return False
        if isinstance(option, str):
            matches = [o for o in self._options if o.key == option]
            if not matches:
                return False
            opt = matches[0]
        else:
            if option < 0 or option >= len(self._options):
                return False
            opt = self._options[option]
        if opt.locked:
            return False
        opt.on_chosen()
        return True

    # ── State transitions (SetEventState / SetEventFinished) ────────────

    def _set_state(self, page: str, options: list[EventOption]) -> None:
        self.page = page
        self._options = list(options)
        if not self._options:
            self.finished = True

    def _finish(self, page: str) -> None:
        """Mirrors SetEventFinished: land on a result page with no options."""
        self._set_state(page, [])

    def __repr__(self) -> str:
        state = "finished" if self.finished else f"page={self.page}"
        return f"{self.name} ({state})"
