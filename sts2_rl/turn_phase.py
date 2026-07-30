"""PlayerTurnPhase — where a player is inside their own turn.

A direct port of PlayerTurnPhase.cs. This is NOT `CombatState.phase`
(sts2_rl/combat.py's two-value PLAYER_TURN / COMBAT_OVER, which models
`CombatManager.IsInProgress` + `CurrentSide`): it is the per-player
`PlayerCombatState.Phase`, and content reads it. `UnceasingTop.IsValidPhase`
(UnceasingTop.cs:29-36) compiles to `(uint)(phase - 2) <= 2u`, i.e. exactly
{AutoPrePlay, Play, AutoPostPlay}, so the ORDINALS are load-bearing and the
enum is an IntEnum in the game's declaration order.
"""
from __future__ import annotations

from enum import IntEnum


class PlayerTurnPhase(IntEnum):
    """PlayerTurnPhase.cs:6-61."""

    #: No phase. Combat not in progress, or it is the enemy's turn.
    #: Set by CombatManager.cs:429 (every StartTurn, both sides), :904 (Reset)
    #: and :978 (EndCombatInternal).
    NONE = 0

    #: From the switch off the enemy side until the player may play cards:
    #: block clear, Hook.AfterSideTurnStart, energy reset, hand draw.
    #: Set by CombatManager.cs:464, AFTER Hook.BeforeSideTurnStart at :458.
    START = 1

    #: Start-of-turn auto-plays. Entered at CombatManager.cs:616 purely to
    #: bracket Hook.AfterAutoPrePlayPhaseEntered, and left again at :618.
    AUTO_PRE_PLAY = 2

    #: The player may play cards and use potions. Hooks fire only in response
    #: to player actions. CombatManager.cs:618.
    PLAY = 3

    #: End-of-turn auto-plays: Hook.AfterAutoPostPlayPhaseEntered.
    #: CombatManager.cs:1165.
    AUTO_POST_PLAY = 4

    #: From "end turn" until the switch to the enemy side: Hook.BeforeTurnEnd,
    #: the hand flush, Hook.AfterTurnEnd. CombatManager.cs:1175.
    END = 5
