"""Relics — mirroring STS2's RelicModel (src/Core/Models/Relics).

Every Ironclad-obtainable relic from the standard pools — SharedRelicPool
(118 relics) + IroncladRelicPool (8) — one relic per module. Event-pool relics
are out of scope. See `base.py` for the `Relic` base class, hook mapping, and
the stub convention for purely out-of-combat relics.

Each relic module calls `@register_relic`; importing this package imports them
all (via `pkgutil` auto-discovery below), binds every relic class into the
package namespace (so `from sts2_rl.relics import Akabeko` works), and freezes
the catalogue as `ALL_RELICS`. Build any relic by id with `make_relic("id")`.
"""
from __future__ import annotations

import importlib
import pkgutil

from .base import (
    Relic,
    RelicRarity,
    _RELIC_CLASSES,
    make_relic,
    register_relic,
)

# Import every relic module so its @register_relic decorator runs.
for _module_info in pkgutil.iter_modules(__path__):
    if _module_info.name != "base":
        importlib.import_module(f"{__name__}.{_module_info.name}")

# Freeze the catalogue and bind each relic class into the package namespace so
# callers can `from sts2_rl.relics import <ClassName>`.
ALL_RELICS: dict[str, type[Relic]] = dict(_RELIC_CLASSES)
globals().update({cls.__name__: cls for cls in ALL_RELICS.values()})

__all__ = [
    "Relic",
    "RelicRarity",
    "make_relic",
    "register_relic",
    "ALL_RELICS",
    *sorted(cls.__name__ for cls in ALL_RELICS.values()),
]
