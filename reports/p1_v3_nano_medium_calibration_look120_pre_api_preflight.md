# Look-120 pre-API preflight

Status: `PASS_READY_BEFORE_STATISTICAL_EXECUTION`

The 120 scenes and 360 public stories are present and hash-linked to the
frozen amendment. Before running Single-BOSS/Bootstrap-BOSS, the exact runtime
environment was checked fail-closed.

The exact Conda/R runtimes were verified using explicit executable paths:

- Python: `D:/Coding/Anaconda/envs/p1v3_py31020/python.exe`, version `3.10.20`.
- Java: `D:/Coding/Anaconda/envs/cau/Library/bin/java.exe`, OpenJDK `21.0.10`.
- Rscript: `D:/Coding/R44/R-4.4.3/bin/x64/Rscript.exe`, R `4.4.3`.
- `bnlearn`: `5.3-20260901`; `bnlearn::mmpc` is loadable.
- The pinned Tetrad JAR is present and its SHA-256 matches.

The earlier PATH-only check was blocked; this rerun passed after using the
registered executable paths and `R_LIBS_USER=D:/Coding/R44/library`.

No statistical fit was started and no result was produced yet.

Boundary remains:

```text
statistical fits: 0
semantic API calls: 0
Oracle/validation/holdout access: 0
```

The exact audit is stored at
`data/manifests/p1_v3_nano_medium_calibration_look120_pre_api_preflight_audit.json`.
The next action is the separately authorized statistical-parent execution.
No prompt, schema, threshold or cohort change is allowed.
