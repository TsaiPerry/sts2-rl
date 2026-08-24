"""snapshots.py — mid-run start-state snapshots for the combat env (R11,
phase 3 of the entity-obs-schema work, Task 2).

A `Snapshot` captures the six facts a combat needs to start with full
fidelity instead of the combat env's synthetic defaults (fresh basic deck,
zero relics, full HP, empty belt): the run's deck (with per-card instance
state), relics (with counters), hp/max_hp, potion belt (slot gaps
preserved), the current act, and which encounter it is about to fight.
`snapshot_from_run` reads those facts off a live `RunState` + `Encounter`
(the exact point `RunDriver._run_combat` reaches right after
`run.create_combat`, per the R11 snapshot invariants); `build_start_state`
turns a `Snapshot` back into fresh engine objects a caller threads into
`CombatState`/`STS2FullCombatEnv`. Fidelity is proven at the OBS level (the
rebuilt state's deck/relic/potion/hp rows match the source's), per phase-3
Locked Decision 2 — never by `repr`/attribute comparison, since a live
`Card`/`Relic` instance carries incidental machinery (hook wiring, combat
back-references) a snapshot must not try to reproduce.

## Deviations from the literal brief (recorded per requirement 1)

1. **`CardSnap` gained `affliction_amount`.** The brief's field list
   (`id, upgraded, enchantment, affliction`) omits it, but
   `full_env.card_features` (`f[24]`) and `card_instance_row` both read
   `card.affliction.amount` into the observation
   (`full_env.py:738,977` — `_clip01(card.affliction.amount / 10.0)`), so a
   snapshot that drops it cannot round-trip the obs row a card with a
   stacked affliction produces. `enchantment` stays a bare id: no obs path
   reads `card.enchantment.amount` (verified: full_env.py only calls
   `_enchantment_id_int`, never touches `.amount`), so nothing is lost by
   restoring every enchantment at its class default.
2. **`upgraded` is genuinely boolean today.** `Card.upgrade_level` is an
   int and `Card.upgrade()` only increments it, but a repo-wide grep of
   `sts2_rl/cards/` finds no card with `max_upgrade_level > 1` — every card
   in the current content set is upgraded 0 or 1 times. `upgraded: bool`
   (`upgrade_level > 0`) is therefore lossless today; restoring sets
   `upgrade_level = 1 if upgraded else 0`. If a future card ever raises
   `max_upgrade_level`, this becomes a real gap — flagged here rather than
   silently wrong.
3. **`RelicSnap` stays `{id, counter}`, per the locked decision — not
   relitigated.** `relic_obs.relic_row` actually returns `(counter, flag)`,
   and ~22 relics are flag-only (their counter is always 0 — e.g.
   `lizard_tail.is_used_up`). A snapshot cannot restore that flag; the
   round trip is still exact for these because `relic_row`'s counter half
   is a constant 0 regardless of the flag, so `0 == 0` holds — but the
   FLAG itself (e.g. "this Lizard Tail has already fired") does not survive
   a snapshot. Recorded as a known, deliberate limitation of the locked
   `{id, counter}` contract, not a bug in this module.
4. **Counter restoration uses a small reverse table
   (`_COUNTER_REBUILD`).** `relic_obs.py`'s per-relic counter functions are
   private closures (not attribute names), so restoring a relic's counter
   generically requires knowing which raw attribute each relic's counter
   function reads. `_COUNTER_REBUILD` mirrors that table for every relic
   `relic_obs._TABLE` admits a counter for (32 relics: 28 counter-only + 4
   both-counter-and-flag), verified against each relic's own source file
   (attribute names confirmed by grep, not guessed from comments). For the
   28 direct/modulo/clamp relics the raw attribute is set to the displayed
   counter itself (every one of those transforms is idempotent under
   self-application — a modulo or clamp applied to an already-reduced value
   is a no-op); the 3 true inversions (`silver_crucible`,
   `wongos_mystery_ticket`, `winged_boots`, each `max(0, N - x)`) invert
   properly; `paels_tooth` (`len(stored_cards)`) rebuilds a
   counter-length placeholder list, since only the count is
   observation-visible (`relic_obs.py`'s own docstring: "the COUNT is
   admitted... the card IDENTITIES inside the list must never leak").
   In-combat-only counters (the 10 relics gated by
   `relic_obs._IN_COMBAT_ONLY_COUNTERS`) need no reverse entry at all:
   `Relic.attach` calls `reset_for_combat()` on every relic a fresh
   `CombatState` registers, which re-zeroes their raw per-combat attribute
   regardless of what a snapshot restored — so their pre-combat counter is
   always 0 both at capture time (the harvest hook fires right after
   `create_combat`, i.e. after this same reset already ran on the run's
   live relics) and at rebuild time.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, TYPE_CHECKING

from .afflictions import make_affliction
from .cards import make_card
from .enchantments import make_enchantment
from .events import (
    BATTLEWORN_DUMMY_SETTING_1,
    BATTLEWORN_DUMMY_SETTING_2,
    BATTLEWORN_DUMMY_SETTING_3,
    DENSE_VEGETATION_EVENT_ENCOUNTER,
    FAKE_MERCHANT_EVENT_ENCOUNTER,
    MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER,
    PUNCH_OFF_EVENT_ENCOUNTER,
)
from .monsters import Encounter
from .monsters.glory import ENCOUNTERS as _GLORY_ENCOUNTERS
from .monsters.hive import ENCOUNTERS as _HIVE_ENCOUNTERS
from .monsters.overgrowth import ENCOUNTERS as _OVERGROWTH_ENCOUNTERS
from .monsters.underdocks import ENCOUNTERS as _UNDERDOCKS_ENCOUNTERS
from .relic_obs import relic_row
from .relics import make_relic

if TYPE_CHECKING:
    from .cards import Card
    from .combat import CombatState
    from .relics import Relic
    from .run import RunState

# Schema 2 (v20 drill env): +gold, +floor (promoted from provenance),
# +room_type ("MONSTER"/"ELITE"/"BOSS" — recorded by the harvester from the
# driver's own room_type, never derived from the encounter id: event-launched
# encounters make that mapping ambiguous), and the harvest ascension in
# provenance. `load_snapshots` hard-rejects schema-1 files (re-harvest rather
# than dual-format support).
SNAPSHOT_SCHEMA = 2


# ─────────────────────────────────────────────────────────────────────────
# Dataclasses
# ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CardSnap:
    id: str
    upgraded: bool
    enchantment: str | None
    affliction: str | None
    # Deviation #1 (module docstring): obs-visible, the brief's field list
    # omits it. `None` whenever `affliction` is `None`.
    affliction_amount: int | None = None

    @staticmethod
    def from_card(card: "Card") -> "CardSnap":
        return CardSnap(
            id=card.id,
            upgraded=card.upgrade_level > 0,
            enchantment=card.enchantment.id if card.enchantment is not None else None,
            affliction=card.affliction.id if card.affliction is not None else None,
            affliction_amount=(
                card.affliction.amount if card.affliction is not None else None
            ),
        )

    def rebuild(self) -> "Card":
        card = make_card(self.id)
        if self.upgraded:
            card.upgrade()
        if self.enchantment is not None:
            # The real EnchantInternal path, not a bare `card.enchantment =`
            # assignment: it wires the enchantment->card BACK-reference
            # (downgrade paths call `enchantment.modify_card()` through it —
            # a one-directional attach left `.card` None and crashed the
            # first time a Knights-elite Dampen downgraded an enchanted card
            # in a v20 drill), and `modify_card()` re-applies the
            # enchantment's field effects, which a FRESH `make_card` needs —
            # unlike the game's clone path, whose copied values already
            # carry them (attach_internal's own docstring).
            enchantment = make_enchantment(self.enchantment)
            enchantment.attach_internal(card)
            enchantment.modify_card()
        if self.affliction is not None:
            # Same back-reference discipline as `CardCmd.afflict`
            # (cmds.py:1451-1452): `hook_contains` reads `affliction.card`,
            # so a one-directional attach silently deadens the affliction's
            # combat hooks.
            affliction = make_affliction(
                self.affliction, self.affliction_amount or 1
            )
            affliction.card = card
            card.affliction = affliction
        return card


@dataclass(frozen=True)
class RelicSnap:
    id: str
    counter: int

    @staticmethod
    def from_relic(relic: "Relic") -> "RelicSnap":
        counter, _flag = relic_row(relic, in_combat=True)
        return RelicSnap(id=relic.id, counter=counter)

    def rebuild(self) -> "Relic":
        relic = make_relic(self.id)
        spec = _COUNTER_REBUILD.get(self.id)
        if spec is not None:
            spec(relic, self.counter)
        return relic


@dataclass(frozen=True)
class Snapshot:
    deck: tuple[CardSnap, ...]
    relics: tuple[RelicSnap, ...]
    hp: int
    max_hp: int
    potion_slots: tuple[str | None, ...]
    act: int
    encounter_id: str
    # Schema 2: run-level facts a run-env drill reset needs that the combat
    # env's synthetic defaults never did. Dataclass defaults are a
    # constructor convenience only — the JSON layer treats all three as
    # REQUIRED (`_snapshot_from_json` KeyErrors on an absent field).
    gold: int = 0
    floor: int = 0
    room_type: str = ""
    # json-safe: {"seed": ..., "ascension": ..., "episode_decisions": ...}.
    # A plain (mutable) dict — see snapshot_from_run's docstring for why the
    # harvester (a separate lane) fills "episode_decisions" in afterward.
    provenance: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────
# Relic counter reverse table (deviation #4)
# ─────────────────────────────────────────────────────────────────────────


def _direct(attr: str) -> Callable[["Relic", int], None]:
    def setter(relic: "Relic", counter: int) -> None:
        setattr(relic, attr, counter)
    return setter


def _inverted(attr: str, base: int) -> Callable[["Relic", int], None]:
    def setter(relic: "Relic", counter: int) -> None:
        setattr(relic, attr, max(0, base - counter))
    return setter


def _paels_tooth(relic: "Relic", counter: int) -> None:
    relic.stored_cards = [None] * counter


# 28 counter-only relics (relic_obs._COUNTER_ONLY) — every transform there is
# `attr`, `attr % n`, `max(0, attr)` or `min(attr, n)`, all idempotent when
# the raw attribute is set directly to the already-displayed counter.
_COUNTER_REBUILD: dict[str, Callable[["Relic", int], None]] = {
    "girya": _direct("times_lifted"),
    "book_of_five_rings": _direct("cards_added"),
    "iron_club": _direct("cards_played"),
    "fishing_rod": _direct("combats_seen"),
    "lasting_candy": _direct("combats_seen"),
    "paels_wing": _direct("rewards_sacrificed"),
    "nunchaku": _direct("_attacks_played"),
    "pen_nib": _direct("_attacks_played"),
    "tuning_fork": _direct("_skills_played"),
    "sword_of_stone": _direct("elites_defeated"),
    "ember_tea": _direct("combats_left"),
    "kunai": _direct("_attacks_this_turn"),
    "kusarigama": _direct("_attacks_this_turn"),
    "letter_opener": _direct("_skills_this_turn"),
    "ornamental_fan": _direct("_attacks_this_turn"),
    "shuriken": _direct("_attacks_this_turn"),
    "velvet_choker": _direct("cards_played_this_turn"),
    "diamond_diadem": _direct("cards_played_this_turn"),
    "pocketwatch": _direct("_played_this_turn"),
    "brilliant_scarf": _direct("cards_played_this_turn"),
    "paels_legion": _direct("cooldown"),
    "joss_paper": _direct("cards_exhausted"),
    "fake_happy_flower": _direct("turns_seen"),
    "happy_flower": _direct("turns_seen"),
    "pendulum": _direct("turns_seen"),
    "pollinous_core": _direct("turns_seen"),
    "pumpkin_candle": _direct("kindle_count"),
    "paels_tooth": _paels_tooth,
    # 4 both-counter-and-flag relics (relic_obs._BOTH): 3 true inversions,
    # 1 direct modulo.
    "silver_crucible": _inverted("times_used", 3),
    "wongos_mystery_ticket": _inverted("combats_finished", 5),
    "toy_box": _direct("combats_seen"),
    "winged_boots": _inverted("times_used", 3),
}


# ─────────────────────────────────────────────────────────────────────────
# Encounter registry
# ─────────────────────────────────────────────────────────────────────────


# Every encounter an EVENT (not a map room) can launch a combat against:
# Combat-layout events' `canonical_encounter` plus the plain `Encounter`
# constants other events assign to `pending_encounter` directly.
# `encounter_registry()` alone only covers the four per-act monster
# packages, so an event-launched fight needs these too or `build_start_state`
# raises `KeyError`. Gathered by hand (not via `ALL_EVENTS`) because an
# event's encounter can live inside arbitrary `_fight`/`_setting_N` code, not
# a common attribute — `Event.canonical_encounter` only covers the three
# Combat-layout events (Punch-Off, The Lantern Key, the unported Architect);
# Dense Vegetation, Fake Merchant and Battleworn Dummy assign
# `pending_encounter` directly instead. `test_encounter_registry_covers_
# every_event_encounter` in test_snapshots.py ties this tuple to every
# `Encounter` instance `sts2_rl.events` exports, so a missed one fails loudly
# instead of surfacing as a silent `KeyError` on a harvested dataset.
_EVENT_ENCOUNTERS: tuple[Encounter, ...] = (
    DENSE_VEGETATION_EVENT_ENCOUNTER,
    PUNCH_OFF_EVENT_ENCOUNTER,
    MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER,
    FAKE_MERCHANT_EVENT_ENCOUNTER,
    BATTLEWORN_DUMMY_SETTING_1,
    BATTLEWORN_DUMMY_SETTING_2,
    BATTLEWORN_DUMMY_SETTING_3,
)


def encounter_registry() -> Mapping[str, Encounter]:
    """Complete `encounter.id -> Encounter` map across every act's monster
    package (overgrowth/act 1, underdocks/act 2, hive/act 3, glory/act 4 —
    `rooms.py`'s `_ACT_ROOMS` ordering), including elites and bosses, PLUS
    every encounter an event can launch (`_EVENT_ENCOUNTERS`, above — fix
    report 2). Keyed by `Encounter.id`, NOT the source packages' own dict
    keys — the two differ for the majority of entries (e.g.
    `overgrowth.ENCOUNTERS`'s `"flyconid"` key holds an `Encounter` whose own
    `.id` is `"flyconid_normal"`), and `.id` is the identity `CombatState`/
    obs code actually reads (`state.encounter.id`), so it is the only key a
    `Snapshot.encounter_id` can be resolved against.
    """
    registry: dict[str, Encounter] = {}
    for pool in (
        _OVERGROWTH_ENCOUNTERS,
        _UNDERDOCKS_ENCOUNTERS,
        _HIVE_ENCOUNTERS,
        _GLORY_ENCOUNTERS,
    ):
        for encounter in pool.values():
            if encounter.id in registry:
                raise ValueError(
                    f"encounter_registry: duplicate encounter id {encounter.id!r}"
                )
            registry[encounter.id] = encounter
    for encounter in _EVENT_ENCOUNTERS:
        if encounter.id in registry:
            raise ValueError(
                f"encounter_registry: duplicate encounter id {encounter.id!r}"
            )
        registry[encounter.id] = encounter
    return registry


# ─────────────────────────────────────────────────────────────────────────
# Snapshot <-> RunState
# ─────────────────────────────────────────────────────────────────────────


#: encounter.id -> act module name ("overgrowth"/"underdocks"/"hive"/
#: "glory"). Event-launched encounters map to None — they belong to no act
#: package and cannot be drilled (the drill setup needs the module to force
#: the act's RoomSet). Needed because act 1 is a per-run coin flip between
#: Overgrowth and Underdocks: an act-0 snapshot's encounter pins which one
#: the source run rolled, and a drill reset must restore THAT module or the
#: encounter isn't in the act's registry at all.
_ACT_MODULE_BY_ENCOUNTER: dict[str, str] = {}
for _name, _pool in (
    ("overgrowth", _OVERGROWTH_ENCOUNTERS),
    ("underdocks", _UNDERDOCKS_ENCOUNTERS),
    ("hive", _HIVE_ENCOUNTERS),
    ("glory", _GLORY_ENCOUNTERS),
):
    for _enc in _pool.values():
        _ACT_MODULE_BY_ENCOUNTER[_enc.id] = _name


def act_module_for_encounter(encounter_id: str) -> "str | None":
    """The act package an encounter belongs to, or None for event-launched
    encounters (not drillable — no act RoomSet contains them)."""
    return _ACT_MODULE_BY_ENCOUNTER.get(encounter_id)


def snapshot_from_run(
    run: "RunState", encounter: Encounter, room_type: str,
) -> Snapshot:
    """Reads the start-state facts off a live `RunState` right before
    (or, for the harvest hook, right after `create_combat` has just attached
    them — see the module docstring) a combat begins.

    `room_type` is the driver's own room type for the combat being entered
    (`RoomType.name`, e.g. "BOSS") — schema 2 records it as a first-class
    fact because it cannot be derived from the encounter id.

    `provenance["seed"]` is `run.string_seed` (the only seed value a
    `RunState` retains — legacy runs driven by a bare, non-string-seeded
    `random.Random` carry no recoverable numeric seed on the run itself, so
    this is `None` for them). `episode_decisions` cannot be derived from a
    `RunState` at all (it isn't a run-level counter) — it defaults to `0`
    here and the harvester is expected to overwrite it before writing, since
    `Snapshot.provenance` is a plain (non-frozen) dict even though the
    dataclass itself is frozen. `provenance["ascension"]` is the run's own
    ascension (hygiene: know what a bank was harvested at; never restored —
    the drilling env's own `--ascension` rules).
    """
    deck = tuple(CardSnap.from_card(c) for c in run.deck)
    relics = tuple(RelicSnap.from_relic(r) for r in run.relics)
    potion_slots = tuple(p.id if p is not None else None for p in run.potions)
    return Snapshot(
        deck=deck,
        relics=relics,
        hp=run.hp,
        max_hp=run.max_hp,
        potion_slots=potion_slots,
        act=run.act_index,
        encounter_id=encounter.id,
        gold=run.gold,
        floor=run.total_floor,
        room_type=room_type,
        provenance={
            "seed": run.string_seed,
            "ascension": getattr(run, "ascension", 0),
            "episode_decisions": 0,
        },
    )


def build_start_state(snap: Snapshot) -> dict:
    """Rebuilds fresh engine objects from a `Snapshot` — kwargs for
    `CombatState`/`STS2FullCombatEnv`'s `deck_cards`/`relics`/`max_hp`/
    `current_hp`/`potion_slots` arguments. Raises `KeyError` naming the id
    if `snap.encounter_id` is not in `encounter_registry()`.
    """
    registry = encounter_registry()
    if snap.encounter_id not in registry:
        raise KeyError(
            f"build_start_state: unknown encounter id {snap.encounter_id!r}"
        )
    return {
        "deck_cards": [c.rebuild() for c in snap.deck],
        "relics": [r.rebuild() for r in snap.relics],
        "max_hp": snap.max_hp,
        "current_hp": snap.hp,
        "potion_slots": list(snap.potion_slots),
        "encounter": registry[snap.encounter_id],
    }


# ─────────────────────────────────────────────────────────────────────────
# JSON round trip
# ─────────────────────────────────────────────────────────────────────────


def _snapshot_to_json(snap: Snapshot) -> dict:
    return {
        "deck": [
            {
                "id": c.id,
                "upgraded": c.upgraded,
                "enchantment": c.enchantment,
                "affliction": c.affliction,
                "affliction_amount": c.affliction_amount,
            }
            for c in snap.deck
        ],
        "relics": [{"id": r.id, "counter": r.counter} for r in snap.relics],
        "hp": snap.hp,
        "max_hp": snap.max_hp,
        "potion_slots": list(snap.potion_slots),
        "act": snap.act,
        "encounter_id": snap.encounter_id,
        "gold": snap.gold,
        "floor": snap.floor,
        "room_type": snap.room_type,
        "provenance": dict(snap.provenance),
    }


def _snapshot_from_json(obj: dict) -> Snapshot:
    return Snapshot(
        deck=tuple(
            CardSnap(
                id=c["id"],
                upgraded=c["upgraded"],
                enchantment=c["enchantment"],
                affliction=c["affliction"],
                affliction_amount=c.get("affliction_amount"),
            )
            for c in obj["deck"]
        ),
        relics=tuple(RelicSnap(id=r["id"], counter=r["counter"]) for r in obj["relics"]),
        hp=obj["hp"],
        max_hp=obj["max_hp"],
        potion_slots=tuple(obj["potion_slots"]),
        act=obj["act"],
        encounter_id=obj["encounter_id"],
        # Schema-2 required fields — a KeyError here means a hand-edited or
        # foreign file that lied about its schema header; loud beats a
        # silently zero-gold drill state.
        gold=obj["gold"],
        floor=obj["floor"],
        room_type=obj["room_type"],
        provenance=dict(obj.get("provenance", {})),
    )


def save_snapshots(path, snapshots: Iterable[Snapshot]) -> None:
    """Writes JSON Lines: a file-level header `{"snapshot_schema": 1}` first,
    then one snapshot per line."""
    path = Path(path)
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"snapshot_schema": SNAPSHOT_SCHEMA}))
        f.write("\n")
        for snap in snapshots:
            f.write(json.dumps(_snapshot_to_json(snap)))
            f.write("\n")


class SnapshotDataset:
    """Sequence-like wrapper over an in-memory list of `Snapshot`s."""

    def __init__(self, snapshots: list[Snapshot]) -> None:
        self._snapshots = snapshots

    def __len__(self) -> int:
        return len(self._snapshots)

    def __getitem__(self, i: int) -> Snapshot:
        return self._snapshots[i]

    def sample(self, rng: random.Random) -> Snapshot:
        if not self._snapshots:
            raise ValueError("SnapshotDataset.sample: dataset is empty")
        return rng.choice(self._snapshots)


def load_snapshots(path) -> SnapshotDataset:
    """Loads a JSONL dataset written by `save_snapshots`. Loud on a missing
    or mismatched `snapshot_schema` header — never silently reinterprets an
    old/foreign format."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        lines = [line for line in f.read().splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"load_snapshots: {path} is empty (missing header line)")
    header = json.loads(lines[0])
    if "snapshot_schema" not in header:
        raise ValueError(
            f"load_snapshots: {path}'s first line is not a snapshot_schema header: {header!r}"
        )
    if header["snapshot_schema"] != SNAPSHOT_SCHEMA:
        raise ValueError(
            f"load_snapshots: {path} has snapshot_schema {header['snapshot_schema']!r}, "
            f"expected {SNAPSHOT_SCHEMA!r}"
        )
    snapshots = [_snapshot_from_json(json.loads(line)) for line in lines[1:]]
    return SnapshotDataset(snapshots)
