# Rest-Site Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port Girya (Lift), Shovel (Dig), Eternal Feather (passive heal), Byrdonis Egg's Hatch (+ the Byrdpip relic and ByrdSwoop card it requires), and Miniature Tent (multi-action rest visits) — closing every rest-site fidelity gap identified against the decompiled source.

**Architecture:** Rest-site actions are already fully generic in the RL action space — any option a relic (and, after this plan, a card) appends via `modify_rest_site_options(run, options)` becomes action index 3+ in `DecisionRequest.legal_actions()` for `DecisionKind.REST`, with zero action-space or observation changes. This plan (a) lets cards use that hook too (needed for Byrdonis Egg), (b) fills in four relics that already had the hook available but were documented no-op stubs, and (c) changes `driver.py`'s `_run_rest()` from a single-shot ask to a loop, needed only for Miniature Tent (a rest-site visit may take more than one action).

**Tech Stack:** Python 3.12, pytest.

## Global Constraints

- Fidelity to the decompiled game source (`c:\Users\Perry\Desktop\Slay the Spire 2\src`) is authoritative — cited file:line references below are from that source tree.
- Follow existing sts2_rl conventions exactly: relic/card modules under `sts2_rl/relics/` and `sts2_rl/cards/`, `@register_relic`/`@register_card` decorators, `RelicRarity`/`CardRarity` enums, docstrings citing the source `.cs` file.
- Every new id (`byrdpip`, `byrd_swoop`) is picked up automatically by `sts2_rl/vocab.py`'s append-on-import mechanism — do not hand-edit `vocab.json`.
- Do not commit — this repo already has unrelated uncommitted work in progress; leave changes staged/unstaged for the user to review.

---

### Task 1: Girya — LIFT rest-site option

**Files:**
- Modify: `sts2_rl/relics/girya.py`
- Test: `test/test_ancients.py`

**Interfaces:**
- Consumes: `RestSiteOption` (from `.base`, already defined at `sts2_rl/relics/base.py:64-76`), `RunState.rest_site_options()` (already iterates `self.relics` calling `modify_rest_site_options`).
- Produces: nothing new consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Append to `test/test_ancients.py` (end of file, after `test_jeweled_mask_free_power_turn_one`):

```python


def test_girya_lift_option():
    run = fresh_run(53)
    run.add_relic("girya")
    girya = run.relics[0]
    for expected in (1, 2, 3):
        options = run.rest_site_options()
        assert [o.key for o in options] == ["LIFT"]
        options[0].on_select(run)
        assert girya.times_lifted == expected
    # Maxed out at 3 lifts: the option disappears.
    assert run.rest_site_options() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest test/test_ancients.py::test_girya_lift_option -v`
Expected: FAIL — `run.rest_site_options()` returns `[]` (Girya doesn't add anything yet).

- [ ] **Step 3: Implement**

Replace the full contents of `sts2_rl/relics/girya.py`:

```python
from __future__ import annotations

from .base import Relic, RelicRarity, RestSiteOption, register_relic


@register_relic
class Girya(Relic):
    """Girya.cs — start each combat with Strength equal to the times lifted
    at rest sites (0-3, via the LIFT rest-site option: LiftRestSiteOption
    just increments TimesLifted)."""

    id = "girya"
    name = "Girya"
    rarity = RelicRarity.RARE

    MAX_LIFTS = 3

    def __init__(self, times_lifted: int = 0) -> None:
        super().__init__()
        self.times_lifted = min(times_lifted, self.MAX_LIFTS)

    def on_combat_start(self) -> None:
        if self.times_lifted > 0:
            from ..cmds import PowerCmd
            from ..powers import StrengthPower
            PowerCmd.apply(
                self.hooks, self.player, StrengthPower, self.times_lifted,
                applier=self.player,
            )

    def modify_rest_site_options(self, run, options) -> None:
        if self.times_lifted >= self.MAX_LIFTS:
            return
        options.append(RestSiteOption("LIFT", lambda run: self._lift()))

    def _lift(self) -> None:
        self.times_lifted += 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest test/test_ancients.py::test_girya_lift_option -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sts2_rl/relics/girya.py test/test_ancients.py
git commit -m "feat: Girya's LIFT rest-site option"
```

---

### Task 2: Shovel — DIG rest-site option

**Files:**
- Modify: `sts2_rl/relics/shovel.py`
- Test: `test/test_ancients.py`

**Interfaces:**
- Consumes: `RestSiteOption` (from `.base`), `RunState.has_available_relics()` and `RunState.obtain_relic_from_grab_bag()` (already exist at `sts2_rl/run.py:383-385` and `:447-452`, used today by treasure rooms).
- Produces: nothing new consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Append to `test/test_ancients.py` (end of file):

```python


def test_shovel_dig_option():
    run = fresh_run(53)
    run.add_relic("shovel")
    bag_before = len(run.relic_grab_bag)
    relics_before = len(run.relics)
    options = run.rest_site_options()
    assert [o.key for o in options] == ["DIG"]
    options[0].on_select(run)
    assert len(run.relic_grab_bag) == bag_before - 1
    assert len(run.relics) == relics_before + 1
    # Empty bag: the option disappears.
    run.relic_grab_bag.clear()
    assert run.rest_site_options() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest test/test_ancients.py::test_shovel_dig_option -v`
Expected: FAIL — `run.rest_site_options()` returns `[]`.

- [ ] **Step 3: Implement**

Replace the full contents of `sts2_rl/relics/shovel.py`:

```python
from __future__ import annotations

from .base import Relic, RelicRarity, RestSiteOption, register_relic


@register_relic
class Shovel(Relic):
    """Shovel.cs — the DIG rest-site option: pull the next relic from the
    front of the grab bag (RelicFactory.PullNextRelicFromFront), the same
    mechanism a treasure chest uses. Only offered while the bag has a relic
    left."""

    id = "shovel"
    name = "Shovel"
    rarity = RelicRarity.RARE

    def modify_rest_site_options(self, run, options) -> None:
        if not run.has_available_relics():
            return
        options.append(
            RestSiteOption("DIG", lambda run: run.obtain_relic_from_grab_bag())
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest test/test_ancients.py::test_shovel_dig_option -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sts2_rl/relics/shovel.py test/test_ancients.py
git commit -m "feat: Shovel's DIG rest-site option"
```

---

### Task 3: Eternal Feather — passive heal on rest-site entry

**Files:**
- Modify: `sts2_rl/relics/eternal_feather.py`
- Test: `test/test_ancients.py`

**Interfaces:**
- Consumes: `Relic.after_room_entered(self, run, point, room_type)` (already-existing hook, `sts2_rl/relics/base.py:179-180`), `RoomType.REST_SITE` (`sts2_rl/rooms.py:47`, already imported at the top of `test/test_ancients.py`), `RunState.heal(amount)` (`sts2_rl/run.py:191-195`).
- Produces: nothing new consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Append to `test/test_ancients.py` (end of file):

```python


def test_eternal_feather_heals_on_rest_entry():
    run = fresh_run(53)
    run.add_relic("eternal_feather")
    run.hp = 40
    relic = run.relics[0]
    groups = len(run.deck) // 5
    relic.after_room_entered(run, None, RoomType.REST_SITE)
    assert run.hp == 40 + 3 * groups
    # Not a rest site: no heal.
    hp = run.hp
    relic.after_room_entered(run, None, RoomType.MONSTER)
    assert run.hp == hp
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest test/test_ancients.py::test_eternal_feather_heals_on_rest_entry -v`
Expected: FAIL — `run.hp` stays at 40 (the stub does nothing).

- [ ] **Step 3: Implement**

Replace the full contents of `sts2_rl/relics/eternal_feather.py`:

```python
from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class EternalFeather(Relic):
    """EternalFeather.cs — AfterRoomEntered: on entering a rest site, heal
    3 HP for every 5 cards in the deck (floor division), automatically, with
    no player choice involved (not a RestSiteOption)."""

    id = "eternal_feather"
    name = "Eternal Feather"
    rarity = RelicRarity.UNCOMMON

    CARDS_PER_HEAL = 5
    HEAL_PER_GROUP = 3

    def after_room_entered(self, run, point, room_type) -> None:
        from ..rooms import RoomType
        if room_type != RoomType.REST_SITE:
            return
        groups = len(run.deck) // self.CARDS_PER_HEAL
        if groups:
            run.heal(self.HEAL_PER_GROUP * groups)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest test/test_ancients.py::test_eternal_feather_heals_on_rest_entry -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sts2_rl/relics/eternal_feather.py test/test_ancients.py
git commit -m "feat: Eternal Feather's passive rest-site heal"
```

---

### Task 4: Card rest-site hook + Byrdpip relic + ByrdSwoop card + Byrdonis Egg's HATCH

**Files:**
- Create: `sts2_rl/rest_site.py`
- Create: `sts2_rl/relics/byrdpip.py`
- Modify: `sts2_rl/relics/base.py`
- Modify: `sts2_rl/cards/base.py`
- Modify: `sts2_rl/cards/event_cards.py`
- Modify: `sts2_rl/cards/__init__.py`
- Modify: `sts2_rl/run.py`
- Test: `test/test_events.py`

**Interfaces:**
- Produces: `RestSiteOption` now importable from `sts2_rl.rest_site` (relics/base.py re-exports it, so `from .base import RestSiteOption` inside `sts2_rl/relics/*.py` keeps working unchanged). `Card.modify_rest_site_options(self, run, options) -> None` (no-op default, overridden by `ByrdonisEggCard`). `RunState.rest_site_options()` now scans `self.deck` before `self.relics`. `run.transform_card(card, into=...)` and `run.add_relic(relic_id_or_instance)` (both pre-existing, `sts2_rl/run.py:298-330` and `:374-381`) are the only RunState methods this task's new code calls.

- [ ] **Step 1: Write the failing test**

Append to `test/test_events.py`, directly after `test_byrdonis_egg_is_unplayable_in_combat` (before the `# ── Dense Vegetation ──` section marker):

```python

def test_byrdonis_egg_hatch_grants_byrdpip_and_transforms_egg():
    run = fresh_run()
    event = make_event("byrdonis_nest", run).begin()
    event.choose("TAKE")
    options = run.rest_site_options()
    assert [o.key for o in options] == ["HATCH"]
    options[0].on_select(run)
    assert any(r.id == "byrdpip" for r in run.relics)
    assert not any(c.id == "byrdonis_egg" for c in run.deck)
    assert any(c.id == "byrd_swoop" for c in run.deck)
    # The egg is gone, so Hatch no longer appears.
    assert run.rest_site_options() == []


def test_byrd_swoop_deals_damage():
    deck = [make_card("byrd_swoop") for _ in range(5)]
    combat = CombatState(starting_deck=deck, rng=random.Random(0))
    enemy = combat.enemy
    hp_before = enemy.hp
    combat.play_card(0)
    assert enemy.hp == hp_before - 14
    swoop = make_card("byrd_swoop")
    swoop.upgrade()
    assert swoop._damage == 18
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest test/test_events.py::test_byrdonis_egg_hatch_grants_byrdpip_and_transforms_egg test/test_events.py::test_byrd_swoop_deals_damage -v`
Expected: FAIL — `test_byrd_swoop_deals_damage` fails with a `KeyError`/lookup failure (`byrd_swoop` isn't registered), and the Hatch test fails because `run.rest_site_options()` is `[]` (no card hook exists yet).

- [ ] **Step 3a: Create the shared `RestSiteOption` module**

Create `sts2_rl/rest_site.py`:

```python
"""RestSiteOption — an extra rest-site action contributed by a card or relic
(mirrors STS2's Entities.RestSite.RestSiteOption / the AbstractModel hook
Hook.TryModifyRestSiteOptions, which iterates deck cards then relics —
IterateHookListeners). Shared by cards/base.py and relics/base.py;
relics/base.py re-exports it so existing `from .base import RestSiteOption`
imports across the relics package keep working unchanged.
"""
from __future__ import annotations


class RestSiteOption:
    """`key` mirrors the source's OptionId; `on_select(run)` performs the
    effect (RestSiteOption.OnSelect)."""

    def __init__(self, key: str, on_select) -> None:
        self.key = key
        self.on_select = on_select

    def __repr__(self) -> str:
        return f"RestSiteOption({self.key})"
```

- [ ] **Step 3b: Re-point `relics/base.py` at the shared module**

In `sts2_rl/relics/base.py`, change the top import block from:

```python
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from ..valueprops import ValueProp
```

to:

```python
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from ..rest_site import RestSiteOption
from ..valueprops import ValueProp
```

Then delete the now-duplicate class definition (it currently sits between the `_MERCHANT_COST_BY_RARITY` dict and `_RELIC_CLASSES`):

```python
class RestSiteOption:
    """An extra rest-site action provided by a relic (mirrors RestSiteOption /
    Hook.TryModifyRestSiteOptions — Pael's Growth's Clone, Pumpkin Candle's
    Kindle, Meat Cleaver's Cook). `key` mirrors the source's OptionId;
    `on_select(run)` performs the effect (RestSiteOption.OnSelect)."""

    def __init__(self, key: str, on_select) -> None:
        self.key = key
        self.on_select = on_select

    def __repr__(self) -> str:
        return f"RestSiteOption({self.key})"


_RELIC_CLASSES: dict[str, type[Relic]] = {}
```

so only this remains in its place:

```python
_RELIC_CLASSES: dict[str, type[Relic]] = {}
```

Also update the `modify_rest_site_options` docstring further down in the same file (it currently reads "Pael's Growth's Clone, Pumpkin Candle's Kindle, Meat Cleaver's Cook"):

```python
    def modify_rest_site_options(self, run, options: "list[RestSiteOption]") -> None:
        """RelicModel.TryModifyRestSiteOptions — append extra rest-site
        actions (Pael's Growth's Clone, Pumpkin Candle's Kindle, Meat
        Cleaver's Cook, Shovel's Dig, Girya's Lift). The driver surfaces
        them after Heal/Smith/Leave."""
```

- [ ] **Step 3c: Add the Card hook**

In `sts2_rl/cards/base.py`, add to the `TYPE_CHECKING` block:

```python
if TYPE_CHECKING:
    from ..afflictions import Affliction
    from ..combat import CombatCtx
    from ..rest_site import RestSiteOption
```

Then add a new hook method, right before `def __repr__` at the end of the `Card` class:

```python
    # ── Run-level rest-site hook (mirrors Relic.modify_rest_site_options) ──
    # A deck-resident quest card can add a rest-site option the same way a
    # relic does (Byrdonis Egg's Hatch). RunState.rest_site_options() scans
    # the deck before the relics (mirrors IterateHookListeners's order).

    def modify_rest_site_options(self, run, options: "list[RestSiteOption]") -> None:
        """AbstractModel.TryModifyRestSiteOptions: append an extra rest-site
        action (default no-op)."""

    def __repr__(self) -> str:
        suffix = "+" * self.upgrade_level if self.upgrade_level > 0 else ""
        return f"{self.name}{suffix}"
```

- [ ] **Step 3d: Update `RunState.rest_site_options()`**

In `sts2_rl/run.py`, replace:

```python
    def rest_site_options(self):
        """Hook.TryModifyRestSiteOptions over the run's relics: the extra
        rest-site actions beyond Heal/Smith/Leave (Pael's Growth's Clone,
        Pumpkin Candle's Kindle, Meat Cleaver's Cook)."""
        options: list = []
        for relic in list(self.relics):
            relic.modify_rest_site_options(self, options)
        return options
```

with:

```python
    def rest_site_options(self):
        """Hook.TryModifyRestSiteOptions over the run's deck cards then
        relics (mirrors IterateHookListeners's order): the extra rest-site
        actions beyond Heal/Smith/Leave (Byrdonis Egg's Hatch, Pael's
        Growth's Clone, Pumpkin Candle's Kindle, Meat Cleaver's Cook,
        Shovel's Dig, Girya's Lift)."""
        options: list = []
        for card in list(self.deck):
            card.modify_rest_site_options(self, options)
        for relic in list(self.relics):
            relic.modify_rest_site_options(self, options)
        return options
```

- [ ] **Step 3e: Add the Byrdpip relic**

Create `sts2_rl/relics/byrdpip.py`:

```python
from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Byrdpip(Relic):
    """Byrdpip.cs — granted by Byrdonis Egg's HATCH rest-site option
    (HatchRestSiteOption.OnSelect: RelicCmd.Obtain<Byrdpip>). AfterObtained
    transforms every Byrdonis Egg card in the deck into ByrdSwoop, a real
    playable card. The source also spawns a decorative pet at combat start
    (Monsters/Byrdpip.cs), but that pet has 9999 HP, a hidden health bar,
    and a move state machine that does nothing (NOTHING_MOVE) — pure
    animation flavor for ByrdSwoop's attack, no combat mechanics — so the
    sim omits it, matching Pael's Legion's precedent of modeling only a pet
    relic's mechanical payoff, not an actual pet creature."""

    id = "byrdpip"
    name = "Byrdpip"
    rarity = RelicRarity.EVENT
    adds_pet = True

    def after_obtained(self, run) -> None:
        from ..cards import make_card
        for card in list(run.deck):
            if card.id == "byrdonis_egg":
                run.transform_card(card, into=make_card("byrd_swoop"))
```

- [ ] **Step 3f: Wire Byrdonis Egg's HATCH option and add ByrdSwoop**

In `sts2_rl/cards/event_cards.py`, change the module docstring from:

```python
"""Cards granted only by events — not part of any reward pool.

Sources: ByrdonisEgg.cs (Byrdonis Nest), Peck.cs and ToricToughness.cs
(Wood Carvings), plus the Act-2 (Underdocks / Hive) event cards —
UltimateStrike/UltimateDefend (Amalgamator), Exterminate/Squash (Bugslayer),
Metamorphosis (Spirit Grafter), Enlightenment (Zen Weaver), FeedingFrenzy
(Endless Conveyor), and LanternKey (The Lantern Key). The Trash Heap card pool
lives in trash_heap_cards.py.
"""
```

to:

```python
"""Cards granted only by events — not part of any reward pool.

Sources: ByrdonisEgg.cs and ByrdSwoop.cs (Byrdonis Nest's Hatch, granted by
the Byrdpip relic — see relics/byrdpip.py), Peck.cs and ToricToughness.cs
(Wood Carvings), plus the Act-2 (Underdocks / Hive) event cards —
UltimateStrike/UltimateDefend (Amalgamator), Exterminate/Squash (Bugslayer),
Metamorphosis (Spirit Grafter), Enlightenment (Zen Weaver), FeedingFrenzy
(Endless Conveyor), and LanternKey (The Lantern Key). The Trash Heap card pool
lives in trash_heap_cards.py.
"""
```

Change the imports from:

```python
from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx
```

to:

```python
from .base import Card, CardRarity, CardType, TargetType, register_card
from ..rest_site import RestSiteOption

if TYPE_CHECKING:
    from ..combat import CombatCtx
```

Replace the `ByrdonisEggCard` class:

```python
@register_card
class ByrdonisEggCard(Card):
    """Quest — Unplayable. Taken from the Byrdonis Nest event; in the game it
    adds a "Hatch" rest-site option (pet). The sim has no rest sites, so in
    combat it is simply an unplayable card clogging the deck.

    Source: ByrdonisEgg.cs
      Cost -1 | Quest | Quest | TargetType.None | Unplayable | MaxUpgradeLevel 0
    """
    id = "byrdonis_egg"
    name = "Byrdonis Egg"
    card_type = CardType.QUEST
    rarity = CardRarity.QUEST
    target_type = TargetType.NONE
    is_playable = False
    max_upgrade_level = 0
    is_unpowered = True
    can_be_generated_by_modifiers = False

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass
```

with:

```python
@register_card
class ByrdonisEggCard(Card):
    """Quest — Unplayable. Taken from the Byrdonis Nest event. Adds a HATCH
    rest-site option (ByrdonisEgg.cs TryModifyRestSiteOptions): selecting it
    grants the Byrdpip relic, which transforms every Byrdonis Egg in the
    deck into ByrdSwoop (see relics/byrdpip.py).

    Source: ByrdonisEgg.cs
      Cost -1 | Quest | Quest | TargetType.None | Unplayable | MaxUpgradeLevel 0
    """
    id = "byrdonis_egg"
    name = "Byrdonis Egg"
    card_type = CardType.QUEST
    rarity = CardRarity.QUEST
    target_type = TargetType.NONE
    is_playable = False
    max_upgrade_level = 0
    is_unpowered = True
    can_be_generated_by_modifiers = False

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass

    def modify_rest_site_options(self, run, options) -> None:
        options.append(RestSiteOption("HATCH", lambda run: run.add_relic("byrdpip")))


@register_card
class ByrdSwoopCard(Card):
    """Attack (Event, 0E) — deal 14 damage. Granted by Byrdpip transforming
    every Byrdonis Egg in the deck (Hatch).

    Source: ByrdSwoop.cs — Damage 14 (Move), OnUpgrade +4.
    """
    id = "byrd_swoop"
    name = "Byrd Swoop"
    card_type = CardType.ATTACK
    rarity = CardRarity.EVENT
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._damage = 14

    def _on_upgrade(self) -> None:
        self._damage += 4

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        DamageCmd.deal(
            ctx.hooks, ctx.resolve_target(target_idx), self._damage,
            dealer=ctx.player, card=self,
        )
```

- [ ] **Step 3g: Register `ByrdSwoopCard` in the package**

In `sts2_rl/cards/__init__.py`, change:

```python
from .event_cards import (
    ByrdonisEggCard,
    PeckCard,
    ToricToughnessCard,
    UltimateStrikeCard,
    UltimateDefendCard,
    ExterminateCard,
    SquashCard,
    MetamorphosisCard,
    EnlightenmentCard,
    FeedingFrenzyCard,
    LanternKeyCard,
)
```

to:

```python
from .event_cards import (
    ByrdonisEggCard,
    ByrdSwoopCard,
    PeckCard,
    ToricToughnessCard,
    UltimateStrikeCard,
    UltimateDefendCard,
    ExterminateCard,
    SquashCard,
    MetamorphosisCard,
    EnlightenmentCard,
    FeedingFrenzyCard,
    LanternKeyCard,
)
```

And in the `__all__` list, change:

```python
    # Event cards
    "ByrdonisEggCard",
    "PeckCard",
```

to:

```python
    # Event cards
    "ByrdonisEggCard",
    "ByrdSwoopCard",
    "PeckCard",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -m pytest test/test_events.py -v`
Expected: PASS (all tests in the file, including the two new ones and the pre-existing `test_byrdonis_nest_*` / `test_byrdonis_egg_is_unplayable_in_combat`).

Also run the full existing rest-site relic tests to confirm the `rest_site_options()` reorder (deck before relics) doesn't break them:

Run: `py -m pytest test/test_ancients.py -k "meat_cleaver or pumpkin_candle or paels_growth or girya or shovel" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sts2_rl/rest_site.py sts2_rl/relics/base.py sts2_rl/relics/byrdpip.py sts2_rl/cards/base.py sts2_rl/cards/event_cards.py sts2_rl/cards/__init__.py sts2_rl/run.py test/test_events.py
git commit -m "feat: card rest-site hook + Byrdpip relic + ByrdSwoop card + Byrdonis Egg's HATCH"
```

---

### Task 5: Miniature Tent — multi-action rest visits (driver loop rewrite)

**Files:**
- Modify: `sts2_rl/relics/base.py`
- Modify: `sts2_rl/relics/miniature_tent.py`
- Modify: `sts2_rl/run.py`
- Modify: `sts2_rl/driver.py`
- Test: `test/test_driver.py`
- Test: `test/test_ancients.py`

**Interfaces:**
- Consumes: `RunState.rest_site_options()` (Task 4), `RunState.upgradable_cards()` (pre-existing).
- Produces: `Relic.should_disable_remaining_rest_site_options(self, run) -> bool` (default `True`), `RunState.should_disable_remaining_rest_site_options(self) -> bool`, and three new fields on `DecisionRequest`: `rest_options: list | None`, `rest_heal_used: bool`, `rest_smith_used: bool`.

- [ ] **Step 1: Write the failing tests**

Append to `test/test_ancients.py` (end of file):

```python


def test_miniature_tent_disables_hook_returns_false():
    run = fresh_run(1)
    run.add_relic("miniature_tent")
    assert run.should_disable_remaining_rest_site_options() is False
    run2 = fresh_run(1)
    assert run2.should_disable_remaining_rest_site_options() is True
```

Insert into `test/test_driver.py`, directly after `test_no_dream_catcher_no_reward_card_after_rest_heal` (before `test_combat_rewards_offered_after_won_fight`):

```python

def test_miniature_tent_allows_a_second_rest_site_action():
    run = fresh_run(7)
    run.add_relic("miniature_tent")
    run.hp = 40

    def scripted(request):
        if request.kind == DecisionKind.REST:
            if not request.rest_heal_used:
                return 0                       # heal first
            if not request.rest_smith_used:
                return 1                       # then smith
            return 2                           # leave
        return request.legal_actions()[0]      # forced card selector

    driver = RunDriver(run, scripted)
    driver._run_rest()
    assert run.hp == 64                          # healed
    assert any(c.upgrade_level > 0 for c in run.deck)  # and smithed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest test/test_ancients.py::test_miniature_tent_disables_hook_returns_false test/test_driver.py::test_miniature_tent_allows_a_second_rest_site_action -v`
Expected: FAIL — `RunState` has no `should_disable_remaining_rest_site_options` attribute yet (`AttributeError`), and the driver test's second `DecisionRequest` never arrives because `_run_rest()` is single-shot.

- [ ] **Step 3a: Add the relic hook**

In `sts2_rl/relics/base.py`, replace:

```python
    def modify_rest_site_options(self, run, options: "list[RestSiteOption]") -> None:
        """RelicModel.TryModifyRestSiteOptions — append extra rest-site
        actions (Pael's Growth's Clone, Pumpkin Candle's Kindle, Meat
        Cleaver's Cook, Shovel's Dig, Girya's Lift). The driver surfaces
        them after Heal/Smith/Leave."""

    def modify_rest_site_heal_rewards(self, run, rewards) -> None:
```

with:

```python
    def modify_rest_site_options(self, run, options: "list[RestSiteOption]") -> None:
        """RelicModel.TryModifyRestSiteOptions — append extra rest-site
        actions (Pael's Growth's Clone, Pumpkin Candle's Kindle, Meat
        Cleaver's Cook, Shovel's Dig, Girya's Lift). The driver surfaces
        them after Heal/Smith/Leave."""

    def should_disable_remaining_rest_site_options(self, run) -> bool:
        """RelicModel.ShouldDisableRemainingRestSiteOptions — default True
        (a rest-site visit ends after one action). Miniature Tent returns
        False so the visit continues until Leave or the options run out."""
        return True

    def modify_rest_site_heal_rewards(self, run, rewards) -> None:
```

- [ ] **Step 3b: Implement Miniature Tent**

Replace the full contents of `sts2_rl/relics/miniature_tent.py`:

```python
from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class MiniatureTent(Relic):
    """MiniatureTent.cs — ShouldDisableRemainingRestSiteOptions returns
    False: a rest-site visit doesn't end after one action, so the player may
    keep choosing options (Heal, Smith, other relic/card options) until they
    explicitly Leave or run out."""

    id = "miniature_tent"
    name = "Miniature Tent"
    rarity = RelicRarity.SHOP

    def should_disable_remaining_rest_site_options(self, run) -> bool:
        return False
```

- [ ] **Step 3c: Add `RunState.should_disable_remaining_rest_site_options()`**

In `sts2_rl/run.py`, immediately after the `rest_site_options()` method (before the `has_event_pet` property), add:

```python
    def should_disable_remaining_rest_site_options(self) -> bool:
        """Hook.ShouldDisableRemainingRestSiteOptions: True (end the visit
        after one action) unless a relic says otherwise (Miniature Tent),
        in which case the visit continues."""
        return all(
            relic.should_disable_remaining_rest_site_options(self)
            for relic in self.relics
        )
```

- [ ] **Step 3d: Rewrite the driver's rest-site flow**

In `sts2_rl/driver.py`, in the `DecisionRequest` dataclass, change:

```python
    n_options: int = 0                            # SELECT_OPTION
```

to:

```python
    n_options: int = 0                            # SELECT_OPTION
    rest_options: "list | None" = None            # REST: this visit's option snapshot
    rest_heal_used: bool = False                  # REST
    rest_smith_used: bool = False                 # REST
```

Then, in `legal_actions()`, replace the `DecisionKind.REST` branch:

```python
        if kind == DecisionKind.REST:
            legal = [REST_HEAL]
            if self.run.upgradable_cards():
                legal.append(REST_SMITH)
            legal.append(REST_LEAVE)
            # Relic-provided extra options (Hook.TryModifyRestSiteOptions:
            # Clone / Kindle / Cook) at indices 3+.
            legal.extend(
                REST_LEAVE + 1 + i
                for i in range(len(self.run.rest_site_options()))
            )
            return legal
```

with:

```python
        if kind == DecisionKind.REST:
            legal = []
            if not self.rest_heal_used:
                legal.append(REST_HEAL)
            if not self.rest_smith_used and self.run.upgradable_cards():
                legal.append(REST_SMITH)
            legal.append(REST_LEAVE)
            # Card/relic-provided extra options (Hook.TryModifyRestSiteOptions:
            # Byrdonis Egg's Hatch, Pael's Growth's Clone, Pumpkin Candle's
            # Kindle, Meat Cleaver's Cook, Shovel's Dig, Girya's Lift) at
            # indices 3+, drawn from this visit's snapshot (`rest_options`)
            # rather than recomputed, so a used-up option can't reappear
            # mid-visit (Miniature Tent).
            legal.extend(
                REST_LEAVE + 1 + i
                for i in range(len(self.rest_options or []))
            )
            return legal
```

Finally, replace `_run_rest`:

```python
    def _run_rest(self) -> None:
        idx = self._ask(DecisionRequest(kind=DecisionKind.REST, run=self.run))
        if idx == REST_HEAL:
            self.run.rest_heal()
            # HealRestSiteOption.ExecuteRestSiteHeal: relics may add a reward
            # (Dream Catcher's 3-card choice) to the screen after the heal.
            self._offer_rewards(self.run.rest_heal_rewards())
        elif idx == REST_SMITH:
            self.run.rest_upgrade()
        elif idx > REST_LEAVE:
            # A relic-provided option (Clone / Kindle / Cook).
            options = self.run.rest_site_options()
            options[idx - REST_LEAVE - 1].on_select(self.run)
        # REST_LEAVE: nothing.
```

with:

```python
    def _run_rest(self) -> None:
        """RestSiteOption.Generate + RestSiteSynchronizer.ChooseOption: a
        visit takes one snapshot of the extra options up front (so a used-up
        one — e.g. Meat Cleaver's Cook — can't be picked twice even if its
        precondition would still allow it), then loops asking for an action
        until Leave or Hook.ShouldDisableRemainingRestSiteOptions says the
        visit is over (default: after the first action; Miniature Tent lets
        it continue)."""
        run = self.run
        options = run.rest_site_options()
        heal_used = False
        smith_used = False
        while True:
            idx = self._ask(DecisionRequest(
                kind=DecisionKind.REST, run=run,
                rest_options=options,
                rest_heal_used=heal_used,
                rest_smith_used=smith_used,
            ))
            if idx == REST_LEAVE:
                return
            if idx == REST_HEAL:
                run.rest_heal()
                # HealRestSiteOption.ExecuteRestSiteHeal: relics may add a
                # reward (Dream Catcher's 3-card choice) after the heal.
                self._offer_rewards(run.rest_heal_rewards())
                heal_used = True
            elif idx == REST_SMITH:
                run.rest_upgrade()
                smith_used = True
            else:
                # A card/relic-provided option (Hatch / Clone / Kindle /
                # Cook / Dig / Lift), picked from this visit's snapshot.
                options.pop(idx - REST_LEAVE - 1).on_select(run)
            if run.should_disable_remaining_rest_site_options():
                return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest test/test_ancients.py::test_miniature_tent_disables_hook_returns_false test/test_driver.py::test_miniature_tent_allows_a_second_rest_site_action -v`
Expected: PASS

Then confirm no regression on the pre-existing rest-site driver tests (no relic present ⇒ still one action per visit) and the whole-run smoke tests (random policy must still terminate cleanly through rest sites):

Run: `py -m pytest test/test_driver.py -v`
Expected: PASS (including `test_rest_choices`, `test_dream_catcher_rest_heal_offers_card_reward`, `test_no_dream_catcher_no_reward_card_after_rest_heal`, `test_random_runs_complete`, `test_invincible_random_run_reaches_victory`).

- [ ] **Step 5: Commit**

```bash
git add sts2_rl/relics/base.py sts2_rl/relics/miniature_tent.py sts2_rl/run.py sts2_rl/driver.py test/test_driver.py test/test_ancients.py
git commit -m "feat: Miniature Tent's multi-action rest visits"
```

---

## Final verification

After all 5 tasks:

Run: `py -m pytest test/ -v`
Expected: full suite PASS, no regressions.

Run: `py -m pytest test/test_vocab.py -v`
Expected: PASS — confirms `byrdpip` and `byrd_swoop` were appended to `vocab.json` without exceeding the `relics`/`cards` capacities.
