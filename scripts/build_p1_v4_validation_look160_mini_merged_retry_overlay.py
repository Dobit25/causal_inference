"""Create the deterministic, derived overlay used to resume the remaining look-160 calls."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results/raw/p1_v4_independent_validation/look160/mini_semantic/raw_responses.jsonl"
OVERLAYS = [
    ROOT / "results/raw/p1_v4_independent_validation/look160/mini_semantic/provider_incident_retry_overlay.jsonl",
    ROOT / "results/raw/p1_v4_independent_validation/look160/mini_semantic/batch4_provider_retry_overlay.jsonl",
    ROOT / "results/raw/p1_v4_independent_validation/look160/mini_semantic/sv064_provider_retry_overlay.jsonl",
]
OUT = ROOT / "results/raw/p1_v4_independent_validation/look160/mini_semantic/all_retry_overlays.jsonl"

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def canonical(row: dict) -> bytes:
    return (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()

def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def main() -> None:
    raw = rows(RAW)
    raw_by_id = {r["logical_id"]: r for r in raw}
    expected = [r["logical_id"] for r in raw if r.get("status") == "provider_error"]
    merged = {}
    source = {}
    for path in OVERLAYS:
        for row in rows(path):
            lid = row["logical_id"]
            if lid in merged:
                raise RuntimeError(f"duplicate retry logical_id: {lid}")
            if lid not in raw_by_id or raw_by_id[lid].get("status") != "provider_error":
                raise RuntimeError(f"overlay does not replace raw provider error: {lid}")
            if row.get("status") == "provider_error" or not row.get("response_sha256"):
                raise RuntimeError(f"unresolved retry overlay: {lid}")
            merged[lid] = row
            source[lid] = path.name
    if set(merged) != set(expected):
        raise RuntimeError(f"overlay coverage mismatch: expected={expected}, got={list(merged)}")
    # Preserve the raw-cache provider-error order, not the order of source files.
    body = b"".join(canonical(merged[lid]) for lid in expected)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists() and OUT.read_bytes() != body:
        raise RuntimeError("merged overlay drift")
    if not OUT.exists():
        OUT.write_bytes(body)
    manifest = {
        "schema_version": "fourgraph.p1_v4_validation_look160_mini_merged_retry_overlay.v1",
        "status": "PASS_OFFLINE_MERGED_OVERLAY",
        "raw_sha256": sha(RAW),
        "source_overlay_hashes": {p.name: sha(p) for p in OVERLAYS},
        "logical_ids": expected,
        "records": len(expected),
        "effective_overlay_sha256": sha(OUT),
        "raw_immutable": True,
        "api_calls": 0,
        "oracle_access": 0,
        "holdout_access": 0,
    }
    mp = ROOT / "data/manifests/p1_v4_validation_look160_mini_merged_retry_overlay_audit.json"
    data = canonical(manifest)
    if mp.exists() and mp.read_bytes() != data:
        raise RuntimeError("merged overlay audit drift")
    if not mp.exists():
        mp.write_bytes(data)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
