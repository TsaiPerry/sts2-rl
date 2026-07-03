"""Interactive Slay the Spire 2 combat demo.

Deck      : 3 × Strike, 2 × Defend, 1 × Breakthrough (power), 1 × Sweep (AoE),
            1 × Armaments (card selection), 1 × Whirlwind (X-cost)
Controls  : type a card index to play it, 'e' to end your turn.
            Card-selection effects (Armaments, Burning Pact, ...) prompt you
            to choose; X-cost cards spend all remaining energy.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

import random

from sts2_rl import CombatState
from sts2_rl.cards import Card, TargetType, make_card
from sts2_rl.creatures import Creature
from sts2_rl.monsters import Monster, MoveType
from sts2_rl.monsters.overgrowth import ENCOUNTERS as OVERGROWTH_ENCOUNTERS

# ── Change this key to fight a different Overgrowth encounter ─────────────────
ENCOUNTER = OVERGROWTH_ENCOUNTERS["slimes_normal"]
DECK =  ([make_card("strike") for _ in range(4)]
        + [make_card("defend") for _ in range(4)]
        + [make_card("breakthrough")]
        + [make_card("armaments"), make_card("whirlwind")]
        + [make_card("bash")])
# ─────────────────────────────────────────────────────────────────────────────

_SEP = "─" * 56

_TARGET_HINTS = {
    TargetType.ANY_ENEMY:    "→ pick target",
    TargetType.ALL_ENEMIES:  "→ all enemies",
    TargetType.RANDOM_ENEMY: "→ random enemy",
    TargetType.SELF:         "→ self",
    TargetType.NONE:         "",
}


# ── Display helpers ───────────────────────────────────────────────────────────

def _cost_str(state: CombatState, card: Card) -> str:
    if card.energy_cost_x:
        return "X"
    # card.energy_cost already includes per-turn modifiers (Stomp discounts,
    # Infernal Blade freebies); the hook adds power effects on top (Tangled).
    return str(state.hooks.modify_card_energy_cost(card, card.energy_cost))


def _is_affordable(state: CombatState, card: Card) -> bool:
    if card.energy_cost_x:
        return True  # X may be 0
    return state.hooks.modify_card_energy_cost(card, card.energy_cost) <= state.player.energy


def _powers_str(c: Creature) -> str:
    if not c.powers:
        return ""
    return f"  [{', '.join(f'{n}:{pw.amount}' for n, pw in c.powers.items())}]"


def _intent_str(e: Monster) -> str:
    intent = e.current_intent
    extra = "".join(f" +{t.value}" for t in intent.also)
    if intent.move_type != MoveType.ATTACK:
        return f"{intent.move_type.value.replace('_', ' ').title()}{extra}"
    dmg = intent.damage + e.strength
    if intent.hits > 1:
        return f"Attack {intent.hits}×{dmg} ({intent.hits * dmg} total){extra}"
    return f"Attack {dmg}{extra}"


def _enemy_line(i: int, e: Monster) -> str:
    name = e.__class__.__name__
    if e.is_dead:
        return f"  [{i}] {name:10s}  DEAD"
    blk = f"  Block {e.block}" if e.block else ""
    return f"  [{i}] {name:10s}  HP {e.hp:>3}/{e.max_hp}{blk}  → {_intent_str(e)}{_powers_str(e)}"


def _hand_line(state: CombatState, i: int, card: Card) -> str:
    # repr shows upgrades ("Strike+") — hands can be upgraded mid-combat now.
    name = repr(card)
    hint = _TARGET_HINTS[card.target_type]
    if not card.is_playable:
        note = "  (unplayable)"
    elif not _is_affordable(state, card):
        note = "  (no energy)"
    else:
        note = ""
    return f"    {i}: [{_cost_str(state, card)}E] {name:14s} {hint}{note}"


def _render(state: CombatState) -> None:
    p = state.player
    print(f"\n{_SEP}")
    print(f"  Turn {state.turn}")
    print(f"  Player  HP {p.hp}/{p.max_hp}  Block {p.block}  Energy {p.energy}{_powers_str(p)}")
    print(f"  Draw {len(p.draw_pile)}  Discard {len(p.discard_pile)}  Exhaust {len(p.exhaust_pile)}")
    print()
    for i, e in enumerate(state.enemies):
        print(_enemy_line(i, e))
    print()
    print("  Hand:")
    for i, card in enumerate(p.hand):
        print(_hand_line(state, i, card))
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


def _interactive_selector(purpose: str, candidates: list[Card], count: int) -> list[Card]:
    """Card selector for CombatState.card_selector: prompts instead of random.

    Called mid-card-resolution by effects like Armaments ("upgrade"),
    Burning Pact ("exhaust"), Headbutt ("from_discard"), Brand ("brand").
    """
    count = min(count, len(candidates))
    if count == len(candidates):
        return list(candidates)  # forced choice — no point prompting
    label = purpose.replace("_", " ")
    print(f"  Choose {count} card(s) — {label}:")
    for i, card in enumerate(candidates):
        print(f"    {i}: {card!r}")
    while True:
        raw = input("  Select> ").strip()
        picks = raw.replace(",", " ").split()
        if (
            len(picks) == count
            and all(p.isdigit() and int(p) < len(candidates) for p in picks)
            and len({int(p) for p in picks}) == count
        ):
            return [candidates[int(p)] for p in picks]
        print(f"  Enter {count} distinct index(es) between 0 and {len(candidates) - 1}.")


def _play_card(state: CombatState, idx: int) -> bool:
    """Try to play the card at hand index idx; return True if it was played."""
    if not 0 <= idx < len(state.player.hand):
        print("  No card at that index.")
        return False
    card = state.player.hand[idx]
    if not card.is_playable:
        print("  That card is unplayable.")
        return False
    if not _is_affordable(state, card):
        print("  Not enough energy.")
        return False
    if card.energy_cost_x and state.player.energy == 0:
        print("  (X = 0 — playing for no effect.)")

    target_idx = None
    if card.target_type == TargetType.ANY_ENEMY:
        target_idx = _pick_target(state)
    if not state.play_card(idx, target_idx=target_idx):
        print("  Can't play that card right now.")
        return False
    return True


# ── Main loop ─────────────────────────────────────────────────────────────────

def _build_deck() -> list[Card]:
    return DECK


def main() -> None:
    state = CombatState(
        starting_deck=_build_deck(),
        encounter=ENCOUNTER,
        rng=random.Random(),
    )
    state.card_selector = _interactive_selector
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
