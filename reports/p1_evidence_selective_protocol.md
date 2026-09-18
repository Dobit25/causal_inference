# P1-v3 Evidence-Selective Hybrid — frozen protocol

## Research objective

P1-v3 tests whether resampling stability from observational data can restrict semantic orientation to statistically supported adjacencies, while repeated fixed semantic queries provide empirical reliability rather than treating an LLM's self-reported confidence as a causal probability.

The output is an evidence-aware partial graph and an edge ledger. The method may abstain; it is not required to manufacture a complete DAG.

## Frozen statistical design

- Primary method: Bootstrap-BOSS only. The BOSS/PC/DirectLiNGAM ensemble is deferred to a later robustness experiment.
- Each scene starts from `N=2000` observations. Every bootstrap resample also contains 2,000 rows drawn with replacement and is standardized independently.
- The registered study procedure uses 200 resamples per scene. Each unordered pair is recorded as absent, undirected, A→B or B→A; all rates use all 200 runs as denominator.
- Adjacency thresholds are `0.60, 0.70, 0.80, 0.90, 0.95`; direction thresholds are `0.80, 0.90, 0.95`.
- A weak adjacency is vetoed before semantic orientation. An unstable BOSS direction is downgraded to undirected, never silently reversed. A threshold-produced PDAG without a consistent DAG extension is invalid; no heuristic repair is allowed.

Bootstrap frequency is a resampling-stability measure, not a causal probability and not proof that an edge is correct.

## Frozen semantic design

- Model snapshot: `gpt-5.4-nano-2026-03-17`.
- Call unit: one whole-graph batch for each scene × story variant × prompt variant.
- Six fixed paraphrases balance variable order three versus three. Responses are normalized deterministically to A→B, B→A or undetermined.
- Very High means 6/6 same direction; High means 5/6 plus one undetermined; Medium means 4/6 plus two undetermined; any vote in both directions is Conflict.
- Only Very High and High may be automatically oriented, and only after their agreement group attains an empirical reliability lower bound of at least 95% on an independent calibration cohort. Medium remains unresolved/human review.
- Directed answers require an exact quote from the supplied story. Association-only text cannot support a direction.

The vote fraction and any model-generated number are not called a causal probability.

## Hybrid decision and risk control

An edge may receive a semantic direction only after passing the statistical veto, empirical semantic-reliability requirement and global graph-consistency checks. Meek closure is deterministic; propagated directions are labeled separately and remain part of end-to-end error.

Candidate selection uses Learn-then-Test or an equivalent familywise risk-control procedure with target selective error `α=0.05`, failure probability `δ=0.05`, and minimum useful coverage `20%`. Thresholds maximize coverage only among candidates certified safe. If none passes, the protocol stops without lowering the gate or opening the final holdout.

## Cohorts and evidence boundary

The old 20 development scenes and 20 P1V validation scenes are historical diagnostics only. New method-development, semantic-calibration and threshold-validation roles must be disjoint at scene level. Their exact sizes will be fixed by a prospective power simulation before generation—not by budget alone. The existing 80-scene final holdout remains sealed for one-time evaluation only after every upstream gate passes.

This freeze runs no Bootstrap-BOSS repetition, generates no scene, makes no API call and accesses no final-holdout result. The next authorized action is offline implementation and synthetic conformance of Bootstrap-BOSS aggregation. Study-scene execution remains forbidden.
