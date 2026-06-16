from sts2_rl import STS2CombatEnv

env = STS2CombatEnv(render_mode="human")
env.reset()
env.render()

state = env._state

while not state.is_over:
    hand = state.player.hand
    valid = state.valid_actions()

    print("\nHand:")
    for i, card in enumerate(hand):
        playable = (i + 1) in valid
        print(f"  {i}: {card.name}{'' if playable else ' (not enough energy)'}")
    print("  e: end turn")

    while True:
        raw = input("Play> ").strip().lower()
        if raw == "e":
            state.end_turn()
            break
        if raw.isdigit():
            idx = int(raw)
            if (idx + 1) in valid:
                state.play_card(idx)
                break
            print("Invalid — not playable right now.")
            continue
        print("Enter a card number or 'e' to end turn.")

    env.render()

result = state.result
print(f"\n{'Victory!' if result.player_won else 'Defeat.'} ({result.turns_taken} turns)")
