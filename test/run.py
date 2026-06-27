"""Interactive Slay the Spire 2 combat demo.

Deck      : 3 × Strike, 2 × Defend, 1 × Breakthrough (power), 1 × Sweep (AoE attack)
Encounter : Slime (14–16 HP, 6 dmg/turn) + Goblin (9–11 HP, 3×2 dmg/turn)

Controls  : type a card index to play it, 'e' to end your turn.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import random

from sts2_rl import CombatState
from sts2_rl.cards import BreakthroughCard, DefendCard, StrikeCard, SweepCard, TargetType
from sts2_rl.monsters import Encounter, Intent, Monster, MoveType


# ── Demo monsters ────────────────────────────────────────────────────────────

class Slime(Monster):
    min_hp = 14
    max_hp = 16

    @property
    def current_intent(self) -> Intent:
        return Intent(move_type=MoveType.ATTACK, damage=6, hits=1)

    def take_turn(self, ctx) -> None:
        self._execute_attack(ctx, 6, 1)


class Goblin(Monster):
    min_hp = 9
    max_hp = 11

    @property
    def current_intent(self) -> Intent:
        return Intent(move_type=MoveType.ATTACK, damage=3, hits=2)

    def take_turn(self, ctx) -> None:
        self._execute_attack(ctx, 3, 2)


DEMO_ENCOUNTER = Encounter(id="demo", monster_classes=[Slime, Goblin])


# ── Display helpers ───────────────────────────────────────────────────────────

def _intent_str(e: Monster) -> str:
    intent = e.current_intent
    if intent.move_type == MoveType.ATTACK:
        dmg = intent.damage + e.strength
        if intent.hits > 1:
            return f"Attack {intent.hits}×{dmg} ({intent.hits * dmg} total)"
        return f"Attack {dmg}"
    return "Buff"


def _render(state: CombatState) -> None:
    p = state.player
    sep = "─" * 56
    print(f"\n{sep}")
    pws = f"  [{', '.join(f'{n}:{pw.amount}' for n, pw in p.powers.items())}]" if p.powers else ""
    print(f"  Player  HP {p.hp}/{p.max_hp}  Block {p.block}  Energy {p.energy}{pws}")
    print()
    for i, e in enumerate(state.enemies):
        if e.is_dead:
            print(f"  [{i}] {e.__class__.__name__:10s}  DEAD")
        else:
            blk = f"  Block {e.block}" if e.block else ""
            pws = f"  [{', '.join(f'{n}:{pw.amount}' for n, pw in e.powers.items())}]" if e.powers else ""
            print(f"  [{i}] {e.__class__.__name__:10s}  HP {e.hp:>3}/{e.max_hp}{blk}  → {_intent_str(e)}{pws}")
    print()
    print(f"  Hand:")
    for i, card in enumerate(p.hand):
        cost = state.hooks.modify_card_energy_cost(card, card.energy_cost)
        affordable = "  " if cost <= p.energy else "  (no energy)"
        ttype = {
            TargetType.ANY_ENEMY:   "→ pick target",
            TargetType.ALL_ENEMIES: "→ all enemies",
            TargetType.SELF:        "→ self",
            TargetType.NONE:        "",
        }[card.target_type]
        print(f"    {i}: [{cost}E] {card.name:14s} {ttype}{affordable}")
    print(f"{sep}")


def _pick_target(state: CombatState) -> int:
    living = [(i, e) for i, e in enumerate(state.enemies) if not e.is_dead]
    if len(living) == 1:
        return living[0][0]
    opts = "  ".join(f"{i}={e.__class__.__name__}" for i, e in living)
    while True:
        raw = input(f"  Target ({opts}): ").strip()
        if raw.isdigit() and int(raw) in [i for i, _ in living]:
            return int(raw)
        print("  Invalid — enter a living enemy index.")


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    deck = (
        [StrikeCard()      for _ in range(3)]
        + [DefendCard()    for _ in range(2)]
        + [BreakthroughCard()]
        + [SweepCard()]
    )
    state = CombatState(
        starting_deck=deck,
        encounter=DEMO_ENCOUNTER,
        rng=random.Random(),
    )
    _render(state)

    while not state.is_over:
        raw = input("Play> ").strip().lower()

        if raw == "e":
            state.end_turn()
            _render(state)
            continue

        if raw.isdigit():
            idx = int(raw)
            if idx < 0 or idx >= len(state.player.hand):
                print("  No card at that index.")
                continue
            card = state.player.hand[idx]
            cost = state.hooks.modify_card_energy_cost(card, card.energy_cost)
            if cost > state.player.energy:
                print("  Not enough energy.")
                continue

            target_idx = None
            if card.target_type == TargetType.ANY_ENEMY:
                target_idx = _pick_target(state)

            state.play_card(idx, target_idx=target_idx)
            _render(state)
            continue

        print("  Enter a card index or 'e' to end your turn.")

    r = state.result
    print(f"\n{'Victory!' if r.player_won else 'Defeat.'} (completed in {r.turns_taken} turn(s))")


if __name__ == "__main__":
    main()
