# Look-120 pre-API preflight

Status: `BLOCKED_ENVIRONMENT_BEFORE_STATISTICAL_EXECUTION`

The 120 scenes and 360 public stories are present and hash-linked to the
frozen amendment. Before running Single-BOSS/Bootstrap-BOSS, the exact runtime
environment was checked fail-closed.

Observed blockers:

- Python environment: `3.10.21`; required frozen version: `3.10.20`.
- `java` is not available in the current PATH.
- `Rscript` is not available in the current PATH.

The pinned Tetrad JAR is present and its SHA-256 matches. No statistical fit
was started, so no result was produced under an unapproved environment.

Boundary remains:

```text
statistical fits: 0
semantic API calls: 0
Oracle/validation/holdout access: 0
```

The exact audit is stored at
`data/manifests/p1_v3_nano_medium_calibration_look120_pre_api_preflight_audit.json`.
The next action is to provide the exact Python 3.10.20, Java 21.0.10 and R
4.4.3/bnlearn environment, then rerun this verifier. No prompt, schema,
threshold or cohort change is allowed.
