"""Completeness harness for the source-to-sim audit pipeline.

Design: audit/README.md.
Deliberately dumb — enumeration, hashing, and record validation only; it
never judges faithfulness. Agents write the audit records; this tool makes
sure they cannot skip a unit, skip a hook, or leave a verdict vague.

Usage:
  py audit/tools/harness.py roster [KIND]       # work queue + unmatched units
  py audit/tools/harness.py skeleton UNIT       # write record skeleton
  py audit/tools/harness.py validate [PATH...]  # validate records
  py audit/tools/harness.py rehash UNIT|PATH... # re-pin hashes (NOT a re-audit)
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import importlib
import inspect
import json
import os
import pkgutil
import re
import sys
from pathlib import Path

# audit/tools/harness.py -> parents[0]=audit/tools, [1]=audit, [2]=repo root.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

DEFAULT_GAME_ROOT = Path(
    os.environ.get("STS2_GAME_SRC", r"c:\Users\Perry\Desktop\Slay the Spire 2")
)
DEFAULT_AUDITS_DIR = _REPO / "audit" / "records"
NAME_OVERRIDES_PATH = Path(__file__).with_name("name_overrides.json")

# Audit verdicts in rollup precedence order (low -> high).
VERDICTS = ("faithful", "waiver", "deliberate-divergence", "gap")

# `extra_sources[i].side` — which root the entry's path resolves against.
# Content records cite files from BOTH trees (a power record routinely rests on
# PowerCmd.cs and on cmds.py), and unlike the singular game_source/sim_source
# pair the extra list is unordered and mixed, so each entry names its own root.
SOURCE_SIDES = ("game", "sim")

GAME_MODEL_DIRS = {
    "relic": "src/Core/Models/Relics",
    "power": "src/Core/Models/Powers",
    "card": "src/Core/Models/Cards",
    "monster": "src/Core/Models/Monsters",
    "event": "src/Core/Models/Events",
    "enchantment": "src/Core/Models/Enchantments",
    # `potion` added 2026-07-26 on Perry's instruction ("don't ignore potions
    # anymore"), replacing the shared contract's blanket potion exclusion. The
    # exclusion had become load-bearing in the wrong direction: 10 entries
    # across the card and power tiers waived real behaviour on it, while the
    # relic tier filed 45 potion-mechanic gaps. Making it a KIND is what turns
    # "out of scope" into "unaudited", which is a fact the tools can report.
    "potion": "src/Core/Models/Potions",
    # Three "systems tier" kinds added 2026-08-03 (wiring only, no records
    # yet). `encounter` and `affliction` are the game's own content dirs;
    # `character` gets one too even though only Ironclad is in scope
    # (see `_sim_units`'s comment).
    "encounter": "src/Core/Models/Encounters",
    "affliction": "src/Core/Models/Afflictions",
    "character": "src/Core/Models/Characters",
}

# `public override <type> <Name>(  |  => ...  |  { ...` — one-regex scan of
# the decompiled output, which is uniform. Captures the member name whether
# it is a method or an expression-bodied property. The type character class
# includes `()` so a parenthesised tuple return — `Task<(PileType, int)>`,
# `(decimal, bool)` — is matched; without it those hooks were silently
# skipped, and the enumeration cannot be trusted if it can miss a member.
# The quantifier is non-greedy, so `void Foo(` still parses as type `void`.
#
# OPEN DEFECT, not fixed here (2026-08-03, P1-T4): this same blind spot exists
# for `protected override` — and it is not rare. Measured with
# `grep -l "protected override" <dir>/*.cs | wc -l` against each model dir's
# TOTAL .cs file count (non-recursive, same population `unported()` globs):
#   Relics 246/298, Powers 143/260, Cards 564/578, Monsters 117/121,
#   Events 68/68, Enchantments 9/23, Potions 63/64 files. `validate` currently
#   passes hundreds of finished records for these seven kinds against an
#   enumeration that cannot see every `protected override` member they
#   declare — those records are not wrong on the strength of anything found
#   here, but they have not been checked against the fuller enumeration
#   either. Widening this regex globally would retroactively flag all of them
#   as incomplete in one step, which is a decision for whoever runs that
#   campaign, not a side effect of fixing the three new "systems tier" kinds
#   below. See PROTECTED_OVERRIDE_KINDS for the narrow fix that IS made here.
_OVERRIDE_RE = re.compile(
    r"^\s*public\s+override\s+(?:sealed\s+)?(?:async\s+)?"
    r"[\w<>,.?\[\]() ]+?\s(\w+)\s*(?:\(|=>|\{|$)",
    re.M,
)

# Same scan, but for `protected override` — identical shape otherwise, so any
# fix to the type character class or the quantifier above must be mirrored
# here (or the two would silently drift apart on the exact same class of bug
# this pair exists to catch).
_PROTECTED_OVERRIDE_RE = re.compile(
    r"^\s*protected\s+override\s+(?:sealed\s+)?(?:async\s+)?"
    r"[\w<>,.?\[\]() ]+?\s(\w+)\s*(?:\(|=>|\{|$)",
    re.M,
)

# Kinds whose GAME-side subject is declared `protected override`, not
# `public override` — added 2026-08-03 for the three "systems tier" kinds
# (encounter/affliction/character). The motivating case: EVERY one of the 88
# `src/Core/Models/Encounters/*.cs` files declares
#   protected override IReadOnlyList<(MonsterModel, string?)> GenerateMonsters()
# and that method — the monster roster, slot assignment, RNG draw count/
# stream, ordering — is the entire subject of the encounter audit. Before this
# constant existed, `_declared_overrides` only matched `public override`, so
# `GenerateMonsters` was invisible to `skeleton`/`validate` and an encounter
# record could be pronounced complete having verdicted nothing about it.
#
# Scoped to exactly these three kinds, not widened for everyone, because the
# seven pre-existing kinds (`card`, `relic`, `power`, `monster`, `event`,
# `potion`, `enchantment`) have hundreds of `protected override` members of
# their own (see the finding logged on `_OVERRIDE_RE` above) and every one of
# those kinds already has finished, `validate`-passing records written
# against the narrower enumeration. Widening for them here would silently
# invalidate that work as a side effect of an unrelated task instead of as a
# deliberate, reviewed decision — exactly the failure mode
# `MODEL_ROOT_CLASSES`'s own block comment already warns about ("a promise one
# root did not keep"). A named, scoped constant — checked at the one place
# enumeration happens — means widening it later for another kind is a
# one-line change with an explicit reason, not a boolean threaded through
# every call site that touches enumeration.
PROTECTED_OVERRIDE_KINDS = frozenset({"encounter", "affliction", "character"})

# `public sealed class Foo : Bar, IBaz` -> ("Foo", "Bar, IBaz").
_CLASS_DECL_RE = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*)*"
    r"(?:public|internal|private|protected)?\s*"
    r"(?:abstract\s+|sealed\s+|static\s+|partial\s+|unsafe\s+)*"
    r"(?:class|record)\s+(\w+)\s*(?:<[^>]*>)?\s*:\s*([^\{\r\n]+)",
    re.M,
)

# Base classes whose members are the *framework*, not the unit. Every power
# derives from PowerModel, so enumerating PowerModel's own overrides into all
# 138 power records would add the same noise 138 times — and that layer is
# audited, once, by the seam tier (hook_dispatch hashes AbstractModel.cs and
# the model files). Base-class following stops here.
#
# THIS WAS A PROMISE ONE ROOT DID NOT KEEP. Until 2026-08-03 there was no
# potion seam, so stopping at PotionModel meant PotionModel.OnUseWrapper — the
# whole use path for all 51 potions — was verdicted nowhere, and `validate`
# could not notice because a root is exactly what it is told to stop at. That
# hole is WIRED SHUT (not yet audited) by SEAM_SOURCES["potion_pipeline"]
# (PotionCmd.cs + PotionModel.cs, see audit/seams/potion_pipeline.md). The 51
# potion records' own `shared-mechanisms.md` guard citation is unchanged —
# that doc is still the per-unit pointer to the shared mechanism — but now a
# seam record actually exists to carry that mechanism's own verdict once
# audited, instead of the hole being merely documented. Before adding a root
# here, check which seam covers it — same rule, now with an example that
# actually got closed instead of just documented.
MODEL_ROOT_CLASSES = frozenset({
    "AbstractModel", "AfflictionModel", "BadgeModel", "CardModel",
    "CreatureModel", "EnchantmentModel", "EventModel", "ModifierModel",
    "MonsterModel", "OrbModel", "PotionModel", "PowerModel", "RelicModel",
})

# EncounterModel and CharacterModel are DELIBERATELY NOT roots here, checked
# (not assumed) as part of widening enumeration to `protected override` for
# their kinds (2026-08-03, P1-T4). Both are the immediate base of every unit
# in their kind (every Encounters/*.cs : EncounterModel, every rostered
# Characters/*.cs : CharacterModel), so if either declared a `protected
# override` member, widening the regex would newly pull it in as "inherited"
# — a real behaviour change worth a decision, per the task brief. Read
# directly: neither file declares ANY `protected override` member (both have
# exactly one relevant override at all, `public override bool
# ShouldReceiveCombatHooks => false`, already surfaced today as an inherited
# hook — e.g. encounter/flyconid's fourth hook). So promoting them to roots
# would suppress that existing, legitimate hook for no compensating benefit;
# leaving them off costs nothing, because there is no protected member to
# leak in. AfflictionModel (already a root, above) is a different case: it
# DOES declare `protected override void AfterCloned()`, but root membership
# already stops `split_overrides` before it reaches AfflictionModel.cs at
# all, so the widened regex cannot surface it either way — root status, not
# regex width, is what's controlling there.


def _declared_overrides(cs_text: str, kind: str | None = None) -> list[str]:
    """Names of every `public override` member declared in this text, in
    source order. When `kind` is one of PROTECTED_OVERRIDE_KINDS, also
    includes `protected override` members (see that constant's comment) —
    merged by position, not by pattern, so a file mixing both visibilities
    still enumerates in the order they're actually declared."""
    matches = [(m.start(), m.group(1)) for m in _OVERRIDE_RE.finditer(cs_text)]
    if kind in PROTECTED_OVERRIDE_KINDS:
        matches += [(m.start(), m.group(1))
                    for m in _PROTECTED_OVERRIDE_RE.finditer(cs_text)]
    matches.sort(key=lambda t: t[0])
    return list(dict.fromkeys(name for _, name in matches))


def _base_class_name(cs_text: str) -> str | None:
    """The immediate base CLASS of the first type declared in `cs_text`.

    C# puts the base class first in the base list, so only the first entry can
    be one. Returns None when the type has no base class (interfaces only) or
    when the base is a framework root."""
    m = _CLASS_DECL_RE.search(cs_text)
    if not m:
        return None
    first = m.group(2).split(",")[0]
    name = re.sub(r"<.*", "", first).strip()
    if not name or name in MODEL_ROOT_CLASSES:
        return None
    if len(name) > 1 and name[0] == "I" and name[1].isupper():
        return None  # interface, so the type has no base class at all
    return name


@functools.lru_cache(maxsize=8)
def _cs_index(game_root: str) -> dict[str, tuple[str, ...]]:
    """stem -> every .cs file with that stem, under the game root."""
    idx: dict[str, list[str]] = {}
    for p in Path(game_root).rglob("*.cs"):
        idx.setdefault(p.stem, []).append(str(p))
    return {k: tuple(v) for k, v in idx.items()}


def find_class_file(name: str, game_root: Path | None = None) -> Path | None:
    """Locate the .cs file declaring `name`. The base of a one-line subclass
    routinely lives in a different file (and a different directory), so this
    searches the whole game tree rather than the unit's own model dir."""
    root = game_root or DEFAULT_GAME_ROOT
    decl = re.compile(rf"\b(?:class|record)\s+{re.escape(name)}\b")
    for cand in _cs_index(str(root)).get(name, ()):
        p = Path(cand)
        if decl.search(p.read_text(encoding="utf-8-sig", errors="replace")):
            return p
    return None


def split_overrides(cs_text: str, game_root: Path | None = None,
                    source_path: Path | None = None,
                    kind: str | None = None) -> tuple[list[str], list[str]]:
    """(declared here, inherited from the immediate base), in declaration order.

    A `.cs` file that declares only `OriginModel` while its base declares the
    real behaviour used to enumerate as one hook, so `validate` confirmed a
    verdict for that one and never noticed the other seven. One level of base
    is enough for the shapes this source uses; `game_root` is required to
    resolve it because the base normally lives in another file.

    `kind` is passed straight through to both `_declared_overrides` calls —
    the unit's own file AND its base's — so a PROTECTED_OVERRIDE_KINDS unit
    whose base also declares a `protected override` member would see it as
    inherited too. (As of 2026-08-03 this is moot for all three scoped kinds:
    EncounterModel.cs and CharacterModel.cs declare none, and AfflictionModel
    is already a MODEL_ROOT_CLASSES root so its members — including the one
    `protected override AfterCloned()` it does have — are never reached from
    here regardless. Passing `kind` through anyway is correct on principle and
    costs nothing today.)"""
    declared = _declared_overrides(cs_text, kind)
    if game_root is None:
        return declared, []
    base = _base_class_name(cs_text)
    if not base:
        return declared, []
    bp = find_class_file(base, game_root)
    if bp is None or (source_path and bp.resolve() == Path(source_path).resolve()):
        return declared, []
    inherited = [n for n in _declared_overrides(
        bp.read_text(encoding="utf-8-sig", errors="replace"), kind)
        if n not in declared]
    return declared, inherited


def list_overrides(cs_text: str, game_root: Path | None = None,
                   source_path: Path | None = None,
                   kind: str | None = None) -> list[str]:
    """Every `public override` member the unit really has, in declaration
    order: the ones it declares, then the ones it inherits from its immediate
    base. Pass `game_root` to get the inherited half. Pass `kind` to widen the
    enumeration to `protected override` for PROTECTED_OVERRIDE_KINDS."""
    declared, inherited = split_overrides(cs_text, game_root, source_path, kind)
    return declared + inherited


def hook_key(key: str) -> str:
    """A record's hook key, reduced to the member name it starts with.

    Records annotate keys with provenance — `"Type (inherited,
    TemporaryStrengthPower.cs:32-42)"` — so enumeration is matched against the
    leading identifier rather than the whole string."""
    m = re.match(r"\s*([A-Za-z_]\w*)", key or "")
    return m.group(1) if m else (key or "").strip()


def file_sha256(path: Path) -> str:
    """sha256 of the file's text with line endings normalized to LF."""
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def source_base(side: str, game_root: Path | None = None) -> Path:
    """Root an `extra_sources` entry's path resolves against."""
    return (game_root or DEFAULT_GAME_ROOT) if side == "game" else _REPO


def _pascal(unit_id: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in unit_id.split("_"))


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _load_name_overrides() -> dict[str, str]:
    return json.loads(NAME_OVERRIDES_PATH.read_text(encoding="utf-8"))


def _sim_units(kind: str) -> dict[str, type]:
    """unit_id -> sim class, from the sim's own registries."""
    if kind == "relic":
        from sts2_rl.relics import ALL_RELICS
        return dict(ALL_RELICS)
    if kind == "power":
        from sts2_rl.powers import ALL_POWERS
        return dict(ALL_POWERS)
    if kind == "card":
        import sts2_rl.cards  # noqa: F401 — triggers registration imports
        from sts2_rl.cards.base import _CARD_CLASSES
        return dict(_CARD_CLASSES)
    if kind == "event":
        from sts2_rl.events import ALL_EVENTS
        return dict(ALL_EVENTS)
    if kind == "enchantment":
        from sts2_rl.enchantments import ALL_ENCHANTMENTS
        return dict(ALL_ENCHANTMENTS)
    if kind == "potion":
        from sts2_rl.potions import ALL_POTIONS
        return dict(ALL_POTIONS)
    if kind == "monster":
        return _monster_units()
    if kind == "affliction":
        from sts2_rl.afflictions import ALL_AFFLICTIONS
        return dict(ALL_AFFLICTIONS)
    if kind == "character":
        # Ironclad-relevant scope. `CHARACTERS` holds all FIVE playable
        # characters — Ironclad plus four source-verified-but-unported rows
        # (characters.py's module docstring); `DeprecatedCharacter` and
        # `RandomCharacter` are framework plumbing the sim never registers as
        # a playable character at all, so they are not content and do not
        # belong here regardless of scope. Porting Silent/Regent/Necrobinder/
        # Defect is a separate campaign, not this audit's job, but `roster`
        # reports what the sim REGISTERS, not what is content-complete — so
        # all five appear, which is deliberately fine (see the prompt brief).
        # Every one of the five is built by a function in this single file
        # (`_ironclad`/`_unported`, both called from `_build_registry`), so
        # the shared `Character` dataclass stands in for `cls`: unlike an
        # instance (which `inspect.getsourcefile` cannot resolve — no
        # `__module__` on a plain value), the class correctly resolves to
        # `characters.py` for every one of the five, because that really is
        # where every one of them is defined.
        from sts2_rl.characters import CHARACTERS, Character
        return {cid: Character for cid in CHARACTERS}
    if kind == "encounter":
        return _encounter_units()
    raise ValueError(f"unknown kind: {kind}")


def _monster_units() -> dict[str, type]:
    """Walk the four act packages and collect Monster subclasses by module."""
    from sts2_rl.monsters.base import Monster

    units: dict[str, type] = {}
    for act in ("overgrowth", "underdocks", "hive", "glory"):
        pkg = importlib.import_module(f"sts2_rl.monsters.{act}")
        for info in pkgutil.iter_modules(pkg.__path__):
            mod = importlib.import_module(f"sts2_rl.monsters.{act}.{info.name}")
            for _, cls in inspect.getmembers(mod, inspect.isclass):
                if (
                    issubclass(cls, Monster)
                    and cls is not Monster
                    and cls.__module__ == mod.__name__
                ):
                    units[_snake(cls.__name__)] = cls
    return units


def _encounter_units() -> dict[str, object]:
    """unit_id -> the per-monster submodule that builds the instance.

    The four acts' `ENCOUNTERS: dict[str, Encounter]` registries hold
    dataclass INSTANCES, not classes — every encounter shares the one
    `Encounter` class (`monsters/base.py`), so `inspect.getsourcefile
    (type(instance))` would point every single encounter at base.py instead
    of the file that actually builds it (an `Encounter(...)` call in a
    per-monster module, e.g. `BYGONE_EFFIGY_ELITE` in `bygone_effigy.py`).
    `roster()` only needs *something* `inspect.getsourcefile` accepts, and it
    accepts a module just as well as a class, so this walks each act's
    submodules — the same way `_monster_units` does — and hands back the
    submodule that actually holds the matching instance, matched by IDENTITY
    rather than name (a submodule routinely builds more than one encounter,
    e.g. `slimes.py`'s `SLIMES_NORMAL` and `SLIMES_WEAK`, and both must
    resolve to `slimes.py`).

    Also verifies the four acts' dicts share no key: `roster` would silently
    let one shadow the other in a merged namespace, and that would hide a
    real content collision rather than surface it.

    The four `ENCOUNTERS` dicts are not the whole story. Six game files build
    an `EncounterModel` that the room system never reaches through the normal
    per-act monster rotation — instead an *event* hands the built encounter
    straight to combat (`Event.pending_encounter` / `Event.canonical_encounter`,
    see `events/base.py`'s docstring), and the sim mirrors that with a
    module-level `Encounter(...)` instance that sits outside all four dicts.
    Confirmed by grepping every module-level `Encounter(` construction under
    `sts2_rl/` (2026-08-03): the 80 ENCOUNTERS-dict entries are every encounter
    reachable from `rooms.py`'s ordinary spawn path, and exactly five more are
    real, consumed, ported content:
      - `DenseVegetationEventEncounter.cs` -> `events/dense_vegetation.py`
      - `PunchOffEventEncounter.cs`        -> `events/punch_off.py`
      - `MysteriousKnightEventEncounter.cs`-> `monsters/hive/flail_knight.py`
        (built there, not in `events/the_lantern_key.py` — that module only
        imports the constant; matches how the four acts' encounters live in a
        per-monster submodule rather than in the act's own `__init__.py`)
      - `FakeMerchantEventEncounter.cs`    -> `monsters/fake_merchant.py`
      - `BattlewornDummyEventEncounter.cs` -> `monsters/glory/battle_friend.py`
    A SIXTH file matching the same "*EventEncounter.cs" naming pattern,
    `TheArchitectEventEncounter.cs`, is NOT one of these, despite an earlier
    pass over this campaign guessing otherwise: `events/base.py`'s
    `is_combat_layout` comment and `run.py`'s `complete_run` docstring both
    say outright that The Architect's victory event is unported (no sim
    `Encounter` instance exists for it anywhere), so its `.cs` file correctly
    surfaces as unported below, same as `DeprecatedEncounter.cs` (literally
    deprecated, not content) and `TunnelerNormal.cs` (the sim only ports the
    Weak variant, `TunnelerWeak.cs`).
    Two more near-duplicates this grep turned up are dead code, not gaps, and
    are deliberately NOT rostered: top-level `sts2_rl/monsters/nibbit.py`
    (`NIBBITS_NORMAL`/`NIBBITS_WEAK`) and `sts2_rl/monsters/
    fuzzy_wurm_crawler.py` (`FUZZY_WURM_ENCOUNTER`) are pre-`overgrowth/`-
    package leftovers, fully superseded by their same-named counterparts in
    `monsters/overgrowth/`, and imported by nothing — not `monsters/__init__.py`
    (which imports the `overgrowth/` package's versions under the same names),
    not any event, not any test. A unit with no import path is not "ported
    content that never passes through an ENCOUNTERS dict" — it is unreachable,
    so it stays out of the roster the same way `sim_only` skeletons stay out
    of `unported()`'s C#-side count.

    `BattlewornDummyEventEncounter.cs` is ONE class whose ONE `GenerateMonsters`
    switch picks among three monster models by a `Setting` enum; the sim
    mirrors the three arms as three separate constants
    (`BATTLEWORN_DUMMY_SETTING_1/2/3`), but every `public override` hook on the
    class (`RoomType`, `ShouldGiveRewards`, `AllPossibleMonsters`,
    `SaveCustomState`/`LoadCustomState`) is shared code with nothing to tell
    apart per setting. Auditing it as three units would cite the same hooks in
    three records with nothing keeping their verdicts in sync — the exact
    cross-record-disagreement failure mode this campaign already treats as a
    defect elsewhere — for zero benefit, since there is no per-setting
    behaviour to disagree about in the first place. So it is ONE unit, same as
    every other `.cs` file, not three.

    Unit ids reuse each encounter's own `Encounter.id` field where one exists
    (already a stable identity used elsewhere, e.g. `snapshots.py`'s
    `_EVENT_ENCOUNTERS` tuple) rather than inventing new ones. Battleworn Dummy
    has three ids and no single one can stand for the whole class, so it is
    named after its own `.cs` file instead, in the same "<name>_event" shape
    the real ids already use. None of the five collides with an
    ENCOUNTERS-dict key (checked below, not just assumed) or with each other.
    """
    from sts2_rl.monsters.base import Encounter

    units: dict[str, object] = {}
    owning_act: dict[str, str] = {}
    for act in ("overgrowth", "underdocks", "hive", "glory"):
        pkg = importlib.import_module(f"sts2_rl.monsters.{act}")
        instance_module: dict[int, object] = {}
        for info in pkgutil.iter_modules(pkg.__path__):
            mod = importlib.import_module(f"sts2_rl.monsters.{act}.{info.name}")
            for val in vars(mod).values():
                if isinstance(val, Encounter):
                    instance_module.setdefault(id(val), mod)
        for unit_id, enc in pkg.ENCOUNTERS.items():
            if unit_id in units:
                raise ValueError(
                    f"encounter id {unit_id!r} is defined in both "
                    f"{owning_act[unit_id]}.ENCOUNTERS and {act}.ENCOUNTERS")
            owning_act[unit_id] = act
            # Fallback to the act package itself on the (currently unused)
            # chance an encounter is built directly in the act's __init__.py
            # rather than a per-monster submodule.
            units[unit_id] = instance_module.get(id(enc), pkg)

    from sts2_rl.events import dense_vegetation, punch_off
    from sts2_rl.monsters import fake_merchant
    from sts2_rl.monsters.glory import battle_friend
    from sts2_rl.monsters.hive import flail_knight

    extra_units = {
        "dense_vegetation_event": dense_vegetation,
        "punch_off_event": punch_off,
        "mysterious_knight_event": flail_knight,
        "fake_merchant_event": fake_merchant,
        "battleworn_dummy_event": battle_friend,
    }
    for unit_id, mod in extra_units.items():
        if unit_id in units:
            raise ValueError(
                f"encounter id {unit_id!r} collides with an "
                f"ENCOUNTERS-dict key from {owning_act.get(unit_id)!r}")
        units[unit_id] = mod
    return units


def _game_path(kind: str, unit_id: str, game_root: Path,
               overrides: dict[str, str]) -> Path:
    key = f"{kind}/{unit_id}"
    if key in overrides:
        return game_root / overrides[key]
    suffix = "Power" if kind == "power" else ""
    return game_root / GAME_MODEL_DIRS[kind] / f"{_pascal(unit_id)}{suffix}.cs"


def roster(kind: str, game_root: Path | None = None) -> list[dict]:
    """The audit work queue for one kind (see module docstring)."""
    root = game_root or DEFAULT_GAME_ROOT
    overrides = _load_name_overrides()
    rows = []
    for unit_id, cls in sorted(_sim_units(kind).items()):
        gp = _game_path(kind, unit_id, root, overrides)
        sim_file = inspect.getsourcefile(cls)
        rows.append({
            "unit": f"{kind}/{unit_id}",
            "sim_path": str(Path(sim_file).resolve().relative_to(_REPO)),
            "game_path": str(gp.relative_to(root)),
            "game_exists": gp.is_file(),
        })
    return rows


def unported(kind: str, game_root: Path | None = None) -> list[str]:
    """C# model files in this kind's directory matched by no sim unit.

    Informational: many are out of Ironclad scope, not gaps."""
    root = game_root or DEFAULT_GAME_ROOT
    matched = {
        Path(r["game_path"]).name
        for r in roster(kind, root)
        if r["game_exists"]
    }
    model_dir = root / GAME_MODEL_DIRS[kind]
    return sorted(
        p.name for p in model_dir.glob("*.cs") if p.name not in matched
    )


# ── Seams (Tier 2) ────────────────────────────────────────────────────────
# Engine seams audited as ordering specs, not per-hook records. Paths are
# repo-relative (game side under the game root). If a listed C# file does
# not exist, locate the real one with a grep and fix this table.
SEAM_SOURCES: dict[str, tuple[list[str], list[str]]] = {
    "damage_pipeline": (
        # DamageCmd.cs itself is just two AttackCommand-builder factory
        # methods; the actual per-hit pipeline (block/modifier/kill order)
        # lives in CreatureCmd.Damage, dispatched through the Hook static
        # methods it calls (ModifyDamage, ModifyHpLost, ShouldDie, ...).
        ["src/Core/Commands/DamageCmd.cs", "src/Core/Commands/CreatureCmd.cs",
         "src/Core/Hooks/Hook.cs"],
        ["sts2_rl/cmds.py", "sts2_rl/valueprops.py"],
    ),
    "power_cmd": (
        # PowerCmd.cs itself is the orchestration (Apply/ModifyAmount/Remove/
        # FindExistingInstanceForStacking), but the sign-aware power typing
        # (GetTypeForAmount), stacking-removal, and 0-amount-is-a-no-op rules
        # it depends on live in PowerModel.cs, and the additive/multiplicative/
        # predicate dispatch mechanics (ModifyPowerAmountGiven/Received,
        # Before/AfterPowerAmountChanged, AfterModifyingPowerAmountGiven/
        # Received) live in Hook.cs's static dispatcher methods.
        ["src/Core/Commands/PowerCmd.cs", "src/Core/Hooks/Hook.cs",
         "src/Core/Models/PowerModel.cs"],
        ["sts2_rl/cmds.py", "sts2_rl/hooks.py", "sts2_rl/powers.py"],
    ),
    "creature_card_cmds": (
        # The four Cmd files are the orchestration, but three of the seam's
        # behaviours live outside them: the sim's `CardSelectCmd` class has no
        # counterpart other than CardSelectCmd.cs (auto-select-when-few,
        # draw-pile ordering); every CardPileCmd pile mutation delegates to
        # CardPile.AddInternal/RemoveInternal/RandomizeOrderInternal (index
        # semantics, MaxCardsInHand); and the shuffle semantics the seed facts
        # rest on (StableShuffle = sort-then-Fisher-Yates, UnstableShuffle)
        # live in ListExtensions. Sim side: cmds.py holds only part of the
        # counterpart — the pile verbs are on PlayerCombatState (player.py),
        # the deck/gold verbs on RunState (run.py), and CardCmd.AutoPlay maps
        # to CombatState.auto_play_card (combat.py). See the scope-boundary
        # section of audit/seams/creature_card_cmds.md for the
        # method-level split against turn_structure and hook_dispatch.
        # Three more files were added in the Task 7 fix pass because the record
        # cites them as primary evidence and an unpinned source cannot go
        # stale: Creature.cs holds the *Internal mutators every CreatureCmd
        # verb delegates to (GainBlockInternal/LoseBlockInternal/HealInternal/
        # SetCurrentHpInternal/SetMaxHpInternal/StunInternal/
        # RemoveAllPowersInternalExcept — steps 8/16/18/20/25/30 and guards
        # G4/G13); Hook.cs holds the four BLOCK dispatchers this record claims
        # (ModifyBlock at 1310-1340 and AfterModifyingBlockAmount at 649-656
        # are G1's and G2's primary evidence — the other Hook.cs regions belong
        # to damage_pipeline / power_cmd / hook_dispatch, see the doc's
        # scope-boundary section); and hooks.py is where the sim's block
        # modifiers return a bare aggregate with no companion event, which is
        # G2's core evidence. Both prior seams already list Hook.cs.
        # Thirteen more were added in the Task 9 fix pass (clause (c) of step
        # 13, hook_dispatch's gap G9 at the BLOCK site). That clause's verdict
        # is DORMANT, and the dormancy rests entirely on the *literal factors*
        # the block modifiers return: every reachable block multiplier is
        # binary-exact, so the sim's float product equals C#'s sequential
        # decimal fold. That claim goes wrong the moment any of these files
        # grows a non-dyadic factor, so the whole block-modifier population is
        # pinned — the 8 C# ModifyBlockMultiplicative overrides (FrailPower,
        # NoBlockPower, ShadowmeldPower, UnmovablePower, PaelsLegion, Vambrace,
        # VitruvianMinion, MultiplayerScalingModel), the 2 ModifyBlockAdditive
        # ones (DexterityPower, FastenPower — the additive half of the same
        # dispatch, and G1/step 15 already cite them), and the three sim files
        # holding their five ported counterparts (powers.py: Frail x0.75,
        # Unmovable x2, No Block x0; relics/vambrace.py x2 — also G1's and G2's
        # primary sim evidence; relics/paels_legion.py x2).
        ["src/Core/Commands/CreatureCmd.cs", "src/Core/Commands/PlayerCmd.cs",
         "src/Core/Commands/CardCmd.cs", "src/Core/Commands/CardPileCmd.cs",
         "src/Core/Commands/CardSelectCmd.cs",
         "src/Core/Entities/Cards/CardPile.cs",
         "src/Core/Entities/Creatures/Creature.cs",
         "src/Core/Hooks/Hook.cs",
         "src/Core/Extensions/ListExtensions.cs",
         "src/Core/Models/Powers/DexterityPower.cs",
         "src/Core/Models/Powers/FastenPower.cs",
         "src/Core/Models/Powers/FrailPower.cs",
         "src/Core/Models/Powers/NoBlockPower.cs",
         "src/Core/Models/Powers/ShadowmeldPower.cs",
         "src/Core/Models/Powers/UnmovablePower.cs",
         "src/Core/Models/Relics/PaelsLegion.cs",
         "src/Core/Models/Relics/Vambrace.cs",
         "src/Core/Models/Relics/VitruvianMinion.cs",
         "src/Core/Models/Singleton/MultiplayerScalingModel.cs"],
        ["sts2_rl/cmds.py", "sts2_rl/player.py", "sts2_rl/run.py",
         "sts2_rl/combat.py", "sts2_rl/hooks.py", "sts2_rl/powers.py",
         "sts2_rl/relics/vambrace.py", "sts2_rl/relics/paels_legion.py"],
    ),
    "turn_structure": (
        # CombatManager.cs is the turn driver, but PlayerTurnPhase.cs is a bare
        # enum and every other file the ordering spec rests on was missing.
        # Added on the game side (Task 8 Step A):
        #  - CombatState.cs: CurrentSide / RoundNumber / CreaturesOnCurrentSide /
        #    Enemies / IsLiveCombat, the side accessors every StartTurn branch
        #    reads.
        #  - Creature.cs: the per-creature turn verbs CombatManager calls —
        #    BeforeTurnStart (673-679), AfterTurnStart (681-692, the turn-1
        #    block-clear skip), ClearBlock (718-728), OnSideSwitch (694-704),
        #    TakeTurn (706-716), PrepareForNextTurn (546-554), IsPrimaryEnemy
        #    (252-263). Split by method against creature_card_cmds — see the
        #    scope-boundary section of audit/seams/turn_structure.md.
        #  - PlayerCombatState.cs: TurnNumber/IncrementTurnNumber, ResetEnergy /
        #    AddMaxEnergyToCurrent, EndOfTurnCleanup, Phase.
        #  - CardModel.cs: OnTurnEndInHandWrapper (1682-1698) and the per-turn
        #    card reset EndOfTurnCleanup (1610-1623).
        #  - MonsterModel.cs: PerformMove / SpawnedThisTurn / OnSideSwitch /
        #    RollMove — the enemy half of the turn loop (move SELECTION is
        #    Task 10's).
        #  - Hook.cs: the turn dispatchers (BeforeTurnEnd 1238-1261, AfterTurnEnd
        #    1265-1291, BeforeSideTurnStart 1144-1159, AfterSideTurnStart
        #    1163-1175, AfterBlockCleared 119-125, ShouldClearBlock 2193-...).
        #    Claimed by method against damage_pipeline / power_cmd /
        #    creature_card_cmds / hook_dispatch — see the doc's boundary section.
        #  - PowerCmd.cs: TickDownDuration (190-200), the duration-tick verb the
        #    seed fact's V/W/F tick runs through. power_cmd owns the SET site of
        #    SkipNextDurationTick (PowerCmd.cs:146); this record owns the
        #    consume site only.
        #  - WeakPower.cs / VulnerablePower.cs / FrailPower.cs: the three
        #    AfterSideTurnEnd(side == Enemy) callers that make the tick an
        #    enemy-side-end event, which is what the sim's on_enemy_side_end
        #    maps to.
        #  - SturdyClamp.cs / HornCleat.cs / CaptainsWheel.cs / Anchor.cs:
        #    load-bearing witnesses for gap G1 (the unconditional
        #    AfterBlockCleared loop) — a preventer and three listeners.
        #  - PaelsEye.cs / RunicPyramid.cs: the ported ShouldTakeExtraTurn and
        #    ShouldFlush implementations that make gaps G3 and G4 live.
        # Added in the Task 8 fix pass — the content files seven LIVE labels
        # rest on. The rule is: if a verdict's liveness or dormancy argument
        # cites a file with line numbers, that file is part of the audited
        # unit's evidence and MUST be hashed. Editing it is exactly the event
        # staleness detection exists to catch — a Barricade/Cloak Clasp/
        # Orichalcum/Royal Poison/Imbued/Joss Paper/Unceasing Top change can
        # invalidate G1, G2, G4, G8, G12, G13, G14, G16, G17 or G18 without
        # touching CombatManager.cs, and the record must go stale when it does.
        # (The earlier "hashing them would make the record stale on every
        # unrelated relic edit" note had this backwards, and did not explain
        # why the six relics above were hashed and these were not.)
        #  - BarricadePower.cs: G1/G2's ShouldClearBlock preventer.
        #  - CloakClasp.cs: G8's and G12's contender.
        #  - Orichalcum.cs (44-56): G12's two-phase VeryEarly snapshot.
        #  - RoyalPoison.cs (18-25): G13's turn-1 player-damage trigger.
        #  - Enchantments/Imbued.cs (11, 20-26): G14's only
        #    ShouldStartAtBottomOfDrawPile implementer.
        #  - JossPaper.cs (102-124): G4's and G17's causedByEthereal deferral.
        #  - UnceasingTop.cs (25-35): G16's source-comment evidence.
        # Sim side: combat.py + player.py cover under half the seam — hooks.py
        # holds the turn dispatchers (and the missing ones), creatures.py the
        # is_gone/retained_after_death win-condition inputs, monsters/base.py
        # take_turn/telegraph_next_move, powers.py the _tick_duration sites,
        # cards/base.py reset_turn_cost_modifiers, and the relic/card/
        # enchantment modules the live gaps' sim halves (the six original ones
        # plus barricade_card.py, cloak_clasp.py, orichalcum.py,
        # royal_poison.py, joss_paper.py, electric_shrymp.py, unceasing_top.py,
        # whispering_earring.py, apparition.py and enchantments.py, added in
        # the fix pass for the same reason).
        ["src/Core/Combat/CombatManager.cs", "src/Core/Combat/PlayerTurnPhase.cs",
         "src/Core/Combat/CombatState.cs",
         "src/Core/Entities/Creatures/Creature.cs",
         "src/Core/Entities/Players/PlayerCombatState.cs",
         "src/Core/Models/CardModel.cs", "src/Core/Models/MonsterModel.cs",
         "src/Core/Hooks/Hook.cs", "src/Core/Commands/PowerCmd.cs",
         "src/Core/Models/Powers/WeakPower.cs",
         "src/Core/Models/Powers/VulnerablePower.cs",
         "src/Core/Models/Powers/FrailPower.cs",
         "src/Core/Models/Relics/SturdyClamp.cs",
         "src/Core/Models/Relics/HornCleat.cs",
         "src/Core/Models/Relics/CaptainsWheel.cs",
         "src/Core/Models/Relics/Anchor.cs",
         "src/Core/Models/Relics/PaelsEye.cs",
         "src/Core/Models/Relics/RunicPyramid.cs",
         "src/Core/Models/Powers/BarricadePower.cs",
         "src/Core/Models/Relics/CloakClasp.cs",
         "src/Core/Models/Relics/Orichalcum.cs",
         "src/Core/Models/Relics/RoyalPoison.cs",
         "src/Core/Models/Relics/JossPaper.cs",
         "src/Core/Models/Relics/UnceasingTop.cs",
         "src/Core/Models/Enchantments/Imbued.cs"],
        ["sts2_rl/combat.py", "sts2_rl/player.py", "sts2_rl/hooks.py",
         "sts2_rl/creatures.py", "sts2_rl/monsters/base.py",
         "sts2_rl/powers.py", "sts2_rl/cards/base.py",
         "sts2_rl/relics/sturdy_clamp.py", "sts2_rl/relics/horn_cleat.py",
         "sts2_rl/relics/captains_wheel.py", "sts2_rl/relics/anchor.py",
         "sts2_rl/relics/paels_eye.py", "sts2_rl/relics/runic_pyramid.py",
         "sts2_rl/cards/barricade_card.py", "sts2_rl/relics/cloak_clasp.py",
         "sts2_rl/relics/orichalcum.py", "sts2_rl/relics/royal_poison.py",
         "sts2_rl/relics/joss_paper.py", "sts2_rl/relics/electric_shrymp.py",
         "sts2_rl/relics/unceasing_top.py",
         "sts2_rl/relics/whispering_earring.py",
         "sts2_rl/cards/apparition.py", "sts2_rl/enchantments.py"],
    ),
    "hook_dispatch": (
        # Hook.cs holds the 147 static dispatchers and AbstractModel.cs the
        # virtual hook surface they call, but NEITHER of them decides which
        # listeners exist or in what order — and that ordering is this seam's
        # central claim. Added on the game side (Task 9 Step A):
        #  - CombatState.cs: IterateHookListeners (410-493), the ONLY statement
        #    of combat listener order (per creature: Powers -> Monster |
        #    Relics -> PotionSlots -> Orbs -> AllPiles cards + Affliction +
        #    Enchantment; then Modifiers, BadgeModels, MultiplayerScalingModel),
        #    and Contains (549-599), the per-item liveness re-filter.
        #  - RunState.cs: IterateHookListeners (545-596), the run-side order
        #    (deck cards + enchantments, then relics/potions/modifiers/badges
        #    only when there is no child combat, then the combat listeners).
        #  - Entities/Players/Player.cs: IsActiveForHooks (112, 272, 438,
        #    859-870), the per-player gate both iterators consult.
        #  - Entities/Players/PlayerCombatState.cs: AllPiles (70-80) — the card
        #    listeners are ordered Hand, Draw, Discard, Exhaust, Play and
        #    RE-DERIVED per dispatch, which is why a card's listener position
        #    moves when it changes pile.
        #  - Models/MonsterModel.cs, AfflictionModel.cs, EnchantmentModel.cs,
        #    BadgeModel.cs: the ShouldReceiveCombatHooks declarations and the
        #    listener categories the sim's flat list does or does not have.
        #  - Models/CardModel.cs (1895-1965): the per-Replay CardPlay loop that
        #    fires Hook.BeforeCardPlayed / Hook.AfterCardPlayed once per
        #    iteration — primary evidence for gap G4.
        #  - Powers/BufferPower.cs (18-27): the source comment that states the
        #    Late phase is load-bearing ("We use Late because other effects may
        #    reduce damage taken to 0 too") — evidence for gap G3.
        #  - Powers/TangledPower.cs + Powers/FreeAttackPower.cs +
        #    Powers/CuriousPower.cs + Relics/SpikedGauntlets.cs +
        #    Relics/BrilliantScarf.cs: the ported early-phase / Late-phase
        #    TryModifyEnergyCostInCombat pairs that make G2 and G3 LIVE.
        #  - Relics/ThrowingAxe.cs + Relics/PenNib.cs: the ported pair that
        #    makes G4 LIVE.
        # Every file above is cited with line numbers by the record, so by the
        # rule adopted in Task 8 it must be hashed: a change to it can
        # invalidate a verdict without touching Hook.cs.
        # Added in the Task 9 FIX PASS. The rule above was stated and then only
        # half-applied: these files are cited as evidence by the record (most
        # of them with line numbers) and were not hashed. Swept for with
        # audit/tools/dormancy_probes.py's companion citation sweep, i.e. every
        # .py/.cs token in audit/records/seam/hook_dispatch.json + the doc, resolved to
        # a real path and checked against this table. Game side:
        #  - Models/Afflictions/Hexed.cs: the ONLY C# affliction overriding an
        #    AbstractModel hook (AfterCardEnteredCombat) -- G6's whole dormancy
        #    argument ("porting Hexed is what makes G6 live").
        #  - Relics/WhiteBeastStatue.cs + Relics/WingedBoots.cs +
        #    Models/Modifiers/Flight.cs: the only implementers of
        #    ShouldForcePotionReward / ShouldAllowFreeTravel -- step 37's
        #    dormancy ("no second listener exists to be skipped"). NOTE the
        #    record used to cite Flight.cs as src/Core/Modifiers/Flight.cs,
        #    which does not exist; the real path is src/Core/Models/Modifiers/.
        #  - Relics/Fiddle.cs: the sole AfterPreventingDraw implementer, whose
        #    presentation-only body is why step 35's missing preventer
        #    out-param drops nothing observable.
        # Sim side: mad_science.py + events/tanx.py (the content that grants
        # G2's and G4's witnesses), relics/daughter_of_the_wind.py (G8's
        # executed witness), rewards.py (step 37's `any(...)`), previews.py and
        # env.py and cards/base.py (step 39's call sites and the max(0, ...)
        # clamp the no-negative-cost argument rests on), relics/paels_eye.py
        # (N3's CombatHistory reader -- the fix pass also found the record's
        # second named reader, relics/whispering_earring.py, reads no history
        # at all, so it is corrected in the record and NOT hashed), and
        # enchantments.py (G4's replay sources).
        # Sim side: hooks.py is only the dispatch bodies. The listener REGISTRY
        # is spread over combat.py (__init__ registration order, and
        # _resolve_card_play's once-per-play card bracket), cmds.py (power and
        # card register/unregister), player.py (potion belt register/detach,
        # all_cards), powers.py (Power._expire) and relics/base.py (attach);
        # monsters/base.py and afflictions.py are where the two MISSING
        # listener categories would be. The rest are the live gaps' sim halves.
        ["src/Core/Hooks/Hook.cs", "src/Core/Models/AbstractModel.cs",
         "src/Core/Combat/CombatState.cs", "src/Core/Runs/RunState.cs",
         "src/Core/Entities/Players/Player.cs",
         "src/Core/Entities/Players/PlayerCombatState.cs",
         "src/Core/Models/MonsterModel.cs",
         "src/Core/Models/AfflictionModel.cs",
         "src/Core/Models/EnchantmentModel.cs",
         "src/Core/Models/BadgeModel.cs",
         "src/Core/Models/CardModel.cs",
         "src/Core/Models/Powers/BufferPower.cs",
         "src/Core/Models/Powers/TangledPower.cs",
         "src/Core/Models/Powers/FreeAttackPower.cs",
         "src/Core/Models/Powers/CuriousPower.cs",
         "src/Core/Models/Relics/SpikedGauntlets.cs",
         "src/Core/Models/Relics/BrilliantScarf.cs",
         "src/Core/Models/Relics/ThrowingAxe.cs",
         "src/Core/Models/Relics/PenNib.cs",
         "src/Core/Models/Afflictions/Hexed.cs",
         "src/Core/Models/Relics/WhiteBeastStatue.cs",
         "src/Core/Models/Relics/WingedBoots.cs",
         "src/Core/Models/Modifiers/Flight.cs",
         "src/Core/Models/Relics/Fiddle.cs",
         # Cited by the fix pass's own corrected evidence, so hashed by the
         # same rule: KinPriest.cs:81-108 + Vantom.cs:97-105 are the two
         # already-ported members of G5's corrected 12-model list, and
         # FairyInABottle.cs is the single potion that overrides any hook at
         # all (step 15's executed evidence).
         "src/Core/Models/Monsters/KinPriest.cs",
         "src/Core/Models/Monsters/Vantom.cs",
         "src/Core/Models/Potions/FairyInABottle.cs"],
        ["sts2_rl/hooks.py", "sts2_rl/combat.py", "sts2_rl/cmds.py",
         "sts2_rl/player.py", "sts2_rl/powers.py", "sts2_rl/history.py",
         "sts2_rl/relics/base.py", "sts2_rl/monsters/base.py",
         "sts2_rl/afflictions.py",
         "sts2_rl/relics/spiked_gauntlets.py",
         "sts2_rl/relics/brilliant_scarf.py",
         "sts2_rl/relics/pen_nib.py", "sts2_rl/relics/throwing_axe.py",
         "sts2_rl/cards/unrelenting.py",
         "sts2_rl/monsters/overgrowth/vine_shambler.py",
         "sts2_rl/cards/mad_science.py", "sts2_rl/events/tanx.py",
         "sts2_rl/relics/daughter_of_the_wind.py",
         "sts2_rl/rewards.py", "sts2_rl/previews.py", "sts2_rl/env.py",
         "sts2_rl/cards/base.py",
         "sts2_rl/relics/paels_eye.py",
         "sts2_rl/enchantments.py",
         # Cited by the fix pass's own corrected evidence: tinker_time.py +
         # events/__init__.py are G2's rule-6 co-occurrence proof;
         # the_kin.py is G5's already-contended trigger; shrinker_beetle.py
         # and potions.py apply gap G9's Shrink witness; whirlwind.py and
         # full_env.py complete step 39's X-cost argument.
         "sts2_rl/events/tinker_time.py", "sts2_rl/events/__init__.py",
         "sts2_rl/monsters/overgrowth/the_kin.py",
         "sts2_rl/monsters/overgrowth/shrinker_beetle.py",
         "sts2_rl/potions.py", "sts2_rl/cards/whirlwind.py",
         "sts2_rl/full_env.py"],
    ),
    "monster_state_machine": (
        # The machine itself (all five files live one directory deeper than the
        # plan said, under src/Core/MonsterMoves/MonsterMoveStateMachine/).
        ["src/Core/MonsterMoves/MonsterMoveStateMachine/MonsterMoveStateMachine.cs",
         "src/Core/MonsterMoves/MonsterMoveStateMachine/MonsterState.cs",
         "src/Core/MonsterMoves/MonsterMoveStateMachine/MoveState.cs",
         "src/Core/MonsterMoves/MonsterMoveStateMachine/RandomBranchState.cs",
         "src/Core/MonsterMoves/MonsterMoveStateMachine/ConditionalBranchState.cs",
         "src/Core/MonsterMoves/MoveRepeatType.cs",
         # The machine's drivers (split by method with turn_structure /
         # creature_card_cmds — see the doc's boundary section).
         "src/Core/Models/MonsterModel.cs",
         "src/Core/Entities/Creatures/Creature.cs",
         "src/Core/Commands/CreatureCmd.cs",
         "src/Core/Combat/CombatManager.cs",
         # Monster models the record cites with line numbers: the five that
         # make the AddBranch-arg gap live, the two that read it correctly,
         # the hand-rolled ports, the ConditionalBranchState users, and the
         # AfterDeath hand-off from hook_dispatch.
         "src/Core/Models/Monsters/FlailKnight.cs",
         "src/Core/Models/Monsters/HunterKiller.cs",
         "src/Core/Models/Monsters/ScrollOfBiting.cs",
         "src/Core/Models/Monsters/SpectralKnight.cs",
         "src/Core/Models/Monsters/FakeMerchantMonster.cs",
         "src/Core/Models/Monsters/FossilStalker.cs",
         "src/Core/Models/Monsters/TwoTailedRat.cs",
         "src/Core/Models/Monsters/Flyconid.cs",
         "src/Core/Models/Monsters/TwigSlimeM.cs",
         "src/Core/Models/Monsters/LeafSlimeS.cs",
         "src/Core/Models/Monsters/Inklet.cs",
         "src/Core/Models/Monsters/PhrogParasite.cs",
         "src/Core/Models/Monsters/SlitheringStrangler.cs",
         "src/Core/Models/Monsters/Mawler.cs",
         "src/Core/Models/Monsters/Fogmog.cs",
         "src/Core/Models/Monsters/Exoskeleton.cs",
         "src/Core/Models/Monsters/Fabricator.cs",
         "src/Core/Models/Monsters/CeremonialBeast.cs",
         "src/Core/Models/Monsters/DecimillipedeSegment.cs",
         "src/Core/Models/Monsters/TestSubject.cs",
         "src/Core/Models/Monsters/WaterfallGiant.cs",
         "src/Core/Models/Monsters/Architect.cs",
         "src/Core/Models/Monsters/BigDummy.cs",
         "src/Core/Models/Monsters/KinPriest.cs",
         "src/Core/Models/Monsters/ThievingHopper.cs",
         "src/Core/Models/Powers/IllusionPower.cs",
         "src/Core/Models/Powers/FlutterPower.cs",
         "src/Core/Models/AbstractModelSubtypes.cs",
         # Added in the fix pass, all cited with line numbers by G4's corrected
         # (Whistle -> Glory) liveness argument and by steps 47-48's spawn-roll
         # truth table.
         "src/Core/Combat/CombatSide.cs",
         "src/Core/Models/Monsters/SoulNexus.cs"],
        ["sts2_rl/monsters/state_machine.py",
         "sts2_rl/monsters/base.py",
         "sts2_rl/cmds.py",
         "sts2_rl/combat.py",
         "sts2_rl/creatures.py",
         "sts2_rl/powers.py",
         "sts2_rl/monsters/hive/flail_knight.py",
         "sts2_rl/monsters/hive/hunter_killer.py",
         "sts2_rl/monsters/hive/exoskeleton.py",
         "sts2_rl/monsters/hive/decimillipede.py",
         "sts2_rl/monsters/glory/scroll_of_biting.py",
         "sts2_rl/monsters/glory/knights.py",
         "sts2_rl/monsters/glory/fabricator.py",
         "sts2_rl/monsters/fake_merchant.py",
         "sts2_rl/monsters/underdocks/fossil_stalker.py",
         "sts2_rl/monsters/underdocks/two_tailed_rat.py",
         "sts2_rl/monsters/overgrowth/flyconid.py",
         "sts2_rl/monsters/overgrowth/slimes.py",
         "sts2_rl/monsters/overgrowth/inklets.py",
         "sts2_rl/monsters/overgrowth/phrog_parasite.py",
         "sts2_rl/monsters/overgrowth/slithering_strangler.py",
         "sts2_rl/monsters/overgrowth/mawler.py",
         "sts2_rl/monsters/overgrowth/fogmog.py",
         "sts2_rl/monsters/overgrowth/ceremonial_beast.py",
         "sts2_rl/monsters/overgrowth/fuzzy_wurm_crawler.py",
         "sts2_rl/monsters/overgrowth/shrinker_beetle.py",
         "sts2_rl/monsters/overgrowth/the_kin.py",
         "sts2_rl/monsters/hive/thieving_hopper.py",
         "sts2_rl/monsters/hive/slumbering_beetle.py",
         "sts2_rl/monsters/underdocks/lagavulin_matriarch.py",
         "sts2_rl/monsters/underdocks/terror_eel.py",
         "sts2_rl/monsters/hive/__init__.py",
         "sts2_rl/monsters/glory/__init__.py",
         "sts2_rl/cards/whistle.py",
         "sts2_rl/events/fake_merchant.py",
         # Added in the fix pass. rooms.py / tanxs_whistle.py / run.py carry
         # G4's corrected liveness route (tanx is Glory-only and Glory is the
         # last act); bowlbugs.py is where ImbalancedPower's only applier sets
         # is_off_balance, which is why that stun site is inert; the four spawn
         # callers are cited by step 48's dormancy argument.
         "sts2_rl/rooms.py",
         "sts2_rl/run.py",
         "sts2_rl/relics/tanxs_whistle.py",
         "sts2_rl/monsters/hive/bowlbugs.py",
         "sts2_rl/monsters/underdocks/corpse_slug.py",
         "sts2_rl/monsters/hive/ovicopter.py",
         "sts2_rl/monsters/hive/the_obscura.py",
         "sts2_rl/monsters/underdocks/living_fog.py"],
    ),
    # Five "systems tier" seams added 2026-08-03 (wiring only — scope docs +
    # empty records). No verdicts yet;
    # audit/seams/<name>.md carries
    # the scope-boundary reasoning summarized in each comment below.
    "rng_streams": (
        # Rng.cs is the counter-wrapping PRNG every stream is one instance of;
        # MegaRandom.cs is the Xoshiro256** core it wraps. Neither file knows
        # about "streams" by NAME — that identity is the two RngType enums
        # (PlayerRngType.cs: 3 per-player streams; RunRngType.cs: 12 per-run
        # streams — found by grepping every consumer of PlayerRngSet/RunRngSet
        # for what defines their type parameter; no third file defines a
        # stream anywhere in src/) and the two Set classes that seed one Rng
        # per enum value off one base seed (PlayerRngSet.cs, RunRngSet.cs).
        # StringHelper.cs is pinned too: GetDeterministicHashCode is how a
        # stream's NAME becomes part of its seed (`new Rng(Seed, name)` adds
        # `GetDeterministicHashCode(SnakeCase(rngType))`), so a change to
        # either method silently reseeds every stream. Together these six
        # files are the whole "which stream a draw comes off, and in what
        # count" map — GAP-QUEUE.md's own "Behaviour in no tier's scope"
        # section names this as the highest-impact structural hole in the
        # queue, since stream desync is the highest-impact failure class the
        # queue tracks.
        ["src/Core/Random/Rng.cs", "src/Core/Random/MegaRandom.cs",
         "src/Core/Random/PlayerRngSet.cs", "src/Core/Runs/RunRngSet.cs",
         "src/Core/Entities/Rngs/PlayerRngType.cs",
         "src/Core/Entities/Rngs/RunRngType.cs",
         "src/Core/Helpers/StringHelper.cs"],
        # rng.py ports every file above in one module (MegaRandom, Rng,
        # RunRngSet, PlayerRngSet, RunRngType, PlayerRngType, plus
        # snake_case/deterministic_hash_code for StringHelper.cs). combat_rng.py
        # is the per-purpose CombatRng facade (legacy shared-random vs. parity
        # per-stream) every in-combat RNG consumer actually calls through.
        # run.py INSTANTIATES RunRngSet/PlayerRngSet but defines no stream
        # identity of its own — it is a consumer, claimed by run_layer for its
        # orchestration role, not here (see run_layer's scope doc).
        ["sts2_rl/rng.py", "sts2_rl/combat_rng.py"],
    ),
    "rewards": (
        # The 11 Rewards/*.cs files are the reward TYPES (Card/Gold/Potion/
        # Relic/SpecialCard/CardRemoval reward, plus the LinkedRewardSet that
        # groups them and the RewardType enum/extensions) and RewardsSet, the
        # per-room generator whose two populate loops around Hook.ModifyRewards
        # are this seam's central claim (see the crystal_sphere/g3 finding
        # below). RewardsCmd.cs is the only Commands/*.cs file whose subject is
        # rewards (OfferForRoomEnd/OfferCustom/GenerateForRoomEnd/GenerateCustom
        # — all four are thin wrappers around RewardsSet, so the file adds no
        # new logic but is the entry point every room-end and event/relic
        # reward path calls through).
        # CardCreationFlags/Options/Source/CardRarityOddsType.cs live under
        # src/Core/Runs/ in the game tree (so the P1-T2 brief's own
        # controller-analysis filed them under run_layer), but they are
        # overruled to HERE: their whole subject is "what cards can a reward
        # generate and at what rarity", and the sim proves it — every one of
        # the four is ported inside rewards.py (RarityOddsType,
        # CardCreationSource, CardCreationFlags, CardCreationOptions classes),
        # not run.py. Filing them under run_layer would split one audited
        # concept across two records for no reason but which C# folder it
        # happened to ship in.
        ["src/Core/Rewards/CardRemovalReward.cs", "src/Core/Rewards/CardReward.cs",
         "src/Core/Rewards/GoldReward.cs", "src/Core/Rewards/LinkedRewardSet.cs",
         "src/Core/Rewards/PotionReward.cs", "src/Core/Rewards/RelicReward.cs",
         "src/Core/Rewards/Reward.cs", "src/Core/Rewards/RewardType.cs",
         "src/Core/Rewards/RewardTypeExtensions.cs", "src/Core/Rewards/RewardsSet.cs",
         "src/Core/Rewards/SpecialCardReward.cs", "src/Core/Commands/RewardsCmd.cs",
         "src/Core/Runs/CardCreationFlags.cs", "src/Core/Runs/CardCreationOptions.cs",
         "src/Core/Runs/CardCreationSource.cs", "src/Core/Runs/CardRarityOddsType.cs"],
        # rewards.py is the whole sim counterpart: it carries the four
        # reassigned Runs/*.cs ports listed above AND the reward-generation
        # pipeline (roll_gold_reward, create_reward_cards, CombatRewards,
        # apply_reward_modifiers, generate_combat_rewards) that stands in for
        # RewardsSet/RewardsCmd. Nothing else in the sim generates a reward.
        ["sts2_rl/rewards.py"],
    ),
    "relic_pools": (
        # RelicGrabBag.cs is the escalation-ladder/refill machine two live
        # bugs already live here (relic/circlet/g4): GetAvailableDeque's
        # Shop->Common->Uncommon->Rare climb before falling back to Circlet,
        # and the _refreshAllowed refill branch. RelicFactory/CardFactory/
        # PotionFactory.cs are the three pool-to-instance choke points
        # (CardFactory doubles as the card-pool seam's factory per the brief —
        # there is no separate "card_pools" seam). RelicCmd.cs (Obtain/Remove/
        # Replace/Melt) and RelicSelectCmd.cs (the ChooseARelicScreen pick) are
        # the only two Commands/*.cs files whose subject is relics reaching a
        # player, as opposed to a pool being built. The 32 RelicPools/
        # CardPools/PotionPools files (9+13+10) are every named pool
        # (character/shared/event/deprecated/mock/token/curse/status/quest) —
        # claimed as one set rather than filtering because each one is a
        # top-level GenerateAll* roster with no shared base logic to point at
        # instead; a partial claim would leave an arbitrary subset unpinned
        # for no principled reason. GrabBag.cs (the generic weighted-pop
        # primitive RelicGrabBag delegates UnstableShuffle to) is NOT claimed
        # here — despite rng.py's grab_and_remove docstring naming it, its only
        # real caller is ActModel's tag-safe encounter/event picking, so it is
        # claimed by rooms_and_map instead (see that seam's doc).
        ["src/Core/Runs/RelicGrabBag.cs", "src/Core/Factories/RelicFactory.cs",
         "src/Core/Factories/CardFactory.cs", "src/Core/Factories/PotionFactory.cs",
         "src/Core/Commands/RelicCmd.cs", "src/Core/Commands/RelicSelectCmd.cs",
         "src/Core/Models/RelicPools/DefectRelicPool.cs",
         "src/Core/Models/RelicPools/DeprecatedRelicPool.cs",
         "src/Core/Models/RelicPools/EventRelicPool.cs",
         "src/Core/Models/RelicPools/FallbackRelicPool.cs",
         "src/Core/Models/RelicPools/IroncladRelicPool.cs",
         "src/Core/Models/RelicPools/NecrobinderRelicPool.cs",
         "src/Core/Models/RelicPools/RegentRelicPool.cs",
         "src/Core/Models/RelicPools/SharedRelicPool.cs",
         "src/Core/Models/RelicPools/SilentRelicPool.cs",
         "src/Core/Models/CardPools/ColorlessCardPool.cs",
         "src/Core/Models/CardPools/CurseCardPool.cs",
         "src/Core/Models/CardPools/DefectCardPool.cs",
         "src/Core/Models/CardPools/DeprecatedCardPool.cs",
         "src/Core/Models/CardPools/EventCardPool.cs",
         "src/Core/Models/CardPools/IroncladCardPool.cs",
         "src/Core/Models/CardPools/MockCardPool.cs",
         "src/Core/Models/CardPools/NecrobinderCardPool.cs",
         "src/Core/Models/CardPools/QuestCardPool.cs",
         "src/Core/Models/CardPools/RegentCardPool.cs",
         "src/Core/Models/CardPools/SilentCardPool.cs",
         "src/Core/Models/CardPools/StatusCardPool.cs",
         "src/Core/Models/CardPools/TokenCardPool.cs",
         "src/Core/Models/PotionPools/DefectPotionPool.cs",
         "src/Core/Models/PotionPools/DeprecatedPotionPool.cs",
         "src/Core/Models/PotionPools/EventPotionPool.cs",
         "src/Core/Models/PotionPools/IroncladPotionPool.cs",
         "src/Core/Models/PotionPools/MockPotionPool.cs",
         "src/Core/Models/PotionPools/NecrobinderPotionPool.cs",
         "src/Core/Models/PotionPools/RegentPotionPool.cs",
         "src/Core/Models/PotionPools/SharedPotionPool.cs",
         "src/Core/Models/PotionPools/SilentPotionPool.cs",
         "src/Core/Models/PotionPools/TokenPotionPool.cs"],
        # relic_pools.py + potion_pools.py are the transcribed rosters
        # (source-order id/rarity tuples) for the relic and potion halves;
        # cards/pool.py is the card-pool equivalent the brief asked to locate
        # (IRONCLAD_POOL/COLORLESS_POOL/CURSE_POOL plus the CardFactory.
        # FilterForCombat/GetDistinctForCombat/transform-options ports).
        # combat_card_db.py was checked and excluded: it is NetCombatCardDb's
        # per-combat card-ID assigner (multiplayer net identity), not pool
        # composition — a different subject entirely.
        ["sts2_rl/relic_pools.py", "sts2_rl/potion_pools.py", "sts2_rl/cards/pool.py"],
    ),
    "run_layer": (
        # RunManager.cs is the run orchestrator (also cross-cited by
        # rooms_and_map for its BuildRoomTypeBlacklist/RollRoomTypeFor methods
        # only — split by method, see that seam's doc). IRunState.cs is its
        # declared surface, the same "root contract, audited once" role
        # AbstractModel.cs plays for hook_dispatch. ExtraRunFields.cs is a
        # 3-field bag; two fields (StartedWithNeow save/load display,
        # TestSubjectKills save-progression) are unsimulated, but the third
        # (FreedRepy) is real, ported gameplay state (war_historian_repy.py's
        # only other reader), so the whole file is claimed.
        #
        # This seam is deliberately thin: RunState.cs (the other half of "the
        # run") is already claimed by hook_dispatch (IterateHookListeners);
        # RelicGrabBag.cs and RunRngSet.cs are claimed by relic_pools and
        # rng_streams respectively (do not double-claim — see those seams'
        # docs); CardCreationFlags/Options/Source/CardRarityOddsType.cs are
        # claimed by rewards, overruling the brief's own controller-analysis,
        # because rewards.py is where the sim actually ports them (see that
        # seam's doc). What is left after every neighbouring seam takes its
        # subject is orchestration plumbing — the singleton and its contract.
        #
        # Of the 21 Runs/*.cs candidate files (Runs/* minus RunState.cs),
        # 12 are dropped as pure DTO/interface/multiplayer/score plumbing —
        # every one is named, with its reason, in audit/seams/run_layer.md's
        # file table (not silently omitted): GameMode.cs + GameModeExtension.cs
        # (Daily/Custom mode + achievement-lock, unsimulated meta-progression);
        # ICardScope.cs (pure interface, implementation lives on RunState.cs/
        # CombatState.cs, both claimed elsewhere); IPlayerCollection.cs (pure
        # test-mocking interface per its own doc comment); MapLocation.cs +
        # RunLocation.cs (packet-serialization value types for multiplayer
        # message routing / map voting, by their own doc comments); NullRunState.cs
        # (null-object stub for menu/test contexts outside an active run — the
        # RL sim is always inside one); PlayerMapPointHistoryEntry.cs (per-floor
        # stat-tracking DTO, JSON+packet serialization only); RunHistory.cs +
        # RunHistoryPlayer.cs + RunHistoryUtilities.cs (save-file run-history
        # bookkeeping, no gameplay branch); ScoreUtility.cs (score/badge/
        # leaderboard math, not RL-relevant — the brief's own "score plumbing"
        # drop category).
        ["src/Core/Runs/RunManager.cs", "src/Core/Runs/IRunState.cs",
         "src/Core/Runs/ExtraRunFields.cs"],
        ["sts2_rl/run.py"],
    ),
    "rooms_and_map": (
        # Rooms/*.cs (14) and Map/*.cs (16) are claimed wholesale per the
        # brief (every room type + every map-generation file, including the
        # mock/null/saved/spoils variants — the room/map tier has no shared
        # base worth pointing at instead, same reasoning as relic_pools' 32
        # pool files). Models/Acts/*.cs (5: Overgrowth/Underdocks/Hive/Glory/
        # DeprecatedAct) is the sim's ACTS-INTO-THIS-SEAM decision: the sim has
        # no act registry (verified — no ACTS/ALL_ACTS/class Act anywhere in
        # sts2_rl/, per the brief), so there is no "act" kind to roster Acts
        # against, and Acts' structure (encounter/event rosters, boss discovery
        # order, map point type rolls) is folded into this seam instead of
        # being invisible.
        #
        # Four files were added on top of the brief's literal Rooms+Map+Acts
        # list, found by reading rooms.py/actmap.py/shop.py/rest_site.py's own
        # docstrings for game paths outside those three directories:
        #  - Models/ActModel.cs: the ACTS' BASE CLASS (GenerateRooms, the
        #    default GetMapPointTypes, ApplyActDiscoveryOrderModifications) —
        #    rooms.py's docstring cites it directly ("RoomSet.cs + ActModel.
        #    GenerateRooms -> RoomSet/ActRooms"); omitting it would leave the
        #    one method every Act file calls into unpinned.
        #  - Odds/UnknownMapPointOdds.cs: the "?"-node pity roller rooms.py
        #    ports as UnknownOdds; lives under Core/Odds/, not Map/ or Rooms/.
        #  - Entities/RestSite/RestSiteOption.cs: rest_site.py's own docstring
        #    names it as ground truth (Hook.TryModifyRestSiteOptions); it is a
        #    sibling of Rooms/RestSiteRoom.cs, not the same file.
        #  - Helpers/GrabBag.cs: the generic weighted-pop primitive ActModel
        #    uses for tag-safe encounter/event picking (AddWithoutRepeatingTags)
        #    — NOT claimed by relic_pools (see that seam's doc) because
        #    RelicGrabBag's own shuffle/escalation logic never calls it.
        # Entities/Merchant/*.cs (7 of 8): shop.py's docstring names
        # MerchantInventory.cs and MerchantEntry.cs as ground truth alongside
        # the already-listed Rooms/MerchantRoom.cs; the four entry subclasses
        # (Card/CardRemoval/Potion/Relic) and PurchaseStatus.cs are the pricing/
        # stocking logic shop.py ports. MerchantDialogueSet.cs (the 8th file,
        # shop NPC flavor lines) is dropped — presentation only, no priced
        # behaviour.
        # RunManager.cs is cross-cited from run_layer (BuildRoomTypeBlacklist/
        # RollRoomTypeFor only, per rooms.py's docstring — the rest of the file
        # is run_layer's, see that seam's doc for the split).
        #
        # NOT claimed here: EncounterModel.cs's own GenerateMonstersWithSlots
        # (monster-slot generation) — GAP-QUEUE.md names this as one of the
        # two worst systems-tier holes, but it is the ENCOUNTER kind's own
        # subject (each encounter content record's future job), not "which
        # encounter gets rolled for a room". Left open on purpose; see the
        # P1-T2 report's MODEL_ROOT_CLASSES discussion for why EncounterModel
        # is still not a root.
        ["src/Core/Rooms/AbstractRoom.cs", "src/Core/Rooms/BackgroundAssets.cs",
         "src/Core/Rooms/CombatEventVisuals.cs", "src/Core/Rooms/CombatRoom.cs",
         "src/Core/Rooms/CombatRoomMode.cs", "src/Core/Rooms/EventRoom.cs",
         "src/Core/Rooms/ICombatRoomVisuals.cs", "src/Core/Rooms/MapRoom.cs",
         "src/Core/Rooms/MerchantRoom.cs", "src/Core/Rooms/RestSiteRoom.cs",
         "src/Core/Rooms/RoomSet.cs", "src/Core/Rooms/RoomType.cs",
         "src/Core/Rooms/RoomTypeExtensions.cs", "src/Core/Rooms/TreasureRoom.cs",
         "src/Core/Map/ActMap.cs", "src/Core/Map/GoldenPathActMap.cs",
         "src/Core/Map/MapCoord.cs", "src/Core/Map/MapPathPruning.cs",
         "src/Core/Map/MapPoint.cs", "src/Core/Map/MapPointState.cs",
         "src/Core/Map/MapPointType.cs", "src/Core/Map/MapPointTypeCounts.cs",
         "src/Core/Map/MapPostProcessing.cs", "src/Core/Map/MapTravel.cs",
         "src/Core/Map/MockCraftedActMap.cs", "src/Core/Map/MockSinglePointActMap.cs",
         "src/Core/Map/NullActMap.cs", "src/Core/Map/SavedActMap.cs",
         "src/Core/Map/SpoilsActMap.cs", "src/Core/Map/StandardActMap.cs",
         "src/Core/Models/Acts/DeprecatedAct.cs", "src/Core/Models/Acts/Glory.cs",
         "src/Core/Models/Acts/Hive.cs", "src/Core/Models/Acts/Overgrowth.cs",
         "src/Core/Models/Acts/Underdocks.cs", "src/Core/Models/ActModel.cs",
         "src/Core/Odds/UnknownMapPointOdds.cs",
         "src/Core/Entities/RestSite/RestSiteOption.cs",
         "src/Core/Entities/Merchant/MerchantEntry.cs",
         "src/Core/Entities/Merchant/MerchantInventory.cs",
         "src/Core/Entities/Merchant/MerchantCardEntry.cs",
         "src/Core/Entities/Merchant/MerchantCardRemovalEntry.cs",
         "src/Core/Entities/Merchant/MerchantPotionEntry.cs",
         "src/Core/Entities/Merchant/MerchantRelicEntry.cs",
         "src/Core/Entities/Merchant/PurchaseStatus.cs",
         "src/Core/Helpers/GrabBag.cs", "src/Core/Commands/MapCmd.cs",
         "src/Core/Runs/RunManager.cs"],
        ["sts2_rl/rooms.py", "sts2_rl/actmap.py", "sts2_rl/rest_site.py",
         "sts2_rl/shop.py"],
    ),
    "potion_pipeline": (
        # The `commands_remainder` decision (P1-T2 brief, item 6): of the 13
        # Commands/*.cs files not already claimed by an existing seam, 4 go to
        # a new-in-this-task seam (RewardsCmd->rewards, MapCmd->rooms_and_map,
        # RelicCmd+RelicSelectCmd->relic_pools — all folded into the seam
        # above that owns their subject, per the brief's own instruction), 8
        # are out of scope (ForgeCmd/OrbCmd/OstyCmd — Regent/Defect/
        # Necrobinder, Ironclad-irrelevant; SfxCmd/VfxCmd/TalkCmd/ThinkCmd —
        # presentation; Cmd.cs — overruling the brief's suggested run_layer
        # fold, since on inspection it is nothing but Godot scene-tree timer
        # waits for animation pacing, the same presentation category as the
        # four *Cmd files beside it, not run orchestration), and PotionCmd.cs
        # has no natural fold target — it is the ENTIRE belt-procurement/
        # discard pipeline (TryToProcure/Discard, each wrapping a Hook.*
        # dispatch), and folding it into relic_pools (pool composition) or
        # rewards (offer generation) would misdescribe it. So it gets this
        # sixth seam, paired with PotionModel.cs: harness.MODEL_ROOT_CLASSES'
        # block comment already documented this exact hole ("There is no
        # potion seam, so stopping at PotionModel means PotionModel.
        # OnUseWrapper ... is verdicted nowhere") — that comment is updated
        # alongside this entry to point at potion_pipeline instead of
        # asserting the hole is still open.
        ["src/Core/Commands/PotionCmd.cs", "src/Core/Models/PotionModel.cs"],
        # potions.py holds every ported potion's OnUse body (already cited by
        # hook_dispatch for unrelated gap evidence — cross-seam citation on the
        # sim side is normal, see hooks.py/combat.py/player.py's own multi-seam
        # citations). player.py is the belt itself (add_potion/discard_potion,
        # PotionCmd.TryToProcure/Discard's counterpart). combat.py is
        # use_potion, the in-combat consumption path. run.py's add_potion is
        # the run-level (non-combat, e.g. reward) grant path.
        ["sts2_rl/potions.py", "sts2_rl/player.py", "sts2_rl/combat.py",
         "sts2_rl/run.py"],
    ),
}
SEAMS: tuple[str, ...] = tuple(SEAM_SOURCES)


def _hash_sources(paths: list[str], base: Path) -> list[dict]:
    return [{"path": p, "sha256": file_sha256(base / p)} for p in paths]


def skeleton(unit: str, game_root: Path | None = None,
             audits_dir: Path | None = None, sim_only: bool = False) -> Path:
    """Write audit/records/<kind>/<id>.json with hooks/steps enumerated and
    verdicts empty, ready for an agent to fill in. Refuses to overwrite."""
    root = game_root or DEFAULT_GAME_ROOT
    adir = audits_dir or DEFAULT_AUDITS_DIR
    kind, _, unit_id = unit.partition("/")

    if sim_only:
        row = next(r for r in roster(kind, root) if r["unit"] == unit)
        record = {
            "unit": unit,
            "sim_only": True,
            "rationale": "",
            "sim_source": {"path": row["sim_path"],
                           "sha256": file_sha256(_REPO / row["sim_path"])},
            "hooks": {},
            "guards": [],
            "verdict": "",
            "audited": "",
        }
    elif kind == "seam":
        game_paths, sim_paths = SEAM_SOURCES[unit_id]
        record: dict = {
            "unit": unit,
            "game_sources": _hash_sources(game_paths, root),
            "sim_sources": _hash_sources(sim_paths, _REPO),
            "steps": [],
            "guards": [],
            "verdict": "",
            "audited": "",
        }
    else:
        row = next(r for r in roster(kind, root) if r["unit"] == unit)
        gp = root / row["game_path"]
        record = {
            "unit": unit,
            "game_source": {"path": row["game_path"], "sha256": file_sha256(gp)},
            "sim_source": {"path": row["sim_path"],
                           "sha256": file_sha256(_REPO / row["sim_path"])},
            "hooks": {
                name: {"maps_to": "", "verdict": ""}
                for name in list_overrides(
                    gp.read_text(encoding="utf-8-sig", errors="replace"),
                    game_root=root, source_path=gp, kind=kind)
            },
            "guards": [],
            "verdict": "",
            "audited": "",
        }

    out = Path(adir) / kind / f"{unit_id}.json"
    if out.exists():
        raise FileExistsError(f"{out} exists — delete it explicitly to re-audit")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return out


_SHA_RE = re.compile(r"[0-9a-f]{64}")


def _check_extra_sources(record: dict, errs: list[str]) -> None:
    """Validate the optional `extra_sources` list.

    Every file a verdict cites with a line number has to be hashed by the
    record (audit/README.md, "Staleness"). The singular game_source/sim_source
    pair only covers the unit's own two files, so any *other* file a content
    record leans on goes here — one entry per file, each naming the root its
    path resolves against. Optional: the key may be absent entirely."""
    if "extra_sources" not in record:
        return
    srcs = record.get("extra_sources")
    if not isinstance(srcs, list):
        errs.append("extra_sources: must be a list")
        return
    for i, s in enumerate(srcs):
        if not isinstance(s, dict):
            errs.append(f"extra_sources[{i}]: must be an object")
            continue
        if not s.get("path") or not s.get("sha256"):
            errs.append(f"extra_sources[{i}]: path and sha256 required")
        elif not _SHA_RE.fullmatch(str(s["sha256"])):
            errs.append(
                f"extra_sources[{i}]: sha256 must be 64 lowercase hex digits")
        if s.get("side") not in SOURCE_SIDES:
            errs.append(
                f"extra_sources[{i}]: side {s.get('side')!r} not one of "
                f"{SOURCE_SIDES}")


def record_entries(record: dict) -> list[dict]:
    """Every verdict-bearing entry in a record: hooks, steps and guards."""
    out = list((record.get("hooks") or {}).values())
    out += list(record.get("steps") or [])
    out += list(record.get("guards") or [])
    return [e for e in out if isinstance(e, dict)]


def _check_entry(where: str, entry: dict, errs: list[str]) -> None:
    v = entry.get("verdict", "")
    if v not in VERDICTS:
        errs.append(f"{where}: verdict {v!r} not one of {VERDICTS}")
        return
    if v in ("waiver", "deliberate-divergence") and not entry.get("rationale"):
        errs.append(f"{where}: verdict {v!r} requires a non-empty rationale")
    if v == "gap" and not entry.get("issue"):
        errs.append(f"{where}: verdict 'gap' requires a non-empty issue")
    # Optional `live` — liveness as data instead of a LIVE/dormant token buried
    # in prose, which a third of the power tier's gap entries simply omitted.
    if "live" in entry:
        if not isinstance(entry["live"], bool):
            errs.append(f"{where}: 'live' must be true or false, "
                        f"got {entry['live']!r}")
        elif v != "gap":
            errs.append(f"{where}: 'live' only means something on a 'gap' "
                        f"entry, not {v!r}")


def enumeration_gaps(record: dict, game_root: Path | None = None) -> list[str]:
    """`public override` members the unit INHERITS that the record gives no
    verdict for. Reported separately from validate_record's errors because the
    422 records predating base-class following were written against an
    enumeration that could not see these; promoting them to errors in one step
    would red-line the whole ledger. `validate --strict-inherited` does that
    promotion once the records have caught up."""
    root = game_root or DEFAULT_GAME_ROOT
    kind = record.get("unit", "").split("/", 1)[0]
    if record.get("sim_only") or kind == "seam":
        return []
    gp = root / (record.get("game_source") or {}).get("path", "")
    if not gp.is_file():
        return []
    _, inherited = split_overrides(
        gp.read_text(encoding="utf-8-sig", errors="replace"), root, gp, kind)
    have = {hook_key(k) for k in (record.get("hooks") or {})}
    return [n for n in inherited if n not in have]


def validate_record(record: dict, game_root: Path | None = None,
                    strict_inherited: bool = False) -> list[str]:
    """Completeness/vocabulary validation. Returns error strings; [] = valid.
    Staleness (hash drift) is audit_status.py's job, not validation's."""
    root = game_root or DEFAULT_GAME_ROOT
    errs: list[str] = []
    unit = record.get("unit", "")
    kind, _, unit_id = unit.partition("/")
    if not kind or not unit_id:
        return [f"bad unit id: {unit!r}"]

    entries: list[dict] = []

    if kind == "seam":
        for side in ("game_sources", "sim_sources"):
            srcs = record.get(side) or []
            if not srcs:
                errs.append(f"{side}: at least one source required")
            for i, s in enumerate(srcs):
                if not s.get("path") or not s.get("sha256"):
                    errs.append(f"{side}[{i}]: path and sha256 required")
        steps = record.get("steps") or []
        if not steps:
            errs.append("seam record requires non-empty steps")
        for i, s in enumerate(steps):
            if not s.get("what"):
                errs.append(f"steps[{i}]: 'what' required")
            _check_entry(f"steps[{i}]", s, errs)
        entries += steps
    elif record.get("sim_only") is not None and record.get("sim_only") is not False:
        # A unit the sim has and the game does not (a test fixture, a
        # scaffold). It cannot carry a game_source, so the ordinary shape
        # rejects it and audit_status shows it unaudited forever. Recording it
        # as sim-only-by-design is a CLAIM, so it costs a rationale.
        if record.get("sim_only") is not True:
            errs.append(f"sim_only must be true, got {record['sim_only']!r}")
        if record.get("game_source"):
            errs.append("sim_only record must not carry a game_source")
        src = record.get("sim_source") or {}
        if not src.get("path") or not src.get("sha256"):
            errs.append("sim_source: path and sha256 required")
        elif not (_REPO / src["path"]).is_file():
            errs.append(f"sim source not found: {_REPO / src['path']}")
        if not record.get("rationale"):
            errs.append("sim_only requires a rationale naming why the unit has "
                        "no C# counterpart")
        if record.get("verdict") not in VERDICTS:
            errs.append(f"verdict {record.get('verdict')!r} not one of {VERDICTS}")
        hooks = record.get("hooks") or {}
        for name, entry in hooks.items():
            _check_entry(f"hooks[{name}]", entry, errs)
        entries += list(hooks.values())
    else:
        for side in ("game_source", "sim_source"):
            src = record.get(side) or {}
            if not src.get("path") or not src.get("sha256"):
                errs.append(f"{side}: path and sha256 required")
        hooks = record.get("hooks")
        if hooks is None:
            errs.append("hooks section required")
            hooks = {}
        gp = root / (record.get("game_source") or {}).get("path", "")
        if gp.is_file():
            have = {hook_key(k) for k in hooks}
            declared, inherited = split_overrides(
                gp.read_text(encoding="utf-8-sig", errors="replace"), root, gp,
                kind)
            missing = [n for n in declared if n not in have]
            if strict_inherited:
                missing += [n for n in inherited if n not in have]
            if missing:
                errs.append(
                    f"hooks missing verdicts for overrides: {sorted(missing)}")
        else:
            errs.append(f"game source not found: {gp}")
        for name, entry in hooks.items():
            _check_entry(f"hooks[{name}]", entry, errs)
            if entry.get("verdict") == "faithful" and not entry.get("maps_to"):
                errs.append(f"hooks[{name}]: 'faithful' requires maps_to")
        entries += list(hooks.values())

    _check_extra_sources(record, errs)

    guards = record.get("guards") or []
    for i, g in enumerate(guards):
        if not g.get("what"):
            errs.append(f"guards[{i}]: 'what' required")
        _check_entry(f"guards[{i}]", g, errs)
    entries += guards

    verdicts = [e.get("verdict") for e in entries if e.get("verdict") in VERDICTS]
    if verdicts:
        worst = max(verdicts, key=VERDICTS.index)
        if record.get("verdict") != worst:
            errs.append(
                f"unit verdict {record.get('verdict')!r} != rollup {worst!r}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", record.get("audited") or ""):
        errs.append("audited must be YYYY-MM-DD")
    return errs


REHASH_WARNING = """\
  ############################################################################
  #  REHASH IS NOT A RE-AUDIT.                                               #
  #                                                                          #
  #  A source hash is not bookkeeping - it is the record's claim that its    #
  #  verdicts were reached against exactly this text. Re-pinning it without  #
  #  re-reading both sides converts a durable finding into a decoration:     #
  #  the record then asserts a verdict over code nobody has looked at, and   #
  #  the staleness detector can never flag it again.                         #
  #                                                                          #
  #  Only run this AFTER an agent has re-read the changed source and         #
  #  confirmed every verdict in the record still holds. It is a mechanical   #
  #  convenience for the last step of a re-audit, never a substitute for one.#
  ############################################################################
"""


def rehash_record(record: dict, game_root: Path | None = None) -> list[str]:
    """Recompute every hash the record carries. Mutates it in place and
    returns one line per hash that actually changed (empty = already current).

    Covers all three shapes: the seam plural lists, the content singular pair,
    and the optional `extra_sources` list — a partial re-pin would leave the
    record half-stale, which is worse than not re-pinning at all."""
    root = game_root or DEFAULT_GAME_ROOT
    changes: list[str] = []

    def repin(where: str, src: dict, base: Path) -> None:
        p = base / src.get("path", "")
        if not p.is_file():
            changes.append(f"{where}: MISSING {p} — left unchanged")
            return
        new = file_sha256(p)
        if new != src.get("sha256"):
            changes.append(
                f"{where}: {src.get('path')} {str(src.get('sha256'))[:12]}"
                f" -> {new[:12]}")
            src["sha256"] = new

    for side, base in (("game_sources", root), ("sim_sources", _REPO)):
        for i, s in enumerate(record.get(side) or []):
            repin(f"{side}[{i}]", s, base)
    for side, base in (("game_source", root), ("sim_source", _REPO)):
        src = record.get(side)
        if isinstance(src, dict) and src.get("path"):
            repin(side, src, base)
    for i, s in enumerate(record.get("extra_sources") or []):
        if isinstance(s, dict):
            repin(f"extra_sources[{i}]", s, source_base(s.get("side"), root))
    return changes


def _record_path(target: str, audits_dir: Path | None = None) -> Path:
    """Accept either a unit id (`power/artifact`) or a record file path."""
    adir = Path(audits_dir or DEFAULT_AUDITS_DIR)
    if not target.endswith(".json"):
        kind, _, unit_id = target.partition("/")
        return adir / kind / f"{unit_id}.json"
    return Path(target)


def rehash(targets: list[str], game_root: Path | None = None,
           audits_dir: Path | None = None, write: bool = True) -> dict[str, list[str]]:
    """Bulk `rehash_record` over unit ids and/or record paths."""
    out: dict[str, list[str]] = {}
    for t in targets:
        p = _record_path(t, audits_dir)
        record = json.loads(p.read_text(encoding="utf-8"))
        changes = rehash_record(record, game_root=game_root)
        if changes and write:
            p.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        out[str(p)] = changes
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ap_roster = sub.add_parser("roster", help="print the audit work queue")
    ap_roster.add_argument("kind", nargs="?", choices=sorted(GAME_MODEL_DIRS))
    ap_skel = sub.add_parser("skeleton", help="write a record skeleton")
    ap_skel.add_argument("unit", help="e.g. relic/unsettling_lamp or seam/power_cmd")
    ap_skel.add_argument(
        "--sim-only", action="store_true",
        help="unit exists in the sim with no C# counterpart (needs a rationale)")
    ap_val = sub.add_parser("validate", help="validate audit records")
    ap_val.add_argument("paths", nargs="*", help="record files (default: all)")
    ap_val.add_argument(
        "--strict-inherited", action="store_true",
        help="treat un-audited INHERITED overrides as errors, not warnings")
    ap_re = sub.add_parser(
        "rehash",
        help="re-pin a record's source hashes — NOT a re-audit, see the banner")
    ap_re.add_argument("targets", nargs="*",
                       help="unit ids (power/artifact) and/or record paths")
    ap_re.add_argument("--all", action="store_true",
                       help="every record under audit/records/ (bulk form)")
    ap_re.add_argument("--kind", help="every record of one kind (bulk form)")
    ap_re.add_argument("--dry-run", action="store_true",
                       help="report what would be re-pinned, write nothing")
    args = ap.parse_args(argv)

    if args.cmd == "roster":
        kinds = [args.kind] if args.kind else sorted(GAME_MODEL_DIRS)
        for kind in kinds:
            rows = roster(kind)
            unmatched = [x for x in rows if not x["game_exists"]]
            extra = unported(kind)
            print(f"{kind}: {len(rows)} sim units, "
                  f"{len(unmatched)} unmatched, {len(extra)} unported C# files")
            for x in unmatched:
                print(f"  UNMATCHED {x['unit']} -> expected {x['game_path']}")
    if args.cmd == "skeleton":
        out = skeleton(args.unit, sim_only=args.sim_only)
        print(f"wrote {out}")
    if args.cmd == "validate":
        paths = ([Path(p) for p in args.paths]
                 or sorted(DEFAULT_AUDITS_DIR.rglob("*.json")))
        bad = warned = 0
        for p in paths:
            record = json.loads(p.read_text(encoding="utf-8"))
            errs = validate_record(
                record, strict_inherited=args.strict_inherited)
            for e in errs:
                print(f"{p}: {e}")
            bad += bool(errs)
            if not args.strict_inherited:
                gaps = enumeration_gaps(record)
                if gaps:
                    print(f"{p}: WARN inherited overrides with no verdict: "
                          f"{sorted(gaps)}")
                    warned += 1
        print(f"{len(paths)} record(s), {bad} invalid"
              + (f", {warned} with un-audited inherited overrides "
                 f"(re-run with --strict-inherited)" if warned else ""))
        return 1 if bad else 0
    if args.cmd == "rehash":
        print(REHASH_WARNING, file=sys.stderr)
        targets = list(args.targets)
        if args.all:
            targets += [str(p) for p in sorted(DEFAULT_AUDITS_DIR.rglob("*.json"))]
        if args.kind:
            targets += [str(p) for p in
                        sorted((DEFAULT_AUDITS_DIR / args.kind).glob("*.json"))]
        if not targets:
            print("rehash: nothing to do — pass unit ids, --all or --kind")
            return 2
        results = rehash(targets, write=not args.dry_run)
        repinned = 0
        for path, changes in results.items():
            for c in changes:
                print(f"{path}: {c}")
            repinned += bool(changes)
        verb = "would re-pin" if args.dry_run else "re-pinned"
        print(f"{len(results)} record(s), {verb} {repinned}")
        print("re-pinned hashes are worthless unless the record was re-audited "
              "against the new text", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
