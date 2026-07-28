"""Pool-wide shape sweeps for the `potion` content tier.

The relic tier's `relic_probes.py` is the template (PROMPT.md, "Sweep the shape
before you audit the units"): every number an audit record states should be
re-derivable by running a committed script, and a shape that repeats across the
roster should be found once rather than fifteen units at a time.

Two rules from that tier's write-up are honoured here deliberately:

* **A sweep may escalate a candidate; it may never clear one.** Every bucket
  below is a *work list*, never a safety claim. Where a bucket cannot be decided
  mechanically the probe prints ``INCONCLUSIVE`` rather than agreement.
* **Diff the observable, not just the object.** ``sweep-attrs`` compares the C#
  declarations against the sim *attributes the sim actually reads* (the shop
  price, the reward pool, the action mask, the target resolver), and names the
  reader for each.

Probes:

  sweep-attrs        Rarity / Usage / TargetType / CanBeGeneratedInCombat from
                     each C# model vs the sim class's rarity / automatic /
                     targeted / in_reward_pool.
  sweep-usage        The Usage census: which potions the game lets you drink
                     outside combat, against the sim's single combat-only path.
  sweep-onuse        Per unit, the C# OnUse body lines and the sim `use` body
                     lines side by side (the read list for a batch).
  sweep-overrides    Every `public override` each C# potion declares, plus the
                     ones it inherits, so a batch can see its enumeration
                     before generating skeletons.
  sweep-hooks        Which potions override an AbstractModel hook (i.e. are
                     hook listeners while they sit in the belt) on each side.
  sweep-vars         CanonicalVars numeric constants from the C# vs the sim
                     class's numeric class attributes.

Run: py audit/tools/potion_probes.py [probe]   (no arg = every probe)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

sys.path.insert(0, str(_HERE.parent))
import harness  # noqa: E402

GAME_ROOT = harness.DEFAULT_GAME_ROOT
POTION_DIR = GAME_ROOT / "src/Core/Models/Potions"


def _rows() -> list[dict]:
    return harness.roster("potion", GAME_ROOT)


def _cs(row: dict) -> str:
    return (GAME_ROOT / row["game_path"]).read_text(
        encoding="utf-8-sig", errors="replace")


def _one(text: str, pat: str) -> str:
    m = re.search(pat, text)
    return m.group(1) if m else "-"


def _sim_classes() -> dict:
    from sts2_rl.potions import ALL_POTIONS
    return dict(ALL_POTIONS)


# ── sweep-attrs ───────────────────────────────────────────────────────────
def sweep_attrs() -> None:
    """C# Rarity/Usage/TargetType/CanBeGeneratedInCombat vs the sim attrs.

    Sim readers, so a mismatch is an observable rather than a field diff:
      rarity          -> shop.MerchantPotionEntry price + potion_pools bucket
      in_reward_pool  -> potions.random_potion's pool filter
      automatic       -> combat.CombatState.use_potion's reject + the env mask
      targeted        -> combat.CombatState.use_potion's target resolution
    """
    from sts2_rl.potion_pools import NOT_GENERATED_IN_COMBAT, _POOL_RARITY

    sim = _sim_classes()
    print(f"{'unit':26} {'C# rarity':10} {'sim':10} {'C# usage':11} "
          f"{'auto':5} {'C# target':16} {'tgtd':5} {'genC':5} {'pool':5}")
    bad = []
    for row in _rows():
        uid = row["unit"].split("/", 1)[1]
        text = _cs(row)
        rarity = _one(text, r"override PotionRarity Rarity => PotionRarity\.(\w+)")
        usage = _one(text, r"override PotionUsage Usage => PotionUsage\.(\w+)")
        target = _one(text, r"override TargetType TargetType => TargetType\.(\w+)")
        gen = "false" if re.search(
            r"override bool CanBeGeneratedInCombat => false", text) else "true"
        cls = sim[uid]
        srar = getattr(cls, "rarity", "-")
        auto = getattr(cls, "automatic", False)
        tgtd = getattr(cls, "targeted", False)
        pool = getattr(cls, "in_reward_pool", True)
        simgen = "false" if uid in NOT_GENERATED_IN_COMBAT else "true"
        print(f"{uid:26} {rarity:10} {srar:10} {usage:11} {str(auto):5} "
              f"{target:16} {str(tgtd):5} {gen}/{simgen:4} "
              f"{str(pool)}/{str(uid in _POOL_RARITY):5}")
        if rarity.lower() != str(srar).lower():
            bad.append(f"{uid}: rarity {rarity} vs {srar}")
        if (usage == "Automatic") != bool(auto):
            bad.append(f"{uid}: Usage {usage} vs automatic={auto}")
        if (target == "AnyEnemy") != bool(tgtd):
            bad.append(f"{uid}: TargetType {target} vs targeted={tgtd}")
        if gen != simgen:
            bad.append(f"{uid}: CanBeGeneratedInCombat {gen} vs {simgen}")
        if (uid in _POOL_RARITY) != bool(pool):
            bad.append(f"{uid}: in_reward_pool {pool} vs pool membership "
                       f"{uid in _POOL_RARITY}")
    print()
    for b in bad:
        print("MISMATCH", b)
    print(f"{len(bad)} attribute mismatch(es)")
    print("NOTE: agreement here is NOT a clear -- TargetType has five values "
          "and the sim models one boolean, so AllEnemies/Self/AnyPlayer all "
          "read `targeted=False`. See sweep-usage.")


# ── sweep-usage ───────────────────────────────────────────────────────────
def sweep_usage() -> None:
    """The Usage census. `PotionUsage.AnyTime` means the game's Use button is
    live outside combat; the sim's only `use_potion` is CombatState's."""
    buckets: dict[str, list[str]] = {}
    for row in _rows():
        uid = row["unit"].split("/", 1)[1]
        usage = _one(_cs(row), r"override PotionUsage Usage => PotionUsage\.(\w+)")
        buckets.setdefault(usage, []).append(uid)
    for usage, ids in sorted(buckets.items()):
        print(f"{usage} ({len(ids)}): {', '.join(sorted(ids))}")
    print()
    sites = []
    for p in sorted((_REPO / "sts2_rl").rglob("*.py")):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\bdef use_potion\b", line):
                sites.append(f"{p.relative_to(_REPO)}:{i}")
    print("sim `def use_potion` definitions:", sites or "NONE")
    print("=> every AnyTime potion's out-of-combat arm has no sim path at all")


# ── sweep-onuse ───────────────────────────────────────────────────────────
def _cs_onuse(text: str) -> list[str]:
    out, depth, started = [], 0, False
    for line in text.splitlines():
        if not started and re.search(r"(protected|public).*Task OnUse\(", line):
            started = True
            continue
        if started:
            depth += line.count("{") - line.count("}")
            s = line.strip()
            if s and s not in ("{",):
                out.append(s)
            if depth <= 0 and out:
                break
    return out


def sweep_onuse() -> None:
    import inspect
    sim = _sim_classes()
    for row in _rows():
        uid = row["unit"].split("/", 1)[1]
        print(f"===== {uid} ({row['game_path']}) =====")
        for line in _cs_onuse(_cs(row)) or ["(no OnUse override)"]:
            print("  C# |", line)
        try:
            src, start = inspect.getsourcelines(sim[uid].use)
            for n, line in enumerate(src, start):
                print(f"  py |{n:5}| {line.rstrip()}")
        except (TypeError, OSError):
            print("  py | (inherits Potion.use)")


# ── sweep-overrides ───────────────────────────────────────────────────────
def sweep_overrides() -> None:
    for row in _rows():
        uid = row["unit"].split("/", 1)[1]
        gp = GAME_ROOT / row["game_path"]
        declared, inherited = harness.split_overrides(_cs(row), GAME_ROOT, gp)
        extra = re.findall(
            r"protected override [\w<>,.?\[\]() ]+? (\w+)", _cs(row))
        print(f"{uid:26} public={declared} protected={sorted(set(extra))} "
              f"inherited={inherited}")


# ── sweep-hooks ───────────────────────────────────────────────────────────
_ABSTRACT_HOOKS: set[str] | None = None


def _abstract_hooks() -> set[str]:
    global _ABSTRACT_HOOKS
    if _ABSTRACT_HOOKS is None:
        text = (GAME_ROOT / "src/Core/Models/AbstractModel.cs").read_text(
            encoding="utf-8-sig", errors="replace")
        _ABSTRACT_HOOKS = set(re.findall(
            r"public virtual [\w<>,.?\[\]() ]+? (\w+)\s*\(", text))
    return _ABSTRACT_HOOKS


def sweep_hooks() -> None:
    """Which potions listen to hooks while they sit in the belt.

    A potion is a hook listener on BOTH sides for its whole time in the belt
    (CombatState.IterateHookListeners walks PotionSlots; the sim registers each
    held potion in combat.py / player.add_potion), so an override here is
    behaviour the potion has WITHOUT being drunk."""
    hooks = _abstract_hooks()
    sim = _sim_classes()
    sim_hook_names = _sim_hook_names()
    print("C# potions overriding an AbstractModel hook:")
    for row in _rows():
        uid = row["unit"].split("/", 1)[1]
        gp = GAME_ROOT / row["game_path"]
        declared, _ = harness.split_overrides(_cs(row), GAME_ROOT, gp)
        got = [d for d in declared if d in hooks]
        got += [m for m in re.findall(
            r"(?:protected|public) override [\w<>,.?\[\]() ]+? (\w+)", _cs(row))
            if m in hooks and m not in got]
        if got:
            print(f"  {uid:26} {got}")
    print("sim potions defining a hook-listener method:")
    for uid, cls in sorted(sim.items()):
        got = sorted(n for n in vars(cls) if n in sim_hook_names)
        if got:
            print(f"  {uid:26} {got}")


def _sim_hook_names() -> set[str]:
    from sts2_rl.hooks import HookSystem
    return {n for n in vars(HookSystem) if not n.startswith("_")}


# ── sweep-vars ────────────────────────────────────────────────────────────
def sweep_vars() -> None:
    """C# CanonicalVars numerics vs the sim class's numeric class attrs.

    INCONCLUSIVE by construction: the C# var names (BlockVar, CardsVar,
    PowerVar<T>, DynamicVar("HealPercent")) do not line up with the sim's
    constant names, and several potions carry a display-only var. It is a read
    list, not a check."""
    sim = _sim_classes()
    for row in _rows():
        uid = row["unit"].split("/", 1)[1]
        text = _cs(row)
        nums = re.findall(
            r"new (\w+(?:<\w+>)?)\(\s*([\d.]+)m?", text)
        simnums = {k: v for k, v in vars(sim[uid]).items()
                   if k.isupper() and isinstance(v, (int, float))}
        print(f"{uid:26} C#={nums} sim={simnums}")
        if re.search(r"GetValueIfAscension", text):
            print(f"{'':26} !! ascension branch present -- take the LAST arg")


# ── aoe-power ─────────────────────────────────────────────────────────────
def aoe_power() -> None:
    """EXECUTED witness for the AoE-POWER target-set gap.

    `CombatState.HittableEnemies` is `Enemies.Where(IsHittable)` and IsHittable
    consults `Hook.ShouldAllowHitting`; the sim's AoE potions filter on
    `not is_gone` and `PowerCmd.apply` has no `CanReceivePowers` guard
    (audit/records/seam/power_cmd.json G6). A creature mid-Illusion-revival is
    the concrete case: alive at 1 HP, so `not is_gone`, but refused by
    should_allow_hitting.

    Prints the sim's post-use enemy powers next to the C# target list the same
    state would produce. Does not clear anything: the DAMAGE potions are shown
    alongside precisely because they are the arm where the sim's own
    DamageCmd.deal applies the predicate and the gap does not bite.
    """
    import random

    from sts2_rl.cards import make_card
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters import Encounter
    from sts2_rl.monsters.overgrowth.fogmog import EyeWithTeeth
    from sts2_rl.potions import (
        ExplosiveAmpoule, PotionOfBinding, ShacklingPotion,
    )

    # EyeWithTeeth is the Illusion carrier -- Fogmog SUMMONS it
    # (monsters/overgrowth/fogmog.py:95); Parafright is the Hive twin.
    for potion_cls in (PotionOfBinding, ShacklingPotion, ExplosiveAmpoule):
        cs = CombatState(
            starting_deck=[make_card("strike") for _ in range(5)],
            rng=random.Random(0),
            encounter=Encounter("probe_illusion", [EyeWithTeeth]),
        )
        enemy = cs.enemies[0]
        illusion = enemy.powers.get("illusion")
        if illusion is None:
            print(f"{potion_cls.__name__}: INCONCLUSIVE -- no illusion power on "
                  f"{enemy}; the monster's setup changed")
            continue
        # The state the C# calls un-hittable: alive, mid-revival.
        enemy.hp = 1
        illusion.is_reviving = True
        hittable_cs = cs.hooks.should_allow_hitting(enemy)
        sim_targets = [e for e in cs.enemies if not e.is_gone]
        before = dict(
            (pid, p.amount) for pid, p in enemy.powers.items())
        hp_before = enemy.hp
        potion_cls().use(cs._ctx())
        after = dict((pid, p.amount) for pid, p in enemy.powers.items())
        landed = {k: v for k, v in after.items() if before.get(k) != v}
        print(f"{potion_cls.__name__}:")
        print(f"  should_allow_hitting(enemy) = {hittable_cs}  "
              f"=> C# HittableEnemies = []  |  sim filter kept "
              f"{len(sim_targets)} enemy(ies)")
        print(f"  sim powers changed by the use: {landed or '{}'}   "
              f"hp {hp_before} -> {enemy.hp}")


# ── touch-of-insanity ─────────────────────────────────────────────────────
def touch_of_insanity() -> None:
    """EXECUTED witness for Touch of Insanity's candidate filter.

    `TouchOfInsanity.cs:22` filters the hand with
    `c.CostsEnergyOrStars(includeGlobalModifiers: false) ||
     c.CostsEnergyOrStars(includeGlobalModifiers: true)`
    -- an OR over CostModifiers.Local and CostModifiers.All
    (CardModel.cs:1578-1595). The sim tests `c.energy_cost > 0`
    (potions.py:166-169), and `Card.energy_cost` (cards/base.py:222-232) is the
    LOCAL cost only: no hook-driven global modifier reaches it.

    So the divergence needs a card whose local cost is 0 and whose global cost
    is above 0 -- i.e. a locally-freed card under a cost-RAISING global
    modifier. Spiked Gauntlets is one (`modify_card_energy_cost` +1 on Power
    cards, relics/spiked_gauntlets.py:26-31).
    """
    import random

    from sts2_rl.cards import make_card
    from sts2_rl.combat import CombatState
    from sts2_rl.relics import ALL_RELICS

    gauntlets = ALL_RELICS.get("spiked_gauntlets")
    if gauntlets is None:
        print("INCONCLUSIVE -- spiked_gauntlets is not a registered relic")
        return
    power_card = None
    for cid in ("inflame", "metallicize", "demon_form", "feel_no_pain"):
        try:
            c = make_card(cid)
        except KeyError:
            continue
        if c.card_type.name == "POWER":
            power_card = cid
            break
    if power_card is None:
        print("INCONCLUSIVE -- no ported Power card found to build the witness")
        return

    cs = CombatState(
        starting_deck=[make_card("strike") for _ in range(5)],
        rng=random.Random(0),
        relics=[gauntlets()],
    )
    card = make_card(power_card)
    card.set_free_this_turn()          # a locally-freed card, e.g. from Power Potion
    cs.player.hand = [card]
    local = card.energy_cost
    withglobal = cs.hooks.modify_energy_cost(card, local) \
        if hasattr(cs.hooks, "modify_energy_cost") else None
    if withglobal is None:
        for name in dir(cs.hooks):
            if "energy_cost" in name and not name.startswith("_"):
                withglobal = getattr(cs.hooks, name)(card, local)
                break
    sim_candidates = [
        c for c in cs.player.hand
        if not getattr(c, "energy_cost_x", False) and c.energy_cost > 0
    ]
    print(f"card {power_card!r} (Power), set_free_this_turn, with Spiked "
          f"Gauntlets held")
    print(f"  local cost (Card.energy_cost)          = {local}")
    print(f"  cost with the global modifier applied  = {withglobal}")
    print(f"  C#  CostsEnergyOrStars(false)={local > 0}  "
          f"CostsEnergyOrStars(true)={bool(withglobal and withglobal > 0)}  "
          f"=> offered = {local > 0 or bool(withglobal and withglobal > 0)}")
    print(f"  sim candidate list = {sim_candidates}  "
          f"=> offered = {bool(sim_candidates)}")


# ── pin-append ────────────────────────────────────────────────────────────
def pin_append() -> None:
    """Justify the re-pin of the records staled by appending pins.

    Adding `TestPotionContentPins` to `test/test_hook_order.py` changes that
    file's hash, and nine card/relic records hash it through `extra_sources`
    because they cite a pin's `file:line`. `audit/README.md` is explicit that a
    stale record needs a re-audit by an agent and not a regenerated hash — so
    the re-audit question here is exactly: *did anything those nine records
    cite actually change?*

    This probe answers it mechanically, so the answer is reproducible rather
    than asserted:

      1. the pre-pin file is a strict PREFIX of the post-pin file (append only);
      2. every `test/test_hook_order.py:N` any record cites is inside that
         prefix and its line CONTENT is unchanged.

    Both true ⇒ every verdict resting on those citations still holds and
    `harness.py rehash` is the sanctioned last step. Either false ⇒ a real
    re-audit is owed and the probe says so.
    """
    import hashlib
    import subprocess

    pin_file = _REPO / "test" / "test_hook_order.py"
    rel = "test/test_hook_order.py"

    def blob(ref: str) -> str | None:
        p = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=_REPO,
                           capture_output=True)
        return p.stdout.decode("utf-8") if p.returncode == 0 else None

    def sha(text: str) -> str:
        return hashlib.sha256(
            text.replace("\r\n", "\n").encode("utf-8")).hexdigest()

    # The baseline is whatever hash the stale records still carry.
    stored: set[str] = set()
    citing: dict[str, set[int]] = {}
    for path in sorted((_REPO / "audit" / "records").rglob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        for src in rec.get("extra_sources") or []:
            if str(src.get("path", "")).replace("\\", "/").endswith(rel):
                stored.add(src["sha256"])
        blobtext = json.dumps(rec)
        lines = {int(m) for m in re.findall(
            r"test[/\\]test_hook_order\.py:(\d+)", blobtext)}
        for lo, hi in re.findall(
                r"test[/\\]test_hook_order\.py:(\d+)-(\d+)", blobtext):
            lines |= set(range(int(lo), int(hi) + 1))
        if lines:
            citing[rec["unit"]] = lines

    current = pin_file.read_text(encoding="utf-8")
    cur_sha = sha(current)
    print(f"records hashing {rel}: {len(stored)} distinct sha256 stored")
    for s in sorted(stored):
        print(f"  stored {s[:16]}  {'== current' if s == cur_sha else '!= current (STALE)'}")
    print(f"current  {cur_sha[:16]}  ({len(current.splitlines())} lines)")

    # Find the committed revision matching the stored hash.
    baseline = None
    for ref in ("audit-pipeline", "main", "HEAD~5", "HEAD~4", "HEAD~3"):
        t = blob(ref)
        if t is not None and sha(t) in stored:
            baseline = (ref, t)
            break
    if baseline is None:
        print("INCONCLUSIVE -- no reachable revision of the pin file matches the "
              "hash the records store; a real re-audit is owed")
        return
    ref, old = baseline
    old_lines, new_lines = old.splitlines(), current.splitlines()
    append_only = old_lines == new_lines[: len(old_lines)]
    print(f"baseline revision: {ref} ({len(old_lines)} lines)")
    print(f"(1) append-only (old is a strict prefix of new): {append_only}")

    moved = []
    for unit, lines in sorted(citing.items()):
        for n in sorted(lines):
            if n > len(old_lines) or old_lines[n - 1] != new_lines[n - 1]:
                moved.append(f"{unit} cites :{n}")
    print(f"(2) cited lines whose content changed: {len(moved)}")
    for m in moved:
        print(f"    {m}")
    print(f"    (checked {sum(len(v) for v in citing.values())} citations "
          f"across {len(citing)} records)")
    if append_only and not moved:
        print("VERDICT: no cited line moved or changed -- every verdict resting "
              "on this file still holds, so `py audit/tools/harness.py rehash "
              "<unit>...` is the sanctioned last step of the re-audit.")
    else:
        print("VERDICT: a cited line moved or changed -- REHASH IS NOT ENOUGH, "
              "those records need a real re-audit.")


PROBES = {
    "aoe-power": aoe_power,
    "touch-of-insanity": touch_of_insanity,
    "pin-append": pin_append,
    "sweep-attrs": sweep_attrs,
    "sweep-usage": sweep_usage,
    "sweep-onuse": sweep_onuse,
    "sweep-overrides": sweep_overrides,
    "sweep-hooks": sweep_hooks,
    "sweep-vars": sweep_vars,
}


def main(argv: list[str]) -> int:
    names = argv[1:] or [n for n in PROBES if n != "sweep-onuse"]
    for name in names:
        if name not in PROBES:
            print(f"unknown probe {name!r}; have {sorted(PROBES)}")
            return 2
        print(f"\n########## {name} ##########")
        PROBES[name]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
