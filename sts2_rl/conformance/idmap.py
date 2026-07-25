"""Map RunReplays save ids (CARD.X / RELIC.X / POTION.X) to sim registry ids.

Default rule: strip the prefix, lowercase. Exceptions are collected empirically
(Task 3 Step 2 dumps unmapped ids) — keep this table SMALL and evidence-based;
a missing mapping is reported as part of a floor divergence, never a crash."""
from __future__ import annotations

_CARD_EXCEPTIONS = {
    "strike_ironclad": "strike",
    "defend_ironclad": "defend",
}
_RELIC_EXCEPTIONS: dict[str, str] = {}
_POTION_EXCEPTIONS: dict[str, str] = {}


def _key(save_id: str) -> str:
    return save_id.split(".", 1)[-1].lower()


def sim_card_id(save_id: str) -> str | None:
    from ..cards.base import _CARD_CLASSES
    k = _CARD_EXCEPTIONS.get(_key(save_id), _key(save_id))
    return k if k in _CARD_CLASSES else None


def sim_relic_id(save_id: str) -> str | None:
    from ..relics import ALL_RELICS
    k = _RELIC_EXCEPTIONS.get(_key(save_id), _key(save_id))
    return k if k in ALL_RELICS else None


def sim_potion_id(save_id: str) -> str | None:
    # ALL_POTIONS is the *implemented* catalogue; POTION_POOL is the full
    # reward/shop roster the sim also tracks as _ParityPotion placeholders
    # (Character.PotionPool ∪ SharedPotionPool). A placeholder the sim
    # legitimately carries in the belt (e.g. MazalethsGift) must map to its id,
    # not None — otherwise the floor-potion diff misreads a correctly-held
    # placeholder as a divergence and the resync drops it (un-filling a slot
    # the game had full). Both registries key on the snake_case id.
    from ..potion_pools import _POOL_RARITY
    from ..potions import ALL_POTIONS
    k = _POTION_EXCEPTIONS.get(_key(save_id), _key(save_id))
    return k if (k in ALL_POTIONS or k in _POOL_RARITY) else None
