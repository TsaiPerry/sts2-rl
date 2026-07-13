"""RunState — the minimal out-of-combat run layer that events act on.

Mirrors the single-player slice of the game's Player/IRunState: current and
max HP, gold, the deck, relics, potions, and the relic grab bag. Events
(sts2_rl.events) mutate this state; combats are entered with
`create_combat(...)` and their outcome synced back with `finish_combat(...)`.

Faithful mechanics ported from the source:
  - starting stats: 80 HP, 99 gold, 5×Strike + 4×Defend + Bash
    (Ironclad.cs: StartingHp/StartingGold/StartingDeck)
  - rest-site heal: 30% of max HP, truncated (HealRestSiteOption.cs)
  - relic grab bag: rarity roll <0.5 Common, <0.83 Uncommon, else Rare, then
    the first bag relic of that rarity is pulled and removed for the rest of
    the run (RelicFactory.RollRarity / PullNextRelicFromFront)
  - card transformation: a random different card of Common/Uncommon/Rare
    rarity from the character pool replaces the original in place
    (CardFactory.GetDefaultTransformationOptions / GetFilteredTransformationOptions)
  - gold amounts truncate toward zero and gains require amount > 0
    (PlayerCmd.GainGold/LoseGold `(int)amount` casts)

Deliberate simplifications: no run-level hook dispatch (relics like Tungsten
Rod don't reduce event HP loss), no unlock state (every implemented relic/
potion/card is in its pool), and the game's Colorless transform pool for
Quest/Event-rarity originals falls back to the character pool.
"""
from __future__ import annotations

import copy
import random
from typing import TYPE_CHECKING, Callable

from .cards import Card, CardRarity, IRONCLAD_POOL, make_card
from .cards.base import _CARD_CLASSES
from .combat import CombatState
from .potions import Potion, _POTION_CLASSES
from .relics import ALL_RELICS, Relic, RelicRarity, make_relic

if TYPE_CHECKING:
    from .monsters import Encounter


# Rarities eligible for the relic grab bag (starter/shop/event/ancient relics
# never come from the bag — they have dedicated sources).
_BAG_RARITIES = (RelicRarity.COMMON, RelicRarity.UNCOMMON, RelicRarity.RARE)

# Rarities a transform can produce (GetFilteredTransformationOptions keeps
# Common/Uncommon/Rare only).
_TRANSFORM_RARITIES = (CardRarity.COMMON, CardRarity.UNCOMMON, CardRarity.RARE)


def ironclad_starting_deck() -> list[Card]:
    """Ironclad.cs StartingDeck: 5 Strikes, 4 Defends, 1 Bash."""
    return (
        [make_card("strike") for _ in range(5)]
        + [make_card("defend") for _ in range(4)]
        + [make_card("bash")]
    )


class RunState:
    STARTING_HP = 80       # Ironclad.cs StartingHp
    STARTING_GOLD = 99     # Ironclad.cs StartingGold
    MAX_POTIONS = 3        # Player potionSlotCount

    def __init__(
        self,
        rng: random.Random | None = None,
        deck: list[Card] | None = None,
        max_hp: int | None = None,
        hp: int | None = None,
        gold: int | None = None,
        relics: list[Relic] | None = None,
        potions: list[Potion] | None = None,
        card_selector: Callable[[str, list[Card], int], list[Card]] | None = None,
    ) -> None:
        self.rng = rng or random.Random()
        self.deck: list[Card] = deck if deck is not None else ironclad_starting_deck()
        self.max_hp = max_hp if max_hp is not None else self.STARTING_HP
        self.hp = hp if hp is not None else self.max_hp
        self.gold = gold if gold is not None else self.STARTING_GOLD
        self.relics: list[Relic] = list(relics or [])
        self.potions: list[Potion] = list(potions or [])[: self.MAX_POTIONS]
        # Out-of-combat card chooser with the same signature as
        # CombatState.card_selector: (purpose, candidates, count) -> cards.
        # None = uniform random with the run RNG.
        self.card_selector = card_selector
        # Relic grab bag (RelicGrabBag): every bag-eligible relic in a random
        # order; pulled relics never reappear this run.
        self.relic_grab_bag: list[str] = [
            relic_id for relic_id, cls in ALL_RELICS.items()
            if cls.rarity in _BAG_RARITIES
        ]
        self.rng.shuffle(self.relic_grab_bag)

    # ── HP ───────────────────────────────────────────────────────────────

    @property
    def is_dead(self) -> bool:
        return self.hp <= 0

    def heal(self, amount: int) -> int:
        """Heal up to amount, capped at max HP. Returns HP restored."""
        healed = max(0, min(int(amount), self.max_hp - self.hp))
        self.hp += healed
        return healed

    def lose_hp(self, amount: int) -> None:
        """Unblockable, unpowered event damage (CreatureCmd.Damage with
        ValueProp.Unblockable | Unpowered). Can kill."""
        self.hp -= int(amount)

    def kill(self) -> None:
        self.hp = 0

    def rest_site_heal_amount(self) -> int:
        """HealRestSiteOption.GetBaseHealAmount: 30% of max HP, truncated."""
        return self.max_hp * 3 // 10

    def gain_max_hp(self, amount: int) -> None:
        """CreatureCmd.GainMaxHp: raise max HP, then heal the same amount."""
        self.max_hp += int(amount)
        self.heal(int(amount))

    def lose_max_hp(self, amount: int) -> None:
        """CreatureCmd.LoseMaxHp: max HP floors at 1; current HP above the new
        max is lost as unblockable damage (i.e. clamped)."""
        new_max = max(1, self.max_hp - int(amount))
        self.max_hp = new_max
        self.hp = min(self.hp, new_max)

    # ── Gold ─────────────────────────────────────────────────────────────

    def gain_gold(self, amount: float) -> None:
        """PlayerCmd.GainGold: truncate toward zero; no-op unless positive."""
        gained = int(amount)
        if amount > 0:
            self.gold += gained

    def lose_gold(self, amount: float) -> None:
        """PlayerCmd.LoseGold: truncate; gold never goes below 0."""
        self.gold = max(0, self.gold - int(amount))

    # ── Deck ─────────────────────────────────────────────────────────────

    def add_card(self, card: Card) -> Card:
        self.deck.append(card)
        return card

    def remove_cards(self, cards: list[Card]) -> None:
        for card in cards:
            self.deck.remove(card)

    def removable_cards(self) -> list[Card]:
        """CardModel.IsRemovable: everything except Eternal cards."""
        return [c for c in self.deck if not c.eternal]

    def transformable_cards(self) -> list[Card]:
        """CardModel.IsTransformable: in the deck this equals IsRemovable."""
        return self.removable_cards()

    def upgradable_cards(self) -> list[Card]:
        return [c for c in self.deck if c.is_upgradable]

    def select_cards(
        self,
        purpose: str,
        candidates: list[Card],
        count: int = 1,
    ) -> list[Card]:
        """Out-of-combat card selection (mirrors CardSelectCmd.FromDeck*).

        purpose is a short label ("transform", "upgrade", "remove",
        "enchant") so a selector policy can distinguish contexts. Delegates to
        self.card_selector when installed; otherwise picks uniformly at
        random with the run RNG.
        """
        if count <= 0 or not candidates:
            return []
        count = min(count, len(candidates))
        if self.card_selector is not None:
            chosen = list(self.card_selector(purpose, list(candidates), count))[:count]
            return [c for c in chosen if c in candidates]
        return self.rng.sample(candidates, count)

    def transform_card(self, card: Card, into: Card | None = None) -> Card:
        """Transform a deck card (CardCmd.TransformToRandom / TransformTo).

        With `into` set, the replacement is exact (Wood Carvings' Peck /
        Toric Toughness). Otherwise a random different Common/Uncommon/Rare
        card from the character pool is rolled. The replacement takes the
        original's place in the deck.
        """
        if into is None:
            options = [
                card_id for card_id in IRONCLAD_POOL
                if _CARD_CLASSES[card_id].rarity in _TRANSFORM_RARITIES
                and card_id != card.id
            ]
            into = make_card(self.rng.choice(options))
        idx = self.deck.index(card)
        self.deck[idx] = into
        return into

    # ── Potions ──────────────────────────────────────────────────────────

    def add_potion(self, potion: Potion) -> bool:
        """Add a potion if a slot is free. Returns whether it was kept."""
        if len(self.potions) >= self.MAX_POTIONS:
            return False
        self.potions.append(potion)
        return True

    def random_potion(self) -> Potion:
        """A uniformly random potion from the implemented pool (approximates
        the character + shared potion pools of PotionReward)."""
        cls = self.rng.choice(sorted(_POTION_CLASSES.values(), key=lambda c: c.id))
        return cls()

    # ── Relics ───────────────────────────────────────────────────────────

    def add_relic(self, relic: Relic | str) -> Relic:
        if isinstance(relic, str):
            relic = make_relic(relic)
        self.relics.append(relic)
        return relic

    def has_available_relics(self) -> bool:
        """RelicGrabBag.HasAvailableRelics for this run."""
        return bool(self.relic_grab_bag)

    def pull_relic_from_front(self) -> Relic | None:
        """RelicFactory.PullNextRelicFromFront: roll rarity (<0.5 Common,
        <0.83 Uncommon, else Rare), pull the first bag relic of that rarity.
        Falls back to the front of the bag when no relic matches the rolled
        rarity (the game substitutes a fallback relic); None if the bag is
        empty."""
        if not self.relic_grab_bag:
            return None
        roll = self.rng.random()
        rarity = (
            RelicRarity.COMMON if roll < 0.5
            else RelicRarity.UNCOMMON if roll < 0.83
            else RelicRarity.RARE
        )
        for relic_id in self.relic_grab_bag:
            if ALL_RELICS[relic_id].rarity == rarity:
                self.relic_grab_bag.remove(relic_id)
                return make_relic(relic_id)
        return make_relic(self.relic_grab_bag.pop(0))

    def obtain_relic_from_grab_bag(self) -> Relic | None:
        """Pull from the bag front and add it to the run's relics."""
        relic = self.pull_relic_from_front()
        if relic is not None:
            self.relics.append(relic)
        return relic

    # ── Combat integration ───────────────────────────────────────────────

    def create_combat(self, encounter: Encounter, **kwargs) -> CombatState:
        """Enter a combat carrying this run's deck, relics, potions, and HP.

        The deck is deep-copied so in-combat mutations (upgrades, afflictions,
        cost changes) don't leak back — the game clones canonical cards into
        each combat the same way. Call finish_combat afterwards to sync the
        outcome back into the run.
        """
        return CombatState(
            starting_deck=copy.deepcopy(self.deck),
            rng=self.rng,
            encounter=encounter,
            potions=self.potions,
            relics=self.relics,
            card_selector=kwargs.pop("card_selector", self.card_selector),
            max_hp=self.max_hp,
            current_hp=self.hp,
            **kwargs,
        )

    def finish_combat(self, combat: CombatState) -> None:
        """Sync a finished combat back into the run: HP, max HP (Feed), and
        remaining potions."""
        self.max_hp = combat.player.max_hp
        self.hp = max(0, combat.player.hp)
        self.potions = list(combat.player.potions)

    def __repr__(self) -> str:
        return (
            f"RunState(hp={self.hp}/{self.max_hp}, gold={self.gold}, "
            f"deck={len(self.deck)} cards, relics={len(self.relics)}, "
            f"potions={len(self.potions)})"
        )
