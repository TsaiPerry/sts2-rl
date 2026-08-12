"""CLI: ``py -m sts2_rl.live.export_contract --out contract.json``.

Writes ``build_contract()`` to disk. The generated file is a build
artifact (not source) — see the repo's ``.gitignore``.
"""
from __future__ import annotations

import argparse
import json

from .contract import build_contract


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", default="contract.json",
        help="Output path for the generated contract JSON (default: contract.json)")
    args = parser.parse_args(argv)

    contract = build_contract()
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(contract, f, indent=1)
        f.write("\n")
    print(f"wrote {args.out} ({len(json.dumps(contract))} bytes)")


if __name__ == "__main__":
    main()
