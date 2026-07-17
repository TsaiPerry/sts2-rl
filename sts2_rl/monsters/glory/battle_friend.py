from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_TIME_LIMIT = 3  # BattlewornDummyTimeLimitPower(3)


class _BattleFriend(MachineMonster):
    """A training dummy: it never acts, but flees after 3 turns if still alive.

    Source: BattleFriendV1/2/3.cs — a single NOTHING_MOVE that loops, with
    AfterAddedToRoom applying BattlewornDummyTimeLimitPower(3). Fought in the
    Battleworn Dummy event; the reward (potion / two upgrades / relic) is
    granted by the event's resume_after_combat only if the dummy is destroyed
    before it flees (BattlewornDummy.cs Resume)."""

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import BattlewornDummyTimeLimitPower
        PowerCmd.apply(hooks, self, BattlewornDummyTimeLimitPower, _TIME_LIMIT)

    def build_machine(self) -> MonsterMoveStateMachine:
        nothing = MoveState(
            "NOTHING_MOVE", lambda ctx: None, Intent(MoveType.UNKNOWN)
        )
        nothing.follow_up = nothing
        return MonsterMoveStateMachine([nothing], nothing)


class BattleFriendV1(_BattleFriend):
    """Setting 1 dummy — 75 HP (BattleFriendV1.cs). Victory offers a potion."""

    min_hp = 75
    max_hp = 75


class BattleFriendV2(_BattleFriend):
    """Setting 2 dummy — 150 HP (BattleFriendV2.cs). Victory upgrades 2 cards."""

    min_hp = 150
    max_hp = 150


class BattleFriendV3(_BattleFriend):
    """Setting 3 dummy — 300 HP (BattleFriendV3.cs). Victory grants a relic."""

    min_hp = 300
    max_hp = 300


# The three encounters selected by the event's difficulty settings
# (BattlewornDummyEventEncounter.cs picks the dummy by Setting; its
# ShouldGiveRewards=false suppresses the normal reward screen — the event's
# Resume grants the setting's reward instead).
BATTLEWORN_DUMMY_SETTING_1 = Encounter(
    id="battleworn_dummy_setting_1", monster_classes=[BattleFriendV1],
    should_give_rewards=False,
)
BATTLEWORN_DUMMY_SETTING_2 = Encounter(
    id="battleworn_dummy_setting_2", monster_classes=[BattleFriendV2],
    should_give_rewards=False,
)
BATTLEWORN_DUMMY_SETTING_3 = Encounter(
    id="battleworn_dummy_setting_3", monster_classes=[BattleFriendV3],
    should_give_rewards=False,
)
