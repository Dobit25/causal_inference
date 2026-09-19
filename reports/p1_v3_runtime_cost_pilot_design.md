# P1-v3 runtime/cost pilot — frozen offline design

This artifact designs an engineering feasibility pilot; it does not execute one. The future pilot uses 9 synthetic-only scenes, measures 270 Bootstrap-BOSS fits after 3 excluded warm-ups, and samples 108 whole-graph semantic calls. It will project the frozen study envelope of 840 scenes, 168000 Bootstrap-BOSS fits, and 15120 semantic calls.

The design separates engineering feasibility from scientific evidence. Pilot graphs cannot estimate edge stability, pilot responses cannot establish semantic reliability, pilot scenes cannot enter any study cohort, and no threshold or hypothesis may change from pilot outcomes. Runtime is projected with scene-stratified median, p95 and leave-one-scene-out ranges, with a 1.25 reserve multiplier.

Current API prices were deliberately not fetched or invented offline. Before execution, a separate preflight must pin the official rate card, model snapshot, remaining approved budget, machine/software environment, exact synthetic IDs, runner hashes and disk capacity. The pilot has a hard API cost cap of USD 1.50.

All gates must pass: deterministic generation/replay, at least 268/270 measured BOSS fits with failure rate at most 1%, projected single-worker runtime with reserve at most 168 hours, all 108 logical API cases complete, final schema success 100%, first-attempt schema success at least 95%, retry rate at most 5%, exact snapshot 100%, cost/storage within registered limits, and no unclassified terminal failure.

No pilot ID, observation row, Bootstrap/BOSS fit or semantic API response was created. The only next authorized action is another offline step: freeze the executable preflight. Explicit user authorization is still required before any pilot execution.
