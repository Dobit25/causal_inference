# P1-v3 Statistical Ensemble Protocol Amendment

## Phase A–B scope

This amendment characterizes Single-BOSS, Bootstrap-BOSS, PC, MMPC and FGES,
with GFCI as a PAG-to-skeleton sensitivity condition. The primary ensemble is
the 3/5 majority of method-level skeleton votes. Bootstrap repetitions count as
one method-level vote, and all six Bootstrap-BOSS threshold candidates are
retained rather than selected from development results.

Phase A–B is offline only. It freezes contracts and tests fixture behavior; it
does not materialize study scenes, load observations, run discovery algorithms,
read Oracle data, access holdout, or call a semantic model.

## Scope and counts

- Development cohort: 30 registered IDs `P1V3SD000–029`, N=2000, linear
  non-Gaussian SCM; not materialized in this phase.
- Statistical execution, when separately authorized: 30 Single-BOSS, 6,000
  Bootstrap-BOSS, 30 PC, 30 MMPC, 30 FGES and 30 GFCI sensitivity fits.
- Bootstrap candidates: `.60/.80`, `.60/.90`, `.80/.80`, `.80/.90`,
  `.95/.80`, `.95/.90` (adjacency/direction stability).

## Important interpretation boundary

BOSS uses `BasisFunctionBicScore`; FGES uses `SemBicScore` with the same numeric
penalty value. Therefore BOSS–FGES is registered as **algorithm-plus-score
sensitivity**, not an isolated search-strategy comparison.

## Semantic reuse

The candidate universe is the shared union of eligible undirected edges from
Single-BOSS, all six Bootstrap candidates and the primary ensemble, bounded by
21 pairs for seven nodes. One raw whole-story response is reused byte-for-byte;
filtering and closure are performed independently per condition. Prompt
chunking is forbidden. Overflow requires an amendment.

## Pending gates

Before live execution, the exact R/bnlearn environment and activated
Tetrad/Python/Java runtime must be verified, and the 21-pair semantic prompt
must pass provider-tokenizer/context preflight. A failed check stops the run.
