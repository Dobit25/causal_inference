from __future__ import annotations

import argparse
import json
from pathlib import Path

from fourgraph.runtime_cost_pilot import PilotAuthorizationError, require_live_authorization, sha256


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "data/manifests/p1_v3_runtime_cost_pilot_preflight_audit.json"
CHECKPOINT = ROOT / "data/manifests/p1_v3_runtime_cost_pilot_execution_checkpoint.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization-check", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    if args.authorization_check:
        if checkpoint["authorization"]["pilot_execution"]:
            raise SystemExit("unexpected live authorization in frozen checkpoint")
        print("Execution checkpoint is frozen DENY; no pilot workload is authorized")
        return 0
    if args.execute:
        try:
            require_live_authorization(checkpoint["authorization"], sha256(PREFLIGHT))
        except PilotAuthorizationError as exc:
            raise SystemExit(str(exc)) from exc
        raise SystemExit("authorization unexpectedly passed a DENY checkpoint")
    parser.error("choose --authorization-check; --execute is currently forbidden")


if __name__ == "__main__":
    raise SystemExit(main())
