"""Freeze a resume authorization for exactly the 413 uncached logical calls."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_validation_look160_mini_resume413.yaml"
RUNNER = ROOT / "scripts/run_p1_v4_validation_look160_mini_remaining720.py"

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest().upper()
def load(path: Path) -> dict:
    v = yaml.safe_load(path.read_text(encoding="utf-8")) if path.suffix in {".yaml", ".yml"} else json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(v, dict): raise RuntimeError(f"mapping expected: {path}")
    return v
def jsonl(path: Path) -> list[dict]: return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
def write_new(path: Path, value: object) -> str:
    body=(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode(); path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.read_bytes()!=body: raise RuntimeError(f"artifact drift: {path}")
    if not path.exists(): path.write_bytes(body)
    return hashlib.sha256(body).hexdigest().upper()

def main() -> None:
    cfg=load(CONFIG); plan_path=ROOT/cfg["parents"]["execution_plan"]["path"]; pf_path=ROOT/cfg["parents"]["provider_preflight"]["path"]; raw_path=ROOT/cfg["parents"]["raw_responses"]["path"]; overlay_path=ROOT/cfg["runtime"]["transport_retry_overlay"]["path"]
    for name,path,expected in (("plan",plan_path,cfg["parents"]["execution_plan"]["sha256"]),("preflight",pf_path,cfg["parents"]["provider_preflight"]["sha256"]),("raw",raw_path,cfg["parents"]["raw_responses"]["sha256"]),("overlay",overlay_path,cfg["runtime"]["transport_retry_overlay"]["sha256"])):
        if sha(path)!=expected: raise RuntimeError(f"{name} hash drift")
    plan=load(plan_path); ids=[r["logical_id"] for r in plan["logical_calls"]]; raw=jsonl(raw_path); overlay=jsonl(overlay_path); effective={r["logical_id"] for r in raw}|{r["logical_id"] for r in overlay}; pending=[x for x in ids if x not in effective]
    checks={"plan_2640_unique":len(ids)==len(set(ids))==2640,"raw_cache_2227":len(raw)==2227,"effective_cache_2227":len(effective)==2227,"pending_413":len(pending)==413,"preflight_pass":load(pf_path).get("status")=="PASS","mini_medium":cfg["semantic_contract"]["model"]=="gpt-5.4-mini-2026-03-17" and cfg["semantic_contract"]["reasoning_effort"]=="medium","hard_stop":cfg["token_control"]["hard_stop_tokens"]==3_000_000,"oracle_holdout_locked":not cfg["boundary"]["oracle_access"] and not cfg["boundary"]["holdout_access"]}
    if not all(checks.values()): raise RuntimeError(f"checks failed: {[k for k,v in checks.items() if not v]}")
    checkpoint={"schema_version":"fourgraph.p1_v4_validation_look160_mini_resume413_authorization_checkpoint.v1","status":"PASS_READY_NOT_EXECUTED","checks":checks,"config_sha256":sha(CONFIG),"runner_sha256":sha(RUNNER),"plan_sha256":sha(plan_path),"provider_preflight_sha256":sha(pf_path),"raw_sha256":sha(raw_path),"overlay_sha256":sha(overlay_path),"authorized_logical_ids":pending,"authorized_calls":413,"api_calls_before_execution":0,"oracle_access":0,"holdout_access":0}
    cp_sha=write_new(ROOT/cfg["outputs"]["live_authorization_checkpoint"],checkpoint)
    auth={"schema_version":"fourgraph.p1_v4_validation_look160_mini_resume413_authorization.v1","status":"PASS_LIVE_AUTHORIZED","explicit_user_live_authorization":True,"user_authorization_scope":"resume exactly the 413 uncached logical calls","checkpoint_sha256":cp_sha,"authorized_logical_calls":2640,"execution_slice":{"batch_id":"look160_resume_413","max_new_calls":413,"authorized_pending_logical_ids":pending},"token_hard_stop":3_000_000,"project_hard_stop_usd":18.0,"oracle_access":0,"holdout_access":0}
    a_sha=write_new(ROOT/cfg["outputs"]["live_authorization"],auth)
    audit={"schema_version":"fourgraph.p1_v4_validation_look160_mini_resume413_authorization_audit.v1","status":"PASS_RESUME_413_AUTHORIZATION","checks":checks,"config_sha256":sha(CONFIG),"checkpoint_sha256":cp_sha,"authorization_sha256":a_sha,"authorized_new_calls":413,"executed_new_calls":0,"effective_cached_calls":len(effective),"oracle_access":0,"holdout_access":0,"metrics_calculated":False}
    au_sha=write_new(ROOT/cfg["outputs"]["live_authorization_audit"],audit); print(json.dumps({"status":audit["status"],"pending":len(pending),"checkpoint_sha256":cp_sha,"authorization_sha256":a_sha,"audit_sha256":au_sha},indent=2))
if __name__=='__main__': main()
