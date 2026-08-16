"""Afflictions — markers attached to a single card, mirroring STS2's
AfflictionModel.

An affliction carries no logic of its own: the power that applied it reads it
back later. Ringing/Smog/Tainted gate whether a card can be played this turn;
Entangled raises an Attack card's energy cost. Applied and cleared through
`CardCmd.afflict` / `clear_affliction` in cmds.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .hooks import CAT_CARD
from .vocab import capacity as vocab_capacity, frozen_ids

if TYPE_CHECKING:
    from .cards import Card


_AFFLICTION_CLASSES: dict[str, type[Affliction]] = {}


def register_affliction(cls: type[Affliction]) -> type[Affliction]:
    """Registers a concrete `Affliction` subclass by its `id`.

    Mirrors `enchantments.register_enchantment`: an explicit decorator rather
    than a `__subclasses__()` walk, because the frozen vocabulary (vocab.py)
    needs a deterministic source that does not depend on import order.
    """
    _AFFLICTION_CLASSES[cls.id] = cls
    return cls


def make_affliction(affliction_id: str, amount: int = 1) -> Affliction:
    """Factory mirroring `enchantments.make_enchantment`.

    Unlike `Enchantment.__init__` (which defaults `amount` to 1),
    `Affliction.__init__` requires `amount` with no default, so this factory
    supplies one; every real call site constructs the concrete class
    directly with an explicit amount and is unaffected by this default.
    """
    return _AFFLICTION_CLASSES[affliction_id](amount)


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

    # `CombatState.IterateHookListeners` adds `cardModel.Affliction` to the
    # listener list immediately after its card and before that card's
    # Enchantment (CombatState.cs:458-461) — THAT is the load-bearing citation.
    # `AfflictionModel.cs:146`'s `ShouldReceiveCombatHooks => true` corroborates
    # it but is decorative: `grep -rn ShouldReceiveCombatHooks src/` finds
    # declarations and zero readers in this build. So an affliction shares its
    # card's slot; `HookSystem._ordered` emits it from the pile walk, and this
    # is the fallback hint for one whose card is in no pile.
    #
    # DORMANT on today's content, both ends: none of the seven sim Affliction
    # subclasses below defines any HookSystem hook, and of the ten C# files
    # under src/Core/Models/Afflictions exactly one overrides an AbstractModel
    # hook (Hexed.cs, AfterCardEnteredCombat) and Hexed is a data-only stub
    # here. The machinery exists so that porting Hexed is a content change and
    # not an engine change (hook_dispatch/G6).
    hook_category = CAT_CARD
    # Rides on a card rather than sitting in a pile itself; see Enchantment.
    hook_is_card_rider = True

    def __init__(self, amount: int) -> None:
        self.amount = amount
        self.card: Card | None = None

    def hook_contains(self) -> bool:
        """`CombatState.Contains`' AfflictionModel arm (CombatState.cs:591):
        `HasCard && !Card.HasBeenRemovedFromState && Card.Owner.IsActiveForHooks`.

        `HasCard` is `_card != null` (AfflictionModel.cs:90). C# guarantees it
        goes false the moment the affliction is cleared —
        `CardModel.ClearAfflictionInternal` (CardModel.cs:1532-1540) calls
        `AfflictionModel.ClearInternal` (:249-254), which nulls `_card`, before
        nulling the card's own `Affliction`. `CardCmd.clear_affliction` mirrors
        both halves for exactly this reason.
        """
        card = self.card
        return card is not None and card.hook_contains()

    def __repr__(self) -> str:
        return f"{self.name}({self.amount})"

    def can_afflict_card_type(self, card_type) -> bool:
        """AfflictionModel.CanAfflictCardType (AfflictionModel.cs:175-178),
        default True. Tainted is the only game-source override (Skill only)."""
        return True

    def can_afflict(self, card: "Card") -> bool:
        """AfflictionModel.CanAfflict (AfflictionModel.cs:190-205).

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


@register_affliction
class RingingAffliction(Affliction):
    """Applied by RingingPower; blocks play after the turn's first card."""

    id = "ringing"
    name = "Ringing"


@register_affliction
class EntangledAffliction(Affliction):
    """Applied by TangledPower to Attack cards; raises their energy cost."""

    id = "entangled"
    name = "Entangled"


@register_affliction
class SmogAffliction(Affliction):
    """Applied by SmoggyPower to Skill cards; blocks playing them this turn."""

    id = "smog"
    name = "Smog"


@register_affliction
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


@register_affliction
class GalvanizedAffliction(Affliction):
    """Applied by GalvanicPower (Globe Head) to Power cards; playing a
    Galvanized card deals N damage to the player.

    IsStackable = true (Galvanized.cs:7) — see TaintedAffliction's note;
    GalvanicPower is the same dormant-on-content shape."""

    id = "galvanized"
    name = "Galvanized"
    is_stackable = True


@register_affliction
class HexedAffliction(Affliction):
    """Applied by HexPower (Spectral Knight); while present the card is
    Ethereal (exhausts if still in hand at turn end)."""

    id = "hexed"
    name = "Hexed"


@register_affliction
class BoundAffliction(Affliction):
    """Applied by ChainsOfBindingPower (the Queen) to drawn cards; only one
    Bound card may be played per turn."""

    id = "bound"
    name = "Bound"


ALL_AFFLICTIONS: dict[str, type[Affliction]] = dict(_AFFLICTION_CLASSES)

# Stable vocabulary (frozen append-only + capacity-padded; vocab.py). Mirrors
# full_env.py's CARD_IDS / run_env.py's RELIC_IDS wiring; it lives here
# rather than in full_env.py/run_env.py because this file owns the registry
# those constants are derived from.
AFFLICTION_IDS: list[str] = frozen_ids("afflictions", ALL_AFFLICTIONS)
AFFLICTION_INDEX: dict[str, int] = {aid: i for i, aid in enumerate(AFFLICTION_IDS)}
N_AFFLICTIONS = vocab_capacity("afflictions")
