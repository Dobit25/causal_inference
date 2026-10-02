"""Offline metadata repair for already recorded Phase D normalized artifacts.

It does not rerun a fit or alter a graph; it copies frozen execution identity
metadata from the raw artifact into its paired normalized record.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from adapters.common import canonical_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", default="results/p1v3_statistical_ensemble/raw")
    parser.add_argument("--normalized-root", default="results/p1v3_statistical_ensemble/normalized")
    args = parser.parse_args()
    raw_root, normalized_root = ROOT / args.raw_root, ROOT / args.normalized_root
    changed = 0
    for raw_path in sorted(raw_root.glob("*.json")):
        normalized_path = normalized_root / raw_path.name
        if not normalized_path.is_file():
            continue
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
        job = raw["job"]
        normalized["config_hash"] = job["config_hash"]
        normalized["dependency_hashes"] = job["dependency_hashes"]
        normalized_path.write_bytes(canonical_json(normalized))
        changed += 1
    print(json.dumps({"changed": changed, "fits_rerun": 0}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
