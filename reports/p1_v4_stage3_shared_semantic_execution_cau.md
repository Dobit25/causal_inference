# P1V4 Stage 3D shared semantic execution (cau)

## Verdict

`INCOMPLETE_OR_PROVIDER_INCIDENT`. The frozen execution plan has exactly 360
append-only logical records, but only 359 include a completed provider
response. No scientific metric, closure, Oracle read, or downstream reasoner
step was run.

## Execution accounting

| Item | Result |
|---|---:|
| Planned logical calls | 360 |
| Completed provider responses | 359 |
| Missing / outcome unknown | 1 |
| Completed valid responses | 273 |
| Completed pair-invalid responses | 86 |
| Completed schema-invalid responses | 0 |
| New provider errors after resume | 0 |

The sole missing logical call is `P1V4SD010/partial/P1`. Its client process
was stopped while the request was pending; no response, provider request ID or
usage record was received. It was recorded as `TransportOutcomeUnknown` and
was not retried. The earlier monitoring artifact that incorrectly stated zero
completed responses is retained and superseded by its correction artifact.

## Provider usage for the 359 received responses

| Usage | Tokens |
|---|---:|
| Input | 216,838 |
| Output | 218,148 |
| Reasoning | 159,951 |
| Total | 434,986 |

## Boundary

- Oracle access: 0
- Holdout access: 0
- Downstream reasoner runs: 0
- No prompt, schema, model, pool or threshold change occurred.

## Required disposition

A separately authorized incident disposition is required before replacing the
one missing logical call. Until then, the response set is not eligible for
semantic re-score, agreement aggregation, closure, precision, coverage, or
calibration progression.
