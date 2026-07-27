"""Completeness harness for the source-to-sim audit pipeline.

Design: docs/superpowers/specs/2026-07-24-source-audit-pipeline-design.md.
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
}

# `public override <type> <Name>(  |  => ...  |  { ...` — one-regex scan of
# the decompiled output, which is uniform. Captures the member name whether
# it is a method or an expression-bodied property. The type character class
# includes `()` so a parenthesised tuple return — `Task<(PileType, int)>`,
# `(decimal, bool)` — is matched; without it those hooks were silently
# skipped, and the enumeration cannot be trusted if it can miss a member.
# The quantifier is non-greedy, so `void Foo(` still parses as type `void`.
_OVERRIDE_RE = re.compile(
    r"^\s*public\s+override\s+(?:sealed\s+)?(?:async\s+)?"
    r"[\w<>,.?\[\]() ]+?\s(\w+)\s*(?:\(|=>|\{|$)",
    re.M,
)

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
# 134 power records would add the same noise 134 times — and that layer is
# already audited, once, by the seam tier (hook_dispatch hashes
# AbstractModel.cs and the model files). Base-class following stops here.
MODEL_ROOT_CLASSES = frozenset({
    "AbstractModel", "AfflictionModel", "BadgeModel", "CardModel",
    "CreatureModel", "EnchantmentModel", "EventModel", "ModifierModel",
    "MonsterModel", "OrbModel", "PotionModel", "PowerModel", "RelicModel",
})


def _declared_overrides(cs_text: str) -> list[str]:
    """Names of every `public override` member declared in this text."""
    return list(dict.fromkeys(_OVERRIDE_RE.findall(cs_text)))


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
                    source_path: Path | None = None) -> tuple[list[str], list[str]]:
    """(declared here, inherited from the immediate base), in declaration order.

    A `.cs` file that declares only `OriginModel` while its base declares the
    real behaviour used to enumerate as one hook, so `validate` confirmed a
    verdict for that one and never noticed the other seven. One level of base
    is enough for the shapes this source uses; `game_root` is required to
    resolve it because the base normally lives in another file."""
    declared = _declared_overrides(cs_text)
    if game_root is None:
        return declared, []
    base = _base_class_name(cs_text)
    if not base:
        return declared, []
    bp = find_class_file(base, game_root)
    if bp is None or (source_path and bp.resolve() == Path(source_path).resolve()):
        return declared, []
    inherited = [n for n in _declared_overrides(
        bp.read_text(encoding="utf-8-sig", errors="replace"))
        if n not in declared]
    return declared, inherited


def list_overrides(cs_text: str, game_root: Path | None = None,
                   source_path: Path | None = None) -> list[str]:
    """Every `public override` member the unit really has, in declaration
    order: the ones it declares, then the ones it inherits from its immediate
    base. Pass `game_root` to get the inherited half."""
    declared, inherited = split_overrides(cs_text, game_root, source_path)
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
    if kind == "monster":
        return _monster_units()
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
}
SEAMS: tuple[str, ...] = tuple(SEAM_SOURCES)


def _hash_sources(paths: list[str], base: Path) -> list[dict]:
    return [{"path": p, "sha256": file_sha256(base / p)} for p in paths]


def skeleton(unit: str, game_root: Path | None = None,
             audits_dir: Path | None = None) -> Path:
    """Write audit/records/<kind>/<id>.json with hooks/steps enumerated and
    verdicts empty, ready for an agent to fill in. Refuses to overwrite."""
    root = game_root or DEFAULT_GAME_ROOT
    adir = audits_dir or DEFAULT_AUDITS_DIR
    kind, _, unit_id = unit.partition("/")

    if kind == "seam":
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
                    game_root=root, source_path=gp)
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
    if record.get("sim_only") or (record.get("unit", "").split("/", 1)[0] == "seam"):
        return []
    gp = root / (record.get("game_source") or {}).get("path", "")
    if not gp.is_file():
        return []
    _, inherited = split_overrides(
        gp.read_text(encoding="utf-8-sig", errors="replace"), root, gp)
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
                gp.read_text(encoding="utf-8-sig", errors="replace"), root, gp)
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
        out = skeleton(args.unit)
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
