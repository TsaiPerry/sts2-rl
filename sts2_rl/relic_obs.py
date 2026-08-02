"""relic_obs.py — pure, side-effect-free mapping from a live relic instance to
its observation row: ``(counter, flag)``. Implements OBS_SCHEMA.md §6 (R1 of
`prompts/entity-obs-schema.md` phase 1), whose row shape is
``(relic_id, counter, flag)`` — the id half is written by the observation
caller from `vocab.py`; this module supplies only the two aux floats.

THE PRINCIPLE (do not weaken this without re-reading the source): a relic's
internal state may enter the observation only if the game draws it on the
relic icon. The game has exactly THREE display paths, and nothing else:

1. ``NRelicInventoryHolder.RefreshAmount`` (`NRelicInventoryHolder.cs:116-119`),
   gated on ``RelicModel.ShowCounter`` (default `false`, `RelicModel.cs:347`) —
   the on-icon number, read from ``RelicModel.DisplayAmount``
   (default `0`, `RelicModel.cs:349`).
2. Status tinting / the pulse-or-dim shader parameter
   (`RelicModel.cs:487-503`'s `UpdateTexture`, driven by the `Status` enum
   property `RelicModel.cs:330-345`) — set by individual relics via
   ``base.Status = RelicStatus.Active/Disabled/Normal``.
3. ``IsUsedUp``'s hovertip rewrite (`RelicModel.cs:365-369`).

All three display paths are opt-in per relic (verified by reading every
relic file under `Slay the Spire 2/src/Core/Models/Relics/*.cs`, not sampled) —
"the sim tracks it" or "a mod could read it" are never arguments for
inclusion; only a citation to one of the three paths above is.

Census (re-measured 2026-08-01, this file): ``ALL_RELICS`` holds 259
registered classes; instantiating all of them finds **70 with mutable
state** (65 set an attribute in ``__init__``, 5 more — the ``_healed``
conformance shims — create one lazily) and **189 with none at all**, for
which presence alone is a complete description and ``relic_row`` returns
``(0, 0)``.

Of the 70 stateful relics, this module admits **50**: **32 carry a counter**
(28 counter-only + 4 with both), **22 carry a flag** (18 flag-only + 4 with
both), and **20 are excluded outright** — no ``ShowCounter``, ``Status``
assignment or ``IsUsedUp`` override anywhere in their `.cs` file. See
``EXCLUDED_RELIC_STATE`` for the exact attributes that must never reach the
tensor, and the module docstring in `prompts/entity-obs-schema.md`'s report
for four corrections this census makes to the 2026-08-01 planning-doc
census (verified against source, not copied from prose):

- **`brilliant_scarf` and `paels_legion` are ALSO in-combat-only** —
  `BrilliantScarf.cs:125-135` guards `ShowCounter` on
  `CombatManager.Instance.IsInProgress` exactly like the other 8, and
  `PaelsLegion.cs`'s `DisplayAmount` returns `-1` (hidden) whenever
  `!CombatManager.Instance.IsInProgress`. The in-combat-only set is **10
  relics, not 8**.
- **`rainbow_ring` has a genuine Status tint** (`RainbowRing.cs:90`,
  `base.Status = _activationCountThisTurn > 0 ? Active : Normal`) — admitted
  here as a flag (`_activated`), with its three per-type progress bools
  (`_attack`, `_skill`, `_power` — never independently displayed) excluded.
- **`lava_rock`, `venerable_tea_set` and `fake_venerable_tea_set` also tint
  Status** (`LavaRock.cs:62`, `VenerableTeaSet.cs:36`,
  `FakeVenerableTeaSet.cs:38`) and are admitted as flags.

Design choice on redundant flags: several counter relics (kunai, nunchaku,
pen_nib, tuning_fork, diamond_diadem, pocketwatch, brilliant_scarf, …) ALSO
tint Status, but always as a pure function of the SAME counter already
returned (`counter == threshold`), so a second field would carry zero new
information. Those are published as counter-only. A flag is added alongside
a counter only where it depends on genuinely separate state the counter
cannot express (`silver_crucible.treasure_rooms_entered`,
`wongos_mystery_ticket.gave_relic`, `toy_box`'s two different thresholds on
one counter) or, cheaply, wherever `IsUsedUp` is a real override
(`winged_boots`) even if it happens to be arithmetically derivable — because
`IsUsedUp` is itself display path 3, independent of path 1.

Three implementation rules (OBS_SCHEMA.md §6), each of which leaks silently
if done naively:

1. **Publish the DISPLAYED value, never the raw attribute.** Seven relics
   (`book_of_five_rings`, `iron_club`, `nunchaku`, `fishing_rod`,
   `lasting_candy`, `toy_box`, `paels_wing`) store a cumulative count the UI
   only ever shows modulo something; three more invert it (`N − x`:
   `winged_boots`, `silver_crucible`, `wongos_mystery_ticket`); `paels_tooth`
   shows a `len()`. `pen_nib._attacks_played` and `joss_paper.cards_exhausted`
   already store the modulo'd value in the sim (`pen_nib.py:34`,
   `joss_paper.py:855`) — checked against `PenNib.cs:1945-1957` /
   `JossPaper.cs:695-703`, not assumed; this module still applies a
   defensive `% N` so a future change to either relic cannot silently regress
   into a raw-counter leak.
2. **In-combat-only counters read 0 outside combat.** `relic_row` takes a
   mandatory keyword-only `in_combat` so a caller cannot forget it; ten
   relics gate their counter on it (see above — two more than the
   plan-stage census found).
3. **Excluded state must be excluded.** `EXCLUDED_RELIC_STATE` is the
   non-leak test's data-driven fixture: relic id -> the attribute name(s)
   that must never influence `relic_row`'s output. The two that matter most:
   `fur_coat.marked_coords` is future map knowledge (`fur_coat.py:23,46,90`)
   and `dusty_tome.ancient_card` names a card the player has not been shown.

Counter scaling: this module returns the RAW displayed integer (post
modulo/inversion/clamp); the observation lane divides by `CLAMP_CEILING`
(10, so admitted values land in `[0, 0.9]`) — see OBS_SCHEMA.md §5.2's
`player.relics.f` row, `(counter/10, flag)`. `CLAMP_CEILING` here is **9**:
the maximum statically-bounded admissible counter (the three mod-10 relics —
nunchaku, pen_nib, tuning_fork). Three counters are uncapped in the source
(`pocketwatch`, `diamond_diadem`: raw cards-played-this-turn, unbounded on an
infinite-combo turn; `pumpkin_candle`: +5 per kindle with no re-kindle cap)
and are clamped to the same ceiling — chosen uniformly rather than per-relic
so every admitted counter shares one saturation point and the `/10` lane
never needs a second scale. The clamp is applied uniformly to every
admitted counter (a no-op for the ones already bounded below 9), not
selectively, so a future relic added to this table cannot silently reopen
an unbounded channel by omission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

# The ceiling every admitted counter is clamped to before being handed to
# the observation lane's `/10` scaling. See the module docstring.
CLAMP_CEILING = 9


@dataclass(frozen=True)
class _RelicSpec:
    counter: Optional[Callable[[object], int]] = None
    counter_in_combat_only: bool = False
    flag: Optional[Callable[[object], bool]] = None
    flag_in_combat_only: bool = False


def _clamp(value: int) -> int:
    if value < 0:
        return 0
    if value > CLAMP_CEILING:
        return CLAMP_CEILING
    return value


# ---------------------------------------------------------------------------
# Counter-only relics (28) — a displayed number, no independent flag.
# citations are the DisplayAmount/ShowCounter overrides in
# `Slay the Spire 2/src/Core/Models/Relics/<ClassName>.cs`.
# ---------------------------------------------------------------------------
_COUNTER_ONLY: dict[str, Callable[[object], int]] = {
    "girya": lambda r: r.times_lifted,                                # Girya.cs:26,338 (0-3)
    "book_of_five_rings": lambda r: r.cards_added % 5,                # BookOfFiveRings.cs:24-34
    "iron_club": lambda r: r.cards_played % 4,                        # IronClub.cs:487-499
    "fishing_rod": lambda r: r.combats_seen % 3,                      # FishingRod.cs:21
    "lasting_candy": lambda r: r.combats_seen % 2,                    # LastingCandy.cs:1011-1021
    "paels_wing": lambda r: r.rewards_sacrificed % 2,                 # PaelsWing.cs:1820-1830
    "nunchaku": lambda r: r._attacks_played % 10,                     # Nunchaku.cs:1292-1302
    "pen_nib": lambda r: r._attacks_played % 10,                      # PenNib.cs:1919-1929 (already % 10)
    "tuning_fork": lambda r: r._skills_played % 10,                   # TuningFork.cs:2559-2569 (self-resetting)
    "sword_of_stone": lambda r: r.elites_defeated,                    # SwordOfStone.cs:19-21 (0-5)
    "ember_tea": lambda r: max(0, r.combats_left),                    # EmberTea.cs:23-27 (0-5)
    "kunai": lambda r: r._attacks_this_turn % 3,                      # Kunai.cs:739-749
    "kusarigama": lambda r: r._attacks_this_turn % 3,                 # Kusarigama.cs:870-880
    "letter_opener": lambda r: r._skills_this_turn % 3,               # LetterOpener.cs:1152-1162
    "ornamental_fan": lambda r: r._attacks_this_turn % 3,             # OrnamentalFan.cs:1406-1416
    "shuriken": lambda r: r._attacks_this_turn % 3,                   # Shuriken.cs:2301-2311
    "velvet_choker": lambda r: r.cards_played_this_turn,              # VelvetChoker.cs:2678-2688 (raw, capped at 6 by mechanics)
    "diamond_diadem": lambda r: r.cards_played_this_turn,             # DiamondDiadem.cs:22-24 (raw, clamped by this module)
    "pocketwatch": lambda r: r._played_this_turn,                     # Pocketwatch.cs:25-27 (raw, clamped by this module)
    "brilliant_scarf": lambda r: (
        r.cards_played_this_turn if r.cards_played_this_turn < 5 else 0
    ),                                                                 # BrilliantScarf.cs:125-137
    "paels_legion": lambda r: max(0, r.cooldown),                     # PaelsLegion.cs:1564-1582 (0-2)
    "joss_paper": lambda r: r.cards_exhausted % 5,                    # JossPaper.cs:603-613 (already % 5)
    "fake_happy_flower": lambda r: r.turns_seen % 5,                  # FakeHappyFlower.cs:275-285
    "happy_flower": lambda r: r.turns_seen % 3,                       # HappyFlower.cs:385-395
    "pendulum": lambda r: r.turns_seen % 3,                           # Pendulum.cs:2062-2072
    "pollinous_core": lambda r: min(r.turns_seen, 4),                 # PollinousCore.cs:2167-2177
    "paels_tooth": lambda r: len(r.stored_cards),                     # PaelsTooth.cs:1689-1699 (count, never contents)
    "pumpkin_candle": lambda r: r.kindle_count,                       # PumpkinCandle.cs:24-26 (uncapped, clamped by this module)
}

# ---------------------------------------------------------------------------
# Flag-only relics (18) — Status tint or IsUsedUp hovertip, no counter.
# ---------------------------------------------------------------------------
_FLAG_ONLY: dict[str, Callable[[object], bool]] = {
    "art_of_war": lambda r: not r._attacks_last_turn,                 # ArtOfWar.cs:70-107 (approximation, see report)
    "belt_buckle": lambda r: r._applied,                              # BeltBuckle.cs:235-245
    "burning_sticks": lambda r: r._used_this_combat,                  # BurningSticks.cs:281-309
    "lizard_tail": lambda r: r.is_used_up,                            # LizardTail.cs:404-424
    "maw_bank": lambda r: r.is_used_up,                               # MawBank.cs:471-489
    "paels_eye": lambda r: r.used_this_combat,                        # PaelsEye.cs:602-660
    "red_skull": lambda r: r._applied,                                # RedSkull.cs:747-765
    "ripple_basin": lambda r: r._attack_this_turn,                    # RippleBasin.cs:794-826
    "silken_tress": lambda r: r.is_used_up,                           # SilkenTress.cs:853-875
    "throwing_axe": lambda r: r.used_this_combat,                     # ThrowingAxe.cs:1098-1134
    "unsettling_lamp": lambda r: r._finished,                         # UnsettlingLamp.cs:1200-1292 (IsFinishedTriggering)
    "vambrace": lambda r: r._used,                                    # Vambrace.cs:1357-1421 (BlockGainedThisCombat)
    "rainbow_ring": lambda r: r._activated,                           # RainbowRing.cs:90
    "bone_tea": lambda r: r.is_used_up,                               # BoneTea.cs:23-27 (ShowCounter false; hovertip only, range 0-1)
    "tea_of_discourtesy": lambda r: r.is_used_up,                     # TeaOfDiscourtesy.cs:23-25 (same pattern as bone_tea)
    "lava_rock": lambda r: r.has_triggered,                           # LavaRock.cs:62
    "venerable_tea_set": lambda r: r._pending,                        # VenerableTeaSet.cs:36
    "fake_venerable_tea_set": lambda r: r._pending,                   # FakeVenerableTeaSet.cs:38
}

# ---------------------------------------------------------------------------
# Both counter AND flag (4) — the flag depends on state the counter alone
# cannot express (or, for winged_boots, IsUsedUp is display path 3 on its
# own merits even though it happens to be arithmetically derivable here).
# ---------------------------------------------------------------------------
_BOTH: dict[str, tuple[Callable[[object], int], Callable[[object], bool]]] = {
    "silver_crucible": (
        lambda r: max(0, 3 - r.times_used),                           # SilverCrucible.cs:967 (Cards=3, inversion)
        lambda r: r.is_used_up,                                       # :943-953 (also needs treasure_rooms_entered — excluded)
    ),
    "wongos_mystery_ticket": (
        lambda r: max(0, 5 - r.combats_finished),                     # WongosMysteryTicket.cs:30 (inversion)
        lambda r: r.gave_relic,                                       # :26-28 (IsUsedUp => GaveRelic)
    ),
    "toy_box": (
        lambda r: r.combats_seen % 3,                                 # ToyBox.cs:36-44
        lambda r: r.is_used_up,                                       # :32 (CombatsSeen >= Combats*Relics — a different threshold)
    ),
    "winged_boots": (
        lambda r: max(0, 3 - r.times_used),                           # WingedBoots.cs:26 (inversion)
        lambda r: r.is_used_up,                                       # :22
    ),
}

# ---------------------------------------------------------------------------
# In-combat-only counters (10 — two more than the 2026-08-01 planning-doc
# census found: brilliant_scarf and paels_legion also gate ShowCounter /
# DisplayAmount on CombatManager.Instance.IsInProgress). See module
# docstring.
# ---------------------------------------------------------------------------
_IN_COMBAT_ONLY_COUNTERS = frozenset({
    "kunai", "kusarigama", "letter_opener", "ornamental_fan", "shuriken",
    "velvet_choker", "diamond_diadem", "pocketwatch", "brilliant_scarf",
    "paels_legion",
})


def _build_table() -> dict[str, _RelicSpec]:
    table: dict[str, _RelicSpec] = {}
    for rid, counter_fn in _COUNTER_ONLY.items():
        table[rid] = _RelicSpec(
            counter=counter_fn,
            counter_in_combat_only=rid in _IN_COMBAT_ONLY_COUNTERS,
        )
    for rid, flag_fn in _FLAG_ONLY.items():
        table[rid] = _RelicSpec(flag=flag_fn)
    for rid, (counter_fn, flag_fn) in _BOTH.items():
        table[rid] = _RelicSpec(
            counter=counter_fn,
            counter_in_combat_only=rid in _IN_COMBAT_ONLY_COUNTERS,
            flag=flag_fn,
        )
    return table


_TABLE: dict[str, _RelicSpec] = _build_table()


def relic_row(relic, *, in_combat: bool) -> tuple[int, int]:
    """``(counter, flag)`` for one relic instance — the DISPLAYED values,

    never the raw attribute. ``in_combat`` is mandatory (keyword-only) so a
    caller cannot forget the eight — now ten — in-combat-only gates by
    relying on a default.

    Pure and side-effect-free: reads attributes off `relic`, never mutates
    it, never touches `relic.combat` / `relic.player` beyond what the
    lambdas above read (all of which are already-computed scalars, not
    fresh hook dispatches).
    """
    spec = _TABLE.get(getattr(relic, "id", None))
    if spec is None:
        return (0, 0)

    counter = 0
    if spec.counter is not None and (in_combat or not spec.counter_in_combat_only):
        counter = _clamp(int(spec.counter(relic)))

    flag = 0
    if spec.flag is not None and (in_combat or not spec.flag_in_combat_only):
        flag = int(bool(spec.flag(relic)))

    return (counter, flag)


# ---------------------------------------------------------------------------
# EXCLUDED_RELIC_STATE — the non-leak test's fixture. Every attribute listed
# here is mutable sim state that must NEVER influence `relic_row`'s output,
# either because the whole relic has no display path (verified: no
# `ShowCounter`, `Status =` assignment or `IsUsedUp` override anywhere in
# its `.cs` file) or because it is the un-displayed half of an
# otherwise-admitted relic's internal bookkeeping.
# ---------------------------------------------------------------------------
EXCLUDED_RELIC_STATE: dict[str, tuple[str, ...]] = {
    # Fully excluded: no display path at all (20 relics; 15 + the 5
    # sim-only `_healed` conformance shims, which have no C# counterpart).
    "beating_remnant": ("_received_this_turn",),
    "bing_bong": ("_cards_to_skip",),
    "centennial_puzzle": ("_used_this_combat",),
    "demon_tongue": ("_triggered_this_turn",),
    "dusty_tome": ("ancient_card",),          # a card the player has not been shown
    "fake_orichalcum": ("_should_trigger",),
    "orichalcum": ("_should_trigger",),
    "fur_coat": ("act_index", "marked_coords", "_armed"),  # future map knowledge
    "golden_compass": ("golden_path_act",),
    "lava_lamp": ("took_damage_this_combat", "_in_combat_room"),
    "music_box": ("used_this_turn", "_card_being_played"),
    "paels_tears": ("had_leftover_energy",),
    "permafrost": ("_activated",),
    "ruined_helmet": ("_used",),
    "self_forming_clay": ("_pending_block",),
    "lees_waffle": ("_healed",),
    "looming_fruit": ("_healed",),
    "mango": ("_healed",),
    "pear": ("_healed",),
    "strawberry": ("_healed",),
    # Second attributes on otherwise-admitted relics — the un-displayed
    # half of a two-part internal latch.
    "pen_nib": ("_card_to_double",),
    "vambrace": ("_triggering_card",),
    "paels_legion": ("_affected_card",),
    "pocketwatch": ("_played_last_turn",),
    "unsettling_lamp": ("_in_flight", "_triggering"),
    "silver_crucible": ("treasure_rooms_entered",),
    "rainbow_ring": ("_attack", "_skill", "_power"),
    "art_of_war": ("_attacks_this_turn",),
    "joss_paper": ("_ethereal_pending",),
    # paels_tooth.stored_cards: the COUNT (len()) is admitted as the
    # counter; the card IDENTITIES inside the list must never leak. Not
    # listed here (the attribute itself is legitimately read) — pinned
    # instead by a dedicated identity-invariance test.
}
