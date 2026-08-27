# Preliminary Experiment Plan

## Experimental unit

A base NoisyCausal causal system / SCM.

Questions and noisy variants are nested within that system.

## Four graph conditions

### G1 — LLM-only
Input:
- variable semantics;
- clean natural-language causal context;
- no ground-truth graph;
- no observational table.

Output:
- strict machine-readable DAG;
- optional per-edge confidence.

### G2 — SCD-only
Input:
- observational table sampled from the same clean SCM;
- anonymize columns (`X1`, `X2`, ...) where possible to prevent semantic leakage.

No natural-language semantics.

Choose the SCD method after artifact/data-type inspection. Candidate families:
- PC / constraint-based;
- score-based;
- a DAG-output method matched to the SCM assumptions.

### G3 — Hybrid
Recommended pilot logic:
1. run SCD;
2. estimate edge stability/uncertainty by bootstrap if feasible;
3. locate ambiguous/low-confidence edge decisions;
4. query the same semantic LLM used by G1 only on uncertain decisions;
5. integrate proposals as constrained preferences;
6. enforce acyclicity;
7. save an arbitration log.

Do not let the LLM blindly overwrite strong statistical evidence.

### G4 — Oracle
Use the benchmark ground-truth graph only as:
- reference for graph metrics;
- downstream oracle graph condition.

Never use it to tune or correct G1–G3.

## Canonical graph representation

Normalize all graphs to one schema, then serialize identically.

Example:

```text
[Causal Graph]
Infection -> Medicine
Medicine -> Recovery
```

Sort nodes/edges deterministically.

## Fixed graph-guided reasoner

All graph conditions use one code path:

```text
[Causal Graph]
{graph}

[Background / Evidence]
{same context}

[Question]
{same question}

[Task]
Use the causal graph as the structural assumption and answer in the required schema.
```

Freeze:
- model/version;
- prompt;
- temperature;
- max tokens;
- graph encoding;
- parser.

## Dev / holdout split

### Dev — 10 SCMs
Allowed:
- prompt debugging;
- parser repair;
- SCD method selection;
- hybrid threshold selection.

### Holdout — 30–50 SCMs
Forbidden:
- prompt tuning;
- threshold tuning;
- deleting difficult cases after seeing results.

## Stage A — Clean proof of concept

For each holdout SCM:
1. build G1–G4;
2. compute graph metrics;
3. run fixed reasoner on clean questions;
4. compute downstream accuracy.

Required outputs:
- graph-quality table;
- downstream accuracy table;
- oracle gap;
- graph-metric vs reasoning correlation.

## Stage B — Structured-noise reasoning

Use graphs frozen from Stage A.

First noises:
- IV;
- CS;
- CI.

Report:
- accuracy by graph condition × noise;
- clean-to-noise drop;
- graph-condition interactions.

## Stage C — Noisy graph induction

Optional after Stage B:
- reconstruct LLM/hybrid graphs from noisy context;
- compare graph degradation and reasoning degradation.

## Stochasticity

Pilot:
- main deterministic/low-temperature run;
- repeat at least 20% of items 3 times.

Full paper:
- multiple repeated runs / model seeds where meaningful.

## Statistics

- paired bootstrap over `system_id`;
- McNemar for matched binary correctness;
- multiple-testing correction;
- Spearman correlation between graph metrics and downstream accuracy;
- cluster bootstrap because multiple questions can share one SCM.

## Success criteria

A promising pilot needs at least one reproducible signal:
- meaningful downstream difference among graph conditions;
- hybrid advantage;
- non-trivial oracle gap;
- disagreement between structural ranking and causal-reasoning ranking;
- SID/AID outperform SHD as predictors of downstream utility;
- specific graph errors disproportionately harm reasoning;
- graph provenance changes noise robustness.

A well-powered null result is still informative.
