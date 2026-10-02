# Phase F — Hybrid metric calculation authorization checkpoint

Status: **PASS — authorized for offline metric calculation only**.

The checkpoint pins the Case-B replay audit (`AAA8FEEA…`), replay outputs
(`8303E74B…`) and incident-resolution amendment configuration
(`F93925E6…`). Verification found exactly 480 replay records, byte-for-byte
replay, zero remaining implementation defects, zero protocol ambiguities,
531 out-of-parent directions removed, 15 global conflicts fail-closed and
108 invalid parent graphs fail-closed. The provider incident
`P1V3SD028/full/P1` remains a missing response and is not retried.

Oracle and holdout access are both zero. The authorization covers only the
offline computation of orientation precision, coverage, abstention,
false-adjacency-to-orientation errors and descriptive risk–coverage data for
Single-BOSS, C1–C6 and Ensemble 3/5. No API, statistical discovery,
calibration, threshold tuning, downstream reasoner or significance testing is
authorized.
