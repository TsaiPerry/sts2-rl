from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..cards import CardType
from ..valueprops import DamageProps

if TYPE_CHECKING:
    from ..cards import Card
    from ..player import PlayerCombatState

@register_relic
class Kusarigama(Relic):
    """Every time you play 3 Attacks in a single turn, deal 6 damage to a
    random enemy."""

    id = "kusarigama"
    name = "Kusarigama"
    rarity = RelicRarity.UNCOMMON

    ATTACKS = 3
    DAMAGE = 6

    def __init__(self) -> None:
        super().__init__()
        self._attacks_this_turn = 0

    def on_combat_start(self) -> None:
        self._attacks_this_turn = 0

    def on_player_turn_end(self, player: PlayerCombatState) -> None:
        self._attacks_this_turn = 0

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        if card.card_type != CardType.ATTACK:
            return
        self._attacks_this_turn += 1
        if self._attacks_this_turn % self.ATTACKS == 0:
            living = self.living_enemies()
            if not living:
                return
            from ..cmds import DamageCmd
            # Kusarigama.cs: RunState.Rng.CombatTargets.NextItem(HittableEnemies).
            target = self.combat.combat_rng.targets.choice(living)
            DamageCmd.deal(
                self.hooks, target, self.DAMAGE,
                dealer=self.player, props=DamageProps.NON_CARD_UNPOWERED,
            )
            self._check_win()
