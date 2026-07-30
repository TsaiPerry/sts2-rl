from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


def _basic_with_tag(deck, tag: str, last: bool = False):
    """The first (or last) Basic-rarity deck card carrying `tag`
    (Leafy Poultice transforms the first Strike/Defend)."""
    from ..cards import CardRarity

    matches = [
        c for c in deck if c.rarity == CardRarity.BASIC and tag in c.tags
    ]
    if not matches:
        return None
    return matches[-1] if last else matches[0]


@register_relic
class LeafyPoultice(Relic):
    """LeafyPoultice.cs — lose 12 Max HP; transform a basic Strike and a
    basic Defend (the deck's first of each)."""

    id = "leafy_poultice"
    name = "Leafy Poultice"
    rarity = RelicRarity.ANCIENT
    MAX_HP = 12

    def after_obtained(self, run) -> None:
        run.lose_max_hp(self.MAX_HP)
        # LeafyPoultice.cs:36 is `CardCmd.Transform([...], Owner.PlayerRng.
        # Transformations)` and the port passed no stream, so `run.transform_card`
        # fell to the shared-rng arm and took ZERO draws where the game takes two.
        # Unlike relic/claws (whose CardTransformations carry an explicit
        # Replacement, so GetReplacement never touches the Rng --
        # CardTransformation.cs:55-59) this relic uses the single-argument
        # `new CardTransformation(cardModel)` ctor (:30, :34), which leaves
        # Replacement null and falls through to
        # CardFactory.CreateRandomCardForTransform, which DOES draw. So both
        # replacement cards AND every later Transformations draw in the run
        # diverged. `pick_rng=` is what relics/pandoras_box.py, relics/astrolabe.py
        # and events/whispering_hollow.py already pass.
        pick_rng = (run.player_rng.transformations
                    if run.player_rng is not None else None)
        for tag in ("strike", "defend"):
            card = _basic_with_tag(run.deck, tag)
            if card is not None:
                run.transform_card(card, pick_rng=pick_rng)
