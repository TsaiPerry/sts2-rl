"""HookSystem — the central callback registry, mirroring STS2's AbstractModel
hook pattern.

Every power, card, and the combat history register as a listener on a single
`HookSystem`. Dispatch is duck-typed: a hook only calls listeners that define a
matching method, so a listener implements only the hooks it cares about. Three
families (see the HookSystem docstring): Modifier (aggregate a return value),
Event (fire-and-forget), and Predicate (any False short-circuits). `HookSystem.
combat` back-references the owning CombatState so listeners can reach
combat-level state.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .valueprops import ValueProp

if TYPE_CHECKING:
    from .cards import Card
    from .creatures import Creature
    from .player import PlayerCombatState


class HookSystem:
    """
    Central callback registry mirroring the STS2 AbstractModel hook pattern.

    Three hook families:
      Modifier  — aggregate listener returns before applying an effect.
                    Additive:       each listener returns an amount to ADD; system sums them.
                    Multiplicative: each listener returns a factor; system takes the product.
                    Chain:          each listener receives the current value and returns a new one.
      Event     — fire-and-forget; listeners react with side effects.
      Predicate — any listener returning False short-circuits the default behaviour.
    """

    def __init__(self) -> None:
        self._listeners: list[Any] = []
        # Back-reference to the owning CombatState; set by CombatState.__init__.
        # Lets powers reach combat-level state (e.g. Infested spawning Wrigglers).
        self.combat: Any = None

    def register(self, listener: Any) -> None:
        self._listeners.append(listener)

    def unregister(self, listener: Any) -> None:
        self._listeners.remove(listener)

    # ── Modifier hooks — damage ──────────────────────────────────────────
    # Pipeline: base + additive → × multiplicative → cap → block → modify_hp_lost → apply

    def modify_damage_additive(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None = None,
        card: Card | None = None,
    ) -> int:
        """Sum of all flat bonuses added before the multiplier (e.g. Pen Nib +1)."""
        total = 0
        for l in list(self._listeners):
            if hasattr(l, "modify_damage_additive"):
                total += l.modify_damage_additive(target, amount, dealer, card)
        return total

    def modify_damage_multiplicative(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None = None,
        card: Card | None = None,
    ) -> float:
        """Product of all damage multipliers (e.g. Vulnerable ×1.5, Weak ×0.75)."""
        factor = 1.0
        for l in list(self._listeners):
            if hasattr(l, "modify_damage_multiplicative"):
                factor *= l.modify_damage_multiplicative(target, amount, dealer, card)
        return factor

    def modify_damage_cap(
        self,
        target: Creature,
        dealer: Creature | None = None,
        card: Card | None = None,
    ) -> int | None:
        """Minimum cap returned by any listener, or None for no cap."""
        cap: int | None = None
        for l in list(self._listeners):
            if hasattr(l, "modify_damage_cap"):
                c = l.modify_damage_cap(target, dealer, card)
                if c is not None:
                    cap = c if cap is None else min(cap, c)
        return cap

    # ── Modifier hooks — block ───────────────────────────────────────────
    # Pipeline: base + additive → × multiplicative → apply

    def modify_block_additive(
        self,
        target: Creature,
        amount: int,
        card: Card | None = None,
    ) -> int:
        """Sum of all flat block bonuses (e.g. Dexterity +N per Defend)."""
        total = 0
        for l in list(self._listeners):
            if hasattr(l, "modify_block_additive"):
                total += l.modify_block_additive(target, amount, card)
        return total

    def modify_block_multiplicative(
        self,
        target: Creature,
        amount: int,
        card: Card | None = None,
    ) -> float:
        """Product of all block multipliers (e.g. Frail ×0.75)."""
        factor = 1.0
        for l in list(self._listeners):
            if hasattr(l, "modify_block_multiplicative"):
                factor *= l.modify_block_multiplicative(target, amount, card)
        return factor

    # ── Modifier hooks — HP loss ─────────────────────────────────────────

    def modify_hp_lost(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None = None,
        card: Card | None = None,
    ) -> int:
        """Chain-modify HP loss after block absorption (e.g. Torii: cap at 1, Tungsten Rod: -1)."""
        for l in list(self._listeners):
            if hasattr(l, "modify_hp_lost"):
                amount = l.modify_hp_lost(target, amount, dealer, card)
        return max(0, amount)

    # ── Modifier hooks — misc ────────────────────────────────────────────

    def modify_strength_given(
        self,
        target: Creature,
        amount: int,
        card: Card | None = None,
    ) -> int:
        """Chain-modify strength gain."""
        for l in list(self._listeners):
            if hasattr(l, "modify_strength_given"):
                amount = l.modify_strength_given(target, amount, card)
        return amount

    def modify_power_amount(
        self,
        power_cls: type,
        target: Creature,
        amount: int,
        applier: Creature | None = None,
    ) -> int:
        """Chain-modify the amount of a power as it is applied (mirrors
        TryModifyPowerAmountReceived; e.g. Ruined Helmet doubles the first
        Strength gain). Only runs on real applications, never previews."""
        for l in list(self._listeners):
            if hasattr(l, "modify_power_amount"):
                amount = l.modify_power_amount(power_cls, target, amount, applier)
        return amount

    def modify_vulnerable_multiplier(
        self, dealer: Creature | None, mult: float
    ) -> float:
        """Chain-modify the Vulnerable damage multiplier (mirrors
        ModifyVulnerableMultiplier; e.g. Paper Phrog adds +0.25). Consulted by
        VulnerablePower — stateless, so it is preview-safe."""
        for l in list(self._listeners):
            if hasattr(l, "modify_vulnerable_multiplier"):
                mult = l.modify_vulnerable_multiplier(dealer, mult)
        return mult

    def modify_card_energy_cost(self, card: Card, cost: int) -> int:
        """Chain-modify a card's energy cost for this play (e.g. Apotheosis, Nightmare)."""
        for l in list(self._listeners):
            if hasattr(l, "modify_card_energy_cost"):
                cost = l.modify_card_energy_cost(card, cost)
        return max(0, cost)

    def modify_max_energy(self, player: PlayerCombatState, amount: int) -> int:
        """Chain-modify base energy gained at turn start (e.g. Ectoplasm -1)."""
        for l in list(self._listeners):
            if hasattr(l, "modify_max_energy"):
                amount = l.modify_max_energy(player, amount)
        return max(0, amount)

    def modify_energy_gain(self, player: PlayerCombatState, amount: int) -> int:
        """Chain-modify bonus energy gained mid-turn from cards or effects."""
        for l in list(self._listeners):
            if hasattr(l, "modify_energy_gain"):
                amount = l.modify_energy_gain(player, amount)
        return max(0, amount)

    def modify_hand_draw(self, player: PlayerCombatState, count: int) -> int:
        """Chain-modify how many cards are drawn at turn start."""
        for l in list(self._listeners):
            if hasattr(l, "modify_hand_draw"):
                count = l.modify_hand_draw(player, count)
        return max(0, count)

    def modify_card_play_count(
        self,
        card: Card,
        target: Creature | None,
        count: int,
    ) -> int:
        """Chain-modify how many times a card is played (e.g. Burst, Corruption)."""
        for l in list(self._listeners):
            if hasattr(l, "modify_card_play_count"):
                count = l.modify_card_play_count(card, target, count)
        return max(1, count)

    def modify_card_play_result_pile(self, card: Card, pile: str) -> str:
        """Chain-modify where a played card ends up once its play resolves
        (mirrors ModifyCardPlayResultPileTypeAndPosition). pile is "discard"
        by default; a listener may return "draw_top" to put the card on top
        of the draw pile instead (Nostalgia). Consulted only for cards that
        would land in the discard pile (exhausted cards and Powers never
        reach it)."""
        for l in list(self._listeners):
            if hasattr(l, "modify_card_play_result_pile"):
                pile = l.modify_card_play_result_pile(card, pile)
        return pile

    def modify_orb_value(self, player: PlayerCombatState, value: int) -> int:
        """Chain-modify orb passive/evoke value (e.g. Defect relic bonuses)."""
        for l in list(self._listeners):
            if hasattr(l, "modify_orb_value"):
                value = l.modify_orb_value(player, value)
        return value

    def modify_x_value(self, card: Card, value: int) -> int:
        """Chain-modify the X captured when an X-cost card is played (mirrors
        ModifyXValue, e.g. Chemical X +2)."""
        for l in list(self._listeners):
            if hasattr(l, "modify_x_value"):
                value = l.modify_x_value(card, value)
        return max(0, value)

    # ── Event hooks — combat lifecycle ───────────────────────────────────

    def on_combat_start(self) -> None:
        """Fires after combat state is initialised, before the first player turn."""
        for l in list(self._listeners):
            if hasattr(l, "on_combat_start"):
                l.on_combat_start()

    def on_combat_end(self, player_won: bool) -> None:
        """Fires when combat concludes."""
        for l in list(self._listeners):
            if hasattr(l, "on_combat_end"):
                l.on_combat_end(player_won)

    # ── Event hooks — player turn lifecycle ──────────────────────────────

    def on_player_turn_start(self, player: PlayerCombatState) -> None:
        """Fires at the start of the player's turn, before cards are drawn."""
        for l in list(self._listeners):
            if hasattr(l, "on_player_turn_start"):
                l.on_player_turn_start(player)

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        """Fires at the start of the player's turn AFTER the hand is drawn.

        Maps the game's post-draw turn-start slots — AfterPlayerTurnStart(Late)
        and the player-side AfterSideTurnStart, which CombatManager fires after
        SetupPlayerTurn (energy reset → hand draw) completes. Most turn-start
        relics live here (Akabeko, Bellows, Lantern, ...).
        """
        for l in list(self._listeners):
            if hasattr(l, "on_player_turn_started"):
                l.on_player_turn_started(player)

    def on_player_turn_end(self, player: PlayerCombatState) -> None:
        """Fires at the end of the player's turn, before the hand is discarded."""
        for l in list(self._listeners):
            if hasattr(l, "on_player_turn_end"):
                l.on_player_turn_end(player)

    def on_energy_reset(self, player: PlayerCombatState) -> None:
        """Fires immediately after energy is set at turn start."""
        for l in list(self._listeners):
            if hasattr(l, "on_energy_reset"):
                l.on_energy_reset(player)

    def on_energy_spent(self, card: Card, amount: int) -> None:
        """Fires when energy is consumed to play a card."""
        for l in list(self._listeners):
            if hasattr(l, "on_energy_spent"):
                l.on_energy_spent(card, amount)

    # ── Event hooks — enemy turn lifecycle ───────────────────────────────

    def on_enemy_turn_start(self, enemy: Creature) -> None:
        """Fires at the start of the enemy's turn."""
        for l in list(self._listeners):
            if hasattr(l, "on_enemy_turn_start"):
                l.on_enemy_turn_start(enemy)

    def on_enemy_turn_end(self, enemy: Creature) -> None:
        """Fires at the end of each individual enemy's turn."""
        for l in list(self._listeners):
            if hasattr(l, "on_enemy_turn_end"):
                l.on_enemy_turn_end(enemy)

    def on_enemy_side_end(self) -> None:
        """Fires once after ALL living enemies have taken their turns for the round."""
        for l in list(self._listeners):
            if hasattr(l, "on_enemy_side_end"):
                l.on_enemy_side_end()

    def before_attack(self, dealer: Creature) -> None:
        """Fires before a monster attack command's hits (mirrors Hook.BeforeAttack)."""
        for l in list(self._listeners):
            if hasattr(l, "before_attack"):
                l.before_attack(dealer)

    def after_attack(self, dealer: Creature) -> None:
        """Fires after a monster attack command's last hit (mirrors Hook.AfterAttack);
        powers that boost "the next attack" (Vigor) consume their stacks here."""
        for l in list(self._listeners):
            if hasattr(l, "after_attack"):
                l.after_attack(dealer)

    # ── Event hooks — card lifecycle ─────────────────────────────────────

    def before_card_played(self, card: Card, target: Creature | None = None) -> None:
        """Fires before a card's on_play() resolves (mirrors BeforeCardPlayed).
        Used by relics that must act on the card before its effects (e.g. Pen
        Nib marking the 10th Attack for doubling).

        target is the single creature the card was played at (mirrors
        CardPlay.Target) — set only for a resolved single-enemy target, None
        for untargeted/AoE plays. Consulted by SurroundedPower to flip Kaiser
        Crab facing on any targeted card play, not just damaging ones."""
        for l in list(self._listeners):
            if hasattr(l, "before_card_played"):
                l.before_card_played(card, target)

    def on_card_played(self, card: Card) -> None:
        """Fires after a card's on_play() resolves."""
        for l in list(self._listeners):
            if hasattr(l, "on_card_played"):
                l.on_card_played(card)

    def on_card_drawn(self, card: Card, from_hand_draw: bool = False) -> None:
        """Fires each time a card enters the hand from the draw pile.

        from_hand_draw is True only for the initial hand draw at the start of
        the player's turn; False for all mid-turn draws (card effects, powers).
        Mirrors STS2's AfterCardDrawn / AfterCardDrawnEarly fromHandDraw param.
        """
        for l in list(self._listeners):
            if hasattr(l, "on_card_drawn"):
                l.on_card_drawn(card, from_hand_draw)

    def on_card_entered_combat(self, card: Card) -> None:
        """Fires when a card is created mid-combat (e.g. Slimed, Dazed, Wound
        added by an enemy). Lets active powers afflict it (Ringing, Tangled)."""
        for l in list(self._listeners):
            if hasattr(l, "on_card_entered_combat"):
                l.on_card_entered_combat(card)

    def on_card_discarded(self, card: Card) -> None:
        """Fires when a card is discarded at end of turn (not when played)."""
        for l in list(self._listeners):
            if hasattr(l, "on_card_discarded"):
                l.on_card_discarded(card)

    def on_card_exhausted(self, card: Card) -> None:
        """Fires when a card is sent to the exhaust pile."""
        for l in list(self._listeners):
            if hasattr(l, "on_card_exhausted"):
                l.on_card_exhausted(card)

    def on_card_retained(self, card: Card) -> None:
        """Fires when a card stays in hand past the end of a turn."""
        for l in list(self._listeners):
            if hasattr(l, "on_card_retained"):
                l.on_card_retained(card)

    def on_hand_emptied(self, player: PlayerCombatState) -> None:
        """Fires after the hand has been fully discarded at end of turn."""
        for l in list(self._listeners):
            if hasattr(l, "on_hand_emptied"):
                l.on_hand_emptied(player)

    def on_shuffle(self, player: PlayerCombatState) -> None:
        """Fires when the discard pile is shuffled back into the draw pile."""
        for l in list(self._listeners):
            if hasattr(l, "on_shuffle"):
                l.on_shuffle(player)

    # ── Event hooks — damage / block / HP ────────────────────────────────

    def on_attacked(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None = None,
        card: Card | None = None,
    ) -> None:
        """Fires when a hit connects (post-modifier, pre-block). amount > 0 guaranteed."""
        for l in list(self._listeners):
            if hasattr(l, "on_attacked"):
                l.on_attacked(target, amount, dealer, card)

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None = None,
        card: Card | None = None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        """Fires after a creature receives damage (post-pipeline, post-block).

        props carries the damage typing (mirrors AfterDamageReceived's
        ValueProp param) so listeners can gate on powered attacks."""
        for l in list(self._listeners):
            if hasattr(l, "on_damage_received"):
                l.on_damage_received(target, amount, dealer, card, props)

    def on_damage_dealt(
        self,
        dealer: Creature,
        target: Creature,
        amount: int,
        card: Card | None = None,
    ) -> None:
        """Fires after a creature deals damage (e.g. Thorns reflection, lifesteal)."""
        for l in list(self._listeners):
            if hasattr(l, "on_damage_dealt"):
                l.on_damage_dealt(dealer, target, amount, card)

    def on_block_gained(
        self, target: Creature, amount: int, card: Card | None = None
    ) -> None:
        """Fires after block is added to a creature. `card` is the source card
        when the block came from a card play (None for powers/potions/relics)."""
        for l in list(self._listeners):
            if hasattr(l, "on_block_gained"):
                l.on_block_gained(target, amount, card)

    def on_block_broken(self, target: Creature) -> None:
        """Fires when an attack deals more damage than the target's remaining block."""
        for l in list(self._listeners):
            if hasattr(l, "on_block_broken"):
                l.on_block_broken(target)

    def on_block_cleared(self, target: Creature) -> None:
        """Fires when block is wiped at the start of a turn."""
        for l in list(self._listeners):
            if hasattr(l, "on_block_cleared"):
                l.on_block_cleared(target)

    def on_hp_changed(self, target: Creature, delta: int) -> None:
        """Fires whenever a creature's HP changes (delta is negative for damage)."""
        for l in list(self._listeners):
            if hasattr(l, "on_hp_changed"):
                l.on_hp_changed(target, delta)

    # ── Event hooks — powers ─────────────────────────────────────────────

    def on_power_applied(
        self,
        name: str,
        target: Creature,
        amount: int,
        applier: Creature | None = None,
    ) -> None:
        """Fires when a power (strength, dexterity, etc.) is applied to a creature.

        applier is the creature that applied the power, when known (mirrors
        AfterPowerApplied's applier param)."""
        for l in list(self._listeners):
            if hasattr(l, "on_power_applied"):
                l.on_power_applied(name, target, amount, applier)

    def on_power_amount_changed(
        self,
        name: str,
        target: Creature,
        delta: int,
        applier: Creature | None = None,
    ) -> None:
        """Fires when an existing power's stack count changes.

        applier is the creature that caused the change, when known (None for
        ticks/expiry)."""
        for l in list(self._listeners):
            if hasattr(l, "on_power_amount_changed"):
                l.on_power_amount_changed(name, target, delta, applier)

    # ── Event hooks — creatures entering / leaving combat ───────────────

    def on_creature_added(self, creature: Creature) -> None:
        """Fires when a creature joins combat mid-fight (mirrors AfterCreatureAddedToCombat)."""
        for l in list(self._listeners):
            if hasattr(l, "on_creature_added"):
                l.on_creature_added(creature)

    def on_creature_escaped(self, creature: Creature) -> None:
        """Fires when a creature escapes from combat alive."""
        for l in list(self._listeners):
            if hasattr(l, "on_creature_escaped"):
                l.on_creature_escaped(creature)

    def on_stunned(self, creature: Creature) -> None:
        """Fires when a creature is stunned (will skip its next turn)."""
        for l in list(self._listeners):
            if hasattr(l, "on_stunned"):
                l.on_stunned(creature)

    # ── Event hooks — potions ────────────────────────────────────────────

    def on_potion_used(self, potion: Any, target: Creature | None) -> None:
        """Fires after a potion's effect resolves (mirrors AfterPotionUsed)."""
        for l in list(self._listeners):
            if hasattr(l, "on_potion_used"):
                l.on_potion_used(potion, target)

    # ── Event hooks — death ──────────────────────────────────────────────

    def on_death(self, creature: Creature) -> None:
        """Fires when a creature's HP reaches 0 and death is not prevented."""
        for l in list(self._listeners):
            if hasattr(l, "on_death"):
                l.on_death(creature)

    # ── Predicate hooks ──────────────────────────────────────────────────

    def should_die(self, creature: Creature) -> bool:
        """False from any listener prevents death (e.g. Fairy in a Bottle, Torii)."""
        for l in list(self._listeners):
            if hasattr(l, "should_die"):
                if not l.should_die(creature):
                    return False
        return True

    def should_clear_block(self, creature: Creature) -> bool:
        """False from any listener preserves block across the turn boundary."""
        for l in list(self._listeners):
            if hasattr(l, "should_clear_block"):
                if not l.should_clear_block(creature):
                    return False
        return True

    def should_reset_energy(self, player: PlayerCombatState) -> bool:
        """False from any listener makes turn-start energy ADD to the current
        energy instead of replacing it (mirrors ShouldPlayerResetEnergy →
        ResetEnergy / AddMaxEnergyToCurrent; e.g. Ice Cream)."""
        for l in list(self._listeners):
            if hasattr(l, "should_reset_energy"):
                if not l.should_reset_energy(player):
                    return False
        return True

    def should_draw(self, player: PlayerCombatState, from_hand_draw: bool = False) -> bool:
        """False from any listener prevents the next draw (e.g. No Draw status).

        from_hand_draw is True only for the initial hand draw at the start of
        the player's turn; False for all mid-turn draws (card effects, powers).
        Mirrors STS2's ShouldDraw fromHandDraw param.
        """
        for l in list(self._listeners):
            if hasattr(l, "should_draw"):
                if not l.should_draw(player, from_hand_draw):
                    return False
        return True

    def should_flush_hand(self) -> bool:
        """False from any listener keeps the hand instead of discarding it at
        the end of the turn (mirrors ShouldFlush; e.g. Ringing Triangle keeps
        the turn-1 hand)."""
        for l in list(self._listeners):
            if hasattr(l, "should_flush_hand"):
                if not l.should_flush_hand():
                    return False
        return True

    def should_allow_hitting(self, target: Creature) -> bool:
        """False from any listener makes the target un-hittable (e.g. Intangible)."""
        for l in list(self._listeners):
            if hasattr(l, "should_allow_hitting"):
                if not l.should_allow_hitting(target):
                    return False
        return True

    def should_play_card(self, card: Card, auto_play: bool = False) -> bool:
        """False from any listener prevents the card from being played (e.g. Ringing).

        auto_play is True when the play is an auto-play (Havoc, Stampede, ...)
        rather than a manual play from the hand — mirrors the AutoPlayType
        argument of the game's ShouldPlay hook (Enthralled only blocks manual
        plays).
        """
        for l in list(self._listeners):
            if hasattr(l, "should_play_card"):
                if not l.should_play_card(card, auto_play):
                    return False
        return True

    def should_ethereal_trigger(self, card: Card) -> bool:
        """False from any listener prevents an ethereal card from being exhausted."""
        for l in list(self._listeners):
            if hasattr(l, "should_ethereal_trigger"):
                if not l.should_ethereal_trigger(card):
                    return False
        return True
