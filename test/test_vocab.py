"""vocab.py — frozen append-only vocabularies + reserved capacities.

The contract under test: once an id enters vocab.json its index never
changes (append-only, stale ids retained), and every layout constant is the
reserved capacity, so porting content never changes obs/action dims or
scrambles existing indices (the two failure modes that force retrains).
"""
import json

import pytest

from sts2_rl import full_env, run_env
from sts2_rl.vocab import CAPACITIES, capacity, frozen_ids, merge_frozen


# ═════════════════════════════════════════════════════════════════════════
# merge_frozen
# ═════════════════════════════════════════════════════════════════════════

def test_merge_appends_new_ids_sorted_after_frozen():
    merged, new = merge_frozen(["zeta", "alpha"], ["alpha", "mu", "beta", "zeta"])
    assert merged == ["zeta", "alpha", "beta", "mu"]
    assert new == ["beta", "mu"]


def test_merge_keeps_stale_frozen_ids():
    # "gone" is no longer registered but keeps its slot: dropping it would
    # shift every later index and scramble trained weights.
    merged, new = merge_frozen(["a", "gone", "b"], ["a", "b"])
    assert merged == ["a", "gone", "b"]
    assert new == []


def test_merge_is_idempotent():
    merged, new = merge_frozen(["a", "b"], ["b", "a"])
    assert merged == ["a", "b"] and new == []


# ═════════════════════════════════════════════════════════════════════════
# frozen_ids persistence
# ═════════════════════════════════════════════════════════════════════════

def test_seeds_file_on_first_use(tmp_path):
    path = tmp_path / "vocab.json"
    ids = frozen_ids("cards", ["strike", "bash", "defend"], path=path)
    assert ids == ["bash", "defend", "strike"]          # first seed: sorted
    assert json.loads(path.read_text())["cards"] == ids


def test_reload_preserves_order_and_appends_at_end(tmp_path):
    path = tmp_path / "vocab.json"
    first = frozen_ids("cards", ["strike", "bash"], path=path)
    # A new registration sorting BEFORE existing ids still lands at the end.
    second = frozen_ids("cards", ["strike", "bash", "anger"], path=path)
    assert second == first + ["anger"]
    # Existing indices are untouched.
    for i, cid in enumerate(first):
        assert second[i] == cid
    # And the append was persisted.
    assert frozen_ids("cards", ["strike", "bash", "anger"], path=path) == second


def test_kinds_are_independent(tmp_path):
    path = tmp_path / "vocab.json"
    frozen_ids("cards", ["strike"], path=path)
    frozen_ids("relics", ["burning_blood"], path=path)
    data = json.loads(path.read_text())
    assert data == {"cards": ["strike"], "relics": ["burning_blood"]}


def test_capacity_overflow_raises(tmp_path):
    path = tmp_path / "vocab.json"
    too_many = [f"card{i:04d}" for i in range(CAPACITIES["cards"] + 1)]
    with pytest.raises(RuntimeError, match="reserved capacity"):
        frozen_ids("cards", too_many, path=path)


# ═════════════════════════════════════════════════════════════════════════
# Live wiring: the envs' vocabularies obey the contract
# ═════════════════════════════════════════════════════════════════════════

_ENV_VOCABS = [
    ("cards", full_env.CARD_IDS, full_env.N_CARDS),
    ("potions", full_env.POTION_IDS, full_env.N_POTIONS),
    ("powers", full_env.POWER_IDS, full_env.N_POWERS),
    ("monsters", full_env.MONSTER_IDS, full_env.N_MONSTERS),
    ("relics", run_env.RELIC_IDS, run_env.N_RELICS),
    ("events", run_env.EVENT_IDS, run_env.N_EVENTS),
    ("purposes", run_env.PURPOSE_IDS, run_env.N_PURPOSES),
]


@pytest.mark.parametrize("kind,ids,n", _ENV_VOCABS, ids=[v[0] for v in _ENV_VOCABS])
def test_layout_constants_are_capacities(kind, ids, n):
    assert n == capacity(kind)
    assert len(ids) <= n, (
        f"'{kind}' outgrew its reserved capacity — vocab.frozen_ids should "
        f"have raised at import")
    assert len(set(ids)) == len(ids)


@pytest.mark.parametrize("kind,ids,n", _ENV_VOCABS, ids=[v[0] for v in _ENV_VOCABS])
def test_env_vocab_matches_persisted_registry(kind, ids, n):
    """The import-time list IS the persisted frozen order (envs and
    checkpoints trained on other machines must agree on it)."""
    from sts2_rl.vocab import VOCAB_PATH, _load
    assert _load(VOCAB_PATH).get(kind) == ids


def test_registered_content_is_covered():
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.relics import ALL_RELICS
    assert set(_CARD_CLASSES) <= set(full_env.CARD_IDS)
    assert set(ALL_RELICS) <= set(run_env.RELIC_IDS)


def test_capacities_cover_full_game_totals():
    """Counted from the decompiled game source (2026-07): the capacities must
    hold the COMPLETE game so porting content is fine-tune-only, never a
    dim change. Cards 577, relics 298, powers 260, monsters 121, potions 64,
    events 68."""
    game_totals = {
        "cards": 577, "relics": 298, "powers": 260,
        "monsters": 121, "potions": 64, "events": 68,
    }
    for kind, total in game_totals.items():
        assert CAPACITIES[kind] >= total, (kind, total, CAPACITIES[kind])
