"""Task 5 (SpireBot live bot): the contract exporter's tests.

The contract is the single source of truth the future C# mod's
``Contract.Load`` reads for obs layout, vocab ids, game-id mapping and
action layout — built from ``sts2_rl/live/contract.py:build_contract()``.
"""
import json

from sts2_rl import full_env, run_env
from sts2_rl.live.contract import build_contract


def test_contract_dims_match_layout():
    c = build_contract()
    layout = run_env.run_obs_layout()  # the real accessor (lives in run_env,
    # not full_env — the brief's pseudo-call was schematic)
    assert c["f_dim"] == sum(w for _, w in layout.f_segments)
    assert c["i_dim"] == sum(w for _, w in layout.i_segments)
    assert c["combat_obs_schema"] == full_env.OBS_SCHEMA_VERSION == 8
    assert c["run_obs_schema"] == run_env.RUN_OBS_SCHEMA_VERSION == 12


def test_contract_layout_offsets_are_contiguous():
    c = build_contract()
    for half in ("f", "i"):
        off = 0
        for seg in c["layout"][half]:
            assert seg["offset"] == off
            off += seg["width"]


def test_contract_vocab_matches_frozen_vocab():
    c = build_contract()
    from sts2_rl.obs import oid
    assert c["vocab"]["cards"] == {
        name: oid(idx) for name, idx in full_env.CARD_INDEX.items()
    }
    assert c["vocab"]["relics"] == {
        name: oid(idx) for name, idx in full_env.RELIC_INDEX.items()
    }
    assert c["vocab"]["events"] == {
        name: oid(idx) for name, idx in run_env.EVENT_INDEX.items()
    }


def test_contract_game_id_map_covers_ironclad_cards():
    c = build_contract()
    assert len(c["game_id_map"]["cards"]) > 0
    # every mapped value must be a valid vocab id
    valid = set(c["vocab"]["cards"].values())
    assert set(c["game_id_map"]["cards"].values()) <= valid


def test_contract_game_id_map_round_trips_through_idmap():
    """Every game_id_map card entry must resolve back to its own sim id via
    the conformance idmap module — the contract's game ids aren't a
    parallel, possibly-diverging guess."""
    from sts2_rl.conformance import idmap
    c = build_contract()
    inv_vocab = {v: k for k, v in c["vocab"]["cards"].items()}
    for game_id, oid_val in c["game_id_map"]["cards"].items():
        sim_id = idmap.sim_card_id(game_id)
        assert sim_id == inv_vocab[oid_val]


def test_contract_action_layout_matches_run_env():
    c = build_contract()
    a = c["actions"]
    assert a["n_actions"] == run_env.N_ACTIONS
    assert a["combat"]["play_base"] == full_env.COMBAT_PLAY_BASE
    assert a["combat"]["max_hand"] == full_env.MAX_HAND
    assert a["combat"]["max_enemies"] == full_env.MAX_ENEMIES
    assert a["combat"]["potion_base"] == full_env.COMBAT_POTION_BASE
    assert a["choice"]["base"] == run_env.CHOICE_BASE
    assert a["choice"]["slots"] == run_env.CHOICE_SLOTS
    assert a["select"]["base"] == run_env.SELECT_BASE
    assert a["select"]["max_candidates"] == run_env.MAX_SELECT_CANDIDATES
    assert a["belt_potion"]["base"] == run_env.POTION_BASE
    assert a["belt_potion"]["slots"] == run_env.MAX_POTION_SLOTS
    assert a["discard"]["base"] == run_env.DISCARD_BASE
    assert a["discard"]["slots"] == run_env.MAX_POTION_SLOTS


def test_contract_is_json_serializable(tmp_path):
    p = tmp_path / "contract.json"
    p.write_text(json.dumps(build_contract()))
    assert json.loads(p.read_text())["contract_version"] == 2


def test_contract_game_id_map_covers_powers_and_monsters():
    c = build_contract()
    for kind in ("powers", "monsters"):
        assert len(c["game_id_map"][kind]) > 0
        valid = set(c["vocab"][kind].values())
        assert set(c["game_id_map"][kind].values()) <= valid


def test_contract_game_id_map_power_coverage_floor():
    # Every one of vocab.json's 138 power ids was verified (Task A research)
    # to resolve to a real decompiled PowerModel subclass named
    # PascalCase(id) + "Power" -- zero exceptions found. Coverage must stay
    # at the full 138 unless vocab.json changes (frozen).
    c = build_contract()
    assert len(c["game_id_map"]["powers"]) == 138


def test_contract_game_id_map_monster_coverage_floor():
    # 108 of vocab.json's 111 monster ids match a concrete decompiled
    # MonsterModel subclass verbatim; the other 3 (MachineMonster,
    # _BattleFriend, _Cultist) are sim-internal abstract base classes with
    # no game-source counterpart and stay unmapped (see game_ids.py).
    c = build_contract()
    assert len(c["game_id_map"]["monsters"]) == 108


def test_contract_game_id_map_power_probe_vulnerable():
    c = build_contract()
    assert c["game_id_map"]["powers"]["POWER.VULNERABLE_POWER"] \
        == c["vocab"]["powers"]["vulnerable"]


def test_contract_game_id_map_monster_probe_ironclad_act1():
    # Aeonglass: an Ironclad act-1 (Glory) monster.
    c = build_contract()
    assert c["game_id_map"]["monsters"]["MONSTER.AEONGLASS"] \
        == c["vocab"]["monsters"]["Aeonglass"]


def test_contract_game_id_map_round_trips_through_game_ids_module():
    """Every game_id_map powers/monsters entry must resolve back to its own
    sim id via game_ids.py's own reverse resolvers -- the contract's game
    ids aren't a parallel, possibly-diverging guess."""
    from sts2_rl.live import game_ids
    c = build_contract()
    for kind, resolver in (
        ("powers", game_ids.sim_power_id),
        ("monsters", game_ids.sim_monster_id),
    ):
        inv_vocab = {v: k for k, v in c["vocab"][kind].items()}
        for game_id, oid_val in c["game_id_map"][kind].items():
            sim_id = resolver(game_id)
            assert sim_id == inv_vocab[oid_val]


def test_contract_game_id_map_covers_afflictions_and_enchantments():
    c = build_contract()
    for kind in ("afflictions", "enchantments"):
        assert len(c["game_id_map"][kind]) > 0
        valid = set(c["vocab"][kind].values())
        assert set(c["game_id_map"][kind].values()) <= valid


def test_contract_game_id_map_affliction_coverage_floor():
    # Every one of the 7 ported affliction sim ids (ringing/entangled/smog/
    # tainted/galvanized/hexed/bound) matches a decompiled AfflictionModel
    # subclass verbatim (PascalCase(sim_id), no suffix -- see game_ids.py
    # affliction_game_id); zero exceptions found (Ringing.cs, Smog.cs,
    # Tainted.cs, Entangled.cs, Galvanized.cs, Hexed.cs, Bound.cs under
    # Slay the Spire 2/src/Core/Models/Afflictions).
    c = build_contract()
    assert len(c["game_id_map"]["afflictions"]) == 7


def test_contract_game_id_map_enchantment_coverage_floor():
    # All 20 of the sim's ported enchantment ids match a decompiled
    # EnchantmentModel subclass under Slay the Spire 2/src/Core/Models/
    # Enchantments; 19 are PascalCase(sim_id) verbatim, one exception
    # ("souls" -> "SoulsPower.cs", class SoulsPower) mirrors the POWER/
    # MONSTER exceptions-dict pattern (game_ids.py enchantment_game_id).
    # (enchantments.py's own header comment claims only 19 are ported and
    # names Momentum as unported -- that comment is stale: MomentumEnchantment
    # is `@register_enchantment`'d and present in ENCHANTMENT_INDEX.)
    c = build_contract()
    assert len(c["game_id_map"]["enchantments"]) == 20


def test_contract_game_id_map_affliction_probe_ringing():
    c = build_contract()
    assert c["game_id_map"]["afflictions"]["AFFLICTION.RINGING"] \
        == c["vocab"]["afflictions"]["ringing"]


def test_contract_game_id_map_affliction_probe_tainted():
    c = build_contract()
    assert c["game_id_map"]["afflictions"]["AFFLICTION.TAINTED"] \
        == c["vocab"]["afflictions"]["tainted"]


def test_contract_game_id_map_enchantment_probe_perfect_fit():
    c = build_contract()
    assert c["game_id_map"]["enchantments"]["ENCHANTMENT.PERFECT_FIT"] \
        == c["vocab"]["enchantments"]["perfect_fit"]


def test_contract_game_id_map_enchantment_probe_souls_exception():
    # Confirms the "souls" -> SoulsPower exception (Enchantments/
    # SoulsPower.cs: `public sealed class SoulsPower : EnchantmentModel`).
    c = build_contract()
    assert c["game_id_map"]["enchantments"]["ENCHANTMENT.SOULS_POWER"] \
        == c["vocab"]["enchantments"]["souls"]


def test_contract_game_id_map_round_trips_through_game_ids_module_afflictions_enchantments():
    from sts2_rl.live import game_ids
    c = build_contract()
    for kind, resolver in (
        ("afflictions", game_ids.sim_affliction_id),
        ("enchantments", game_ids.sim_enchantment_id),
    ):
        inv_vocab = {v: k for k, v in c["vocab"][kind].items()}
        for game_id, oid_val in c["game_id_map"][kind].items():
            sim_id = resolver(game_id)
            assert sim_id == inv_vocab[oid_val]


def test_game_ids_monsters_without_game_class_are_documented_and_unmapped():
    from sts2_rl.live import game_ids
    from sts2_rl import full_env
    c = build_contract()
    for sim_id in game_ids.MONSTERS_WITHOUT_GAME_CLASS:
        assert sim_id in full_env.MONSTER_INDEX
        oid_val = c["vocab"]["monsters"][sim_id]
        assert oid_val not in set(c["game_id_map"]["monsters"].values())
