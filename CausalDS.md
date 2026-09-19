# Master Plan — Released CausalDS P0 → Fresh Homogeneous Hybrid P1

> Status: P0 closed with `REFINE`; P1-v2 closed at T21 v3-E with a terminal negative validation result. P1-v3 protocol and the Bootstrap-BOSS aggregation layer are frozen/conformant offline: production/reference agreed on all 60 aggregates and 900 thresholded parents. No BOSS/Tetrad study run, new cohort, semantic API call or final-holdout access has occurred. Only offline semantic-reliability/statistical-veto conformance is authorized next.

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

P1 is the primary controlled Hybrid study:

- 100 fresh scenes;
- 20 development and 80 holdout;
- stratified 5–7 node connected DAGs;
- no latent confounding;
- linear non-Gaussian SCMs with independent exogenous noise;
- BOSS + `BasisFunctionBicScore` as the primary CPDAG-producing SCD method;
- DirectLiNGAM as a structural sensitivity comparator only;
- `N=2000` observations per SCM;
- `N=500` and `N=10000` sensitivity on 20 scenes.

Each scene has deterministic `full`, `partial`, and `ambiguous` semantic-evidence variants. H2 performs one global CPDAG-consistent orientation rather than independent edge decisions. The forced view always returns the best consistent extension; the selective view returns that DAG only when development-frozen confidence/conflict rules accept it, otherwise it preserves the unchanged raw CPDAG. Exact details and evidence boundaries are frozen in `configs/p1_hybrid_v1.yaml`.

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

P1 uses BOSS + `BasisFunctionBicScore` as its primary statistical method because the central object is a CPDAG whose unresolved directions can be preserved or semantically oriented. DirectLiNGAM remains a DAG-producing structural sensitivity comparator under the deliberately matched linear, acyclic, non-Gaussian independent-error assumptions; it is not a downstream primary condition.

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
- T13 holdout execution freeze — complete. Exact graph holdout membership is 25 scenes, partitioned into 20 primary and 5 supplementary scenes. The primary panel is fixed at 20 × 5 tasks × 5 graph conditions = 500 downstream records; the 77 supplementary task rows are frozen as exploratory inventory and are not sent through the fixed five-task reasoner or pooled into primary accuracy. Builder/reasoner snapshots, prompts, schemas, canonical `X000...` encoding, SCD/Hybrid methods, retry/cache/failure policy, output paths, structural/downstream metrics, and paired scene-clustered/BH analysis are hash-pinned in `data/manifests/t13_holdout_execution.json`. T13 made zero API calls, read no holdout content/gold/Oracle edges, computed no accuracy, and reports `holdout_accessed: false`, `t14_authorized: true`, `t14_started: false`.
- T14 released P0 — complete as one logical resumable holdout run. The 25-scene graph panel produced 25 LLM DAGs, 25 raw SCD CPDAGs, 25 projected DAGs and 23 Hybrid DAGs; two Hybrid attempts terminated outside the parent equivalence class after frozen retries and no fallback. Grading-only Oracle loading followed the non-Oracle seal and persisted no Oracle edges. All 125 graph schedule rows and 500 primary downstream rows are terminal; the latter comprise 493 answered, five graph-failure and two reasoner-failure records over 245 canonical identities. Outputs replay offline, supplementary downstream remained zero, and T15 aggregate analysis has not started.
- T15 scene-clustered analysis — complete offline with 5,000 paired scene-cluster bootstrap replicates, all registered pairwise contrasts, exact McNemar sensitivity and BH correction by metric family. Holdout directed F1 is 0.949 for LLM, 0.296 for projected SCD and 0.918 for the 23 successful Hybrid graphs. Official downstream accuracy is 0.930 Oracle, 0.820 LLM, 0.710 Hybrid, 0.110 projected SCD and 0.080 raw SCD; uncertainty-aware graph-conformance is reported separately and must not be interpreted as ground-truth graph accuracy. T14 remains byte-replayable and no API call, failure rerun or post-holdout retuning occurred.
- T16 P0 findings and GO/REFINE/STOP — complete with `REFINE`. P0 supports semantic orientation over deterministic projection for direction and official downstream adjustment/control answers, but does not establish H1 superiority over standalone LLM or universal CPDAG/DAG superiority. The two Hybrid failures and residual Oracle-reasoner error remain part of the findings. T17 subsequently converted this decision into the frozen prospective P1 Hybrid protocol; P1 generation/live execution has not started.
- T17 P1 Hybrid protocol design — complete; the generator, semantic-evidence doses, H1/H2 rules, abstention selection, graph/downstream schedule, statistics, evidence boundaries, and stage gates are hash-frozen without generating scenes or calling a model.
- T18 fresh SCM generator, inventory, deterministic split, and task/query generation — complete. The frozen substrate contains 100 eligible linear non-Gaussian SCMs, 500 solver-agreed tasks, exact 20/80 IDs, `N=2000` for every scene, and nested `N=500/10000` for 20 scenes. No live LLM/SCD/Hybrid execution or holdout scoring occurred.
- T19 semantic story variants and blinded manual audit — complete. Generated 300 deterministic public stories (`full`, `partial`, `ambiguous`), hash-pinned 100 adapter-only alias maps, passed text-level truth validation, and completed a 20-development-scene internal blinded QA panel. This QA is explicitly not independent external human validation. No model/method execution or holdout manual review occurred.
- T20 H2 implementation and offline conformance — complete. Production and independent solvers agreed on 150/150 forced decisions and 3,000/3,000 selective decisions; all 30 malformed inputs were rejected and all graph-preservation invariants passed. No API, P1 scene, development result, or holdout result was accessed.
- T21 development-only graph construction and threshold selection — execution complete, gate not passed. Captured 60 shared preference artifacts and 80 API attempts on 20 development scenes; materialized 160 non-Oracle graph rows and 180 structural metric rows. The best threshold candidate reached 0.90 orientation precision at 0.04975 coverage, below the frozen 0.95 gate. No threshold was selected; T22/T23 are unauthorized.
- T21 Amendment v2 — complete, gate still not passed. The isolated 120-case direction/ambiguity conformance suite passed 120/120, ruling out the simple left/right elicitation failure seen as a candidate explanation. With prompt v2, forced orientation precision was 0.776 full, 0.597 partial and 0.463 ambiguous; the best registered selective candidate reached only 0.737 precision at 0.0945 coverage. Standalone LLM partial/ambiguous DAGs and the Oracle-CPDAG diagnostic were evaluation-only and excluded from threshold selection. Even with the Oracle CPDAG, all-pair semantic orientation reached 0.903 full and 0.847 partial, still below 0.95. Further prompt tuning, T22 and P1 holdout access are unauthorized under this protocol.
- T21 Amendment v3-A — complete and design-only. Froze `G_HYBRID_H2_EDGE_SELECTIVE`: exact consistent-extension scoring, semantic-confidence/global-stability grid, exact compatible-subset selection, deterministic Meek closure, per-edge provenance, false-adjacency penalties, and a fail-closed validation gate. Existing development data is engineering-only; threshold selection will require 20 new validation SCMs under a later registered stage. V3-A made zero API calls, generated zero scenes, implemented no method and accessed zero holdout scene artifacts. Only T21 v3-B offline implementation and synthetic conformance are authorized.
- T21 Amendment v3-B — complete and offline. Implemented the decision/partial-graph contracts, exact production solver, independent reference solver and deterministic Meek R1–R4 closure. A balanced 180-case synthetic suite produced 3,600/3,600 production/reference agreements and rejected 40/40 invalid fixtures. V3-B made zero API calls, generated zero validation scenes and accessed zero P1 development/holdout scenes. Only T21 v3-C offline generation and freeze of the new 20-scene validation cohort is authorized; live semantic calls remain forbidden.
- T21 Amendment v3-C — complete and offline. Generated exactly 20 validation-only linear non-Gaussian SCMs under seed 21301 with frozen `P1V000–P1V019` / `scene_110000–scene_110019` mappings, N=2000 observations, 100 graph-sensitive tasks and 60 deterministic semantic stories. Production/reference task solvers agreed 100/100; allocations and raw/versioned hashes are frozen and replay byte-for-byte. V3-C made zero API calls, ran no SCD/H1/H2/reasoner and accessed no existing development/holdout scene artifact. T21 v3-D is now authorized; final holdout access remains forbidden.
- T21 Amendment v3-D — complete, validation gate failed. Ran BOSS on 20/20 validation scenes and captured 60/60 frozen-model semantic responses with zero retry. Evaluated exactly the frozen 5×4 threshold grid. All outputs were graph-valid, but no candidate achieved precision ≥0.95, answered edges ≥20 and coverage ≥0.20 simultaneously. Best precision-first candidate was 83/97 correct (`0.8557`) at `0.4554` coverage with 13 false adjacencies oriented. No threshold was selected, no selected-graph artifact was materialized and final holdout access remains forbidden. Only the terminal v3-E decision is authorized.
- T21 Amendment v3-E — complete, P1-v2 terminal. Recorded the failed validation gate without lowering it or retuning the same cohort, hash-pinned 70 T21 v2/v3 artifacts, confirmed the selected-graph manifest is empty and retained the 80-scene holdout seal. T22 and P1-v2 execution are permanently unauthorized. Only P1-v3 protocol design is authorized, beginning from GPT-5.4 Nano, whole-graph semantic calls and Bootstrap-BOSS primary; ensemble execution is deferred.
- P1-v3 Evidence-Selective protocol freeze — complete and design-only. Frozen 200 Bootstrap-BOSS resamples of size N=2000, independent standardization, four-state edge evidence, 15 statistical threshold pairs, statistical veto, six fixed whole-graph prompt variants, empirical reliability classes, globally valid partial-graph output and risk-controlled selection (`α=0.05`, `δ=0.05`, minimum coverage 0.20). The SCD ensemble is deferred. No Bootstrap implementation/run, cohort generation, API call or final-holdout access occurred. Only offline Bootstrap-BOSS implementation and synthetic conformance are authorized.
- P1-v3 Bootstrap-BOSS offline implementation — complete. Added deterministic row-index generation, per-resample standardization, exact 200-run aggregation, completed-PDAG validation, unconditional four-state rates, conditional diagnostics and thresholded parent construction with fail-closed consistent-extension checks. A 60-case synthetic suite produced 60/60 production/reference aggregate agreements and 900/900 parent agreements; run order, node-input order and immutability passed 60/60, and 30/30 invalid fixtures were rejected. No study observations, Tetrad/BOSS execution, new scenes, API or holdout were accessed. Only offline semantic reliability and statistical-veto conformance is authorized next.
- T22 P1 holdout execution freeze.
- T23 one-time P1 holdout execution.
- T24 P1 analysis, findings, and optional robustness/CLadder replication decision.

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

## 18. P1-v3 semantic reliability and statistical veto

The successor Evidence-Selective protocol now has an offline-conformant semantic layer. Six fixed, variable-order-balanced whole-graph responses are normalized per edge into `very_high`, `high`, `medium`, `uncertain`, or `conflict`. A directed vote is valid only when its evidence quote is an exact directional sentence in the supplied story; association-only text, alias errors, missing pairs and contradictory cause/effect fields fail closed.

Agreement is not treated as a probability. Empirical-reliability records must later be estimated on a new independent calibration cohort and certified by the registered risk-control procedure. Until then every group remains `pending_risk_control`, so it cannot auto-orient an edge. The statistical-veto table excludes weak or absent Bootstrap-BOSS adjacencies, preserves stable statistical directions unless certified semantic evidence agrees, and abstains on certified conflicts. This layer passed synthetic production/reference conformance without any model call, BOSS run or study-data access.

## 19. P1-v3 prospective power and independent cohorts

The successor study uses the scene as the independent inferential unit. For each semantic group or threshold candidate, edge errors are first reduced to a bounded within-scene error fraction; one-sided Hoeffding–Bentkus tests then receive a Bonferroni share of the total failure budget. This prevents pseudo-replication from treating several edges of the same SCM as independent evidence.

The frozen plan contains 40 development scenes, 400 semantic-calibration scenes and 400 threshold-validation scenes. Development is engineering-only. Calibration can certify the six `story variant × Very High/High` groups but cannot choose a statistical threshold. Validation receives the already frozen reliability decisions and may select maximum coverage among the fifteen candidates only once. The three roles use separate namespaces and seeds; old P1 cohorts are diagnostics only and the existing 80-scene final holdout remains sealed.

At least 280 calibration scenes must contribute to a semantic group and at least 340 validation scenes must contribute to a threshold candidate. At these minima, prospective power is respectively 0.849 and 0.872 under a true 1% error design alternative. These numbers are planning assumptions, not performance results. The design created no scene, observation or exact scene-ID manifest and authorized no live method execution.

## 20. P1-v3 successor generator and allocator conformance

The successor generator now implements deterministic exact-marginal allocation and the frozen linear non-Gaussian SCM blueprint family, but the implementation hard-rejects the reserved `P1V3D`, `P1V3C` and `P1V3T` namespaces. A later hash-frozen execution layer is required before real IDs can exist.

Offline conformance used 24 synthetic blueprints across three `SYN*` roles. Production allocation matched an independent reference, every graph/query was reproducible, and the two task solvers agreed on all 120 task targets. No observational array or semantic story was generated. The 40/400/400 real design was checked only for count/range/namespace/seed consistency and remains unmaterialized.

## 21. P1-v3 runtime/cost pilot design

The engineering pilot is frozen as a separate synthetic-only measurement step, not as a scientific experiment. If later authorized, it will generate and replay 9 `SYNPILOT` scenes, time 270 measured Bootstrap-BOSS fits after three excluded warm-ups, and issue 108 whole-graph semantic calls across 6 scenes, 3 story variants and 6 balanced prompt variants. These observations will project the resource envelope for 840 scenes, 168,000 BOSS fits and 15,120 semantic calls using scene-stratified median, p95 and leave-one-scene-out ranges plus a 1.25 reserve.

All feasibility gates are preregistered, including deterministic replay, at least 268/270 successful measured fits with failure rate at most 1%, projected single-worker runtime at most 168 hours after reserve, 100% final API schema success, at least 95% first-attempt schema success, retry rate at most 5%, exact model snapshot, and cost/storage limits. Pilot outcomes cannot tune thresholds, certify edge stability or semantic reliability, or enter any study cohort. Provider rates, budget, machine environment, exact pilot IDs and runners must be hash-frozen in a separate offline preflight before execution can be authorized.
