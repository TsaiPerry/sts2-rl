"""RestSiteOption — an extra rest-site action contributed by a card or relic
(mirrors STS2's Entities.RestSite.RestSiteOption / the AbstractModel hook
Hook.TryModifyRestSiteOptions, which iterates deck cards then relics —
IterateHookListeners). Shared by cards/base.py and relics/base.py;
relics/base.py re-exports it so existing `from .base import RestSiteOption`
imports across the relics package keep working unchanged.
"""
from __future__ import annotations


class RestSiteOption:
    """`key` mirrors the source's OptionId; `on_select(run)` performs the
    effect (RestSiteOption.OnSelect)."""

    def __init__(self, key: str, on_select) -> None:
        self.key = key
        self.on_select = on_select

    def __repr__(self) -> str:
        return f"RestSiteOption({self.key})"
