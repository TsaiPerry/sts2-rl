from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Circlet(Relic):
    """Circlet.cs — `RelicFactory.FallbackRelic` (RelicFactory.cs:13): the
    relic handed out when a pull finds nothing.

    `PullNextRelicFromFront` is
    `grabBag.PullFromFront(rarity, filter, runState) ?? FallbackRelic`
    (RelicFactory.cs:47), and `PullFromFront` returns null the moment the
    ROLLED RARITY's deque is empty (RelicGrabBag.cs:129-146) — it never
    reaches into another rarity. So a Circlet is what a run gets once it has
    exhausted a rarity, and it does nothing: the class declares no hooks at
    all, only `Rarity => None` and `IsStackable => true`.

    `IsStackable => true` (Circlet.cs:9) is what lets a second one be
    obtained: once a rarity is exhausted every later pull of it hands out
    another Circlet. The sim needs no flag for that — `RunState.add_relic`
    appends without a duplicate guard, so they already pile up.
    """

    id = "circlet"
    name = "Circlet"
    # `RelicRarity.None` — in no grab-bag deque, so it is never offered by a
    # reward, a shop or a chest; only RelicFactory's fallback produces it.
    rarity = RelicRarity.NONE
    is_allowed_in_shops = False
