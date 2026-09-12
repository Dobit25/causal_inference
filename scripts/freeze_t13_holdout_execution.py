"""Build or byte-check the offline T13 holdout execution freeze."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fourgraph.holdout_freeze import build_t13  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/t13_holdout_freeze.yaml")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    config = ROOT / args.config
    artifacts = build_t13(ROOT, config)
    for relative, payload in artifacts.items():
        path = ROOT / relative
        if args.check:
            if not path.is_file() or path.read_bytes() != payload:
                raise SystemExit(f"T13 byte check failed: {relative}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    print(f"T13 {'checked' if args.check else 'frozen'}: {len(artifacts)} artifacts; API calls=0; holdout_accessed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
