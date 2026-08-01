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

    #: AfflictionModel.IsStackable (AfflictionModel.cs:127), default False.
    #: Only Galvanized and Tainted override it True in the game source.
    is_stackable: bool = False

    def __init__(self, amount: int) -> None:
        self.amount = amount
        self.card: Card | None = None

    def __repr__(self) -> str:
        return f"{self.name}({self.amount})"

    def can_afflict_card_type(self, card_type) -> bool:
        """AfflictionModel.CanAfflictCardType (AfflictionModel.cs:175-178),
        default True. Tainted is the only game-source override (Skill only)."""
        return True

    def can_afflict(self, card: "Card") -> bool:
        """AfflictionModel.CanAfflict (AfflictionModel.cs:190-205).
        creature_card_cmds/N2 + step65 — `CardCmd.afflict` (cmds.py)
        previously consulted no such predicate at all.

        The `CanAfflictUnplayableCards` clause (AfflictionModel.cs:196-199)
        is not modeled: the sim has no Unplayable-keyword surface on `Card`,
        and every ported affliction (Bound/Entangled/Galvanized/Hexed/
        Ringing/Smog/Tainted) leaves `CanAfflictUnplayableCards` at its
        default (True, AfflictionModel.cs:125), under which that clause can
        never refuse regardless of whether the card is unplayable — so
        omitting it changes nothing observable for any ported content.
        """
        if not self.can_afflict_card_type(card.card_type):
            return False
        if card.affliction is not None and (
            not self.is_stackable or type(card.affliction) is not type(self)
        ):
            return False
        return True


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
    Tainted card gives the player Tainted (take +N attack damage this turn).

    IsStackable = true and CanAfflictCardType restricted to Skill
    (Tainted.cs:9-19) — the only affliction in the game source that overrides
    either. VitalSparkPower never re-applies through `CardCmd.afflict`'s own
    stacking branch (it filters `card.affliction is None` and syncs the
    amount directly in `on_stack`), so IsStackable is currently dormant on
    ported content; ported here for fidelity regardless.
    """

    id = "tainted"
    name = "Tainted"
    is_stackable = True

    def can_afflict_card_type(self, card_type) -> bool:
        from .cards import CardType
        return card_type == CardType.SKILL


class GalvanizedAffliction(Affliction):
    """Applied by GalvanicPower (Globe Head) to Power cards; playing a
    Galvanized card deals N damage to the player.

    IsStackable = true (Galvanized.cs:7) — see TaintedAffliction's note;
    GalvanicPower is the same dormant-on-content shape."""

    id = "galvanized"
    name = "Galvanized"
    is_stackable = True


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
