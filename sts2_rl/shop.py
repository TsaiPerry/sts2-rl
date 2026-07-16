"""Merchant shop — the run layer's Shop room (MerchantRoom / MerchantInventory).

Ports the single-player slice of the game's merchant:
  - MerchantRoom.cs / MerchantInventory.cs → MerchantInventory (the stocked
    shop, built when a Shop map point is entered)
  - MerchantEntry.cs + the four entry subclasses → the entry classes below
    (card / relic / potion / card-removal), each with a cost and a purchase()
  - CardFactory.CreateForMerchant / RelicFactory.PullNextRelicFromBack /
    PotionFactory + the pricing formulas transcribed from the source

Inventory (single player):
  - 5 character cards, types [Attack, Attack, Skill, Skill, Power]; one random
    entry is On Sale (half price). Rarity is the shop roll; the card is a
    uniform pick of the rolled (rarity, type) from the Ironclad pool, deduped
    against the other card entries.
  - 2 Colorless cards, rarities [Uncommon, Rare] (the rarity overload of
    CardFactory.CreateForMerchant: exactly that rarity, uniform pick from the
    Colorless pool, deduped against the other card entries). Colorless cards
    cost 15% more (GetCost: RoundToInt(base × 1.15)).
  - 3 relics: two of a rolled rarity (Common/Uncommon/Rare) pulled from the
    back of the grab bag, one of Shop rarity from the shop-relic bag; all
    filtered by IsAllowedInShops.
  - 3 distinct random potions.
  - 1 card-removal service (75 + 25 × removals used; the Inflation ascension
    raises this, not modeled — the sim uses non-ascension values).

Deliberate deviations from the source (documented per the repo convention):
  - one shared run RNG instead of the game's per-player `PlayerRng.Shops`
    stream (the repo's one-RNG convention);
  - purchases resolve immediately (no reservation / UI); The Courier's
    restock-after-purchase is not modeled (entries clear when bought).
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from .cards import CardRarity, CardType
from .cards.base import _CARD_CLASSES, make_card
from .relics import RelicRarity

if TYPE_CHECKING:
    from .cards import Card
    from .potions import Potion
    from .relics import Relic
    from .run import RunState


# MerchantInventory._coloredCardTypes — the 5 character-card slots.
_COLORED_CARD_TYPES = (
    CardType.ATTACK,
    CardType.ATTACK,
    CardType.SKILL,
    CardType.SKILL,
    CardType.POWER,
)

# MerchantInventory._colorlessCardRarities — the 2 Colorless-card slots.
_COLORLESS_CARD_RARITIES = (
    CardRarity.UNCOMMON,
    CardRarity.RARE,
)

def _next_float(rng: random.Random, lo: float, hi: float) -> float:
    """Rng.NextFloat(lo, hi)."""
    return lo + (hi - lo) * rng.random()


def _create_merchant_card(
    run: "RunState", card_type: CardType, exclude_ids: set[str]
) -> "Card | None":
    """CardFactory.CreateForMerchant(type): roll the shop rarity (reading the
    run's drifting pity offset without advancing it, per
    RollWithoutChangingFutureOdds), drop to the next rarity that actually has
    a card of this type, then pick uniformly."""
    from .cards import IRONCLAD_POOL
    from .rewards import RarityOddsType, next_allowed_card_rarity

    options = [
        cid
        for cid in IRONCLAD_POOL
        if _CARD_CLASSES[cid].rarity != CardRarity.BASIC
        and cid not in exclude_ids
    ]
    rarity = run.card_rarity_odds.roll_without_changing_future_odds(
        RarityOddsType.SHOP
    )
    rarity = next_allowed_card_rarity(
        rarity,
        lambda r: any(
            _CARD_CLASSES[c].rarity == r and _CARD_CLASSES[c].card_type == card_type
            for c in options
        ),
    )
    if rarity is None:
        return None
    matching = [
        c
        for c in options
        if _CARD_CLASSES[c].rarity == rarity
        and _CARD_CLASSES[c].card_type == card_type
    ]
    return make_card(run.rng.choice(matching)) if matching else None


def _create_merchant_colorless_card(
    run: "RunState", rarity: CardRarity, exclude_ids: set[str]
) -> "Card | None":
    """CardFactory.CreateForMerchant(rarity): the Colorless slots take the
    given rarity as-is (no pity roll, no fallback walk) and pick uniformly
    from the Colorless pool, deduped against the other card entries."""
    from .cards import COLORLESS_POOL

    matching = [
        cid
        for cid in COLORLESS_POOL
        if _CARD_CLASSES[cid].rarity == rarity and cid not in exclude_ids
    ]
    return make_card(run.rng.choice(matching)) if matching else None


# ── Entries ──────────────────────────────────────────────────────────────


class MerchantEntry:
    """MerchantEntry.cs — a purchasable slot with a cost and stock flag."""

    def __init__(self, run: "RunState") -> None:
        self.run = run
        self.cost = 0

    @property
    def is_stocked(self) -> bool:
        raise NotImplementedError

    @property
    def enough_gold(self) -> bool:
        return self.cost <= self.run.gold

    def purchase(self) -> bool:
        """Buy this entry if stocked and affordable. Returns success."""
        if not self.is_stocked or not self.enough_gold:
            return False
        gold_spent = self.cost
        if not self._buy():
            return False
        # Hook.AfterItemPurchased (MerchantEntry.OnTryPurchaseWrapper): fires
        # for every successful purchase with the gold actually spent (Maw
        # Bank deactivates the first time this is > 0).
        for relic in list(self.run.relics):
            relic.after_item_purchased(self.run, self, gold_spent)
        return True

    def _buy(self) -> bool:
        raise NotImplementedError


class MerchantCardEntry(MerchantEntry):
    """MerchantCardEntry.cs — a buyable card. GetCost: Rare 150, Uncommon 75,
    else 50 (Colorless cards ×1.15, rounded), times the ±5% jitter, halved
    when On Sale."""

    def __init__(
        self, run: "RunState", card_type: CardType, exclude_ids: set[str]
    ) -> None:
        super().__init__(run)
        self.card: "Card | None" = _create_merchant_card(run, card_type, exclude_ids)
        self.on_sale = False
        self._calc_cost()

    @property
    def is_stocked(self) -> bool:
        return self.card is not None

    def set_on_sale(self) -> None:
        self.on_sale = True
        self._calc_cost()

    @staticmethod
    def _base_cost(card: "Card") -> int:
        from .cards import COLORLESS_POOL

        cost = {
            CardRarity.RARE: 150,
            CardRarity.UNCOMMON: 75,
        }.get(card.rarity, 50)
        if card.id in COLORLESS_POOL:
            # GetCost: card.Pool is ColorlessCardPool → RoundToInt(num × 1.15)
            cost = round(cost * 1.15)
        return cost

    def _calc_cost(self) -> None:
        if self.card is None:
            return
        self.cost = round(self._base_cost(self.card) * _next_float(self.run.rng, 0.95, 1.05))
        if self.on_sale:
            self.cost //= 2

    def _buy(self) -> bool:
        self.run.lose_gold(self.cost)
        self.run.add_card(self.card)
        self.card = None
        return True


class MerchantColorlessCardEntry(MerchantCardEntry):
    """A Colorless card slot: stocked by rarity (Uncommon / Rare) from the
    Colorless pool instead of by type from the character pool (mirrors the
    MerchantCardEntry(cardRarity) constructor + PopulateColorlessCardEntries).
    Never On Sale — the sale roll only covers the 5 character slots."""

    def __init__(
        self, run: "RunState", rarity: CardRarity, exclude_ids: set[str]
    ) -> None:
        MerchantEntry.__init__(self, run)
        self.card: "Card | None" = _create_merchant_colorless_card(
            run, rarity, exclude_ids
        )
        self.on_sale = False
        self._calc_cost()


class MerchantRelicEntry(MerchantEntry):
    """MerchantRelicEntry.cs — a buyable relic pulled from the back of the grab
    bag. Cost = MerchantCost × ±15% jitter."""

    def __init__(
        self, run: "RunState", rarity: RelicRarity, blacklist: set[str]
    ) -> None:
        super().__init__(run)
        self.relic: "Relic | None" = run.pull_relic_from_back(rarity, blacklist)
        self._calc_cost()

    @property
    def is_stocked(self) -> bool:
        return self.relic is not None

    def _calc_cost(self) -> None:
        if self.relic is None:
            return
        self.cost = round(self.relic.merchant_cost * _next_float(self.run.rng, 0.85, 1.15))

    def _buy(self) -> bool:
        self.run.lose_gold(self.cost)
        self.run.add_relic(self.relic)
        self.relic = None
        return True


class MerchantPotionEntry(MerchantEntry):
    """MerchantPotionEntry.cs — a buyable potion. GetCost: Rare 100, Uncommon
    75, else 50, times the ±5% jitter."""

    def __init__(self, run: "RunState", potion: "Potion") -> None:
        super().__init__(run)
        self.potion: "Potion | None" = potion
        self._calc_cost()

    @property
    def is_stocked(self) -> bool:
        return self.potion is not None

    @staticmethod
    def _base_cost(potion: "Potion") -> int:
        return {"rare": 100, "uncommon": 75}.get(potion.rarity, 50)

    def _calc_cost(self) -> None:
        if self.potion is None:
            return
        self.cost = round(self._base_cost(self.potion) * _next_float(self.run.rng, 0.95, 1.05))

    def _buy(self) -> bool:
        # PotionCmd.TryToProcure fails when the potion belt is full.
        if not self.run.add_potion(self.potion):
            return False
        self.run.lose_gold(self.cost)
        self.potion = None
        return True


class MerchantCardRemovalEntry(MerchantEntry):
    """MerchantCardRemovalEntry.cs — remove a card from the deck. Cost climbs
    75 + 25 × removals used (non-ascension; Inflation raises it, not modeled)."""

    BASE_COST = 75
    PRICE_INCREASE = 25

    def __init__(self, run: "RunState") -> None:
        super().__init__(run)
        self.used = False
        self._calc_cost()

    @property
    def is_stocked(self) -> bool:
        return not self.used

    def _calc_cost(self) -> None:
        self.cost = self.BASE_COST + self.PRICE_INCREASE * self.run.card_shop_removals_used

    def _buy(self) -> bool:
        removable = self.run.removable_cards()
        chosen = self.run.select_cards("remove", removable, 1)
        if not chosen:
            return False
        self.run.lose_gold(self.cost)
        self.run.remove_cards(chosen)
        self.run.card_shop_removals_used += 1
        self.used = True
        return True


# ── Inventory ──────────────────────────────────────────────────────────────


class MerchantInventory:
    """MerchantInventory.cs — the stocked shop for one Shop room visit."""

    def __init__(self, run: "RunState") -> None:
        self.run = run
        self.character_card_entries: list[MerchantCardEntry] = []
        self.colorless_card_entries: list[MerchantColorlessCardEntry] = []
        self.relic_entries: list[MerchantRelicEntry] = []
        self.potion_entries: list[MerchantPotionEntry] = []
        self.card_removal_entry: MerchantCardRemovalEntry | None = None

    @property
    def card_entries(self) -> list[MerchantCardEntry]:
        """MerchantInventory.CardEntries: character then Colorless slots."""
        return [*self.character_card_entries, *self.colorless_card_entries]

    @classmethod
    def create(cls, run: "RunState") -> "MerchantInventory":
        """MerchantInventory.CreateForNormalMerchant."""
        inv = cls(run)
        inv._populate_cards()
        inv._populate_colorless_cards()
        inv._populate_relics()
        inv._populate_potions()
        inv.card_removal_entry = MerchantCardRemovalEntry(run)
        return inv

    @property
    def all_entries(self) -> list[MerchantEntry]:
        entries: list[MerchantEntry] = [
            *self.card_entries,
            *self.relic_entries,
            *self.potion_entries,
        ]
        if self.card_removal_entry is not None:
            entries.append(self.card_removal_entry)
        return entries

    def _populate_cards(self) -> None:
        on_sale_index = self.run.rng.randrange(len(_COLORED_CARD_TYPES))
        exclude_ids: set[str] = set()
        for i, card_type in enumerate(_COLORED_CARD_TYPES):
            entry = MerchantCardEntry(self.run, card_type, exclude_ids)
            if entry.card is not None:
                exclude_ids.add(entry.card.id)
            self.character_card_entries.append(entry)
            if i == on_sale_index:
                entry.set_on_sale()

    def _populate_colorless_cards(self) -> None:
        """PopulateColorlessCardEntries: one Uncommon and one Rare Colorless
        slot, deduped against every stocked card entry."""
        for rarity in _COLORLESS_CARD_RARITIES:
            exclude_ids = {
                e.card.id for e in self.card_entries if e.card is not None
            }
            entry = MerchantColorlessCardEntry(self.run, rarity, exclude_ids)
            self.colorless_card_entries.append(entry)

    def _populate_relics(self) -> None:
        from .run import roll_relic_rarity

        rarities = [
            roll_relic_rarity(self.run.rng),
            roll_relic_rarity(self.run.rng),
            RelicRarity.SHOP,
        ]
        blacklist: set[str] = set()
        for rarity in rarities:
            entry = MerchantRelicEntry(self.run, rarity, blacklist)
            if entry.relic is not None:
                blacklist.add(entry.relic.id)
            self.relic_entries.append(entry)

    def _populate_potions(self) -> None:
        for potion in self.run.random_potions(3, distinct=True):
            self.potion_entries.append(MerchantPotionEntry(self.run, potion))
