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


# Where each listener kind falls in one creature's walk, mirroring
# CombatState.IterateHookListeners (CombatState.cs:413-467). Listener classes
# declare their slot as a `hook_category` class attribute; the sim has no orbs,
# and CombatHistory is a sim-only listener that sits ahead of the walk.
CAT_HISTORY = -1
CAT_POWER = 0
CAT_RELIC = 1
CAT_POTION = 2
CAT_CARD = 3
_CAT_CARD = CAT_CARD          # default for a listener that declares nothing

# The complete listener passes Hook.cs runs, in order. "" is the plain hook.
_PHASES = ("_very_early", "_early", "", "_late")
# Longest first, so `_very_early` is matched before the `_early` it ends with.
_PHASE_SUFFIXES = tuple(sorted((s for s in _PHASES if s), key=len, reverse=True))

_PHASE_HOOKS_BY_CLASS: dict[type, frozenset[str]] = {}


# ── Hook.IterateCombatHookListeners' combat-over gate ────────────────────
#
# `Hook.IterateCombatHookListeners` (Hook.cs:53-63) opens with
#
#     if (IsOverOrEnding && !IsStarting) yield break;
#
# so a dispatch that BEGINS after the combat started ending reaches nobody.
# It is an iterator, so the test runs once at enumeration start rather than
# per listener: a dispatch that began while the combat was live still visits
# every listener even if one of them ends the combat. `_each` is a generator
# too, so putting the test at the top of it reproduces both halves exactly.
#
# It does NOT apply to every hook. Bucketing all 147 public dispatchers by how
# each enumerates listeners (`py audit/tools/dormancy_probes.py hook-buckets`):
# 73 go through this guard, 63 call `runState.IterateHookListeners` directly —
# an iterator that never consults it — 10 bypass it deliberately by walking a
# creature's own listeners, and `ModifyDamage` delegates its whole walk to the
# run-side `ModifyDamageInternal`. The ten deliberate bypasses are exactly the
# kill/death/combat-end sequence that has to keep working while the combat is
# ending: AfterCardPlayed, AfterDamageGiven, AfterBlockBroken,
# AfterCreatureAddedToCombat, AfterDiedToDoom, ModifyKeywordsInCombat,
# ModifyUnblockedDamageTarget, ShouldCreatureBeRemovedFromCombatAfterDeath,
# ShouldStopCombatFromEnding and ShouldPowerBeRemovedOnDeath.
#
# So the gate is a per-hook property, and this map is the sim hook name -> the
# C# dispatcher it IS, restricted to the guarded bucket. A sim hook absent from
# the map is ungated, which is the safe direction: it keeps today's behaviour.
# Absent on purpose, with the reason:
#   * the run-side and bypass buckets above (on_card_played, on_damage_dealt,
#     on_block_broken, on_creature_added, on_death, should_die,
#     should_stop_combat_from_ending, before/on_damage_received,
#     modify_hp_lost, on_combat_start, on_combat_end, before/on_potion_used,
#     should_remove_from_combat_after_death, should_power_be_removed_on_death,
#     the two modify_damage_* chains, and after_card_changed_piles --
#     Hook.AfterCardChangedPiles walks `runState.IterateHookListeners(
#     combatState)` (Hook.cs:169), NOT IterateCombatHookListeners, so it is
#     run-side and takes no IsOverOrEnding yield-break. Note the pairing at the
#     transform site: AfterCardEnteredCombat one line earlier IS gated
#     (Hook.cs:225), so the two dispatches CardCmd.cs:445-447 makes back to back
#     do not share the gate;
#   * sim-only names with no `public static` in Hook.cs at all
#     (modify_damage_cap, modify_strength_given, modify_vulnerable_multiplier,
#     on_attacked, on_card_retained, on_hp_changed, on_power_applied,
#     on_creature_escaped, on_stunned, on_extra_turn);
#
# `IsStarting` needs no counterpart: the sim only ever sets Phase.COMBAT_OVER
# in `CombatState._end_combat`, so the gate cannot be closed during setup.
_COMBAT_GATED_HOOKS: dict[str, str] = {
    "after_attack": "AfterAttack",
    "after_auto_post_play_phase_entered": "AfterAutoPostPlayPhaseEntered",
    "after_auto_pre_play_phase_entered": "AfterAutoPrePlayPhaseEntered",
    "after_enemy_side_start": "AfterSideTurnStart",
    "after_player_turn_end": "AfterTurnEnd",
    "after_side_turn_start": "AfterSideTurnStart",
    "before_attack": "BeforeAttack",
    "before_card_played": "BeforeCardPlayed",
    "before_enemy_side_end": "BeforeTurnEnd",
    "before_enemy_side_start": "BeforeSideTurnStart",
    "before_side_turn_start": "BeforeSideTurnStart",
    "modify_block_additive": "ModifyBlock",
    "modify_block_multiplicative": "ModifyBlock",
    "modify_card_energy_cost": "ModifyEnergyCostInCombat",
    "modify_card_play_count": "ModifyCardPlayCount",
    "modify_card_play_result_pile": "ModifyCardPlayResultPileTypeAndPosition",
    "modify_energy_gain": "ModifyEnergyGain",
    "modify_hand_draw": "ModifyHandDraw",
    "modify_max_energy": "ModifyMaxEnergy",
    "modify_orb_value": "ModifyOrbValue",
    "modify_power_amount": "ModifyPowerAmountReceived",
    "modify_x_value": "ModifyXValue",
    "on_block_cleared": "AfterBlockCleared",
    "on_block_gained": "AfterBlockGained",
    "on_card_discarded": "AfterCardDiscarded",
    "on_card_drawn": "AfterCardDrawn",
    "on_card_entered_combat": "AfterCardEnteredCombat",
    "on_card_exhausted": "AfterCardExhausted",
    "on_energy_reset": "AfterEnergyReset",
    "on_energy_spent": "AfterEnergySpent",
    "on_enemy_side_end": "AfterTurnEnd",
    "on_hand_emptied": "AfterHandEmptied",
    "on_player_turn_end": "BeforeTurnEnd",
    "on_player_turn_start": "BeforeHandDraw",
    "on_player_turn_started": "AfterPlayerTurnStart",
    "on_power_amount_changed": "AfterPowerAmountChanged",
    "on_shuffle": "AfterShuffle",
    "should_allow_hitting": "ShouldAllowHitting",
    "should_clear_block": "ShouldClearBlock",
    "should_draw": "ShouldDraw",
    "should_ethereal_trigger": "ShouldEtherealTrigger",
    "should_flush_hand": "ShouldFlush",
    "should_play_card": "ShouldPlay",
    "should_reset_energy": "ShouldPlayerResetEnergy",
    "should_take_extra_turn": "ShouldTakeExtraTurn",
}


def _phase_hooks(cls: type) -> frozenset[str]:
    """The base hook names `cls` declares a phase variant of.

    Memoised per class: the scan walks `dir()`, which is far too slow to run
    per dispatch, and a listener class's method set does not change at runtime.
    """
    cached = _PHASE_HOOKS_BY_CLASS.get(cls)
    if cached is None:
        names = set()
        for attr in dir(cls):
            # Longest first: `x_very_early` also ends in `_early`, and only the
            # `_very_early` reading is the real one.
            for suffix in _PHASE_SUFFIXES:
                if attr.endswith(suffix):
                    names.add(attr[: -len(suffix)])
                    break
        cached = frozenset(names)
        _PHASE_HOOKS_BY_CLASS[cls] = cached
    return cached


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
        # id() of every currently-registered listener. `CombatState.
        # IterateHookListeners` (CombatState.cs:482-488) yields an item only
        # `if (Contains(item))`, evaluated as the enumeration reaches it — so a
        # listener unregistered by an earlier listener in the SAME dispatch is
        # skipped. A membership set keeps that check O(1) on the dispatch path.
        self._live: set[int] = set()
        # Back-reference to the owning CombatState; set by CombatState.__init__.
        # Lets powers reach combat-level state (e.g. Infested spawning Wrigglers).
        self.combat: Any = None
        # Derived-order cache; see _ordered(). `_epoch` counts membership
        # changes, so the key changes whenever the list or the enemy order does.
        self._epoch = 0
        self._order_key: Any = None
        self._order: list[Any] = []
        # Base hook names for which some current listener declares a phase
        # variant; see _each().
        self._phased: frozenset[str] = frozenset()
        # AttackCommand.Results for the attack currently being executed: a list
        # of (receiver, unblocked_damage) appended by DamageCmd.deal between
        # before_attack and after_attack, or None outside an attack. Suck and
        # Painful Stabs both read `command.Results` and cannot be expressed
        # without it (SuckPower.cs:28-41, PainfulStabsPower.cs:40-44).
        self._attack_results: list | None = None

    def register(self, listener: Any) -> None:
        self._listeners.append(listener)
        self._live.add(id(listener))
        self._epoch += 1

    def unregister(self, listener: Any) -> None:
        self._listeners.remove(listener)
        # `_listeners` can legitimately hold the same object twice; only drop
        # the liveness mark when the last copy goes.
        if not any(l is listener for l in self._listeners):
            self._live.discard(id(listener))
        self._epoch += 1

    # ── Dispatch order and phases ────────────────────────────────────────

    def _ordered(self) -> list[Any]:
        """The listener list in the game's dispatch order.

        `CombatState.IterateHookListeners` (CombatState.cs:410-493) builds no
        list: it re-derives the listeners per dispatch from the creatures
        themselves, allies before enemies, and within a player walks Powers
        (416) -> Relics (428-435) -> PotionSlots (436-443) -> Orbs (448) ->
        the cards of AllPiles (449-467). `self._listeners` is registration
        order, which is close to the mirror image of that — relics are appended
        at combat setup and a power joins only when applied, so relics always
        ran first where the game runs powers first.

        This sorts registration order into the derived one. The sort is stable,
        so listeners tied on (creature, category) keep the order they
        registered in — which is what keeps an enchantment immediately after
        its own card. `CombatHistory` is a sim-only listener with no C#
        counterpart (note N3) and stays first, ahead of the creature walk, so
        an entry exists by the time anything reacts to it.

        Re-deriving per dispatch would be the literal port; instead the result
        is cached and invalidated whenever the listener list or the enemy order
        changes, which are the only two inputs.
        """
        enemies = getattr(self.combat, "enemies", None) or ()
        key = (self._epoch, tuple(id(e) for e in enemies))
        if key == self._order_key:
            return self._order

        # Ally side first (the sim has exactly one ally, the player), then the
        # enemies in combat-list order.
        rank = {id(e): i + 1 for i, e in enumerate(enemies)}

        def sort_key(item):
            i, l = item
            owner = getattr(l, "owner", None)
            return (rank.get(id(owner), 0) if owner is not None else 0,
                    getattr(l, "hook_category", _CAT_CARD), i)

        self._order = [l for _, l in
                       sorted(enumerate(self._listeners), key=sort_key)]
        self._order_key = key
        self._phased = frozenset().union(
            *(_phase_hooks(type(l)) for l in self._listeners)
        ) if self._listeners else frozenset()
        return self._order

    @property
    def combat_is_over(self) -> bool:
        """`CombatManager.IsOverOrEnding` — the predicate
        `Hook.IterateCombatHookListeners` gates on.

        The sim has one flag where C# has two states (`IsEnding` while the
        ending sequence runs, `IsOver` after it): `CombatState.phase` is set to
        `Phase.COMBAT_OVER` in `_end_combat`, which is the moment the ending
        begins, so it covers both. Outside a combat (a bare HookSystem, or a
        run-level listener walk) there is no phase and the gate is inert.
        """
        combat = self.combat
        if combat is None:
            return False
        from .combat import Phase

        # `getattr`, because CombatState back-references itself here early in
        # __init__ and only assigns `phase` further down — so combat SETUP
        # dispatches (encounter build, on_combat_start) find no phase at all.
        # That is `IsStarting`, the guard's own exemption, for free.
        return getattr(combat, "phase", None) == Phase.COMBAT_OVER

    def _each(self, hook: str):
        """Yield (listener, bound method) for every listener implementing
        `hook`, in `_ordered()` order.

        24 of Hook.cs's 147 dispatchers run 2-4 *complete* listener passes and
        AbstractModel.cs declares 27 phase-suffixed hooks: a VeryEarly pass,
        then Early, then the plain one, then Late, each re-enumerating the
        whole listener list. A listener opts into a pass by defining
        `<hook>_very_early` / `<hook>_early` / `<hook>_late` alongside (or
        instead of) `<hook>`.

        The passes only run for hooks some current listener actually phases —
        `_phased` is recomputed with the order cache — so the common case stays
        a single walk.

        For a hook in `_COMBAT_GATED_HOOKS` this yields NOTHING once the combat
        is over — `Hook.IterateCombatHookListeners`' `if (IsOverOrEnding &&
        !IsStarting) yield break` (Hook.cs:55-58). Both are generators, so the
        test lands at enumeration start in both: a dispatch that began while the
        combat was live still reaches every listener even if one of them ends it.
        """
        if hook in _COMBAT_GATED_HOOKS and self.combat_is_over:
            return
        # `_phased` is refreshed as a side effect of `_ordered()`, so it has to
        # be current before the branch below reads it.
        self._ordered()
        live = self._live
        if hook in self._phased:
            for suffix in _PHASES:
                name = hook + suffix
                # Each pass is its own IterateCombatHookListeners call in C#
                # (Hook.cs:204 and :212 for AfterCardDrawn, :1580 and :1584 for
                # ModifyEnergyCostInCombat), so `_ordered()` is re-read per
                # pass: a listener registered by an earlier pass is visible to
                # a later one. Binding it once meant the plain pass could not
                # see what the VeryEarly pass had added.
                for l in self._ordered():
                    if id(l) not in live:
                        continue
                    fn = getattr(l, name, None)
                    if fn is not None:
                        yield l, fn
            return
        for l in self._ordered():
            if id(l) not in live:
                continue
            fn = getattr(l, hook, None)
            if fn is not None:
                yield l, fn

    # ── Modifier hooks — damage ──────────────────────────────────────────
    # Pipeline: base + additive → × multiplicative → cap → block → modify_hp_lost → apply

    def modify_damage_additive(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None = None,
        card: Card | None = None,
        modifiers: list | None = None,
        props: ValueProp = ValueProp.NONE,
    ) -> int:
        """Fold every flat damage bonus into the running amount, in order, and
        return the NEW amount (e.g. Strength +N, Pen Nib +1).

        A chain, not a parallel sum: `ModifyDamageInternal` (Hook.cs:2515-2526)
        runs

            num2 = item.ModifyDamageAdditive(target, num, props, dealer, card);
            num += num2;

        so each listener is handed what the previous ones produced. The sim used
        to hand every listener the pre-step base and return the SUM of the
        deltas, which the caller added to the base.

        Over the listeners the game actually ships the two shapes agree, and
        that is an enumeration rather than an argument: all 13 overrides of
        ModifyDamageAdditive / ModifyBlockAdditive in the decompiled source
        (Accuracy, Calcify, Dexterity, Fasten, Leadership, PhantomBlades,
        Strength, Tainted, Vigor, FakeStrikeDummy, MiniatureCannon,
        MysticLighter, StrikeDummy) ignore the `amount`/`block` parameter
        entirely — each one either returns `0m` from a guard or returns a
        constant (`base.Amount`, or a DynamicVar). So no shipped listener can
        witness the difference, which is why relic/fake_strike_dummy's ordering
        note was dormant. It is a chain here anyway, because that is the
        contract a listener is entitled to and the next ported additive listener
        should not have to rediscover it.

        `modifiers` mirrors `out modifiers`: every listener whose delta was not
        zero (`if (num2 != 0m) list.Add(item)`), for
        `after_modify_damage_amount`.
        """
        for l, fn in self._each("modify_damage_additive"):
            delta = fn(target, amount, dealer, card, props)
            amount += delta
            if modifiers is not None and delta != 0:
                modifiers.append(l)
        return amount

    def modify_damage_multiplicative(
        self,
        target: Creature,
        amount: float,
        dealer: Creature | None = None,
        card: Card | None = None,
        modifiers: list | None = None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        """Fold every damage multiplier into the running amount, in order, and
        return the new amount (e.g. Vulnerable ×1.5, Weak ×0.75).

        This is a *chain*, not a product. `ModifyDamageInternal`
        (Hook.cs:2515-2538) runs `num *= item.ModifyDamageMultiplicative(...)`
        per listener over a running `decimal`, so each listener sees — and
        multiplies — what the previous one produced. Taking the product of
        every factor and applying it once is a different number: Shrink (×0.7)
        plus Vulnerable (×1.5) on 20 damage is `20*1.5 = 30`, `30*0.7 = 21` in
        the game, where the product form computes `1.5*0.7 = 1.0499999999999998`
        and `int(20 * that) = 20`.

        `modifiers` mirrors the `out modifiers` list: every listener whose
        factor was not exactly 1 is appended, so the caller can notify them via
        `after_modify_damage_amount`.
        """
        for l, fn in self._each("modify_damage_multiplicative"):
            factor = fn(target, amount, dealer, card, props)
            amount *= factor
            if modifiers is not None and factor != 1:
                modifiers.append(l)
        return amount

    def after_modify_damage_amount(self, modifiers: list, target: Creature) -> None:
        """Notify the listeners that actually changed a damage amount (mirrors
        Hook.AfterModifyingDamageAmount)."""
        for l in modifiers:
            fn = getattr(l, "after_modify_damage_amount", None)
            if fn is not None:
                fn(target)

    def modify_damage_cap(
        self,
        target: Creature,
        dealer: Creature | None = None,
        card: Card | None = None,
    ) -> int | None:
        """Minimum cap returned by any listener, or None for no cap."""
        cap: int | None = None
        for l, fn in self._each("modify_damage_cap"):
            c = fn(target, dealer, card)
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
        modifiers: list | None = None,
        props: ValueProp = ValueProp.NONE,
    ) -> int:
        """Fold every flat block bonus into the running amount and return the new
        amount (e.g. Dexterity +N per Defend) — a chain, exactly as `ModifyBlock`
        does it (`num += item.ModifyBlockAdditive(target, num, ...)`,
        Hook.cs:1310-1340). See `modify_damage_additive` for why the shape
        matters and why no shipped listener can witness it.

        `modifiers` mirrors `out modifiers`: every listener whose delta was
        non-zero, for `after_modify_block_amount`.
        """
        for l, fn in self._each("modify_block_additive"):
            delta = fn(target, amount, card, props)
            amount += delta
            if modifiers is not None and delta != 0:
                modifiers.append(l)
        return amount

    def modify_block_multiplicative(
        self,
        target: Creature,
        amount: float,
        card: Card | None = None,
        modifiers: list | None = None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        """Fold every block multiplier into the running amount and return the
        new amount (e.g. Frail ×0.75) — a chain, not a product, exactly as
        `ModifyBlock` does it (`num *= item2.ModifyBlockMultiplicative(...)`,
        Hook.cs:1310-1340). See `modify_damage_multiplicative`."""
        for l, fn in self._each("modify_block_multiplicative"):
            factor = fn(target, amount, card, props)
            amount *= factor
            if modifiers is not None and factor != 1:
                modifiers.append(l)
        return amount

    def after_modify_block_amount(self, modifiers: list, target: Creature,
                                  amount: int, card: Card | None = None) -> None:
        """Notify the listeners that actually changed a block amount (mirrors
        Hook.AfterModifyingBlockAmount, Hook.cs:649-657).

        C#'s three implementers are all ported — Vambrace.cs:82-95,
        PaelsLegion.cs:155-169 and FastenPower.cs:37-41 — and each needs to
        know it was an *active* modifier of this particular gain, which is what
        the `modifiers` list carries and what a plain `on_block_gained` cannot.

        `amount` is C#'s `modifiedBlock`: two of the three listeners open on
        `if (modifiedAmount <= 0m) return;`, so they need the value, and
        CreatureCmd.cs:646 hands it to them BEFORE `GainBlockInternal` — the
        dispatch is not a notification that block landed.
        """
        for l in modifiers:
            fn = getattr(l, "after_modify_block_amount", None)
            if fn is not None:
                fn(target, amount, card)

    # ── Modifier hooks — HP loss ─────────────────────────────────────────

    def modify_hp_lost(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None = None,
        card: Card | None = None,
        modifiers: list | None = None,
    ) -> int:
        """Chain-modify HP loss after block absorption (e.g. Torii: cap at 1, Tungsten Rod: -1).

        `modifiers` mirrors Hook.ModifyHpLost's `out modifiers`: when a list is
        passed, every listener that actually changed the amount is appended to
        it, so the caller can notify them via `after_modify_hp_lost`. Pure-read
        callers (previews.py) pass nothing and so notify nobody.
        """
        for l, fn in self._each("modify_hp_lost"):
            before = amount
            amount = fn(target, amount, dealer, card)
            if modifiers is not None and amount != before:
                modifiers.append(l)
        return max(0, amount)

    def after_modify_hp_lost(self, modifiers: list, target: Creature) -> None:
        """Notify the listeners that changed an HP-loss amount (mirrors
        Hook.AfterModifyingHpLostAfterOsty — Buffer decrements here)."""
        for l in modifiers:
            if hasattr(l, "after_modify_hp_lost"):
                l.after_modify_hp_lost(target)

    # ── Modifier hooks — misc ────────────────────────────────────────────

    def modify_strength_given(
        self,
        target: Creature,
        amount: int,
        card: Card | None = None,
    ) -> int:
        """Chain-modify strength gain."""
        for l, fn in self._each("modify_strength_given"):
            amount = fn(target, amount, card)
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
        for l, fn in self._each("modify_power_amount"):
            amount = fn(power_cls, target, amount, applier)
        return amount

    def modify_vulnerable_multiplier(
        self, dealer: Creature | None, mult: float
    ) -> float:
        """Chain-modify the Vulnerable damage multiplier (mirrors
        ModifyVulnerableMultiplier; e.g. Paper Phrog adds +0.25). Consulted by
        VulnerablePower — stateless, so it is preview-safe."""
        for l, fn in self._each("modify_vulnerable_multiplier"):
            mult = fn(dealer, mult)
        return mult

    def modify_card_energy_cost(self, card: Card, cost: int) -> int:
        """Chain-modify a card's energy cost for this play (e.g. Apotheosis, Nightmare)."""
        for l, fn in self._each("modify_card_energy_cost"):
            cost = fn(card, cost)
        return max(0, cost)

    def modify_max_energy(self, player: PlayerCombatState, amount: int) -> int:
        """Chain-modify base energy gained at turn start (e.g. Ectoplasm -1)."""
        for l, fn in self._each("modify_max_energy"):
            amount = fn(player, amount)
        return max(0, amount)

    def modify_energy_gain(self, player: PlayerCombatState, amount: int) -> int:
        """Chain-modify bonus energy gained mid-turn from cards or effects."""
        for l, fn in self._each("modify_energy_gain"):
            amount = fn(player, amount)
        return max(0, amount)

    def modify_hand_draw(self, player: PlayerCombatState, count: int) -> int:
        """Chain-modify how many cards are drawn at turn start."""
        for l, fn in self._each("modify_hand_draw"):
            count = fn(player, count)
        return max(0, count)

    def modify_card_play_count(
        self,
        card: Card,
        target: Creature | None,
        count: int,
    ) -> int:
        """Chain-modify how many times a card is played (e.g. Burst, Corruption)."""
        for l, fn in self._each("modify_card_play_count"):
            count = fn(card, target, count)
        return max(1, count)

    def modify_card_play_result_pile(self, card: Card, pile: str) -> str:
        """Chain-modify where a played card ends up once its play resolves
        (mirrors ModifyCardPlayResultPileTypeAndPosition). pile is "discard"
        by default; a listener may return "draw_top" to put the card on top
        of the draw pile instead (Nostalgia). Consulted only for cards that
        would land in the discard pile (exhausted cards and Powers never
        reach it)."""
        for l, fn in self._each("modify_card_play_result_pile"):
            pile = fn(card, pile)
        return pile

    def modify_orb_value(self, player: PlayerCombatState, value: int) -> int:
        """Chain-modify orb passive/evoke value (e.g. Defect relic bonuses)."""
        for l, fn in self._each("modify_orb_value"):
            value = fn(player, value)
        return value

    def modify_x_value(self, card: Card, value: int) -> int:
        """Chain-modify the X captured when an X-cost card is played (mirrors
        ModifyXValue, e.g. Chemical X +2)."""
        for l, fn in self._each("modify_x_value"):
            value = fn(card, value)
        return max(0, value)

    # ── Event hooks — combat lifecycle ───────────────────────────────────

    def on_combat_start(self) -> None:
        """Fires after combat state is initialised, before the first player turn."""
        for l, fn in self._each("on_combat_start"):
            fn()

    def on_combat_end(self) -> None:
        """`Hook.AfterCombatEnd` (Hook.cs:328-335) — ONE pass, and only on the
        victory path: `EndCombatInternal` fires it at CombatManager.cs:988,
        while `ProcessPendingLoss` (:956-965) fires nothing at all. Hence no
        `player_won` argument: there is no losing dispatch to distinguish."""
        for l, fn in self._each("on_combat_end"):
            fn()

    def on_combat_victory(self) -> None:
        """`Hook.AfterCombatVictory` (Hook.cs:340-352) — TWO complete passes,
        `AfterCombatVictoryEarly` over every listener then `AfterCombatVictory`
        over every listener, which the `_early` suffix walk gives for free.
        Fired at CombatManager.cs:999, strictly after Hook.AfterCombatEnd."""
        for l, fn in self._each("on_combat_victory"):
            fn()

    # ── Event hooks — player turn lifecycle ──────────────────────────────

    def before_side_turn_start(self, player: PlayerCombatState) -> None:
        """`Hook.BeforeSideTurnStart` — CombatManager.cs:458.

        The FIRST hook of a side's turn: after each participant's
        `Creature.BeforeTurnStart` and before everything else the turn does —
        before the enemies' next-move roll (:478-484), before the block clear
        (`Creature.AfterTurnStart`, :492-499) and long before `SetupPlayerTurn`.
        Bag of Marbles, Red Mask, Kunai, Shuriken, Orichalcum and the round-1
        arm of PlatingPower all live here, and the sim used to run them at one
        of the two post-energy slots instead.

        The PLAYER side's leg. The enemy side's is `before_enemy_side_start`,
        which is the same C# hook dispatched for the other side.
        """
        for l, fn in self._each("before_side_turn_start"):
            fn(player)

    def on_player_turn_start(self, player: PlayerCombatState) -> None:
        """`Hook.BeforeHandDraw` — inside SetupPlayerTurn (CombatManager.cs:653),
        after `Hook.AfterEnergyReset` and before `ModifyHandDraw` and the draw.

        The name predates the audit; the slot is BeforeHandDraw's and always
        was. Toolbox, Jeweled Mask, Blessed Antler and Hello World live here.
        """
        for l, fn in self._each("on_player_turn_start"):
            fn(player)

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        """`Hook.AfterPlayerTurnStart` — CombatManager.cs:675, the LAST line of
        SetupPlayerTurn, so it runs after that player's hand draw and once per
        player.

        This used to double as the player-side `Hook.AfterSideTurnStart`, which
        is a different hook at a different point (:522, after every player's
        SetupPlayerTurn) with a different, larger population — 18 of the
        listeners parked here were really that one. See `after_side_turn_start`.
        Bellows, Pendulum, Gambling Chip and Choices Paradox are genuinely
        AfterPlayerTurnStart; Blood Vial and Fake Blood Vial are its LATE pass
        (`on_player_turn_started_late`).
        """
        for l, fn in self._each("on_player_turn_started"):
            fn(player)

    def after_side_turn_start(self, player: PlayerCombatState) -> None:
        """`Hook.AfterSideTurnStart` — CombatManager.cs:522.

        Fired once for the whole side AFTER every `SetupPlayerTurn` has
        finished, and so after `Hook.AfterPlayerTurnStart`; the orb queue and
        then `PlayerTurnPhase.AutoPrePlay` (:556-572) follow it. This is where
        most of the turn-start content actually lives — Akabeko, Lantern,
        Happy Flower, Crossbow, Sai, Seal of Gold, Demon Form, Poison, Rampart.

        The PLAYER side's leg; the enemy side's is `after_enemy_side_start`.
        """
        for l, fn in self._each("after_side_turn_start"):
            fn(player)

    def after_auto_pre_play_phase_entered(self, player: PlayerCombatState) -> None:
        """Hook.AfterAutoPrePlayPhaseEntered — CombatManager.cs:556-572 gives
        start-of-turn auto-plays their OWN phase, entered strictly after
        Hook.AfterSideTurnStart and the orb queue. The sim had no such phase and
        hand-rolled its implementers onto neighbouring slots."""
        for l, fn in self._each("after_auto_pre_play_phase_entered"):
            fn(player)

    def after_auto_post_play_phase_entered(self, player: PlayerCombatState) -> None:
        """Hook.AfterAutoPostPlayPhaseEntered — CombatManager.cs:1160-1176
        enters PlayerTurnPhase.AutoPostPlay, drains the auto-plays, sets
        Phase = End, and only THEN fires Hook.BeforeTurnEnd. Making it a real
        step rather than a listener is what stops the answer depending on
        registration order: Stampede's auto-plays always precede Cloak Clasp's
        hand count, whichever category each happens to be."""
        for l, fn in self._each("after_auto_post_play_phase_entered"):
            fn(player)

    def on_player_turn_end(self, player: PlayerCombatState) -> None:
        """Fires at the end of the player's turn, before the hand is discarded."""
        for l, fn in self._each("on_player_turn_end"):
            fn(player)

    def after_player_turn_end(self, player: PlayerCombatState) -> None:
        """Hook.AfterTurnEnd for the player side (CombatManager.cs:1307) —
        fires AFTER the turn-end card effects and the hand flush, so block a
        turn-end effect just added (Plating) is already on the player. Distinct
        from `on_player_turn_end`, which is Hook.BeforeTurnEnd."""
        for l, fn in self._each("after_player_turn_end"):
            fn(player)

    def on_energy_reset(self, player: PlayerCombatState) -> None:
        """Fires immediately after energy is set at turn start."""
        for l, fn in self._each("on_energy_reset"):
            fn(player)

    def on_energy_spent(self, card: Card, amount: int) -> None:
        """Fires when energy is consumed to play a card."""
        for l, fn in self._each("on_energy_spent"):
            fn(card, amount)

    # ── Event hooks — enemy turn lifecycle ───────────────────────────────

    def before_enemy_side_start(self) -> None:
        """`Hook.BeforeSideTurnStart` for the ENEMY side — CombatManager.cs:458.

        The same hook as `before_side_turn_start`, dispatched for the other
        side. C# has ONE hook taking `(state, side, participants)` and every
        implementer opens by testing `side` or `participants.Contains(Owner)`;
        the sim splits it per side, as it already did for `Hook.AfterTurnEnd`
        (`after_player_turn_end` / `on_enemy_side_end`). The split is
        behaviour-preserving because the two sides never start a turn at the
        same moment, so there is no cross-side order to lose.

        Fires ONCE for the whole side, before any block is cleared and long
        before any enemy moves. HardenedShellPower's per-turn damage counter
        (HardenedShellPower.cs:71, which has no participants filter at all)
        lives here.
        """
        for l, fn in self._each("before_enemy_side_start"):
            fn()

    def after_enemy_side_start(self) -> None:
        """`Hook.AfterSideTurnStart` for the ENEMY side — CombatManager.cs:522.

        Fires ONCE, after the block-clear and AfterBlockCleared passes have
        completed for every enemy and before ExecuteEnemyTurn walks them for
        their moves — so Poison has already ticked on enemy 3 by the time
        enemy 1 attacks. Poison, Demon Form, Slow and the Plating decay live
        here; Sandpit's countdown is the `_late` pass
        (`after_enemy_side_start_late`, SandpitPower.cs:70).
        """
        for l, fn in self._each("after_enemy_side_start"):
            fn()

    def before_enemy_side_end(self) -> None:
        """`Hook.BeforeTurnEnd` for the ENEMY side — CombatManager.cs:1251, the
        first line of EndEnemyTurnInternal, once for the whole side after every
        enemy has moved.

        The player-side counterpart is `on_player_turn_end`. Two ported powers
        need the sub-phases this dispatcher gets from `_each`: AsleepPower
        drops its owner's Plating in `_very_early` (AsleepPower.cs:38) and
        PlatingPower grants its block in `_early` (PlatingPower.cs:61, "We do
        this in early so that it triggers before end-of-turn damage effects"),
        so on the last sleeping turn the Plating is gone before it can grant.
        """
        for l, fn in self._each("before_enemy_side_end"):
            fn()

    def on_enemy_side_end(self) -> None:
        """`Hook.AfterTurnEnd` for the ENEMY side — CombatManager.cs:1256, once
        after ALL enemies have taken their turns for the round.

        `AbstractModel.AfterSideTurnEnd` (Hook.cs:1267-1292) is dispatched from
        here, so every ported implementation of it belongs on this slot:
        Regen, Ritual, Hatch, Slumber, Escape Artist, Asleep and the Battleworn
        Dummy's time limit all used to sit on a per-enemy slot instead.
        """
        for l, fn in self._each("on_enemy_side_end"):
            fn()

    def before_attack(self, dealer: Creature, card: Card | None = None) -> None:
        """Fires before an attack command's hits — a monster attack move or a
        player Attack-card play (mirrors Hook.BeforeAttack(AttackCommand),
        which fires for every AttackCommand.Execute(), card- or monster-
        sourced alike; AttackCommand.cs).

        card is the source card for a player attack (mirrors AttackCommand.
        ModelSource / FromCard), None for a monster attack (FromMonster never
        sets ModelSource). Consulted by VigorPower to no-op on an unpowered
        attack (mirrors VigorPower.cs BeforeAttack's
        `if (!command.DamageProps.IsPoweredAttack()) return;` — no real
        Attack card is unpowered today, but Vigor must not be worth tracking
        one that is)."""
        self._attack_results = []
        for l, fn in self._each("before_attack"):
            fn(dealer, card)

    def after_attack(self, dealer: Creature, card: Card | None = None) -> None:
        """Fires after an attack command's last hit (mirrors Hook.AfterAttack);
        powers that boost "the next attack" (Vigor) consume their stacks here.

        card mirrors before_attack's card param (AttackCommand.ModelSource).

        `results` is AttackCommand.Results — the (receiver, unblocked_damage)
        pairs this attack produced, accumulated by DamageCmd.deal. Listeners
        that only care that an attack ended ignore it."""
        results = self._attack_results or []
        self._attack_results = None
        for l, fn in self._each("after_attack"):
            fn(dealer, card, results)

    # ── Event hooks — card lifecycle ─────────────────────────────────────

    def before_card_played(self, card: Card, target: Creature | None = None) -> None:
        """Fires before a card's on_play() resolves (mirrors BeforeCardPlayed).
        Used by relics that must act on the card before its effects (e.g. Pen
        Nib marking the 10th Attack for doubling).

        target is the single creature the card was played at (mirrors
        CardPlay.Target) — set only for a resolved single-enemy target, None
        for untargeted/AoE plays. Consulted by SurroundedPower to flip Kaiser
        Crab facing on any targeted card play, not just damaging ones."""
        for l, fn in self._each("before_card_played"):
            fn(card, target)

    def on_card_played(self, card: Card, is_auto_play: bool = False) -> None:
        """Fires after a card's on_play() resolves.

        `is_auto_play` is CardPlay.IsAutoPlay — the flag Brilliant Scarf and
        Pael's Eye both read and the sim's play path did not carry."""
        for l, fn in self._each("on_card_played"):
            fn(card, is_auto_play)

    def on_card_drawn(self, card: Card, from_hand_draw: bool = False) -> None:
        """Fires each time a card enters the hand from the draw pile.

        from_hand_draw is True only for the initial hand draw at the start of
        the player's turn; False for all mid-turn draws (card effects, powers).
        Mirrors STS2's AfterCardDrawn / AfterCardDrawnEarly fromHandDraw param.
        """
        for l, fn in self._each("on_card_drawn"):
            fn(card, from_hand_draw)

    def on_card_entered_combat(self, card: Card) -> None:
        """Fires when a card is created mid-combat (e.g. Slimed, Dazed, Wound
        added by an enemy). Lets active powers afflict it (Ringing, Tangled)."""
        for l, fn in self._each("on_card_entered_combat"):
            fn(card)

    def after_card_changed_piles(self, card: Card, pile: str,
                                 cloned_by: Any = None) -> None:
        """Hook.AfterCardChangedPiles (Hook.cs:167-179).

        Two COMPLETE passes, plain then Late, which `_each` gives us because
        `AfterCardChangedPilesLate` is a declared phase; SoulFysh.cs:91-108 is
        the game's only Late implementer.

        `pile` is the sim's pile name ("hand", "draw", "discard", "exhaust",
        "deck", "play"). C# calls the parameter `oldPileType`, but that name is
        only accurate at the Add site (CardPileCmd.cs:635 passes
        `oldPile?.Type ?? None`): the transform site passes the pile the
        replacement was just placed IN (CardCmd.cs:447 `pile2.Type`). No ported
        listener reads the argument at all — all four read `card.Pile.Type`
        instead (BingBong.cs:31, BookOfFiveRings.cs:84, DarkstonePeriapt.cs:19,
        LuckyFysh.cs:27) — so the value is passed through as the game passes it
        rather than reconciled.

        Dispatched from the combat-pile transform only. The DECK-pile leg lives
        on the run, where `Relic.after_card_added_to_deck` is this same hook
        filtered to `pile.Type == PileType.Deck` (the filter every ported
        listener applies itself); the remaining C# sites — Add, RemoveFromCombat
        and the manual play — are seam/creature_card_cmds guard G8 and still
        dispatch nothing.
        """
        for l, fn in self._each("after_card_changed_piles"):
            fn(card, pile, cloned_by)

    def on_card_discarded(self, card: Card) -> None:
        """Fires when a card is discarded at end of turn (not when played)."""
        for l, fn in self._each("on_card_discarded"):
            fn(card)

    def on_card_exhausted(self, card: Card,
                          caused_by_ethereal: bool = False) -> None:
        """Hook.AfterCardExhausted (Hook.cs:237-242, dispatched from
        CardCmd.cs:237-244).

        The CAUSE is a parameter, not a property of the card:
        `causedByEthereal: true` is passed from exactly two sites in the whole
        game, both at turn end (CombatManager.cs:1240 and CardModel.cs:1692).
        Joss Paper branches on it (JossPaper.cs:102-114); the sim branched on
        `card.is_ethereal` instead, so an Ethereal card exhausted MID-TURN was
        booked to the deferred pile and its credit withheld until the flush,
        where the game credits it at once.
        """
        for l, fn in self._each("on_card_exhausted"):
            fn(card, caused_by_ethereal)

    def on_card_retained(self, card: Card) -> None:
        """Fires when a card stays in hand past the end of a turn."""
        for l, fn in self._each("on_card_retained"):
            fn(card)

    def on_hand_emptied(self, player: PlayerCombatState) -> None:
        """Fires after the hand has been fully discarded at end of turn."""
        for l, fn in self._each("on_hand_emptied"):
            fn(player)

    def modify_shuffle_order(self, player: PlayerCombatState, cards: list,
                             is_initial_shuffle: bool) -> None:
        """`Hook.ModifyShuffleOrder` (Hook.cs:2004-2010) — NOT a notification.

        The listeners are handed the shuffled list itself and mutate it in place,
        which is how Perfect Fit puts its card on top (`Remove` + `Insert(0)`,
        PerfectFit.cs:10-16). Two dispatch sites, both AFTER the Fisher-Yates and
        BEFORE the pile is repopulated: `CardPileCmd.cs:877` (the mid-combat
        shuffle, `isInitialShuffle: false`) and `CardPile.cs:73`
        (RandomizeOrderInternal at combat start, `isInitialShuffle: true`).

        The sim used to stand this in with `on_shuffle` = Hook.AfterShuffle, a
        DIFFERENT hook fired at CardPileCmd.cs:917 after the pile is rebuilt. The
        substitution worked for a lone enchanted card and broke for two: which of
        two competing listeners lands its card on top is decided by DISPATCH
        ORDER, and `_ordered()`'s key is registration index, so a mid-combat copy
        always won. C# re-derives its listeners per dispatch from the piles
        (CombatState.cs:449-467, the enchantment added at :462-465), and at
        CardPileCmd.cs:877 the DISCARD pile still holds all of its cards (only
        drawPile entries are removed, :878-881) — so the card sitting LATER IN THE
        DISCARD fires last and ends on top. Hence the per-hook ordering below,
        which is the one place in the sim where a hook does not use `_each`.

        `cards` is in the sim's own orientation (top at the END), so a listener
        that wants the top appends where C# inserts at 0.
        """
        combat = getattr(self, "combat", None)
        if combat is not None and getattr(combat, "is_over_or_ending", False):
            return
        # `AllPiles` order (PlayerCombatState.cs:70-79): Hand, Draw, Discard,
        # Exhaust. A listener whose card is in none of them (the card currently
        # mid-OnPlay, i.e. PileType.Play) sorts last, as it does in C#.
        position: dict[int, int] = {}
        for i, card in enumerate(player.all_cards):
            position[id(card)] = i
        last = len(position)

        def pile_key(item):
            i, listener = item
            card = getattr(listener, "card", None)
            if card is None:
                card = listener if hasattr(listener, "id") else None
            return (position.get(id(card), last), i)

        listeners = [l for _, l in sorted(enumerate(self._listeners),
                                          key=pile_key)]
        for listener in listeners:
            fn = getattr(listener, "modify_shuffle_order", None)
            if fn is not None:
                fn(player, cards, is_initial_shuffle)

    def on_shuffle(self, player: PlayerCombatState) -> None:
        """Fires when the discard pile is shuffled back into the draw pile."""
        for l, fn in self._each("on_shuffle"):
            fn(player)

    # ── Event hooks — damage / block / HP ────────────────────────────────

    def on_attacked(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None = None,
        card: Card | None = None,
    ) -> None:
        """Fires when a hit connects (post-modifier, pre-block). amount > 0 guaranteed."""
        for l, fn in self._each("on_attacked"):
            fn(target, amount, dealer, card)

    def before_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None = None,
        card: Card | None = None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        """Hook.BeforeDamageReceived — fired at CreatureCmd.cs:263, after the
        modifier passes and **before** block absorption.

        Unlike `on_damage_received` this is NOT subject to the killing-blow
        skip (CreatureCmd.cs:392's `!WasTargetKilled || !IsDead`), because it
        runs before any HP is lost. That is the whole of `damage_pipeline/G1`:
        Thorns lives here in C# (ThornsPower.cs:17-24), so a 99-damage Strike
        into a 3-HP Thorns-5 enemy costs the attacker 5, where hanging Thorns
        on the sim's AfterDamageReceived cost it 0.
        """
        for l, fn in self._each("before_damage_received"):
            fn(target, amount, dealer, card, props)

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
        for l, fn in self._each("on_damage_received"):
            fn(target, amount, dealer, card, props)

    def on_damage_dealt(
        self,
        dealer: Creature,
        target: Creature,
        amount: int,
        card: Card | None = None,
    ) -> None:
        """Fires after a creature deals damage (e.g. Thorns reflection, lifesteal)."""
        for l, fn in self._each("on_damage_dealt"):
            fn(dealer, target, amount, card)

    def on_block_gained(
        self, target: Creature, amount: int, card: Card | None = None
    ) -> None:
        """Fires after block is added to a creature. `card` is the source card
        when the block came from a card play (None for powers/potions/relics)."""
        for l, fn in self._each("on_block_gained"):
            fn(target, amount, card)

    def on_block_broken(self, target: Creature, dealer: Creature | None = None,
                        card: Card | None = None) -> None:
        """Fires when damage consumes the target's remaining block (mirrors
        DamageResult.WasBlockBroken: Block <= 0 && blockedDamage > 0 — an
        exact break counts, overflow is not required). dealer/card identify
        the damage source (Hand Drill checks dealer == its owner)."""
        for l, fn in self._each("on_block_broken"):
            fn(target, dealer, card)

    def on_block_cleared(self, target: Creature) -> None:
        """Fires when block is wiped at the start of a turn."""
        for l, fn in self._each("on_block_cleared"):
            fn(target)

    def on_hp_changed(self, target: Creature, delta: int) -> None:
        """Fires whenever a creature's HP changes (delta is negative for damage)."""
        for l, fn in self._each("on_hp_changed"):
            fn(target, delta)

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
        for l, fn in self._each("on_power_applied"):
            fn(name, target, amount, applier)

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
        for l, fn in self._each("on_power_amount_changed"):
            fn(name, target, delta, applier)

    # ── Event hooks — creatures entering / leaving combat ───────────────

    def on_creature_added(self, creature: Creature) -> None:
        """Fires when a creature joins combat mid-fight (mirrors AfterCreatureAddedToCombat)."""
        for l, fn in self._each("on_creature_added"):
            fn(creature)

    def on_creature_escaped(self, creature: Creature) -> None:
        """Fires when a creature escapes from combat alive."""
        for l, fn in self._each("on_creature_escaped"):
            fn(creature)

    def on_stunned(self, creature: Creature) -> None:
        """Fires when a creature is stunned (will skip its next turn)."""
        for l, fn in self._each("on_stunned"):
            fn(creature)

    # ── Event hooks — potions ────────────────────────────────────────────

    def before_potion_used(self, potion: Any, target: Creature | None) -> None:
        """Hook.BeforePotionUsed — PotionModel.cs:297, fired by OnUseWrapper
        BEFORE the effect resolves.

        `SurroundedPower.cs:82` is the source's ONLY implementer. The sim had
        one potion hook where C# has two, so the Kaiser Crab's facing flip ran
        a phase late: a Fire Potion into a 1-HP Crusher left the sim facing
        left (x1.5) where the game faces right (x1.0) — 80 -> 44 HP versus
        80 -> 56 on the next Precision Beam.
        """
        for l, fn in self._each("before_potion_used"):
            fn(potion, target)

    def on_potion_used(self, potion: Any, target: Creature | None) -> None:
        """Fires after a potion's effect resolves (mirrors AfterPotionUsed)."""
        for l, fn in self._each("on_potion_used"):
            fn(potion, target)

    # ── Event hooks — death ──────────────────────────────────────────────

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        """Hook.AfterDeath — fires on BOTH C# branches, to EVERY listener.

        `CreatureCmd.cs:519` dispatches it with `wasRemovalPrevented: false` on
        the real-death arm and `CreatureCmd.cs:566` with `true` on the
        prevented one. The sim used to fire it only on the real-death arm,
        which is why `GremlinHorn.cs:24-32` — whose only test is
        `target.Side != Owner.Creature.Side`, with no `wasRemovalPrevented`
        guard — never paid its +1 energy and 1 card on a prevented death.
        """
        for l, fn in self._each("on_death"):
            fn(creature, was_removal_prevented)

    def should_stop_combat_from_ending(self) -> bool:
        """Hook.ShouldStopCombatFromEnding (Hook.cs:2442-2448), consulted by
        `CombatManager.cs:196` AFTER the "any primary enemy still alive?" test.

        This is what holds a fight open around a creature that is dead at 0 HP
        but about to revive: `AdaptablePower.cs:53-56` (the Test Subject) and
        `InfestedPower.cs:37` both return true. The sim had no such gate, so
        letting a prevented death leave the creature genuinely dead — which is
        the C# shape — would end the combat early without it.
        """
        for l, fn in self._each("should_stop_combat_from_ending"):
            if fn():
                return True
        return False

    def should_power_be_removed_on_death(self, power) -> bool:
        """Hook.ShouldPowerBeRemovedOnDeath (Hook.cs:2495-2509) — False from any
        listener keeps `power` on its dead owner.

        Exactly one implementer exists in the whole decompiled game,
        `IllusionPower.cs:59-66`: an Illusion keeps its buffs (and itself), and
        keeps debuffs only when they are `ITemporaryPower`.
        """
        for l, fn in self._each("should_power_be_removed_on_death"):
            if not fn(power):
                return False
        return True

    # ── Predicate hooks ──────────────────────────────────────────────────

    def should_die(self, creature: Creature, preventer: list | None = None) -> bool:
        """False from any listener prevents death (e.g. Fairy in a Bottle, Torii).

        `preventer` mirrors Hook.ShouldDie's `out preventer`: the vetoing
        listener is appended to it, so the caller can hand it to
        `after_preventing_death`."""
        for l, fn in self._each("should_die"):
            if not fn(creature):
                if preventer is not None:
                    preventer.append(l)
                return False
        return True

    def after_preventing_death(self, preventer: list, creature: Creature) -> None:
        """Notify the listener that vetoed a death (mirrors
        Hook.AfterPreventingDeath — Fairy in a Bottle heals here)."""
        for l in preventer:
            if hasattr(l, "after_preventing_death"):
                l.after_preventing_death(creature)

    def should_remove_from_combat_after_death(self, creature: Creature) -> bool:
        """Hook.ShouldCreatureBeRemovedFromCombatAfterDeath — False from any
        listener keeps the corpse in the combat (Decimillipede's Reattach).
        This does NOT prevent the death; see `should_die` for that."""
        for l, fn in self._each("should_remove_from_combat_after_death"):
            if not fn(creature):
                return False
        return True

    def should_clear_block(self, creature: Creature,
                           preventer: list | None = None) -> bool:
        """False from any listener preserves block across the turn boundary.

        `preventer` mirrors `Hook.ShouldClearBlock`'s `out preventer`
        (Creature.cs:718-728): the vetoing listener is appended so
        `Creature.ClearBlock` can hand it to `AfterPreventingBlockClear`.
        Sturdy Clamp needs the identity — `SturdyClamp.cs:31-46` opens
        `if (this != preventer || creature != Owner.Creature) return`, so it
        caps the retained block only when IT was the preventer, not when
        Barricade was.
        """
        for l, fn in self._each("should_clear_block"):
            if not fn(creature):
                if preventer is not None:
                    preventer.append(l)
                return False
        return True

    def after_preventing_block_clear(self, preventer: list,
                                     creature: Creature) -> None:
        """Hook.AfterPreventingBlockClear (Creature.cs:726) — the else-arm of
        ClearBlock, notifying the listener that vetoed the clear."""
        for l in preventer:
            fn = getattr(l, "after_preventing_block_clear", None)
            if fn is not None:
                fn(creature)

    def should_reset_energy(self, player: PlayerCombatState) -> bool:
        """False from any listener makes turn-start energy ADD to the current
        energy instead of replacing it (mirrors ShouldPlayerResetEnergy →
        ResetEnergy / AddMaxEnergyToCurrent; e.g. Ice Cream)."""
        for l, fn in self._each("should_reset_energy"):
            if not fn(player):
                return False
        return True

    def should_draw(self, player: PlayerCombatState, from_hand_draw: bool = False) -> bool:
        """False from any listener prevents the next draw (e.g. No Draw status).

        from_hand_draw is True only for the initial hand draw at the start of
        the player's turn; False for all mid-turn draws (card effects, powers).
        Mirrors STS2's ShouldDraw fromHandDraw param.
        """
        for l, fn in self._each("should_draw"):
            if not fn(player, from_hand_draw):
                return False
        return True

    def should_flush_hand(self) -> bool:
        """False from any listener keeps the hand instead of discarding it at
        the end of the turn (mirrors ShouldFlush; e.g. Ringing Triangle keeps
        the turn-1 hand)."""
        for l, fn in self._each("should_flush_hand"):
            if not fn():
                return False
        return True

    def should_allow_hitting(self, target: Creature) -> bool:
        """False from any listener makes the target un-hittable (e.g. Intangible)."""
        for l, fn in self._each("should_allow_hitting"):
            if not fn(target):
                return False
        return True

    def should_take_extra_turn(self, player: PlayerCombatState) -> bool:
        """True from any listener grants the player an extra turn instead of
        the enemy side acting (Hook.ShouldTakeExtraTurn — Pael's Eye). Unlike
        the other predicates this aggregates with ANY, mirroring the game's
        `players.Any(ShouldTakeExtraTurn)` check in the turn driver."""
        for l, fn in self._each("should_take_extra_turn"):
            if fn(player):
                return True
        return False

    def on_extra_turn(self, player: PlayerCombatState) -> None:
        """An extra player turn was just granted, before the fresh turn starts
        (folds the game's BeforeSideTurnEndEarly hand-exhaust + the
        AfterTakingExtraTurn bookkeeping into one notification — the sim has
        no Early hook phases)."""
        for l, fn in self._each("on_extra_turn"):
            fn(player)

    def should_play_card(self, card: Card, auto_play: bool = False) -> bool:
        """False from any listener prevents the card from being played (e.g. Ringing).

        auto_play is True when the play is an auto-play (Havoc, Stampede, ...)
        rather than a manual play from the hand — mirrors the AutoPlayType
        argument of the game's ShouldPlay hook (Enthralled only blocks manual
        plays).
        """
        for l, fn in self._each("should_play_card"):
            if not fn(card, auto_play):
                return False
        return True

    def should_ethereal_trigger(self, card: Card) -> bool:
        """False from any listener prevents an ethereal card from being exhausted."""
        for l, fn in self._each("should_ethereal_trigger"):
            if not fn(card):
                return False
        return True
