"""Map decompiled-game runtime ids (``POWER.X`` / ``MONSTER.X``) to sim vocab
ids for ``contract.py``'s ``game_id_map`` (Task A of the SpireBot live-bot
project).

No RunReplays save-key table exists for powers/monsters the way
``conformance/idmap.py`` has one for cards/relics/potions (replay comparison
keys those two off resolved runtime state, not a save-file id list), so this
module derives the mapping directly from the decompiled game's own id
computation instead of guessing.

Evidence (decompiled source, ``Slay the Spire 2/src``):

- ``Core/Models/ModelDb.cs:471-494`` -- ``ModelDb.GetId(Type)`` returns
  ``new ModelId(GetCategory(type), GetEntry(type))`` where
  ``GetCategory`` = ``ModelId.SlugifyCategory(nearest-AbstractModel-subclass
  .Name)`` (``PowerModel`` -> ``POWER``, ``MonsterModel`` -> ``MONSTER``,
  stripping a trailing ``_MODEL``, ``Core/Models/ModelId.cs:57-67``) and
  ``GetEntry`` = ``StringHelper.Slugify(type.Name)`` -- the CONCRETE class
  name, unstripped.
- ``Core/Models/ModelId.cs:37-40`` -- ``ModelId.ToString()`` returns
  ``Category + "." + Entry``, e.g. ``POWER.VULNERABLE_POWER``,
  ``MONSTER.AEONGLASS``.
- ``Core/Helpers/StringHelper.cs:69-79`` -- ``Slugify(txt)`` inserts ``_``
  before every uppercase letter preceded by an alphanumeric char (i.e. every
  camel-case word boundary), upper-cases, then strips anything outside
  ``[A-Z0-9_]``.
- ``RunReplays/RunReplays/GameStateSnapshot.cs:96,109`` -- ``PowerInfo.Id =
  p.Id.ToString()``: a live mod literally holds this exact dotted string for
  power instances, confirming it as the wire format (not the bare class
  name, not an attribute). The same snapshot does NOT serialize a
  ``MonsterModel.Id``/``ModelId`` for enemies today (only a display
  ``Creature.Name``), but the identifier a mod WOULD read off
  ``combatState.Enemies[e].Monster`` is this same ``ModelId`` computation --
  every concrete ``MonsterModel`` subclass gets one via ``AbstractModel``'s
  constructor (``Core/Models/AbstractModel.cs:70-78``) regardless of whether
  today's snapshot happens to serialize it.

Verified default rules (checked against every ``.cs`` file under
``Slay the Spire 2/src/Core/Models/{Powers,Monsters}`` and vocab.json's
current 138 powers / 111 monsters, Task A research -- see
``.superpowers/sdd/task-A-report.md``):

- **powers**: the game class name is ``PascalCase(vocab_id) + "Power"``.
  All 138 vocab power ids resolve this way; zero exceptions found.
- **monsters**: the game class name IS the vocab id verbatim -- vocab's
  ``monsters`` list is already PascalCase game/sim class names (sim
  monster classes are named identically to their game counterparts by this
  repo's porting convention; ``full_env.MONSTER_INDEX`` keys off
  ``e.__class__.__name__`` for exactly this reason). 108 of 111 resolve
  this way; the other 3 (``MONSTERS_WITHOUT_GAME_CLASS``) are sim-internal
  abstract base classes with no decompiled-source counterpart at all and
  are intentionally left unmapped -- see that constant's docstring.
- **afflictions**/**enchantments**: the same ``ModelId`` computation applies
  to every ``AbstractModel`` subclass, not just powers/monsters --
  ``AfflictionModel``/``EnchantmentModel`` are themselves ``: AbstractModel``,
  so ``GetCategory`` -> ``AFFLICTION``/``ENCHANTMENT`` (``AfflictionModel``/
  ``EnchantmentModel`` slugified and stripped of the trailing ``_MODEL``,
  exactly like ``PowerModel`` -> ``POWER``). Unlike powers, the concrete
  class name carries NO suffix -- it is ``PascalCase(sim_id)`` verbatim.
  Evidence: ``sts2_rl/afflictions.py``'s and ``sts2_rl/enchantments.py``'s
  own docstrings cite the decompiled source file per class (e.g.
  ``Tainted.cs``, ``Galvanized.cs``, ``Hexed.cs`` for afflictions;
  ``Sown.cs``, ``Slither.cs``, ``Adroit.cs``, ``TezcatarasEmber.cs``,
  ``PerfectFit.cs``, ``RoyallyApproved.cs``, etc. for enchantments), and
  every one of those file/class names is ``PascalCase(sim_id)`` verbatim,
  with exactly one exception: ``sts2_rl/enchantments.py``'s
  ``SoulsEnchantment`` (``id = "souls"``) cites ``Source: SoulsPower.cs`` --
  the decompiled class is named ``SoulsPower`` despite extending
  ``EnchantmentModel``, not ``PowerModel``. All 7 affliction sim ids
  (``afflictions.AFFLICTION_INDEX``) and all 20 enchantment sim ids
  (``enchantments.ENCHANTMENT_INDEX``) were checked against their module's
  own source-file citations; ``_ENCHANTMENT_CLASS_EXCEPTIONS`` holds the
  one divergence found (``_AFFLICTION_CLASS_EXCEPTIONS`` is empty).

``_POWER_CLASS_EXCEPTIONS``/``_MONSTER_CLASS_EXCEPTIONS``/
``_AFFLICTION_CLASS_EXCEPTIONS``/``_ENCHANTMENT_CLASS_EXCEPTIONS`` mirror
``conformance/idmap.py``'s exceptions-dict shape (small, evidence-based); only
the enchantment table is non-empty today, so a future divergent id has
somewhere to go without restructuring this module.
"""
from __future__ import annotations

import re

_POWER_CLASS_EXCEPTIONS: dict[str, str] = {}
_MONSTER_CLASS_EXCEPTIONS: dict[str, str] = {}
_AFFLICTION_CLASS_EXCEPTIONS: dict[str, str] = {}
# "souls" -> Core/Models/Enchantments/SoulsPower.cs's `class SoulsPower :
# EnchantmentModel` -- the game's own concrete class carries a "Power" suffix
# unlike every other ported enchantment (PascalCase(sim_id) verbatim).
_ENCHANTMENT_CLASS_EXCEPTIONS: dict[str, str] = {"souls": "SoulsPower"}

# Vocab monster ids with no concrete decompiled MonsterModel subclass at
# all -- these are sim-internal abstract base classes that
# ``full_env._monster_classes()``'s ``Monster.__subclasses__()`` walk
# surfaces (because Python subclass discovery can't distinguish "abstract
# base used by several monster families" from "a real monster"), not real
# game content:
#   - MachineMonster (sts2_rl/monsters/state_machine.py:449) -- the shared
#     state-machine base every Glory-act machine monster inherits.
#   - _BattleFriend (sts2_rl/monsters/glory/battle_friend.py) -- shared base
#     for BattleFriendV1/V2/V3.
#   - _Cultist (sts2_rl/monsters/underdocks/cultists.py) -- shared base for
#     DampCultist/CalcifiedCultist.
# No POWER.*/MONSTER.* game id exists for these; report as unmapped, do not
# guess one.
MONSTERS_WITHOUT_GAME_CLASS: frozenset[str] = frozenset({
    "MachineMonster", "_BattleFriend", "_Cultist",
})


def _slugify(class_name: str) -> str:
    """Port of ``StringHelper.Slugify`` (``Core/Helpers/StringHelper.cs:69-
    79``): insert ``_`` before every uppercase letter preceded by an
    alphanumeric char, upper-case the result, then strip anything outside
    ``[A-Z0-9_]``."""
    out: list[str] = []
    for i, ch in enumerate(class_name):
        if ch.isupper() and i > 0 and class_name[i - 1].isalnum():
            out.append("_")
        out.append(ch)
    s = re.sub(r"\s+", "_", "".join(out).strip().upper())
    return re.sub(r"[^A-Z0-9_]", "", s)


def _pascal(snake_id: str) -> str:
    """Inverse of the snake_case vocab convention: ``one_two_punch`` ->
    ``OneTwoPunch``. Round-trips through ``_slugify`` for every id in
    vocab.json today (Task A verification script)."""
    return "".join(word.capitalize() for word in snake_id.split("_"))


def _power_class_name(sim_id: str) -> str:
    return _POWER_CLASS_EXCEPTIONS.get(sim_id, _pascal(sim_id) + "Power")


def _monster_class_name(sim_id: str) -> str:
    return _MONSTER_CLASS_EXCEPTIONS.get(sim_id, sim_id)


def _affliction_class_name(sim_id: str) -> str:
    return _AFFLICTION_CLASS_EXCEPTIONS.get(sim_id, _pascal(sim_id))


def _enchantment_class_name(sim_id: str) -> str:
    return _ENCHANTMENT_CLASS_EXCEPTIONS.get(sim_id, _pascal(sim_id))


def power_game_id(sim_id: str) -> str:
    """``sim_id`` (a ``full_env.POWER_INDEX`` key) -> its ``POWER.X``
    decompiled-game id."""
    return f"POWER.{_slugify(_power_class_name(sim_id))}"


def monster_game_id(sim_id: str) -> str | None:
    """``sim_id`` (a ``full_env.MONSTER_INDEX`` key) -> its ``MONSTER.X``
    decompiled-game id, or ``None`` if ``sim_id`` has no game-source class
    (see ``MONSTERS_WITHOUT_GAME_CLASS``)."""
    if sim_id in MONSTERS_WITHOUT_GAME_CLASS:
        return None
    return f"MONSTER.{_slugify(_monster_class_name(sim_id))}"


def affliction_game_id(sim_id: str) -> str:
    """``sim_id`` (an ``afflictions.AFFLICTION_INDEX`` key) -> its
    ``AFFLICTION.X`` decompiled-game id."""
    return f"AFFLICTION.{_slugify(_affliction_class_name(sim_id))}"


def enchantment_game_id(sim_id: str) -> str:
    """``sim_id`` (an ``enchantments.ENCHANTMENT_INDEX`` key) -> its
    ``ENCHANTMENT.X`` decompiled-game id."""
    return f"ENCHANTMENT.{_slugify(_enchantment_class_name(sim_id))}"


def sim_power_id(game_id: str) -> str | None:
    """Inverse of ``power_game_id``: ``POWER.X`` -> the sim's snake_case
    power id, or ``None`` if unrecognized."""
    from .. import full_env
    entry = game_id.split(".", 1)[-1]
    if not entry.endswith("_POWER"):
        return None
    sim_id = entry[: -len("_POWER")].lower()
    return sim_id if sim_id in full_env.POWER_INDEX else None


def sim_monster_id(game_id: str) -> str | None:
    """Inverse of ``monster_game_id``: ``MONSTER.X`` -> the sim's PascalCase
    monster class id, or ``None`` if unrecognized."""
    from .. import full_env
    entry = game_id.split(".", 1)[-1]
    sim_id = _pascal(entry.lower())
    return sim_id if sim_id in full_env.MONSTER_INDEX else None


def sim_affliction_id(game_id: str) -> str | None:
    """Inverse of ``affliction_game_id``: ``AFFLICTION.X`` -> the sim's
    snake_case affliction id, or ``None`` if unrecognized.

    Unlike ``sim_monster_id``, no ``_pascal()`` round-trip is needed: every
    ported affliction id's slugified PascalCase form re-inserts underscores
    at exactly the original snake_case boundaries (e.g. ``ringing`` ->
    ``Ringing`` -> ``RINGING``), so ``entry.lower()`` already recovers the
    sim id directly. ``_AFFLICTION_CLASS_EXCEPTIONS`` is empty today, but is
    still consulted first so a future exception doesn't require touching
    this function."""
    from .. import afflictions
    entry = game_id.split(".", 1)[-1]
    for exc_sim_id, cls_name in _AFFLICTION_CLASS_EXCEPTIONS.items():
        if _slugify(cls_name) == entry:
            return exc_sim_id if exc_sim_id in afflictions.AFFLICTION_INDEX \
                else None
    sim_id = entry.lower()
    return sim_id if sim_id in afflictions.AFFLICTION_INDEX else None


def sim_enchantment_id(game_id: str) -> str | None:
    """Inverse of ``enchantment_game_id``: ``ENCHANTMENT.X`` -> the sim's
    snake_case enchantment id, or ``None`` if unrecognized. Checks
    ``_ENCHANTMENT_CLASS_EXCEPTIONS`` first (``SOULS_POWER`` -> ``souls``),
    same shape as ``entry.lower()`` recovering every non-exception id
    directly (see ``sim_affliction_id``)."""
    from .. import enchantments
    entry = game_id.split(".", 1)[-1]
    for exc_sim_id, cls_name in _ENCHANTMENT_CLASS_EXCEPTIONS.items():
        if _slugify(cls_name) == entry:
            return exc_sim_id if exc_sim_id in enchantments.ENCHANTMENT_INDEX \
                else None
    sim_id = entry.lower()
    return sim_id if sim_id in enchantments.ENCHANTMENT_INDEX else None


def power_game_id_map(index: dict[str, int]) -> dict[str, int]:
    """``{"POWER.X": oid}`` for every ``sim_id`` in ``index``
    (``full_env.POWER_INDEX``)."""
    from ..obs import oid
    return {power_game_id(sim_id): oid(idx) for sim_id, idx in index.items()}


def monster_game_id_map(index: dict[str, int]) -> dict[str, int]:
    """``{"MONSTER.X": oid}`` for every ``sim_id`` in ``index``
    (``full_env.MONSTER_INDEX``) that has a game-source class."""
    from ..obs import oid
    out: dict[str, int] = {}
    for sim_id, idx in index.items():
        game_id = monster_game_id(sim_id)
        if game_id is not None:
            out[game_id] = oid(idx)
    return out


def affliction_game_id_map(index: dict[str, int]) -> dict[str, int]:
    """``{"AFFLICTION.X": oid}`` for every ``sim_id`` in ``index``
    (``afflictions.AFFLICTION_INDEX``)."""
    from ..obs import oid
    return {
        affliction_game_id(sim_id): oid(idx) for sim_id, idx in index.items()
    }


def enchantment_game_id_map(index: dict[str, int]) -> dict[str, int]:
    """``{"ENCHANTMENT.X": oid}`` for every ``sim_id`` in ``index``
    (``enchantments.ENCHANTMENT_INDEX``)."""
    from ..obs import oid
    return {
        enchantment_game_id(sim_id): oid(idx) for sim_id, idx in index.items()
    }
