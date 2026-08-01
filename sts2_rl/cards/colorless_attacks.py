"""Colorless Attack cards (ColorlessCardPool.cs).

One class per card, numbers transcribed from src/Core/Models/Cards/<Name>.cs.
The pool's 11 multiplayer-only cards are excluded (FilterForPlayerCount);
Ultimate Strike / Ultimate Defend live in event_cards.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx
    from ..creatures import Creature


@register_card
class BolasCard(Card):
    """Attack (Rare, 0E) — deal 3 damage. If played, returns to your hand at
    the start of the next turn.

    Source: Bolas.cs — Damage 3 (Move), OnUpgrade +1. BeforeHandDraw: if this
    card was played last player turn and is not in the hand, add it to the
    hand (the sim's pre-draw slot is on_player_turn_start).
    """
    id = "bolas"
    name = "Bolas"
    card_type = CardType.ATTACK
    rarity = CardRarity.RARE
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._damage = 3

    def _on_upgrade(self) -> None:
        self._damage += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        DamageCmd.deal(
            ctx.hooks, ctx.resolve_target(target_idx), self._damage,
            dealer=ctx.player, card=self,
        )

    def on_player_turn_start(self, player) -> None:
        _return_to_hand_if_played_last_turn(self)


@register_card
class DramaticEntranceCard(Card):
    """Attack (Uncommon, 0E) — Innate. Deal 11 damage to ALL enemies. Exhaust.

    Source: DramaticEntrance.cs — Damage 11 (Move) to all opponents,
    keywords Exhaust + Innate, OnUpgrade damage +4.
    """
    id = "dramatic_entrance"
    name = "Dramatic Entrance"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ALL_ENEMIES
    exhausts = True
    innate = True

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._damage = 11

    def _on_upgrade(self) -> None:
        self._damage += 4

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        DamageCmd.deal(
            ctx.hooks, ctx.resolve_target(target_idx), self._damage,
            dealer=ctx.player, card=self,
        )


@register_card
class FisticuffsCard(Card):
    """Attack (Uncommon, 1E) — deal 7 damage; gain block equal to the
    unblocked damage dealt.

    Source: Fisticuffs.cs — Damage 7 (Move), then GainBlock(sum of
    TotalDamage + OverkillDamage, Move). OnUpgrade damage +2.
    """
    id = "fisticuffs"
    gains_block = True  # CardModel.GainsBlock
    name = "Fisticuffs"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 7

    def _on_upgrade(self) -> None:
        self._damage += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, DamageCmd, DamageResult
        # Fisticuffs.cs:32 sums `r.TotalDamage + r.OverkillDamage`, i.e.
        # BlockedDamage + UnblockedDamage + Overkill — the whole post-modifier
        # figure. `deal`'s int return is only the last two terms, so the
        # BLOCKED portion was dropped: hitting an enemy holding 20 block for 7
        # granted 0 block instead of 7.
        result = DamageResult()
        DamageCmd.deal(
            ctx.hooks, ctx.resolve_target(target_idx), self._damage,
            dealer=ctx.player, card=self, result=result,
        )
        if result.total_plus_overkill > 0:
            BlockCmd.apply(ctx.hooks, ctx.player,
                           result.total_plus_overkill, card=self)


@register_card
class FlashOfSteelCard(Card):
    """Attack (Uncommon, 0E) — deal 5 damage; draw 1 card.

    Source: FlashOfSteel.cs — Damage 5 (Move), Draw 1, OnUpgrade damage +3.
    """
    id = "flash_of_steel"
    name = "Flash of Steel"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._damage = 5
        self._cards = 1

    def _on_upgrade(self) -> None:
        self._damage += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, DrawCmd
        DamageCmd.deal(
            ctx.hooks, ctx.resolve_target(target_idx), self._damage,
            dealer=ctx.player, card=self,
        )
        DrawCmd.draw(ctx.player, self._cards)


@register_card
class GoldAxeCard(Card):
    """Attack (Rare, 1E) — deal 1 damage for every card played this combat.

    Source: GoldAxe.cs — CalculatedDamage: base 0 + 1 × (card plays finished
    this combat; the in-progress Gold Axe play is not yet finished).
    OnUpgrade: gains Retain.
    """
    id = "gold_axe"
    name = "Gold Axe"
    card_type = CardType.ATTACK
    rarity = CardRarity.RARE
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self.retain = False

    def _on_upgrade(self) -> None:
        self.retain = True

    def calc_damage(self, ctx: CombatCtx, target: "Creature | None" = None) -> int:
        from ..history import CardPlayedEntry
        return sum(1 for _ in ctx.combat.history.of_type(CardPlayedEntry))

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        target = ctx.resolve_target(target_idx)
        DamageCmd.deal(
            ctx.hooks, target, self.calc_damage(ctx, target),
            dealer=ctx.player, card=self,
        )


@register_card
class HandOfGreedCard(Card):
    """Attack (Rare, 2E) — deal 20 damage; if this kills the enemy, gain 20
    gold (credited to the run by finish_combat).

    Source: HandOfGreed.cs — Damage 20 (Move) + Gold 20, OnUpgrade +5/+5.
    CanBeGeneratedInCombat=false. The source also checks
    ShouldOwnerDeathTriggerFatal over the target's powers; no implemented
    power vetoes fatal, so the sim checks the kill directly.
    """
    id = "hand_of_greed"
    name = "Hand of Greed"
    card_type = CardType.ATTACK
    rarity = CardRarity.RARE
    target_type = TargetType.ANY_ENEMY
    can_be_generated_in_combat = False

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._damage = 20
        self._gold = 20

    def _on_upgrade(self) -> None:
        self._damage += 5
        self._gold += 5

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, should_trigger_fatal
        target = ctx.resolve_target(target_idx)
        was_alive = not target.is_gone
        # HandOfGreed.cs:49 — the same shape as Feed's:
        # `Target.Powers.All(p => p.ShouldOwnerDeathTriggerFatal())`, read
        # before the attack.
        fatal = should_trigger_fatal(target)
        DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
        if fatal and was_alive and target.is_dead:
            ctx.combat.gold_gained += self._gold


@register_card
class JackpotCard(Card):
    """Attack (Rare, 3E) — deal 25 damage; add 3 random 0-cost cards to your
    hand (upgraded when this card is upgraded).

    Source: Jackpot.cs — Damage 25 (Move), then GetForCombat over the
    character pool filtered to canonical cost 0 and not X-cost; upgraded
    Jackpot upgrades the generated cards. OnUpgrade damage +5.
    """
    id = "jackpot"
    name = "Jackpot"
    card_type = CardType.ATTACK
    rarity = CardRarity.RARE
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 3
        self._damage = 25
        self._cards = 3

    def _on_upgrade(self) -> None:
        self._damage += 5

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from .base import _CARD_CLASSES
        from .pool import pool_card_ids
        from ..cmds import CardPileCmd, DamageCmd
        DamageCmd.deal(
            ctx.hooks, ctx.resolve_target(target_idx), self._damage,
            dealer=ctx.player, card=self,
        )
        options = [
            cid for cid in pool_card_ids(pool=ctx.combat.card_pool)
            if _CARD_CLASSES[cid]()._energy_cost == 0
            and not _CARD_CLASSES[cid].energy_cost_x
        ]
        if not options:
            return
        for _ in range(self._cards):
            from .base import make_card
            # Jackpot.cs — CardFactory.GetForCombat on
            # Rng.CombatCardGeneration: one NextItem per card, WITH
            # replacement, in pool order.
            new_card = make_card(ctx.combat.combat_rng.card_gen.choice(options))
            if self.upgrade_level > 0 and new_card.is_upgradable:
                new_card.upgrade()
            CardPileCmd.add_to_hand(ctx.hooks, ctx.player, new_card)


@register_card
class MindBlastCard(Card):
    """Attack (Uncommon, 1E) — Innate. Deal damage equal to the number of
    cards in your draw pile.

    Source: MindBlast.cs — CalculatedDamage: 1 × draw pile count, keyword
    Innate. OnUpgrade: cost -1 (→ 0).
    """
    id = "mind_blast"
    name = "Mind Blast"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY
    innate = True

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def _on_upgrade(self) -> None:
        self._energy_cost = max(0, self._energy_cost - 1)

    def calc_damage(self, ctx: CombatCtx, target: "Creature | None" = None) -> int:
        return len(ctx.player.draw_pile)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        target = ctx.resolve_target(target_idx)
        DamageCmd.deal(
            ctx.hooks, target, self.calc_damage(ctx, target),
            dealer=ctx.player, card=self,
        )


@register_card
class OmnisliceCard(Card):
    """Attack (Uncommon, 0E) — deal 8 damage; then deal the unblocked damage
    dealt to ALL other enemies (unpowered).

    Source: Omnislice.cs — Damage 8 (Move) to the target, then the first
    hit's TotalDamage + OverkillDamage to every other hittable enemy as
    Unpowered|Move. OnUpgrade damage +3.
    """
    id = "omnislice"
    name = "Omnislice"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._damage = 8

    def _on_upgrade(self) -> None:
        self._damage += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        from ..valueprops import DamageProps
        from ..cmds import DamageResult
        target = ctx.resolve_target(target_idx)
        # Omnislice.cs:39 splashes `damageResult.TotalDamage + OverkillDamage`,
        # the same quantity Fisticuffs gains as block — not the HP actually
        # removed. Into a target holding 8 block the splash is 8, not 0.
        result = DamageResult()
        DamageCmd.deal(
            ctx.hooks, target, self._damage, dealer=ctx.player, card=self,
            result=result,
        )
        splash = result.total_plus_overkill
        if splash <= 0:
            return
        for enemy in [e for e in ctx.enemies if e is not target and not e.is_gone]:
            DamageCmd.deal(
                ctx.hooks, enemy, splash, dealer=ctx.player, card=self,
                props=DamageProps.CARD_UNPOWERED,
            )


@register_card
class RendCard(Card):
    """Attack (Rare, 2E) — deal 15 damage, plus 5 for each debuff on the
    target.

    Source: Rend.cs — CalculatedDamage: base 15 + 5 × (target's debuff
    count, temporary powers excluded; a positive power holding a negative
    amount counts as a debuff). OnUpgrade: base +3, per-debuff +3.
    """
    id = "rend"
    name = "Rend"
    card_type = CardType.ATTACK
    rarity = CardRarity.RARE
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._base = 15
        self._extra = 5

    def _on_upgrade(self) -> None:
        self._base += 3
        self._extra += 3

    @staticmethod
    def _debuff_count(target: "Creature | None") -> int:
        from ..powers import PowerType, TemporaryStrengthPower
        if target is None:
            return 0
        count = 0
        for power in target.powers.values():
            if isinstance(power, TemporaryStrengthPower):
                continue  # ITemporaryPower is excluded by the source
            is_debuff = power.power_type == PowerType.DEBUFF or (
                power.allow_negative and power.amount < 0
            )
            if is_debuff:
                count += 1
        return count

    def calc_damage(self, ctx: CombatCtx, target: "Creature | None" = None) -> int:
        return self._base + self._extra * self._debuff_count(target)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        target = ctx.resolve_target(target_idx)
        DamageCmd.deal(
            ctx.hooks, target, self.calc_damage(ctx, target),
            dealer=ctx.player, card=self,
        )


@register_card
class SalvoCard(Card):
    """Attack (Rare, 1E) — deal 12 damage; retain your hand this turn.

    Source: Salvo.cs — Damage 12 (Move) + RetainHandPower 1. OnUpgrade
    damage +4.
    """
    id = "salvo"
    name = "Salvo"
    card_type = CardType.ATTACK
    rarity = CardRarity.RARE
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 12

    def _on_upgrade(self) -> None:
        self._damage += 4

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, PowerCmd
        from ..powers import RetainHandPower
        DamageCmd.deal(
            ctx.hooks, ctx.resolve_target(target_idx), self._damage,
            dealer=ctx.player, card=self,
        )
        PowerCmd.apply(ctx.hooks, ctx.player, RetainHandPower, 1, applier=ctx.player)


@register_card
class SeekerStrikeCard(Card):
    """Attack (Uncommon, 1E) — deal 9 damage; choose 1 of 3 random cards from
    your draw pile to put into your hand. Tagged Strike.

    Source: SeekerStrike.cs — Damage 9 (Move); 3 shuffled draw-pile cards
    offered, the pick moves to the hand. OnUpgrade damage +3.
    """
    id = "seeker_strike"
    name = "Seeker Strike"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY
    tags = frozenset({"strike"})

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 9
        self._cards = 3

    def _on_upgrade(self) -> None:
        self._damage += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        DamageCmd.deal(
            ctx.hooks, ctx.resolve_target(target_idx), self._damage,
            dealer=ctx.player, card=self,
        )
        player = ctx.player
        # SeekerStrike.cs:36 — `PileType.Draw.GetPile(Owner).Cards.ToList()
        # .StableShuffle(Rng.CombatCardSelection).Take(Cards.IntValue)`. Three
        # divergences stacked: the shared rng, `sample` rather than
        # shuffle-then-take, and no stabilising sort, so identical draw-pile
        # CONTENTS in a different ORDER offered different cards. The pile goes
        # over reversed, in the game's top-first orientation, for the same
        # reason card/catastrophe reverses it.
        from ..player import stable_shuffled_cards

        options = stable_shuffled_cards(
            list(reversed(player.draw_pile)),
            ctx.combat.combat_rng,
            stream=ctx.combat.combat_rng.card_selection,
        )[:self._cards]
        # SeekerStrike.cs:37 hands these off to `CardSelectCmd.FromCombatPile`
        # against the DRAW pile (filtered to `cardOptions.Contains`), so an
        # installed Selector sees the `orderby Rarity, Id` pre-sort
        # (CardSelectCmd.cs:403-408), not the shuffled order above.
        chosen = ctx.combat.select_cards("from_draw", options, 1, is_draw_pile=True)
        for card in chosen:
            if len(player.hand) >= player.MAX_HAND_SIZE:
                break
            player.draw_pile.remove(card)
            player.hand.append(card)


@register_card
class ThrummingHatchetCard(Card):
    """Attack (Uncommon, 1E) — deal 11 damage. If played, returns to your
    hand at the start of the next turn.

    Source: ThrummingHatchet.cs — Damage 11 (Move), OnUpgrade +3; the same
    BeforeHandDraw return-to-hand as Bolas.
    """
    id = "thrumming_hatchet"
    name = "Thrumming Hatchet"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 11

    def _on_upgrade(self) -> None:
        self._damage += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        DamageCmd.deal(
            ctx.hooks, ctx.resolve_target(target_idx), self._damage,
            dealer=ctx.player, card=self,
        )

    def on_player_turn_start(self, player) -> None:
        _return_to_hand_if_played_last_turn(self)


@register_card
class VolleyCard(Card):
    """Attack (Uncommon, X) — deal 10 damage to a random enemy X times.

    Source: Volley.cs — Damage 10 (Move) with hit count = X, targeting
    random opponents. OnUpgrade damage +4.
    """
    id = "volley"
    name = "Volley"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.RANDOM_ENEMY
    energy_cost_x = True

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._damage = 10

    def _on_upgrade(self) -> None:
        self._damage += 4

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        for _ in range(self.captured_x):
            living = [e for e in ctx.enemies if not e.is_gone]
            if not living or ctx.player.is_dead:
                return
            # AttackCommand.cs:601-602 — `Rng.CombatTargets.NextItem(validTargets)`
            # per hit, with the living set re-derived each time.
            enemy = ctx.combat.combat_rng.targets.choice(living)
            DamageCmd.deal(ctx.hooks, enemy, self._damage, dealer=ctx.player, card=self)


def _return_to_hand_if_played_last_turn(card: Card) -> None:
    """Shared Bolas / Thrumming Hatchet return: if the card was played last
    player turn and is not in the hand, move it there from its current pile
    (mirrors CardModel.BeforeHandDraw in both sources). Runs in the pre-draw
    turn-start slot, so the hand-size cap is effectively never binding."""
    combat = card.combat
    if combat is None or combat.is_over:
        return
    from ..history import CardPlayedEntry
    played_last_turn = any(
        e.card is card and e.turn == combat.turn - 1
        for e in combat.history.of_type(CardPlayedEntry)
    )
    if not played_last_turn:
        return
    player = combat.player
    if card in player.hand or len(player.hand) >= player.MAX_HAND_SIZE:
        return
    # Bolas.cs:43-47 / ThrummingHatchet.cs:37-41 test only
    # `pile == null || pile.Type != PileType.Hand` and then
    # `CardPileCmd.Add(this, PileType.Hand)`, which moves the card from
    # WHEREVER it is — the EXHAUST pile included, and the PLAY pile too
    # (the hook fires from a turn boundary, but a card can sit in Play across
    # one: `AutoPlayFromDrawPile` parks all its picks before playing any).
    # Searching only draw and discard silently stranded an exhausted card
    # (Brand, Burning Pact, Second Wind and Fiend Fire all exhaust from hand
    # with a null filter).
    if player.remove_from_current_pile(card) is not None:
        player.hand.append(card)
