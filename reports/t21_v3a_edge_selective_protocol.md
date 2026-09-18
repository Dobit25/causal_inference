# T21 Amendment v3-A — frozen P1-v2 Edge-Selective protocol

T21 v3-A freezes a new development and validation protocol after T21 v2 failed the preregistered 0.95 orientation-precision gate. It does not reinterpret that failure, lower the gate, execute a method, generate validation scenes, call a model, or access any of the 80 frozen P1 holdout scene artifacts.

## Method boundary

`G_HYBRID_H2_EDGE_SELECTIVE` may orient only undirected edges already present in the raw BOSS CPDAG. It may not add or delete adjacencies, reverse a compelled direction, or claim to repair the BOSS skeleton. Skeleton or compelled-edge correction remains a separate future H3 question.

For each exact consistent DAG extension of the parent CPDAG, the method sums log Bernoulli direction likelihoods from the frozen GPT-5.4 Nano semantic-preference artifact. A stable softmax with fixed temperature 1 gives extension weights. Semantic confidence is `max(p, 1-p)`; global stability is the total normalized extension weight supporting a candidate direction. An edge becomes a candidate only when both registered thresholds pass.

Candidate directions are not accepted independently. An exact optimizer selects a jointly compatible subset with maximum total global stability, followed by maximum edge count, maximum semantic confidence, and canonical lexicographic tie-breaking. The selected directions must coexist in at least one parent-consistent DAG extension. Deterministic Meek R1–R4 closure then runs to a fixed point. Every final mark is labeled `compelled`, `semantic_selected`, `closure_propagated`, or `unresolved`.

## Threshold and safety gate

The frozen grid contains 20 candidates: five semantic-confidence thresholds (`0.80`, `0.90`, `0.95`, `0.99`, `0.999`) crossed with four global-stability thresholds (`0.80`, `0.90`, `0.95`, `1.00`). Threshold selection cannot use downstream answers or comparator rankings.

An eligible candidate must have 100% graph validity, at least 0.95 end-to-end selective orientation precision, at least 20 answered edges, and at least 0.20 coverage. End-to-end precision includes both semantic-selected and closure-propagated directions, excludes parent-compelled edges, and counts every oriented false BOSS adjacency as incorrect. Among eligible candidates, coverage is maximized using the frozen tie-break sequence. If none is eligible, P1-v2 stops without holdout access.

## Cohorts

The existing 20 development scenes are method-engineering data only and cannot select the new threshold. T21 v3-C will deterministically generate 20 new linear non-Gaussian validation SCMs (`P1V000…P1V019`, `scene_110000…scene_110019`) from master seed 21301, using the T18 family, `N=2000`, balanced graph/noise/query allocations and the frozen T19 story variants. No such scene is generated in v3-A.

The existing 80 T18 holdout IDs remain unchanged and unopened. They may be frozen for one-time execution at T22 only if the new validation cohort passes every gate after the method, output contract, scorer, prompt, model, thresholds and closure implementation have been hash-frozen.

## Next authorized action

Only `T21_V3B_OFFLINE_IMPLEMENTATION_AND_SYNTHETIC_CONFORMANCE` is authorized. It must implement the partial-graph contract, exact production solver, independent reference solver, Meek closure, provenance labels and malformed-input rejection without API calls or P1 scene access. Validation generation, live semantic inference, downstream reasoning and holdout execution remain unauthorized.
