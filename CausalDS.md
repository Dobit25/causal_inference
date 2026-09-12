# Master Plan — Released CausalDS P0 → Fresh Homogeneous P1

> Status: design frozen on 2026-08-30. This document supersedes the former NoisyCausal-first execution plan while retaining its negative artifact audit as project history.

## 1. Research objective

For the same causal scene, construct four graph conditions:

\[
G_{LLM},\quad G_{SCD},\quad G_{HYBRID},\quad G_{ORACLE}
\]

and pass them through one frozen graph-guided LLM reasoner. The project asks:

> How do graph provenance, graph uncertainty, and graph errors affect downstream causal adjustment/control reasoning, and which graph metrics best explain that functional utility?

The four information regimes are:

- `G_LLM`: public story and variable semantics only.
- `G_SCD`: anonymized same-scene observational data only.
- `G_HYBRID`: SCD skeleton/CPDAG plus story semantics for unresolved orientation only.
- `G_ORACLE`: grading-only ground-truth DAG.

The reasoner is provenance-blind. Across graph conditions, only the graph payload changes.

## 2. Study architecture

### P0 — Released CausalDS

P0 validates the complete pipeline on a pinned official artifact and provides an exploratory result through nested cohorts:

- graph cohort: 33 clean, fully observed released scenes, T04-frozen split 8 development / 25 holdout;
- primary downstream cohort: 27 of those scenes with the same five adjustment/control tasks, T04-frozen split 7 / 20;
- supplementary cohort: the remaining 6 scenes, T04-frozen split 1 / 5 and reported separately;
- raw SCD CPDAG as the primary statistical graph;
- deterministic projected DAG as sensitivity.

Released scenes have mixed data profiles and heterogeneous SCM mechanisms. P0 must not be presented as a universal test of one homogeneous SCD assumption family.

### P1 — Fresh homogeneous CausalDS

P1 is the primary scientific study:

- 100 fresh scenes;
- 20 development and 80 holdout;
- stratified 5–7 node connected DAGs;
- no latent confounding;
- linear non-Gaussian SCMs with independent exogenous noise;
- DirectLiNGAM as the matched primary SCD method;
- `N=2000` observations per SCM;
- `N=500` and `N=10000` sensitivity on 20 scenes.

Nonlinear additive-noise SCMs and an ANM-compatible SCD method form a later robustness extension, not part of the first P1 result.

### External replication

CLadder is considered only after P1 produces a reproducible result worth testing externally. Its artifact, resampling semantics, latent-variable handling, and graph representation require a separate audit.

## 3. Pinned CausalDS release

Official sources:

- GitHub: <https://github.com/andleb/causalds>
- Hugging Face: <https://huggingface.co/datasets/andleb/causalds>
- Paper: <https://arxiv.org/abs/2607.08093>

Pinned versions:

- GitHub commit: `c74671d0a0924efc5bb021fc8966f856d5b80a4f`.
- Hugging Face revision: `2880dfa710d08e076055cb0248ef0c534a93b0fa`.
- Paper: arXiv `2607.08093v1`, submitted 2026-07-09.
- Code license: Apache-2.0.
- Data license: CC0-1.0; cite CauseNet for CauseNet-seeded verbalizations.

The release contains public scene data and an explicit grading view. “Private” means grading-only access within the experiment, not unavailable data. Loader boundaries must enforce this distinction.

The T02 audit at the pinned revisions verifies:

```text
100 scenes
2,589 complete-catalog tasks
1,223 Rung-2 tasks
48 clean scenes
33 clean scenes without latent nodes
33 graph-eligible clean/no-latent scenes
27 primary downstream scenes satisfying all five frozen task requirements
6 supplementary exploratory scenes
16,000 public observational rows per selected scene
3–7 graph nodes in the selected cohort
```

Provenance and hashes are in `data/manifests/causalds.json`; interpretation is in `reports/causalds_release_audit.md`.

## 4. Experimental unit and nesting

The independent unit is the causal scene/SCM:

\[
SCM_s \rightarrow D_s=\{x^{(1)},\ldots,x^{(N)}\}
\]

and:

\[
SCM_s \rightarrow Q_s=\{q_{s1},\ldots,q_{s5}\}.
\]

Never pool questions or rows from different SCMs into one discovery table. Tasks and four graph conditions are repeated measurements nested within `scene_id`.

## 5. Released P0 nested cohorts and tasks

Graph-cohort eligibility requires:

1. pinned main scene bank;
2. clean observation variant;
3. no latent nodes;
4. ground-truth DAG available in the grading view;
5. public schema/data mapping available.

This yields 33 graph-eligible scenes for graph construction, SCD selection, structural metrics, hybrid orientation metrics, and graph-quality Outcome A.

Primary downstream eligibility additionally requires all five tasks in this frozen priority:

1. `identification__one_valid_adjustment_set`;
2. `identification__all_minimal_adjustment_sets`;
3. `identification__minimal_adjustment_set_size`;
4. `identification__n_valid_adjustment_sets`;
5. `bias_diagnostic__forbidden_controls_list`.

The general contract allows 2–5 tasks per scene, maximum five. Twenty-seven graph-cohort scenes contain all five, yielding the primary homogeneous downstream panel. The other six scenes remain supplementary exploratory cases; their task results are never pooled into primary accuracy.

The frozen nested cohorts are:

```text
Graph cohort: 33 scenes, dev 8 / holdout 25
├─ Primary downstream: 27 scenes × 5 tasks, dev 7 / holdout 20
└─ Supplementary: 6 scenes, dev 1 / holdout 5
```

Primary and supplementary cohorts partition the graph cohort. A scene must keep the same dev/holdout role in every cohort to which it belongs. T03 built the provisional deterministic stratified split; T04 verified all 33 scenes and froze the same IDs without exclusions or replacements.

## 6. Information and leakage contract

| Information | LLM | SCD | Hybrid | Oracle | Reasoner |
|---|---:|---:|---:|---:|---:|
| Public causal story | Yes | No | Yes | No | No |
| Variable semantics | Yes | No | Yes | No | Non-causal glossary only |
| Observational table | No | Yes | Yes | No | No |
| Ground-truth graph | No | No | No | Yes | Only as explicit oracle payload |
| Gold answer | No | No | No | No | Scoring after inference |
| Holdout results | No tuning | No tuning | No tuning | No tuning | No tuning |

The public CausalDS story is graph-faithful. Passing it to the downstream reasoner would create a second graph-information channel and invalidate the “only graph changes” treatment. Therefore the reasoner receives only graph, query, non-causal glossary, and output schema.

Use code-level allowlists and separate loader types. Prompt instructions alone are not a security boundary.

## 7. Graph conditions

### 7.1 G_LLM

Input:

- public story;
- public variable names/types/semantics.

Forbidden:

- observational table;
- grading graph;
- gold answer.

Output: validated canonical DAG plus raw model output, edge confidence, rationale, retry count, and graph hash.

T08 implements this as one scene-level call, independent of downstream tasks. A dedicated public loader exposes only `story.md` plus names/types/semantics from `schema.json`. The prompt requires a decision for every unordered node pair exactly once; the parser rejects incomplete pairs, unknown fields/nodes, invalid confidence, duplicate pairs, and cycles. Invalid output is retried at most twice, with no heuristic repair or fallback graph. Valid output passes through the T06 LLM adapter.

T08 is complete on the frozen development split. The live adapter uses OpenAI Responses with immutable snapshot `gpt-5.4-nano-2026-03-17`, OpenAI SDK `3.6.0`, strict JSON-schema output, `reasoning_effort=none`, `temperature=0`, `service_tier=default`, and `store=false`. All 8/8 development scenes produced valid canonical DAGs in one attempt; the ignored raw log replays the versioned graph set byte-for-byte. No holdout scene is accessed before T14. The same frozen semantic model/configuration is reserved for T10 Hybrid orientation.

### 7.2 G_SCD

Input: only the same-scene observational table with anonymized identifiers.

P0 output:

```text
G_SCD_RAW       = CPDAG
G_SCD_PROJECTED = deterministic consistent DAG extension
```

The raw CPDAG is primary. The projected DAG is sensitivity only. T05 selected BOSS with `BasisFunctionBicScore` (`penalty_discount=1.0`, `truncation_limit=3`, one deterministic data-order start) on the eight frozen graph-development scenes. This basis-function method supports mixed smooth nonlinear dependence; it does not erase the documented heterogeneous-mechanism and faithfulness limitations.

T09 materialized this frozen method on all eight development scenes as canonical `fourgraph.graph.v1` artifacts: 8/8 raw CPDAGs and 8/8 parent-linked deterministic projected DAGs. A full rerun reproduced the artifacts byte-for-byte, the raw graphs exactly match the T05-selected outputs, and no story, LLM, task, Oracle, grading, or holdout input was accessed.

P1 uses DirectLiNGAM because fresh SCM assumptions are deliberately matched to linear, acyclic, non-Gaussian independent-error identification.

### 7.3 G_HYBRID H1

H1 is formally:

\[
\boxed{\text{SCD skeleton and compelled directions} + \text{semantic orientation of unresolved edges}}
\]

Rules:

- preserve SCD adjacency;
- preserve compelled orientations;
- send only unresolved pairs to the semantic LLM;
- forbid edge addition and deletion;
- reject cycles and CPDAG-incompatible collider changes;
- require one semantic direction for every unresolved adjacency; reject the scene after the bounded retry budget rather than inventing `unknown`, deleting an edge, or falling back to the deterministic projection;
- persist edge-level arbitration.

H1 tests semantic orientation assistance. It is not a general hybrid adjacency-repair method.

T10 has now materialized H1 on all eight frozen development scenes. It reused the exact T08 OpenAI snapshot/configuration but never read the T08 `G_LLM` graph artifacts. Starting from each raw T09 CPDAG, it oriented 27/27 unresolved edges with one confidence/rationale audit per decision and produced 8/8 canonical parent-linked DAGs. The T06 validator confirmed unchanged skeletons and compelled directions, exact parent hashes, acyclicity, and Markov-equivalence membership. All eight calls passed without validation retry; replay regenerates the graph set byte-for-byte. Observational tables, projected DAGs, tasks, grading/Oracle, and holdout scenes were not accessed.

### 7.4 G_ORACLE

Load the grading-only DAG through a dedicated adapter. Use it for graph metrics and the explicit oracle reasoner condition. Never use it to choose, orient, repair, or tune non-oracle graphs.

T07 implements this boundary in `fourgraph.causalds_oracle`. Public schema order creates the shared `X000...` variable map; only the required graph/mapping subsection of grading `ground_truth.json` is converted to an `oracle/dag/dag` artifact. The loader never returns the raw grading record. Typed grading purposes and architecture tests keep the runtime SCD module free of grading dependencies. Integration validation covers the eight frozen graph-development scenes only; holdout Oracle graphs are deferred to T14.

## 8. Canonical graph contract

T06 freezes `fourgraph.graph.v1` as the one cross-builder artifact used by LLM, SCD, Hybrid, Oracle, reasoner, and graph metrics. Its structural core represents both directed and undirected edges (abridged audit view below):

```json
{
  "schema_version": "fourgraph.graph.v1",
  "scene_id": "scene_000001",
  "graph_method": "scd",
  "graph_type": "cpdag",
  "graph_view": "cpdag",
  "nodes": ["X000", "X001", "X002"],
  "edges": [
    {"source": "X000", "target": "X001", "mark": "directed"},
    {"source": "X001", "target": "X002", "mark": "undirected"}
  ],
  "provenance": "builder/evidence/config/input/parent hashes",
  "edge_audit": [],
  "graph_sha256": "structure only",
  "artifact_sha256": "structure plus audit metadata"
}
```

Required invariants:

- fixed contiguous node universe `X000...` from public schema order, with anonymized/public mapping in a separate hashed variable-map artifact;
- deterministic node/edge ordering and serialization;
- no duplicate edges or self-loops;
- graph-type validation;
- deterministic SHA-256 structure and full-artifact hashes;
- DAG acyclicity where required;
- exact completed-PDAG validity for the project graph-size range;
- method-specific evidence allowlists and parent/input/config provenance hashes;
- a provenance-blind reasoner view and a normalized metrics view.

JSON Schema validates record shape; the Python validator is authoritative for graph theory, leakage policy, and parent-child relationships. The complete contract is documented in `docs/graph_contract.md`, frozen by `configs/graph_contract_v1.yaml`, and indexed by `data/manifests/graph_contract_v1.json`.

### Deterministic DAG projection

The sensitivity projection:

1. keeps compelled directions;
2. selects a CPDAG-consistent DAG extension;
3. uses lexicographic tie-breaking;
4. preserves the skeleton;
5. introduces no forbidden cycle or incompatible unshielded collider;
6. logs every arbitrary orientation.

The serialized child must also reference the exact parent CPDAG artifact hash. A relationship validator reproduces the deterministic trace and checks each unresolved edge exactly once.

Hybrid H1 uses the same parent relationship contract but records each orientation as a non-arbitrary semantic decision. It must preserve the parent skeleton, compelled directions, and Markov equivalence class.

The result is an interface/sensitivity artifact, not additional statistical evidence.

## 9. Fixed reasoner and CPDAG semantics

The reasoner contract is:

\[
R(G,q,v)\rightarrow \hat y,
\]

where `v` is a non-causal variable glossary.

Freeze model snapshot, system prompt, graph encoding, task view, temperature, max tokens, parser, scorer, and retry policy. Do not reveal graph provenance.

### Conservative/invariance rule

For a CPDAG:

- `X -> Y` is compelled/directed information;
- `X -- Y` means direction unknown;
- evaluate the task across CPDAG-compatible DAG extensions;
- return the invariant answer if every extension agrees;
- return `undetermined` if compatible extensions imply different answers.

Two scores are mandatory:

1. `oracle_answer_accuracy`: agreement with the true-scene answer;
2. `uncertainty_aware_correctness`: an invariant answer is correct when identified; `undetermined` is correct when the CPDAG does not uniquely determine the answer.

Projected-DAG sensitivity uses the official task answer schema.

## 10. Graph metrics

For all graph sources:

- skeleton precision/recall/F1;
- adjacency false positives/negatives;
- validity and node consistency.

For raw CPDAG:

- compelled-orientation correctness;
- incorrect compelled orientations;
- unresolved orientation rate;
- CPDAG-compatible skeleton SHD.

For DAGs and projected-DAG sensitivity:

- directed-edge precision/recall/F1;
- orientation accuracy conditional on correct adjacency;
- SHD and normalized SHD.

SID/AID enter only when graph type, node sets, and implementation assumptions are compatible. Missing compatibility is reported as unavailable, never as zero.

T11 now freezes and implements these structural metrics on the eight development scenes. Skeleton SHD is adjacency FP + FN; DAG SHD compares unordered-pair states with reversal cost one; CPDAG state SHD retains absent/undirected/directed distinctions; normalization uses `n choose 2`; and all summaries are equal-weight scene macros. It produced 40/40 records for `G_LLM`, raw/projected `G_SCD`, `G_HYBRID`, and in-memory grading-only `G_ORACLE`. No LLM call, task access, builder adjustment, Oracle-edge persistence, or holdout access occurred. SID/AID remain null/unavailable pending a pinned validated implementation.

## 11. Statistical design

For each primary downstream scene and graph method, aggregate the five task outcomes first:

\[
Accuracy_{s,m}=\frac{1}{5}\sum_{t=1}^{5}Correct_{s,t,m}.
\]

Then compare graph methods with paired scene-level inference.

- Independent/bootstrap unit: `scene_id`.
- Primary uncertainty: paired scene-clustered bootstrap, 5000 repetitions.
- McNemar: sensitivity only.
- Correlation: Spearman with scene-clustered uncertainty or method-specific scene-level analysis.
- Multiple tests: Benjamini–Hochberg within each declared phase family.
- Use all 33 graph scenes for graph-level analyses and the fixed 27×5 panel for primary downstream analyses.
- Never treat 27×5×4 answers as independent SCM samples or pool supplementary task accuracy into the primary panel.

## 12. Co-equal outcome families

The project has no single privileged positive-result endpoint. Outcomes are co-equal and exploratory within the phase where they are available:

- A: graph-quality ranking;
- B: downstream graph-condition ranking;
- C: disagreement between structural and downstream rankings;
- D: oracle gap and residual oracle error;
- E: SID/AID relationship to utility when compatible;
- F: controlled deletion/addition/reversal effects;
- G: observation-layer robustness effects.

Clean P0/P1 reports A–D. E is conditional; F and G are later experiments. Report effect sizes and confidence intervals for null, adverse, and favorable results alike. GO/REFINE/STOP depends on pipeline validity, sufficient variation, scorer validity, leakage control, and reproducibility.

## 13. Reproducibility record

Persist at least:

```json
{
  "scene_id": "...",
  "task_id": "...",
  "graph_method": "llm|scd|hybrid|oracle",
  "graph_view": "cpdag|projected_dag|dag",
  "graph_schema_version": "fourgraph.graph.v1",
  "variable_mapping_sha256": "...",
  "graph_sha256": "...",
  "graph_artifact_sha256": "...",
  "prompt_hash": "...",
  "model_id": "...",
  "model_version": "...",
  "raw_output": "...",
  "parsed_answer": "...",
  "gold_answer": "...",
  "oracle_answer_correct": true,
  "uncertainty_aware_correct": true,
  "latency_ms": null,
  "input_tokens": null,
  "output_tokens": null,
  "retry_count": 0
}
```

For hybrid, also persist statistical support, CPDAG mark, LLM proposal/confidence, final decision, and decision reason for every candidate edge.

## 14. Development and holdout

### P0

- Graph cohort: frozen development 8, holdout 25.
- Primary downstream cohort: frozen development 7, holdout 20.
- Supplementary cohort: frozen development 1, holdout 5.
- T04 data integrity froze the exact IDs and task manifests before T05 method selection.

### P1

- Development: 20 scenes.
- Holdout: 80 scenes.

Development permits loader/parser debugging, P0 SCD choice, prompt syntax, and policy implementation. Before holdout, freeze scene/task IDs, prompts, model snapshot, SCD config, graph contract, projection, hybrid rules, scorers, metrics, exclusions, and statistics. Any modification creates a new experiment version.

## 15. Execution sequence

- T00 Bootstrap — complete.
- T01 NoisyCausal artifact audit — complete, negative readiness result.
- T02 CausalDS design freeze and release audit — complete.
- T03 scene inventory, eligibility, and provisional nested 8/25, 7/20, and 1/5 splits — complete.
- T04 public data integrity, grading isolation, and final nested split/task-manifest freeze — complete.
- T05 P0 SCD/CPDAG method and projection implementation choice — complete; `p0_scd_ready: true`.
- T06 canonical graph contract — complete; `fourgraph.graph.v1` is frozen with cross-builder adapters, semantic validators, canonical hashes, and provenance-blind consumer views.
- T07 grading-only Oracle loader — complete; 8/8 development DAGs valid, raw grading content isolated, no holdout access.
- T08 public-story-only LLM graph builder — complete; OpenAI `gpt-5.4-nano-2026-03-17`, 8/8 development DAGs valid and replayable, no retries, no holdout access.
- T09 SCD graph builder — complete; 8/8 raw development CPDAGs and 8/8 deterministic projected-DAG sensitivity artifacts, byte-reproducible with no holdout/semantic/Oracle access.
- T10 Hybrid H1 — complete; 8/8 development DAGs, 27/27 semantic orientations audited, unchanged T09 skeletons/compelled directions, byte-replayable, and no forbidden/holdout access.
- T11 graph metrics — complete; 40/40 development records, type-correct CPDAG/DAG metric families, Hybrid attribution, byte-reproducible, and no builder tuning/holdout access.
- T12 fixed reasoner and two scorers — implementation and development run complete: 175/175 records, exact conservative CPDAG targets, and byte-for-byte replay. The selected Gemma reasoner reached only 19/35 on the Oracle-graph sanity condition, so `holdout_reasoner_ready: false`; refine under a new version before T13/T14.
- T12 v2 design amendment — model-independent foundation complete. T12 v1 is preserved as a holdout-ineligible diagnostic baseline; a 150-case CausalDS-answer-free conformance suite, five task-specific response schemas, canonical identical-input response cache, and Pearl back-door construct-validity sensitivity are frozen.
- T12 v2 GPT-5.4 Mini candidate — measurement audit matched 150/150 targets, but the frozen `gpt-5.4-mini-2026-03-17` high-reasoning/4096-token candidate failed the 10-case engineering smoke: one case completed correctly and a second exhausted all 4096 reasoning tokens on three attempts without visible JSON. The run stopped after four captured calls; no 150-case conformance, Oracle-development, full development matrix, or holdout run occurred. A separately pre-registered candidate is required.
- T12 v2 GPT-5.4 Mini-B diagnostic — changed only `max_output_tokens` from 4096 to 8192. All 10 smoke cases completed and parsed on the first attempt; the previously truncated case answered correctly after 5414 reasoning tokens. Smoke strict accuracy was 9/10 for diagnosis only, and one case used 7937 reasoning tokens. Mini-B is technically eligible for the 150-case conformance gate, but that run awaits a separate budget/GO decision; holdout remains unopened.
- T12 v2 GPT-5.4 Mini-C headroom diagnostic — changed only the ceiling from 8192 to 10240 and pre-registered maximum utilization <=0.80. All 10 cases eventually parsed, but `SYN054` exhausted 10240 reasoning tokens with no visible output before succeeding on retry with 3324. All-call utilization was 1.00, so Mini-C failed the headroom gate and was stopped before 150-case conformance. This demonstrates run-to-run variability and argues against indefinitely increasing the ceiling.
- T12 v2 GPT-5.4 Mini-D effort/conformance diagnostic — held the 10240 ceiling and prompt v2 fixed, changing only reasoning effort from high to medium. The smoke passed without retry. The approved full run then completed 150/150 responses on the first attempt with maximum utilization 0.5047 and cost USD 0.5458095, but strict accuracy was only 105/150 = 0.700. CPDAG answered passed at 0.925, while DAG was 0.560, CPDAG-undetermined 0.7429, and forbidden-controls only 7/30. Mini-D failed four scientific gates and is not Oracle-development or holdout eligible.
- T12 v3 prompt contract — complete. Mini-D runtime and canonical JSON graph encoding remain fixed; prompt input is a shared operational base plus exactly one of five task-specific modules. Internal `no_valid_adjustment_set` maps only at the output boundary to official `"no_backdoor"`; sentinel precedence and CPDAG per-task invariance are explicit. The opened v2 suite remains diagnostic-only.
- T12 v3 sealed conformance suite — complete. Seed 1203 produced 150 new five-node cases with 30 per task: 90 answered DAG, 30 invariant CPDAG, and 30 undetermined CPDAG. It uses no CausalDS story, answer, or holdout evidence, has zero exact v2 case overlap, and two independent implementations agree on 150/150 expected targets. The 20-case manual panel and deterministic 10-case smoke manifest are frozen and hash-pinned.
- T12 v3 GPT-5.4 Mini conformance — all prospective scientific gates passed. The 10-case smoke passed its engineering gates, then the frozen full run reached 146/150 = 0.9733 strict accuracy: DAG 87/90, invariant CPDAG 29/30, undetermined CPDAG 30/30, with every task at least 28/30. Five of 155 captured attempts exhausted the 10240-token ceiling and succeeded on registered retry, so the separate headroom diagnostic failed; records/audit still replay byte-for-byte.
- T12 v3 `G_ORACLE` development gate — passed. The separately registered run covered exactly 7 frozen primary development scenes × 5 tasks and reached 34/35 = 0.9714. All 35 outputs were schema-valid at the first attempt, every task reached at least 6/7, all 12 required empty sentinels were correct, and cache-only replay was byte-identical.
- T12 v3 full development matrix — passed. The separately registered 7 × 5 × 5 run produced 175 records from 105 unique canonical inputs, inherited all 35 Oracle identities, made 70 new calls, and reused responses across identical graph/query/glossary inputs. Oracle-answer accuracy was 34/35 Oracle, 33/35 LLM, 31/35 Hybrid, 6/35 projected SCD, and 4/35 raw SCD; uncertainty-aware correctness was 34/35, 34/35, 32/35, 33/35, and 35/35. All integrity gates passed, no ranking-driven retuning occurred, and `reasoner_frozen_for_holdout`, `holdout_reasoner_ready`, and `t13_eligible` are true. T13 and holdout remain unstarted.
- T13 frozen task manifest validation.
- T14 released P0.
- T15 scene-clustered analysis.
- T16 P0 findings and GO/REFINE/STOP.
- T17 fresh P1 generation.
- T18+ P1, robustness, and optional CLadder replication.

## 16. Final information flow

```text
Public story ------------------------> G_LLM -------\
Public observations ----------------> G_SCD --------\
Story + G_SCD unresolved edges -----> G_HYBRID ------+--> same frozen reasoner
Grading-only truth -----------------> G_ORACLE ------/
```

Oracle never flows into LLM, SCD, or hybrid. The reasoner never receives the causal story or observational data.

## 17. Governing principle

The project does not seek a predetermined ranking such as `Hybrid > LLM > SCD`. It seeks a reproducible answer about how graph provenance, identifiable uncertainty, and structural error propagate into downstream causal adjustment/control reasoning.
