"""Interactive Slay the Spire 2 combat demo.

Deck      : 3 × Strike, 2 × Defend, 1 × Breakthrough (power), 1 × Sweep (AoE attack)
Controls  : type a card index to play it, 'e' to end your turn.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import random

from sts2_rl import CombatState
from sts2_rl.cards import BreakthroughCard, Card, DefendCard, StrikeCard, SweepCard, TargetType
from sts2_rl.creatures import Creature
from sts2_rl.monsters import Monster, MoveType
from sts2_rl.monsters.overgrowth import ENCOUNTERS as OVERGROWTH_ENCOUNTERS

# ── Change this key to fight a different Overgrowth encounter ─────────────────
ENCOUNTER = OVERGROWTH_ENCOUNTERS["slimes_weak"]
# ─────────────────────────────────────────────────────────────────────────────

_SEP = "─" * 56

_TARGET_HINTS = {
    TargetType.ANY_ENEMY:   "→ pick target",
    TargetType.ALL_ENEMIES: "→ all enemies",
    TargetType.SELF:        "→ self",
    TargetType.NONE:        "",
}


# ── Display helpers ───────────────────────────────────────────────────────────

def _card_cost(state: CombatState, card: Card) -> int:
    return state.hooks.modify_card_energy_cost(card, card.energy_cost)


def _powers_str(c: Creature) -> str:
    if not c.powers:
        return ""
    return f"  [{', '.join(f'{n}:{pw.amount}' for n, pw in c.powers.items())}]"


def _intent_str(e: Monster) -> str:
    intent = e.current_intent
    if intent.move_type != MoveType.ATTACK:
        return "Buff"
    dmg = intent.damage + e.strength
    if intent.hits > 1:
        return f"Attack {intent.hits}×{dmg} ({intent.hits * dmg} total)"
    return f"Attack {dmg}"


def _enemy_line(i: int, e: Monster) -> str:
    name = e.__class__.__name__
    if e.is_dead:
        return f"  [{i}] {name:10s}  DEAD"
    blk = f"  Block {e.block}" if e.block else ""
    return f"  [{i}] {name:10s}  HP {e.hp:>3}/{e.max_hp}{blk}  → {_intent_str(e)}{_powers_str(e)}"


def _render(state: CombatState) -> None:
    p = state.player
    print(f"\n{_SEP}")
    print(f"  Player  HP {p.hp}/{p.max_hp}  Block {p.block}  Energy {p.energy}{_powers_str(p)}")
    print()
    for i, e in enumerate(state.enemies):
        print(_enemy_line(i, e))
    print()
    print("  Hand:")
    for i, card in enumerate(p.hand):
        cost = _card_cost(state, card)
        affordable = "  " if cost <= p.energy else "  (no energy)"
        print(f"    {i}: [{cost}E] {card.name:14s} {_TARGET_HINTS[card.target_type]}{affordable}")
    print(_SEP)


# ── Input handling ────────────────────────────────────────────────────────────

def _pick_target(state: CombatState) -> int:
    living = [(i, e) for i, e in enumerate(state.enemies) if not e.is_dead]
    if len(living) == 1:
        return living[0][0]
    indices = {i for i, _ in living}
    opts = "  ".join(f"{i}={e.__class__.__name__}" for i, e in living)
    while True:
        raw = input(f"  Target ({opts}): ").strip()
        if raw.isdigit() and int(raw) in indices:
            return int(raw)
        print("  Invalid — enter a living enemy index.")


def _play_card(state: CombatState, idx: int) -> bool:
    """Try to play the card at hand index idx; return True if it was played."""
    if not 0 <= idx < len(state.player.hand):
        print("  No card at that index.")
        return False
    card = state.player.hand[idx]
    if _card_cost(state, card) > state.player.energy:
        print("  Not enough energy.")
        return False

    target_idx = None
    if card.target_type == TargetType.ANY_ENEMY:
        target_idx = _pick_target(state)
    if not state.play_card(idx, target_idx=target_idx):
        print("  Can't play that card right now.")
        return False
    return True


# ── Main loop ─────────────────────────────────────────────────────────────────

def _build_deck() -> list[Card]:
    return (
        [StrikeCard() for _ in range(3)]
        + [DefendCard() for _ in range(2)]
        + [BreakthroughCard(), SweepCard()]
    )


def main() -> None:
    state = CombatState(
        starting_deck=_build_deck(),
        encounter=ENCOUNTER,
        rng=random.Random(),
    )
    _render(state)

    while not state.is_over:
        raw = input("Play> ").strip().lower()
        if raw == "e":
            state.end_turn()
            _render(state)
        elif raw.isdigit():
            if _play_card(state, int(raw)):
                _render(state)
        else:
            print("  Enter a card index or 'e' to end your turn.")

    r = state.result
    print(f"\n{'Victory!' if r.player_won else 'Defeat.'} (completed in {r.turns_taken} turn(s))")


if __name__ == "__main__":
    main()
