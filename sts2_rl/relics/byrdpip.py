from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Byrdpip(Relic):
    """Byrdpip.cs — granted by Byrdonis Egg's HATCH rest-site option
    (HatchRestSiteOption.OnSelect: RelicCmd.Obtain<Byrdpip>). AfterObtained
    transforms every Byrdonis Egg card in the deck into ByrdSwoop, a real
    playable card. The source also spawns a decorative pet at combat start
    (Monsters/Byrdpip.cs), but that pet has 9999 HP, a hidden health bar,
    and a move state machine that does nothing (NOTHING_MOVE) — pure
    animation flavor for ByrdSwoop's attack, no combat mechanics — so the
    sim omits it, matching Pael's Legion's precedent of modeling only a pet
    relic's mechanical payoff, not an actual pet creature."""

    id = "byrdpip"
    name = "Byrdpip"
    rarity = RelicRarity.EVENT
    adds_pet = True

    def after_obtained(self, run) -> None:
        from ..cards import make_card
        for card in list(run.deck):
            if card.id == "byrdonis_egg":
                run.transform_card(card, into=make_card("byrd_swoop"))
