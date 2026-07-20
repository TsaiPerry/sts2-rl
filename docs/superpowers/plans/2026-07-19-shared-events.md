# Shared (cross-act) events — port plan

> **STATUS (2026-07-19): 16 of 18 shared events shipped, plus the shared
> ancient Darv.** Waves 1–3 (15 events), the SHARED_EVENTS queue wiring, and
> wave 4's Darv + Fake Merchant are done and green (2103 tests).
>
> **Deferred by decision, not by accident:**
> - **Crystal Sphere** — its whole payout is the 11×11 reveal minigame
>   (`Events/Custom/CrystalSphereEvent/`). Any headless form is an invented
>   abstraction rather than a port, so it was left out instead of guessed at.
> - **War Historian Repy** — `IsAllowed => false` in the source; it is reached
>   only by carrying a Lantern Key card into its room, via a quest/room hook
>   the sim does not model. Porting the event without that hook would add
>   unreachable code.
>
> Everything below is the original plan; the per-wave notes stand as the
> record of what was built.

**Goal:** port `ModelDb.AllSharedEvents` (18 events available in every act's
event queue, ModelDb.cs:135) and `AllSharedAncients` (Darv), closing the
"no shared (cross-act) events" deviation documented in rooms.py.

**Source of truth:** `c:\Users\Perry\Desktop\Slay the Spire 2\src\Core\`
(paths below relative to that). Non-ascension values; everything unlocked
(epoch gates Event1/2/3Epoch are skipped, matching the sim's convention).

## Wiring (rooms.py)

`ActModel.GenerateRooms` (ActModel.cs:334) builds each act's event queue as
`AllEvents.Concat(ModelDb.AllSharedEvents)` then shuffles. Sim change:
`RoomSet.generate` seeds `event_ids` from `rooms.event_pool + SHARED_EVENTS`
(a new tuple in `events/__init__.py`, in ModelDb order) before the existing
shuffle. `ensure_next_event_is_valid` already applies `is_allowed` + the
seen-set, which is how gated shared events (act windows, gold/potion/relic
predicates) stay out of ineligible acts.

NOTE: this changes seeded event-queue draws — update any test that pins a
queue order (the golden rule: fidelity wins over old sim behavior).

## The 18 events (Models/Events/*.cs), grouped by dependency wave

Per event: one module in `sts2_rl/events/`, `@register_event`, options named
after the source loc keys, `is_allowed` mirrored exactly, tests in
`test/test_shared_events.py`. RNG call ORDER must match the source
(e.g. StoneOfAllTime burns `Rng.NextInt(100)` after each choice).

### Wave 1 — no new content systems

- **SlipperyBridge** (floor > 6, all decks have a removable card):
  OVERCOME removes the shown random non-Basic card; HOLD_ON deals
  3+n unblockable/unpowered HP loss (n = holds so far), re-rolls the shown
  card excluding previously shown types (`SkippedRemovals`), loops forever
  (page suffix caps at LOOP after 7).
- **ThisOrThat**: PLAIN = 6 HP loss + gain rng(41,68) gold (CalculateVars);
  ORNATE = grab-bag relic + Clumsy curse. (Clumsy ✓ in sim.)
- **TheLegendsWereTrue** (act 1, deck > 0, hp ≥ 10): NAB_THE_MAP = add a
  Spoils Map card to deck (✓ in sim); SLOWLY_FIND_AN_EXIT = 8 damage +
  offer 1 random unlocked potion (PlayerRng.Rewards in source; sim single
  stream).
- **BrainLeech** (acts 1-2): SHARE_KNOWLEDGE = pick 1 of 5 character-pool
  reward cards into deck; RIP = 5 unblockable/unpowered damage + a 3-card
  Colorless reward offer (no rarity mods).
- **TheFutureOfPotions** (all players ≥ 2 potions): options = first 3 held
  potions; trade one → discard it, offer 3 UPGRADED character-pool cards of
  mapped rarity (Rare/Event→Rare, Uncommon→Uncommon, Common/Token→Common)
  and a per-potion pre-rolled random type (Attack/Skill; +Power only for
  Uncommon+ rarities — see PotionToCardType). CanRemovePotions guard is
  UI-only (sim has no out-of-combat potion discard) — skip, document.
- **RanwidTheElder** (acts 2-3, all: ≥1 tradable relic, gold ≥ 100,
  ≥1 potion): give a random potion → 1 grab-bag relic; 100 gold → 1;
  a random tradable relic → 2. Locked-option placeholders when the roll
  finds nothing. Needs `Relic.is_tradable` (RelicModel.IsTradable —
  read source for which relics opt out; default true).
- **RelicTrader** (acts 2-3, all players ≥ 5 tradable relics): 3 owned
  (stable-shuffled) paired against 3 grab-bag pulls; trade one pair.
  OwnedRelics/NewRelics are rolled lazily at first options build.
- **RoomFullOfCheese** (acts 1-2): GORGE = pick 2 of 8 uniform-Common
  character-pool cards; SEARCH = 14 damage + **ChosenCheese** relic (NEW —
  Models/Relics/ChosenCheese.cs).

### Wave 2 — new enchantments (enchantments.py)

New: **Sharp**, **Nimble**, **Vigorous**, **Corrupted**
(Models/Enchantments/*.cs — read for exact hooks; Swift already ported).

- **SelfHelpBook**: enchant Sharp×2 on an Attack / Nimble×2 on a Skill /
  Swift×2 on a Power (each option locked if no eligible deck card).
- **StoneOfAllTime** (act 2, all have a potion): LIFT = discard a random
  potion, +10 max HP, burn rng(100); PUSH = 6 HP loss, Vigorous×8 on a
  chosen card, burn rng(100).
- **Symbiote** (acts 2-3): APPROACH = Corrupted×1 on a chosen card (locked
  if none enchantable); KILL_WITH_FIRE = transform 1 card.

### Wave 3 — new potion + relic packs

- **FoulPotion** (Models/Potions/FoulPotion.cs, Event rarity, any-time):
  in combat = 12 unpowered damage to ALL enemies; at a shop = +100 gold &
  the merchant leaves (NMerchantRoom.FoulPotionThrown); at FakeMerchant =
  starts its fight. Port combat + shop halves with Wave 3, FakeMerchant
  half with Wave 4.
- **PotionCourier** (acts 2-3): GRAB_POTIONS = offer 3 Foul Potions;
  RANSACK = offer 1 random UNCOMMON potion.
- **TeaMaster** (acts 1-2, all gold ≥ 150): 50g → **BoneTea**, 150g →
  **EmberTea**, free → **TeaOfDiscourtesy** (3 NEW relics).
- **DollRoom** (act 2): random 1 of 3 / 5 HP → stable-shuffled choose 1 of
  2 / 15 HP → choose 1 of 3 of **DaughterOfTheWind**, **MrStruggles**,
  **BingBong** (3 NEW relics).
- **WelcomeToWongos** (act 2, all gold ≥ 100): 100g → Common grab-bag relic
  (shop-allowed filter), 200g → pre-rolled Rare (**featured**), 300g →
  **WongosMysteryTicket** (NEW), LEAVE → downgrade a random upgraded card.
  Wongo points are meta-progression (SaveManager.Progress) — a run can
  earn at most 32/purchase toward 2000, so the badge relic
  (**WongoCustomerAppreciationBadge**) is unreachable in one run; model
  points per-run, document the badge as effectively-unreachable (still
  port the relic if trivial, else stub).

### Wave 4 — heavy

- **FakeMerchant** (acts 2-3, single-player, gold ≥ 100 OR holding a Foul
  Potion): a fake shop. Sim mapping (documented approximation of the
  custom UI): options = the 6 stocked fake relics @50g each (NEW relics:
  FakeAnchor, FakeBloodVial, FakeHappyFlower, FakeLeesWaffle, FakeMango,
  FakeOrichalcum, FakeSneckoEye, FakeStrikeDummy, FakeVenerableTeaSet —
  9 in pool, 6 stocked per visit via UnstableShuffle) + LEAVE + (if
  holding Foul Potion) THROW = fight **FakeMerchantEventEncounter**
  (Models/Encounters/) rewarding **FakeMerchantsRug** + remaining stock.
- **CrystalSphere** (acts 2-3, all gold ≥ 100): UNCOVER_FUTURE = lose
  50+rng(1,49) gold, minigame ×3 clicks; PAYMENT_PLAN = gain Debt curse
  (✓ in sim), minigame ×6. Minigame (Events/Custom/CrystalSphereEvent/):
  11×11 grid, corners + two ring expansions pre-cleared, 14 items placed
  by rng (1 relic, 2 common + 1 rare potion, C/U/R card rewards, 1 curse,
  5 small + 2 big gold); each click = 3×3 clear (Big tool); fully-revealed
  items pay out. Headless approximation: clicks become
  `run.select_option` decisions over a coarse grid, or scripted-random —
  decide at implementation, document either way.
- **Darv** (shared ancient): `UnlockState.SharedAncients` = [Darv];
  RunManager.GenerateRooms shuffles and partitions the shared list across
  acts 2..N (`NextInt(count+1)` per act, consumed in order); each act's
  ancient roll = `NextItem(act ancients ∪ subset)`. Sim: extend
  driver.ACT_ANCIENTS rolling. Options: per relic-set filters (act 2:
  Ectoplasm|Sozu; act 3: PhilosophersStone|VelvetChoker; always:
  Astrolabe, BlackStar, CallingBell, EmptyCage, PandorasBox (deck-clear
  modifier filter — always true in sim), RunicPyramid, SneckoEye), pick
  one per eligible set, UnstableShuffle, then coin flip: 2 + **DustyTome**
  (with SetupForPlayer) or plain 3. 12 NEW relics — most are run-altering
  (transforms, card manipulation); port with the same care as the
  Ancient-shrine relic pools epic.
- **WarHistorianRepy**: `IsAllowed => false` — reached only by carrying a
  LanternKey card (sim: events/the_lantern_key.py grants it). Check how
  the game surfaces the Repy room (quest/map hook) before porting; grants
  **HistoryCourse** (NEW relic) or a 2-potion + 2-relic reward chest,
  consuming the key(s).

## Test strategy

- `test/test_shared_events.py`: per-event behavior + is_allowed gates,
  driven headlessly like test_events_*.py (fresh_run + make_event).
- Queue wiring: a seeded run's act queue contains shared ids; gated ones
  skipped via ensure_next_event_is_valid.
- Relic/enchantment behavior tests beside their kin (test_relics.py /
  test_powers-style seeded combats).
- Full suite green at each wave boundary; update seed-pinned tests broken
  by the queue-content change (fidelity wins).

## Conventions

- One module per event/relic; docstrings cite the .cs file; loc-key option
  names; single RNG stream (documented deviation); commands not direct
  mutation; no commits (user commits).
