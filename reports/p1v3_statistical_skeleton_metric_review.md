# Phase F scientific review: independent statistical skeleton metrics

## Scope and interpretation

This checkpoint is an offline audit of the statistical parent graphs already
recorded by Phase D. It does not recompute Phase F semantic precision or
coverage. Those numbers refer to directions published after semantic selection
and closure, whereas this report scores only unordered adjacency against a
deterministically reconstructed Oracle DAG skeleton on the 30 development
scenes. A false adjacency is therefore an error before any LLM stage exists.

The Phase F Ensemble result (`329/335`, 98.21% published-direction precision;
79.76% coverage) remains a development-only hybrid result. Its denominator
contains semantic-selected and closure-propagated directions. The 108
parent-graph fail-closed records, 15 global conflicts, 531 directions outside
their parent graph, and one missing provider response remain in the replay
audit; they are not silently removed or turned into successes. The risk–
coverage endpoint in that result is descriptive, not a registered threshold
curve. No tuning, generalization claim, calibration, significance test, or
holdout access is authorized by this checkpoint.

For the primary Ensemble condition specifically, the hybrid metric artifact
contains 420 candidate edge records (210 Full and 210 Partial), 335 published
directions, and 85 abstentions. Of the published directions, 109 are
`semantic_selected` and 226 are `closure_propagated`; the corresponding
correct counts are 109 and 220. The 240 `parent_fail_closed_records` shown in
the condition table are condition-level replay records and should not be
mistaken for the 108 unique parent-graph failure records in the incident
replay audit.

## Method

The unit is one scene–condition–unordered node pair. The Oracle skeleton is
reconstructed in memory from the frozen deterministic development generator;
its SCM commitments match the Phase-D scene metadata for all 30 scenes. Phase-D
normalized graph artifacts are read as-is. Bootstrap C1–C6 retain a pair when
its observed adjacency stability meets that candidate's adjacency threshold;
direction thresholds do not affect this skeleton-only calculation. The primary
ensemble uses one method-level Bootstrap vote at the frozen 0.80 rule and a
3-of-5 vote over Single-BOSS, Bootstrap, PC, MMPC and FGES. GFCI is reported as
an adjacency-only sensitivity condition; PAG endpoint marks are discarded.

## Results (pooled over 30 scenes)

| Condition | TP | FP | FN | Precision | Recall | F1 | FP rate | Mean edges/scene |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Single-BOSS | 212 | 45 | 1 | 82.49% | 99.53% | 90.21% | 18.22% | 8.57 |
| Bootstrap C1/C2 | 213 | 44 | 0 | 82.88% | 100.00% | 90.64% | 17.81% | 8.57 |
| Bootstrap C3/C4 | 211 | 27 | 2 | 88.66% | 99.06% | 93.57% | 10.93% | 7.93 |
| Bootstrap C5/C6 | 209 | 19 | 4 | 91.67% | 98.12% | 94.78% | 7.69% | 7.60 |
| PC | 200 | 0 | 13 | 100.00% | 93.90% | 96.85% | 0.00% | 6.67 |
| MMPC | 201 | 1 | 12 | 99.50% | 94.37% | 96.87% | 0.40% | 6.73 |
| FGES | 211 | 15 | 2 | 93.36% | 99.06% | 96.13% | 6.07% | 7.53 |
| Ensemble 3/5 | 210 | 0 | 3 | 100.00% | 98.59% | 99.29% | 0.00% | 7.00 |
| GFCI sensitivity | 202 | 0 | 11 | 100.00% | 94.84% | 97.35% | 0.00% | 6.73 |

Scene-macro results are stored in the machine-readable result artifact. They
are reported separately because pooled pair records give larger scenes more
weight.

## Interpretation

The statistical layer already explains much of the later hybrid behavior. A
single BOSS parent is high-recall but admits 45 false adjacencies. Raising the
bootstrap adjacency threshold removes false positives monotonically (44 → 27 →
19) at the cost of a small number of false negatives (0 → 2 → 4). The frozen
3/5 heterogeneous ensemble has zero false-positive adjacencies in this
development cohort and misses only three true adjacencies. This is evidence of
a strong development skeleton, not a final generalization claim: the cohort is
small, synthetic, and used for method development.

The independent skeleton checkpoint therefore separates two sources of error:
the parent graph itself and the later semantic/closure stage. It does not prove
that an LLM can orient these edges, and it does not authorize calibration,
downstream reasoning, or holdout execution.

## Audit status

`PASS_OFFLINE_SKELETON_METRICS`; 5,520 deterministic pair records across 12
conditions; 6,150 frozen normalized fits read; 30/30 Oracle commitments
verified; Phase-D artifacts unchanged; statistical reruns = 0; semantic API
calls = 0; calibration/holdout access = 0. Replay is byte-for-byte stable.
