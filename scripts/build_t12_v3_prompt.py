"""Build or byte-check the versioned T12 v3 prompt-contract manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.reasoner_v3 import PromptV3Bundle  # noqa: E402


CONFIG = PROJECT_ROOT / "configs/t12_v3_prompt.yaml"


def _load_config() -> dict[str, Any]:
    value = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("T12 v3 prompt config must be an object")
    return value


def build() -> tuple[Path, bytes]:
    config = _load_config()
    prompt = config["prompt_bundle"]
    bundle = PromptV3Bundle.load(
        base_path=PROJECT_ROOT / prompt["base"],
        module_paths={
            task: PROJECT_ROOT / path for task, path in prompt["modules"].items()
        },
    )
    components = bundle.manifest_components()
    # Store repository-relative paths rather than machine-specific absolute paths.
    components["base"]["path"] = prompt["base"]
    for task, path in prompt["modules"].items():
        components["modules"][task]["path"] = path
    components["bundle_sha256"] = sha256_hex(
        canonical_json_bytes(
            {"base": components["base"], "modules": components["modules"]}
        )
    )
    payload = {
        "schema_version": "fourgraph.t12_v3_prompt_contract.v1",
        "config_sha256": sha256_hex(CONFIG.read_bytes()),
        "prompt_components": components,
        "internal_no_valid_set_name": prompt["internal_no_valid_set_name"],
        "official_no_valid_set_serialization": prompt[
            "official_no_valid_set_serialization"
        ],
        "sentinel_contract": config["sentinel_contract"],
        "task_routing": prompt["task_routing"],
        "evidence_contract": config["evidence_contract"],
        "opened_v2_suite_role": config["calibration"]["opened_v2_suite"]["role"],
        "new_sealed_suite_status": config["calibration"]["new_sealed_suite"][
            "status"
        ],
        "live_execution_allowed": config["live_execution"]["allowed"],
        "holdout_accessed": False,
    }
    target = PROJECT_ROOT / prompt["contract_manifest"]
    return target, canonical_json_bytes(payload, newline=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target, payload = build()
    if args.check:
        if target.read_bytes() != payload:
            raise RuntimeError("T12 v3 prompt manifest does not reproduce byte-for-byte")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    print(json.dumps(json.loads(payload), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
