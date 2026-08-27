# Coding Log

## T00 — Bootstrap
- Status: Complete
- Started: 2026-08-27
- Finished: 2026-08-27
- Commit: Not committed
- Config: `configs/pilot.yaml`
- Files changed: `.gitignore`, `pyproject.toml`, `configs/pilot.yaml`, `src/fourgraph/`, `tests/test_bootstrap.py`, `codinglog.md`
- Summary: Created the minimal Python package, CLI, YAML config loader, deterministic seed utility, and tests.
- Tests: `conda run -n cau pytest` — 4 passed
- Results: Package imports as version 0.1.0; `fourgraph --help` and config validation succeed in `cau`.
- Risks: Causal-discovery and model dependencies intentionally deferred until the T01 artifact audit.
- Next: T01 — audit the official NoisyCausal artifact and record `scd_ready`.
