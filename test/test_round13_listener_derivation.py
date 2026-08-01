"""Round 13, R1: `CombatState.IterateHookListeners` as a per-dispatch DERIVED
walk with a lazy per-item `Contains` filter.

Everything here pins `CombatState.cs:410-493` and its `Contains` arms
(`:549-599`) against `sts2_rl/hooks.py`'s `_ordered`/`_derive`/`_each`. Four
gap clusters from `audit/records/seam/hook_dispatch.json`:

  G1  (steps 9, 44) card listener order is per-pile and re-derived, where the
      sim froze `player.all_cards` at combat start;
  G2  (step 6, SLOT half) potions walk `PotionSlots` in slot order, where the
      sim used the order they registered in;
  G5  (step 3) `MonsterModel` is a listener in its own slot, right after that
      creature's powers;
  G6  (guard G6) `AfflictionModel` is a listener immediately after its card
      and before that card's enchantment;
  G7  (steps 4, 11, 12, 16, 45) the per-item re-check: `Contains` is evaluated
      as the enumeration REACHES each item, so state a listener changes mid
      dispatch is honoured for the listeners after it.
"""
from __future__ import annotations

import random

from sts2_rl import CombatState
from sts2_rl.afflictions import Affliction
from sts2_rl.cards import make_card
from sts2_rl.cmds import CardCmd, PowerCmd
from sts2_rl.hooks import CAT_CARD
from sts2_rl.potions import make_potion
from sts2_rl.powers import ThornsPower
from sts2_rl.relics import make_relic

HOOK = "on_combat_start"        # no arguments, dispatched through `_each`


def fresh(**kw) -> CombatState:
    return CombatState(rng=random.Random(0), **kw)


def probe(cs, listeners, log, hook: str = HOOK):
    """Give each of `listeners` a recorder for `hook` and make the presence
    cache notice.

    `_has_listener_for` is keyed on `_epoch`, which only register/unregister
    bump — attaching a method to an already-registered instance is invisible
    to it by design (a listener's hook set is a property of its CLASS). These
    tests attach per-instance recorders, so the cache entry for that one hook
    name is dropped explicitly.
    """
    for listener in listeners:
        def rec(*a, _l=listener, **k):
            log.append(_l)
        setattr(listener, hook, rec)
    cs.hooks._presence_cache.pop(hook, None)


def visited(cs, hook: str = HOOK):
    return [l for l, _ in cs.hooks._each(hook)]


# ══════════════════════════════════════════════════════════════════════════
# G1 — card order is derived from pile membership, per dispatch
# ══════════════════════════════════════════════════════════════════════════

def test_a_card_that_changes_pile_changes_its_dispatch_position():
    """`AllPiles` is Hand, Draw, Discard, Exhaust, Play
    (PlayerCombatState.cs:70-80) and CombatState.cs:449-467 walks it on EVERY
    dispatch, so moving a card between piles moves it in the listener list.

    The sim registered `player.all_cards` once at combat start
    (hand + draw + discard + exhaust, evaluated then) and never reordered, so
    a card kept its combat-start position for the whole fight — gap G1.
    """
    cs = fresh()
    cs.player.hand.clear()
    # Two cards in the DRAW pile. The sim's list keeps the TOP of the pile at
    # the END, and the walk is top-first — see
    # `test_the_draw_pile_walks_top_first`.
    bottom, top = make_card("strike"), make_card("defend")
    cs.player.draw_pile[:] = [bottom, top]
    for card in (bottom, top):
        cs.hooks.register(card)
        card.combat = cs

    log: list = []
    probe(cs, [bottom, top], log)
    assert visited(cs) == [top, bottom]

    # Move the pile's BOTTOM card to the HAND. Hand walks before Draw, so it
    # now dispatches FIRST, with no register/unregister anywhere.
    log.clear()
    cs.player.draw_pile.remove(bottom)
    cs.player.hand.append(bottom)
    assert visited(cs) == [bottom, top]

    # ...and back to the bottom of the draw pile (index 0 in the sim's
    # orientation), which puts it last again.
    cs.player.hand.remove(bottom)
    cs.player.draw_pile.insert(0, bottom)
    assert visited(cs) == [top, bottom]


def test_the_draw_pile_walks_top_first():
    """`CardPile` is TOP-FIRST: `MoveToTopInternal` is `_cards.Insert(0, card)`
    (CardPile.cs:160-167), `MoveToBottomInternal` is `_cards.Add` (:142-149),
    `AddInternal`'s default `index = -1` appends (:83-96) and `CardPileCmd`'s
    default position is `CardPilePosition.Bottom`. A draw takes
    `drawPile.Cards.FirstOrDefault()` (CardPileCmd.cs:843), so index 0 IS the
    top, and `CombatState.cs:452-455` walks the pile top -> bottom.

    The sim stores its draw pile the other way up — `player.py`'s
    `draw_pile.pop()  # end of list = top of pile`, and `CardPileCmd.
    add_to_draw` converts a game index `p` to sim index `count - p` in as many
    words. The derivation must therefore walk the draw pile REVERSED. Hand,
    discard and exhaust need no such flip: both engines append at the end.
    """
    cs = fresh()
    cs.player.hand.clear()
    bottom, top = make_card("strike"), make_card("defend")
    cs.player.draw_pile[:] = [bottom, top]          # sim: top of pile is LAST
    for card in (bottom, top):
        cs.hooks.register(card)
        card.combat = cs

    log: list = []
    probe(cs, [bottom, top], log)
    # The card that would be drawn next is the one C# has at Cards[0].
    assert cs.player.draw_pile[-1] is top
    assert visited(cs) == [top, bottom]


def test_pile_order_beats_registration_order():
    """The stronger form: the card registered LAST dispatches FIRST when its
    pile says so. Under the old rule (registration index as the tie-break
    inside the card category) this was impossible."""
    cs = fresh()
    cs.player.hand.clear()
    cs.player.draw_pile.clear()
    early, late = make_card("strike"), make_card("defend")
    cs.player.draw_pile.append(early)
    cs.hooks.register(early)
    early.combat = cs
    cs.player.hand.append(late)          # hand walks before draw
    cs.hooks.register(late)
    late.combat = cs

    log: list = []
    probe(cs, [early, late], log)
    assert cs.hooks._listeners.index(early) < cs.hooks._listeners.index(late)
    assert visited(cs) == [late, early]


def test_the_four_piles_walk_in_allpiles_order():
    cs = fresh()
    cs.player.hand.clear()
    cs.player.draw_pile.clear()
    cards = {name: make_card("strike")
             for name in ("hand", "draw", "discard", "exhaust")}
    for card in cards.values():
        cs.hooks.register(card)
        card.combat = cs
    cs.player.hand.append(cards["hand"])
    cs.player.draw_pile.append(cards["draw"])
    cs.player.discard_pile.append(cards["discard"])
    cs.player.exhaust_pile.append(cards["exhaust"])

    log: list = []
    probe(cs, list(cards.values()), log)
    assert visited(cs) == [cards["hand"], cards["draw"],
                           cards["discard"], cards["exhaust"]]


def test_a_card_mid_onplay_walks_in_the_play_slot_last():
    """CardCmd.cs:116 parks a card being played in `PileType.Play`, which is
    the FIFTH and last entry of AllPiles, so it dispatches after the exhaust
    pile however it got there.

    RE-STAGED 2026-08-01 (round 13, R5): `_derive`'s Play leg was a stand-in
    reading `player._playing_card` off a card parked in the discard; it now
    walks the real `player.play_pile` (creature_card_cmds N9/step82)."""
    cs = fresh()
    cs.player.hand.clear()
    cs.player.draw_pile.clear()
    playing, other = make_card("strike"), make_card("defend")
    for card in (playing, other):
        cs.hooks.register(card)
        card.combat = cs
    cs.player.discard_pile[:] = [playing, other]
    log: list = []
    probe(cs, [playing, other], log)
    assert visited(cs) == [playing, other]

    cs.player.discard_pile.remove(playing)
    cs.player.play_pile.append(playing)   # now in PileType.Play
    assert visited(cs) == [other, playing]


# ══════════════════════════════════════════════════════════════════════════
# G2 (slot half) — potions walk PotionSlots, not registration order
# ══════════════════════════════════════════════════════════════════════════

def test_potions_dispatch_in_belt_slot_order_not_registration_order():
    """CombatState.cs:436-443 walks `player.PotionSlots` by index. The sim
    filled the belt slot correctly but appended the potion to `_listeners`,
    and `_ordered`'s tie-break was that registration index — so a potion
    procured into a freed slot 0 dispatched AFTER one that had been sitting
    in slot 1 since combat start (gap G2, slot half)."""
    cs = fresh(potions=[make_potion("block_potion"),
                        make_potion("strength_potion")])
    slot0, slot1 = cs.player.potions[0], cs.player.potions[1]
    log: list = []
    probe(cs, [slot0, slot1], log)
    assert visited(cs) == [slot0, slot1]

    # Drink slot 0's potion, then procure a new one: it lands back in slot 0
    # (first null index, Player.AddPotionInternal) but registers LAST.
    cs.player.discard_potion(slot0)
    fresh_potion = make_potion("fire_potion")
    assert cs.player.add_potion(fresh_potion)
    assert cs.player.potions[0] is fresh_potion

    log.clear()
    probe(cs, [fresh_potion, slot1], log)
    assert cs.hooks._listeners.index(slot1) < \
        cs.hooks._listeners.index(fresh_potion)
    assert visited(cs) == [fresh_potion, slot1]      # slot order wins


# ══════════════════════════════════════════════════════════════════════════
# G5 — MonsterModel is a listener, in its own slot
# ══════════════════════════════════════════════════════════════════════════

def test_the_monster_is_a_listener_right_after_its_own_powers():
    """CombatState.cs:417-421 — `creature.Player == null ->
    list.Add(creature.Monster)`, immediately after `list.AddRange(
    creature.Powers)` at :416. MonsterModel.cs:51 declares
    ShouldReceiveCombatHooks. The sim's Monster IS its MonsterModel."""
    cs = fresh()
    enemy = cs.enemy
    PowerCmd.apply(cs.hooks, enemy, ThornsPower, 1, applier=cs.player)
    order = cs.hooks._ordered()
    assert enemy in order
    thorns = enemy.powers["thorns"]
    assert order.index(thorns) + 1 == order.index(enemy)
    # ...and after every player-side listener: allies precede enemies (:413).
    assert order.index(enemy) == len(order) - 1


def test_a_monster_removed_from_combat_stops_being_dispatched_to():
    """`Contains`' MonsterModel arm is `Creature.CombatState != null`
    (CombatState.cs:585) and nothing else.

    The sim's stand-in for the nulled back-pointer is
    `Monster.combat_removal_committed`, set at the two statements that call
    `CombatState.RemoveCreature` (CreatureCmd.cs:529 and :601) — NOT the
    derived `is_removed_from_combat`, which answers "will this corpse be
    removed?" the instant HP reaches zero, long before C# executes the
    removal. See `test_a_dying_monster_receives_its_own_after_death`.
    """
    from sts2_rl.cmds import CreatureCmd

    cs = fresh()
    enemy = cs.enemy
    log: list = []
    probe(cs, [enemy], log)
    assert visited(cs) == [enemy]

    enemy.hp = 0                       # dead, but nothing has removed it yet
    assert enemy.is_removed_from_combat            # the PREDICTION says gone
    assert visited(cs) == [enemy]                  # C# has not removed it yet

    enemy.hp = 5
    CreatureCmd.kill(cs.hooks, enemy)  # the real removal statement runs here
    assert enemy.combat_removal_committed is True
    assert visited(cs) == []


def test_a_death_vetoed_corpse_is_still_dispatched_to():
    """`ShouldCreatureBeRemovedFromCombatAfterDeath` said no
    (CreatureCmd.cs:508), so the `:523-531` removal block is skipped entirely
    and `Creature.CombatState` stays non-null: a withered Decimillipede
    segment keeps receiving hooks."""
    from sts2_rl.cmds import CreatureCmd

    cs = fresh()
    enemy = cs.enemy

    class _Retainer:
        hook_category = CAT_CARD

        def should_remove_from_combat_after_death(self, creature) -> bool:
            return False

    cs.hooks.register(_Retainer())
    log: list = []
    probe(cs, [enemy], log)
    CreatureCmd.kill(cs.hooks, enemy)
    assert enemy.is_dead and enemy.retained_after_death
    assert enemy.combat_removal_committed is False
    assert visited(cs) == [enemy]


def test_an_escaped_monster_stops_being_dispatched_to():
    """The OTHER `CombatState.RemoveCreature` caller: `CreatureCmd.Escape`
    (CreatureCmd.cs:601 -> `CombatState.CreatureEscaped`, CombatState.cs:
    266-270) always removes, with no hook to consult."""
    from sts2_rl.cmds import CreatureCmd

    cs = fresh()
    enemy = cs.enemy
    log: list = []
    probe(cs, [enemy], log)
    assert visited(cs) == [enemy]

    CreatureCmd.escape(cs.hooks, enemy)
    assert enemy.combat_removal_committed is True
    assert visited(cs) == []


def test_a_dying_monster_receives_its_own_after_death():
    """`CreatureCmd.KillWithoutCheckingWinCondition` in statement order:
    `shouldRemoveFromCombat` is COMPUTED at :508, `Hook.AfterDeath` is
    dispatched at :519, and only then — at :523-531 —
    `CombatState.RemoveCreature` nulls `Creature.CombatState`
    (CombatState.cs:299-302). So throughout its own AfterDeath the dying
    creature still passes the MonsterModel arm of `Contains` (:585, which
    tests the back-pointer and NOTHING else) and receives the hook.

    The sim used to answer that arm from `is_removed_from_combat`, which is
    `is_gone and not retained_after_death` — true the moment HP hits zero,
    i.e. before `_resolve_death` is even entered. Eight of the ten C# monster
    `AfterDeath` overrides are self-death-only, and KinPriest's `else if
    (creature == base.Creature)` arm (KinPriest.cs:104-107) is this record's
    own named trigger for G5, so the first content port G5 unblocks lands
    exactly here.
    """
    from sts2_rl.cmds import CreatureCmd

    cs = fresh()
    enemy = cs.enemy
    seen: list = []

    def record(creature, was_removal_prevented: bool = False) -> None:
        seen.append((creature, enemy.combat_removal_committed))

    enemy.on_death = record
    cs.hooks._presence_cache.pop("on_death", None)

    CreatureCmd.kill(cs.hooks, enemy)
    assert seen == [(enemy, False)]          # delivered, and still in combat
    assert enemy.combat_removal_committed is True   # removed AFTER the hook


def test_a_dying_monster_is_consulted_by_its_own_should_die():
    """The same window, one statement earlier: `Hook.ShouldDie`
    (CreatureCmd.cs:505) and `Hook.ShouldCreatureBeRemovedFromCombatAfterDeath`
    (:508) both run before the `:523-531` removal, so the creature at 0 HP is
    still one of their listeners."""
    from sts2_rl.cmds import CreatureCmd

    cs = fresh()
    enemy = cs.enemy
    asked: list = []

    def should_die(creature, preventer=None) -> bool:
        asked.append(creature)
        return True

    enemy.should_die = should_die
    cs.hooks._presence_cache.pop("should_die", None)
    CreatureCmd.kill(cs.hooks, enemy)
    assert asked == [enemy]


def test_a_monster_that_dies_during_its_own_move_leaves_when_the_move_ends():
    """`CreatureCmd.cs:527` refuses `combatState.RemoveCreature` while
    `monster.IsPerformingMove`; `MonsterModel.PerformMove` (MonsterModel.cs:
    447-451) completes the deferred removal once the move returns."""
    from sts2_rl.cmds import CreatureCmd

    cs = fresh()
    enemy = cs.enemy
    during: list = []

    def suicide(ctx):
        CreatureCmd.kill(cs.hooks, enemy)
        during.append(enemy.combat_removal_committed)

    enemy.take_turn = suicide
    enemy.spawned_this_turn = False
    cs._run_enemy_turns()
    assert during == [False]                       # still in combat mid-move
    assert enemy.combat_removal_committed is True  # removed at the move's end


# ══════════════════════════════════════════════════════════════════════════
# G6 — AfflictionModel is a listener, between its card and its enchantment
# ══════════════════════════════════════════════════════════════════════════

class _HookedAffliction(Affliction):
    """A synthetic affliction that implements a hook.

    G6 is DORMANT on content: none of the seven ported afflictions defines a
    hook, and the only C# affliction that overrides one (Hexed.cs,
    AfterCardEnteredCombat) is an unported stub. What this pins is the
    MACHINERY — that when such an affliction is ported it lands in the slot
    CombatState.cs:458-461 gives it.
    """

    id = "test_hooked"
    name = "TestHooked"

    def on_combat_start(self) -> None:      # noqa: D102 - recorder patched in
        pass


def test_an_affliction_dispatches_immediately_after_its_own_card():
    """CombatState.cs:456-465, in order: `list.Add(cardModel)`, then
    `cardModel.Affliction`, then `cardModel.Enchantment`."""
    from sts2_rl.enchantments import make_enchantment

    cs = fresh()
    cs.player.hand.clear()
    cs.player.draw_pile.clear()
    before, card, after = (make_card("strike"), make_card("defend"),
                           make_card("strike"))
    for c in (before, card, after):
        cs.hooks.register(c)
        c.combat = cs
    cs.player.hand[:] = [before, card, after]

    affliction = CardCmd.afflict(card, _HookedAffliction, 1)
    assert affliction is not None
    enchantment = make_enchantment("sharp")
    enchantment.attach_internal(card)
    cs.hooks.register(enchantment)

    log: list = []
    probe(cs, [before, card, affliction, enchantment, after], log)
    assert visited(cs) == [before, card, affliction, enchantment, after]


def test_an_affliction_is_registered_and_unregistered_with_its_card():
    cs = fresh()
    card = cs.player.draw_pile[0]
    affliction = CardCmd.afflict(card, _HookedAffliction, 1)
    assert affliction in cs.hooks._listeners
    assert affliction.card is card

    CardCmd.clear_affliction(card)
    # CardModel.ClearAfflictionInternal (CardModel.cs:1532-1540) calls
    # AfflictionModel.ClearInternal (:249-254), which nulls `_card` — so
    # `HasCard`, the first leg of Contains' affliction arm (:591), goes false.
    assert card.affliction is None
    assert affliction.card is None
    assert affliction not in cs.hooks._listeners
    assert affliction.hook_contains() is False


def test_an_affliction_whose_card_left_its_pile_is_seated_by_the_extras_merge():
    """PINS A KNOWN DIVERGENCE, not the C# rule.

    C# is unambiguous for cards: a card in no pile is in no `AllPiles` entry
    (CombatState.cs:449-467) and `CardModel.ShouldReceiveCombatHooks` is
    `Pile?.IsCombatPile ?? false` (CardModel.cs:1045), so it is not a listener
    at all — and neither is its affliction, which C# reaches only THROUGH the
    card (:458). The sim's registry can outlive the pile that holds a card
    (`cards/primal_force.py` displaces a card from the hand without
    unregistering it), so `_merge_extras` re-seats such a card — and its
    affliction behind it — at the end of the card group rather than dropping
    it, because dropping would silently retire a listener the sim dispatches
    to today. That is a transitional safety net; this test pins the net, not
    the game.
    """
    cs = fresh()
    cs.player.hand.clear()
    cs.player.draw_pile.clear()
    card = make_card("strike")
    cs.hooks.register(card)
    card.combat = cs
    cs.player.hand.append(card)
    affliction = CardCmd.afflict(card, _HookedAffliction, 1)

    order = cs.hooks._ordered()
    assert order.index(affliction) == order.index(card) + 1

    other = make_card("defend")
    cs.hooks.register(other)
    other.combat = cs
    cs.player.discard_pile.append(other)

    cs.player.hand.remove(card)          # in no pile at all now
    order = cs.hooks._ordered()
    # Still reachable — the sim never silently retires a registered listener —
    # but out of the pile walk entirely, so it sits at the end of the card
    # group with its affliction still glued behind it.
    assert order.index(affliction) == order.index(card) + 1
    assert order.index(card) > order.index(other)


# ══════════════════════════════════════════════════════════════════════════
# G7 — the lazy, per-item Contains re-check
# ══════════════════════════════════════════════════════════════════════════

def test_a_card_removed_from_state_mid_dispatch_is_skipped():
    """`Contains` is evaluated per item as the enumeration reaches it
    (CombatState.cs:482-488), and the CardModel arm (:593) is
    `!HasBeenRemovedFromState && Owner.IsActiveForHooks`. So a card that an
    EARLIER listener in the same dispatch removed from state never runs."""
    cs = fresh()
    cs.player.hand.clear()
    cs.player.draw_pile.clear()
    remover, victim = make_card("strike"), make_card("defend")
    for card in (remover, victim):
        cs.hooks.register(card)
        card.combat = cs
    cs.player.hand[:] = [remover, victim]

    log: list = []
    probe(cs, [remover, victim], log)
    assert visited(cs) == [remover, victim]

    def kill_the_victim(*a, **k):
        log.append(remover)
        victim.has_been_removed_from_state = True

    remover.on_combat_start = kill_the_victim
    log.clear()
    for _, fn in cs.hooks._each(HOOK):
        fn()
    assert log == [remover]              # the victim was reached and refused


def test_a_played_power_card_is_flagged_removed_from_state():
    """`CardPileCmd.RemoveFromCombat` ends with `oldCard.RemoveFromState()`
    (CardPileCmd.cs:189 -> CardModel.cs:1604-1608), and a played Power card's
    result pile is `PileType.None`, which CardModel.cs:1979-1982 resolves to
    exactly that command. Until this fix `has_been_removed_from_state` was
    declared on `Card` but never assigned anywhere in production, so the first
    leg of the CardModel `Contains` arm (CombatState.cs:593) was
    machinery-only."""
    from sts2_rl.cmds import CardPileCmd

    cs = fresh()
    cs.player.hand.clear()
    inflame = make_card("inflame")
    cs.player.hand.append(inflame)
    CardPileCmd._enter_combat(cs.hooks, inflame)
    assert inflame.has_been_removed_from_state is False

    cs.player.energy = 9
    assert cs.play_card(0)
    assert inflame.has_been_removed_from_state is True
    assert inflame.hook_contains() is False


def test_a_transformed_card_is_flagged_removed_from_state():
    """`CardCmd.Transform`'s tail (CardCmd.cs:498-506) calls `RemoveFromState`
    on every ORIGINAL once the replacements have landed."""
    from sts2_rl.cmds import CardCmd

    cs = fresh()
    cs.player.hand.clear()
    cs.player.draw_pile.clear()
    original = make_card("strike")
    cs.player.hand.append(original)
    cs.hooks.register(original)
    original.combat = cs

    replacement = CardCmd.transform_to_random(cs.hooks, cs.player, original)
    assert replacement is not None
    assert original.has_been_removed_from_state is True
    assert original.hook_contains() is False


def test_combat_setup_clears_the_removed_from_state_flag():
    """`CardModel.AfterCloned` resets it (CardModel.cs:1228) because the game
    builds a fresh clone per combat. The sim reuses one `Card` object across a
    whole run, and `reset_combat_state` is where it stands in for the clone —
    without the reset a Power card played in one fight would never listen
    again."""
    card = make_card("inflame")
    card.has_been_removed_from_state = True
    card.reset_combat_state()
    assert card.has_been_removed_from_state is False


def test_a_relic_removed_from_state_mid_dispatch_is_skipped():
    """Same shape, RelicModel arm (CombatState.cs:597)."""
    cs = fresh(relics=[make_relic("pen_nib"), make_relic("orichalcum")])
    first, second = cs.relics
    log: list = []
    probe(cs, [first, second], log)
    assert visited(cs) == [first, second]

    def melt_the_second(*a, **k):
        log.append(first)
        second.has_been_removed_from_state = True

    first.on_combat_start = melt_the_second
    log.clear()
    for _, fn in cs.hooks._each(HOOK):
        fn()
    assert log == [first]


def test_a_melted_relic_is_skipped_by_the_walk():
    """The one skip inside the relic leg itself (CombatState.cs:431), not part
    of Contains. Dormant on today's content — the sim drops a melted relic
    from the run rather than flagging it — so this pins the machinery."""
    cs = fresh(relics=[make_relic("pen_nib"), make_relic("orichalcum")])
    first, second = cs.relics
    log: list = []
    probe(cs, [first, second], log)
    assert visited(cs) == [first, second]

    second.is_melted = True
    assert visited(cs) == [first]
    # ...and it is NOT quietly re-seated by the extras merge, which exists for
    # listeners the walk could not reach, not ones it refused.
    assert second not in cs.hooks._ordered()


def test_an_inactive_player_contributes_only_its_powers():
    """CombatState.cs:424-427 — `!player.IsActiveForHooks -> continue`, which
    skips that player's relics, potions, orbs and cards but NOT the powers
    added one line earlier at :416."""
    cs = fresh(relics=[make_relic("pen_nib")],
               potions=[make_potion("block_potion")])
    PowerCmd.apply(cs.hooks, cs.player, ThornsPower, 3, applier=cs.player)
    order = cs.hooks._ordered()
    assert cs.relics[0] in order
    assert cs.player.potions[0] in order
    assert cs.player.draw_pile[0] in order

    cs.player.is_active_for_hooks = False
    order = cs.hooks._ordered()
    assert cs.player.powers["thorns"] in order      # :416 already added it
    assert cs.relics[0] not in order
    assert cs.player.potions[0] not in order
    assert all(c not in order for c in cs.player.all_cards)
    assert cs.enemy in order                        # the enemy is unaffected


def test_the_player_stops_being_active_for_hooks_once_it_really_dies():
    """`Player.DeactivateHooks` (Player.cs:857-860) is called from
    CreatureCmd.cs:553, in the REAL-death arm only and after Hook.AfterDeath —
    a prevented death (Fairy in a Bottle, Lizard Tail) leaves the flag alone,
    which is the whole reason the flag exists instead of reading IsAlive."""
    from sts2_rl.cmds import CreatureCmd

    cs = fresh()
    assert cs.player.is_active_for_hooks is True
    CreatureCmd.kill(cs.hooks, cs.player)
    assert cs.player.is_dead
    assert cs.player.is_active_for_hooks is False


def test_a_revive_puts_the_player_back_in_the_walk():
    """`Creature.HealInternal` (Creature.cs:477-485) calls
    `Player?.ActivateHooks()` when a heal takes a dead creature back above
    zero. `Player.ReviveBeforeCombatEnd` (:821-827) exists ONLY to exploit
    that before `Hook.AfterCombatEnd`, and Player.cs:816-819 says why: a
    still-dead player's relics "will not be subscribed to the HookBus, and
    relics which rely on AfterCombatEnd to reset state will not be reset for
    the next combat"."""
    from sts2_rl.cmds import CreatureCmd

    cs = fresh(relics=[make_relic("pen_nib")])
    CreatureCmd.kill(cs.hooks, cs.player)
    assert cs.player.is_active_for_hooks is False
    assert cs.relics[0] not in cs.hooks._ordered()

    CreatureCmd.heal(cs.hooks, cs.player, 1)
    assert cs.player.is_active_for_hooks is True
    assert cs.relics[0] in cs.hooks._ordered()


def test_the_victory_path_revives_before_dispatching_after_combat_end():
    """CombatManager.EndCombatInternal (CombatManager.cs:986-988) runs every
    player's ReviveBeforeCombatEnd and only THEN Hook.AfterCombatEnd, so a
    player who won at 0 HP still gets their relics' end-of-combat resets."""
    cs = fresh(relics=[make_relic("chosen_cheese")])
    cs.player.hp = 0
    cs.player.is_active_for_hooks = False        # as a real death would leave it
    before = cs.player.max_hp
    cs._end_combat_internal()
    assert cs.player.is_active_for_hooks is True
    assert cs.player.max_hp == before + 1        # ChosenCheese.cs:16 fired


def test_death_prevention_leaves_the_player_active_for_hooks():
    cs = fresh()

    class _Saviour:
        hook_category = CAT_CARD

        def should_die(self, creature, preventer=None):
            if preventer is not None:
                preventer.append(self)
            return False

    cs.hooks.register(_Saviour())
    from sts2_rl.cmds import CreatureCmd
    CreatureCmd.kill(cs.hooks, cs.player)
    assert cs.player.is_active_for_hooks is True


# ══════════════════════════════════════════════════════════════════════════
# Listeners the walk cannot reach are seated, not dropped
# ══════════════════════════════════════════════════════════════════════════

def test_a_registered_listener_the_walk_cannot_reach_keeps_its_category_slot():
    """C# has no such case, but the sim's registry can outlive the structure:
    an orphaned Instanced power (power_cmd/G5 — C#'s `Creature.Powers` is a
    LIST that keeps both instances where the sim's dict indexes one), a card
    in no pile, a bare object a test registered. `_merge_extras` seats each at
    the end of its (creature, category) group rather than dropping it."""
    cs = fresh(relics=[make_relic("pen_nib")])

    class _PowerSlot:
        hook_category = 0                    # CAT_POWER

    class _Tail:
        hook_category = 99                   # past every declared slot

    power_slot, tail = _PowerSlot(), _Tail()
    cs.hooks.register(power_slot)
    cs.hooks.register(tail)
    log: list = []
    probe(cs, [power_slot, tail, cs.relics[0]], log)
    order = visited(cs)
    assert order == [power_slot, cs.relics[0], tail]


def test_a_played_power_card_stops_listening():
    """A Power card's result pile is `PileType.None`
    (CardModel.GetResultPileTypeForCardPlay, CardModel.cs:2070-2075), which
    CardModel.cs:1979-1982 resolves to `CardPileCmd.RemoveFromCombat` — it
    leaves every combat pile and so leaves `AllPiles`. The sim kept it
    registered for the rest of the combat."""
    cs = fresh()
    cs.player.hand.clear()
    inflame = make_card("inflame")
    cs.player.hand.append(inflame)
    from sts2_rl.cmds import CardPileCmd
    CardPileCmd._enter_combat(cs.hooks, inflame)
    assert inflame in cs.hooks._listeners

    cs.player.energy = 9
    assert cs.play_card(0)
    assert inflame not in cs.hooks._listeners
    assert inflame not in cs.hooks._ordered()


# ══════════════════════════════════════════════════════════════════════════
# Performance contract
# ══════════════════════════════════════════════════════════════════════════

def test_the_presence_gate_stays_above_the_derivation():
    """Requirement 1 of the round-13 performance contract: a dispatch no live
    listener implements must not build the order at all."""
    cs = fresh()
    calls = []
    real = type(cs.hooks)._derive
    try:
        type(cs.hooks)._derive = lambda self, *a, **k: (calls.append(1),
                                                        real(self, *a, **k))[1]
        assert list(cs.hooks._each("no_such_hook_anywhere")) == []
        assert calls == []
    finally:
        type(cs.hooks)._derive = real


def test_a_pile_move_does_not_invalidate_the_presence_cache():
    """Requirement 3: the presence cache keys on listener-SET membership only.
    Moving a card between piles changes the ORDER, never the set, so the
    cached answer must survive it — `_epoch` must not move."""
    cs = fresh()
    cs.hooks._has_listener_for("on_card_drawn")
    epoch = cs.hooks._epoch
    cached = dict(cs.hooks._presence_cache)

    card = cs.player.draw_pile[0]
    cs.player.draw_pile.remove(card)
    cs.player.hand.append(card)

    assert cs.hooks._epoch == epoch
    assert cs.hooks._presence_cache == cached
    assert cs.hooks._ordered()[-1] is cs.enemy      # order still re-derived
    assert cs.hooks._ordered().index(card) < \
        cs.hooks._ordered().index(cs.player.draw_pile[0])
