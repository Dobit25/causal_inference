# Four-Graph Causal Reasoning

This repository studies how causal-graph provenance and uncertainty affect downstream LLM causal adjustment/control reasoning.

For each causal scene it compares:

- `G_LLM`: story semantics only;
- `G_SCD`: observational data only;
- `G_HYBRID`: SCD skeleton plus semantic orientation;
- `G_ORACLE`: grading-only ground truth.

## Frozen direction

1. Released CausalDS P0: exploratory nested cohorts with 33 clean, causally sufficient graph scenes, a primary `27 x 5` downstream panel, and 6 separately reported supplementary scenes.
2. Fresh homogeneous CausalDS P1: primary study on 100 linear non-Gaussian SCMs.
3. Optional nonlinear robustness and CLadder external replication.

The detailed source of truth is [CausalDS.md](CausalDS.md). Compact protocols are [00_CONTEXT.md](00_CONTEXT.md) through [06_PILOT_CONFIG_SPEC.md](06_PILOT_CONFIG_SPEC.md).

## Environment

The project uses the existing conda environment `cau` with Python 3.10. T05 additionally pins OpenJDK 21 for the direct JPype/Tetrad adapter; `environment.yml` records the complete environment contract.

```powershell
conda run -n cau python -m pytest
conda run -n cau python -m fourgraph --help
conda run -n cau python -m fourgraph validate-config configs/p0_released.yaml
conda run -n cau python -m fourgraph validate-config configs/p1_fresh.yaml
```

Reproduce the T02 release/cohort audit against the extracted pinned source archive:

```powershell
conda run -n cau python scripts/audit_causalds_release.py <extracted-causalds-source-root>
```

Reproduce and byte-check the T03 scene inventory and provisional nested split:

```powershell
conda run -n cau python scripts/build_causalds_t03.py <extracted-causalds-source-root> --check
```

Reproduce and byte-check the T04 integrity audit and frozen manifests:

```powershell
conda run -n cau python scripts/audit_causalds_t04.py <extracted-causalds-source-root> --check
```

Verify the frozen T05 method, jar/config hashes, and exact selected graphs on all eight development scenes:

```powershell
conda run -n cau python scripts/fetch_tetrad_t05.py
conda run -n cau python scripts/evaluate_causalds_t05.py <extracted-causalds-source-root> --jar data/raw/t05/py-tetrad/pytetrad/resources/tetrad-current.jar --check
```

Regenerate or byte-check the T06 canonical graph-contract fixtures and manifest:

```powershell
conda run -n cau python scripts/build_graph_contract_t06.py
conda run -n cau python scripts/build_graph_contract_t06.py --check
conda run -n cau python -m fourgraph validate-variable-map data/manifests/t06_variable_map_example.json
```

All future LLM, SCD, Hybrid, and Oracle builders emit `fourgraph.graph.v1`. Its full specification is [docs/graph_contract.md](docs/graph_contract.md).

Generate or byte-check the T07 development-only Oracle loader audit:

```powershell
conda run -n cau python scripts/audit_causalds_t07.py <extracted-causalds-source-root>
conda run -n cau python scripts/audit_causalds_t07.py <extracted-causalds-source-root> --check
```

Replay or byte-check the completed T08 development graph set (this does not make another model call):

```powershell
conda run -n cau python scripts/audit_causalds_t08.py <extracted-causalds-source-root> --replay-log results/raw/t08_llm_graph/gpt-5.4-nano-2026-03-17_dev.jsonl
conda run -n cau python scripts/audit_causalds_t08.py <extracted-causalds-source-root> --replay-log results/raw/t08_llm_graph/gpt-5.4-nano-2026-03-17_dev.jsonl --check
```

T08 is complete on the frozen development split: OpenAI snapshot `gpt-5.4-nano-2026-03-17` generated 8/8 valid canonical `G_LLM` DAGs in one attempt each. Raw calls remain ignored under `results/raw/`; the versioned audit and graph manifest reproduce byte-for-byte from that log. Holdout remains unopened.

Generate or byte-check the completed T09 development SCD graph set:

```powershell
conda run -n cau python scripts/build_causalds_t09.py <extracted-causalds-source-root>
conda run -n cau python scripts/build_causalds_t09.py <extracted-causalds-source-root> --check
```

T09 emits eight primary raw CPDAGs and eight deterministic projected-DAG sensitivity artifacts from anonymized same-scene observational data only. It does not call an LLM or access story, Oracle, tasks, or holdout.

Replay or byte-check the completed T10 development Hybrid H1 graph set (this does not make another model call):

```powershell
conda run -n cau python scripts/audit_causalds_t10.py <extracted-causalds-source-root> --replay-log results/raw/t10_hybrid/gpt-5.4-nano-2026-03-17_dev.jsonl
conda run -n cau python scripts/audit_causalds_t10.py <extracted-causalds-source-root> --replay-log results/raw/t10_hybrid/gpt-5.4-nano-2026-03-17_dev.jsonl --check
```

T10 reuses the frozen T08 semantic model/configuration to orient only the unresolved edges of each raw T09 CPDAG. It generated 8/8 parent-linked Hybrid DAGs and audited 27/27 orientations without changing skeletons, compelled directions, or equivalence classes. It does not read the T08 graph artifacts, projected DAGs, tasks, Oracle, or holdout.

Generate or byte-check the completed T11 development graph metrics:

```powershell
conda run -n cau python scripts/evaluate_causalds_t11.py <extracted-causalds-source-root>
conda run -n cau python scripts/evaluate_causalds_t11.py <extracted-causalds-source-root> --check
```

T11 emits 40 type-aware per-scene records for five graph views. Oracle DAGs are grading-only and remain in memory; raw CPDAGs are never silently projected. No LLM calls, task access, builder tuning, or holdout access occurs.

Run, resume, or byte-check the T12 fixed development reasoner:

```powershell
conda run -n cau python scripts/run_causalds_t12_live.py <extracted-causalds-source-root> --resume
conda run -n cau python scripts/run_causalds_t12_live.py <extracted-causalds-source-root> --check
```

T12 produced 175/175 development records from one provenance-blind Gemma reasoner and two independent scorers. Its contract/replay gate passes, but the Oracle-graph sanity accuracy is 19/35, so the current reasoner is not approved for holdout.

Build or byte-check the T12 v2 model-independent conformance and construct-validity artifacts:

```powershell
conda run -n cau python scripts/build_t12_v2_conformance.py
conda run -n cau python scripts/build_t12_v2_conformance.py --check
conda run -n cau python scripts/audit_t12_construct_validity.py <extracted-causalds-source-root>
conda run -n cau python scripts/audit_t12_construct_validity.py <extracted-causalds-source-root> --check
```

This amendment does not replace T12 v1 or select a new model. It adds 150 synthetic conformance cases, task-specific schemas, canonical response caching, and an official-versus-Pearl scoring sensitivity before prospective model gating.

Run or replay the prospectively gated Gemma conformance retest (raw calls/cache remain ignored):

```powershell
conda run -n cau python scripts/run_t12_v2_gemma_conformance.py --resume
conda run -n cau python scripts/run_t12_v2_gemma_conformance.py --check
```

Gemma completed 150/150 cases but scored 0.133 overall and failed six of seven prospective gates, so it was not advanced to the Oracle-development or holdout stages.

Audit or replay the separately frozen GPT-5.4 Mini candidate smoke (live raw calls/cache remain ignored):

```powershell
conda run -n cau python scripts/audit_t12_v2_measurement.py --check
conda run -n cau python scripts/run_t12_v2_openai_mini.py --smoke --resume
conda run -n cau python scripts/run_t12_v2_openai_mini.py --smoke --check
```

The `high`/4096-token Mini candidate stopped at the engineering gate: one case completed correctly, while another exhausted all 4096 reasoning tokens on three attempts without visible JSON. Therefore the 150-case conformance, Oracle-development, full development matrix, and holdout stages were not run. Changing effort or token budget requires a new candidate config.

Run or replay the separately frozen 8192-token Mini-B diagnostic smoke:

```powershell
conda run -n cau python scripts/run_t12_v2_openai_mini.py --config configs/t12_v2_openai_mini_b.yaml --smoke --resume
conda run -n cau python scripts/run_t12_v2_openai_mini.py --config configs/t12_v2_openai_mini_b.yaml --smoke --check
```

Mini-B changed only `max_output_tokens` and passed 10/10 technical smoke cases without retries. Its 9/10 strict accuracy is diagnostic only; the 150-case prospective gate still requires a separate GO decision.

Run or byte-check the 10240-token Mini-C headroom diagnostic:

```powershell
conda run -n cau python scripts/run_t12_v2_openai_mini.py --config configs/t12_v2_openai_mini_c.yaml --smoke --resume
conda run -n cau python scripts/run_t12_v2_openai_mini.py --config configs/t12_v2_openai_mini_c.yaml --smoke --check
```

Mini-C eventually parsed 10/10 cases but failed its pre-registered headroom gate: one attempt exhausted all 10240 reasoning tokens and required retry. It was not advanced to the 150-case gate.

Run or byte-check the Mini-D controlled reasoning-effort diagnostic:

```powershell
conda run -n cau python scripts/run_t12_v2_openai_mini.py --config configs/t12_v2_openai_mini_d.yaml --smoke --resume
conda run -n cau python scripts/run_t12_v2_openai_mini.py --config configs/t12_v2_openai_mini_d.yaml --smoke --check
```

Mini-D kept prompt v2 and the 10240-token ceiling fixed and changed only `high` to `medium`. It passed the engineering smoke, then completed all 150 conformance cases on the first attempt with no retries and maximum utilization 0.5047. Strict accuracy was 105/150 = 0.700, so it failed the prospective scientific gates and was not advanced to Oracle-development or holdout.

Build or byte-check the T12 v3 task-specific prompt contract and sealed conformance suite:

```powershell
conda run -n cau python scripts/build_t12_v3_prompt.py
conda run -n cau python scripts/build_t12_v3_prompt.py --check
conda run -n cau python scripts/build_t12_v3_conformance.py
conda run -n cau python scripts/build_t12_v3_conformance.py --check
```

V3 keeps Mini-D and canonical JSON fixed, uses a shared base plus one task-specific module, and maps internal `no_valid_adjustment_set` to official `no_backdoor`. The seed-1203 suite contains 150 new cases, 30 per task, and two independent solvers agree on all 150 expected targets without using CausalDS story, answers, or holdout data.

Replay the completed T12 v3 smoke or full conformance run without making new API calls:

```powershell
conda run -n cau python scripts/run_t12_v3_openai_mini.py --config configs/t12_v3_openai_mini.yaml --smoke --check
conda run -n cau python scripts/run_t12_v3_openai_mini.py --config configs/t12_v3_openai_mini_full.yaml --check
```

The frozen GPT-5.4 Mini v3 candidate passed every prospective scientific conformance gate: 146/150 overall, 87/90 DAG, 29/30 invariant CPDAG, 30/30 undetermined CPDAG, and at least 28/30 for each task. Five attempts exhausted the 10240-token ceiling and succeeded on registered retry, so the headroom diagnostic remains failed.

Replay the completed 35-task `G_ORACLE` development gate without making API calls:

```powershell
conda run -n cau python scripts/run_t12_v3_oracle_development.py data/raw/causalds/source-c74671d0/causalds-c74671d0a0924efc5bb021fc8966f856d5b80a4f --check
```

The Oracle-development gate passed at 34/35 = 0.9714: 35/35 outputs were schema-valid on the first attempt, every task reached at least 6/7, and all 12 required empty-sentinel outputs were correct.

Replay the completed five-condition full development matrix without making API calls:

```powershell
conda run -n cau python scripts/run_t12_v3_full_development.py data/raw/causalds/source-c74671d0/causalds-c74671d0a0924efc5bb021fc8966f856d5b80a4f --check
```

The matrix produced 175 records from 105 unique canonical inputs, inheriting 35 calls and making 70 new calls. Oracle-answer accuracy was 34/35 Oracle, 33/35 LLM, 31/35 Hybrid, 6/35 projected SCD, and 4/35 raw SCD. Uncertainty-aware correctness was respectively 34/35, 34/35, 32/35, 33/35, and 35/35. All integrity gates passed; the reasoner is frozen and holdout-ready, while T13 and holdout remain unstarted.

## Provenance

- Active CausalDS audit: `reports/causalds_release_audit.md`.
- T03 inventory/split report: `reports/t03_scene_inventory_split.md`.
- T04 integrity/freeze report: `reports/t04_data_integrity.md`.
- T05 SCD/CPDAG selection report: `reports/t05_scd_method_selection.md`.
- T06 canonical graph-contract report: `reports/t06_graph_contract.md`.
- T07 grading-only Oracle loader report: `reports/t07_oracle_loader.md`.
- T08 public-story-only LLM builder report: `reports/t08_llm_graph_builder.md`.
- T09 development SCD graph-builder report: `reports/t09_scd_graph_builder.md`.
- T10 Hybrid H1 graph-builder report: `reports/t10_hybrid_graph_builder.md`.
- T11 development graph-metrics report: `reports/t11_graph_metrics.md`.
- T12 fixed-reasoner report: `reports/t12_fixed_reasoner.md`.
- T12 v3 Oracle-development report: `reports/t12_v3_oracle_development.md`.
- T12 v3 full-development report: `reports/t12_v3_full_development.md`.
- T12 v2 design-amendment report: `reports/t12_v2_design_amendment.md`.
- T12 v2 GPT-5.4 Mini candidate report: `reports/t12_v2_openai_mini.md`.
- T12 v2 GPT-5.4 Mini-B diagnostic report: `reports/t12_v2_openai_mini_b.md`.
- T12 v2 GPT-5.4 Mini-C headroom report: `reports/t12_v2_openai_mini_c.md`.
- T12 v2 GPT-5.4 Mini-D effort report: `reports/t12_v2_openai_mini_d.md`.
- T12 v3 task-specific prompt design: `reports/t12_v3_prompt_design.md`.
- Source manifest index: `data/MANIFEST.json`.
- Historical NoisyCausal negative audit: `docs/data_audit.md`.

Raw benchmark artifacts, generated scenes, and raw experiment outputs remain outside Git and are tracked through immutable manifests and hashes.
