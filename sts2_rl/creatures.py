class Creature:
    def __init__(self, max_hp: int) -> None:
        self.max_hp = max_hp
        self.hp = max_hp
        self.block = 0
        self.strength = 0

    @property
    def is_dead(self) -> bool:
        return self.hp <= 0
