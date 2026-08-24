"""``build_contract()`` — the SpireBot live-bot contract (Task 5).

The future C# mod's ``Contract.Load`` reads the JSON this produces as its
single source of truth for obs layout, vocab ids, game-id mapping and
action layout, so it must be built entirely from the live sim's own
constants and layout accessors (``sts2_rl/full_env.py``,
``sts2_rl/run_env.py``, ``sts2_rl/vocab.py``, ``sts2_rl/obs.py``) — nothing
here is a second, independently-maintained copy of a number that already
lives somewhere else.

``layout`` describes the RUN observation (``run_env.run_obs_layout()``):
the run obs embeds the combat block as its ``combat.*``-prefixed segments,
and that whole thing — not the standalone combat obs — is what the C# mod
feeds the model (see the run env's own module docstring).

``game_id_map`` inverts ``sts2_rl/conformance/idmap.py`` (cards, relics,
potions) and ``sts2_rl/conformance/ids.py`` (events) — the same exception
tables the SP2 conformance oracles already trust — rather than
re-deriving the game's naming convention from scratch. Powers and monsters
had no such table in this repo until Task A (``sts2_rl/live/game_ids.py``):
the conformance stream never needed a game-id mapping for them (replay
comparison keys those two off resolved runtime state, not a save-file id
list), so ``game_ids.py`` derives their ids directly from the decompiled
game's own ``ModelId`` computation instead.
"""
from __future__ import annotations

from .. import full_env, run_env
from ..afflictions import AFFLICTION_INDEX
from ..conformance import idmap
from ..conformance import ids as ids_mod
from ..enchantments import ENCHANTMENT_INDEX
from ..obs import ObsLayout, oid
from . import game_ids

# 2: v22 potion-discard action block (run_env.DISCARD_BASE, N_ACTIONS 243→253)
# — "actions.discard" added; consumers sizing the head off n_actions alone
# would silently mis-shape against a v1 model, so the version gates it.
CONTRACT_VERSION = 2

# kind -> {sim_id: vocab_index} (0-based; oid() below adds the +1 PAD offset)
_VOCAB_INDEX: dict[str, dict[str, int]] = {
    "cards": full_env.CARD_INDEX,
    "relics": full_env.RELIC_INDEX,
    "powers": full_env.POWER_INDEX,
    "monsters": full_env.MONSTER_INDEX,
    "potions": full_env.POTION_INDEX,
    "events": run_env.EVENT_INDEX,
    "purposes": run_env.PURPOSE_INDEX,
    "afflictions": AFFLICTION_INDEX,
    "enchantments": ENCHANTMENT_INDEX,
}


def _vocab_block() -> dict[str, dict[str, int]]:
    return {
        kind: {name: oid(idx) for name, idx in index.items()}
        for kind, index in _VOCAB_INDEX.items()
    }


def _seg_list(segments: list[tuple[str, int]]) -> list[dict]:
    out = []
    offset = 0
    for name, width in segments:
        out.append({"name": name, "offset": offset, "width": width})
        offset += width
    return out


def _layout_block(layout: ObsLayout) -> dict[str, list[dict]]:
    return {
        "f": _seg_list(layout.f_segments),
        "i": _seg_list(layout.i_segments),
    }


def _prefixed_game_id_map(
    prefix: str,
    sim_ids: list[str],
    index: dict[str, int],
    exceptions: dict[str, str],
) -> dict[str, int]:
    """``{"<PREFIX>.<SAVE_KEY>": oid}`` for every ``sim_id`` in ``sim_ids``.

    ``exceptions`` is the ``idmap`` module's ``save-key -> sim-id`` table
    (default rule: save key == sim id). Inverted here so the exception
    lands on the sim id it actually names, mirroring ``idmap``'s own
    ``_key()`` + exceptions lookup exactly (reused, not re-derived) —
    ``sim_card_id("CARD." + game_id_map_key)`` must round-trip back to the
    original sim id, which is what ``test_contract_game_id_map_round_trips_
    through_idmap`` checks.
    """
    inv_exceptions = {sim: key for key, sim in exceptions.items()}
    out: dict[str, int] = {}
    for sim_id in sim_ids:
        if sim_id not in index:
            continue  # dead frozen slot (class removed, index kept)
        save_key = inv_exceptions.get(sim_id, sim_id)
        game_id = f"{prefix}.{save_key.upper()}"
        out[game_id] = oid(index[sim_id])
    return out


def _event_game_id_map() -> dict[str, int]:
    out: dict[str, int] = {}
    for key, idx in run_env.EVENT_INDEX.items():
        game_id = ids_mod.event_game_id(key)
        out[game_id] = oid(idx)
    return out


def _game_id_map() -> dict[str, dict[str, int]]:
    return {
        "cards": _prefixed_game_id_map(
            "CARD", full_env.CARD_IDS, full_env.CARD_INDEX,
            idmap._CARD_EXCEPTIONS),
        "relics": _prefixed_game_id_map(
            "RELIC", full_env.RELIC_IDS, full_env.RELIC_INDEX,
            idmap._RELIC_EXCEPTIONS),
        "potions": _prefixed_game_id_map(
            "POTION", full_env.POTION_IDS, full_env.POTION_INDEX,
            idmap._POTION_EXCEPTIONS),
        "events": _event_game_id_map(),
        "powers": game_ids.power_game_id_map(full_env.POWER_INDEX),
        "monsters": game_ids.monster_game_id_map(full_env.MONSTER_INDEX),
        "afflictions": game_ids.affliction_game_id_map(AFFLICTION_INDEX),
        "enchantments": game_ids.enchantment_game_id_map(ENCHANTMENT_INDEX),
    }


def _actions_block() -> dict:
    return {
        "n_actions": run_env.N_ACTIONS,
        "combat": {
            "end_turn": 0,
            "play_base": full_env.COMBAT_PLAY_BASE,
            "max_hand": full_env.MAX_HAND,
            "max_enemies": full_env.MAX_ENEMIES,
            "potion_base": full_env.COMBAT_POTION_BASE,
            "max_potions": run_env.MAX_POTION_SLOTS,
        },
        "choice": {
            "base": run_env.CHOICE_BASE,
            "slots": run_env.CHOICE_SLOTS,
        },
        "select": {
            "base": run_env.SELECT_BASE,
            "max_candidates": run_env.MAX_SELECT_CANDIDATES,
        },
        "belt_potion": {
            "base": run_env.POTION_BASE,
            "slots": run_env.MAX_POTION_SLOTS,
        },
        "discard": {
            "base": run_env.DISCARD_BASE,
            "slots": run_env.MAX_POTION_SLOTS,
        },
    }


def build_contract() -> dict:
    """The whole contract, ready for ``json.dumps``."""
    layout = run_env.run_obs_layout()
    return {
        "contract_version": CONTRACT_VERSION,
        "combat_obs_schema": full_env.OBS_SCHEMA_VERSION,
        "run_obs_schema": run_env.RUN_OBS_SCHEMA_VERSION,
        "f_dim": layout.f_dim,
        "i_dim": layout.i_dim,
        "layout": _layout_block(layout),
        "vocab": _vocab_block(),
        "game_id_map": _game_id_map(),
        "actions": _actions_block(),
    }
