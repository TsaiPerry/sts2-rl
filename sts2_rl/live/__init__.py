"""SpireBot live-bot support: the contract exporter.

``sts2_rl/live/contract.py:build_contract()`` is the single source of truth
the future C# mod's ``Contract.Load`` reads for obs layout, vocab ids,
game-id mapping and action layout. ``export_contract.py`` is its CLI:
``py -m sts2_rl.live.export_contract --out contract.json``.
"""
