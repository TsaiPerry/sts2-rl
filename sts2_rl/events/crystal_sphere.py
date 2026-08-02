"""Crystal Sphere — pay in gold or in curses, then dig items out of an 11x11
fog grid.

Source: Models/Events/CrystalSphere.cs, with the payout in
Events/Custom/CrystalSphereEvent/ (ported in `_crystal_sphere.py`).

  IsAllowed:      every player holds >= 100 gold, and CurrentActIndex > 0
  CalculateVars:  UncoverFutureCost = 50 + Rng.NextInt(1, 50)
  UNCOVER_FUTURE: lose that gold, then 3 divinations
  PAYMENT_PLAN:   add a Debt curse, then 6 divinations

WHAT THE SIM DOES NOT MODEL: the CHOICE of cell. In the game a divination is a
mouse click on one of 121 cells with one of two tools, informed by whatever the
previous clicks uncovered — a genuine spatial decision. The sim resolves the
clicks internally instead of surfacing them to the policy, using the automated
rule the game itself ships for this screen (`CrystalSphereScreenHandler`, the
AutoSlay handler: a uniformly random still-hidden cell, Big tool —
CrystalSphereScreenHandler.cs:82-104). The two EVENT options are real
decisions and are surfaced normally.

The engine is faithful either way: `run.crystal_sphere_clicks` overrides the
policy, which is how the conformance runner replays a recording's
`CrystalSphereClick {x} {y} {tool}` commands exactly.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import make_card
from ._crystal_sphere import TOOL_BIG, CrystalSphereMinigame, Item, ItemKind
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_BASE_COST = 50               # _uncoverFutureCost
_UNCOVER_DIVINATIONS = 3      # _uncoverFutureProphesizeCount
_PAYMENT_DIVINATIONS = 6      # _paymentPlanCount
_MIN_GOLD = 100               # IsAllowed's `p.Gold >= 100`
_SMALL_GOLD, _BIG_GOLD = 10, 30   # CrystalSphereGold._smallAmount/_largeAmount


def _pick_from(rng, seq):
    """`Rng.NextItem` on the parity path, `random.Random.choice` on the legacy
    one — the same two-armed idiom the other events use for their own rolls."""
    return rng.next_item(seq) if hasattr(rng, "next_item") else rng.choice(seq)


@register_event
class CrystalSphere(Event):
    id = "crystal_sphere"
    name = "Crystal Sphere"

    def __init__(self, run: "RunState") -> None:
        super().__init__(run)
        self.cost = _BASE_COST
        self.minigame: CrystalSphereMinigame | None = None
        self.divinations_spent = 0

    @classmethod
    def is_allowed(cls, run: "RunState") -> bool:
        # `Players.All(p => p.Gold >= 100) && CurrentActIndex > 0` — one player
        # here, so All collapses to the single check.
        return run.gold >= _MIN_GOLD and run.act_index > 0

    def calculate_vars(self) -> None:
        # `DynamicVars["UncoverFutureCost"].BaseValue += Rng.NextInt(1, 50)`
        # (:44-47). NextInt's upper bound is exclusive.
        er = self.event_rng
        self.cost = _BASE_COST + (
            er.next_int_range(1, 50) if er is not None else self.rng.randint(1, 49))

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("UNCOVER_FUTURE", self._uncover_future),
            EventOption("PAYMENT_PLAN", self._payment_plan),
        ]

    # ── The two options (:67-81) ─────────────────────────────────────────

    def _uncover_future(self) -> None:
        self.run.lose_gold(self.cost)
        self._play(_UNCOVER_DIVINATIONS)
        self._finish("FINISH")

    def _payment_plan(self) -> None:
        # `CardPileCmd.AddCurseToDeck<Debt>(Owner)` — the price is the curse,
        # not gold.
        self.run.add_card(make_card("debt"))
        self._play(_PAYMENT_DIVINATIONS)
        self._finish("FINISH")

    # ── The minigame ─────────────────────────────────────────────────────

    def _play(self, divinations: int) -> None:
        er = self.event_rng
        self.minigame = CrystalSphereMinigame(
            (lambda seq: _pick_from(er if er is not None else self.rng, seq)),
            divinations,
            on_reveal=self._on_reveal,
        )
        policy = self.run.crystal_sphere_clicks
        while not self.minigame.is_finished:
            # A policy returning None declines this click — the conformance
            # one does that when the recording has none left for this
            # minigame — and the automated rule takes over.
            click = policy(self.minigame) if policy is not None else None
            x, y, tool = click if click is not None else self._default_click(
                self.minigame)
            self.minigame.click(x, y, tool)
            self.divinations_spent += 1
        self._grant(self.minigame.revealed)

    def _default_click(self, game: CrystalSphereMinigame) -> tuple[int, int, int]:
        """`CrystalSphereScreenHandler.HandleAsync` — the game's own automated
        player picks `random.NextItem(cells where Entity.IsHidden)` and clicks
        it with the tool the screen opened on, which the minigame ctor sets to
        Big (CrystalSphereMinigame.cs:134)."""
        hidden = game.hidden_cells()
        if not hidden:
            return (0, 0, TOOL_BIG)
        x, y = _pick_from(self.run.crystal_sphere_rng, hidden)
        return (x, y, TOOL_BIG)

    def _on_reveal(self, item: Item) -> None:
        """CrystalSphereCurse.RevealItem (CrystalSphereCurse.cs:18-26) is the
        only item with an effect at reveal time — every other payout waits for
        CompleteMinigame. It is therefore also the only one the player cannot
        decline."""
        if item.kind is ItemKind.CURSE:
            self.run.add_card(make_card("doubt"))

    # ── Payout (CompleteMinigame -> OfferCrystalSphereRewards) ───────────

    def _grant(self, revealed: list[Item]) -> None:
        """`revealed.Select(r => r.ToReward(owner, rng)).OfType<Reward>()` then
        one `RewardsCmd.OfferCustom` (OneOffSynchronizer.cs:205-209).

        EVERY reward is built — consuming the event's Rng — before any of them
        is presented, and in reveal order. `OfType<Reward>()` drops the nulls,
        which is how the curse (whose base `ToReward` returns null) contributes
        no row. Every item is handed the EVENT's Rng, not the player's Rewards
        stream.

        DRAW ORDER. `ToReward` is not where most of the randomness lives.
        Only `CrystalSpherePotion` rolls at construction (`rng.NextItem`,
        CrystalSpherePotion.cs:36); a CardReward merely builds its options and
        a RelicReward merely stores the rng. Their draws happen later, in
        `RewardsSet.GenerateWithoutOffering`'s populate sweep — after both
        ModifyRewards passes (RewardsSet.cs:137-143). So the order here is:
        every potion roll in reveal order, then `apply_reward_modifiers`
        (hooks, then the card-group populate sweep), then the relic pull.

        RESIDUAL CAVEAT: in C# the populate sweep walks ONE ordered reward
        list, so a relic revealed before a card item populates before it. The
        sim's `CombatRewards` has no unified reward list — cards and relics
        are separate collections — so the relic pull is done after the card
        sweep unconditionally. That is the one draw-order divergence left in
        this port, and it only shows when the relic and at least one card item
        are revealed together."""
        from ..rewards import CombatRewards, apply_reward_modifiers
        from ..rooms import RoomType

        if not revealed:
            return
        er = self.event_rng
        # `room` stays None: a mid-event OfferCustom set has no AbstractRoom
        # behind it (RewardsSet.cs:106-110), same as brain_leech's Rip and
        # the_future_of_potions' screen. `room_type` only labels the screen.
        rewards = CombatRewards(room_type=RoomType.MONSTER)
        has_relic = False
        for item in revealed:
            if item.kind is ItemKind.GOLD:
                rewards.gold += _BIG_GOLD if item.is_big else _SMALL_GOLD
            elif item.kind is ItemKind.POTION:
                rewards.potions.append(self._roll_potion(item.rarity))
            elif item.kind is ItemKind.CARD:
                rewards.card_rewards.append(self._card_group(item.rarity))
            elif item.kind is ItemKind.RELIC:
                has_relic = True
        if rewards.gold:
            self.run.gain_gold(rewards.gold)
        # Hook passes, then the card groups draw their options — the sweep
        # this function already models (rewards.py, RewardsSet.cs:137-143).
        apply_reward_modifiers(self.run, rewards)
        if has_relic:
            # `RelicReward.Populate` -> `PullNextRelicFromFront(player,
            # rngOverride)`. The pull spends a grab-bag slot whether or not the
            # offer is then taken (RelicReward.cs:74-91).
            relic = self.run.pull_relic_from_front(rarity_rng=er)
            if relic is not None:
                rewards.relics.append(relic)
                self.run.offer_relic(relic)
        self.pending_rewards = rewards

    def _roll_potion(self, rarity: str):
        """`rng.NextItem(GetPotionOptions(owner, []) where Rarity == _rarity)`
        (CrystalSpherePotion.cs:31-38) — the full out-of-combat pool narrowed
        to one rarity, one draw, on the EVENT's Rng (not the Rewards stream
        `Event.offer_pool_potion` uses)."""
        from ..potion_pools import make_pool_potion

        options = [pid for pid, r in self.run.potion_pool if r == rarity]
        er = self.event_rng
        return make_pool_potion(
            _pick_from(er if er is not None else self.rng, options))

    def _card_group(self, rarity: str):
        """`new CardReward(new CardCreationOptions(Character.CardPool, Other,
        Uniform, c => c.Rarity == _rarity).WithRngOverride(rng), 3, owner)`
        (CrystalSphereCardReward.cs:49-54).

        This is the RAW CardCreationOptions ctor, NOT
        `ForNonCombatWithUniformOdds` — so unlike Room Full of Cheese's screen
        it does NOT carry `NoUpgradeRoll` (CardCreationOptions.cs:160-163) and
        its cards still take their act-scaled upgrade draw. No flags at all,
        so the reward-options hooks (the egg relics' offer-side upgrade) apply
        normally."""
        from ..cards import CardRarity
        from ..cards.pool import _CARD_CLASSES, reward_pool_card_ids
        from ..rewards import CardRewardGroup, RarityOddsType
        from ..rooms import RoomType

        wanted = CardRarity[rarity.upper()]
        pool = [
            cid for cid in reward_pool_card_ids(self.run.card_pool)
            if _CARD_CLASSES[cid].rarity == wanted
        ]
        # Left UNPOPULATED on purpose: `new CardReward(options, 3, owner)` only
        # stores the options, and the draw happens in the populate sweep after
        # both ModifyRewards passes. `_grant`'s `apply_reward_modifiers` is
        # that sweep.
        return CardRewardGroup(
            room_type=RoomType.MONSTER, count=3, pool=tuple(pool),
            odds_type=RarityOddsType.UNIFORM, rng=self.event_rng,
        )
