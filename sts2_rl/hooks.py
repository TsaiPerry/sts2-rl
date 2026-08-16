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
# CombatState.IterateHookListeners (CombatState.cs:413-467): per creature,
# Powers (:416) -> MonsterModel (:417-421) or, for a player, Relics (:428-435)
# -> PotionSlots (:436-443) -> Orbs (:448) -> the cards of AllPiles (:449-467).
# CombatHistory is a sim-only listener (note N3) that sits ahead of the walk.
#
# These are no longer the DISPATCH rule -- `_ordered()` derives the walk from
# the live combat state, which is what CombatState.IterateHookListeners does.
# They survive as the slot hint for a listener the derivation cannot reach
# (an orphaned power instance, a card in no pile, a synthetic test listener):
# `_merge_extras` seats such a listener at the end of its (creature, category)
# group instead of dropping it. The numbering has GAPS from the pre-round-13
# values because the monster and orb slots were missing from it entirely; only
# the relative order is ever read.
CAT_HISTORY = -1
CAT_POWER = 0
CAT_MONSTER = 1
CAT_RELIC = 2
CAT_POTION = 3
CAT_ORB = 4                   # reserved: the sim has no orbs (note N7)
CAT_CARD = 5
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
# `IsStarting` needs no counterpart: during `CombatState.__init__`, before
# `phase` is assigned, both `is_ending` and `is_over_or_ending` read False on
# the missing attribute (`getattr` guards on both), so `combat_is_over` --
# which now delegates to `is_over_or_ending` (hook_dispatch/guard10, round
# 14) -- stays False throughout setup exactly like the old phase-only check.
_COMBAT_GATED_HOOKS: dict[str, str] = {
    "after_attack": "AfterAttack",
    "after_auto_post_play_phase_entered": "AfterAutoPostPlayPhaseEntered",
    "after_auto_pre_play_phase_entered": "AfterAutoPrePlayPhaseEntered",
    "after_enemy_side_start": "AfterSideTurnStart",
    "after_modify_power_amount_given": "AfterModifyingPowerAmountGiven",
    "after_modify_power_amount_received": "AfterModifyingPowerAmountReceived",
    "after_modifying_hand_draw": "AfterModifyingHandDraw",
    "after_player_turn_end": "AfterTurnEnd",
    "after_side_turn_start": "AfterSideTurnStart",
    "before_attack": "BeforeAttack",
    "before_block_gained": "BeforeBlockGained",
    "before_card_auto_played": "BeforeCardAutoPlayed",
    "before_card_played": "BeforeCardPlayed",
    "before_enemy_side_end": "BeforeTurnEnd",
    "before_enemy_side_start": "BeforeSideTurnStart",
    "before_flush": "BeforeFlush",
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
    "modify_power_amount_given_additive": "ModifyPowerAmountGiven",
    "modify_power_amount_given_multiplicative": "ModifyPowerAmountGiven",
    "modify_power_amount_received": "ModifyPowerAmountReceived",
    "modify_x_value": "ModifyXValue",
    "on_block_cleared": "AfterBlockCleared",
    "on_block_gained": "AfterBlockGained",
    "on_card_discarded": "AfterCardDiscarded",
    "on_card_drawn": "AfterCardDrawn",
    "on_card_entered_combat": "AfterCardEnteredCombat",
    "on_card_exhausted": "AfterCardExhausted",
    "on_card_generated_for_combat": "AfterCardGeneratedForCombat",
    "on_energy_reset": "AfterEnergyReset",
    "on_energy_spent": "AfterEnergySpent",
    "on_enemy_side_end": "AfterTurnEnd",
    "on_hand_emptied": "AfterHandEmptied",
    "on_player_turn_end": "BeforeTurnEnd",
    "on_player_turn_start": "BeforeHandDraw",
    "on_player_turn_started": "AfterPlayerTurnStart",
    "on_power_amount_changed": "AfterPowerAmountChanged",
    "on_shuffle": "AfterShuffle",
    "should_afflict": "ShouldAfflict",
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
        # Combat-side mirror of RunManager.Instance.HasAscension — set by
        # RunState.create_combat from the run's ascension. Deliberately a
        # per-combat instance attribute, NOT a module global: multiple envs
        # at different ascension levels interleave in one process.
        self.ascension: int = 0
        # `_epoch` counts membership changes (register/unregister). It is the
        # invalidation signal for the PRESENCE cache only -- the dispatch ORDER
        # is re-derived per dispatch now, because a pile move changes the order
        # without changing membership and there is no pile-mutation choke point
        # to hang a dirty flag on (67 direct pile-list mutation sites across 15
        # files). See _ordered().
        self._epoch = 0
        # Base hook names for which some current listener declares a phase
        # variant; see _each(). Maintained INCREMENTALLY by register/unregister:
        # recomputing this union per order rebuild was the dominant cost of a
        # naive rebuild-per-dispatch (round 13 measurement).
        self._phased: frozenset[str] = frozenset()
        # How many registered listeners ride on a card rather than sitting in a
        # pile themselves (afflictions and enchantments; `hook_is_card_rider`).
        # Zero lets `_derive` splice the four piles in with list.extend instead
        # of walking card by card -- a ~9x difference on the derivation, and
        # the common case (no enchanted, no afflicted card in the combat).
        self._riders = 0
        # How many registered listeners declare no derivable `hook_category`
        # at all (synthetic listeners in tests, anything a future caller
        # registers by hand). Non-zero forces `_ordered` down the merge path,
        # which seats them by category instead of dropping them.
        self._undeclared = 0
        # Per-hook "does any live listener implement this" cache, keyed by
        # hook name to (epoch, bool); see _has_listener_for(). A dormant hook
        # (creature_card_cmds/G8's after_card_changed_piles/
        # on_card_generated_for_combat wiring, tier-2 Task 8) would otherwise
        # pay a full _ordered() rebuild + one getattr MISS per listener on
        # every dispatch even though the answer never changes between
        # register()/unregister() calls -- measured at ~23-35% overhead on
        # the sim's hottest loop (the per-card draw) before this cache.
        self._presence_cache: dict[str, tuple[int, bool]] = {}
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
        self._phased |= _phase_hooks(type(listener))
        if getattr(listener, "hook_is_card_rider", False):
            self._riders += 1
        if getattr(listener, "hook_category", None) is None:
            self._undeclared += 1

    def unregister(self, listener: Any) -> None:
        self._listeners.remove(listener)
        # `_listeners` can legitimately hold the same object twice; only drop
        # the liveness mark when the last copy goes.
        if not any(l is listener for l in self._listeners):
            self._live.discard(id(listener))
        self._epoch += 1
        # `_phased` is a union, so removing one member cannot be done
        # incrementally -- recompute. unregister() is orders of magnitude
        # rarer than dispatch (a power expiring, a potion leaving the belt),
        # and `_phase_hooks` is memoised per class, so this is a union of
        # ~35 interned frozensets rather than a dir() scan.
        self._phased = frozenset().union(
            *(_phase_hooks(type(l)) for l in self._listeners)
        ) if self._listeners else frozenset()
        if getattr(listener, "hook_is_card_rider", False):
            self._riders -= 1
        if getattr(listener, "hook_category", None) is None:
            self._undeclared -= 1

    # ── Dispatch order and phases ────────────────────────────────────────

    def _ordered(self) -> list[Any]:
        """The listener list in the game's dispatch order, DERIVED from the
        live combat state on every call.

        `CombatState.IterateHookListeners` (CombatState.cs:410-493) keeps no
        registry: it builds a fresh list per dispatch out of the creatures
        themselves — allies then enemies as one index space (:413-415) and,
        per creature, `creature.Powers` (:416) then either the MonsterModel
        (:417-421) or, for a player that passes `IsActiveForHooks` (:424-427),
        Relics skipping IsMelted (:428-435), PotionSlots in SLOT order skipping
        nulls (:436-443), Orbs (:448) and finally every card of `AllPiles` =
        Hand, Draw, Discard, Exhaust, Play (PlayerCombatState.cs:70-80), each
        card followed by its Affliction and then its Enchantment (:449-467) —
        each pile enumerated TOP-FIRST, which for the draw pile is the reverse
        of the sim's own storage order (see `_derive`).
        So the order is a function of CURRENT pile membership and slot
        occupancy, not of registration history: a card that changes pile
        changes its dispatch position (gap G1), and a potion procured into
        slot 0 dispatches ahead of one sitting in slot 1 that arrived earlier
        (the slot half of gap G2).

        The sim's `_listeners` stays the MEMBERSHIP authority (it is what
        `register`/`unregister` maintain and what the presence cache keys on);
        this method supplies the ORDER. Everything the derivation reaches is
        emitted in the game's slot; anything registered that it cannot reach —
        a card sitting in no pile, a synthetic listener a test registered by
        hand — is seated at the end of its (creature, category)
        group by `_merge_extras` rather than dropped, since dropping would
        silently retire a listener the sim dispatches to today.

        `CombatHistory` is a sim-only listener with no C# counterpart (note
        N3) and stays first, ahead of the creature walk, so an entry exists by
        the time anything reacts to it.

        There is no order cache: a pile move changes the order without
        changing membership, and the sim has no pile-mutation choke point to
        invalidate on. The cost is paid only behind `_each`'s presence gate.
        """
        order = self._derive()
        if self._undeclared or len(order) != len(self._listeners):
            return self._merge_extras()
        return order

    def _derive(self, groups: list | None = None,
                excluded: set | None = None) -> list[Any]:
        """One `CombatState.IterateHookListeners` list build (CombatState.cs:
        412-481), minus the lazy `Contains` filter — `_each` applies that per
        item, which is where C# applies it too (:482-488).

        `groups`, when given, collects `((rank, category), end_index)` for
        every slot of the walk in walk order, so `_merge_extras` knows where a
        listener the walk could not reach belongs.

        `excluded`, when given, collects the `id()` of every listener the walk
        REFUSED on purpose — a melted relic (:431) and everything past an
        inactive player's powers (:424-427). `_merge_extras` must not put those
        back: "the walk did not reach it" and "the walk decided against it" are
        different facts and only the first one is a sim-side shortfall.
        """
        combat = self.combat
        if combat is None:
            # A bare HookSystem (run-level walks, previews, unit tests): there
            # is no combat to derive from, so registration order is all there is.
            return list(self._listeners)
        out: list[Any] = []
        add = out.append
        extend = out.extend
        mark = None if groups is None else groups.append

        # Sim-only prefix (note N3), ahead of the creature walk.
        history = getattr(combat, "history", None)
        if history is not None:
            add(history)
        if mark is not None:
            mark(((0, CAT_HISTORY), len(out)))

        player = getattr(combat, "player", None)
        enemies = getattr(combat, "enemies", None) or ()
        # CombatState.cs:413-415 — `_allies` then `_enemies` as one index
        # space. The sim has exactly one ally, the player.
        creatures = [player] if player is not None else []
        creatures.extend(enemies)
        for rank, creature in enumerate(creatures):
            # :416 `list.AddRange(creature.Powers)` — BEFORE the player-active
            # check at :424, so a dead player's powers are still added to the
            # list and are dropped (if at all) only by the lazy PowerModel arm
            # of Contains (:599).
            extend(creature.powers.values())
            if mark is not None:
                mark(((rank, CAT_POWER), len(out)))
            if creature is not player:
                # :417-421 `creature.Player == null -> list.Add(creature.Monster)`.
                # The sim's Monster IS its own MonsterModel (gap G5).
                add(creature)
                if mark is not None:
                    mark(((rank, CAT_MONSTER), len(out)))
                continue
            if mark is not None:
                mark(((rank, CAT_MONSTER), len(out)))   # empty for a player
            # :424-427 — an inactive player contributes nothing past its powers.
            if player.is_active_for_hooks:
                # :428-435 relics, skipping IsMelted (:431). The sim removes a
                # melted relic from the run outright (see `Relic.is_tradable`),
                # so `combat.relics` does not hold one today and this loop is
                # a straight copy; the flag is declared on Relic so the skip is
                # expressible and so a wax port has it to set.
                for relic in getattr(combat, "relics", ()):
                    if relic.is_melted:
                        if excluded is not None:
                            excluded.add(id(relic))
                        continue
                    add(relic)
                if mark is not None:
                    mark(((rank, CAT_RELIC), len(out)))
                # :436-443 — PotionSlots in SLOT order, skipping null slots.
                for potion in player.potions:
                    if potion is not None:
                        add(potion)
                if mark is not None:
                    mark(((rank, CAT_POTION), len(out)))
                # :448 OrbQueue.Orbs — the sim has no orbs (note N7).
                if mark is not None:
                    mark(((rank, CAT_ORB), len(out)))
                # :449-467 — AllPiles, and per card the card, its Affliction,
                # then its Enchantment. All five piles are real lists now
                # (`PlayerCombatState.play_pile`, round 13 R5), so the Play leg
                # is one more `extend` and there is no marker to consult.
                #
                # The DRAW pile is walked REVERSED. `CardPile` is top-first —
                # `MoveToTopInternal` is `_cards.Insert(0, card)`
                # (CardPile.cs:160-167), `MoveToBottomInternal` is `_cards.Add`
                # (:142-149), `AddInternal`'s default `index = -1` appends
                # (:83-96), `CardPileCmd`'s default position is
                # `CardPilePosition.Bottom` (CardPileCmd.cs:259) and a draw
                # takes `drawPile.Cards.FirstOrDefault()` (:843) — so
                # `CombatState.cs:452-455` enumerates the draw pile top -> bottom.
                # The sim stores its draw pile the other way up (`player.py`'s
                # `draw_pile.pop()  # end of list = top of pile`, and
                # `CardPileCmd.add_to_draw` converting a game index `p` to sim
                # index `count - p`), so only this pile needs the flip. Hand,
                # discard and exhaust are append-at-end in BOTH engines, so
                # their list order already is C#'s enumeration order.
                if self._riders == 0:
                    # No affliction or enchantment is registered, so the five
                    # piles splice straight in.
                    extend(player.hand)
                    extend(reversed(player.draw_pile))
                    extend(player.discard_pile)
                    extend(player.exhaust_pile)
                    extend(player.play_pile)
                else:
                    for pile in (player.hand, reversed(player.draw_pile),
                                 player.discard_pile, player.exhaust_pile,
                                 player.play_pile):
                        for card in pile:
                            add(card)
                            affliction = card.affliction
                            if affliction is not None:
                                add(affliction)
                            enchantment = card.enchantment
                            if enchantment is not None:
                                add(enchantment)
            else:
                if mark is not None:
                    mark(((rank, CAT_RELIC), len(out)))
                    mark(((rank, CAT_POTION), len(out)))
                    mark(((rank, CAT_ORB), len(out)))
                if excluded is not None:
                    # Everything :424-427 skips, named so `_merge_extras` does
                    # not undo the skip.
                    for relic in getattr(combat, "relics", ()):
                        excluded.add(id(relic))
                    for potion in player.potions:
                        if potion is not None:
                            excluded.add(id(potion))
                    for pile in (player.hand, player.draw_pile,
                                 player.discard_pile, player.exhaust_pile,
                                 player.play_pile):
                        for card in pile:
                            excluded.add(id(card))
                            if card.affliction is not None:
                                excluded.add(id(card.affliction))
                            if card.enchantment is not None:
                                excluded.add(id(card.enchantment))
            if mark is not None:
                mark(((rank, CAT_CARD), len(out)))
        return out

    def _merge_extras(self) -> list[Any]:
        """`_derive`'s walk plus every registered listener it could not reach,
        each seated at the end of its (creature, category) group.

        C# has no such case — a model that is in no list is not a listener at
        all — but the sim's registry can outlive the structure the walk reads:
        a second application of an Instanced power leaves the replaced
        instance registered while the `powers` dict indexes only the new one
        (power_cmd/G5, where C#'s `Creature.Powers` is a LIST that holds
        both), a card can sit in no pile, and tests register bare objects.
        Dropping those would retire listeners the sim dispatches to today, so
        they are merged in instead. Cost is irrelevant: `_ordered` only comes
        here when the fast walk did not account for every registered listener.
        """
        groups: list = []
        excluded: set = set()
        order = self._derive(groups, excluded)
        seen = {id(l) for l in order}
        extras = [l for l in self._listeners
                  if id(l) not in seen and id(l) not in excluded]
        if not extras:
            return order

        enemies = getattr(self.combat, "enemies", None) or ()
        rank_of = {id(e): i + 1 for i, e in enumerate(enemies)}
        ends = dict(groups)
        insertions: dict[int, list] = {}
        for listener in extras:
            rank = rank_of.get(id(listener))
            if rank is None:
                owner = getattr(listener, "owner", None)
                rank = rank_of.get(id(owner), 0) if owner is not None else 0
            slot = (rank, getattr(listener, "hook_category", _CAT_CARD))
            at = ends.get(slot)
            if at is None:
                # A category no group of this walk declares (a synthetic
                # listener's `hook_category = 99`, or an enemy-owned card):
                # the last group that sorts at or before it, else the tail.
                at = len(order)
                for group_slot, end in groups:
                    if group_slot <= slot:
                        at = end
            insertions.setdefault(at, []).append(listener)

        merged: list[Any] = []
        for i, listener in enumerate(order):
            pending = insertions.pop(i, None)
            if pending is not None:
                merged.extend(pending)
            merged.append(listener)
        for i in sorted(insertions):
            merged.extend(insertions[i])
        return merged

    @property
    def combat_is_over(self) -> bool:
        """`CombatManager.IsOverOrEnding` — the predicate
        `Hook.IterateCombatHookListeners` gates on (Hook.cs:53-58:
        `if (IsOverOrEnding && !IsStarting) yield break;`).

        F3-R13 / hook_dispatch/guard10 (round 14): this used to test only
        `phase == Phase.COMBAT_OVER`, C#'s `!IsInProgress` half of
        `IsOverOrEnding` (CombatManager.cs:210-220 — `IsEnding ||
        !IsInProgress`). That missed the `IsEnding` half entirely: the window
        between the killing blow (all primary enemies dead) and
        `CheckWinCondition`'s teardown, where `phase` has not flipped to
        `COMBAT_OVER` yet but C# already refuses to dispatch. Delegating to
        `CombatState.is_over_or_ending` (combat.py) closes that window — it
        already carries the full `IsEnding || !IsInProgress` shape, including
        `ShouldStopCombatFromEnding`'s veto (CombatManager.cs:196) for a
        creature dead at 0 HP and about to revive.

        Outside a combat (a bare HookSystem, or a run-level listener walk)
        `self.combat` is None and the gate stays inert, same as before.
        `getattr` on `is_over_or_ending` for combat SETUP: `CombatState`
        back-references itself here early in `__init__`, before `phase` is
        assigned, so a starting-power `PowerCmd` call during encounter build
        finds neither `phase` nor a meaningful `is_ending` — both read False,
        which is C#'s `IsStarting` exemption (Hook.cs:45-47), for free.

        Perf note (power_cmd/G3+G4, tier-2 Task 18) for the property this
        replaces: it used to matter that `Phase` was cached at module scope
        (the old `_PHASE_CLS`, now removed) rather than re-imported every
        `_each()` call. Delegating to `combat.is_over_or_ending` drops that
        concern entirely — no import in this property at all now — at the
        cost of `is_ending`'s `_all_enemies_dead()` walk (O(enemy count), the
        same recomputation C#'s own `IsEnding` getter does via LINQ `Any()`
        on every read) once `phase` is not already `COMBAT_OVER`.
        """
        combat = self.combat
        if combat is None:
            return False
        return getattr(combat, "is_over_or_ending", False)

    def _has_listener_for(self, hook: str) -> bool:
        """True if some currently-LIVE listener implements `hook` (its plain
        name or any phase-suffixed variant — `_each`'s phased branch would
        find it under either).

        Cached by `(hook, self._epoch)`: `register()`/`unregister()` are the
        ONLY two places anywhere in the codebase that add or remove a
        listener or change its liveness (grepped — no other file touches
        `_listeners`/`_live` directly), and both already bump `_epoch`.

        This cache keys on listener-SET membership ONLY, which is why moving a
        card from one pile to another does not thrash it: a pile move changes
        the dispatch ORDER (`_ordered` re-derives it every call) but not the
        set, so the answer to "does anybody implement this hook" is unchanged
        and no rebuild is needed. A listener's set of implemented hooks is
        a property of its CLASS — ordinary Python methods, not per-instance
        dynamic attributes — matching the assumption `_phase_hooks` already
        makes (memoized per `type(l)`, never re-scanned for a still-registered
        instance); this cache makes the same assumption at the instance
        level, invalidated whenever the *set* of live instances changes
        rather than per-instance.

        This is the whole fix for creature_card_cmds/G8's cost concern: a
        hook with zero implementors today (after_card_changed_piles,
        on_card_generated_for_combat — the sim has no ported combat-pile or
        seventh-Wither-source listener yet) collapses from "rebuild the
        order cache + one getattr MISS per registered listener, every single
        call" to "one dict lookup + one int compare", amortized across
        however many calls happen before the next register/unregister.
        """
        cached = self._presence_cache.get(hook)
        if cached is not None and cached[0] == self._epoch:
            return cached[1]
        live = self._live
        names = tuple(hook + suffix for suffix in _PHASES)
        present = any(
            id(l) in live and any(getattr(l, name, None) is not None
                                  for name in names)
            for l in self._listeners
        )
        self._presence_cache[hook] = (self._epoch, present)
        return present

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
        `_phased` is maintained by register/unregister — so the common case
        stays a single walk.

        For a hook in `_COMBAT_GATED_HOOKS` this yields NOTHING once the combat
        is over — `Hook.IterateCombatHookListeners`' `if (IsOverOrEnding &&
        !IsStarting) yield break` (Hook.cs:55-58). Both are generators, so the
        test lands at enumeration start in both: a dispatch that began while the
        combat was live still reaches every listener even if one of them ends it.

        Also yields NOTHING, cheaply, when no CURRENTLY LIVE listener
        implements `hook` at all (`_has_listener_for`) — the fast path a
        dormant hook (creature_card_cmds/G8) needs on a hot dispatch site
        like the per-card draw. This gate sits ABOVE the `_ordered()`
        derivation on purpose: on the round-13 end_turn benchmark (25 combats ×
        10 end_turns, 30-card deck) 2,100 of 13,275 `_each` calls got past it,
        so 84% never build a list at all. The figure is workload-dependent —
        it is quoted because it was measured, not as a constant.
        Same generator-laziness note applies: it runs at first `next()`, not at
        `_each()`-call time, exactly like the combat-over check above it.

        THE PER-ITEM FILTER (CombatState.cs:482-488, arms at :549-599). C#
        yields an item only `if (Contains(item))`, evaluated as the enumeration
        REACHES it, so a listener that an earlier listener in the same dispatch
        invalidated is skipped. Two legs:

          * registration — `id(l) in self._live`, the sim's stand-in for a
            model having left the structure the walk reads;
          * state — `l.hook_contains()`, the per-type arms: a card, relic,
            potion, affliction or enchantment needs
            `!HasBeenRemovedFromState && Owner.IsActiveForHooks` (:589-597),
            a monster needs `Creature.CombatState != null` (:585). The
            PowerModel arm (:599) checks only owner state and never that the
            power is still attached, which is why a power removed mid-dispatch
            is still called (the recorded `on_enemy_side_end -> IntangiblePower`
            hit is FAITHFUL, not a bug).

        Both legs run AFTER the `getattr` miss test rather than before it. That
        is observationally identical — C# calls the virtual no-op on a listener
        that "does not implement" the hook, so filtering it in or out is
        unobservable — and it keeps the checks off the ~90% of the inner loop
        that is a miss.
        """
        if hook in _COMBAT_GATED_HOOKS and self.combat_is_over:
            return
        if not self._has_listener_for(hook):
            return
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
                    fn = getattr(l, name, None)
                    if fn is None or id(l) not in live:
                        continue
                    contains = getattr(l, "hook_contains", None)
                    if contains is not None and not contains():
                        continue
                    yield l, fn
            return
        for l in self._ordered():
            fn = getattr(l, hook, None)
            if fn is None or id(l) not in live:
                continue
            contains = getattr(l, "hook_contains", None)
            if contains is not None and not contains():
                continue
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

    # ── Modifier hooks — power amount (power_cmd/G3, G4) ─────────────────
    # C# runs THREE separately-sequenced phases per application
    # (PowerCmd.cs:120,125,127 for Apply; :227,232,234 for ModifyAmount, the
    # sim's one collapsed call site for both, power_cmd/step4): a raw-amount
    # event (BeforePowerAmountChanged — no sim analogue, deliberate
    # divergence, power_cmd/step10/step26), the GIVEN chain, then the
    # RECEIVED chain. Given and received are two different shapes and two
    # different C# hooks (`AbstractModel.ModifyPowerAmountGiven{Additive,
    # Multiplicative}` vs `TryModifyPowerAmountReceived`), not one flat
    # chain — Unsettling Lamp (given, UnsettlingLamp.cs:106-129) and Ruined
    # Helmet / Artifact (received, RuinedHelmet.cs:32-53, ArtifactPower.cs:
    # 17-36) turn out to be domain-disjoint on BOTH the target check the old
    # record cited AND on living on different chains entirely.

    def modify_power_amount_given_additive(
        self,
        power_cls: type,
        target: Creature,
        amount: int,
        applier: Creature | None,
        modifiers: list | None = None,
    ) -> int:
        """AbstractModel.ModifyPowerAmountGivenAdditive, the FIRST of the two
        passes `Hook.ModifyPowerAmountGiven` runs (Hook.cs:1892-1900) — a
        chain over the running total, exactly like `modify_damage_additive`.
        No current listener implements this (Lamp is multiplicative-only);
        it exists for shape-parity with C#, which always runs both passes
        together.

        The CALLER gates whether to invoke this at all on `applier != null &&
        combatState.ContainsCreature(applier)` (PowerCmd.cs:122-123) — that
        gate is not here, mirroring where C# puts it: `Hook.
        ModifyPowerAmountGiven` itself has no such gate.

        `modifiers` mirrors the `out modifiers` list: every listener whose
        delta was non-zero, for `after_modify_power_amount_given`.
        """
        for l, fn in self._each("modify_power_amount_given_additive"):
            delta = fn(power_cls, target, amount, applier)
            amount += delta
            if modifiers is not None and delta != 0:
                modifiers.append(l)
        return amount

    def modify_power_amount_given_multiplicative(
        self,
        power_cls: type,
        target: Creature,
        amount: int,
        applier: Creature | None,
        modifiers: list | None = None,
    ) -> int:
        """AbstractModel.ModifyPowerAmountGivenMultiplicative, the SECOND
        pass `Hook.ModifyPowerAmountGiven` runs (Hook.cs:1901-1909), over
        whatever the additive pass produced — sum-THEN-product, not
        commutative with a naive fold, exactly like
        `modify_damage_multiplicative`. Unsettling Lamp's once-per-combat
        doubling lives here (UnsettlingLamp.cs:106-129).
        """
        for l, fn in self._each("modify_power_amount_given_multiplicative"):
            factor = fn(power_cls, target, amount, applier)
            amount *= factor
            if modifiers is not None and factor != 1:
                modifiers.append(l)
        return amount

    def modify_power_amount_received(
        self,
        power_cls: type,
        target: Creature,
        amount: int,
        applier: Creature | None,
        modifiers: list | None = None,
    ) -> int:
        """AbstractModel.TryModifyPowerAmountReceived, dispatched by
        `Hook.ModifyPowerAmountReceived` (Hook.cs:1917-1930) — UNCONDITIONAL,
        unlike the given side: no applier gate exists anywhere for this one.

        Shape is different too: a single pass, but each listener either
        fully REPLACES the running amount or leaves it alone entirely (C#'s
        `bool` return + `out modifiedAmount`), not an additive/multiplicative
        fold. A listener returns the new amount to take effect, or `None`
        for "did not apply". ArtifactPower (ArtifactPower.cs:17-36) and
        RuinedHelmet (RuinedHelmet.cs:32-53) both live here now — this is
        where Artifact actually intercepts a debuff (by returning 0), not a
        hand-rolled block outside the hook loop.

        `modifiers` mirrors the `out modifiers` list: every listener that
        actually replaced the amount, for `after_modify_power_amount_received`.
        """
        for l, fn in self._each("modify_power_amount_received"):
            result = fn(power_cls, target, amount, applier)
            if result is not None:
                amount = result
                if modifiers is not None:
                    modifiers.append(l)
        return amount

    def after_modify_power_amount_given(self, modifiers: list, power) -> None:
        """Notify the given-side listeners that actually changed a power's
        amount (mirrors Hook.AfterModifyingPowerAmountGiven, Hook.cs:
        799-809). Called by `PowerCmd.apply` AFTER the power's state has
        been mutated (PowerCmd.cs:148-150 for a fresh Apply, :238-240 for
        the ModifyAmount/stacking branch) — `power` is that same real
        instance C# passes (its own `power` local), required rather than
        defaulted: passing `None` was a symptom of the dispatch firing
        before the power existed, which is the bug this entry closes. No
        current implementer of the companion hook reads it (there IS no
        current implementer at all — SneckoSkull.cs:32-36 is the sole C#
        override and is unported), but the mechanism now carries the right
        value for a future listener that does."""
        for l in modifiers:
            fn = getattr(l, "after_modify_power_amount_given", None)
            if fn is not None:
                fn(power)

    def after_modify_power_amount_received(self, modifiers: list, power) -> None:
        """Notify the received-side listeners that actually changed a
        power's amount (mirrors Hook.AfterModifyingPowerAmountReceived,
        Hook.cs:811-824). Called by `PowerCmd.apply` AFTER the power's state
        has been mutated (PowerCmd.cs:152 for a fresh Apply, :242 for the
        ModifyAmount/stacking branch) — `power` is that same real instance
        C# passes, required rather than defaulted for the same reason as
        `after_modify_power_amount_given` above. ArtifactPower.
        AfterModifyingPowerAmountReceived (ArtifactPower.cs:38-41) spends
        its own charge here (`PowerCmd.Decrement(this)`); RuinedHelmet.
        AfterModifyingPowerAmountReceived (RuinedHelmet.cs:55-60) marks
        itself used. Neither reads the `power` argument — both act on
        themselves (`this`) — and this still fires for a debuff Artifact
        fully blocked: `power` is then the constructed-but-never-attached
        instance (PowerModel.ApplyInternal's own zero-check only skips
        SetAmount/registration, not these companion events), not None."""
        for l in modifiers:
            fn = getattr(l, "after_modify_power_amount_received", None)
            if fn is not None:
                fn(power)

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

    def modify_hand_draw(self, player: PlayerCombatState, count: int,
                         modifiers: list | None = None) -> int:
        """Chain-modify how many cards are drawn at turn start.

        `modifiers` mirrors `Hook.ModifyHandDraw`'s `out modifiers`
        (Hook.cs:1684-1708): every listener whose delta actually changed the
        count -- across BOTH the plain pass and the `_late` phase `_each`
        already runs for a phased hook, exactly as C#'s two separate
        `IterateCombatHookListeners` loops (plain then
        `ModifyHandDrawLate`) build into the SAME `list` -- is appended, for
        `after_modifying_hand_draw` (turn_structure/step20)."""
        for l, fn in self._each("modify_hand_draw"):
            before = count
            count = fn(player, count)
            if modifiers is not None and count != before:
                modifiers.append(l)
        return max(0, count)

    def after_modifying_hand_draw(self, modifiers: list) -> None:
        """Notify the listeners that changed the hand-draw count (mirrors
        `Hook.AfterModifyingHandDraw`, CombatManager.cs:655; Hook.cs:739-749).
        C#'s `AfterModifyingHandDraw` takes no arguments -- turn_structure/
        step20, dormant (C#'s two ported implementers, Pocketwatch and
        PollinousCore, are both presentation-only `Flash()` calls).

        C#'s dispatcher walks the FULL listener order and calls each one
        `if (modifiers.Contains(modifier))` -- i.e. AT MOST ONCE per
        listener, in combat walk order, not once per `modifiers` entry.
        `modify_hand_draw` can append the SAME listener to `modifiers`
        twice (once for the plain pass, once for `_late`), so iterating
        `modifiers` directly would fire a both-phases listener's
        after-hook twice; dedup by identity + a fresh walk is what stops
        that."""
        seen = {id(l) for l in modifiers}
        for l in self._ordered():
            if id(l) not in seen:
                continue
            fn = getattr(l, "after_modifying_hand_draw", None)
            if fn is not None:
                fn()

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
        """`Hook.ModifyCardPlayResultPileTypeAndPosition` — chain-modify where
        a played card ends up once its play resolves.

        Consulted ONCE per play, for EVERY card, at CardModel.cs:1890, with
        `GetResultPileTypeForCardPlay()` (:2070-2082) evaluated as its
        `defaultPileType` argument. So the seed is the card's real destination,
        not a blanket "discard": `"none"` for a Power or a dupe (:2072-2074),
        `"exhaust"` for `ExhaustOnNextPlay` or the Exhaust keyword (:2076-2080,
        which also CONSUMES `ExhaustOnNextPlay` at :2078), else `"discard"`.
        (Previously the sim's call always passed the literal "discard",
        forcing ReboundPower to re-derive the Exhaust seed by hand.)

        Listeners see all three seeds and may return any of them:
        `ReboundPower` (ReboundPower.cs:19-30) abstains unless the incoming
        pile is Discard and otherwise returns `"draw_top"` — the sim's
        spelling of `(PileType.Draw, CardPilePosition.Top)`; `CorruptionPower`
        (CorruptionPower.cs:27-38) returns `"exhaust"` for any Skill,
        unconditionally, with no abstention of any kind.
        """
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

    def before_card_auto_played(self, card: Card, target: Creature | None = None,
                                auto_play_type: str = "default") -> None:
        """`Hook.BeforeCardAutoPlayed` (CardCmd.cs:122, Hook.cs:155-162) --
        fires in `CardCmd.AutoPlay`, right before `card.OnPlayWrapper` (:130)
        -- i.e. strictly before the ordinary `BeforeCardPlayed` that wrapper
        eventually fires. The sim's auto-play path already fires
        `on_energy_spent(card, 0)` first (combat.py, `auto_play_card`); this
        lands between that and `before_card_played`.

        `auto_play_type` is C#'s `AutoPlayType` argument, carried as of round
        13 (R5) now that a second value is reachable: `CardCmd.DiscardAndDraw`
        auto-plays each collected Sly card with `AutoPlayType.SlyDiscard`
        (CardCmd.cs:203) where every other caller takes the `Default`. It is
        still DORMANT on content -- the only C# implementer that reads it,
        `SkillSilent1Achievement.cs`, is an achievement and is unported
        (creature_card_cmds/step46) -- but the argument exists so the Sly
        machinery is not silently lossy.
        """
        for l, fn in self._each("before_card_auto_played"):
            fn(card, target, auto_play_type)

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

    def after_card_changed_piles(self, card: Card, pile: str | None,
                                 cloned_by: Any = None) -> None:
        """Hook.AfterCardChangedPiles (Hook.cs:167-179).

        Two COMPLETE passes, plain then Late, which `_each` gives us because
        `AfterCardChangedPilesLate` is a declared phase; SoulFysh.cs:91-108 is
        the game's only Late implementer.

        `pile` is the sim's pile name ("hand", "draw", "discard", "exhaust",
        "deck", "play") or `None`. C# calls the parameter `oldPileType`, and
        it names the OLD pile at every site except the transform: the Add
        site (CardPileCmd.cs:635) passes `oldPile?.Type ?? PileType.None` —
        `None` for a freshly generated card, which has no old pile — and the
        two mid-combat reshuffle helpers, which route discard-sourced cards
        through the same Add, pass the pile those cards started in
        ("discard", CardPileCmd.cs:892-912). The transform site is the one
        exception: it passes the pile the replacement was just placed IN
        (CardCmd.cs:447 `pile2.Type`), not an old pile at all. No ported
        listener reads the argument regardless — all four read
        `card.Pile.Type` instead (BingBong.cs:31, BookOfFiveRings.cs:84,
        DarkstonePeriapt.cs:19, LuckyFysh.cs:27) — so the value is passed
        through as the game passes it rather than reconciled, and `None` is
        a safe stand-in for `PileType.None` for the same reason.

        Dispatched from the combat-pile transform (CardCmd.cs:447); the Add
        site, wired at its three sim entry points — `CardPileCmd.
        add_to_hand`/`add_to_draw`/`add_to_discard` (`CardPileCmd.
        _generated_for_combat`, pile=None) and the player's per-card Draw
        (`PlayerCombatState._draw`, pile="draw"); the two mid-combat
        reshuffle helpers (`reshuffle_discard_into_draw`/
        `shuffle_draw_and_discard`, discard-sourced cards only, pile=
        "discard" — mirroring CardPileCmd.cs:892-912's silent, hookless
        re-seat of cards that were already in the draw pile before the
        shuffle); and RemoveFromCombat (CardPileCmd.cs:188 — the sim's one
        site is `monsters/hive/thieving_hopper.py`'s `_thievery`, which
        dispatches with the pile the stolen card just left, "draw" or
        "discard", and `cloned_by=None`, mirroring :188's `cardPile2.Type`
        and its literal `null`). The DECK-pile leg lives on the run, where
        `Relic.after_card_added_to_deck` is this same hook filtered to
        `pile.Type == PileType.Deck` (the filter every ported listener
        applies itself) — untouched by this round's wiring, which is entirely
        combat-side.

        The manual play (CardPileCmd.cs:683) was the last of the four
        enumerated C# sites and is wired as of round 13 (R5), now that the
        Play pile is a real list: `CombatState._add_to_play_pile` dispatches it
        with the pile the card left (Hand for a manual play, None for a
        pile-less auto-play) and a literal null `cloned_by`, AFTER the move —
        `AddDuringManualCardPlay` moves at :669-670 and dispatches at :683.
        The play's EXIT dispatches it again from `pile="play"`
        (`_move_to_result_pile_after_play`, C#'s :1988 -> CardPileCmd.cs:635).
        seam/creature_card_cmds guard G8.

        NOT every sim entry to `CardPileCmd.Add` dispatches it: `ExhaustCmd.
        exhaust` (C#'s `CardCmd.Exhaust` -> `Add(card, PileType.Exhaust)`,
        CardCmd.cs:242) does not, uniformly at all ~30 of its call sites. That
        is a residue of the Add site, not of the manual-play site.
        """
        for l, fn in self._each("after_card_changed_piles"):
            fn(card, pile, cloned_by)

    def on_card_generated_for_combat(self, card: Card,
                                     creator: Any = None) -> None:
        """Hook.AfterCardGeneratedForCombat (Hook.cs:249-258).

        The general interception point for "a card just finished entering a
        combat pile because something GENERATED it" — as distinct from
        `on_card_entered_combat`, which fires as part of the pile move itself
        (AbstractModel.AfterCardEnteredCombat) for any newly created card and
        lets active powers afflict it. This one fires strictly after that:
        combat-gated (Hook.cs:253, `IterateCombatHookListeners` — see
        `on_card_entered_combat`), so a dispatch that begins once the combat
        is over or ending reaches nobody.

        Two C# dispatch sites, both now wired:

          CardPileCmd.cs:246, inside `AddGeneratedCardsToCombat`, once per
          generated card, immediately AFTER that card's own `Add()` call has
          already fired `AfterCardChangedPiles` — mirrored by
          `CardPileCmd._generated_for_combat`, called from `add_to_hand`/
          `add_to_draw`/`add_to_discard`. `creator` is the `Player?` the
          caller passed to `AddGeneratedCardToCombat`; both currently
          reachable callers (Aeonglass.cs:145, WitheringPresencePower.cs:55)
          pass `null`.

          CardCmd.cs:499-506, a THIRD pass over a combat-pile transform's
          results — after `AfterCardChangedPiles`/`AfterTransformedFrom`/
          `AfterTransformedTo` and a presentation-only VFX wait — gated on
          `cardAdded.Pile.Type.IsCombatPile()` (always true for
          `transform_to_random`, which only ever swaps into a combat pile).
          `creator` here is `cardAdded.Owner`, the transforming player —
          never null, unlike the Add site.

        Aeonglass (`monsters/glory/aeonglass.py`'s `_AeonglassWitherListener`)
        is the sim's first ported listener; C#'s other six
        (Regalite/RocketPunch/ArsenalPower/PillarOfCreationPower/
        SmokestackPower/TrashToTreasurePower) are unported.
        """
        for l, fn in self._each("on_card_generated_for_combat"):
            fn(card, creator)

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
        ORDER, and `_ordered()`'s key WAS registration index, so a mid-combat
        copy always won. C# re-derives its listeners per dispatch from the piles
        (CombatState.cs:449-467, the enchantment added at :462-465), and at
        CardPileCmd.cs:877 the DISCARD pile still holds all of its cards (only
        drawPile entries are removed, :878-881) — so the card sitting LATER IN THE
        DISCARD fires last and ends on top.

        This method open-coded that pile derivation for itself, because
        `_ordered()` could not express it. As of round 13 `_ordered()` IS the
        per-dispatch pile derivation, so the hand-rolled sort is gone; what is
        left is a plain `_ordered()` walk, which additionally puts powers,
        relics and potions in their real slots where the hand-rolled key sorted
        every non-card listener to the tail. The sim's only two implementers
        are enchantments (`enchantments.py`), so today's outcome is unchanged.

        It still does NOT go through `_each`, for one reason: the C# dispatcher
        (Hook.cs:2006) walks `IterateCombatHookListeners`, whose gate is
        `CombatManager.IsOverOrEnding`, and `_each`'s gate
        (`HookSystem.combat_is_over`) is the narrower `phase == COMBAT_OVER`.
        Routing this hook through `_each` would WEAKEN a gate that is already
        exact here, so the explicit `is_over_or_ending` test stays. (That
        narrowness is a general `combat_is_over` question, not this hook's —
        recorded in the round-13 report.)

        `cards` is in the sim's own orientation (top at the END), so a listener
        that wants the top appends where C# inserts at 0.
        """
        combat = getattr(self, "combat", None)
        if combat is not None and getattr(combat, "is_over_or_ending", False):
            return
        live = self._live
        for listener in self._ordered():
            fn = getattr(listener, "modify_shuffle_order", None)
            if fn is None or id(listener) not in live:
                continue
            contains = getattr(listener, "hook_contains", None)
            if contains is not None and not contains():
                continue
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
        props: ValueProp = ValueProp.NONE,
        was_fully_blocked: bool = False,
    ) -> None:
        """Hook.AfterDamageGiven (Hook.cs:389-396) — the DEALER-side after-
        damage event, dispatched to EVERY listener (each self-filters on
        `dealer is <its owner>`) for every hit, blocked or not.

        `was_fully_blocked` mirrors `DamageResult.WasFullyBlocked`
        (CreatureCmd.cs:268), which C# listeners are expected to read
        (ImbalancedPower.cs:19) — the sim's caller (`cmds.py` DamageCmd.deal)
        used to gate this whole dispatch on `hp_lost > 0`, making a
        fully-blocked hit invisible to it (power/_after_damage_given_
        substitution, tier-2 Task 26). `amount` is `hp_lost`, i.e.
        `UnblockedDamage + OverkillDamage` (0 on a fully-blocked hit)."""
        for l, fn in self._each("on_damage_dealt"):
            fn(dealer, target, amount, card, props, was_fully_blocked)

    def before_block_gained(
        self, target: Creature, amount: int, card: Card | None = None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        """`Hook.BeforeBlockGained` (CreatureCmd.cs:642, Hook.cs:131-137) --
        the unconditional pre-modifier event, fired with the RAW block amount
        before the source card's enchantment fold and before
        `modify_block_additive`/`modify_block_multiplicative` run.

        Zero C# overrides game-wide today (`grep -rn "override.*
        BeforeBlockGained" src/` returns nothing) -- creature_card_cmds/
        step12, dormant. Kept as a real dispatch so a future override has
        somewhere to attach (tier-2 Task 11, item A)."""
        for l, fn in self._each("before_block_gained"):
            fn(target, amount, card, props)

    def before_block_gained(
        self, target: Creature, amount: int, card: Card | None = None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        """`Hook.BeforeBlockGained` (CreatureCmd.cs:642, Hook.cs:131-137) --
        the unconditional pre-modifier event, fired with the RAW block amount
        before the source card's enchantment fold and before
        `modify_block_additive`/`modify_block_multiplicative` run.

        Zero C# overrides game-wide today (`grep -rn "override.*
        BeforeBlockGained" src/` returns nothing) -- creature_card_cmds/
        step12, dormant. Kept as a real dispatch so a future override has
        somewhere to attach (tier-2 Task 11, item A)."""
        for l, fn in self._each("before_block_gained"):
            fn(target, amount, card, props)

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

    def should_draw(self, player: PlayerCombatState, from_hand_draw: bool = False,
                     preventer: list | None = None) -> bool:
        """False from any listener prevents the WHOLE draw (e.g. No Draw
        status) -- CardPileCmd.Draw (CardPileCmd.cs:804-808) consults this
        exactly ONCE, before the per-card loop even computes how many cards
        fit in the hand, not once per card. A caller that re-evaluated this
        per card would be asking a question C# never asks.

        from_hand_draw is True only for the initial hand draw at the start of
        the player's turn; False for all mid-turn draws (card effects, powers).
        Mirrors STS2's ShouldDraw fromHandDraw param.

        `preventer` mirrors Hook.ShouldDraw's `out modifier`: the vetoing
        listener is appended to it, so the caller can hand it to
        `after_preventing_draw`.
        """
        for l, fn in self._each("should_draw"):
            if not fn(player, from_hand_draw):
                if preventer is not None:
                    preventer.append(l)
                return False
        return True

    def after_preventing_draw(self, preventer: list) -> None:
        """Notify the listener that vetoed a draw (mirrors
        Hook.AfterPreventingDraw, CardPileCmd.cs:806 -- targeted at the one
        `modifier` ShouldDraw named, not a broadcast to every listener).
        Fiddle.cs:41-45 is the sole C# implementer and is Flash()-only VFX."""
        for l in preventer:
            fn = getattr(l, "after_preventing_draw", None)
            if fn is not None:
                fn()

    def before_flush(self, player: PlayerCombatState) -> None:
        """`Hook.BeforeFlush` (CombatManager.cs:1200-1206, Hook.cs:532-538) --
        fires per player, after the `DoTurnEnd` loop (turn-end-in-hand cards)
        and before the `CheckWinCondition` that closes
        `EndPlayerTurnPhaseOneInternal` -- so strictly before
        `EndPlayerTurnPhaseTwoInternal`'s own `Hook.ShouldFlush` (which
        `should_flush_hand` mirrors).

        turn_structure/step55, dormant: C#'s three implementers
        (SlumberingEssence.cs, WellLaidPlansPower.cs, a mock) are all
        unported (tier-2 Task 11, item D). C# also gates this call on
        `LocalContext.NetId.HasValue` (CombatManager.cs:1200) -- but that
        is not a multiplayer flag: the sibling `DoTurnEnd` call three lines
        above (:1188) is gated the same way and DoTurnEnd is what resolves
        Burn and every other turn-end-in-hand card, single-player included.
        It is a local-client-presence check (true throughout ordinary
        single-player play; the sim models no "local client" concept at
        all), not a multiplayer-only gate."""
        for l, fn in self._each("before_flush"):
            fn(player)

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

    def should_afflict(self, card: Card, affliction) -> bool:
        """False from any listener refuses the affliction entirely (Hook.
        ShouldAfflict, Hook.cs:2101-2111 -- an AND-all veto over
        IterateCombatHookListeners, same shape as should_allow_hitting).
        creature_card_cmds/N2 + step64. Zero C# implementers game-wide
        (`grep -rn "override.*ShouldAfflict" src/` returns nothing), so this
        is currently a no-op; kept as a real dispatch so a future override
        has somewhere to attach."""
        for l, fn in self._each("should_afflict"):
            if not fn(card, affliction):
                return False
        return True
