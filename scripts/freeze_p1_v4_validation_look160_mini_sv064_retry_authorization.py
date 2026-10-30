"""Freeze one explicit retry authorization for P1V4SV064/full/P2."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_validation_look160_mini_single_retry_sv064.yaml"
RUNNER = ROOT / "scripts/run_p1_v4_validation_look160_mini_sv064_retry.py"

def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest().upper()
def load(path):
    value = yaml.safe_load(path.read_text(encoding="utf-8")) if path.suffix in {".yaml", ".yml"} else json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise RuntimeError(f"mapping expected: {path}")
    return value
def jsonl(path): return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
def write_new(path, value):
    body = canonical(value); path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != body: raise RuntimeError(f"artifact drift: {path}")
    if not path.exists(): path.write_bytes(body)
    return hashlib.sha256(body).hexdigest().upper()

def main():
    cfg = load(CONFIG)
    parents = {k: ROOT / v["path"] for k, v in cfg["parents"].items()}
    for k, path in parents.items():
        if sha(path) != cfg["parents"][k]["sha256"]: raise RuntimeError(f"{k} hash drift")
    raw = jsonl(parents["raw_responses"]); logical_id = cfg["retry_scope"]["logical_ids"][0]
    by_id = {row["logical_id"]: row for row in raw}; row = by_id.get(logical_id)
    outputs = cfg["outputs"]
    checks = {
        "raw_count": len(raw) == len(by_id) == 1920,
        "exact_id": logical_id == "P1V4SV064/full/P2",
        "original_is_provider_error": row is not None and row.get("status") == "provider_error",
        "no_response_or_usage": row is not None and row.get("request_id") is None and row.get("response_sha256") is None and row.get("total_tokens") is None,
        "one_attempt_only": cfg["retry_scope"]["maximum_attempts_per_logical_id"] == 1,
        "overwrite_forbidden": cfg["retry_scope"]["overwrite_original_error"] == "forbidden",
        "raw_overlay_not_created": not any((ROOT / cfg["runtime"][k]).exists() for k in ("retry_overlay", "retry_attempts", "retry_token_ledger")),
        "token_stop": cfg["token_control"]["hard_stop_tokens"] == 3_000_000,
        "spend_stop": cfg["spend_control"]["project_hard_stop_usd"] == 18.0 and cfg["spend_control"]["hard_limit_enforced"] is True,
        "boundaries_locked": cfg["boundary"]["oracle_access"] is False and cfg["boundary"]["holdout_access"] is False and cfg["boundary"]["metric_calculation"] is False and cfg["boundary"]["closure"] == "forbidden",
    }
    if not all(checks.values()): raise RuntimeError(f"authorization checks failed: {[k for k,v in checks.items() if not v]}")
    checkpoint = {"schema_version":"fourgraph.p1_v4_validation_look160_mini_sv064_retry_checkpoint.v1","status":"PASS_READY_NOT_EXECUTED","checks":checks,"config_sha256":sha(CONFIG),"runner_sha256":sha(RUNNER),"raw_sha256":sha(parents["raw_responses"]),"logical_id":logical_id,"maximum_attempts":1,"oracle_access":0,"holdout_access":0}
    checkpoint_sha = write_new(ROOT / outputs["authorization_checkpoint"], checkpoint)
    auth = {"schema_version":"fourgraph.p1_v4_validation_look160_mini_sv064_retry_authorization.v1","status":"PASS_LIVE_AUTHORIZED","explicit_user_live_authorization":True,"user_authorization_scope":"exactly one retry for P1V4SV064/full/P2","checkpoint_sha256":checkpoint_sha,"logical_ids":[logical_id],"maximum_attempts_per_logical_id":1,"overwrite_original_error":False,"oracle_access":0,"holdout_access":0}
    auth_sha = write_new(ROOT / outputs["authorization"], auth)
    audit = {"schema_version":"fourgraph.p1_v4_validation_look160_mini_sv064_retry_authorization_audit.v1","status":"PASS_SINGLE_RETRY_AUTHORIZATION","checks":checks,"config_sha256":sha(CONFIG),"checkpoint_sha256":checkpoint_sha,"authorization_sha256":auth_sha,"authorized_retry_calls":1,"executed_retry_calls":0,"api_calls":0,"oracle_access":0,"holdout_access":0}
    write_new(ROOT / outputs["authorization_audit"], audit)
    print(json.dumps({"status":audit["status"],"logical_id":logical_id,"authorization_sha256":auth_sha}, indent=2))

if __name__ == "__main__": main()
