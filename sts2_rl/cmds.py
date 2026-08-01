"""Command layer — the verbs that mutate combat state, mirroring STS2's Cmd
classes (DamageCmd, CreatureCmd, PowerCmd, ...).

All effects go through a Cmd rather than touching hp/block/powers directly;
that is what keeps hook dispatch correct. The centrepiece is
`DamageCmd.deal`, the full typed damage pipeline (powered modifiers → cap →
on_attacked → block → modify_hp_lost → apply → death check → post-damage
events). Other Cmds cover block, healing/kill/stun/escape/add, applying and
removing powers, strength, drawing, exhausting, afflicting cards, moving
generated cards between piles, in-combat card selection, and energy gain.

Each Cmd is a namespace of @staticmethods taking the `HookSystem` (and usually
a target) explicitly — there is no Cmd instance state.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .valueprops import DamageProps, ValueProp, is_powered_attack

if TYPE_CHECKING:
    from .afflictions import Affliction
    from .cards import Card
    from .creatures import Creature
    from .hooks import HookSystem
    from .player import PlayerCombatState
    from .powers import Power, PowerType


def is_over_or_ending(hooks: HookSystem) -> bool:
    """`CombatManager.Instance.IsOverOrEnding` as a command sees it.

    Nearly every command in the CreatureCmd / CardCmd / CardPileCmd / PowerCmd
    seams opens with one of these two predicates and returns an empty, zero or
    no-op result. The window they guard is real and not the same as "the combat
    object is gone": `IsEnding` goes true the moment the last primary enemy
    dies, which is BEFORE `CheckWinCondition` tears the fight down, so the
    killing blow's own card is still resolving inside it.

    Out of combat there is nothing to guard: C# would answer `!IsInProgress` ==
    true, but every guard that consults it is additionally qualified by "the
    pile is a combat pile" or is only reachable in combat, so `False` here and
    an explicit pile test at the one asymmetric site (`CardCmd.afflict`) is the
    faithful pair.
    """
    # `getattr` on the property too: `hooks.combat` is duck-typed and the
    # event room-entry layout hangs a cut-down stand-in there (a stream bundle
    # with no creatures) purely to roll monster HP. That object is not a combat
    # in progress in any sense, so nothing about it is ending.
    return getattr(getattr(hooks, "combat", None), "is_over_or_ending", False)


def is_ending(hooks: HookSystem) -> bool:
    """`CombatManager.Instance.IsEnding` — the narrower of the two.

    PowerCmd.Apply/ModifyAmount, CardCmd.Transform and CardPileCmd.Add use this
    one, and the difference is deliberate: `IsEnding` opens with
    `if (!IsInProgress) return false` (CombatManager.cs:184-187), so these
    commands still work out of combat. That is what keeps the deck transformers
    and the event card-adds alive.
    """
    return getattr(getattr(hooks, "combat", None), "is_ending", False)


def can_receive_powers(hooks: HookSystem, target: Creature) -> bool:
    """`Creature.CanReceivePowers` (Creature.cs:308-322), both clauses.

    `CombatState == null` (the corpse was REMOVED) OR a listener refusing
    `Hook.ShouldAllowHitting`. Note what is NOT here: `IsDead`. The property's
    doc comment spells the difference out against `IsHittable` — "a creature is
    not hittable if it's dead, but dead creatures can still have powers applied
    to them" — which is why a removal-vetoed corpse keeps taking debuffs.
    """
    return (not target.is_removed_from_combat
            and hooks.should_allow_hitting(target))


def _combat_contains_creature(hooks: HookSystem, creature: Creature) -> bool:
    """`ICombatState.ContainsCreature` (CombatState.cs:306-313): true if
    `creature` is one of the combat's allies or enemies right now.

    C# tests physical list membership; `CombatState.RemoveCreature`
    (CombatState.cs:299-302) is what nulls a removed creature's back-pointer
    and is why membership can go false. The sim never physically drops a
    creature from `combat.enemies` (`Creature.is_removed_from_combat`'s own
    note, creatures.py) — conformance addresses enemies by index — so
    membership here is "is the combat's player, or is one of combat.enemies"
    AND-ed with "not removed", the sim's stand-in for the same fact.

    Consulted only by `PowerCmd.apply`'s given-side gate (`applier != null &&
    combatState.ContainsCreature(applier)`, PowerCmd.cs:122-123, power_cmd/G3
    steps 12 and 27).
    """
    combat = getattr(hooks, "combat", None)
    if combat is None:
        return False
    is_member = (creature is getattr(combat, "player", None)
                 or creature in getattr(combat, "enemies", ()))
    return is_member and not creature.is_removed_from_combat


def should_trigger_fatal(target: Creature) -> bool:
    """`cardPlay.Target.Powers.All(p => p.ShouldOwnerDeathTriggerFatal())`,
    the test Feed.cs:38 and HandOfGreed.cs:49 both take BEFORE their attack.

    `PowerModel.ShouldOwnerDeathTriggerFatal` defaults to true
    (PowerModel.cs:646) and exactly two non-mock powers override it, both
    ported: MinionPower unconditionally (MinionPower.cs:20-23) and
    ReattachPower unless every other segment is already down
    (ReattachPower.cs:106-109). This is NOT death prevention -- the creature
    really dies; only the Fatal payout is suppressed -- which is why the
    `is_dead` check the two cards already had does not cover it.
    """
    return all(p.should_owner_death_trigger_fatal()
               for p in target.powers.values())


def is_hittable(hooks: HookSystem, target: Creature) -> bool:
    """`Creature.IsHittable` (Creature.cs:285-299) — `!IsDead &&
    Hook.ShouldAllowHitting`. The stricter of the pair: this one DOES exclude a
    corpse, which is what makes `CombatState.HittableEnemies` (CombatState.cs:142)
    a smaller set than "the enemies still in the fight"."""
    return not target.is_gone and hooks.should_allow_hitting(target)


def _resolve_death(hooks: HookSystem, target: Creature) -> None:
    """CreatureCmd.KillWithoutCheckingWinCondition's two arms
    (CreatureCmd.cs:504-570), shared by every path that can bring a creature to
    0 HP.

    Both arms dispatch `Hook.AfterDeath` — the real one with
    `wasRemovalPrevented: false` (CreatureCmd.cs:519), the prevented one with
    `true` (CreatureCmd.cs:566) — and neither floors the creature's HP. The
    prevented creature is left DEAD AT 0 and the preventer is expected to heal
    it; C# then re-kills it if nobody did.

    The real-death arm's own gate is `force || creature.MaxHp <= 0 ||
    Hook.ShouldDie(...)` (CreatureCmd.cs:505, read live on every call, not
    passed in by whichever caller reached it) — a short-circuit OR, so
    whenever `target.max_hp <= 0` the whole `ShouldDie` consultation is
    skipped and death is unconditional: no listener (Lizard Tail, Fairy in a
    Bottle, Torii) is ever asked, and none of their charges are spent. This
    is reachable in the sim only through `CreatureCmd.set_max_hp`'s own
    `MaxHp <= 0` branch (tier-2 Task 19, mechanism E) and, while it's still
    true, any death that follows it — e.g. `set_max_and_current_hp`'s own
    trailing `set_current_hp` call. Ordinary damage-driven death
    (`DamageCmd.deal`, `CreatureCmd.kill`) always has a positive `max_hp`,
    so this clause is inert for them and `should_die` still runs normally —
    a death-prevention listener genuinely CAN save a creature from an
    ordinary max-HP-loss hit (the damage `lose_max_hp` deals through
    `DamageCmd.deal` before this ever runs), just not from the floor-driven
    Kill afterwards.
    """
    preventer: list = []
    if target.max_hp <= 0 or hooks.should_die(target, preventer):
        # CreatureCmd.cs:508 — the death stands; a listener may still keep the
        # corpse in the combat rather than removing it (Decimillipede's
        # ReattachPower).
        target.retained_after_death = (
            not hooks.should_remove_from_combat_after_death(target)
        )
        hooks.on_death(target, False)
        # CreatureCmd.cs:523-531 — the REMOVAL, two statements after
        # Hook.AfterDeath (:519) and one before the power strip (:533-537).
        # `CombatState.RemoveCreature` (CombatState.cs:299-302) is what nulls
        # `Creature.CombatState`, so everything above this line — ShouldDie
        # (:505), ShouldCreatureBeRemovedFromCombatAfterDeath (:508) and
        # AfterDeath itself — ran with the dying creature still IN the combat
        # and therefore still a hook listener (the MonsterModel arm of
        # `Contains`, :585, tests that back-pointer and nothing else). That is
        # why the commit is an explicit flag rather than a read of
        # `is_removed_from_combat`, which is `is_gone and not
        # retained_after_death` and so goes true the moment HP hits zero —
        # see `Monster.combat_removal_committed`.
        #
        # Three gates, all from :523-531: enemies only (a dead PLAYER stays in
        # the combat, Player.cs:103-111), the removal must have been agreed
        # (`retained_after_death` is the cached answer), and `:527` refuses
        # while the monster is performing its move — `CombatState.
        # _run_enemy_turns` completes that deferred case, mirroring
        # MonsterModel.cs:448-451.
        if (target.side == "enemy"
                and not target.retained_after_death
                and not getattr(target, "is_performing_move", False)):
            target.combat_removal_committed = True
        _strip_powers_after_death(hooks, target)
        # CreatureCmd.cs:546-553 — the player-only tail of the real-death arm,
        # after Hook.AfterDeath (:519) and after the power strip (:533-537):
        # `player.DeactivateHooks()` (Player.cs:857-860). From here the
        # player's relics, potions, orbs and cards stop being listeners, both
        # structurally (CombatState.cs:424-427) and through the owner leg of
        # every `Contains` arm (:589-597). C# also drops the player's POWERS
        # here — they are added to the list at :416, before the structural
        # skip, but the PowerModel arm of Contains (:599) tests
        # `Owner.Player?.IsActiveForHooks ?? true` and this owner IS a player.
        # The sim cannot honour that leg from inside this footprint (`Power`
        # has no `hook_contains`; the exact one-line diff is in the round-13
        # R1 report), and it is moot in practice: the strip above has already
        # removed every power that does not override
        # `should_power_be_removed_after_owner_death`.
        #
        # Only reached when the death is real: the prevented arm below leaves
        # the flag alone, which is the whole reason the flag exists rather
        # than reading `is_dead`.
        if getattr(target, "side", None) == "player":
            target.is_active_for_hooks = False
    else:
        # CreatureCmd.cs:565-570. The creature stays at 0 HP: `AfterDeath`
        # fires with wasRemovalPrevented=True, then the preventer is notified
        # so a healing one (Fairy in a Bottle) can top it up. The sim used to
        # floor it at 1 HP here, which is the HP number conformance asserts on
        # and the reason Feed never scored a kill on the Test Subject.
        #
        # The else-arm contains no removal logic at all, so a creature whose
        # death is prevented always stays in the fight: dead at 0 HP and still
        # taking its turns, which is how Illusion's and Adaptable's revive
        # moves get to run. Same shape as a withered Decimillipede segment.
        target.retained_after_death = True
        hooks.on_death(target, True)
        hooks.after_preventing_death(preventer, target)


def _strip_powers_after_death(hooks: HookSystem, target: Creature) -> None:
    """Creature.RemoveAllPowersAfterDeath (Creature.cs:668-671) + the
    `AfterRemoved` tail CreatureCmd.cs:533-537 awaits for each stripped power.

    Strip is the DEFAULT: `PowerModel.ShouldPowerBeRemovedAfterOwnerDeath`
    returns true (PowerModel.cs:637-640) and only six non-mock powers override
    it, while `Hook.ShouldPowerBeRemovedOnDeath` has exactly one implementer in
    the whole game (IllusionPower.cs:59-66). Escape strips silently and takes a
    different path — this is the death arm only.
    """
    doomed = [p for p in list(target.powers.values())
              if p.should_power_be_removed_after_owner_death()
              and hooks.should_power_be_removed_on_death(p)]
    for power in doomed:
        power._expire()
    for power in doomed:
        power.on_removed(target)


class DamageResult:
    """`DamageResult` (DamageResult.cs) as the two cards that read one need it.

    `TotalDamage` is `BlockedDamage + UnblockedDamage` (:63-64) and
    `OverkillDamage` is the excess beyond the target's HP, so
    `TotalDamage + OverkillDamage` -- the quantity Fisticuffs and Omnislice
    both sum -- is the ENTIRE post-modifier damage the attack put out.

    `DamageCmd.deal`'s int return is `hp_lost`, which is the post-block,
    post-`modify_hp_lost` amount and is never clamped to the target's HP, so it
    already equals `UnblockedDamage + OverkillDamage`. The only missing term
    was the BLOCKED one, and that is what this object carries back.
    """

    __slots__ = ("blocked_damage", "hp_lost")

    def __init__(self) -> None:
        self.blocked_damage = 0
        self.hp_lost = 0

    @property
    def total_plus_overkill(self) -> int:
        """`r.TotalDamage + r.OverkillDamage`."""
        return self.blocked_damage + self.hp_lost


class DamageCmd:
    @staticmethod
    def deal(
        hooks: HookSystem,
        target: Creature,
        amount: int,
        dealer: Creature | None = None,
        card: Card | None = None,
        props: ValueProp | None = None,
        result: "DamageResult | None" = None,
    ) -> int:
        """Full damage pipeline. Returns actual HP lost (after block and modifiers).

        props types the damage (mirrors STS2 ValueProp). When omitted it is
        inferred: card/monster attack damage (MOVE), downgraded to unpowered
        for cards marked is_unpowered.
        """
        if props is None:
            if card is not None and card.is_unpowered:
                props = DamageProps.CARD_UNPOWERED
            else:
                props = DamageProps.CARD  # == MONSTER_MOVE
        # CreatureCmd.cs:242-245, the FIRST statement of CreatureCmd.Damage:
        # a dead dealer deals nothing — the call returns an empty DamageResult
        # per target rather than running the pipeline. Reachable now that
        # ThornsPower names its dealer: a multi-hit attacker killed by the
        # first hit's reflect must not land the rest of the attack.
        if dealer is not None and dealer.is_dead:
            return 0
        # CreatureCmd.cs:256-259, the per-target loop's FIRST statement (the
        # sim's single-target `deal` stands in for one iteration of that
        # loop — see guard N2): `originalTarget.IsDead -> continue` skips an
        # already-dead target before ModifyDamage or any other hook runs.
        # IsDead == !IsAlive == CurrentHp <= 0 (Creature.cs:206-208), the same
        # predicate the sim's `is_dead` already is — not `is_gone` (which
        # would also catch an escaped-but-alive creature C# does not skip
        # here). A withered, retained Decimillipede segment (hp <= 0,
        # `retained_after_death`) is ALSO `is_dead` for the whole window it
        # is unhittable, so this guard alone reproduces that case; the sim's
        # `should_allow_hitting` hook (guard N1) exists for the same segment
        # but is not made redundant by this — it is the documented
        # C#-has-no-single-hook-here divergence, kept as is.
        if target.is_dead:
            return 0
        if not hooks.should_allow_hitting(target):
            return 0

        # 1. The source card's own enchantment first, then the listener passes.
        #    Hook.ModifyDamage (Hook.cs:1487-1499) folds EnchantDamageAdditive
        #    and then EnchantDamageMultiplicative into the running amount
        #    BEFORE either listener loop, so a Corrupted Strike (base 6) with
        #    Strength 3 is 6*1.5 = 9 then +3 = 12, not 6+3 = 9 then *1.5 = 13.
        ench = card.enchantment if card is not None else None
        if ench is not None:
            amount += ench.enchant_damage_additive(amount, props)
            amount *= ench.enchant_damage_multiplicative(amount, props)

        # 2. Additive then multiplicative modifiers (Strength, Vulnerable, Weak).
        #    EVERY listener is called for EVERY damage: ModifyDamageInternal
        #    (Hook.cs:2515-2538) has no props gate and leaves the
        #    IsPoweredAttack test to each implementation. Hoisting it here
        #    silently dropped the listeners that deliberately do NOT gate on
        #    Unpowered — Vambrace.cs:59-63, PaelsLegion.cs:132-134 and
        #    UnmovablePower.cs:27-30 all self-gate on Move ALONE.
        dmg_modifiers: list = []
        amount = hooks.modify_damage_additive(
            target, amount, dealer, card, dmg_modifiers, props)
        amount = int(hooks.modify_damage_multiplicative(
            target, amount, dealer, card, dmg_modifiers, props))
        if dmg_modifiers:
            hooks.after_modify_damage_amount(dmg_modifiers, target)

        # 3. Damage cap (e.g. Intangible: cap at 1) — applies to all damage types
        cap = hooks.modify_damage_cap(target, dealer, card)
        if cap is not None:
            amount = min(amount, cap)

        amount = max(0, amount)

        # 4. Pre-block hit event for attacks (e.g. CurlUp triggers even when
        #    block absorbs). Non-move damage (Poison, Thorns) is not a "hit".
        if amount > 0 and ValueProp.MOVE in props:
            hooks.on_attacked(target, amount, dealer, card)

        # 4b. Hook.BeforeDamageReceived (CreatureCmd.cs:263) — after the
        #     modifier passes, before block absorption, and NOT subject to the
        #     killing-blow skip. Thorns reflects from here.
        hooks.before_damage_received(target, amount, dealer, card, props)

        # 5. Block absorption (skipped for unblockable HP loss like Poison)
        hp_lost = amount
        absorbed = 0   # tracked outside the `if` for step 9's WasFullyBlocked
        if target.block > 0 and ValueProp.UNBLOCKABLE not in props:
            absorbed = min(target.block, amount)
            target.block -= absorbed
            hp_lost -= absorbed
            if result is not None:
                result.blocked_damage = absorbed   # DamageResult.BlockedDamage
            # WasBlockBroken (CreatureCmd.cs): Block <= 0 && blockedDamage > 0
            # — an exact break counts; overflow damage is not required.
            if target.block == 0:
                hooks.on_block_broken(target, dealer, card)

        # 6. HP-loss modifiers applied after block (e.g. Torii: cap at 1, Tungsten Rod: -1)
        if hp_lost > 0:
            modifiers: list = []
            hp_lost = hooks.modify_hp_lost(target, hp_lost, dealer, card, modifiers)
            hooks.after_modify_hp_lost(modifiers, target)
        if result is not None:
            result.hp_lost = hp_lost

        # 7. Apply HP loss
        if hp_lost > 0:
            old_hp = target.hp
            target.hp = max(0, target.hp - hp_lost)
            hooks.on_hp_changed(target, target.hp - old_hp)

            # The killing-blow skip decision (step 9 below) is a SNAPSHOT
            # taken here, immediately after the HP write and before death
            # resolution runs — mirroring Creature.LoseHpInternal's
            # WasTargetKilled (Creature.cs:445-457) plus the live IsDead read
            # CreatureCmd.cs:392 makes, both of which happen strictly BEFORE
            # `Kill()` (CreatureCmd.cs:409). Kill() is what runs
            # ShouldDie/ShouldDieLate and a preventer's own synchronous heal
            # (LizardTail.AfterPreventingDeath, LizardTail.cs:53-59), so a
            # death that gets prevented-and-healed can never un-skip the
            # decision in C#. See guard G4 / damage_pipeline step 17.5 — this
            # used to be a live `target.is_dead` re-read taken AFTER
            # `_resolve_death` (below), which let a Lizard Tail heal
            # resurrect Centennial Puzzle's draw.
            was_lethal = target.is_dead

            # 8. Death check — listeners can prevent death (e.g. Fairy in a Bottle)
            if target.hp <= 0:
                _resolve_death(hooks, target)
        else:
            # No HP was lost this call, so death resolution never runs below
            # either way — reading the snapshot here is exactly the live
            # value step 9 would have read under the old, unsnapshotted code.
            was_lethal = target.is_dead

        # 9. Post-damage events. AfterDamageGiven (dealer side, unconditional)
        #    fires BEFORE the killing-blow-guarded AfterDamageReceived
        #    (CreatureCmd.cs:388-395) — swapped from the sim's historical
        #    victim-then-dealer order to match. See guard G6 / damage_pipeline
        #    step 17.4. A killing blow skips the victim's AfterDamageReceived
        #    (CreatureCmd.cs:392 — `!WasTargetKilled || !IsDead`, captured as
        #    `was_lethal` above): the hit that kills a creature does not
        #    trigger its on-damage-received powers (e.g. PersonalHive
        #    shuffles no Dazed on the hit that kills its owner).
        #    AfterDamageGiven (on_damage_dealt) is not killing-blow guarded
        #    and still fires on the kill.
        #
        #    C#'s dispatch (CreatureCmd.cs:390) is `if (combatState != null)
        #    { await Hook.AfterDamageGiven(...) }` — no amount/hp_lost test at
        #    all, so it sees a fully-blocked or zero-damage hit exactly like
        #    every other one; `result.WasFullyBlocked` (DamageResult.cs) is a
        #    field listeners are expected to read (ImbalancedPower.cs:19). The
        #    sim used to require `hp_lost > 0`, which made a fully-blocked hit
        #    invisible to the dealer-side event (power/_after_damage_given_
        #    substitution, tier-2 Task 26) — dropped here; only the
        #    `dealer is not None` half remains, since there is no dealer to
        #    attribute the event to otherwise.
        #    `was_fully_blocked` mirrors `WasFullyBlocked` (CreatureCmd.cs:268
        #    `!props.HasFlag(Unblockable) && (blockedDamage > 0 ||
        #    originalTarget.Block > 0) && (int)unblockedDamage == 0`): not
        #    unblockable, some block was in play (this hit absorbed some, or
        #    the target still has block left), and the FINAL hp_lost is 0.
        was_fully_blocked = (
            ValueProp.UNBLOCKABLE not in props
            and (absorbed > 0 or target.block > 0)
            and hp_lost == 0
        )
        if dealer is not None:
            hooks.on_damage_dealt(dealer, target, hp_lost, card, props,
                                   was_fully_blocked)
        if not was_lethal:
            hooks.on_damage_received(target, hp_lost, dealer, card, props)

        # AttackCommand.Results: every hit of the attack currently bracketed by
        # before_attack / after_attack, for the listeners that read them
        # (SuckPower.cs:28-41, PainfulStabsPower.cs:40-44).
        if hooks._attack_results is not None:
            hooks._attack_results.append((target, hp_lost))

        return hp_lost


class BlockCmd:
    @staticmethod
    def apply(
        hooks: HookSystem,
        target: Creature,
        amount: int,
        card: Card | None = None,
        props: ValueProp | None = None,
    ) -> int:
        """Apply block through the hook pipeline. Returns final block gained.

        `Hook.ModifyBlock` (Hook.cs:1310-1340) calls every listener for every
        block gain and lets each self-gate on props; Dexterity, Frail and
        Fasten do, while Vambrace, Pael's Legion and Unmovable deliberately
        gate on Move ALONE and so must still run for Unpowered block.
        """
        # CreatureCmd.cs:637-640 — the whole command is skipped once the combat
        # is over or ending, hooks and all.
        if is_over_or_ending(hooks):
            return 0
        if props is None:
            props = ValueProp.MOVE
        # CreatureCmd.cs:642 — Hook.BeforeBlockGained, unconditional, fired
        # with the RAW amount before the enchantment fold and before
        # ModifyBlock's chain (tier-2 Task 11, item A; creature_card_cmds/
        # step12, dormant).
        hooks.before_block_gained(target, amount, card, props)
        # The source card's own enchantment folds in before either listener
        # loop (Hook.cs:1315-1320), like the damage side.
        ench = card.enchantment if card is not None else None
        if ench is not None:
            amount += ench.enchant_block_additive(amount, props)
            amount *= ench.enchant_block_multiplicative(amount, props)
        blk_modifiers: list = []
        amount = hooks.modify_block_additive(
            target, amount, card, blk_modifiers, props)
        amount = int(hooks.modify_block_multiplicative(
            target, amount, card, blk_modifiers, props))
        amount = max(0, amount)
        # CreatureCmd.cs:644-646 — Max(modifiedAmount, 0) and then
        # Hook.AfterModifyingBlockAmount, BOTH before the `if (modifiedAmount
        # > 0m)` block that calls GainBlockInternal (:647-651). The dispatch
        # is unconditional; it is the LISTENERS that open on `<= 0`.
        if blk_modifiers:
            hooks.after_modify_block_amount(blk_modifiers, target, amount, card)
        target.block += amount
        hooks.on_block_gained(target, amount, card)
        return amount

    @staticmethod
    def lose_block(hooks: HookSystem, target: Creature, amount: int) -> None:
        """Remove block outside the damage pipeline (mirrors CreatureCmd.
        LoseBlock, CreatureCmd.cs:666-678; creature_card_cmds/step18).

        Three guards folded into one `if`, all C#'s: not over/ending, target
        not dead, amount positive. `LoseBlockInternal` (Creature.cs:468-475)
        floors at 0; when the target HELD block beforehand and now has none,
        `AfterBlockBroken` re-fires -- with NO dealer/card, unlike the
        damage pipeline's own call (DamageCmd.deal step 5's `on_block_broken
        (target, dealer, card)`) -- exactly mirroring C#'s two-argument
        `Hook.AfterBlockBroken(creature.CombatState, creature)` call here.
        BurrowedPower's `AfterRemoved` is the one ported caller
        (`CreatureCmd.LoseBlock(oldOwner, 999999999m)`, BurrowedPower.cs:40).
        """
        if is_over_or_ending(hooks) or target.is_dead or amount <= 0:
            return
        block = target.block
        target.block = max(0, target.block - amount)
        if block > 0 and target.block <= 0:
            hooks.on_block_broken(target)


class CreatureCmd:
    """Creature-level verbs beyond plain damage (mirrors STS2's CreatureCmd)."""

    @staticmethod
    def heal(hooks: HookSystem, target: Creature, amount: int) -> int:
        """Heal up to amount HP, capped at max HP. Returns HP actually restored.

        `CreatureCmd.Heal` (CreatureCmd.cs:691-697) has NO dead-creature guard
        — its only early return is `IsEnding && !IsPlayer`. The sim's old
        `if target.is_dead: return 0` was safe only while a prevented death was
        floored at 1 HP; now that the corpse is left at 0 (CreatureCmd.cs:565),
        that guard would block the very revives it exists for — Illusion's
        REVIVE move and Adaptable's respawn both heal a creature that is dead
        at 0 and retained in combat.
        """
        combat = getattr(hooks, "combat", None)
        if (combat is not None and getattr(combat, "is_over", False)
                and target.side != "player"):
            return 0
        was_dead = target.is_dead
        healed = min(amount, target.max_hp - target.hp)
        if healed > 0:
            target.hp += healed
        # `Creature.HealInternal` (Creature.cs:477-485): a heal that takes a
        # DEAD creature back above zero calls `Player?.ActivateHooks()`
        # (Player.cs:868-871), putting the player's relics, potions and cards
        # back in the listener walk. Without this the revive
        # `ReviveBeforeCombatEnd` performs (Player.cs:821-827) would be
        # pointless -- its whole documented purpose (:816-819) is that "if the
        # player is still dead during HookBus.AfterCombatEnd, their relics will
        # not be subscribed to the HookBus, and relics which rely on
        # AfterCombatEnd to reset state will not be reset for the next combat".
        # `_resolve_death` is what cleared the flag; this is its one reversal.
        if was_dead and not target.is_dead and getattr(
                target, "side", None) == "player":
            target.is_active_for_hooks = True
        # CreatureCmd.cs:751-754 -- Hook.AfterCurrentHpChanged fires whenever
        # the REQUESTED amount is positive, carrying that RAW amount -- NOT
        # the clamped `healed` -- and fires even when healed is 0 (already at
        # full HP). creature_card_cmds/G5 + step22: the sim used to gate on
        # `healed > 0` and report `healed`; dormant because the only ported
        # on_hp_changed listener, Red Skull, ignores the delta and
        # recomputes its strength idempotently from current HP.
        if amount > 0:
            hooks.on_hp_changed(target, amount)
        return healed

    @staticmethod
    def gain_max_hp(hooks: HookSystem, target: Creature, amount: int) -> None:
        """Raise max HP, then heal the same amount (mirrors
        CreatureCmd.GainMaxHp: SetMaxHp followed by Heal). Used by Fruit
        Juice; RunState.gain_max_hp is the out-of-combat twin."""
        if amount <= 0:
            return
        target.max_hp += amount
        CreatureCmd.heal(hooks, target, amount)

    @staticmethod
    def lose_max_hp(
        hooks: HookSystem, target: Creature, amount: int,
        from_card: bool = False,
    ) -> None:
        """Reduce max HP by amount (mirrors CreatureCmd.LoseMaxHp,
        CreatureCmd.cs:811-828; creature_card_cmds/G6 + step28/step29).

        The ORDER is load-bearing: `newMaxHp = MaxHp - amount` is computed
        UNFLOORED, and when that undercuts CurrentHp, the difference is
        dealt as Unblockable|Unpowered damage (`+Move` when `from_card` --
        C#'s `isFromCard`, which is how Rupture-style triggers tell a
        card-sourced max-HP loss from a power's) through the FULL damage
        pipeline (hooks, death check, Kill) -- and only AFTERWARDS does
        MaxHp floor at 1 (`set_max_hp`). The sim used to floor MaxHp first
        and clamp HP with a bare `on_hp_changed`, so no modify_hp_lost /
        on_damage_received / should_die / on_death ever fired and no
        creature could die of max-HP loss: a 10/10 creature losing 30 max HP
        now takes 30 unblockable damage and can die, where it used to end
        alive at 1/1.

        `set_max_hp`'s own MaxHp<=0 Kill branch is unreachable from here --
        the floor passed to it is always >= 1 -- but stays live for
        `set_max_and_current_hp`'s direct callers.
        """
        if amount <= 0:
            return
        new_max_hp = target.max_hp - amount        # UNFLOORED -- may go negative
        if new_max_hp < target.hp:
            props = DamageProps.CARD_HP_LOSS if from_card else DamageProps.NON_CARD_HP_LOSS
            DamageCmd.deal(hooks, target, target.hp - new_max_hp, props=props)
        CreatureCmd.set_max_hp(hooks, target, max(1, new_max_hp))

    @staticmethod
    def set_max_hp(hooks: HookSystem, target: Creature, amount: int) -> int:
        """Set max HP to a new value (mirrors CreatureCmd.SetMaxHp,
        CreatureCmd.cs:839-849; creature_card_cmds/step26). Returns the
        delta applied (new MaxHp - old MaxHp).

        `SetMaxHpInternal` (Creature.cs:493-501) floors the new MaxHp at 0
        and SILENTLY clamps CurrentHp down to it -- no `AfterCurrentHpChanged`
        fires for that clamp; only a caller's own separate HP-changing step
        (the `DamageCmd.deal` in `lose_max_hp`, or `set_current_hp` in
        `set_max_and_current_hp`) fires one. If MaxHp lands at or below 0,
        the creature is killed (:844-847) through `_resolve_death` directly
        -- not through `CreatureCmd.kill`, whose own `if target.is_dead:
        return` entry guard would no-op here, since HP is already clamped to
        <= 0 by the line above by the time this check runs. Unreachable from
        `lose_max_hp` (which always floors the amount it passes here at 1);
        live for a direct `set_max_and_current_hp` caller passing <= 0.

        This branch is exactly `_resolve_death`'s own `target.max_hp <= 0`
        short-circuit (CreatureCmd.cs:844-846's `force || MaxHp <= 0 ||
        ShouldDie(...)`) -- Hook.ShouldDie is never consulted here, so no
        death-prevention listener gets a veto or spends a charge, unlike an
        ordinary damage-driven death (the Unblockable hit `lose_max_hp`
        deals through `DamageCmd.deal` beforehand IS still preventable --
        only the floor's own Kill is unconditional).
        """
        old_max_hp = target.max_hp
        target.max_hp = max(0, amount)
        target.hp = min(target.hp, target.max_hp)
        if target.max_hp <= 0:
            _resolve_death(hooks, target)
        return target.max_hp - old_max_hp

    @staticmethod
    def set_current_hp(hooks: HookSystem, target: Creature, amount: int) -> None:
        """Set current HP to a new value through the death pipeline (mirrors
        CreatureCmd.SetCurrentHp, CreatureCmd.cs:762-779;
        creature_card_cmds/step23).

        `SetCurrentHpInternal` (Creature.cs:488-491) clamps the new value to
        MaxHp only -- no floor -- so, like the property setter C# leans on
        to catch the mistake, callers must not pass a negative amount.
        `AfterCurrentHpChanged` fires whenever the RAW requested `amount`
        differs from the OLD CurrentHp, carrying `amount - old` as the
        delta -- like Heal (creature_card_cmds/G5), this is the raw
        requested value, not the clamped one actually applied. A creature
        left dead afterwards is killed through `_resolve_death` directly,
        the same reasoning as `set_max_hp` above: HP is already at (or
        below) zero by the time this runs. `_resolve_death`'s own
        `target.max_hp <= 0` short-circuit is a LIVE read, not something
        this method decides -- called on its own with a positive `max_hp`
        (the ordinary case) `should_die` still runs normally, but reached
        through `set_max_and_current_hp` with `amount <= 0`, `max_hp` is
        already 0 from the `set_max_hp` call just before it, so this pass
        skips `should_die` too.
        """
        old_hp = target.hp
        target.hp = min(amount, target.max_hp)
        if amount != old_hp:
            hooks.on_hp_changed(target, amount - old_hp)
        if target.is_dead:
            _resolve_death(hooks, target)

    @staticmethod
    def set_max_and_current_hp(hooks: HookSystem, target: Creature, amount: int) -> None:
        """Set both max and current HP to the same new value (mirrors
        CreatureCmd.SetMaxAndCurrentHp, CreatureCmd.cs:856-860;
        creature_card_cmds/step26). SetMaxHp runs first: for the ported
        callers' strictly-positive amounts its own Kill branch and its
        silent CurrentHp-down-clamp are both no-ops, but they still run in
        the C#-mandated order.

        For `amount <= 0` both of the resulting `_resolve_death` passes --
        `set_max_hp`'s own and `set_current_hp`'s trailing one -- skip
        `Hook.ShouldDie` (`target.max_hp` is already <= 0 for both calls),
        so no death-prevention listener is ever consulted or spends a
        charge on either pass; the creature simply dies, matching C#'s own
        live re-read of `MaxHp` inside `KillWithoutCheckingWinCondition`."""
        CreatureCmd.set_max_hp(hooks, target, amount)
        CreatureCmd.set_current_hp(hooks, target, amount)

    @staticmethod
    def kill(hooks: HookSystem, target: Creature) -> None:
        """Set HP to 0 through the death-prevention pipeline (mirrors Kill)."""
        if target.is_dead:
            return
        old_hp = target.hp
        target.hp = 0
        hooks.on_hp_changed(target, -old_hp)
        _resolve_death(hooks, target)

    @staticmethod
    def stun(hooks: HookSystem, target: Creature, next_move_key: str | None = None) -> None:
        """Stun a creature: it skips its next turn (mirrors CreatureCmd.Stun).

        next_move_key overrides the move performed after the stunned turn (the
        source's nextMoveId); by default the creature repeats the move it was
        telegraphing (`StateLog.Last().Id`, Creature.cs:531-535).

        For a MachineMonster this is a MACHINE operation, not a boolean:
        Creature.StunInternal force-sets a real synthetic "STUNNED" MoveState
        through SetMoveImmediate, which REFUSES the override while the pending
        move is pinned by MustPerformOnceBeforeTransitioning
        (MonsterModel.cs:420-432) — that is also what stops a second stun
        landing on an already-stunned creature. Hand-rolled monsters have no
        machine and keep the `_move_key` override.
        """
        machine = getattr(target, "machine", None)
        if machine is not None:
            if not machine.current.can_transition_away:
                return
            target._current_move = machine.stun(next_move_key)
        elif next_move_key is not None and hasattr(target, "_move_key"):
            target._move_key = next_move_key
        target.stunned = True
        hooks.on_stunned(target)

    @staticmethod
    def escape(hooks: HookSystem, creature: Creature) -> None:
        """Remove a creature from combat without killing it (mirrors
        `CreatureCmd.Escape`, CreatureCmd.cs:579-603).

        Escaped creatures no longer act, cannot be targeted, and count as gone
        for the win condition.

        creature_card_cmds/G13 + step8: `RemoveAllPowersInternalExcept()`
        (:589) strips EVERY power via `PowerModel.RemoveInternal`
        (Creature.cs:658-666) — silently, with NO `AfterRemoved` awaited.
        This is the deliberate contrast with death (`_strip_powers_after_death`
        above, CreatureCmd.cs:533-537), which DOES await one per power. C#
        passes no `except` list here (unlike `RemoveAllPowersAfterDeath`'s
        survivor filter), so every power goes, no exceptions. `Power._expire()`
        is the sim's own existing no-`on_removed` primitive for exactly this
        shape (already used by `PowerCmd.apply`'s re-stack-to-zero branch and
        `PowerCmd.modify_amount`'s duration-tick expiry) — reused here rather
        than hand-rolling a second one. The list is snapshotted BEFORE
        mutating (mirroring `_strip_powers_after_death`'s own
        snapshot-then-mutate two-pass shape): `BattlewornDummyTimeLimitPower`
        calls this method on ITS OWN owner from inside its own hook, so the
        power being stripped can be the very listener whose method is on the
        call stack.

        `on_creature_escaped` has no C# hook counterpart — it is one of the
        sim-only dispatch names hooks.py's own architecture comment already
        documents and accepts (alongside on_stunned/on_hp_changed/
        on_extra_turn, hooks.py:83-86) — kept unchanged; nothing in the C#
        Escape path (`CombatManager.RemoveCreature`, `CombatState.
        CreatureEscaped`) dispatches a Hook.AfterX either.
        """
        if creature.is_dead or creature.escaped:
            return
        for power in list(creature.powers.values()):
            power._expire()
        creature.escaped = True
        # CreatureCmd.cs:601 — `creature.CombatState?.CreatureEscaped(creature)`
        # -> `CombatState.CreatureEscaped` (CombatState.cs:266-270) ->
        # `RemoveCreature`, which nulls the back-pointer. The escape path has
        # no hook to consult and always removes, so the commit is
        # unconditional. See `Monster.combat_removal_committed`.
        if creature.side == "enemy":
            creature.combat_removal_committed = True
        hooks.on_creature_escaped(creature)
        # Escaping can end the fight (mirrors CheckWinCondition after Escape).
        combat = hooks.combat
        if combat is not None and not combat.is_over and combat._all_enemies_dead():
            combat._end_combat(player_won=True)

    @staticmethod
    def add(
        hooks: HookSystem, creature: Creature, index: int | None = None,
        slot_name: str | None = None,
    ) -> None:
        """Add a creature to combat mid-fight (mirrors CreatureCmd.Add), firing
        the added-to-combat hook so powers can react.

        `slot_name` is the NAMED `Encounter.Slots` entry the spawn occupies, and
        it is how the game decides position: CreatureCmd.cs:68-69 calls
        CombatState.AddCreature (which APPENDS, CombatState.cs:534-547) and then
        CombatManager.AddCreature, which runs `_state.SortEnemiesBySlotName()`
        whenever `creature.SlotName != null` (CombatManager.cs:841-851) — sorting
        the whole enemy list by `Encounter.Slots.IndexOf(SlotName)`
        (CombatState.cs:495-501). Pass it and the re-sort happens here too.

        `index` is the older, positional escape hatch for spawns whose position
        the sim had to approximate before the slot row existed; None appends,
        which is right for every spawn with no slot rule.
        """
        combat = hooks.combat
        if combat is None:
            return
        # Parity: roll the spawn's unique HP on the Niche stream BEFORE it joins
        # the enemy list, mirroring CombatState.CreateCreature (SetUniqueMonster-
        # HpValue against the creatures already on the side) then AddCreature.
        # The HP roll excludes sibling MaxHps for uniqueness and so is
        # insertion-order-independent (same existing enemy set either way).
        combat.assign_parity_hp(creature)
        # Stable creature id (CombatState.CombatId), continuing the combat's
        # counter — assigned in ATTACH (creation) order regardless of the slot
        # the creature is inserted at, so recorded targets stay valid.
        counter = getattr(combat, "_net_id_counter", None)
        if counter is not None:
            creature.net_id = counter
            combat._net_id_counter = counter + 1
        if index is None:
            combat.enemies.append(creature)
        else:
            combat.enemies.insert(index, creature)
        if slot_name is not None:
            creature.slot_name = slot_name
            combat.sort_enemies_by_slot_name()
        # CreatureCmd.cs:70 — AfterCreatureAdded runs after the slot re-sort
        # and before Hook.AfterCreatureAddedToCombat (:80). It rolls the
        # spawn's opening move only on the player side; a summon that happens
        # during the enemy's own turn (every monster SUMMON move) is left on
        # UNSET_MOVE for the next player-turn-start pass to pick up.
        combat.after_creature_added(creature)
        hooks.on_creature_added(creature)


class PowerCmd:
    @staticmethod
    def apply(
        hooks: HookSystem,
        target: Creature,
        power_cls: type[Power],
        amount: int,
        applier: Creature | None = None,
    ) -> None:
        """
        Apply a power to a creature.

        Debuffs are intercepted by Artifact (one stack consumed per debuff blocked).
        If the power is already present on the target, on_stack() is called instead
        of creating a new instance.
        """
        from .powers import PowerInstanceType, PowerType

        # PowerCmd.cs:69-72 — Apply<T> opens on `IsEnding -> return null`, and
        # ModifyAmount re-tests it for the stacking branch (:217-220). The sim
        # has ONE code path, so the single entry guard covers both C# sites.
        # `IsEnding`, not `IsOverOrEnding`: that is what lets the out-of-combat
        # callers through.
        if is_ending(hooks):
            return

        # PowerCmd.Apply<T> refuses to apply anything to a creature
        # CanReceivePowers says no to (PowerCmd.cs:73-76). Round 6 wired the
        # ShouldAllowHitting half; the `CombatState == null` half arrived with
        # round 7, and it is what the ten card sites in this family were
        # standing in for with a hand-rolled `if not target.is_gone:`. That
        # stand-in was wrong in both directions: it refused a removal-vetoed
        # corpse the game still powers, and — for every OTHER caller, which had
        # no guard at all — it let an ordinary corpse be powered.
        if not can_receive_powers(hooks, target):
            return

        # PowerCmd.cs:165-174 — FindExistingInstanceForStacking dispatches on
        # PowerInstanceType (PowerModel.cs:144; power_cmd/G5). NONE (the
        # default) finds the target's existing instance by id, as before.
        # INSTANCED never finds one — every application starts its own,
        # independently ticking/expiring instance. INSTANCED_PER_APPLIER
        # finds one only if it shares this application's applier; a
        # different applier starts its own instance too. `target.powers`
        # still holds one dict slot per id, so a forced "not found" below
        # falls into the new-instance branch, which OVERWRITES that slot —
        # the instance it replaces is not touched or unregistered, so it
        # keeps ticking toward its own expiry via the hook system (which
        # dispatches from its own listener list, not from `target.powers`);
        # only a direct `target.powers` lookup sees just the newest one.
        #
        # Computed HERE, before the modifier chains, not just for the
        # stacking-vs-new branch below: `existing is None` is also what
        # decides whether the raw-amount `step6` guard just below applies
        # (only `Apply(power, target, ...)`'s own path has it — `Apply<T>`
        # routes an existing instance straight to `ModifyAmount`, which
        # never re-tests the raw amount at all).
        existing = target.powers.get(power_cls.id)
        if existing is not None:
            if power_cls.instance_type is PowerInstanceType.INSTANCED:
                existing = None
            elif (power_cls.instance_type is PowerInstanceType.INSTANCED_PER_APPLIER
                    and existing.applier is not applier):
                existing = None

        # PowerCmd.cs:103 — `Apply(power, target, amount, ...)`'s own
        # `amount == 0m` disjunct (power_cmd/step6): C# returns here, before
        # `Hook.BeforePowerAmountChanged` or either modifier chain ever runs,
        # so a raw zero never even reaches Unsettling Lamp/Artifact/Ruined
        # Helmet. Only the "no existing instance" branch has this check —
        # `ModifyAmount` (the stacking branch) has no such guard at all, and
        # a zero OFFSET flows through its chains normally.
        if existing is None and amount == 0:
            return

        # PowerCmd.cs:122-127 — the two chains run in THIS order, before
        # anything downstream sees the amount. A debuff card whose debuffs
        # Artifact fully blocks still spends Unsettling Lamp's
        # once-per-combat activation (it latched on that card via the
        # given-side chain) even though the doubled amount never lands —
        # Artifact (now a real `modify_power_amount_received` listener,
        # ArtifactPower.cs:17-41, power_cmd/G3+G4) sees whatever the given
        # chain already produced and still only consumes ONE stack, however
        # much Lamp doubled the incoming debuff. Note: the two COMPANION
        # events that Artifact/RuinedHelmet actually act on
        # (`after_modify_power_amount_given/received`) do NOT fire here —
        # they moved to AFTER the power's state is mutated, in each branch
        # below (PowerCmd.cs:148-152 for Apply, :238-242 for ModifyAmount).
        #
        # GIVEN: gated on `applier != null && combatState.ContainsCreature(
        # applier)` (PowerCmd.cs:122-123) — the gate lives HERE, at the call
        # site, mirroring where C# puts it (`Hook.ModifyPowerAmountGiven`
        # itself has no such gate). Two full passes, additive-sum then
        # multiplicative-product (Hook.cs:1888-1912) — not commutative with
        # a naive fold, so two separate dispatcher calls, not one.
        given_modifiers: list = []
        if applier is not None and _combat_contains_creature(hooks, applier):
            amount = hooks.modify_power_amount_given_additive(
                power_cls, target, amount, applier, given_modifiers)
            amount = hooks.modify_power_amount_given_multiplicative(
                power_cls, target, amount, applier, given_modifiers)

        # RECEIVED: UNCONDITIONAL (Hook.cs:1917-1930 has no applier gate at
        # all) — a single pass of full-value overrides
        # (`TryModifyPowerAmountReceived` either replaces the running amount
        # or leaves it alone), not an additive/multiplicative fold.
        # ArtifactPower (ArtifactPower.cs:17-36) and RuinedHelmet
        # (RuinedHelmet.cs:32-53) both live here now, as real listeners
        # instead of a hand-rolled block outside the hook loop.
        received_modifiers: list = []
        amount = hooks.modify_power_amount_received(
            power_cls, target, amount, applier, received_modifiers)

        if existing is not None:
            # PowerCmd.cs:236-242 (ModifyAmount) — SetAmount runs FIRST,
            # THEN the companion events, UNCONDITIONALLY: this pipeline has
            # no CanReceivePowers gate anywhere (the asymmetry with the
            # new-power branch below is real, verified by reading both
            # methods side by side — not an oversight). They also run
            # BEFORE the ShouldRemoveDueToAmount/Remove check further down
            # (:247-249): a stack that drops a power to 0 still notifies
            # Artifact/Ruined Helmet, with the POST-mutation power, before
            # it disappears.
            old_amount = existing.amount
            existing.on_stack(amount)
            power = existing
            if given_modifiers:
                hooks.after_modify_power_amount_given(given_modifiers, power)
            if received_modifiers:
                hooks.after_modify_power_amount_received(received_modifiers, power)
            hooks.on_power_amount_changed(
                power_cls.id, target, existing.amount - old_amount, applier
            )
            # Mirrors ModifyAmount → ShouldRemoveDueToAmount: stacking to 0
            # removes the power (or to <= 0 for powers that can't go negative).
            if existing.amount == 0 or (
                existing.amount < 0 and not existing.allow_negative
            ):
                existing._expire()
                return
        else:
            # PowerCmd.cs:133 — CanReceivePowers is re-tested HERE, after the
            # given/received modifier chains have run, because any listener
            # they invoked could have changed the target's hittability in the
            # meantime (a revival latching mid-application). The sim tested it
            # only at the entry. C# re-tests it on the NEW-power path alone:
            # Apply<T> routes an existing instance to ModifyAmount, which never
            # consults CanReceivePowers at all. C# wraps its ENTIRE tail —
            # ApplyInternal through BOTH companion events, :135-152 — inside
            # this SAME `if (target.CanReceivePowers)` (:133-158): a target
            # that fails this re-test gets NEITHER companion event, not just
            # no power. The `return` below therefore has to skip the
            # companions too, not only skip construction — which it does,
            # simply by returning before `power` is even built.
            if not can_receive_powers(hooks, target):
                return
            # PowerCmd.cs:81 (`power = powerModel.ToMutable()`, done by the
            # `Apply<T>` wrapper before this inner `Apply` even starts) — the
            # PowerModel instance exists, unowned and unregistered, BEFORE
            # ApplyInternal ever runs, and STAYS that way when the
            # post-modifier amount is exactly 0. That is the very object C#
            # still passes to both companion events below (PowerCmd.cs:150,
            # :152) even for a debuff Artifact fully zeroed. Constructing it
            # here unconditionally (`Power.__init__` is pure attribute
            # assignment — no registration, no hook side effect) mirrors
            # that, instead of passing `None` for "nothing to point to".
            power = power_cls(owner=target, amount=amount, hooks=hooks, applier=applier)
            # PowerModel.ApplyInternal (PowerModel.cs:564-573): `if (!(amount
            # == 0m)) { ...; Owner.ApplyPowerInternal(this); }` — a
            # POST-modifier amount of exactly 0 never registers anything.
            # This is what makes a debuff Artifact zeroed via the received
            # chain create nothing, matching the pre-refactor hard-coded
            # early return, without a second special case for Artifact
            # specifically — any received-side listener that zeroes an
            # incoming debuff gets the same "nothing created" outcome. THE
            # TRAP: this zero-check is INTERNAL to ApplyInternal — in C# it
            # gates only the SetAmount/Owner-assignment/registration inside
            # ApplyInternal's own body, not the companion events that sit
            # AFTER the ApplyInternal call but still inside the
            # CanReceivePowers block. So the `if amount != 0` below governs
            # ONLY attach/registration; the companion dispatch after it is
            # unconditional here (gated solely by CanReceivePowers, already
            # re-tested above) and must still fire — that's how Artifact's
            # charge gets spent on a debuff it fully blocks.
            if amount != 0:
                target.powers[power_cls.id] = power
                hooks.register(power)
                hooks.on_power_applied(power_cls.id, target, amount, applier)
                # Debuffs landing on the player skip their first duration
                # tick. This belongs to the attach branch: C# sets
                # SkipNextDurationTick unconditionally inside the
                # CanReceivePowers block (PowerCmd.cs:144-147), but on a
                # power object that — when amount==0 — is never kept
                # anywhere, so nothing ever observes the flag; gating it on
                # `amount != 0` here is behaviorally identical. Setting it at
                # function scope (rather than only here) re-armed the flag on
                # every re-stack, so a second Vulnerable or Weak stack
                # applied in the same turn skipped a tick it should have
                # taken and the debuff expired a turn late — this branch is
                # reached only on a fresh application, never a re-stack.
                if (target.side == "player"
                        and power_cls.power_type == PowerType.DEBUFF):
                    power.skip_next_tick = True
            # PowerCmd.cs:148-152 — the companion events: gated on there
            # having been at least one real modifier (an empty list plays
            # the same role as C#'s `givenModifiers == null`: nobody to
            # notify) and on the CanReceivePowers re-test above — NOT on the
            # `amount != 0` attach branch just above (see the trap note
            # there). `power` is the real instance, matching C#'s own
            # `power` local: neither of C#'s two
            # AfterModifyingPowerAmountReceived implementers currently reads
            # the PowerModel argument (ArtifactPower.cs:38-41 decrements
            # ITSELF; RuinedHelmet.cs:55-60 just flips its own flag), but the
            # mechanism now carries the same value C# does, for a future
            # listener that does.
            if given_modifiers:
                hooks.after_modify_power_amount_given(given_modifiers, power)
            if received_modifiers:
                hooks.after_modify_power_amount_received(received_modifiers, power)

    @staticmethod
    def modify_amount(hooks: HookSystem, power, offset: int) -> None:
        """PowerCmd.ModifyAmount (PowerCmd.cs:215-271), as reached from
        `Decrement` (:179-182) and so from `TickDownDuration` (:190-200).

        The sim's duration ticks used to mutate `power.amount` directly, which
        is why `ModifyAmount`'s `IsEnding` guard (:217-220) never reached them
        (power_cmd G6's carried observation). They route through here now, so
        a tick in the ending window is refused exactly as a fresh application
        is.

        This is the DECREMENT path only, and it deliberately does NOT run the
        `ModifyPowerAmountGiven` / `ModifyPowerAmountReceived` chains that
        `ModifyAmount` runs at :229-233. STALE NOTE, corrected in the
        power_cmd/G3+G4 pass: this used to be blocked on power_cmd/G2 (the
        sim's Unsettling Lamp missing C#'s sign-aware doubling condition, so
        it would have doubled a -1 duration tick into -2) — G2 is now closed
        (Task 17: Lamp gates on `type_for_amount`, which self-protects a
        negative offset on a non-allow_negative debuff by flipping it to
        Buff). Wiring the chains in here is still NOT done — that is a
        separate, broader change (every duration tick in the game would
        start running the received chain) this task's brief did not scope,
        not a known-regression block anymore. `ArtifactPower.Decrement(this)`
        (ArtifactPower.cs:38-41) — this method's own C# analogue —
        deliberately reaches here too (`PowerCmd.modify_amount` is what
        `Power._tick`/Artifact's own charge-spend both call), and skipping
        the chains on THAT call is verified harmless: neither
        `ArtifactPower` nor `RuinedHelmet`'s received-chain check can ever
        fire on Artifact's own -1 self-decrement (Artifact's
        `type_for_amount(-1)` is Buff, not Debuff; RuinedHelmet requires
        `StrengthPower`), so running the chains here would be a no-op for
        today's exactly-two listeners regardless.
        """
        if is_ending(hooks):
            return
        power.amount += offset
        hooks.on_power_amount_changed(power.id, power.owner, offset)
        # :247-250 — `if (power.ShouldRemoveDueToAmount()) await Remove(power)`.
        if power.amount <= 0:
            power._expire()

    @staticmethod
    def remove(
        hooks: HookSystem,
        target: Creature,
        power_id: str,
    ) -> None:
        """Remove a power from a creature by ID."""
        power = target.powers.pop(power_id, None)
        if power is not None:
            try:
                hooks.unregister(power)
            except ValueError:
                pass


class StrengthCmd:
    @staticmethod
    def apply(
        hooks: HookSystem,
        target: Creature,
        amount: int,
        card: Card | None = None,
    ) -> int:
        """Apply strength via the hook pipeline. Returns final strength gained."""
        from .powers import StrengthPower
        amount = hooks.modify_strength_given(target, amount, card)
        PowerCmd.apply(hooks, target, StrengthPower, amount)
        return amount


class DrawCmd:
    @staticmethod
    def draw(player: PlayerCombatState, count: int) -> None:
        """Draw count cards mid-turn (from_hand_draw=False). Hooks fire inside player._draw."""
        player._draw(count, from_hand_draw=False)


class ExhaustCmd:
    @staticmethod
    def exhaust(
        hooks: HookSystem,
        player: PlayerCombatState,
        card: Card,
    ) -> None:
        """Move a card to the exhaust pile from wherever it currently sits
        (mirrors `CardCmd.Exhaust` -> `CardPileCmd.Add(card, PileType.Exhaust,
        Bottom)`, CardCmd.cs:237-246).

        creature_card_cmds/G7: `CardModel.RemoveFromCurrentPile`
        (CardPileCmd.cs:496) is PILE-AGNOSTIC — it removes the card from
        whatever pile it is currently in, not just hand/discard. The old code
        here only checked those two, so a draw-pile card stayed in draw_pile
        AND was appended to exhaust_pile — the same instance in two piles at
        once. `PlayerCombatState.remove_from_current_pile` is that verb, and
        it covers all FIVE piles.

        The fifth one is load-bearing here: an earlier version of this
        docstring argued that "no fourth Play limbo case exists to scan for,
        because a card mid-OnPlay is already physically in discard_pile". That
        premise died with round 13's real `play_pile` (creature_card_cmds
        N9/step82) — an exhaust fired from inside a card's own OnPlay is
        exactly the double-membership bug this scan exists to prevent.

        The exhaust pile is scanned TOO, and re-exhausting an
        already-exhausted card is a legal no-throw REPOSITION to the bottom
        of that pile — not an error. `CardPileCmd.Add` captures
        `oldPile = card.Pile` (CardPileCmd.cs:364) and runs
        `if (oldPile != null) card.RemoveFromCurrentPile(...)` at :494-496
        BEFORE `targetPile.AddInternal(...)` at :510, so when
        `oldPile == targetPile == Exhaust` the card is taken out first and
        `AddInternal`'s `Cards.Contains` guard (CardPile.cs:86-89) is tested
        against an already-emptied slot and never fires. An earlier version of
        this method asserted the card was absent from the exhaust pile before
        appending (N4's pile-ADD idiom); that was wrong here, because it made
        the sim raise where the game performs a legal move. N4's loud-failure
        idiom applies to the ADD helpers whose C# counterparts really can
        throw — this path's C# demonstrably cannot.

        `CardCmd.Exhaust`'s ENTIRE body is inside
        `if (!CombatManager.Instance.IsOverOrEnding)` (CardCmd.cs:239-245), so
        the move, `History.CardExhausted` (:243) and `Hook.AfterCardExhausted`
        (:244) are refused TOGETHER once the fight is ending, and the card is
        left in whatever pile it was in. The gate belongs HERE and not at any
        call site: `CardCmd.cs:242` is the ONLY
        `CardPileCmd.Add(..., PileType.Exhaust, ...)` in the whole source, so
        every exhaust in the game passes through this one method, and `Add`
        itself would refuse anyway (`IsCombatPile && IsEnding`,
        CardPileCmd.cs:312-319; `!IsInProgress`, :398-401 — both before the
        move at :496/:510). It is NOT cosmetic: `JossPaper.CardsExhausted` is
        a `[SavedProperty]` (JossPaper.cs:60-76) incremented from
        `AfterCardExhausted` (:102-114) and cleared by nothing at combat end
        (`AfterCombatEnd` :144-148 clears `EtherealCount` only), so every
        fight that ended on an exhaust used to over-credit a RUN-scoped
        counter by one. R5-review RV-2 / R5 fix pass.
        """
        if is_over_or_ending(hooks):
            return
        player.remove_from_current_pile(card)
        player.exhaust_pile.append(card)
        hooks.on_card_exhausted(card)


class CardCmd:
    # `PileType` raw enum values (PileType.cs). NOT `AllPiles` order — Draw
    # sorts before Hand here, where `AllPiles` puts Hand first. See
    # `pile_index_sort_key`.
    _PILE_TYPE_ORDER = {
        "none": 0, "draw": 1, "hand": 2, "discard": 3,
        "exhaust": 4, "play": 5, "deck": 6,
    }

    @staticmethod
    def pile_index_sort_key(pile_name: str, index: int) -> tuple[int, int]:
        """`CardCmd.PileIndexSort` (CardCmd.cs:353-360), as a sort key.

            if (value1.Item2.Type != value2.Item2.Type)
                return value1.Item2.Type.CompareTo(value2.Item2.Type);
            return value1.Item3.CompareTo(value2.Item3);

        `Item2` is the original's `CardPile` and `Item3` is its index INSIDE
        that pile, captured before the removal (`pile.Cards.IndexOf(...)` at
        :396, `RemoveFromCurrentPile()` at :402). `CardPile.Type.CompareTo` is
        the RAW `PileType` enum compare — None=0, Draw=1, Hand=2, Discard=3,
        Exhaust=4, Play=5, Deck=6 — so this is deliberately NOT `AllPiles`
        order and a Draw-pile original is re-seated before a Hand one.

        Applied at :405 to the whole transformation batch, which is what makes
        a MULTI-card transform's re-insertion order deterministic. The sim's
        transform verbs (`CardCmd.transform_to_random`, `RunState.
        transform_card`) are single-card, so there is nothing to sort YET —
        this is the key the batch path must use when one is ported, and it is
        pinned so the ordering is not re-derived from `AllPiles` by mistake.
        creature_card_cmds/step56.

        A pile name the map does not know raises `KeyError` rather than
        silently sorting as `PileType.None` (note N4's loud-failure idiom):
        `PileIndexSort` cannot be reached with a null pile at all, because
        :392-394 THROWS ("Can't transform … because it has no pile") before
        the index is taken at :396. A silent 0 would be exactly the wrong
        default to hand a future batch transform. R5-review RV-8.
        """
        return (CardCmd._PILE_TYPE_ORDER[pile_name], index)

    @staticmethod
    def discard_and_draw(
        hooks: HookSystem,
        player: PlayerCombatState,
        cards_to_discard,
        cards_to_draw: int = 0,
    ) -> None:
        """`CardCmd.DiscardAndDraw` (CardCmd.cs:172-205), which `Discard` (the
        single- and multi-card overloads, :147-160) is a zero-draw call to.

        The whole point of the verb is the ORDER, and its own warning at
        :139-143 says so — "if you're discarding multiple cards at once for an
        effect like Concentrate or Gambler's Brew, do NOT use this method
        inside a loop, because the timing of the Sly effect will be
        incorrect":

          :174-177  IsOverOrEnding -> return
          :179-182  no cards -> return
          :186-195  per card: collect it if `IsSlyThisTurn` (:188-191),
                    `CardPileCmd.Add(card, discardPile)` (:192),
                    History.CardDiscarded (:193), then
                    `Hook.AfterCardDiscarded` (:194) — APPEND FIRST, hook
                    second
          :197-200  THEN the draw, once, for the whole batch
          :201-204  THEN auto-play every collected Sly card, with
                    `AutoPlayType.SlyDiscard`

        The two sim call sites that open-coded this loop disagreed with each
        other about the append/hook order — `potions.py`'s Gambler's Brew
        fired `on_card_discarded` BEFORE appending, `relics/gambling_chip.py`
        appended first — and neither had the Sly tail. Both now route here.
        creature_card_cmds/step50 + step51.
        """
        if is_over_or_ending(hooks):
            return                                  # :174-177
        discard_cards = list(cards_to_discard)
        if not discard_cards:
            return                                  # :179-182
        sly_cards: list[Card] = []
        for card in discard_cards:
            if card.is_sly_this_turn:               # :188-191
                sly_cards.append(card)
            player.remove_from_current_pile(card)   # :192 Add -> RemoveFromCurrentPile
            player.discard_pile.append(card)
            hooks.on_card_discarded(card)           # :194, AFTER the append
        if cards_to_draw > 0:
            DrawCmd.draw(player, cards_to_draw)     # :197-200
        combat = hooks.combat
        for card in sly_cards:                      # :201-204
            if combat is None:
                break
            combat.auto_play_card(card, auto_play_type="sly_discard")

    @staticmethod
    def downgrade(hooks: HookSystem | None, card: Card) -> None:
        """`CardCmd.Downgrade` (CardCmd.cs:212-223).

        The whole verb sits inside `if (!CombatManager.Instance.IsEnding)`, so
        a downgrade fired by the killing blow does not land — the same window
        `creature_card_cmds` guard G14 covers for the other commands. `IsEnding`
        rather than `IsOverOrEnding`, so the two out-of-combat callers
        (Reflections, Welcome to Wongo's) are unaffected; pass `hooks=None`
        there, which answers False for exactly that reason.

        The `DowngradedCards` run-history append the verb also does (:217-220)
        is telemetry and has no sim surface.
        """
        if is_ending(hooks):
            return
        card.downgrade()

    @staticmethod
    def upgrade(hooks: HookSystem | None, card: Card) -> None:
        """`CardCmd.Upgrade` (CardCmd.cs:265-290), the per-card body.

        Two guards, and the sim's bare `card.upgrade()` had neither: the whole
        verb sits inside `if (!IsEnding)`, and each card is skipped when
        `IsUpgradable` is false -- `CurrentUpgradeLevel < MaxUpgradeLevel`
        (CardModel.cs:785-789). The second one matters far more than it looks:
        35 of the pool's cards have MaxUpgradeLevel 0 (every Curse, Status and
        Quest card), and C# THROWS if CurrentUpgradeLevel is ever set above
        MaxUpgradeLevel (CardModel.cs:773-776) -- so an unguarded `+= 1`
        produced a state the source treats as impossible, and one the
        conformance runner compares against the save as an (id, upgrade_level)
        pair.

        The `UpgradedCards` run-history append (:279-282) is telemetry;
        `FinalizeUpgradeInternal` (:284) clears preview state the sim has none of.
        """
        if is_ending(hooks) or not card.is_upgradable:
            return
        card.upgrade()

    @staticmethod
    def afflict(
        card: Card,
        affliction_cls: type[Affliction],
        amount: int,
    ) -> Affliction | None:
        """Attach an affliction to a card (mirrors CardCmd.Afflict).

        A card holds at most one affliction: an unafflicted card gets a new
        instance, re-applying the same type stacks the amount if the type
        `is_stackable` (else it is refused, see `Affliction.can_afflict`),
        and a card afflicted with a different type is left untouched
        (returns None).
        """
        # CardCmd.cs:627-634, the seam's one ASYMMETRIC liveness guard: refuse
        # when the combat is over or ending AND the card sits in a combat pile,
        # but allow it for a card that does not (a deck card being afflicted
        # out of combat, which is the same command).
        combat = card.combat
        if getattr(combat, "is_over_or_ending", False):
            # "is this card in a COMBAT pile" — and Play is one
            # (PileTypeExtensions.cs:35-42), which is why this asks
            # `pile_type_of` rather than scanning four lists by hand.
            if combat.player.pile_type_of(card) is not None:
                return None
        new_affliction = affliction_cls(amount)
        # Hook.ShouldAfflict (CardCmd.cs:637) -- an AND-all veto dispatched
        # through IterateCombatHookListeners, same gate should_die/
        # should_allow_hitting use. A card with no combat has no HookSystem
        # to consult, so it is treated as passing (the zero-listener default
        # anyway); C# additionally refuses whenever `combatState` itself is
        # null (CardCmd.cs:637's `combatState == null || ...`), which is
        # deliberately NOT mirrored here — the already-closed asymmetric
        # guard just above depends on an out-of-combat afflict succeeding
        # (creature_card_cmds/step63's "loose card" witness,
        # test_afflict_is_refused_only_for_a_card_in_a_combat_pile).
        hooks = getattr(combat, "hooks", None)
        if hooks is not None and not hooks.should_afflict(card, new_affliction):
            return None
        # AfflictionModel.CanAfflict (AfflictionModel.cs:190-205; card type +
        # already-afflicted/stackability). CardCmd.cs:641's own guard.
        if not new_affliction.can_afflict(card):
            return None
        if card.affliction is None:
            new_affliction.card = card
            card.affliction = new_affliction
            # `CombatState.IterateHookListeners` adds `cardModel.Affliction`
            # to the listener list right after its card (CombatState.cs:
            # 458-461) and `AfflictionModel.cs:146` declares
            # `ShouldReceiveCombatHooks => true`, so an affliction is a hook
            # listener for as long as it is attached (hook_dispatch/G6). The
            # walk in `HookSystem._ordered` finds it through the card, so this
            # only has to put it in the membership set; the position comes
            # from the card's pile.
            if hooks is not None:
                hooks.register(new_affliction)
            return new_affliction
        if isinstance(card.affliction, affliction_cls):
            card.affliction.amount += amount
            return card.affliction
        return None

    @staticmethod
    def clear_affliction(card: Card) -> None:
        """Remove a card's affliction if it has one.

        `CardModel.ClearAfflictionInternal` (CardModel.cs:1532-1540) does TWO
        things, and the sim only did the second: it calls
        `AfflictionModel.ClearInternal` (:249-254), which nulls the
        affliction's own `_card` back-reference, and THEN nulls the card's
        `Affliction`. The sim left a cleared affliction still pointing at the
        card it no longer afflicts, which `AfflictionModel.HasCard`
        (AfflictionModel.cs:90) — the first leg of `CombatState.Contains`'
        affliction arm (CombatState.cs:591) — reads. With the affliction now a
        real listener (hook_dispatch/G6) that stale back-reference would be a
        cleared affliction that still passed `Contains`, so both halves are
        mirrored here, plus the unregistration the sim's registry needs.
        """
        affliction = card.affliction
        if affliction is None:
            return
        affliction.card = None
        card.affliction = None
        hooks = getattr(card.combat, "hooks", None)
        if hooks is not None:
            try:
                hooks.unregister(affliction)
            except ValueError:
                pass

    @staticmethod
    def transform_to_random(
        hooks: HookSystem,
        player: PlayerCombatState,
        card: Card,
    ) -> Card | None:
        """Transform a card mid-combat into a random other card (mirrors
        CardCmd.TransformToRandom with isInCombat=true; Entropy).

        The replacement is rolled from the original's transform options
        (see cards.pool.transform_options_in_combat), takes the original's
        place in whichever pile holds it, and becomes a hook listener; the
        original leaves the combat entirely.
        """
        from .cards import make_card
        from .cards.pool import transform_options_in_combat

        # CardCmd.cs:371-374 — `IsEnding -> empty`. The out-of-combat deck
        # transformers (RunState.transform_card) share the C# command and are
        # deliberately unaffected: `IsEnding` is false with no combat running.
        if is_ending(hooks):
            return None
        options = transform_options_in_combat(card, hooks.combat.card_pool)
        if not options:
            return None
        # `CardCmd.TransformToRandom(item, RunState.Rng.CombatCardSelection)`
        # (EntropyPower.cs:31) — the caller names the stream, and Entropy is
        # the only in-combat caller.
        replacement = make_card(
            hooks.combat.combat_rng.card_selection.choice(options))
        # `CardCmd.cs:391-395` reads `item.Original.Pile` and THROWS if it is
        # null — whatever pile holds the card, Play included (a card can be
        # transformed from inside its own OnPlay).
        for pile_name, pile in (
            ("hand", player.hand), ("draw", player.draw_pile),
            ("discard", player.discard_pile), ("exhaust", player.exhaust_pile),
            ("play", player.play_pile),
        ):
            if card in pile:
                pile[pile.index(card)] = replacement
                break
        else:
            return None
        try:
            hooks.unregister(card)
        except ValueError:
            pass
        # `CardCmd.Transform`'s tail (CardCmd.cs:498-506) calls
        # `Original.RemoveFromState()` on every original once the replacements
        # have landed — the first leg of `Contains`' CardModel arm
        # (CombatState.cs:593). See `Card.has_been_removed_from_state`.
        card.has_been_removed_from_state = True
        CardPileCmd._enter_combat(hooks, replacement)
        # CardCmd.cs:447-450, in this order, and shared by both branches of the
        # pile-type test above them:
        #
        #   await Hook.AfterCardChangedPiles(runState, combatState,
        #                                    replacement2, pile2.Type, null);
        #   pile2.InvokeCardAddFinished();
        #   original.AfterTransformedFrom();
        #   replacement2.AfterTransformedTo();
        #
        # `clonedBy` is a literal `null` here — a transform is not a clone, so
        # Bing Bong's `clonedBy == null` test passes for a transformed card
        # where it fails for one Bing Bong itself added (BingBong.cs:31).
        #
        # InvokeCardAddFinished (:448) has NO sim counterpart and needs none:
        # it is `CardAddFinished?.Invoke()` (CardPile.cs:179-182) and the event's
        # only subscriber in the whole source is NCombatCardPile.cs:83-106, a
        # presentation node that animates the card into the pile.
        hooks.after_card_changed_piles(replacement, pile_name, None)
        card.after_transformed_from()
        replacement.after_transformed_to()
        # CardCmd.cs:499-506 — a THIRD pass, after a presentation-only VFX
        # wait (`Cmd.Wait(num)`, :498, no sim counterpart) that this method
        # collapses to nothing: for every successful transform whose card
        # ended up in a combat pile, `Hook.AfterCardGeneratedForCombat(
        # combatState, cardAdded, cardAdded.Owner)`. The `IsCombatPile()`
        # gate is unconditionally true here — `transform_to_random` mirrors
        # `isInCombat=true` only, so `replacement` always landed in one of
        # the four combat piles above. `creator` is the transforming
        # player (`cardAdded.Owner`), unlike the Add site's callers, which
        # both pass `null` — see `CardPileCmd._generated_for_combat`.
        # creature_card_cmds/step61.
        hooks.on_card_generated_for_combat(replacement, player)
        return replacement


class CardPileCmd:
    @staticmethod
    def _refuses_combat_add(hooks: HookSystem, player: PlayerCombatState) -> bool:
        """CardPileCmd.Add's three refusals for a COMBAT pile, all of which sit
        upstream of the actual pile move (the move is at CardPileCmd.cs:408+,
        after the last of them):

          :312-319  `newPile.IsCombatPile && IsEnding` -> every result
                    success = false, so nothing is added;
          :329-340  per card, `creature.IsDead` -> success = false. A SEPARATE
                    refusal: a power holding the fight open leaves IsEnding
                    false while the owner is dead, and the card is still
                    dropped;
          :398-401  `newPile.IsCombatPile && !IsInProgress` -> return.

        The sim's three pile helpers moved the card unconditionally.
        """
        combat = getattr(hooks, "combat", None)
        if combat is None:
            return False
        return getattr(combat, "is_over_or_ending", False) or player.is_dead

    @staticmethod
    def _assert_not_present(pile: list[Card], card: Card, pile_name: str) -> None:
        """`CardPile.AddInternal` throws `InvalidOperationException` if the
        target pile already holds this exact `CardModel` instance
        (CardPile.cs:86-89). creature_card_cmds/N4 + step102c: the sim's
        piles were plain lists with no such invariant, which is what let a
        card end up double-counted across piles silently. Mirrored as
        `ValueError`, this codebase's idiom for an invariant violation (e.g.
        `characters.py`'s "already registered" guard) — .NET has no direct
        analogue and `InvalidOperationException` is a construction-time
        assertion here, not a value users are expected to catch.
        """
        if card in pile:
            raise ValueError(
                f"{pile_name} pile already contains {card!r}")

    @staticmethod
    def _enter_combat(hooks: HookSystem, card: Card) -> None:
        """Register a newly created card as a hook listener (cards listen for
        their whole combat lifetime, mirroring CardModel = AbstractModel) and
        fire the entered-combat hook so active powers can afflict it.

        The card's ENCHANTMENT is registered with it, exactly as
        `CombatState.__init__` does for the starting deck. C# needs no such
        step — `CombatState.IterateHookListeners` re-enumerates from the piles
        on every dispatch and adds `cardModel.Enchantment`
        (CombatState.cs:462-465) — but the sim registers once, so a card
        created MID-combat used to arrive with an inert enchantment. Since
        `create_clone` began carrying the enchantment onto copies
        (enchantment/EG2), that was not merely a dead listener but a crash:
        Corrupted and Sown reach the engine through `self.combat.hooks` in
        their `on_play`, and on a copy `combat` was None.
        """
        card.combat = hooks.combat
        hooks.register(card)
        if card.affliction is not None and card.affliction not in hooks._listeners:
            # CombatState.cs:458-461 — the card's Affliction joins the walk
            # right after it. A card can arrive already afflicted: `create_clone`
            # (cards/base.py) rebuilds the source's affliction on the copy
            # (CardModel.cs:1204-1215's `AfflictInternal`) without going through
            # `CardCmd.afflict`, which is where the registration otherwise
            # happens. hook_dispatch/G6.
            hooks.register(card.affliction)
        if card.enchantment is not None:
            card.enchantment.combat = hooks.combat
            if card.enchantment not in hooks._listeners:
                hooks.register(card.enchantment)
        hooks.on_card_entered_combat(card)

    @staticmethod
    def _generated_for_combat(hooks: HookSystem, card: Card) -> None:
        """The other two events C#'s `AddGeneratedCardToCombat` fires around a
        freshly generated card, both still owed by seam/creature_card_cmds
        (guard G8 for the first, step70 for the second):

          CardPileCmd.cs:635, inside the general `Add` every
          `AddGeneratedCardsToCombat` call routes through — after tweens
          settle, `Hook.AfterCardChangedPiles(..., oldPile?.Type ??
          PileType.None, clonedBy)`. A freshly generated card has no old
          pile, so `oldPile?.Type` is `PileType.None` here — `pile=None`,
          not one of the sim's pile-name strings; `clonedBy` is `None` too
          (none of `add_to_hand`/`add_to_draw`/`add_to_discard`'s callers is
          a clone verb).

          CardPileCmd.cs:246, in `AddGeneratedCardsToCombat`, right after
          that `Add` call returns — `Hook.AfterCardGeneratedForCombat(
          combatState, card, creator)`. `creator` is `None` at both
          currently reachable call chains (Aeonglass.cs:145's own Wither,
          WitheringPresencePower.cs:55's punish Wither) — both pass `null`
          explicitly — so it is not threaded through as a parameter here;
          a future caller that needs a real creator should add one.

        NOT called by `_enter_combat`: the transform site
        (`CardCmd.transform_to_random`) also calls `_enter_combat` but
        dispatches `AfterCardChangedPiles` itself with the pile the
        replacement landed IN (CardCmd.cs:447), not `None` — folding this
        helper into `_enter_combat` would double-fire it there.
        """
        hooks.after_card_changed_piles(card, None, None)
        hooks.on_card_generated_for_combat(card, None)

    @staticmethod
    def add_to_discard(
        hooks: HookSystem,
        player: PlayerCombatState,
        card: Card,
    ) -> None:
        """Add a newly created card to the player's discard pile (mirrors
        CardPileCmd.AddToCombatAndPreview)."""
        if CardPileCmd._refuses_combat_add(hooks, player):
            return
        CardPileCmd._assert_not_present(player.discard_pile, card, "discard")
        player.discard_pile.append(card)
        CardPileCmd._enter_combat(hooks, card)
        CardPileCmd._generated_for_combat(hooks, card)

    @staticmethod
    def add_to_draw(
        hooks: HookSystem,
        player: PlayerCombatState,
        card: Card,
    ) -> None:
        """Add a newly created card to a random position in the player's draw
        pile (mirrors AddGeneratedCardToCombat with PileType.Draw,
        CardPilePosition.Random).

        Parity (CardPileCmd.cs:514): the random slot is drawn from the SHUFFLE
        stream — ``Rng.Shuffle.NextInt(Cards.Count + 1)`` — not the shared run
        rng. The game pile counts index 0 = top (next drawn); the sim stores its
        top at the END (the parity reshuffle reverses game order, player.py),
        so a game index ``p`` lands at sim index ``count - p``. Legacy keeps its
        byte-for-byte shared-rng insertion."""
        if CardPileCmd._refuses_combat_add(hooks, player):
            return
        CardPileCmd._assert_not_present(player.draw_pile, card, "draw")
        crng = hooks.combat.combat_rng
        count = len(player.draw_pile)
        if crng.is_parity:
            p = crng.shuffle.randrange(count + 1)   # game index, 0 = top
            player.draw_pile.insert(count - p, card)
        else:
            player.draw_pile.insert(hooks.combat._rng.randrange(count + 1), card)
        CardPileCmd._enter_combat(hooks, card)
        CardPileCmd._generated_for_combat(hooks, card)

    @staticmethod
    def auto_play_from_draw_pile(
        hooks: HookSystem,
        player: PlayerCombatState,
        count: int,
        position: str = "top",
        force_exhaust: bool = False,
    ) -> None:
        """`CardPileCmd.AutoPlayFromDrawPile` (CardPileCmd.cs:931-966), and it is
        TWO-PHASE — which is the whole reason it exists as one helper.

        Phase 1 (:939-955) pulls all `count` picks out of the draw pile and into
        `PileType.Play`, one `ShuffleIfNecessary` per pick, breaking on an empty
        pile. Phase 2 (:956-965) plays them, setting `ExhaustOnNextPlay =
        forceExhaust` on each first and breaking if the owner has died.

        So every pick is COMMITTED before any of them resolves: a draw, a
        reshuffle or a pile redirect the first card causes cannot change which
        card is played second, and because the waiting cards sit in PileType.Play
        a reshuffle the first one triggers excludes them (bug class 7, pile
        limbo). Both sim callers interleaved instead — Havoc and Mayhem picked
        and played one card per iteration.

        Phase 1's park is a REAL move into `play_pile` as of round 13 (R5).
        Before that the picks were removed from the draw pile into a local list
        and were in no pile at all, which bought the reshuffle immunity by a
        different mechanism but hid them from every `AllCards` sweep and from
        the listener walk.

        `force_exhaust` is applied through `exhaust_on_next_play`, not by moving
        the card by hand: that is what routes it through the normal result-pile
        path, so an unplayable pick reaches `CardCmd.Exhaust`
        (CardModel.cs:2098-2101) and a Power card still vanishes to
        `PileType.None` (:2071-2074).
        """
        combat = hooks.combat
        if is_over_or_ending(hooks) or player.is_dead:
            return                                  # CardPileCmd.cs:933-936
        cards: list[Card] = []
        for _ in range(count):
            player.shuffle_if_necessary()           # :939
            pile = player.draw_pile
            if not pile:
                break                               # :949-952, `break` not continue
            if position == "top":
                card = pile[-1]                     # the sim stores top LAST
            elif position == "bottom":
                card = pile[0]
            else:
                # `Rng.CombatCardSelection.NextItem(drawPile.Cards)` (:942) over
                # the game's top-first orientation, so the index means the same
                # thing in both engines.
                card = combat.combat_rng.card_selection.choice(list(reversed(pile)))
            cards.append(card)
            # `await Add(cardModel, PileType.Play)` (:954) — the card leaves
            # the draw pile now, for a pile no reshuffle reads.
            pile.remove(card)
            player.play_pile.append(card)
            hooks.after_card_changed_piles(card, "draw", None)
        for card in cards:
            if player.is_dead:
                break                               # :958-964
            card.exhaust_on_next_play = force_exhaust
            combat.auto_play_card(card)

    @staticmethod
    def add_to_hand(
        hooks: HookSystem,
        player: PlayerCombatState,
        card: Card,
    ) -> None:
        """Add a newly created card to the player's hand (overflow goes to the
        discard pile) (mirrors CardPileCmd.AddGeneratedCardToCombat with
        PileType.Hand)."""
        if CardPileCmd._refuses_combat_add(hooks, player):
            return
        if len(player.hand) < player.MAX_HAND_SIZE:
            CardPileCmd._assert_not_present(player.hand, card, "hand")
            player.hand.append(card)
        else:
            CardPileCmd._assert_not_present(player.discard_pile, card, "discard")
            player.discard_pile.append(card)
        CardPileCmd._enter_combat(hooks, card)
        CardPileCmd._generated_for_combat(hooks, card)


class CardSelectCmd:
    """In-combat card selection (mirrors the game's CardSelectCmd). The actual
    choice is made by CombatState.select_cards — random by default, or by an
    installed card_selector."""

    @staticmethod
    def from_hand(
        hooks: HookSystem,
        player: PlayerCombatState,
        purpose: str,
        count: int = 1,
        predicate=None,
    ) -> list[Card]:
        """Pick up to count cards from the hand (mirrors CardSelectCmd.FromHand)."""
        candidates = [c for c in player.hand if predicate is None or predicate(c)]
        return hooks.combat.select_cards(purpose, candidates, count)

    @staticmethod
    def from_pile(
        hooks: HookSystem,
        pile: list[Card],
        purpose: str,
        count: int = 1,
        predicate=None,
        is_draw_pile: bool = False,
        min_select: int | None = None,
    ) -> list[Card]:
        """Pick up to count cards from any pile (mirrors FromCombatPile).

        `is_draw_pile` must be passed by callers sourcing from the DRAW pile
        (SecretTechnique/SecretWeapon) — see CombatState.select_cards'
        `is_draw_pile` docstring (CardSelectCmd.cs:403-408's `orderby Rarity,
        Id` pre-sort). Discard-pile callers (Headbutt, Neow's Fury) leave it
        at the default.

        `min_select` must be passed by callers whose C# site builds a genuine
        `CardSelectorPrefs(prompt, minCount, maxCount)` range (Neow's Fury:
        `new CardSelectorPrefs(prompt, 0, num)`, NeowsFury.cs:39) so
        `select_cards`' `RequireManualConfirmation` derivation sees
        `min_select != count` and never takes the auto-select shortcut.
        Headbutt's `CardSelectorPrefs(prompt, 1)` two-arg ctor is MinSelect==
        MaxSelect, so it leaves this at the default.
        """
        candidates = [c for c in pile if predicate is None or predicate(c)]
        return hooks.combat.select_cards(
            purpose, candidates, count,
            min_select=min_select, is_draw_pile=is_draw_pile)


class EnergyCmd:
    @staticmethod
    def gain(
        hooks: HookSystem,
        player: PlayerCombatState,
        amount: int,
    ) -> None:
        """Gain bonus energy mid-turn (from cards or effects, not turn reset)
        (mirrors `PlayerCmd.GainEnergy`, PlayerCmd.cs:29-43).

        card/_is_dead_early_return + relic/lantern/g1: C#'s whole body sits
        inside `!(amount <= 0m) && !CombatManager.Instance.IsEnding`. `IsEnding`
        rather than `IsOverOrEnding` — the same narrower gate `CardCmd.
        downgrade`/`upgrade`, `CardCmd.transform_to_random` and `PowerCmd.apply`
        use above, matching `IsEnding`'s own `!IsInProgress -> false` opening
        (creature_card_cmds/G14) — this is what would let an out-of-combat
        caller through if one ever called this (none currently do). The
        `amount <= 0m` outer bail and the `finalAmount > 0m` inner one are
        deliberately NOT mirrored: relic/lantern guard N1 already found both
        dormant/equivalent for this codebase (`hooks.modify_energy_gain`
        already clamps with `max(0, amount)`, hooks.py:215, making a
        post-clamp `+= 0` a provable no-op) — one verdict per mechanism, not
        re-litigated here. Before this gate, Bloodletting and Offering carried
        their own `if ctx.player.is_dead: return` specifically to compensate
        for its absence; both are deleted now that this closes the gap at its
        root (card/_is_dead_early_return).
        """
        if is_ending(hooks):
            return
        amount = hooks.modify_energy_gain(player, amount)
        player.energy += amount
