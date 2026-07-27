# Potion tier — shared mechanisms (`PotionModel` + the belt)

Narration doc for the `potion` content stream, written 2026-07-26/27. It exists
because of one structural fact the other content tiers do not have:

> **`PotionModel` is a framework root.** `harness.py`'s `MODEL_ROOT_CLASSES`
> lists it beside `CardModel`/`PowerModel`/`RelicModel`, so base-class following
> stops there and no unit record enumerates a `PotionModel` member. The README
> says that layer "is audited once by the seam tier, not 680 times" — but the
> **seam tier has no potion seam**. `PotionModel.OnUseWrapper` is the whole
> use pipeline for all 51 units and nothing in `audit/records/seam/` is a
> verdict on it.

So the wrapper's mechanisms are recorded here once, and each unit record carries
one rollup guard entry (`W: shared PotionModel.OnUseWrapper pipeline`) pointing
at this file, rather than 51 copies of the evidence. Every number below is
re-derivable with `py audit/tools/potion_probes.py`.

## The C# use pipeline

`src/Core/Models/PotionModel.cs:291-342`, in order:

| # | C# | sim | verdict |
|---|---|---|---|
| W1 | `:293` `RemoveBeforeUse()` — the slot is nulled *before* anything resolves | `combat.py:603-606` nulls the slot and detaches the listener before `potion.use` | faithful |
| W2 | `:297` `await Hook.BeforePotionUsed(...)` | **no such dispatcher** — `hooks.py` has only `on_potion_used` | **gap, LIVE** |
| W3 | `:298-323` throw VFX, `TestMode.IsOff` arm | none | waiver (presentation) |
| W4 | `:324`/`:331` `BeginCardOrPotionEffect` / `EndCardOrPotionEffect` — the re-entrancy depth counter | none | gap, dormant |
| W5 | `:327` `await OnUse(choiceContext, target)` | `potion.use(ctx, target)` (`combat.py:609`) | per unit |
| W6 | `:333` `InvokeExecutionFinished()` | none | waiver (presentation/async) |
| W7 | `:336` `CombatManager.Instance.History.PotionUsed(...)` | `history.py` has no potion entry | waiver (presentation) |
| W8 | `:338` `await Hook.AfterPotionUsed(...)` | `hooks.on_potion_used` (`combat.py:610`) | faithful |
| W9 | `:339` `CurrentMapPointHistoryEntry…PotionUsed.Add(Id)` | none | waiver (save/UI only) |
| W10 | `:340` `await CombatManager.Instance.CheckForEmptyHand(...)` | **never called after a potion** | **gap, LIVE** |

### W2 — `Hook.BeforePotionUsed` is not dispatched (LIVE)

`grep -rn 'BeforePotionUsed' src/` gives the dispatcher (`Hook.cs:984-988`), the
virtual (`AbstractModel.cs:983`), the single call site (`PotionModel.cs:297`) and
exactly **one implementer: `SurroundedPower.cs:82`**. The sim's only potion hook
is `hooks.py:566-571 on_potion_used`, whose own docstring says it "mirrors
AfterPotionUsed", dispatched *after* the effect at `combat.py:610`.

`audit/records/power/surrounded.json` already verdicts this `gap` with
`live: true` (Kaiser Crab's Surrounded is ported at `powers.py:2523`), and
binding rule 3 makes that the verdict at every site. Observable: throwing a
targeted potion at the far Kaiser Crab arm does not turn the player to face it,
so every subsequent attack from the un-faced arm keeps its ×1.5.

Note the ordering half as well: even if the sim grew the dispatcher, a potion
that kills its target would fire it too late — C# asks *before* `OnUse`.

### W10 — `CheckForEmptyHand` is not called after a potion (LIVE)

`CombatManager.cs:887-893`, with the source comment at `:880-883` naming its two
callers exactly: "after a card is played, and after a potion is used … besides
ending turn, which should not trigger an empty hand check". The two call sites
are `CardModel.cs:1992` and `PotionModel.cs:340`.

The sim's `on_hand_emptied` has **one** call site, `player.py:197`, inside
`discard_hand` — i.e. precisely the site C# excludes. `audit/records/relic/
unceasing_top.json` guard G1 already files this as a LIVE gap with an executed
witness that happens to be a potion (Ashwater emptying a 2-card hand: sim ends
at 0 cards, game at 1). Matched here, not re-derived.

Reachable from **every** potion, not just the hand-emptying ones: C# checks
whether the hand is empty *after* the use, so drinking any potion on an already
empty hand triggers it.

### W4 — the `IsExecutingCardOrPotionEffect` depth counter (dormant)

`CombatManager.cs:889` refuses the empty-hand check while a card *or potion*
effect is still executing, and `PotionModel.cs:324-332` is what puts a potion
inside that bracket. The sim has no counterpart. Dormant for the same reason
`unceasing_top` G2 is dormant: the ported cards that auto-play another card
mid-resolution do not move the draw pile between the inner and outer ends.
Distinct from `unceasing_top` G2 only in that the *outer* frame here is a potion
(Distilled Chaos auto-plays three cards from inside `OnUse`), so a fix to G2 that
only brackets card plays would leave this half open.

## The belt

Not part of `OnUseWrapper`, but shared by every unit and already owned by relic
records. Listed so unit records can cite rather than re-derive:

- **`PotionCmd.TryToProcure` is not the sim's procure path.** `player.add_potion`
  (`player.py:107-121`) skips `Hook.ShouldProcurePotion` and
  `Hook.AfterPotionProcured` — `relic/petrified_toad` G1/G2, `relic/belt_buckle`,
  `relic/sozu`. Only `entropic_brew` among the 51 procures potions itself.
- **Belt size.** `PlayerCombatState.MAX_POTIONS = 3` (`player.py:57`);
  `relic/potion_belt` and `relic/phial_holster` are the growth paths. The
  belt-full drop is therefore reachable, which is what makes Entropic Brew's
  `while HasOpenPotionSlots` loop terminate identically on both sides.
- **Slot identity is observable.** `UsePotion N` in a recording names a slot, and
  `conformance/runner.py:625-631` diffs `floor_potions` slot-by-slot; the belt is
  never compacted on either side (`player.py:123-127`).

## Facts the sweeps settled (re-run, do not quote)

`py audit/tools/potion_probes.py`:

- `sweep-attrs`: **0** mismatches over 51 units × 5 attributes (Rarity, Usage vs
  `automatic`, TargetType vs `targeted`, `CanBeGeneratedInCombat`, pool
  membership). This is *not* a clear — `TargetType` has five values and the sim
  models one boolean, so `AllEnemies`/`Self`/`AnyPlayer` all read `targeted=False`
  and only `AnyEnemy` is distinguished.
- `sweep-usage`: `CombatOnly` 46, `AnyTime` 4 (`blood_potion`, `entropic_brew`,
  `foul_potion`, `fruit_juice`), `Automatic` 1 (`fairy_in_a_bottle`). The sim has
  exactly one `def use_potion`, on `CombatState` — so every `AnyTime` potion's
  out-of-combat arm has no sim path at all.
- `sweep-hooks`: exactly one potion is a hook listener on each side, and it is
  the same one — `fairy_in_a_bottle` (`ShouldDie` + `AfterPreventingDeath`).
  Agrees with `seam/hook_dispatch` step 15's executed evidence.
- `sweep-overrides`: no potion has a non-root base class, so
  `validate --strict-inherited` has nothing to add for this kind.
