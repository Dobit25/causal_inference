"""Offline conformance test: parent process terminates a deliberately hung worker."""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/p1_v4_validation_look160_provider_incident_recovery.yaml"


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sleeper(seconds: float) -> None:
    time.sleep(seconds)


def main() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    context = multiprocessing.get_context("spawn")
    worker = context.Process(target=sleeper, args=(2.0,))
    started = time.perf_counter()
    worker.start()
    worker.join(timeout=0.25)
    timed_out = worker.is_alive()
    if timed_out:
        worker.terminate()
        worker.join(timeout=5)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    passed = timed_out and not worker.is_alive() and worker.exitcode is not None
    result = {
        "schema_version": "fourgraph.p1_v4_external_watchdog_self_test.v1",
        "status": "PASS" if passed else "FAIL",
        "worker_sleep_seconds": 2.0,
        "parent_deadline_seconds": 0.25,
        "worker_terminated": timed_out,
        "worker_exitcode": worker.exitcode,
        "elapsed_ms": elapsed_ms,
        "no_api_calls": True,
        "config_sha256": hashlib.sha256(CONFIG.read_bytes()).hexdigest().upper(),
    }
    body = canonical(result)
    output = ROOT / config["outputs"]["watchdog_self_test"]
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.read_bytes() != body:
        raise RuntimeError("self-test artifact drift")
    if not output.exists():
        output.write_bytes(body)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
