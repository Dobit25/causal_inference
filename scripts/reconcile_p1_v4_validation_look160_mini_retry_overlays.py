"""Build an immutable effective response view from raw records and retry overlays.

This is an offline reconciliation only. It never calls a provider, reads Oracle,
or modifies the raw response cache.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_validation_look160_mini_effective_overlay_reconciliation.yaml"


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def sha_path(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_immutable(path: Path, body: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != body:
        raise RuntimeError(f"artifact drift: {path}")
    if not path.exists():
        path.write_bytes(body)
    return sha_bytes(body)


def main() -> None:
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    raw_path = ROOT / cfg["parents"]["raw_responses"]
    if sha_path(raw_path) != cfg["parents"]["raw_responses_sha256"]:
        raise RuntimeError("raw response hash drift")
    raw = read_jsonl(raw_path)
    raw_by_id = {}
    duplicate_raw = []
    for row in raw:
        logical_id = row.get("logical_id")
        if logical_id in raw_by_id:
            duplicate_raw.append(logical_id)
        raw_by_id[logical_id] = row
    if len(raw) != cfg["scope"]["terminal_raw_records"] or len(raw_by_id) != len(raw):
        raise RuntimeError("raw record count or uniqueness check failed")

    raw_provider_ids = {k for k, v in raw_by_id.items() if v.get("status") == "provider_error"}
    overlays: dict[str, dict] = {}
    overlay_sources: dict[str, str] = {}
    overlay_hashes = {}
    overlay_statuses = Counter()
    for spec in cfg["overlays"]:
        path = ROOT / spec["path"]
        actual_hash = sha_path(path)
        if actual_hash != spec["sha256"]:
            raise RuntimeError(f"overlay hash drift: {spec['name']}")
        overlay_hashes[spec["name"]] = actual_hash
        rows = read_jsonl(path)
        for row in rows:
            logical_id = row.get("logical_id")
            if logical_id in overlays:
                raise RuntimeError(f"duplicate overlay logical id: {logical_id}")
            if logical_id not in raw_provider_ids:
                raise RuntimeError(f"overlay is not replacing a raw provider error: {logical_id}")
            if row.get("status") == "provider_error":
                raise RuntimeError(f"overlay still has provider error: {logical_id}")
            if not row.get("raw_text") or not row.get("response_sha256"):
                raise RuntimeError(f"overlay has no semantic response hash/text: {logical_id}")
            overlays[logical_id] = row
            overlay_sources[logical_id] = spec["name"]
            overlay_statuses[row.get("status")] += 1

    if set(overlays) != raw_provider_ids:
        missing = sorted(raw_provider_ids - set(overlays))
        unexpected = sorted(set(overlays) - raw_provider_ids)
        raise RuntimeError(f"overlay coverage mismatch; missing={missing}; unexpected={unexpected}")

    effective = []
    source_counts = Counter()
    for row in raw:
        logical_id = row["logical_id"]
        if row.get("status") == "provider_error":
            replacement = overlays[logical_id]
            effective.append(replacement)
            source_counts["retry_overlay"] += 1
        else:
            effective.append(row)
            source_counts["raw"] += 1
    if len(effective) != 1920 or len({row["logical_id"] for row in effective}) != 1920:
        raise RuntimeError("effective view is not exactly 1920 unique records")
    statuses = Counter(row.get("status") for row in effective)
    if statuses.get("provider_error", 0) != 0:
        raise RuntimeError("effective view still contains provider errors")
    if sum(statuses.values()) != 1920:
        raise RuntimeError("effective status counts do not sum to 1920")

    body = b"".join(canonical_json(row) for row in effective)
    output_path = ROOT / cfg["outputs"]["effective_responses"]
    output_hash = write_immutable(output_path, body)
    replay_body = b"".join(canonical_json(row) for row in effective)
    replay_hash = sha_bytes(replay_body)
    if replay_hash != output_hash:
        raise RuntimeError("byte-for-byte replay hash mismatch")

    audit = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_effective_overlay_reconciliation_audit.v1",
        "status": "PASS_EFFECTIVE_VIEW_RECONCILED",
        "offline_only": True,
        "planned_logical_calls": 2640,
        "raw_terminal_records": len(raw),
        "effective_records": len(effective),
        "raw_unique_logical_ids": len(raw_by_id),
        "effective_unique_logical_ids": len({row["logical_id"] for row in effective}),
        "raw_provider_error_count": len(raw_provider_ids),
        "overlay_replacements": len(overlays),
        "unresolved_provider_errors": 0,
        "duplicate_raw_ids": duplicate_raw,
        "overlay_statuses": dict(sorted(overlay_statuses.items())),
        "effective_statuses": dict(sorted(statuses.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "raw_responses_sha256": sha_path(raw_path),
        "overlay_hashes": overlay_hashes,
        "effective_responses_sha256": output_hash,
        "byte_for_byte_replay": replay_hash == output_hash,
        "raw_records_immutable": True,
        "api_calls": 0,
        "oracle_access": 0,
        "holdout_access": 0,
        "metric_calculation": False,
        "semantic_rescore": False,
    }
    audit_path = ROOT / cfg["outputs"]["reconciliation_audit"]
    audit_hash = write_immutable(audit_path, canonical_json(audit))
    report = "\n".join(
        [
            "# P1V4 look-160 effective overlay reconciliation",
            "",
            "Status: **PASS_EFFECTIVE_VIEW_RECONCILED**",
            "",
            "This was an offline reconciliation. Raw provider-error records remain immutable; retry responses are applied only in the derived effective view.",
            "",
            f"- Raw terminal records: **{len(raw)}/1920**",
            f"- Effective records: **{len(effective)}/1920**",
            f"- Raw provider errors replaced by overlays: **{len(overlays)}/13**",
            f"- Effective provider errors remaining: **{statuses.get('provider_error', 0)}**",
            f"- Effective statuses: `{dict(sorted(statuses.items()))}`",
            f"- Overlay statuses: `{dict(sorted(overlay_statuses.items()))}`",
            f"- Effective response SHA-256: `{output_hash}`",
            f"- Audit SHA-256: `{audit_hash}`",
            "- Byte-for-byte replay: **PASS**",
            "- API calls: **0**; Oracle/holdout: **0**; metrics/re-score: **not run**",
            "",
            "Next gate: complete the remaining 720 logical calls under a separate authorization before response freeze.",
            "",
        ]
    )
    report_path = ROOT / cfg["outputs"]["report"]
    write_immutable(report_path, report.encode("utf-8"))
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
