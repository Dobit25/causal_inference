# Experiment Plan

## Experimental conditions

For every eligible scene `s`, construct:

\[
G_{LLM,s},\quad G_{SCD,s},\quad G_{HYBRID,s},\quad G_{ORACLE,s}.
\]

All graph conditions use the same frozen reasoner, query view, non-causal glossary, parser, scorer, decoding settings, and model snapshot. Only the graph payload changes.

T12 v2 additionally deduplicates calls by canonical model/input/configuration hash. `graph_condition` is excluded from this key: identical stripped graphs, queries and glossaries reuse the exact same raw response, preventing provider nondeterminism from masquerading as a graph-source effect.

Before entering the reasoner or metrics, every condition is normalized as `fourgraph.graph.v1`. `graph_method` and provenance remain available to the audit pipeline but are stripped from the `fourgraph.reasoner_graph.v1` payload.

## Graph construction

### G_LLM

- Input: public graph-faithful story and public variable semantics.
- No observational table or grading truth.
- Output: canonical LLM DAG artifact plus confidence/rationale audit logs.
- One graph is constructed per scene, not per task. Every unordered node pair receives exactly one direct-cause/reverse/no-direct-edge decision.
- Strict parsing rejects incomplete, extra, duplicate, non-canonical, or cyclic responses; validation failures may be retried twice but are never heuristically repaired.
- T08 is complete: frozen OpenAI snapshot `gpt-5.4-nano-2026-03-17` produced 8/8 replayable canonical development DAGs in one attempt each. Its configuration is frozen for later T10 semantic orientation; holdout execution remains deferred.

### G_SCD

- Input: anonymized observational table from the same scene only.
- No story or semantic labels.
- P0 primary output: CPDAG.
- P0 method: T05-frozen BOSS + `BasisFunctionBicScore` (`penalty_discount=1.0`, `truncation_limit=3`, one deterministic data-order start).
- P0 sensitivity: deterministic consistent DAG extension with lexicographic tie-breaking.
- P1: DirectLiNGAM DAG under matched linear non-Gaussian assumptions.
- Output: canonical SCD CPDAG/DAG artifact; the projected sensitivity artifact references its raw CPDAG parent hash and complete deterministic orientation trace.
- T09 is complete on the frozen development split: 8/8 raw CPDAGs and 8/8 projected-DAG sensitivity artifacts reproduce byte-for-byte without story, Oracle, tasks, or holdout access.
- T10 is complete on the frozen development split: the T08-frozen semantic configuration oriented 27/27 unresolved raw-T09 CPDAG edges into 8/8 valid parent-linked Hybrid DAGs. Skeletons, compelled directions, and equivalence classes are unchanged; replay is byte-exact and holdout remains unopened.
- T11 is complete on the frozen development split: 40/40 type-aware structural metric records compare five graph views with in-memory grading-only Oracle DAGs. Metrics replay byte-for-byte; no LLM call, task access, builder tuning, persisted Oracle edges, or holdout access occurred.

### G_HYBRID H1

- Start from the SCD skeleton/CPDAG.
- Preserve adjacency and compelled orientations.
- Ask the semantic LLM only about unresolved directions.
- Forbid edge addition/deletion.
- Reject cycles and CPDAG-incompatible collider changes.
- Persist edge-level proposals, confidence, decisions, and reasons.
- Emit a canonical Hybrid DAG only after the parent/skeleton/compelled-direction/equivalence-class validator passes.

### G_ORACLE

- Load the grading-only true DAG.
- Use only for explicit oracle payloads and graph metrics.
- Never tune or repair non-oracle builders with it.
- Emit the same canonical DAG artifact type through a grading-only adapter.
- T07 implementation: derive canonical IDs from public schema order, validate the no-latent grading DAG, and expose no raw ground-truth fields. Development integration is frozen at 8/8 scenes; holdout loading waits until T14.

## CPDAG reasoning

The primary P0 reasoner interprets `X -- Y` as unknown direction. For a task, it reasons over compatible DAG extensions:

- if the answer is invariant, return that answer;
- if compatible DAGs imply different valid answers, return `undetermined`.

Score both:

1. oracle-answer accuracy;
2. uncertainty-aware correctness.

The projected-DAG run uses the official task answer schema and is reported as sensitivity, not as raw SCD truth.

## Reasoner input isolation

```text
[Graph]
{canonical_graph}

[Variable Glossary]
{canonical X000 IDs and variable types only; no public names or causal relations}

[Query]
{treatment, outcome, task, output schema}
```

The reasoner must not receive the causal story, observational table, graph provenance label, or gold answer.

`{canonical_graph}` means the stripped reasoner view, not the full audit artifact. It contains only schema version, graph type, canonical nodes, and edges.

## P0 — Released exploratory study

- Graph cohort: 33 pinned clean, fully observed scenes; T04-frozen split 8 development / 25 holdout.
- Primary downstream cohort: 27 graph-cohort scenes with all five frozen tasks; T04-frozen split 7 / 20.
- Supplementary cohort: the remaining 6 graph-cohort scenes; T04-frozen split 1 / 5 and exploratory reporting only.
- Nesting: primary and supplementary partition the graph cohort, and every scene retains one development/holdout role.
- Unit: `scene_id`.
- Development: loader/parser debugging, P0 SCD selection, prompt syntax, and hybrid policy checks.
- Holdout: no prompt, method, task, threshold, parser, or exclusion changes.

Use all 33 scenes for eligible graph-level analyses, the fixed `27 x 5` panel for primary downstream comparisons, and never pool supplementary task accuracy into the primary panel. P0 verifies feasibility and reports exploratory estimates; released mechanism heterogeneity limits generalization.

## P1 — Fresh primary study

- 100 fresh homogeneous scenes: 20 development, 80 holdout.
- 5–7 nodes, linear non-Gaussian causally sufficient SCMs.
- DirectLiNGAM primary SCD.
- `N=2000` observations; `N=500` and `N=10000` sensitivity on 20 scenes.
- Same reasoner isolation, graph builders, tasks, scorers, and scene-level analysis architecture as P0.

Nonlinear additive-noise SCMs are a later robustness extension, not part of the initial P1 claim.

## Outcome families

Outcomes are co-equal and exploratory within phase:

- A: graph-quality ranking;
- B: downstream graph-condition ranking;
- C: graph-quality versus downstream-ranking disagreement;
- D: oracle-gap and residual-reasoning analysis;
- E: SID/AID utility when compatible;
- F: controlled graph-perturbation effects;
- G: observation-robustness effects.

Clean P0/P1 covers A–D. E–G enter only in their declared later analyses. Report effect sizes, confidence intervals, and BH-adjusted tests; do not define success as “any favorable outcome.”

## Freeze rule

Before holdout, freeze scene/task IDs, all graph builders, CPDAG semantics, DAG projection, reasoner model/version, prompts, graph encoding, parser, scorers, statistics, and exclusion rules. Any later change creates a new experiment version.
