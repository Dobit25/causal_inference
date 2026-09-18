"""Build the P1-free semantic-preference conformance suite for T21 amendment v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path("configs/t21_v2_semantic_conformance.yaml")


def canonical(value: Any, *, newline: bool = False) -> bytes:
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return payload + (b"\n" if newline else b"")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def rank(seed: int, *parts: str) -> str:
    return hashlib.sha256((str(seed) + "|" + "|".join(parts)).encode()).hexdigest()


def production_expected(story: str, left: str, right: str) -> str:
    escaped_left, escaped_right = re.escape(left), re.escape(right)
    forward = [
        rf"{escaped_left} directly influences {escaped_right}",
        rf"changes in {escaped_left} directly cause changes in {escaped_right}",
        rf"{escaped_right} is directly affected by {escaped_left}",
        rf"a direct effect runs from {escaped_left} to {escaped_right}",
    ]
    reverse = [
        rf"{escaped_right} directly influences {escaped_left}",
        rf"changes in {escaped_right} directly cause changes in {escaped_left}",
        rf"{escaped_left} is directly affected by {escaped_right}",
        rf"a direct effect runs from {escaped_right} to {escaped_left}",
    ]
    if any(re.search(pattern, story, flags=re.IGNORECASE) for pattern in forward):
        return "forward"
    if any(re.search(pattern, story, flags=re.IGNORECASE) for pattern in reverse):
        return "reverse"
    if "does not establish which one influences the other" in story or "direction is not established" in story:
        return "ambiguous"
    raise ValueError("Production expected-answer parser could not classify story")


def make_story(label: str, left: str, right: str, template_index: int) -> tuple[str, dict[str, str | None]]:
    if label == "forward":
        source, target = left, right
        templates = [
            "{source} directly influences {target}.",
            "Changes in {source} directly cause changes in {target}.",
            "{target} is directly affected by {source}.",
            "A direct effect runs from {source} to {target}.",
        ]
    elif label == "reverse":
        source, target = right, left
        templates = [
            "{source} directly influences {target}.",
            "Changes in {source} directly cause changes in {target}.",
            "{target} is directly affected by {source}.",
            "A direct effect runs from {source} to {target}.",
        ]
    else:
        source = target = None
        templates = [
            "{left} and {right} are directly connected, but this description does not establish which one influences the other.",
            "There is a direct association between {left} and {right}; direction is not established.",
            "{right} and {left} have a direct connection, but this description does not establish which one influences the other.",
            "A direct relationship joins {left} with {right}; direction is not established.",
        ]
    clause = templates[template_index % len(templates)].format(source=source, target=target, left=left, right=right)
    intro = f"This synthetic example contains two measured quantities: {left} and {right}."
    return f"{intro} {clause}", {"source": source, "target": target}


def build(config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    seed = int(config["suite"]["seed"])
    lexicon = list(config["suite"]["public_alias_lexicon"])
    labels = [label for label, count in config["suite"]["allocation"].items() for _ in range(int(count))]
    random.Random(seed).shuffle(labels)
    rows = []
    agreements = 0
    for index, label in enumerate(labels):
        ordered_aliases = sorted(lexicon, key=lambda alias: rank(seed, f"case{index:03d}", alias))[:2]
        left, right = sorted(ordered_aliases)
        story, truth = make_story(label, left, right, index)
        parsed = production_expected(story, left, right)
        independent = label if (
            label == "ambiguous" and truth["source"] is None
            or label == "forward" and truth == {"source": left, "target": right}
            or label == "reverse" and truth == {"source": right, "target": left}
        ) else "invalid"
        agreements += int(parsed == independent == label)
        rows.append(
            {
                "schema_version": "fourgraph.p1_t21_v2_semantic_case.v1",
                "case_id": f"V2SEM{index:03d}",
                "requested_pair": {"left": left, "right": right},
                "story": story,
                "expected_class": label,
                "expected_probability_interval": (
                    [0.95, 0.999] if label == "forward" else [0.001, 0.05] if label == "reverse" else [0.45, 0.55]
                ),
                "template_index": index % 4,
                "production_expected": parsed,
                "independent_expected": independent,
                "P1_content_used": False,
            }
        )
    if agreements != 120:
        raise RuntimeError(f"Expected solvers disagree: {agreements}/120")
    smoke_ids = []
    for label in ("forward", "reverse", "ambiguous"):
        candidates = [row["case_id"] for row in rows if row["expected_class"] == label]
        smoke_ids.extend(sorted(candidates, key=lambda case: rank(seed, "smoke", case))[:4])
    smoke_ids.sort()
    smoke = {
        "schema_version": "fourgraph.p1_t21_v2_smoke_manifest.v1",
        "seed": seed,
        "case_ids": smoke_ids,
        "count": 12,
        "allocation": {label: sum(next(r for r in rows if r["case_id"] == case)["expected_class"] == label for case in smoke_ids) for label in ("forward", "reverse", "ambiguous")},
    }
    suite_bytes = b"".join(canonical(row, newline=True) for row in rows)
    smoke_bytes = canonical(smoke, newline=True)
    prompt_path = ROOT / config["prompt"]["path"]
    schema_path = ROOT / config["prompt"]["response_schema"]
    audit = {
        "schema_version": "fourgraph.p1_t21_v2_semantic_suite_audit.v1",
        "task": "T21_AMENDMENT_V2_CONFORMANCE",
        "counts": {
            "cases": len(rows),
            "forward": sum(r["expected_class"] == "forward" for r in rows),
            "reverse": sum(r["expected_class"] == "reverse" for r in rows),
            "ambiguous": sum(r["expected_class"] == "ambiguous" for r in rows),
            "expected_solver_agreements": agreements,
            "smoke_cases": len(smoke_ids),
        },
        "hashes": {
            "suite_sha256": sha(suite_bytes),
            "smoke_manifest_sha256": sha(smoke_bytes),
            "prompt_sha256": sha(prompt_path.read_bytes()),
            "response_schema_sha256": sha(schema_path.read_bytes()),
            "config_sha256": sha(canonical(config)),
        },
        "evidence_boundary": {
            "P1_data_story_answer_or_split_accessed": False,
            "api_calls": 0,
            "holdout_accessed": False,
        },
        "verdict": {
            "suite_frozen": True,
            "production_independent_agreement_120_of_120": True,
            "smoke_execution_authorized": True,
            "full_execution_authorized": False,
            "development_rerun_authorized": False,
        },
    }
    return rows, smoke, audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    config = yaml.safe_load((ROOT / args.config).read_text(encoding="utf-8"))
    rows, smoke, audit = build(config)
    outputs = {
        config["outputs"]["suite"]: b"".join(canonical(row, newline=True) for row in rows),
        config["outputs"]["smoke_manifest"]: canonical(smoke, newline=True),
        config["outputs"]["suite_audit"]: canonical(audit, newline=True),
    }
    for relative, payload in outputs.items():
        path = ROOT / relative
        if args.check:
            if path.read_bytes() != payload:
                raise RuntimeError(f"Byte replay mismatch: {relative}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    print(json.dumps({"cases": 120, "agreements": 120, "smoke": 12, "api_calls": 0}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
