# Coding Log

## T00 — Bootstrap
- Status: Complete
- Started: 2026-08-27
- Finished: 2026-08-27
- Commit: Not committed
- Config: `configs/pilot.yaml`
- Files changed: `.gitignore`, `pyproject.toml`, `configs/pilot.yaml`, `src/fourgraph/`, `tests/test_bootstrap.py`, `codinglog.md`
- Summary: Created the minimal Python package, CLI, YAML config loader, deterministic seed utility, and tests.
- Tests: `conda run -n cau pytest` — 4 passed
- Results: Package imports as version 0.1.0; `fourgraph --help` and config validation succeed in `cau`.
- Risks: Causal-discovery and model dependencies intentionally deferred until the T01 artifact audit.
- Next: T01 — audit the official NoisyCausal artifact and record `scd_ready`.

## T01 — NoisyCausal artifact audit
- Status: Complete
- Started: 2026-08-27
- Finished: 2026-08-27
- Commit: Not committed
- Config: Not applicable; read-only artifact audit
- Files changed: `.gitignore`, `data/MANIFEST.json`, `docs/data_audit.md`, `codinglog.md`
- Summary: Audited ACL, arXiv, OpenReview, author GitHub, GitHub repository search, Hugging Face, and Zenodo; inspected and hashed all downloaded first-party publication artifacts and the arXiv source archive.
- Tests: Manifest JSON valid; 3/3 cached artifacts match recorded SHA-256 and byte size; `conda run -n cau pytest` — 4 passed; `git diff --check` clean; raw cache confirmed ignored by Git.
- Results: `scd_ready: false`; no public dataset records, complete per-system SCM/CPDs, executable sampler, or repeated same-SCM observational samples were verified.
- Risks: The benchmark may exist privately or under an unindexed future release. Paper descriptions cannot substitute for a downloadable, licensed, versioned data artifact.
- Next: Request the official records/generator from the authors, then re-run T01; otherwise define a separately named regenerated study or select a resampleable benchmark.

## T02 — CausalDS design freeze and release audit
- Status: Complete
- Started: 2026-08-30
- Finished: 2026-08-30
- Commit: Not committed
- Config: `configs/p0_released.yaml`, `configs/p1_fresh.yaml`
- Files changed: `.gitignore`, `README.md`, `CausalDS.md`, `00_CONTEXT.md`–`06_PILOT_CONFIG_SPEC.md`, `configs/`, `data/MANIFEST.json`, `data/manifests/`, `docs/data_audit.md`, `reports/causalds_release_audit.md`, `scripts/audit_causalds_release.py`, `tests/test_bootstrap.py`, `codinglog.md`
- Summary: Froze the released-P0 to fresh-homogeneous-P1 design; pinned the official CausalDS GitHub/Hugging Face/paper revisions; separated graph-builder and reasoner evidence; specified raw CPDAG reasoning, deterministic projected-DAG sensitivity, skeleton-preserving Hybrid H1, the five-task panel, scene-clustered analysis, and phase-scoped co-equal outcomes.
- Tests: Official source archive and public/grading catalogs hashed; reproducible audit script verified 100 scenes, 2,589 tasks, 1,223 Rung-2 tasks, 48 clean scenes, and the nested P0 cohorts (33 graph, 27 primary, 6 supplementary); manifest JSON and both YAML configs valid; `conda run -n cau python -m pytest` — 6 passed.
- Results: `p0_artifact_ready: true`; all 33 graph scenes contain 16,000 public observational rows and 3–7 graph nodes. The 27 primary scenes contain all five frozen tasks; the other 6 are supplementary exploratory cases. GitHub commit `c74671d0a0924efc5bb021fc8966f856d5b80a4f` and Hugging Face revision `2880dfa710d08e076055cb0248ef0c534a93b0fa` are frozen.
- Risks: Released P0 remains heterogeneous, so the exact CPDAG-producing SCD method must be selected only after T04. Conservative CPDAG scoring and deterministic consistent extension still require implementation and formal tests.
- Next: T03 — build the complete scene inventory and provisional nested 8/25, 7/20, and 1/5 stratification; T04 freezes exact IDs/task manifests after integrity checks.

### T02 amendment — Nested P0 cohorts

- Date: 2026-08-30
- Status: Complete
- Scope: Replaced the former single 27-scene P0 view with a nested graph cohort (33), primary downstream cohort (27 x 5 tasks), and supplementary exploratory cohort (6). Recorded provisional splits 8/25, 7/20, and 1/5 with one consistent split role per scene.
- Files changed: `README.md`, `CausalDS.md`, `00_CONTEXT.md`–`06_PILOT_CONFIG_SPEC.md`, `configs/p0_released.yaml`, `data/manifests/causalds.json`, `reports/causalds_release_audit.md`, `scripts/audit_causalds_release.py`, `tests/test_bootstrap.py`, `codinglog.md`.
- Validation: The pinned-source audit reproduced the exact 33 = 27 + 6 partition and all scene IDs; JSON/YAML invariants and package tests pass; `git diff --check` reports no whitespace errors.
- P1: Unchanged.

## T03 — Scene inventory and provisional nested split

- Status: Complete
- Started: 2026-08-30
- Finished: 2026-08-30
- Commit: Not committed
- Config: `configs/p0_released.yaml`
- Files changed: `README.md`, `CausalDS.md`, `05_CODING_AGENT_PLAN.md`, `06_PILOT_CONFIG_SPEC.md`, `configs/p0_released.yaml`, `data/MANIFEST.json`, `data/manifests/causalds.json`, `data/manifests/causalds_scene_inventory.jsonl`, `data/manifests/p0_provisional_split.json`, `reports/t03_scene_inventory_split.md`, `scripts/build_causalds_t03.py`, `src/fourgraph/causalds_inventory.py`, `tests/test_causalds_t03.py`, `codinglog.md`.
- Summary: Built a metadata inventory for all 100 pinned CausalDS scenes, reproduced the nested 33 graph / 27 primary / 6 supplementary eligibility sets, and generated a seeded deterministic provisional split. Stratification balances graph size, density, conceptual data types, structural labels, and broad special-mechanism prevalence without using task answers.
- Tests: `scripts/build_causalds_t03.py --check` reproduces both artifacts byte-for-byte; SHA-256 and byte-size checks pass; `conda run -n cau python -m pytest` — 11 passed; nesting, coverage, one-role, and balance invariants pass.
- Results: Provisional graph dev IDs are `scene_000098`, `scene_000172`, `scene_000402`, `scene_000415`, `scene_000511`, `scene_000719`, `scene_000792`, and `scene_000814`. Primary dev excludes supplementary `scene_000402`. Maximum numeric absolute standardized mean difference is 0.079 for graph and 0.029 for primary; selected loss 0.329 is below the seeded-start median 2.683.
- Risks: T03 verifies released metadata and file presence, not parquet values, empirical missingness/dtypes, or row-level mappings. A one-scene supplementary development subset cannot represent every supplementary motif; supplementary downstream results remain exploratory. All IDs remain provisional.
- Next: T04 — audit parquet/schema integrity and grading isolation for all 33 graph scenes, then freeze exact nested IDs and primary/supplementary task manifests if every gate passes.

## T04 — Data integrity and final cohort freeze

- Status: Complete
- Started: 2026-08-30
- Finished: 2026-08-30
- Commit: Not committed
- Config: `configs/p0_released.yaml`
- Environment: Added PyArrow 23.0.1 to conda environment `cau` and declared `pyarrow>=15,<24` in `pyproject.toml`.
- Files changed: `README.md`, `CausalDS.md`, `00_CONTEXT.md`, `02_DATA_PROTOCOL.md`, `03_EXPERIMENT_PLAN.md`, `05_CODING_AGENT_PLAN.md`, `06_PILOT_CONFIG_SPEC.md`, `pyproject.toml`, `configs/p0_released.yaml`, `data/MANIFEST.json`, `data/manifests/causalds.json`, `data/manifests/p0_data_integrity.json`, `data/manifests/p0_primary_task_manifest.jsonl`, `data/manifests/p0_supplementary_task_manifest.jsonl`, `data/manifests/p0_frozen_split.json`, `reports/t03_scene_inventory_split.md`, `reports/t04_data_integrity.md`, `scripts/audit_causalds_t04.py`, `src/fourgraph/causalds_access.py`, `src/fourgraph/causalds_integrity.py`, `src/fourgraph/causalds_inventory.py`, `tests/test_causalds_t03.py`, `tests/test_causalds_t04.py`, `codinglog.md`.
- Summary: Read actual public observational and test-feature parquet values for all 33 graph scenes; verified schema, dtype, support, missingness, constants, mappings, DAGs, tasks, and public/grading separation; generated separate primary/supplementary task manifests and froze the unchanged T03 nested split.
- Tests: `scripts/audit_causalds_t04.py --check` reproduces four artifacts byte-for-byte; JSON/YAML and recorded SHA-256/size checks pass; `conda run -n cau python -m pytest` — 16 passed; public/grading rejection paths and all integrity/nesting/task gates pass.
- Results: `integrity_ready: true`; 33/33 scenes passed. Across 528,000 observational rows and 120 columns there are zero null, NaN, infinite, constant, binary-support-mismatch, or duplicate-row findings. The primary manifest contains 135 records; the six-scene supplementary manifest contains 89 exploratory records. Exact graph 8/25, primary 7/20, and supplementary 1/5 memberships are frozen without exclusions or replacements.
- Risks: Physical parquet dtype is `float64` for all columns even though 34 columns are conceptually binary; later SCD adapters must use schema/mechanism type metadata rather than dtype alone. T04 does not establish that any P0 SCD assumptions hold and does not read grading test values.
- Next: T05 — evaluate candidate mixed-data/heterogeneous-mechanism discovery methods on frozen development scenes, select the CPDAG-producing P0 method, and freeze its assumptions/config plus deterministic DAG projection implementation.

## T05 — P0 SCD/CPDAG method and projection selection

- Status: Complete
- Started: 2026-08-30
- Finished: 2026-08-30
- Commit: Not committed
- Config: `configs/t05_scd_selection.yaml` (pre-oracle preregistration), `configs/t05_scd_frozen.yaml` (selected method)
- Environment: Retained Python 3.10.20 in conda `cau`; added OpenJDK 21.0.10, JPype 1.6.0, and NumPy 1.26.4. The adapter calls a pinned Tetrad Java jar directly and does not import the current Python wrapper.
- Files changed: `environment.yml`, `pyproject.toml`, `README.md`, `CausalDS.md`, `00_CONTEXT.md`, `01_SCIENCE_TECH_MAP.md`, `03_EXPERIMENT_PLAN.md`, `05_CODING_AGENT_PLAN.md`, `06_PILOT_CONFIG_SPEC.md`, `configs/p0_released.yaml`, `configs/t05_scd_selection.yaml`, `configs/t05_scd_frozen.yaml`, `data/MANIFEST.json`, `data/manifests/causalds.json`, `data/manifests/p0_scd_selection.json`, `data/manifests/t05_dev_graphs.jsonl`, `reports/causalds_release_audit.md`, `reports/t05_scd_method_selection.md`, `scripts/fetch_tetrad_t05.py`, `scripts/evaluate_causalds_t05.py`, `src/fourgraph/causalds_scd.py`, `src/fourgraph/partial_graph.py`, `tests/test_causalds_t05.py`, `tests/test_partial_graph.py`, `codinglog.md`.
- Summary: Audited official mixed/nonlinear discovery assumptions; preregistered 18 eligible/stress configurations before development oracle scoring; ran every configuration on the eight frozen graph-development scenes with an exact rerun; evaluated the three registered finalists over 240 fixed half-sample runs; implemented anonymous typed data loading, CPDAG metrics, exact small-DAG oracle CPDAG conversion, and deterministic Dor--Tarsi consistent extension.
- Tests: T05 `--check` verifies config/split/jar/graph hashes and exactly reruns the selected graph on 8/8 development scenes; all registered full runs returned valid consistent-extension CPDAG contracts and exact rerun matches; `conda run -n cau python -m pytest` — 24 passed; both P0/P1 configs validate; `git diff --check` is clean apart from line-ending notices.
- Results: `p0_scd_ready: true`; selected `BOSS + BasisFunctionBicScore` with `penalty_discount=1.0`, `truncation_limit=3`, and one deterministic data-order start. Macro skeleton F1 is 0.9594, macro CPDAG SHD 0.375, compelled direction precision/recall 1.0/1.0, half-sample skeleton Jaccard 0.9972, and endpoint agreement 0.9970. Holdout and downstream reasoner were not accessed.
- Risks: The official jar is a pinned `7.6.11-SNAPSHOT`; exact hash mitigates software drift but does not make it a stable release. Basis functions approximate rather than exactly match all logic-gate/neural/heterogeneous mechanisms. The selected raw CPDAG leaves 90% of estimated adjacencies unresolved, so primary reasoning must retain conservative CPDAG semantics. Eight development scenes make method-selection uncertainty non-negligible.
- Next: T06 — extend the minimal T05 partial-graph/projection utilities into the canonical cross-builder graph contract, serialization, hashes, and validators without reopening T05 method selection.

## T06 — Canonical graph contract

- Status: Complete
- Started: 2026-08-31
- Finished: 2026-08-31
- Commit: Not committed
- Config: `configs/graph_contract_v1.yaml`; shared interface referenced by `configs/p0_released.yaml` and `configs/p1_fresh.yaml`
- Files changed: `.gitattributes`, `README.md`, `CausalDS.md`, `00_CONTEXT.md`, `01_SCIENCE_TECH_MAP.md`, `02_DATA_PROTOCOL.md`, `03_EXPERIMENT_PLAN.md`, `04_METRICS_PROTOCOL.md`, `05_CODING_AGENT_PLAN.md`, `06_PILOT_CONFIG_SPEC.md`, `configs/graph_contract_v1.yaml`, `configs/p0_released.yaml`, `configs/p1_fresh.yaml`, `data/MANIFEST.json`, `data/manifests/causalds.json`, `data/manifests/graph_contract_v1.json`, `data/manifests/t06_variable_map_example.json`, `data/manifests/t06_graph_contract_examples.jsonl`, `docs/graph_contract.md`, `reports/causalds_release_audit.md`, `reports/t06_graph_contract.md`, `schemas/graph_contract_v1.schema.json`, `schemas/variable_map_v1.schema.json`, `schemas/reasoner_graph_v1.schema.json`, `scripts/build_graph_contract_t06.py`, `src/fourgraph/cli.py`, `src/fourgraph/graph_adapters.py`, `src/fourgraph/graph_contract.py`, `src/fourgraph/partial_graph.py`, `tests/test_bootstrap.py`, `tests/test_graph_adapters.py`, `tests/test_graph_contract.py`, `tests/test_graph_contract_t06_artifacts.py`, `codinglog.md`.
- Summary: Froze `fourgraph.graph.v1` and `fourgraph.variable_map.v1`; implemented deterministic canonical JSON, separate structure/full-artifact hashes, evidence-scoped provenance, exact DAG/CPDAG validation, cross-source adapters, projection/Hybrid parent relationship checks, and isolated reasoner/metrics views.
- Tests: `scripts/build_graph_contract_t06.py --check` reproduced the variable map, five graph examples, and manifest byte-for-byte; both P0/P1 configs and the variable-map CLI validated; `conda run -n cau python -m pytest` — 46 passed.
- Results: All LLM/SCD/Hybrid/Oracle examples share one node universe and artifact type. Identical projected/Hybrid structures share `graph_sha256` but differ in `artifact_sha256`, while their provenance-blind reasoner payloads match. All eight T05-selected development CPDAG records upgrade through the v1 adapter. Holdout data were not accessed and the four T05 freeze hashes remain unchanged.
- Risks: JSON Schema checks record shape only; callers must use the Python semantic and parent-child validators. Exact completed-PDAG validation is deliberately bounded to eight nodes, covering P0/P1 but requiring a versioned algorithm change for larger future graphs. Evidence hashes attest inputs but T07–T10 must still enforce loader-level access isolation.
- Next: T07 — implement the grading-only Oracle loader and prove non-oracle views cannot access ground-truth graph data.

## T07 — Grading-only Oracle loader

- Status: Complete
- Started: 2026-08-31
- Finished: 2026-08-31
- Commit: Not committed
- Config: `configs/t07_oracle_loader.yaml`; integrated into `configs/p0_released.yaml`
- Files changed: `README.md`, `CausalDS.md`, `00_CONTEXT.md`, `02_DATA_PROTOCOL.md`, `03_EXPERIMENT_PLAN.md`, `05_CODING_AGENT_PLAN.md`, `06_PILOT_CONFIG_SPEC.md`, `configs/p0_released.yaml`, `configs/t07_oracle_loader.yaml`, `data/MANIFEST.json`, `data/manifests/causalds.json`, `data/manifests/t07_oracle_loader_audit.json`, `docs/graph_contract.md`, `reports/causalds_release_audit.md`, `reports/t06_graph_contract.md`, `reports/t07_oracle_loader.md`, `scripts/audit_causalds_t07.py`, `scripts/evaluate_causalds_t05.py`, `src/fourgraph/causalds_access.py`, `src/fourgraph/causalds_integrity.py`, `src/fourgraph/causalds_oracle.py`, `src/fourgraph/causalds_scd.py`, `tests/test_causalds_t04.py`, `tests/test_causalds_t07.py`, `codinglog.md`.
- Summary: Added a typed, artifact-scoped grading capability; implemented public-schema-to-canonical mapping and a grading-only Oracle DAG loader that emits `fourgraph.graph.v1`; removed grading access from runtime SCD; moved the T05 development-scoring compatibility helper into the Oracle module; and added runtime, malformed-graph, provenance-blinding, and AST dependency-boundary tests.
- Tests: T07 `--check` reproduced its audit byte-for-byte on 8/8 frozen development scenes; T04 `--check` reproduced the 33-scene integrity/frozen artifacts; T05 `--check` reran and matched selected development graphs; P0, P1, and T07 configs validated; `conda run -n cau python -m pytest` — 59 passed; JSON validation and `git diff --check` passed apart from expected Windows line-ending notices.
- Results: `oracle_loader_ready: true`; all eight development Oracle graphs are valid canonical DAGs with 3–7 nodes and 2–7 edges. The versioned audit contains hashes/counts but no edge list or raw grading fields. Holdout, grading test values, graph images, task scoring, and the downstream reasoner were not accessed. All four T05 freeze hashes remain unchanged.
- Risks: Python access control is an enforceable project boundary, not an operating-system security sandbox; filesystem-capable code could bypass it, so typed capabilities, AST dependency tests, and review must remain mandatory. Parsing `ground_truth.json` necessarily reads its bytes, but the loader consumes and exposes only graph/mapping fields. Holdout integration remains intentionally untested until T14.
- Next: T08 — implement the public-story-only LLM graph builder and emit validated canonical DAG artifacts with raw model/audit logs.

## T08 — Public-story-only LLM graph builder

- Status: Complete — live development gate passed 8/8
- Started: 2026-08-31
- Finished: Not finished
- Commit: Not committed
- Config: `configs/t08_llm_graph_builder.yaml`; integrated into `configs/p0_released.yaml`
- Files changed: `.gitattributes`, `README.md`, `CausalDS.md`, `00_CONTEXT.md`, `01_SCIENCE_TECH_MAP.md`, `02_DATA_PROTOCOL.md`, `03_EXPERIMENT_PLAN.md`, `05_CODING_AGENT_PLAN.md`, `06_PILOT_CONFIG_SPEC.md`, `configs/p0_released.yaml`, `configs/t08_llm_graph_builder.yaml`, `data/MANIFEST.json`, `data/manifests/causalds.json`, `data/manifests/t08_llm_graph_builder_audit.json`, `data/manifests/t08_dev_graphs.jsonl`, `environment.yml`, `prompts/llm_graph_v1.md`, `pyproject.toml`, `reports/t08_llm_graph_builder.md`, `schemas/llm_graph_response_v1.schema.json`, `scripts/audit_causalds_t08.py`, `scripts/run_causalds_t08_live.py`, `src/fourgraph/causalds_public.py`, `src/fourgraph/causalds_oracle.py`, `src/fourgraph/llm_backend.py`, `src/fourgraph/llm_graph.py`, `src/fourgraph/openai_backend.py`, `tests/test_causalds_t08.py`, `codinglog.md`.
- Summary: Added a dedicated public-only CausalDS input view; froze a scene-level all-pairs prompt and strict response schema; implemented exact pair coverage, confidence, DAG, provider-identity, bounded validation retry, no-repair/no-fallback behavior, T06 canonical artifact creation, raw-call records, and hash-verified deterministic replay. Refactored the shared public variable-map loader out of the Oracle module so semantic construction has no grading dependency.
- Live process: Verified the user-scoped project key with a smoke request, then froze OpenAI Responses snapshot `gpt-5.4-nano-2026-03-17`, SDK `3.6.0`, strict JSON Schema, `reasoning_effort=none`, `temperature=0`, `service_tier=default`, `store=false`, and `OPENAI_API_KEY`. The first Structured Outputs request exposed a missing JSON-Schema `type` on the constant version field; the schema was corrected before any successful graph response. One-scene gate `scene_000098` passed, then the runner replayed it and called only the seven remaining development scenes.
- Tests: All 8 frozen graph-development public inputs validate from `story.md` plus `schema.json`; poison/AST tests prove observations, tasks, answers, SCD, Oracle, grading, and holdout paths do not enter the builder. Strict response parsing, pinned OpenAI request parameters, versioned raw prompt/provider payloads, exact-scene replay, retry exhaustion, metadata validation, and prompt drift are tested. The final T08 replay write and `--check` reproduce versioned artifacts byte-for-byte; full repository tests pass 78/78. T04 reproduces all 33 integrity records and frozen task/split artifacts, T05 selected-method check passes, and T06/T07 checks retain their frozen outputs.
- Results: `t08_complete: true`, `llm_graph_builder_ready: true`; 8/8 development DAGs valid, 8 API calls, 0 validation retries, 7,005 input + 2,564 output tokens, holdout 0/25. Raw prompts/responses remain ignored under `results/raw/`; the versioned audit stores hashes and non-secret metadata.
- Blocker: None for T08. Graph accuracy and downstream reasoning have intentionally not been evaluated here.
- Next: T09 — build the frozen development `G_SCD` graph artifacts. Reuse this exact semantic model/configuration later for T10 Hybrid orientation; do not run holdout before its planned gate.

## T09 — Development SCD graph builder

- Status: Complete
- Started: 2026-09-01
- Finished: 2026-09-01
- Commit: Not committed
- Config: `configs/t09_scd_graph_builder.yaml`
- Files changed: `README.md`, `CausalDS.md`, `01_SCIENCE_TECH_MAP.md`, `03_EXPERIMENT_PLAN.md`, `05_CODING_AGENT_PLAN.md`, `06_PILOT_CONFIG_SPEC.md`, `configs/p0_released.yaml`, `configs/t09_scd_graph_builder.yaml`, `data/MANIFEST.json`, `data/manifests/causalds.json`, `data/manifests/t09_dev_scd_cpdag.jsonl`, `data/manifests/t09_dev_scd_projected_dag.jsonl`, `data/manifests/t09_scd_graph_builder_audit.json`, `reports/causalds_release_audit.md`, `reports/t09_scd_graph_builder.md`, `scripts/build_causalds_t09.py`, `src/fourgraph/scd_graph.py`, `tests/test_causalds_t09.py`, `codinglog.md`.
- Summary: Kept T05 method selection closed; pinned the actual Python 3.10.21/Java 21.0.10/JPype 1.6.0/NumPy 1.26.4/PyArrow 23.0.1 runtime and the existing Tetrad JAR hash; built a public-data/schema-only SCD path; emitted canonical raw CPDAG artifacts with SCD edge audits and deterministic projected-DAG children with exact parent hashes and arbitrary-orientation traces.
- Process: The one-scene gate ran `scene_000098` twice and reproduced both graph views exactly. The full build then processed exactly the eight frozen graph-development scenes, wrote 8 CPDAGs and 8 projections, and a second full algorithm run reproduced all versioned outputs byte-for-byte. Runtime-only records remain ignored under `results/raw/t09_scd/`.
- Tests: T09 unit/artifact tests pass 12/12; the full repository passes 90/90. Tests prevent reopening the T05 candidate/parameters, validate both graph views and their parent relationship, enforce anonymous node universes and evidence boundaries, verify set hashes, and confirm exact equality with all eight T05-selected graphs. T04, T05, T06, T07, T08, and the full T09 `--check` all pass without holdout access.
- Results: `t09_complete: true`, `scd_graph_builder_ready: true`; raw CPDAG 8/8, projected DAG 8/8, holdout 0/25. The raw graphs contain 31 pooled adjacencies: 4 directed and 27 undirected (87.1% pooled unresolved; T05's 90% is the macro scene-average).
- Risks: The selected Tetrad build remains a hashed `7.6.11-SNAPSHOT`; released P0 mechanisms remain heterogeneous; most edge directions remain unidentified. Python 3.10.21 differs from the historical T05 selection record's 3.10.20 patch version, but the independent selected-method check and exact per-scene graph comparison remain unchanged.
- Next: T10 — Hybrid H1. Preserve every T09 raw CPDAG skeleton and compelled direction, use the T08-frozen semantic model only for unresolved orientations, and audit every arbitration without holdout access.

## T10 — Hybrid H1 development graph builder

- Status: Complete
- Started: 2026-09-02
- Finished: 2026-09-02
- Commit: Not committed
- Config: `configs/t10_hybrid_graph_builder.yaml`; integrated into `configs/p0_released.yaml`
- Files changed: `README.md`, `CausalDS.md`, `00_CONTEXT.md`, `01_SCIENCE_TECH_MAP.md`, `02_DATA_PROTOCOL.md`, `03_EXPERIMENT_PLAN.md`, `05_CODING_AGENT_PLAN.md`, `06_PILOT_CONFIG_SPEC.md`, `configs/p0_released.yaml`, `configs/t10_hybrid_graph_builder.yaml`, `data/MANIFEST.json`, `data/manifests/causalds.json`, `data/manifests/t10_dev_hybrid_graphs.jsonl`, `data/manifests/t10_hybrid_graph_builder_audit.json`, `prompts/hybrid_orientation_v1.md`, `reports/causalds_release_audit.md`, `reports/t10_hybrid_graph_builder.md`, `schemas/hybrid_orientation_response_v1.schema.json`, `scripts/audit_causalds_t10.py`, `scripts/run_causalds_t10_live.py`, `src/fourgraph/hybrid_graph.py`, `src/fourgraph/t10_openai_backend.py`, `tests/test_causalds_t10.py`, `codinglog.md`.
- Summary: Implemented Hybrid H1 as a strict child of each raw T09 CPDAG. The semantic model can orient only the supplied unresolved adjacencies; it cannot add/delete edges, reverse compelled directions, consume `G_LLM`, use the projected DAG, or repair an invalid output. Every accepted decision records its direction, confidence, and public-story rationale in the canonical graph artifact.
- Live process: Froze the prompt/schema and exact T08 OpenAI configuration. Ran the hardest scene `scene_000511` first (nine unresolved edges), then resumed across all eight development scenes. Resume replayed the gate and made only seven new calls. Raw prompts/responses and provider payloads remain ignored under `results/raw/t10_hybrid/`.
- Tests: Stress gate and all eight live calls passed on their first attempt. Deterministic replay write plus `--check` regenerated the audit and graph set byte-for-byte. T06 parent-child validation confirms exact parent hashes, identical skeletons, preserved compelled directions, acyclic DAGs, no incompatible new collider, exact equivalence-class membership, and one semantic audit per unresolved edge. Unit tests cover exact pair coverage, forbidden `no_edge`, invalid-equivalence retry, retry exhaustion without fallback, prompt contents, and exact T08 model-policy reuse. The full repository passes 97/97; T04, T06, T07, T08, T09, and T10 checks pass, with T09 again confirming exact equality to the T05-selected graph set.
- Results: `t10_complete: true`, `hybrid_graph_builder_ready: true`; 8/8 development Hybrid DAGs; 27/27 unresolved edges oriented/audited; 8 API calls; 0 validation retries; 7,350 input + 1,857 output tokens; skeleton changes 0; compelled-direction changes 0; parent/equivalence validation 8/8; holdout 0/25.
- Boundaries: Observational tables, T08 graph artifacts, T09 projected DAGs, tasks/queries, answers, grading/Oracle, and holdout scenes were not accessed. Reusing T08 means the semantic model/configuration only, not the graph output.
- Risks: A valid Hybrid DAG is still one semantic choice inside the statistical equivalence class; T10 does not establish graph accuracy. The nano model may make weak semantic decisions despite structural validity. These questions move to T11 graph metrics and later downstream reasoning.
- Next: T11 — compute development graph metrics for the canonical graph sources without reopening or tuning T08–T10 from the results.

## T11 — Development graph metrics

- Status: Complete
- Started: 2026-09-02
- Finished: 2026-09-02
- Commit: Not committed
- Config: `configs/t11_graph_metrics.yaml`; integrated into `configs/p0_released.yaml`
- Files changed: `README.md`, `CausalDS.md`, `00_CONTEXT.md`, `01_SCIENCE_TECH_MAP.md`, `03_EXPERIMENT_PLAN.md`, `04_METRICS_PROTOCOL.md`, `05_CODING_AGENT_PLAN.md`, `06_PILOT_CONFIG_SPEC.md`, `configs/p0_released.yaml`, `configs/t11_graph_metrics.yaml`, `data/MANIFEST.json`, `data/manifests/causalds.json`, `data/manifests/t11_dev_graph_metrics.jsonl`, `data/manifests/t11_graph_metrics_audit.json`, `reports/causalds_release_audit.md`, `reports/t11_graph_metrics.md`, `schemas/graph_metric_record_v1.schema.json`, `scripts/evaluate_causalds_t11.py`, `src/fourgraph/graph_metrics.py`, `tests/test_causalds_t11.py`, `tests/test_graph_metrics.py`, `codinglog.md`.
- Summary: Froze a type-aware graph metric contract over `GraphArtifact.metrics_view()`: common skeleton metrics; exact Oracle-CPDAG compelled/unresolved/state metrics; DAG directed/orientation/SHD metrics; and H1 attribution that separates inherited SCD errors from semantic orientation decisions. DAG reversals cost one in SHD, normalization uses `n choose 2`, and scene macros weight each scene equally.
- Process: Hashed the existing T07–T10 artifacts before evaluation, loaded exactly eight development Oracle DAGs through the grading-only T07 capability, evaluated five graph views per scene, and persisted 40 metric records plus an edge-free Oracle audit and descriptive summaries. The evaluator imports no builder/API module and made no model call.
- Results: `t11_complete: true`, `structural_graph_metrics_ready: true`; 40/40 records. Development macro skeleton F1: LLM 1.000, raw/projected SCD and Hybrid 0.959, Oracle 1.000. DAG directed F1: LLM 0.975, projected SCD 0.225, Hybrid 0.918, Oracle 1.000. Raw SCD unresolved rate is 0.900. Of 24 evaluable unresolved edges, Hybrid oriented 23 correctly and deterministic projection 5; three unresolved SCD edges were inherited false-positive adjacencies.
- Interpretation boundary: These are descriptive diagnostics on eight development scenes, not significance-tested findings. Near-ceiling semantic performance may reflect easy stories. No result was used to alter T08–T10; holdout inference remains deferred.
- SID/AID: Both are recorded as `unavailable` with null values, never zero, because no standard implementation has yet been pinned and validated. Raw CPDAGs were not silently projected.
- Reproducibility: `scripts/evaluate_causalds_t11.py --check` regenerates both outputs byte-for-byte. Config hash `C49EACA54BBD9F5218C768DCD16F5F0CFDCC8B1514166F12D225D1DC6280A6E2`; records hash `96FC8C99E19EBA11F2F8177DC744769D93F5662A6AAE1E9DE0D3A5C6106F7A9D`; audit hash `B0CEC26D62F37018A6E61839860E44F24E8F6E05D9355DA81F9BC6595291CC10`.
- Boundaries: Holdout 0/25; LLM calls 0; tasks/queries not accessed; Oracle edges not persisted; builder tuning false.

## T12 — Fixed reasoner and scorers

- Status: Engineering complete; holdout gate blocked by Oracle-condition sanity result.
- Started: 2026-09-04
- Finished: 2026-09-04
- Commit: Not committed
- Config: `configs/t12_reasoner.yaml`; integrated into `configs/p0_released.yaml`.
- Summary: Implemented a fixed provenance-blind graph reasoner view, public-query-to-canonical-ID extraction, ID/type-only glossary, exact compatible-DAG enumeration, conservative CPDAG invariance, narrow grading-only official targets, and separate oracle-answer/uncertainty-aware scorers. Added Google AI Studio Gemma backend with quota-only key rotation and raw-call resume/replay.
- Live run: `gemma-4-31b-it`, `google-genai==2.21.0`, temperature 0; 7 primary dev scenes × 5 frozen tasks × 5 graph views = 175 records. Raw calls remain under ignored `results/raw/t12_reasoner/`; holdout was not accessed.
- Reproducibility: `scripts/run_causalds_t12_live.py ... --check` regenerated the 175 records and audit byte-for-byte. Records hash `BF7515CA02A2DC5B97266E34BE7251A8566860577854B27036F8F146B33C7F5B`; raw-log hash `F1A8FE8942EA386AE79956306D73E84F6CFD055243DBDF40CE823501B4E2209B`.
- Results: overall oracle-answer accuracy 78/175 (0.446), uncertainty-aware 74/175 (0.423); 31 CPDAG targets undetermined. `G_ORACLE` achieved only 19/35 (0.543). Thirty-five calls used at least one format-validation retry, totaling 39 retry attempts.
- Verdict: `t12_complete: true` for implementation and development evaluation; `holdout_reasoner_ready: false`. Register a T12 v2 reasoner refinement/replacement before T13/T14; do not tune T08–T10 from downstream results.

## T12 v2 design amendment — model-independent foundation

- Status: Implementation ready; provider/model and prospective sanity thresholds not selected.
- Started: 2026-09-04
- Finished: 2026-09-04
- T12 v1 preservation: Verified unchanged config hash `28DB680E...E4126`, records hash `BF7515CA...C7F5B`, and audit hash `7B53BEA2...F5E9C`; added a separate holdout-ineligible diagnostic-baseline status artifact.
- Construct validity: Implemented Pearl back-door total-effect sensitivity for the four adjustment tasks. On 28 development Oracle targets, official and standard conventions agree 22 and disagree 6; the bespoke forbidden-controls construct remains explicitly not applicable.
- Synthetic calibration: Deterministically generated 150 CausalDS-answer-free cases: 30/task, 75 DAG answered, 40 CPDAG invariant, and 35 CPDAG undetermined, with required structural/adjustment feature coverage.
- Response contract: Added five one-field task-specific schemas and a v2 parser. Added scene-free query payloads and a canonical cache whose key excludes graph-source labels and forbids response overwrite.
- Boundaries: No v2 provider/model selected, no API call, no holdout access, and no T08–T10 changes.
- Next: pre-register model candidates and sanity thresholds; evaluate candidates on the synthetic suite before the 35-call Oracle-development gate.

## T12 v2 Gemma conformance retest

- Status: Complete; candidate rejected by prospective sanity gates.
- Started: 2026-09-04
- Finished: 2026-09-04
- Config: `configs/t12_v2_design.yaml`.
- Candidate: Google AI Studio `gemma-4-31b-it`, `google-genai==2.21.0`, temperature 0; six comma-separated credentials with rotation only on quota errors.
- Pre-registered gates: parse 1.00; first-attempt schema compliance >=0.95; overall, DAG, CPDAG-answered and CPDAG-undetermined accuracy >=0.90; every task >=0.80.
- Process: Ran all 150 answer-free synthetic cases. Fixed a provider-only constrained-decoding incompatibility for nested arrays by relaxing only the schema sent to Gemini and retaining strict local list/ID/candidate validation. Added the effective provider-schema hash to the canonical cache identity. Raw prompts/provider responses remain ignored under `results/raw/t12_v2_gemma/`.
- Results: parse 1.000; first-attempt schema compliance 0.867; overall accuracy 20/150 = 0.133. DAG 0.107; CPDAG invariant 0.200; CPDAG undetermined 0.114. Per-task accuracy: one-valid 0.300, all-minimal 0.067, minimal-size 0.200, count-valid 0.033, forbidden-controls 0.067.
- Verdict: only the parse gate passed. `causalds_oracle_development_eligible: false`; no 35-call Oracle-development run and no holdout access. Gemma remains a diagnostic/weaker baseline, not the primary measurement instrument.
- Reproducibility: `scripts/run_t12_v2_gemma_conformance.py --check` replayed all 150 cached responses and regenerated records/audit byte-for-byte. Records SHA-256 `12DDADC...AF08`; audit records the complete hashes.
- Tests: full repository 123/123 passed before the live run; focused v2 tests 8/8 passed after the provider-compatibility correction.
- Next: pre-register a stronger reasoner candidate and run the unchanged synthetic conformance gate.
- Next: T12 — fixed reasoner and scorers using graph + query + non-causal glossary only.

## T12 v2 GPT-5.4 Mini candidate

- Status: Engineering smoke complete; frozen candidate rejected before scientific conformance.
- Started: 2026-09-05
- Finished: 2026-09-05
- Config: `configs/t12_v2_openai_mini.yaml`; exact snapshot `gpt-5.4-mini-2026-03-17`, Responses API, OpenAI SDK 3.6.0, reasoning effort high, max output 4096, default service tier, store false, temperature omitted.
- Measurement audit: Independent active-path/exhaustive-orientation solver matched 150/150 synthetic targets. The deterministic 20-case review panel covers all five tasks and four DAG/CPDAG strata; sentinel values remain distinct. Semantic equivalence is diagnostic only.
- Provider compatibility: OpenAI strict Structured Outputs rejected `oneOf` and `uniqueItems`. The provider adapter now translates to the supported equivalent subset while the unchanged local strict parser remains authoritative. These HTTP 400 preflights did not produce model outputs.
- Official smoke: `SYN001` completed and was strict-correct. `SYN024` returned `incomplete/max_output_tokens` on all three registered attempts; each spent 4096 reasoning tokens and emitted zero visible characters. Captured standard-cost estimate is USD 0.059094 for four calls. Raw prompts/responses and preflight archives remain ignored under `results/raw/t12_v2_openai_mini/`.
- Engineering evidence: exact snapshot check passed; token/reasoning usage logging passed; cache/resume passed; `--smoke --check` reproduces the tracked failure audit byte-for-byte; holdout access is false.
- Verdict: `smoke_technical_passed: false`. The 150-case run, 35-call Oracle-development gate, full 175-record development matrix, and holdout were not started. This does not estimate Mini accuracy; it rejects only the frozen `high + 4096` candidate. Any token-budget or effort change requires a separately pre-registered candidate.
- Tests: 129/129 passed before live smoke; 130/130 passed after failure-audit and documentation synchronization.

## T12 v2 GPT-5.4 Mini-B 8192-token diagnostic

- Status: Engineering smoke passed; stopped for manual review before 150-case conformance.
- Started: 2026-09-06
- Finished: 2026-09-06
- Single change: created `configs/t12_v2_openai_mini_b.yaml` and changed only `reasoner.max_output_tokens` from 4096 to 8192 in the scientific runtime. Snapshot, high effort, prompt/schema/suite, smoke cases, evidence boundary, scorer and prospective gates remain unchanged; outputs use a separate raw/cache namespace.
- Results: 10/10 completed and parsed on the first attempt, zero retries, exact snapshot and full usage telemetry. Reasoning-token min/median/max = 447/2396/7937; latency min/median/max = 3395/14247.5/42404 ms. Estimated captured cost USD 0.147282.
- Diagnostic: `SYN024`, which exhausted 4096 tokens three times, answered correctly after 5414 reasoning tokens. This supports a token-ceiling explanation for the earlier failure. `SYN144` used 7937 reasoning tokens, so 8192 still has narrow headroom.
- Accuracy: 9/10 strict-correct, recorded as diagnostic only. `SYN092` returned `{"n":2}` instead of the official `no_backdoor` sentinel; ten smoke cases are not the registered scientific accuracy gate.
- Boundaries: stopped after smoke as planned. No 150-case conformance, Oracle-development, full development matrix, or holdout access.
- Reproducibility: Mini-B `--smoke --check` reproduces the tracked audit byte-for-byte. Audit SHA-256 `08325DE...B5B49`.
- Tests: final repository regression 132/132 passed.

## T12 v2 GPT-5.4 Mini-C 10240-token headroom diagnostic

- Status: Implemented and smoke-run complete; rejected by the prospectively registered headroom gate.
- Started: 2026-09-06
- Finished: 2026-09-06
- Single runtime change: `reasoner.max_output_tokens` 8192 -> 10240. All other model, prompt, schema, evidence, scorer, suite, retry and API settings remain fixed. Added a pre-live maximum-utilization gate of 0.80 over all provider calls, including retries.
- Results: all 10 cases eventually completed and parsed, but 11 calls were required. `SYN054` attempt 0 consumed 10240/10240 reasoning tokens with zero visible output; attempt 1 succeeded with 3324 reasoning tokens. All-call utilization reached 1.00, so `smoke_technical_passed: false`.
- Accuracy diagnostic: 8/10. `SYN024` changed from the correct Mini-B `undetermined` to `no_backdoor`; `SYN092` again returned count 2 instead of the official `no_backdoor` sentinel. Accuracy was not a smoke gate.
- Usage: 6556 input tokens and 36127 output tokens, including 35889 reasoning tokens; estimated captured cost USD 0.1674885.
- Verdict: Raising the ceiling did not remove truncation and exposed substantial run-to-run variability. Do not raise indefinitely or start the 150-case run under Mini-C. No Oracle-development, full matrix, or holdout access occurred.
- Reproducibility: Mini-C `--smoke --check` reproduces the audit; tracked SHA-256 `CCDD368...2F72`.
- Tests: final repository regression 134/134 passed.

## T12 v2 GPT-5.4 Mini-D medium-effort diagnostic

- Status: Engineering/headroom smoke passed; stopped for manual GO before 150-case conformance.
- Started: 2026-09-06
- Finished: 2026-09-06
- Single runtime change: kept `max_output_tokens: 10240` and prompt v2 fixed; changed only `reasoning_effort: high -> medium`. Snapshot, schemas, suite, 10 smoke IDs, evidence boundary, scorer, retry policy and prospective scientific gates are unchanged. Raw/cache use a separate Mini-D namespace.
- Results: 10/10 completed and parsed on first attempt, zero retries; maximum utilization 0.36259766 passed the registered 0.80 gate. Reasoning min/median/max = 286/1248.5/3689; total reasoning tokens 16999; latency min/median/max = 3923/11490.5/24815 ms; estimated captured cost USD 0.082014.
- Controlled comparison: Mini-C high/10240 required 11 calls, hit 1.00 utilization and used 35889 reasoning tokens. Mini-D used about 52.6% fewer reasoning tokens and did not truncate. This supports high-effort runaway in the observed smoke, without claiming a universal causal effect from one stochastic run per condition.
- Accuracy diagnostic: 7/10. `SYN054` and `SYN144` failed CPDAG `undetermined`; `SYN092` again returned count 2 instead of official `no_backdoor`. Ten cases are not the scientific accuracy gate.
- Smoke boundary: the initial run stopped before conformance pending a separate GO/budget decision; that GO was subsequently granted and is documented below. Oracle-development, full matrix and holdout remained blocked.
- Reproducibility: Mini-D `--smoke --check` replays from its effort-specific cache and reproduces the tracked audit.
- Tracked audit SHA-256: `5D0B2750E758248C0A379ED675AF93E590A9A41F9FDEF395B00AADED46E93A12`.
- Full conformance: after explicit GO, resumed the unchanged candidate over all 150 synthetic cases. Ten smoke responses were cache hits and 140 new calls were made. All 150 completed and passed schema validation on attempt zero; no retry or incomplete response occurred.
- Scientific results: strict and semantic-equivalent accuracy 105/150 = 0.700. DAG answered 0.560, CPDAG answered 0.925, CPDAG undetermined 0.742857. Per-task: one-valid 26/30, all-minimal 25/30, minimal-size 24/30, count-valid 23/30, forbidden-controls 7/30.
- Engineering results: all-call maximum utilization 0.5046875, reasoning min/median/max 117/369/5146, latency min/median/max 1566/3627/31129 ms. Total captured usage was 83400 input and 107391 output tokens including 103855 reasoning tokens; estimated standard cost USD 0.5458095.
- Gate verdict: parse, first-attempt schema and CPDAG-answered gates passed. Overall, DAG, CPDAG-undetermined and per-task gates failed. `causalds_oracle_development_eligible: false`; no Oracle-development, full matrix, or holdout access.
- Full-run reproducibility: `--check` regenerated records and audit byte-for-byte from cache. Records SHA-256 `DD0F3D5604CA682C44939BF63C6FA4DD1013970459319C106977146264B62E62`; audit SHA-256 `FCDF82156F88AE355D6A50E6C60C888FCC88BE70DCD7E8C09FC332E02F4C770A`.

## T12 v3 task-specific prompt contract

- Status: Prompt implementation complete; live candidate intentionally blocked pending a fresh sealed suite.
- Started: 2026-09-06
- Finished: 2026-09-06
- Controlled change: retained Mini-D snapshot/runtime and canonical JSON edge-list encoding; replaced only the generic v2 prompt with a shared base plus exactly one routed task-specific module.
- Semantics: operationalized compatible-DAG enumeration, CausalDS path-edge removal, eligible-candidate filtering, subset enumeration, d-separation, per-DAG answers and cross-DAG invariance. Internal `no_valid_adjustment_set` maps only to official `no_backdoor`; `[]`, `[[]]`, `0`, `no_backdoor` and `undetermined` are explicitly distinct.
- Modules: one-valid uses common-set intersection across compatible DAGs; all-minimal, minimum-size, count-valid and forbidden-controls require exact per-DAG answer equality. Forbidden-controls first applies no-valid-set sentinel precedence, then computes forbidden descendants/colliders only when valid sets exist.
- Examples: added five short five-node synthetic examples for empty versus absent valid sets, direct outcome-to-treatment, CPDAG invariant/non-invariant and forbidden controls. No CausalDS story or answer is included.
- Reproducibility: assembler/manifest builder rejects module/task mismatch, reserved markers and non-stripped evidence. Prompt bundle SHA-256 `B56769130309CC64CAD8A356F3D74E437F2C30B6DD42C76DDF3873A9714A10F6`; contract manifest SHA-256 `65912960D159191E8EF2FD0BBBBB425D9F8384C80733040B6ABE6EC40EE53B93`.
- Scientific boundary: the opened v2 suite is diagnostic-only. `live_execution.allowed: false` until a new deterministic 150-case suite (seed 1203) is generated, independently audited and hash-pinned. No API or holdout access occurred.

## T12 v3 sealed synthetic conformance suite

- Status: Complete offline; live candidate frozen for a separate 10-case smoke decision.
- Started: 2026-09-06
- Finished: 2026-09-06
- Generation: Built 150 new five-node cases with seed 1203, 30 per task. Exact strata are 90 DAG answered, 30 CPDAG invariant and 30 CPDAG undetermined. No CausalDS story, answer or holdout data was used; exact v2 graph/query/task identity overlap is zero.
- Sentinel balance: 40 valid-non-empty, 40 valid-empty, 40 internal `no_valid_adjustment_set`/official `no_backdoor`, and 30 `undetermined`. Each task has the same 18/6/6 DAG/invariant/undetermined layout.
- Structural coverage: generator-level minima were frozen before final selection. Final counts include mediation 10, collider 70, confounding 55, direct outcome-to-treatment 62, forbidden control 42, forbidden descendant 31 and multiple adjustment sets 72.
- Independent audit: production `conservative_target` and an independent active-simple-path/exhaustive-CPDAG solver matched targets and answer classes 150/150. A 20-case panel (4/task across four strata) was inspected directly and passed its checklist.
- Frozen smoke: 10 deterministic cases, two per task, cover DAG, invariant CPDAG, undetermined CPDAG and all four registered answer classes.
- Hashes: suite `55B8B8DB...22EECD`; audit `D1AA891943...04F8F`; panel `C722793A50...C3760`; smoke manifest `BFA8187630...5B49C`; prompt bundle remains `B567691303...A10F6`.
- Candidate: `configs/t12_v3_openai_mini.yaml` keeps Mini-D (`gpt-5.4-mini-2026-03-17`, medium, 10240) and pins prompt, suite, audit, panel, smoke and all five schemas. Only the later 10-case smoke is authorized; the 150-case run cannot auto-start.
- Reproducibility: both builders pass `--check`, reproducing prompt and four suite artifacts byte-for-byte. Focused v3 tests pass 11/11.
- Boundary: zero API calls, no Oracle-development call and no holdout access in this task.

## T12 v3 GPT-5.4 Mini live smoke

- Status: Engineering smoke passed; stopped before the 150-case scientific conformance run.
- Started: 2026-09-06
- Finished: 2026-09-06
- Runner: Extended the existing OpenAI runner without changing v2 replay. V3 verifies prompt-contract, assembled task templates, suite, measurement audit, manual panel, smoke manifest and five schema hashes before loading credentials. Added `scripts/run_t12_v3_openai_mini.py` as the candidate-specific entry point and an API-free `--preflight` mode.
- Official API alignment: Responses API with `text.format` Structured Outputs, `store: false`, default service tier, exact snapshot, medium reasoning and 10240 maximum output tokens.
- Preflight: 10 frozen IDs, 10 unique rendered task-routed prompts, all expected response fixtures parse, all hashes match, zero API calls.
- Live process: exactly 10 provider calls for 10 cases; all completed and validated on attempt zero, with zero retries. Exact snapshot and complete usage telemetry were recorded.
- Engineering gates: parse 10/10, first-attempt schema 10/10, snapshot 10/10, usage 10/10, maximum utilization `0.70195312 <= 0.80`, holdout not accessed. `smoke_technical_passed: true`.
- Usage: 16,330 input tokens, 2,560 cached input tokens, 24,304 output tokens including 24,061 reasoning tokens. Estimated standard cost USD 0.1198875. Reasoning min/median/max 308/1134.5/7165; latency min/median/max 2849/9323.5/48590 ms.
- Diagnostic accuracy: 9/10. `V3SYN103` expected official `no_backdoor` for a direct Outcome-to-Treatment DAG but returned count 8. This is diagnostic only and does not authorize prompt editing after suite opening.
- Reproducibility: `--smoke --check` regenerated the audit byte-for-byte from cache. Audit SHA-256 `81AB3F0E40C239EFD4A96BB19DAF3F518619E3A8FFAF35A04724B8D703B29F53`.
- Boundary: stopped after smoke as pre-registered. No 150-case v3 run, no Oracle-development call, no full development matrix and no holdout access.

## T12 v3 GPT-5.4 Mini full conformance

- Status: All prospective scientific conformance gates passed; stopped before the separately authorized Oracle-development gate.
- Started: 2026-09-07
- Finished: 2026-09-07
- Authorization: Added `configs/t12_v3_openai_mini_full.yaml`, pinning the smoke candidate (`8CD0CC...20C6`) and passed smoke audit (`81AB3F...29F53`). The runner rejects scientific-field drift and permits full conformance only under `next_action: full_150_conformance`.
- Offline preflight: 150/150 prompts rendered and expected fixtures parsed; 10 exact smoke cache hits and 140 planned new cases; zero preflight API calls; no holdout access.
- Execution: Preserved all ten smoke responses, made 140 new case calls plus five registered retries. A long provider/transport wait terminated one terminal process; cache-resume continued without re-running completed cases. Final raw history contains 155 calls: 150 completed and five incomplete max-token attempts.
- Accuracy: 146/150 = 0.973333 strict and semantic-equivalent. DAG 87/90, CPDAG invariant 29/30, CPDAG undetermined 30/30. Per task: one-valid 30/30, all-minimal 30/30, minimal-size 29/30, count-valid 29/30, forbidden-controls 28/30.
- Answer-class diagnostics: no-valid 38/40, undetermined 30/30, valid-empty 39/40, valid-nonempty 39/40. Errors: `V3SYN076` and `V3SYN103` missed `no_backdoor`; `V3SYN128` and `V3SYN139` missed forbidden-controls answers.
- Gates: parse, first-attempt schema, overall, DAG, CPDAG invariant, CPDAG undetermined and per-task all passed. `causalds_oracle_development_eligible: true`.
- Engineering caveat: first-attempt compliance was 145/150 = 0.966667, but five attempts exhausted 10240 tokens, so full-run headroom diagnostic failed (`max utilization=1.0`). All five retries succeeded under the frozen policy.
- Usage: 252,411 input tokens, 151,040 cached input tokens and 320,729 output tokens including 317,142 reasoning tokens; estimated standard cost USD 1.53063675, below the USD 4.50 captured-cost stop.
- Reproducibility: records hash `5E707CD91354F73B26963FF020EA18A88B39CF15F7FA50A32ECDC01A1F44F975`; audit hash `7A9721F6F13A940BE176FEAF2AD4ED3E7EDC14D3100B46A8F744EFC327B5C6E1`; cache-only replay regenerated both byte-for-byte.
- Boundary: no Oracle-development call, full development matrix or holdout access occurred. A separate GO remains required for the 35 Oracle-development tasks.

## T12 v3 documentation synchronization

- Status: Complete.
- Date: 2026-09-11.
- Scope: Updated `00_CONTEXT.md`, `CausalDS.md`, `05_CODING_AGENT_PLAN.md`, `README.md`, `reports/causalds_release_audit.md`, and the T12 summary row in `timeline.md` to reflect the sealed-suite, smoke, and 146/150 full-conformance result.
- Integrity boundary: No config, prompt, schema, manifest, score record, audit artifact, raw response, cache, or other hash-pinned input/output was modified. Historical v1/v2 candidate reports remain unchanged.
- Current gate: `causalds_oracle_development_eligible: true`; the separately authorized 35-task Oracle-development run, full development matrix, T13, and holdout remain unstarted.

## T12 v3 G_ORACLE development gate

- Date: 2026-09-11.
- Status: All applicable Oracle-development gates passed; stopped before the full development matrix.
- Registration: Added immutable candidate `configs/t12_v3_openai_mini_oracle_dev.yaml`, pinning the passed v3 conformance audit, exact frozen primary-dev IDs, task manifest, grading-only Oracle loader, prompt bundle, schemas, GPT-5.4 Mini snapshot, medium reasoning effort and 10240-token ceiling. Live authorization is restricted to `oracle_development_35`; automatic full-matrix/T13 execution and holdout access are disabled.
- Preflight: 7 primary development scenes × 5 tasks = 35 prompts; official targets and targets recomputed from Oracle DAGs were semantically equivalent 35/35. Target classes were 20 valid-nonempty and 15 valid-empty. Twelve records required exact empty representations: six `[]`, three `[[]]`, and three integer `0`. No `no_backdoor` target was present and CPDAG uncertainty was inapplicable because `G_ORACLE` is a DAG.
- Live result: 35/35 requests completed and parsed on attempt zero, with zero retries/incomplete responses. Oracle-answer and uncertainty-aware accuracy were both 34/35 = 0.97142857. One-valid reached 6/7; all-minimal, minimal-size, count-valid, and forbidden-controls each reached 7/7. All 12 required empty sentinels were correct.
- Failure retained: `scene_000511:identification__one_valid_adjustment_set` returned `[]`; the remaining fork `X005 <- X000 -> X006` requires a set containing `X000`. This is a reasoner error, not a parser/scorer failure, and no prompt/model retuning was performed after observing it.
- Usage: 55,210 input tokens including 28,160 cached input tokens; 13,846 output tokens including 13,038 reasoning tokens; median reasoning 313, maximum 1,213, maximum ceiling utilization 0.12080078. Estimated standard cost USD 0.0847065.
- Reproducibility: cache-only `--check` regenerated both artifacts byte-for-byte with zero live calls. Config SHA-256 `328DF4A6B76A71BA4B5C5890EC772B26FD87B0403323168C1C53D742BF3ED70C`; runner `CE75D95A4BB12421EF1DAA17D926B2CBF4E10F69A7A376A246C73CC164E54A17`; score records `CB31DC9179DFCD9F4C1EA56500806875EA2BDF7CAF07D5D1CEBD6083D04E20EA`; audit `3CEBE2329EEA2664F37449FF499BD0C323FDB09E9149D736FDA6F69DF0DB71D8`.
- Verdict: `oracle_development_passed: true`, `full_development_matrix_eligible: true`, `holdout_reasoner_ready: false`, `holdout_accessed: false`. The next permissible step is a separately registered full development matrix; T13 and holdout remain unstarted.

## T12 v3 full development matrix

- Date: 2026-09-11.
- Status: Complete; all registered engineering/integrity gates passed and reasoner frozen before holdout.
- Registration: Added `configs/t12_v3_openai_mini_full_development.yaml` as a lifecycle-only successor to the passed Oracle-development candidate. It pins all T08/T09/T10 graph manifests and audits, the grading-only Oracle loader, exact seven primary-dev IDs, five task panels, model snapshot, prompt bundle, schemas, parser/scorers, and parent Oracle raw/cache hashes. No graph-source accuracy threshold was registered because development ranking is exploratory and must not select a favorable result.
- Preflight: 7 scenes × 5 tasks × 5 graph conditions = 175 records. Canonical cache audit found 105 unique inputs, 35 inherited parent identities covering 90 records, and exactly 70 planned new calls. Graph-source labels are excluded from cache identity.
- Execution: Made exactly 70 new API calls, inherited 35 Oracle calls, and reused responses for 70 duplicate-input records. All 105 unique calls completed; 175/175 records were schema-valid on the first attempt, with zero validation retry and zero incomplete response.
- Oracle-answer accuracy: `G_ORACLE` 34/35 (0.9714), `G_LLM` 33/35 (0.9429), `G_HYBRID` 31/35 (0.8857), `G_SCD_PROJECTED` 6/35 (0.1714), and `G_SCD_RAW` 4/35 (0.1143).
- Uncertainty-aware correctness: `G_ORACLE` 34/35, `G_LLM` 34/35, `G_HYBRID` 32/35, `G_SCD_PROJECTED` 33/35, and `G_SCD_RAW` 35/35. Raw SCD had 31 undetermined targets/responses; high uncertainty-aware correctness is graph-conformance, not official-answer accuracy. The projected-DAG gap likewise shows that the reasoner generally followed a structurally wrong/arbitrary projection.
- Usage: Incremental run used 111,650 input tokens including 67,840 cached input tokens and 107,954 output tokens including 106,268 reasoning tokens. Estimated incremental standard cost was USD 0.5237385; total including inherited Oracle calls was USD 0.608445. Maximum utilization was 0.77900391; median reasoning 459 tokens, max 7,954.
- Integrity diagnostic: Initial audit compared runtime tuples with parent JSON lists and falsely counted only 14/35 inherited Oracle matches. The comparison was corrected to canonical JSON bytes, then cache-only replay verified 35/35 without another API call. No scientific field or result changed.
- Reproducibility: `--check` regenerated scores/audit byte-for-byte with zero calls. Config SHA-256 `B687B9AA3D46B7F013B57DC23052B52987F129661580BD44C324F74045B2AF47`; runner `9E3D8C41A4A3998A9326318105A7C474102229ABE48DEF860C909E7E4B7D1D61`; score records `BACD53AB9CD7B184CDB65D017864DD998800BB84ED4388C23F7723102C5F1037`; audit `F13738A8FD4CB17B52E298DB569467B095FA4F506C47CCF72D3485AA8A0FA503`.
- Boundary/verdict: No T08–T10 or reasoner retuning followed the development ranking. `full_development_matrix_passed: true`, `reasoner_frozen_for_holdout: true`, `holdout_reasoner_ready: true`, `t13_eligible: true`, and `holdout_accessed: false`. T13 and T14 remain unstarted.
