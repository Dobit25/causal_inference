# Research Context — Four-Graph Causal Reasoning

## Governing question

For the same causal scene, compare four graph sources through one frozen graph-guided reasoner:

1. `G_LLM`: semantic graph from the public causal story.
2. `G_SCD`: statistical graph from same-scene observational data only.
3. `G_HYBRID`: SCD skeleton with semantic assistance for unresolved orientation.
4. `G_ORACLE`: grading-only ground-truth graph.

The project asks how graph provenance and graph errors affect downstream causal adjustment/control reasoning, and whether structural metrics predict that functional utility.

## Frozen study direction

```text
Released CausalDS P0
  -> validate artifact and four-graph pipeline
  -> graph analyses on 33 clean, causally sufficient scenes
  -> primary downstream panel on 27 scenes x 5 tasks
  -> 6 supplementary scenes reported separately

Fresh homogeneous CausalDS P1
  -> 100 generated scenes
  -> linear non-Gaussian SCMs
  -> primary scientific study

CLadder
  -> optional external replication after a defensible P1 result
```

P0 uses nested cohorts. After T04 integrity checks, the graph cohort is frozen at 33 released scenes split into 8 development and 25 holdout scenes. Within it, the primary downstream cohort has 27 scenes with the same five frozen graph-sensitive adjustment/control tasks (7/20), while the remaining 6 scenes form a supplementary exploratory cohort (1/5). Supplementary task results are never pooled into primary accuracy.

P1 uses 100 fresh scenes, split into 20 development and 80 holdout scenes, with 5–7 nodes and `N=2000` primary observations per SCM. Sample-size sensitivity uses `N=500` and `N=10000` on 20 scenes.

## Critical experimental control

The downstream reasoner receives only:

- the supplied graph;
- the query;
- a non-causal variable glossary;
- the required answer schema.

It must not receive the graph-faithful causal story or observational table. Otherwise it could reconstruct the graph from a second information channel and ignore the experimental graph payload.

## Graph semantics

P0 uses the T05-frozen `BOSS + BasisFunctionBicScore` configuration (`penalty_discount=1.0`, `truncation_limit=3`) and treats its raw output as a CPDAG. An undirected edge means that adjacency is supported but direction is not identified. The primary reasoner uses conservative/invariance semantics and returns `undetermined` when compatible DAG extensions imply different answers.

T09 has materialized this configuration for all eight frozen development scenes as canonical raw CPDAGs and parent-linked projected-DAG sensitivity artifacts. These outputs reproduce byte-for-byte and were built from same-scene anonymized observations/schema types only; holdout remains unopened.

T10 has materialized Hybrid H1 for the same eight development scenes. The exact T08 semantic model/configuration oriented only the 27 unresolved raw-CPDAG edges; it did not consume T08 graphs or T09 projected DAGs. All 8 outputs preserve their T09 skeleton, compelled directions, parent hash, and equivalence class, with a confidence/rationale audit for every orientation and byte-exact replay. Holdout remains unopened.

T11 has evaluated five graph views per scene on the same development split, yielding 40 byte-reproducible structural metric records. Oracle graphs were loaded only in memory for grading and their edges were not persisted in metric outputs. T08–T10 were not tuned or modified from these results; tasks and holdout remain unopened. SID/AID are explicitly unavailable until a standard implementation is pinned and validated.

A deterministic consistent DAG extension with lexicographic tie-breaking is evaluated only as sensitivity. It preserves compelled orientations, acyclicity, skeleton, and CPDAG-compatible collider structure.

T06 freezes `fourgraph.graph.v1` as the shared graph boundary. Every method emits canonical `X000...` nodes, directed/undirected edge marks, evidence-scoped provenance, edge audit records, a structure hash, and a full-artifact hash. The reasoner receives only the stripped `fourgraph.reasoner_graph.v1` structure; metrics receive the normalized partial graph. See `docs/graph_contract.md`.

T12 implements the fixed downstream reasoner and both scorers on seven primary development scenes. Its prompt contains only the stripped graph, canonical query, and an ID/type-only glossary. Engineering and replay checks pass, but the tested Gemma model scored only 19/35 with `G_ORACLE`; therefore holdout execution is blocked pending a versioned reasoner refinement.

T12 v2 keeps Gemma as a weaker diagnostic baseline and adds an answer-free 150-case conformance suite. An independently audited GPT-5.4 Mini candidate (`high`, 4096 output tokens) failed its pre-registered 10-case engineering smoke when one case exhausted the entire reasoning budget on all three attempts without returning JSON. The candidate was stopped before conformance/development; holdout remains unopened.

A separately frozen Mini-B candidate changed only the output/reasoning ceiling to 8192. It completed and parsed all 10 smoke cases without retries; the previously truncated case needed 5414 reasoning tokens and answered correctly. Mini-B is technically ready for a separately approved 150-case conformance run, not yet approved for Oracle-development or holdout.

Mini-C raised the ceiling to 10240 and pre-registered an 80% headroom gate. Although all 10 cases eventually parsed, one first attempt consumed the full 10240 reasoning tokens without visible output and required retry, so the gate failed. This rules out simple ceiling escalation as a stable solution; no 150-case or holdout run followed.

Mini-D kept the 10240 ceiling and prompt v2 fixed and changed only reasoning effort from high to medium. It passed smoke, then completed the approved 150-case suite with 150/150 first-attempt parses, zero retries and maximum utilization 50.47%. Strict accuracy was 105/150 = 0.700: CPDAG-answered passed at 0.925, but DAG was 0.560, CPDAG-undetermined 0.7429, and forbidden-controls 7/30. Thus medium resolves the observed runaway/truncation problem but not semantic reliability. Mini-D failed the prospective scientific gate; Oracle-development and holdout remain unopened.

T12 v3 keeps Mini-D's `gpt-5.4-mini-2026-03-17`, `reasoning_effort=medium`, 10240-token ceiling, and canonical JSON graph encoding fixed while replacing the generic v2 prompt with a shared operational base plus exactly one task-specific module. Internal `no_valid_adjustment_set` maps only at the output boundary to official `no_backdoor`; the sentinel distinctions and compatible-DAG invariance procedure are explicit.

The fresh sealed v3 conformance suite was generated with seed 1203: 150 five-node cases, 30 per task, partitioned into 90 answered DAG, 30 invariant CPDAG, and 30 undetermined CPDAG cases. It uses no CausalDS story, answer, or holdout data; the production and independent solvers agree on 150/150 expected targets. After a 10-case smoke passed, the frozen candidate completed full conformance at 146/150 = 0.9733 strict accuracy: DAG 87/90, invariant CPDAG 29/30, undetermined CPDAG 30/30, and every task at least 28/30. All prospective scientific gates passed. Five attempts exhausted the 10240-token ceiling and succeeded on registered retry, so the separate headroom diagnostic failed even though first-attempt schema compliance and all scientific gates passed. Replay regenerates the score and audit artifacts byte-for-byte.

The separately registered T12 v3 Oracle-development gate ran on the seven frozen primary development scenes and only `G_ORACLE`: 34/35 = 0.9714 correct, all 35 outputs schema-valid on the first attempt, every task at least 6/7, and all 12 required empty-sentinel records correct.

The subsequently registered full development matrix is also complete: 175 records across `G_LLM`, raw/projected `G_SCD`, `G_HYBRID`, and `G_ORACLE`, representing 105 unique canonical inputs. Thirty-five parent Oracle calls were inherited, 70 new calls were made, and 70 duplicate-input records reused an identical response. Oracle-answer accuracy was 34/35 Oracle, 33/35 LLM, 31/35 Hybrid, 6/35 projected SCD, and 4/35 raw SCD; uncertainty-aware correctness was respectively 34/35, 34/35, 32/35, 33/35, and 35/35. All integrity gates passed, replay is byte-identical, the reasoner is frozen/holdout-ready, and no holdout was accessed. T13 is now eligible but remains unstarted.

## Non-negotiable controls

- Never pool observations from different scenes/SCMs.
- Never expose grading/oracle data to LLM, SCD, hybrid, or reasoner construction paths.
- Route ground-truth graph access only through the T07 typed Oracle loader; it returns a canonical graph artifact rather than the raw grading document.
- Keep the reasoner provenance-blind and frozen across graph conditions.
- Preserve raw outputs, variable-map/graph/artifact hashes, prompt hashes, configs, seeds, and retries.
- Construct `G_LLM` once per scene from the dedicated public story/schema view; require complete pair decisions and a valid DAG, with no heuristic repair or task conditioning.
- Treat `scene_id`, not a task row, as the independent statistical unit.
- Do not optimize for a predetermined graph-method ranking.

## Outcome policy

Outcomes A–G are co-equal and exploratory within their applicable phase:

- clean P0/P1: A–D;
- SID/AID-compatible analysis: E;
- controlled graph perturbation: F;
- observation robustness: G.

Report effect sizes, confidence intervals, and Benjamini–Hochberg-adjusted results. GO/REFINE/STOP decisions depend on feasibility and experimental quality, not on obtaining a favorable result.

## Canonical detailed plan

`CausalDS.md` is the detailed source of truth. Files `00–06` are compact operational views of that plan.
