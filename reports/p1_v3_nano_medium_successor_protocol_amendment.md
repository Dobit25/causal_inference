# P1-v3 Nano-medium successor protocol amendment

## Decision

The successor framework uses `gpt-5.4-nano-2026-03-17` with
`reasoning_effort: medium` as its single primary semantic model. The earlier
Mini-medium runs remain a historical comparator/ablation and are not part of
the primary claim. No additional model matrix will be opened.

This is a prospective protocol decision, not a claim that Nano is universally
better. The Nano evidence available so far came from development-only Phase F;
it does not certify calibration, validation, holdout or real-world performance.

## Frozen framework

The statistical parent is the Ensemble 3/5 composed of Single-BOSS,
method-level Bootstrap-BOSS, PC, MMPC and FGES. Bootstrap C1–C6 remain
sensitivity conditions. The shared sentence-ID prompt, schema, production and
reference validators, six-vote agreement rules, Full/Partial certification
policies, pair-level abstention, condition-specific closure and false-adjacency
error rule are unchanged.

Full and Partial are the certification variants. Ambiguous and non-edge inputs
are diagnostic subsets: they test abstention and hallucination, but do not
contribute automatic direction coverage. Calibration and validation use the
registered sequential looks (120–440 and 160–480 respectively), scene as the
independent unit, confidence sequences, familywise error allocation, 95%
precision lower-bound target, 20% scene-mean coverage floor and the 90% High
guardrail.

## What this amendment does not do

It does not materialize scenes, rerun BOSS/Bootstrap-BOSS, call the semantic
API, access Oracle/holdout, tune the prompt, or select a threshold after seeing
new results. The existing Phase F Nano metrics remain frozen development
diagnostics.

## Next step

After review of this amendment, create a separate fresh-spend and live-
authorization checkpoint for sequential Nano calibration. Only if both
certification policies and the High/ambiguous gates pass may the protocol move
to validation; holdout remains sealed until validation succeeds.
