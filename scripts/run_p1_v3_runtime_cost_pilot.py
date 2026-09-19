from __future__ import annotations

import argparse
import json
from pathlib import Path

from fourgraph.runtime_cost_pilot import PilotAuthorizationError, require_live_authorization, sha256


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "data/manifests/p1_v3_runtime_cost_pilot_preflight_audit.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-preflight", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--authorization", type=Path)
    args = parser.parse_args()
    if not PREFLIGHT.exists():
        raise SystemExit("Frozen preflight audit is missing")
    audit = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if args.check_preflight:
        if audit["authorization"]["pilot_execution"]:
            raise SystemExit("Frozen preflight must not self-authorize live execution")
        print("P1-v3 pilot preflight is frozen; live execution remains forbidden")
        return 0
    if args.execute:
        if args.authorization is None:
            raise SystemExit("--execute requires a separately frozen --authorization record")
        record = json.loads(args.authorization.read_text(encoding="utf-8"))
        try:
            require_live_authorization(record, sha256(PREFLIGHT))
        except PilotAuthorizationError as exc:
            raise SystemExit(str(exc)) from exc
        raise SystemExit("Live workload adapter is intentionally unavailable until a post-preflight execution checkpoint")
    parser.error("choose --check-preflight; live execution is not authorized")


if __name__ == "__main__":
    raise SystemExit(main())
