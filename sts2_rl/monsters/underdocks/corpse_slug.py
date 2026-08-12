from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, Monster, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_WHIP_SLAP_DMG = 3
_WHIP_SLAP_HITS = 2
_GLOMP_DMG = 8          # CorpseSlug.cs:47 base
_GLOMP_DMG_ASC = 9      # DeadlyEnemies
_GOOP_FRAIL = 2
_RAVENOUS_STR = 4       # CorpseSlug.cs:51 base
_RAVENOUS_STR_ASC = 5   # DeadlyEnemies


class CorpseSlug(MachineMonster):
    """WHIP_SLAP → GLOMP → GOOP → loop; the encounter staggers each slug's
    starting move (starter_move_idx, mirroring StarterMoveIdx). Ravenous:
    when a fellow slug dies, this one devours it — stunned for a turn and
    +4 Strength."""

    name = "Corpse Slug"  # localization/eng/monsters.json CORPSE_SLUG.name
    min_hp = 25             # CorpseSlug.cs:39
    max_hp = 27             # CorpseSlug.cs:41
    min_hp_asc = 27         # CorpseSlug.cs:39 -- ToughEnemies
    max_hp_asc = 29         # CorpseSlug.cs:41 -- ToughEnemies

    def __init__(
        self,
        hooks: HookSystem,
        rng: random.Random | None = None,
        *,
        starter_move_idx: int = 0,
    ) -> None:
        self._starter_move_idx = starter_move_idx  # read by build_machine
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import RavenousPower
        PowerCmd.apply(hooks, self, RavenousPower, self._ravenous_str())

    def _glomp_dmg(self) -> int:
        """CorpseSlug.cs:47 `GlompDamage` -- read at both the Intent (build_machine)
        and the executed attack (_glomp)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _GLOMP_DMG_ASC, _GLOMP_DMG)

    def _ravenous_str(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _RAVENOUS_STR_ASC, _RAVENOUS_STR)

    def build_machine(self) -> MonsterMoveStateMachine:
        whip_slap = MoveState(
            "WHIP_SLAP_MOVE", self._whip_slap,
            Intent(MoveType.ATTACK, damage=_WHIP_SLAP_DMG, hits=_WHIP_SLAP_HITS),
        )
        glomp = MoveState(
            "GLOMP_MOVE", self._glomp, Intent(MoveType.ATTACK, damage=self._glomp_dmg())
        )
        goop = MoveState("GOOP_MOVE", self._goop, Intent(MoveType.DEBUFF))
        whip_slap.follow_up = glomp
        glomp.follow_up = goop
        goop.follow_up = whip_slap
        initial = (whip_slap, glomp, goop)[self._starter_move_idx % 3]
        return MonsterMoveStateMachine([whip_slap, glomp, goop], initial)

    def _whip_slap(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _WHIP_SLAP_DMG, _WHIP_SLAP_HITS)

    def _glomp(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._glomp_dmg(), 1)

    def _goop(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import FrailPower
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _GOOP_FRAIL)


@dataclass
class CorpseSlugsEncounter(Encounter):
    """N Corpse Slugs starting on consecutive moves of the loop (mirrors
    EnsureCorpseSlugsStartWithDifferentMoves)."""

    monster_classes: list = field(default_factory=list)
    count: int = 3

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        # Parity (CorpseSlugs{Normal,Weak}.cs:32 ->
        # CorpseSlug.EnsureCorpseSlugsStartWithDifferentMoves, CorpseSlug.cs:138):
        # one `base.Rng.NextInt(3)` on the PER-ENCOUNTER Rng, staggered +1 per
        # slug. Legacy keeps the shared-rng draw.
        if selection_rng is not None:
            start = selection_rng.next_int(3)
        else:
            start = rng.randrange(3)
        return [
            CorpseSlug(hooks, rng, starter_move_idx=(start + i) % 3)
            for i in range(self.count)
        ]


CORPSE_SLUGS_NORMAL = CorpseSlugsEncounter(id="corpse_slugs_normal", count=3)
CORPSE_SLUGS_WEAK = CorpseSlugsEncounter(id="corpse_slugs_weak", count=2)
