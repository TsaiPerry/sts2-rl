# R5 — the Play-pile family (N9+step82, step51, step56, G8's last site; step99 is STALE)

Read first: `.superpowers/sdd/round13/PROTOCOL.md` (binding). Maps below
scouted 2026-08-01; re-verify before building. Wave 2: R1's hook-registry
rework landed in wave 1 — read `hooks.py`'s CURRENT state before touching
anything; the listener order may now be derived from pile membership, in
which case your new pile becomes part of that derivation.

## Premise corrections (the queue is stale on three counts)

1. **`creature_card_cmds/step99` (AutoPlayFromDrawPile) is ALREADY
   IMPLEMENTED** — `cmds.py:1437-1491`, two-phase, callers
   `cards/havoc.py:53` + `powers.py:4317`, tested in
   `test/test_auto_play_from_draw_pile.py`. Verify, then propose closing
   as STALE. Its one Play-pile defect: Phase-1 picks are parked NOWHERE
   (C# parks them in Play, `CardPileCmd.cs:955`) — park them in your new
   pile.
2. The discard-holdback is **unconditional**, not parity-gated
   (`player.py:389-399` documents the 2026-07-29 removal of the
   `is_parity` gate). No parity constraint applies to the pile move.
3. Sim line refs in older prose have drifted; current: holdback sites
   `player.py:375-425` and `:427-466`; play resolution
   `combat.py:883-1019`.

## The core port (N9 + step82): a physical `play_pile`

C#: a card being played sits in `PileType.Play` for the whole of OnPlay.
- Enum order `PileType.cs`: None=0, Draw=1, Hand=2, Discard=3, Exhaust=4,
  Play=5, Deck=6. Play IS a combat pile (`PileTypeExtensions.cs:35-42`).
- `AllPiles` = Hand, Draw, Discard, Exhaust, Play — Play LAST
  (`PlayerCombatState.cs:70-80`); `AllCards` flattens it (`:81`).
- ENTRY, manual play: `CardPileCmd.AddDuringManualCardPlay`
  (`CardPileCmd.cs:647-684`): captures `oldPile` at `:659` BEFORE the
  move, `RemoveFromCurrentPile` `:669`, `AddInternal` into Play `:670`
  (raw insert — NO per-card hook), then the ONE dispatch:
  `:683 Hook.AfterCardChangedPiles(runState, combatState, card,
  oldPile?.Type ?? None, clonedBy: null)` — fires AFTER the move, oldPile
  = Hand for a manual play. **This is creature_card_cmds/G8's last
  unwired site; wiring it closes G8 entirely** (the other three sites
  landed in rounds 12's T8/T20).
- ENTRY, auto play: `CardModel.cs:1879` (full `Add` into Play) and the
  pre-emptive `CardCmd.cs:114-116` (`if (card.Pile == null) Add(card,
  Play)`). ENTRY, refused play: `CardCmd.cs:133-137` moves to Play before
  `MoveToResultPileWithoutPlaying`.
- BONUS SITE the queue never listed: `CardModel.OnTurnEndInHandWrapper`
  (`CardModel.cs:1682-1698`) parks the card in Play during
  `OnTurnEndInHand`, then Ethereal→Exhaust else Add(Discard). The sim's
  `combat.py:773-816` leaves the card in NO pile during the effect.
  In-scope: match C#.
- EXIT after OnPlay: `CardModel.cs:1976-1990` — **gated on
  `pile.Type == PileType.Play`** (a no-op if an effect already moved the
  card out mid-play), then switch on the modified result pile: None →
  `RemoveFromCombat`; Exhaust → `CardCmd.Exhaust`; default → full
  `CardPileCmd.Add` (which fires AfterCardChangedPiles at
  `CardPileCmd.cs:635` with oldPileType=Play).
  `GetResultPileTypeForCardPlay` (`CardModel.cs:2069-2081`): Dupe/Power →
  None; ExhaustOnNextPlay-or-Exhaust-keyword (consumed on read) →
  Exhaust; else Discard.
- `MoveToResultPileWithoutPlaying` (`CardModel.cs:2089-2105`) is ALSO
  gated on Play membership and sends Powers to the DISCARD (doc comment);
  sim's `combat.py:1043-1060` has neither the gate nor the IsDupe branch.
- Shuffle reads ONLY Draw + Discard (`CardPileCmd.cs:864-925`, `:870-871`)
  — with a real Play pile, both holdbacks (`player.py:380-401`,
  `:439-445`) become structurally unnecessary; simplify them away.

## Sim rewrite map (scouted; verify)

- `player.py`: add `play_pile` at `:79-82`; `all_cards` `:113-117` becomes
  hand + draw + discard + exhaust + play (Play LAST); `pile_type_of`
  `:119-142` becomes a real membership test; retire `_playing_card`
  (`:104`) or keep as an alias — your call, justify it.
- `combat.py:883-1019` `_resolve_card_play`: `:895-897` currently appends
  the card to DISCARD (Powers go nowhere — C# puts Powers in Play too;
  the None result happens at EXIT, not entry — fix this); add the entry
  dispatch (G8); rewrite the exit `:1000-1014` to C#'s gated switch;
  `:1043-1060` `_move_to_result_pile_without_playing` gets the Play gate;
  `auto_play_card` `:1072-1081` adds play_pile to its source scan;
  `:773-816` turn-end-in-hand gets the Play leg.
- `cmds.py`: extend the four-pile scans — `ExhaustCmd.exhaust`
  `:1107-1116` (its docstring asserts "no fourth Play limbo case exists"
  — that premise dies; without the fix a mid-play exhaust creates the
  double-membership bug), `CardCmd.afflict` `:1182-1184`,
  `transform_to_random` `:1248-1256`; `auto_play_from_draw_pile`
  `:1437-1491` parks Phase-1 picks in play_pile.
- `combat_card_db.py:33-35` `ordered_piles`: add play_pile as the fifth
  entry (conformance card-id walk; a mid-play card must stay resolvable —
  `test/test_conformance_combat.py:391`).
- De-hacks (self-exclusion workarounds that become dead or WRONG):
  `cards/cascade.py:35-42,61` (removes itself from discard for the
  duration); `cards/headbutt.py:22-24,44-46` (`c is not self` predicate +
  deviation docstring); `cards/trash_heap_cards.py:338` (`is not self`
  guard); `cards/colorless_attacks.py:576-580` (return-to-hand scan needs
  the fifth pile); `powers.py:864-869` CorruptionPower and
  `powers.py:3363-3370` ReboundPower — both guard on
  `card in player.discard_pile`, which is now FALSE mid-play; convert
  them to the play-pile (or the result_pile channel the sim already
  threads at `combat.py:925/1012`) or they silently stop firing. THESE
  TWO ARE THE HARD BLOCKERS — the exit legs `combat.py:1004` and `:1012`
  are likewise guarded on discard membership and become no-ops unless
  rewritten; a played card must never strand in Play.
- `hooks.py`: only the `after_card_changed_piles` docstring's "one site
  remains unwired" paragraph (`:1146-1195`) + whatever seam R1's derived
  order exposes for the fifth pile. If R1's rework already walks piles,
  register/unregister of cards may have changed — READ FIRST.

## step51 — Sly (machinery only; no Sly card is ported)

`CardCmd.DiscardAndDraw` (`CardCmd.cs:174-206`): discard ALL (collecting
`IsSlyThisTurn` cards, `:186-196`), fire per-card AfterCardDiscarded
`:194`, draw `:198-200`, THEN auto-play the collected Sly cards
`:201-204` with `AutoPlayType.SlyDiscard`. Port as a new
`CardCmd.discard_and_draw` in cmds.py. Sim already has the Sly fields
(`cards/base.py:158-162, 207-212, 483-494, 505`). Reroute the two inline
discard loops onto it: `potions.py:255-269` (Gambler's Brew) and — NOTE
FOOTPRINT: potions.py is yours this wave; relics/gambling_chip.py too —
`relics/gambling_chip.py:33-38`. The two currently fire
`on_card_discarded` on OPPOSITE sides of the append (potions hook-then-
append; gambling_chip append-then-hook; C# `CardCmd.cs:192-194` is
append-then-hook) — fixing that asymmetry is in scope and needs its own
pin. `hooks.before_card_auto_played` (`hooks.py:1094-1108`) gains the
AutoPlayType argument.

## step56 — PileIndexSort (machinery only; no multi-card transform ported)

`CardCmd.cs:353-360` sorts by (RAW PileType enum value, original index
captured pre-removal at `:391`) — order Draw(1)→Hand(2)→Discard(3)→
Exhaust(4)→Play(5)→Deck(6), NOT AllPiles order. Applied at `:405`. Sim
transforms are single-card verbs; add the sort helper to the multi-card
path (or document precisely where it will hang) and pin the ordering.

## power/smoggy (carved out of the triage batches for you)

`power/smoggy/AfterCardEnteredCombat` (record `power/smoggy`, hooks key
`AfterCardEnteredCombat`): the sim walks `owner.all_cards` which lacked
the Play pile. Once all_cards includes it, re-derive the entry's claim
and propose its close (or what remains). Do not edit records.

## ADDENDUM (2026-08-01, from R4's review — in scope, same region)

R4's reviewer found `combat.py:940-996` (the play loop you are rewriting)
is missing C#'s `Owner.Creature.IsDead` early return: `CardModel.cs`
checks it at `:1932/:1940/:1950` (before BeforeCardPlayed, before the
enchantment leg, before AfterCardPlayed), so a card play that kills its
own player RETURNS in C# where the sim goes on to dispatch
`after_card_played` (and possibly the enchantment leg). The sim's current
`:995-996` break-on-dead is at the loop tail — wrong slot(s). Re-derive
the exact C# gate positions and land them as part of the exit rewrite,
with a pin (self-damaging lethal play; a vetoed-death play must still
dispatch). Cite `R4-review.md` §findings in your report.

## Tests that pin the OLD behavior (re-stage, don't delete)

`test/test_hook_order.py:339-360`,
`test/test_task8_pile_move_and_generated_hooks.py:213-225`,
`test/test_tier1_residue.py:213-223`,
`test/test_take_random_streams.py:165-183`, `test/test_relics.py:790-812`
— all five manually stage `_playing_card`-in-discard; re-stage against
play_pile keeping their intent. `test/test_auto_play_from_draw_pile.py`
asserts post-play discard membership (should survive). New pins: the G8
entry dispatch (args: oldPile=hand, clonedBy None, AFTER the move); the
exit switch incl. the already-moved no-op; mid-play card excluded from
reshuffle now BY CONSTRUCTION; a mid-play observation of discard size
(env.py:180 semantics — decide + document whether play is observable or
folded into discard; keep obs byte-identical for post-play observations).

## Footprint (yours alone this wave)

`sts2_rl/player.py`, `sts2_rl/combat.py`, `sts2_rl/cmds.py`,
`sts2_rl/powers.py` (Corruption/Rebound only + smoggy re-derivation),
`sts2_rl/potions.py` (Gambler's Brew reroute), `sts2_rl/hooks.py`
(docstring + pile-derivation seam only), `sts2_rl/combat_card_db.py`,
`sts2_rl/cards/cascade.py`, `sts2_rl/cards/headbutt.py`,
`sts2_rl/cards/trash_heap_cards.py`, `sts2_rl/cards/colorless_attacks.py`,
`sts2_rl/cards/base.py` (Sly fields if needed),
`sts2_rl/relics/gambling_chip.py`, `sts2_rl/env.py`/`full_env.py` (verify,
document; avoid observable changes), plus tests.
NOT yours: `driver.py`, `run.py`, `rewards.py`, `events/**`, other
relics/cards, `audit/**`.

## Entries to settle (propose closes/narrows in your report)

`creature_card_cmds/N9` + `/step82` (the pile), `/step99` (STALE),
`/step51` (Sly machinery), `/step56` (PileIndexSort), `/G8` (last site —
full close if the dispatch lands), `power/smoggy`'s hooks entry, plus any
adjacent prose corrections you find. State which reasoning each close
replaces.

Report path: `.superpowers/sdd/round13/R5-report.md`.
