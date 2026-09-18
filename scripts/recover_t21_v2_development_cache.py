"""Recover a deterministic first-seen cache after the documented overlapping-run incident."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/raw/p1_t21_v2_development/openai_calls.jsonl"
TARGET = ROOT / "results/raw/p1_t21_v2_development/openai_calls_recovered.jsonl"


def canonical(row: dict) -> bytes:
    return (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def recover() -> tuple[bytes, dict]:
    seen: set[tuple[str, int]] = set()
    retained: list[dict] = []
    duplicate_rows = 0
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = (str(row["call_id"]), int(row["attempt"]))
        if key in seen:
            duplicate_rows += 1
            continue
        seen.add(key)
        retained.append(row)
    return b"".join(canonical(row) for row in retained), {
        "source_rows": len(retained) + duplicate_rows,
        "retained_first_seen_rows": len(retained),
        "duplicate_rows_preserved_only_in_incident_log": duplicate_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload, summary = recover()
    if args.check:
        expected_rows = {
            (row["call_id"], int(row["attempt"])): row
            for row in map(json.loads, payload.decode("utf-8").splitlines())
        }
        target_rows = {
            (row["call_id"], int(row["attempt"])): row
            for row in map(json.loads, TARGET.read_text(encoding="utf-8").splitlines())
        }
        if any(target_rows.get(key) != row for key, row in expected_rows.items()):
            raise RuntimeError("Recovered cache does not preserve every deterministic first-seen row")
    else:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_bytes(payload)
    print(json.dumps({**summary, "check": args.check}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
