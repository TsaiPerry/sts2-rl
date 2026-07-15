"""The Neow (Ancient) relic pool — the 22 relics Neow's run-start offer draws
from (src/Core/Models/Events/Neow.cs AllPossibleOptions), one class per source
file in src/Core/Models/Relics.

Neow presents 2 "positive" options and 1 "curse" option (see
sts2_rl/events/neow.py); every option grants its relic, whose entire effect is
usually the AfterObtained pickup. They are Ancient rarity, so they never enter
the relic grab bag or shops.

Deliberate deviations (documented per the repo convention):
  - Kaleidoscope (cards from OTHER characters' pools) and Massive Scroll
    (multiplayer-only) can never apply in the single-character sim; they are
    registered with is_allowed_at_neow=False so Neow never offers them,
    mirroring their IsAllowedAtNeow/IsAllowed gates evaluating false here.
  - Lead Paperweight's Colorless card falls back to the Ironclad pool (the
    sim has no Colorless pool — same fallback as Mad Science's Chaos rider).
  - Card offers that the game shows on a choose/skip screen (Hefty Tablet,
    Lost Coffer) go through run.select_cards purposes "obtain" /
    "card_reward"; a selector returning [] is the skip.
  - Small Capsule's single-relic reward screen is auto-taken (a pure gain,
    like the sim's treasure chest).
"""
from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


def _basic_with_tag(deck, tag: str, last: bool = False):
    """The first (or last) Basic-rarity deck card carrying `tag`
    (Neow's Talisman / Leafy Poultice pick their Strike/Defend this way)."""
    from ..cards import CardRarity

    matches = [
        c for c in deck if c.rarity == CardRarity.BASIC and tag in c.tags
    ]
    if not matches:
        return None
    return matches[-1] if last else matches[0]


# ═════════════════════════════════════════════════════════════════════════
# Positive options
# ═════════════════════════════════════════════════════════════════════════


@register_relic
class ArcaneScroll(Relic):
    """ArcaneScroll.cs — obtain a random Rare card (uniform, never upgraded)."""

    id = "arcane_scroll"
    name = "Arcane Scroll"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        from ..cards import CardRarity, make_card
        from ..cards.base import _CARD_CLASSES
        from ..cards.pool import pool_card_ids

        rares = [
            cid for cid in pool_card_ids()
            if _CARD_CLASSES[cid].rarity == CardRarity.RARE
        ]
        if rares:
            run.add_card(make_card(run.rng.choice(rares)))


@register_relic
class BoomingConch(Relic):
    """BoomingConch.cs — in Elite combats, draw 2 extra cards and gain 1
    energy on your first turn."""

    id = "booming_conch"
    name = "Booming Conch"
    rarity = RelicRarity.ANCIENT
    CARDS = 2
    ENERGY = 1

    def _in_elite_first_turn(self) -> bool:
        from ..rooms import RoomType

        return (
            self.combat is not None
            and self.combat.room_type == RoomType.ELITE
            and self.turn <= 1
        )

    def modify_hand_draw(self, player, count: int) -> int:
        if self._in_elite_first_turn():
            return count + self.CARDS
        return count

    def on_player_turn_start(self, player) -> None:
        # AfterSideTurnStart, turn 1 only: +1 energy (fires post-energy-reset).
        if self._in_elite_first_turn():
            player.energy += self.ENERGY


@register_relic
class FishingRod(Relic):
    """FishingRod.cs — after every 3rd Monster combat, upgrade a random
    upgradable card in the deck."""

    id = "fishing_rod"
    name = "Fishing Rod"
    rarity = RelicRarity.ANCIENT
    COMBATS = 3

    def __init__(self) -> None:
        super().__init__()
        self.combats_seen = 0

    def after_combat_end(self, run, room_type) -> None:
        from ..rooms import RoomType

        if room_type != RoomType.MONSTER:
            return
        self.combats_seen += 1
        if self.combats_seen % self.COMBATS == 0:
            upgradable = [c for c in run.deck if c.is_upgradable]
            if upgradable:
                run.rng.choice(upgradable).upgrade()


@register_relic
class GoldenPearl(Relic):
    """GoldenPearl.cs — gain 150 gold."""

    id = "golden_pearl"
    name = "Golden Pearl"
    rarity = RelicRarity.ANCIENT
    GOLD = 150

    def after_obtained(self, run) -> None:
        run.gain_gold(self.GOLD)


@register_relic
class Kaleidoscope(Relic):
    """Kaleidoscope.cs — obtain 2 cards from other characters' pools.

    IsAllowedAtNeow requires every character card pool unlocked; the
    single-character sim has only the Ironclad pool, so this can never be
    offered (documented stub, mirrors Colorful Philosophers)."""

    id = "kaleidoscope"
    name = "Kaleidoscope"
    rarity = RelicRarity.ANCIENT
    is_allowed_at_neow = False


@register_relic
class LeadPaperweight(Relic):
    """LeadPaperweight.cs — obtain a random Colorless card (regular base
    odds). The sim has no Colorless pool: falls back to the Ironclad pool."""

    id = "lead_paperweight"
    name = "Lead Paperweight"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        from ..rewards import RarityOddsType, create_reward_cards

        cards = create_reward_cards(
            run, RarityOddsType.REGULAR, count=1,
            mutate_pity=False, modify_hooks=False,
        )
        for card in cards:
            run.add_card(card)


@register_relic
class LostCoffer(Relic):
    """LostCoffer.cs — a reward screen: a 3-card choice (regular base odds)
    and a potion."""

    id = "lost_coffer"
    name = "Lost Coffer"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        from ..rewards import RarityOddsType, create_reward_cards

        cards = create_reward_cards(
            run, RarityOddsType.REGULAR, mutate_pity=False,
        )
        for card in run.select_cards("card_reward", cards, 1):
            run.add_card(card)
        run.add_potion(run.random_potion())


@register_relic
class MassiveScroll(Relic):
    """MassiveScroll.cs — multiplayer-only (IsAllowed: Players.Count > 1);
    never offerable in the single-player sim (documented stub)."""

    id = "massive_scroll"
    name = "Massive Scroll"
    rarity = RelicRarity.ANCIENT
    is_allowed_at_neow = False


@register_relic
class NeowsTorment(Relic):
    """NeowsTorment.cs — add a Neow's Fury to the deck."""

    id = "neows_torment"
    name = "Neow's Torment"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        run.add_card(make_card("neows_fury"))


@register_relic
class NewLeaf(Relic):
    """NewLeaf.cs — transform a chosen card."""

    id = "new_leaf"
    name = "New Leaf"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        for card in run.select_cards("transform", run.transformable_cards(), 1):
            run.transform_card(card)


@register_relic
class PhialHolster(Relic):
    """PhialHolster.cs — gain 1 potion slot and 2 random potions."""

    id = "phial_holster"
    name = "Phial Holster"
    rarity = RelicRarity.ANCIENT
    POTION_SLOTS = 1
    POTIONS = 2

    def after_obtained(self, run) -> None:
        run.max_potions += self.POTION_SLOTS
        for potion in run.random_potions(self.POTIONS, distinct=True):
            run.add_potion(potion)


@register_relic
class Pomander(Relic):
    """Pomander.cs — upgrade a chosen card."""

    id = "pomander"
    name = "Pomander"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        for card in run.select_cards("upgrade", run.upgradable_cards(), 1):
            card.upgrade()


@register_relic
class PreciseScissors(Relic):
    """PreciseScissors.cs — remove a chosen card from the deck."""

    id = "precise_scissors"
    name = "Precise Scissors"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        chosen = run.select_cards("remove", run.removable_cards(), 1)
        run.remove_cards(chosen)


@register_relic
class ScrollBoxes(Relic):
    """ScrollBoxes.cs — choose one of 2 card bundles; each bundle is 2 random
    Commons + 1 random Uncommon, all 6 cards unique across both bundles."""

    id = "scroll_boxes"
    name = "Scroll Boxes"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        from ..cards import CardRarity, make_card
        from ..cards.base import _CARD_CLASSES
        from ..cards.pool import pool_card_ids

        commons = [
            cid for cid in pool_card_ids()
            if _CARD_CLASSES[cid].rarity == CardRarity.COMMON
        ]
        uncommons = [
            cid for cid in pool_card_ids()
            if _CARD_CLASSES[cid].rarity == CardRarity.UNCOMMON
        ]
        used: set[str] = set()
        bundles: list[list[str]] = []
        for _ in range(2):
            bundle: list[str] = []
            for _ in range(2):
                options = [c for c in commons if c not in used]
                pick = run.rng.choice(options)
                bundle.append(pick)
                used.add(pick)
            options = [c for c in uncommons if c not in used]
            pick = run.rng.choice(options)
            bundle.append(pick)
            used.add(pick)
            bundles.append(bundle)
        chosen = bundles[run.select_option("bundle", len(bundles))]
        for cid in chosen:
            run.add_card(make_card(cid))


@register_relic
class WingedBoots(Relic):
    """WingedBoots.cs — you may travel to any point on the next map row
    (ignoring paths) 3 times."""

    id = "winged_boots"
    name = "Winged Boots"
    rarity = RelicRarity.ANCIENT
    USES = 3

    def __init__(self) -> None:
        super().__init__()
        self.times_used = 0

    @property
    def is_used_up(self) -> bool:
        return self.times_used >= self.USES

    def should_allow_free_travel(self) -> bool:
        return not self.is_used_up

    def on_free_travel_used(self, run) -> None:
        self.times_used += 1


@register_relic
class LavaRock(Relic):
    """LavaRock.cs — the first act's boss rewards include 2 extra relics
    (grab-bag pulls); one-shot."""

    id = "lava_rock"
    name = "Lava Rock"
    rarity = RelicRarity.ANCIENT
    RELICS = 2

    def __init__(self) -> None:
        super().__init__()
        self.has_triggered = False

    def modify_combat_rewards(self, run, rewards) -> None:
        from ..rooms import RoomType

        if (
            self.has_triggered
            or rewards.room_type != RoomType.BOSS
            or run.act_index != 0
        ):
            return
        for _ in range(self.RELICS):
            relic = run.pull_relic_from_front()
            if relic is None:
                break
            run.add_relic(relic)
            rewards.relics.append(relic)
        self.has_triggered = True


@register_relic
class NeowsTalisman(Relic):
    """NeowsTalisman.cs — upgrade the deck's last basic Strike and last basic
    Defend."""

    id = "neows_talisman"
    name = "Neow's Talisman"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        for tag in ("strike", "defend"):
            card = _basic_with_tag(run.deck, tag, last=True)
            if card is not None:
                card.upgrade()


@register_relic
class NutritiousOyster(Relic):
    """NutritiousOyster.cs — gain 11 Max HP."""

    id = "nutritious_oyster"
    name = "Nutritious Oyster"
    rarity = RelicRarity.ANCIENT
    MAX_HP = 11

    def after_obtained(self, run) -> None:
        run.gain_max_hp(self.MAX_HP)


@register_relic
class SmallCapsule(Relic):
    """SmallCapsule.cs — a reward screen with one grab-bag relic (auto-taken
    in the sim)."""

    id = "small_capsule"
    name = "Small Capsule"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        run.obtain_relic_from_grab_bag()


@register_relic
class StoneHumidifier(Relic):
    """StoneHumidifier.cs — whenever you Heal at a rest site, gain 5 Max HP."""

    id = "stone_humidifier"
    name = "Stone Humidifier"
    rarity = RelicRarity.ANCIENT
    MAX_HP = 5

    def after_rest_site_heal(self, run) -> None:
        run.gain_max_hp(self.MAX_HP)


# ═════════════════════════════════════════════════════════════════════════
# Curse options
# ═════════════════════════════════════════════════════════════════════════


@register_relic
class CursedPearl(Relic):
    """CursedPearl.cs — gain 333 gold and a Greed curse."""

    id = "cursed_pearl"
    name = "Cursed Pearl"
    rarity = RelicRarity.ANCIENT
    GOLD = 333

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        run.add_card(make_card("greed"))
        run.gain_gold(self.GOLD)


@register_relic
class HeftyTablet(Relic):
    """HeftyTablet.cs — choose one of 3 random Rare cards (uniform, never
    upgraded; skippable) and gain an Injury curse."""

    id = "hefty_tablet"
    name = "Hefty Tablet"
    rarity = RelicRarity.ANCIENT
    CARDS = 3

    def after_obtained(self, run) -> None:
        from ..cards import CardRarity, make_card
        from ..cards.base import _CARD_CLASSES
        from ..cards.pool import pool_card_ids

        rares = [
            cid for cid in pool_card_ids()
            if _CARD_CLASSES[cid].rarity == CardRarity.RARE
        ]
        count = min(self.CARDS, len(rares))
        options = [make_card(cid) for cid in run.rng.sample(rares, count)]
        for card in run.select_cards("obtain", options, 1):
            run.add_card(card)
        run.add_card(make_card("injury"))


@register_relic
class LargeCapsule(Relic):
    """LargeCapsule.cs — obtain 2 grab-bag relics; add a Strike and a Defend
    to the deck."""

    id = "large_capsule"
    name = "Large Capsule"
    rarity = RelicRarity.ANCIENT
    RELICS = 2

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        for _ in range(self.RELICS):
            run.obtain_relic_from_grab_bag()
        run.add_card(make_card("strike"))
        run.add_card(make_card("defend"))


@register_relic
class LeafyPoultice(Relic):
    """LeafyPoultice.cs — lose 12 Max HP; transform a basic Strike and a
    basic Defend (the deck's first of each)."""

    id = "leafy_poultice"
    name = "Leafy Poultice"
    rarity = RelicRarity.ANCIENT
    MAX_HP = 12

    def after_obtained(self, run) -> None:
        run.lose_max_hp(self.MAX_HP)
        for tag in ("strike", "defend"):
            card = _basic_with_tag(run.deck, tag)
            if card is not None:
                run.transform_card(card)


@register_relic
class NeowsBones(Relic):
    """NeowsBones.cs — obtain 2 random relics from Neow's own pool (excluding
    Neow's Bones; their pickup effects apply) and a random curse."""

    id = "neows_bones"
    name = "Neow's Bones"
    rarity = RelicRarity.ANCIENT
    RELICS = 2
    CURSES = 1

    def after_obtained(self, run) -> None:
        from ..cards.pool import random_curses
        from ..events.neow import neow_relic_pool

        pool = [rid for rid in neow_relic_pool(run) if rid != self.id]
        run.rng.shuffle(pool)
        for rid in pool[: self.RELICS]:
            run.add_relic(rid)
        for curse in random_curses(run.rng, self.CURSES, distinct=True):
            run.add_card(curse)


@register_relic
class PrecariousShears(Relic):
    """PrecariousShears.cs — remove 2 chosen cards; take 16 damage."""

    id = "precarious_shears"
    name = "Precarious Shears"
    rarity = RelicRarity.ANCIENT
    CARDS = 2
    DAMAGE = 16

    def after_obtained(self, run) -> None:
        chosen = run.select_cards("remove", run.removable_cards(), self.CARDS)
        run.remove_cards(chosen)
        run.lose_hp(self.DAMAGE)


@register_relic
class SilkenTress(Relic):
    """SilkenTress.cs — lose ALL gold; the next card reward's options are all
    enchanted with Glam (first time you play the card each combat, it plays
    an extra time); one-shot."""

    id = "silken_tress"
    name = "Silken Tress"
    rarity = RelicRarity.ANCIENT

    def __init__(self) -> None:
        super().__init__()
        self.is_used = False

    def after_obtained(self, run) -> None:
        run.lose_gold(run.gold)

    def modify_card_reward_options(self, run, cards) -> None:
        from ..enchantments import GlamEnchantment

        if self.is_used:
            return
        for card in cards:
            if GlamEnchantment.can_enchant(card):
                GlamEnchantment().attach(card)
        self.is_used = True


@register_relic
class SilverCrucible(Relic):
    """SilverCrucible.cs — your next 3 card rewards offer upgraded cards, but
    the first treasure room you enter holds no chest."""

    id = "silver_crucible"
    name = "Silver Crucible"
    rarity = RelicRarity.ANCIENT
    CARD_REWARDS = 3

    def __init__(self) -> None:
        super().__init__()
        self.times_used = 0
        self.treasure_rooms_entered = 0

    def modify_card_reward_options(self, run, cards) -> None:
        if self.times_used >= self.CARD_REWARDS:
            return
        for card in cards:
            if card.is_upgradable:
                card.upgrade()
        self.times_used += 1

    def after_room_entered(self, run, point, room_type) -> None:
        from ..rooms import RoomType

        if room_type == RoomType.TREASURE:
            self.treasure_rooms_entered += 1

    def should_generate_treasure(self, run) -> bool:
        return self.treasure_rooms_entered > 1
