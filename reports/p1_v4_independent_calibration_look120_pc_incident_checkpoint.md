# PC incident checkpoint — calibration look 120

Status: **forensic checkpoint pass; Phase D remains suspended fail-closed.**

The stopped PC job is `P1V4SC307`, execution identity
`D823FF5FBE1D32979100E7E9185DEF94468A04F7569B8966F6A911FFB51B7DAC`.
It recorded `ValueError: PDAG has no consistent DAG extension`.

The current runner validates the parsed PC graph before persisting its raw or
normalized artifact. Therefore the incident graph itself is absent: frozen
evidence cannot distinguish a genuinely non-CPDAG PC output from an adapter or
validator disagreement. This is an execution-observability defect, not a
scientific finding and not a justification to alter PC parameters.

No fits were replayed, no adapter/validator changed, and no semantic API,
Oracle, or holdout was accessed. A separately authorized isolated replay that
captures the pre-validation graph is required before Phase D may resume.
