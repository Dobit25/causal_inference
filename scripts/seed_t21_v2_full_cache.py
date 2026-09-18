"""Seed T21-v2 with the unchanged full-story LLM calls from frozen T21-v1."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/raw/p1_t21/openai_calls.jsonl"
TARGET = ROOT / "results/raw/p1_t21_v2_development/openai_calls.jsonl"


def canonical(row: dict) -> bytes:
    return (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def payload() -> bytes:
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    selected = [row for row in rows if ":llm_graph:full" in str(row.get("call_id", ""))]
    if len(selected) != 20 or any(int(row["attempt"]) != 0 for row in selected):
        raise RuntimeError("Frozen T21-v1 cache does not contain exactly 20 first-attempt full-story calls")
    selected.sort(key=lambda row: row["call_id"])
    return b"".join(canonical(row) for row in selected)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = payload()
    if args.check:
        expected_rows = {
            (row["call_id"], int(row["attempt"])): row
            for row in map(json.loads, expected.decode("utf-8").splitlines())
        }
        target_rows = {
            (row["call_id"], int(row["attempt"])): row
            for row in map(json.loads, TARGET.read_text(encoding="utf-8").splitlines())
        }
        if any(target_rows.get(key) != row for key, row in expected_rows.items()):
            raise RuntimeError("T21-v2 cache does not preserve the frozen T21-v1 full-story subset")
    else:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_bytes(expected)
    print(json.dumps({"reused_calls": 20, "target": str(TARGET.relative_to(ROOT)), "check": args.check}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
