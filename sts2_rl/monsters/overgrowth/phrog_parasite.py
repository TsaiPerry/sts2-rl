from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, Monster, MoveType, asc_value

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_LASH_DMG = 4      # PhrogParasite.cs:29 base
_LASH_DMG_ASC = 5  # DeadlyEnemies
_LASH_HITS = 4
_INFECT_CARDS = 3  # would add 3 Infection cards to player discard

_BITE_DMG = 6      # Wriggler.cs:34 base
_BITE_DMG_ASC = 7  # DeadlyEnemies


class Wriggler(Monster):
    """Spawned by PhrogParasite's Infested power; starts stunned if summoned mid-combat."""
    min_hp = 17          # Wriggler.cs:30 base
    max_hp = 21
    min_hp_asc = 18       # Wriggler.cs:30 -- ToughEnemies
    max_hp_asc = 22       # Wriggler.cs:32 -- ToughEnemies

    def __init__(
        self,
        hooks: HookSystem,
        rng: random.Random | None = None,
        *,
        start_stunned: bool = False,
        slot: int = 1,
    ) -> None:
        super().__init__(hooks, rng or random.Random())
        # Spawned mid-combat: stunned for its first turn (the combat loop
        # skips stunned creatures' moves, mirroring CreatureCmd.Stun).
        self.stunned = start_stunned
        # Odd slots start with NASTY_BITE; even slots start with WRIGGLE
        self._move_key = "NASTY_BITE" if slot % 2 == 1 else "WRIGGLE"

    def _bite_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _BITE_DMG_ASC, _BITE_DMG)

    @property
    def current_intent(self) -> Intent:
        if self.stunned:
            return Intent(MoveType.STUN)
        if self._move_key == "NASTY_BITE":
            return Intent(MoveType.ATTACK, damage=self._bite_dmg())
        from ...powers import StrengthPower
        # WRIGGLE buffs itself and shuffles an Infection into the discard pile
        return Intent(
            MoveType.BUFF, buffs=[(StrengthPower, 2)], also=(MoveType.STATUS_CARD,),
            status_count=1,
        )

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "NASTY_BITE":
            self._execute_attack(ctx, self._bite_dmg(), 1)
            self._move_key = "WRIGGLE"
        else:
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, 2)
            from ...cards import InfectionCard
            from ...cmds import CardPileCmd
            CardPileCmd.add_to_discard(ctx.hooks, ctx.player, InfectionCard())
            self._move_key = "NASTY_BITE"


class PhrogParasite(Monster):
    """INFECT (adds Infection cards) → LASH (multi-hit) → alternating.
    On death, InfestedPower spawns 4 stunned Wrigglers."""
    name = "Phrog Parasite"
    min_hp = 61
    max_hp = 64
    min_hp_asc = 66   # PhrogParasite.cs:25 -- ToughEnemies
    max_hp_asc = 68   # PhrogParasite.cs:27 -- ToughEnemies

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import InfestedPower
        PowerCmd.apply(hooks, self, InfestedPower, 4)
        self._move_key = "INFECT"

    def _lash_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _LASH_DMG_ASC, _LASH_DMG)

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "INFECT":
            return Intent(MoveType.STATUS_CARD, status_count=_INFECT_CARDS)
        return Intent(MoveType.ATTACK, damage=self._lash_dmg(), hits=_LASH_HITS)

    def take_turn(self, ctx: CombatCtx) -> None:
        if self._move_key == "INFECT":
            from ...cards import InfectionCard
            from ...cmds import CardPileCmd
            for _ in range(_INFECT_CARDS):
                CardPileCmd.add_to_discard(ctx.hooks, ctx.player, InfectionCard())
            self._move_key = "LASH"
        else:
            self._execute_attack(ctx, self._lash_dmg(), _LASH_HITS)
            self._move_key = "INFECT"


PHROG_PARASITE_ELITE = Encounter(
    id="phrog_parasite_elite",
    monster_classes=[PhrogParasite],
)
