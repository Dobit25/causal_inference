# CausalDS Data Protocol

## Pinned official release

- GitHub commit: `c74671d0a0924efc5bb021fc8966f856d5b80a4f`.
- Hugging Face revision: `2880dfa710d08e076055cb0248ef0c534a93b0fa`.
- Paper: arXiv `2607.08093v1`.
- Code license: Apache-2.0.
- Data license: CC0-1.0; CauseNet-derived verbalization seeds require attribution under CC BY 4.0.

Detailed provenance and hashes are stored in `data/manifests/causalds.json`. The audit report is `reports/causalds_release_audit.md`.

## Data unit

The causal scene/SCM is the independent unit. Task rows are repeated measurements nested within a scene.

Valid:

```text
SCM_s -> observational row 1 ... row N -> one SCD run
      -> task 1 ... task 5
```

Invalid:

```text
task/scene 1 -> one row
task/scene 2 -> one row
              -> pooled SCD table
```

## Released P0 nested cohorts

Apply these deterministic graph-cohort eligibility rules:

1. Main released scene bank at the pinned revision.
2. `observation_variant == clean`.
3. No latent nodes in grading-only metadata.
4. DAG oracle is available.
5. Public schema and observations map consistently to observed conceptual variables.

The release audit verifies a 33-scene graph cohort. The nested primary downstream cohort contains the 27 scenes that additionally provide all five frozen tasks; the remaining 6 scenes form a supplementary exploratory cohort. T03 constructed the deterministic graph 8/25, primary 7/20, and supplementary 1/5 allocation. T04 verified all 33 scenes and froze those IDs unchanged. A scene keeps the same development/holdout role across every cohort to which it belongs.

## Frozen P0 task priority

1. `identification__one_valid_adjustment_set`
2. `identification__all_minimal_adjustment_sets`
3. `identification__minimal_adjustment_set_size`
4. `identification__n_valid_adjustment_sets`
5. `bias_diagnostic__forbidden_controls_list`

The general contract permits 2–5 tasks per scene. All 27 primary scenes contain the same five tasks. The 6 supplementary scenes do not enter the primary task-accuracy panel; report their available tasks separately and never synthesize tasks to fill a quota.

## Public/grading boundary

| Data | Graph builders | Reasoner | Scoring/audit |
|---|---:|---:|---:|
| Public story | LLM and hybrid only | No | Audit only |
| Public observational table | SCD builder only; Hybrid receives only the resulting raw CPDAG | No | Integrity checks |
| Non-causal glossary/query | No | Yes | Yes |
| Ground-truth graph | Oracle only | Only as explicit oracle payload | Metrics |
| Gold answer | No | No | After inference only |
| Holdout outputs | No tuning | No tuning | Final analysis |

Use explicit allowlisted views and separate loader paths. Do not pass a complete scene object to a restricted component and rely on prompting to ignore forbidden fields.

T07 enforces grading access with typed purposes and an artifact matrix. Oracle access may resolve only `ground_truth.json`; its loader returns `VariableMap` plus canonical `GraphArtifact`, never the raw grading object. Runtime SCD has no grading resolver dependency. Integrity auditing and post-inference scoring remain distinct purposes.

T08 gives the LLM builder a distinct `PublicLLMGraphInput`: public story text, the public schema-derived variable map, and their hashes only. It contains no path or field for observations, tasks, answers, SCD state, or grading data. Raw prompts and responses remain outside Git; versioned manifests retain hashes and call metadata.

T09 gives the SCD builder only each clean public `data.parquet` plus schema information required for column order and variable type. It immediately replaces public column names with `X000...`, never pools scenes, and emits a primary CPDAG plus a sensitivity-only deterministic projection. The SCD code has no story, task, LLM, grading, or Oracle dependency; machine-specific runtime logs remain outside Git.

T10 loads the raw T09 CPDAG plus public story/schema only. It forbids direct observational-table access, the T08 LLM graph, the T09 projected DAG, tasks, grading/Oracle, and holdout. Raw prompts/responses are ignored under `results/raw/t10_hybrid/`; versioned artifacts contain canonical graphs, hashes, request metadata, and edge-level semantic audits.

## Canonical variable and graph artifacts

For each scene, derive one `fourgraph.variable_map.v1` artifact in public schema order. Canonical IDs are contiguous `X000...`; the public name/type mapping is hashed separately from graphs. SCD receives canonical IDs/types without semantic labels, semantic builders receive the public mapping, and the reasoner receives only a non-causal glossary.

Every graph builder must emit `fourgraph.graph.v1` through the T06 adapters. Persist `mapping_sha256`, structure-only `graph_sha256`, and full `artifact_sha256`. Never use builder-local column order or labels as the comparison node universe. The schemas and semantic rules are documented in `docs/graph_contract.md`.

## Fresh homogeneous P1

Generate 100 scenes with:

- 20 development and 80 holdout scenes;
- stratified 5–7 node connected DAGs;
- no latent confounders;
- linear non-Gaussian SCMs with independent exogenous errors;
- primary `N=2000` observations per SCM;
- `N=500` and `N=10000` sensitivity on 20 scenes;
- the same 2–5 adjustment/control task contract.

Persist generator commit, resolved config, seeds, generated SCMs, story-generation model/version, hashes, and the generated-scene manifest. Do not merge fresh and released results silently.

## Raw-data policy

- `data/raw/` and `data/generated/` are immutable/derived caches and stay outside Git.
- Version manifests, cohort/task IDs, configs, aggregate results, and audit reports.
- Preserve the NoisyCausal negative audit as historical provenance rather than overwriting it.
