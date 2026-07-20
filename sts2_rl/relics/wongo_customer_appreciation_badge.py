from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class WongoCustomerAppreciationBadge(Relic):
    """WongoCustomerAppreciationBadge.cs — a purely cosmetic trophy: the
    source model declares only its Event rarity and has no hooks.

    Awarded for 2000 lifetime Wongo points, which accumulate in the SAVE
    file across runs (SaveManager.Progress.WongoPoints). A single run can
    earn at most 32+16+8 = 56 points, so this relic is unreachable within
    one run of the sim, which models no cross-run progression — it is
    registered so the pool is complete and constructible by id."""

    id = "wongo_customer_appreciation_badge"
    name = "Wongo Customer Appreciation Badge"
    rarity = RelicRarity.EVENT
