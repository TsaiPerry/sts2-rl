from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cards import Card


class Affliction:
    """A marker attached to a single card, mirroring STS2's AfflictionModel.

    Each card holds at most one affliction. Afflictions carry no logic of
    their own — the power that applied them (Ringing, Tangled) reads them.
    """

    id: str
    name: str

    def __init__(self, amount: int) -> None:
        self.amount = amount
        self.card: Card | None = None

    def __repr__(self) -> str:
        return f"{self.name}({self.amount})"


class RingingAffliction(Affliction):
    """Applied by RingingPower; blocks play after the turn's first card."""

    id = "ringing"
    name = "Ringing"


class EntangledAffliction(Affliction):
    """Applied by TangledPower to Attack cards; raises their energy cost."""

    id = "entangled"
    name = "Entangled"


class SmogAffliction(Affliction):
    """Applied by SmoggyPower to Skill cards; blocks playing them this turn."""

    id = "smog"
    name = "Smog"
