from __future__ import annotations

"""Calibration runner plumbing; live provider execution is intentionally gated."""

import argparse
import json
from pathlib import Path

import yaml

from fourgraph.nano_calibration_control import CalibrationBudgetError, CalibrationTokenLedger, logical_identity

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v3_nano_medium_calibration_execution_control_amendment.yaml"
LEDGER = ROOT / "results/runtime/p1_v3_nano_medium_calibration/token_ledger.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true", help="read the append-only ledger; never calls a provider")
    parser.add_argument("--check", action="store_true", help="validate the frozen control and ledger state")
    parser.add_argument("--amendment", type=Path, default=CONFIG)
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    args = parser.parse_args()
    if not (args.dry_run or args.resume or args.check):
        raise SystemExit("live execution is not enabled by this checkpoint; use --dry-run, --resume, or --check")
    amendment = args.amendment if args.amendment.is_absolute() else ROOT / args.amendment
    control = yaml.safe_load(amendment.read_text(encoding="utf-8"))
    budget = control["budget_control"]
    rates = control["cost_accounting"]
    ledger = CalibrationTokenLedger(
        args.ledger,
        max_total_tokens=int(budget["total_tokens_hard_stop"]),
        reset_hour=int(budget["reset_local_time"].split(":", 1)[0]),
        timezone_name=budget["reset_timezone"],
        input_rate_per_million=float(rates["input_rate_usd_per_million"]),
        output_rate_per_million=float(rates["output_including_reasoning_rate_usd_per_million"]),
    )
    snapshot = ledger.snapshot()
    print(json.dumps({"status": "PASS_OFFLINE_RUNNER_PREFLIGHT", "config": str(amendment.relative_to(ROOT)), "snapshot": snapshot, "api_calls": 0, "study_scenes_materialized": 0, "live_provider_adapter": control["runner"]["live_provider_adapter"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
