# T02 — CausalDS Release Audit

## Verdict

```yaml
artifact_verified: true
reasoning_ready: true
graph_eval_ready: true
task_panel_ready: true
observational_data_ready: true
oracle_ready: true
p0_artifact_ready: true
p0_scd_method_selected: true
p0_scd_ready: true
```

The pinned official CausalDS release is sufficient for the released P0 four-graph study. It provides same-scene observational tables, public stories and schemas, complete per-scene task catalogs, stable scene/task linkage, and grading-only ground-truth DAGs. The audit verifies a nested design: 33 clean, causally sufficient graph scenes; 27 of them form the primary five-task downstream panel; the remaining 6 are supplementary exploratory scenes.

T05 selected `BOSS + BasisFunctionBicScore` with penalty discount `1.0` and truncation limit `3` using only the eight frozen graph-development scenes. The full evidence and assumptions are in `reports/t05_scd_method_selection.md`; no holdout scene or downstream reasoner result was used.

## Immutable pins

| Source | Revision | Retrieved | License/use |
|---|---|---|---|
| [Official GitHub repository](https://github.com/andleb/causalds) | `c74671d0a0924efc5bb021fc8966f856d5b80a4f`, commit date 2026-07-17 | 2026-08-30 | Code Apache-2.0; repository `data/` CC0-1.0 |
| [Official Hugging Face dataset](https://huggingface.co/datasets/andleb/causalds) | `2880dfa710d08e076055cb0248ef0c534a93b0fa`, last modified 2026-07-25 | 2026-08-30 | Data CC0-1.0 |
| [arXiv paper](https://arxiv.org/abs/2607.08093v1) | `2607.08093v1`, submitted 2026-07-09 | 2026-08-30 | Paper publication terms |

CauseNet-seeded scene verbalizations derive from CauseNet material under CC BY 4.0 and require citation even though the CausalDS data release is CC0.

## Cached artifact hashes

Raw artifacts are immutable caches under `data/raw/causalds/` and are excluded from Git.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| GitHub source archive at `c74671d0…` | 236,872,831 | `C0D9DC32671C46A989AEE2A0903CE46127372F5C9485AA0B9D9250C69F3E804F` |
| Hugging Face `catalogs/main.parquet` | 168,811 | `2F941D1D754DBFB2AF0495480FE62DDFF2FC27620F5C1260BF55A55BC9C01D2D` |
| Hugging Face `catalogs/grading.parquet` | 12,491,813 | `48E5DFFFFCF4B1978CBEBC5212E6EA484FE0C1A33367CD10BACD28D9DC58FF58` |

The two catalogs embedded in the GitHub archive have identical sizes and SHA-256 hashes to the independently downloaded Hugging Face artifacts.

The extracted source archive contains 1,555 files totaling 398,556,967 bytes. An audit scope comprising 100 `tasks.json`, 100 `schema.json`, and 100 `ground_truth.json` files has aggregate digest:

```text
2cf937101fbd5ba2e16c16ffe851e61dd7808e0868cf71500f3a3b1b6b6fc68c
```

The digest is computed over sorted lines of `relative_path<TAB>size<TAB>sha256`.

## Release layout and access boundary

Each released scene has a public side:

```text
scenes/<scene_id>/story.md
scenes/<scene_id>/variants/<variant>/data.parquet
scenes/<scene_id>/variants/<variant>/schema.json
scenes/<scene_id>/variants/<variant>/tasks.json
```

and a grading side:

```text
scenes_private/<scene_id>/ground_truth.json
scenes_private/<scene_id>/test.parquet
scenes_private/<scene_id>/graph.png
```

The grading data are publicly released for reproducible scoring, but are private with respect to the experimental access policy. Only oracle loading, cohort eligibility, graph metrics, and post-inference scoring may use them.

## Inventory result

| Quantity | Count |
|---|---:|
| Main released scenes | 100 |
| Complete task catalogs | 100 |
| Complete-catalog tasks | 2,589 |
| Rung-2 tasks | 1,223 |
| Clean scenes | 48 |
| Clean scenes without latent nodes | 33 |
| Clean/no-latent scenes with all five frozen tasks | 27 |
| Clean/no-latent supplementary scenes | 6 |

Every graph-cohort scene contains 16,000 public observational rows. Graphs contain 3–7 nodes.

## Nested P0 cohorts

```text
Graph cohort: 33 scenes, provisional dev 8 / holdout 25
├─ Primary downstream: 27 scenes x 5 tasks, provisional dev 7 / holdout 20
└─ Supplementary: 6 scenes, provisional dev 1 / holdout 5
```

Primary and supplementary cohorts partition the graph cohort. Every scene must retain the same development/holdout role in all cohort views. T03 constructs the deterministic stratification; T04 freezes the exact IDs after all 33 scenes pass data integrity checks.

## Primary frozen task panel

Every one of the 27 primary downstream scenes contains:

1. `identification__one_valid_adjustment_set`;
2. `identification__all_minimal_adjustment_sets`;
3. `identification__minimal_adjustment_set_size`;
4. `identification__n_valid_adjustment_sets`;
5. `bias_diagnostic__forbidden_controls_list`.

The 27 primary IDs are stored in `data/manifests/causalds.json`. The six supplementary IDs are `scene_000338`, `scene_000402`, `scene_000521`, `scene_000628`, `scene_000699`, and `scene_000966`. They share four symbolic tasks (`causal_sketch__edges_only`, `causal_sketch__skeleton_edges`, `identification__identifiable_boolean`, and `identification__method_label`) and may contain additional scene-specific tasks. Their downstream results are exploratory only and are never pooled into primary accuracy.

## SCD and graph representation decision

P0 preserves a raw CPDAG as the primary SCD artifact. T05 froze `BOSS + BasisFunctionBicScore` (`penalty_discount=1.0`, `truncation_limit=3`, one deterministic data-order start). A deterministic Dor--Tarsi CPDAG-consistent DAG extension with lexicographic sink tie-breaking is sensitivity only.

P1 resolves this limitation by generating homogeneous linear non-Gaussian, causally sufficient SCMs and matching them to DirectLiNGAM.

T06 froze `fourgraph.graph.v1` as the common LLM/SCD/Hybrid/Oracle exchange artifact, with a separate `fourgraph.variable_map.v1`. Structure-only and full-audit hashes are distinct; exact DAG/CPDAG validation and projection/Hybrid parent checks are mandatory. Details are in `docs/graph_contract.md` and `reports/t06_graph_contract.md`.

T07 implemented the typed grading-only Oracle loader and validated canonical DAG creation on all eight frozen development scenes. It returns no raw grading record, stores no versioned edge list, removes grading access from runtime SCD, and defers holdout Oracle materialization to T14.

T08 implements the public-story/schema-only LLM graph path, strict all-pairs response/DAG validation, bounded retry without heuristic repair, canonical T06 output, and hash-verified replay. OpenAI snapshot `gpt-5.4-nano-2026-03-17` generated valid canonical DAGs for all eight development scenes in one attempt each. The raw log is ignored, its hash is versioned, and neither holdout nor forbidden evidence was accessed.

T09 reran the T05-frozen BOSS/BasisFunctionBicScore configuration from the public same-scene observational tables and schema types only. It produced 8/8 canonical raw CPDAGs and 8/8 deterministic parent-linked projected DAGs, exactly matching the selected T05 graphs and reproducing byte-for-byte on a full rerun. It accessed no story, LLM graph, task, grading, Oracle, or holdout scene.

T10 preserved those raw CPDAG skeletons and compelled directions while the exact T08-frozen OpenAI semantic configuration oriented only their 27 unresolved development edges. It produced 8/8 canonical parent-linked Hybrid DAGs in eight calls with zero validation retries. Every orientation records confidence and rationale; T06 validation confirms exact parent hashes and Markov-equivalence membership. Replay is byte-exact, and T10 accessed no table, T08 graph, projected DAG, task, grading/Oracle, or holdout scene.

T11 evaluated five graph views on each of the eight development scenes and emitted 40 byte-reproducible structural metric records. The evaluator used the T07 Oracle capability in memory, persisted no Oracle edge list, made no LLM calls, read no tasks, and did not tune T08–T10. Raw CPDAG and DAG metric families remain distinct; projected SCD is sensitivity-only. SID/AID are null/unavailable pending a pinned validated implementation.

## Reasoner and scorer boundary

The downstream reasoner must not receive the graph-faithful story or observational table. It receives graph, query, non-causal variable glossary, and output schema only.

For a CPDAG, the main reasoner uses conservative/invariance semantics: return the common answer when all compatible DAG extensions agree, otherwise return `undetermined`. P0 reports both oracle-answer accuracy and uncertainty-aware correctness. The projected-DAG sensitivity run uses official answer scoring.

## Definition of Done

- [x] Official GitHub, Hugging Face, and paper sources verified.
- [x] Immutable revisions and retrieval date recorded.
- [x] Code/data licenses and CauseNet attribution recorded.
- [x] Source archive and public/grading catalogs hashed.
- [x] Public/grading layout and access boundary documented.
- [x] All 100 task catalogs, schemas, and ground-truth records inspected.
- [x] Nested P0 cohorts verified: graph 33, primary 27 x 5, supplementary 6.
- [x] P0/P1 configs and graph/reasoner decisions synchronized.
- [x] Provisional nested 8/25, 7/20, and 1/5 stratification — T03.
- [x] Parquet-level integrity/missingness audit and exact nested IDs/task manifests frozen — T04.
- [x] Exact P0 SCD method and sensitivity projection selected — T05.

- [x] Canonical cross-builder graph contract, hashes, validators, and isolated consumer views frozen — T06.
- [x] Grading-only Oracle loader and non-oracle leakage boundary validated — T07.
- [x] Public-only LLM builder implementation and eight-scene input boundary validated — T08 implementation gate.
- [x] Exact live LLM backend frozen and 8/8 development `G_LLM` DAGs captured/replayed — T08 experiment gate.
- [x] Frozen SCD builder emitted 8/8 raw CPDAGs and 8/8 deterministic projected-DAG sensitivity artifacts — T09.
- [x] Hybrid H1 emitted 8/8 parent-linked DAGs and audited 27/27 unresolved orientations without changing skeleton/compelled directions — T10.
- [x] Type-aware development graph metrics emitted 40/40 records with Hybrid attribution and no builder tuning — T11.
- [x] T12 v3 sealed synthetic conformance suite independently verified 150/150 expected targets without CausalDS story/answers/holdout.
- [x] Frozen T12 v3 GPT-5.4 Mini candidate passed all prospective conformance gates at 146/150 and is eligible for Oracle-development.
- [x] Separately registered T12 v3 `G_ORACLE` development gate passed at 34/35 with every task at least 6/7 and no holdout access.
- [x] Separately registered T12 v3 full development matrix passed all integrity gates; reasoner frozen and T13 eligible.

T02–T11 and the T12 reasoner/scorer infrastructure are implemented. T12 v1 produced 175 replay-verified development records, but Gemma reached only 19/35 on the Oracle-graph sanity condition and remains a holdout-ineligible diagnostic baseline. The separately versioned T12 v3 GPT-5.4 Mini candidate passed sealed synthetic conformance at 146/150, passed its separately registered 35-task `G_ORACLE` development gate at 34/35, and completed the five-condition 175-record development matrix. All integrity gates passed and the reasoner is now frozen/holdout-ready. T13 is eligible but remains unstarted; T14/holdout has not been opened and no holdout evidence has been accessed.
