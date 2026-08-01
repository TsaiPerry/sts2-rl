from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class BloodWallCard(Card):
    """Skill (Common, 2E) — lose 2 HP; gain 16 block.

    Source: BloodWall.cs
      Cost 2 | Skill | Common | TargetType.Self
      OnPlay: CreatureCmd.Damage(self, 2, Unblockable|Unpowered|Move), then GainBlock(16)
      OnUpgrade: block +4 (→ 20)
    """
    id = "blood_wall"
    gains_block = True  # CardModel.GainsBlock
    name = "Blood Wall"
    card_type = CardType.SKILL
    rarity = CardRarity.COMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._hp_loss = 2
        self._block = 16

    def _on_upgrade(self) -> None:
        self._block += 4

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, DamageCmd
        from ..valueprops import DamageProps
        DamageCmd.deal(ctx.hooks, ctx.player, self._hp_loss, card=self, props=DamageProps.CARD_HP_LOSS)
        # BloodWall.cs has no is_dead guard here -- C# unconditionally awaits
        # CreatureCmd.GainBlock next. No divergence to reproduce: GainBlock's
        # own IsOverOrEnding bail (CreatureCmd.cs:637-640), mirrored by
        # BlockCmd.apply, already makes this a no-op on a dying player -- see
        # card/_is_dead_early_return (Task 27) and
        # test/test_is_dead_early_returns.py.
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
