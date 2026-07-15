"""Afflictions — markers attached to a single card, mirroring STS2's
AfflictionModel.

An affliction carries no logic of its own: the power that applied it reads it
back later. Ringing/Smog/Tainted gate whether a card can be played this turn;
Entangled raises an Attack card's energy cost. Applied and cleared through
`CardCmd.afflict` / `clear_affliction` in cmds.py.
"""
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


class TaintedAffliction(Affliction):
    """Applied by VitalSparkPower (Infested Prism) to Skill cards; playing a
    Tainted card gives the player Tainted (take +N attack damage this turn)."""

    id = "tainted"
    name = "Tainted"


class GalvanizedAffliction(Affliction):
    """Applied by GalvanicPower (Globe Head) to Power cards; playing a
    Galvanized card deals N damage to the player."""

    id = "galvanized"
    name = "Galvanized"


class HexedAffliction(Affliction):
    """Applied by HexPower (Spectral Knight); while present the card is
    Ethereal (exhausts if still in hand at turn end)."""

    id = "hexed"
    name = "Hexed"


class BoundAffliction(Affliction):
    """Applied by ChainsOfBindingPower (the Queen) to drawn cards; only one
    Bound card may be played per turn."""

    id = "bound"
    name = "Bound"
