# Coding Agent Plan

## Rules

- Work task-by-task and meet each Definition of Done before advancing.
- Update `codinglog.md` after every completed task.
- Keep all package code under `src/fourgraph/`.
- Never pool observations across scenes.
- Enforce public/grading access with code-level allowlists and tests.
- Use explicit seeds and versioned configs.
- Preserve raw inputs/outputs outside Git and version their manifests/hashes.
- Never tune on holdout results.

## Completed history

### T00 — Bootstrap

Complete: package skeleton, CLI, YAML loader, deterministic seed utility, tests.

### T01 — NoisyCausal artifact audit

Complete with `scd_ready: false`. Retained as a historical negative audit that motivated the CausalDS substrate decision.

### T02 — CausalDS design freeze and release audit

Complete: pinned provenance/hashes, synchronized documents/configs, public/grading boundary, and nested 33/27/6 P0 cohort verification.

### T03 — Scene inventory and provisional nested split

Complete: inventoried all 100 scenes and generated the deterministic provisional graph 8/25, primary 7/20, and supplementary 1/5 allocation with one role per scene.

### T04 — Data integrity and final cohort freeze

Complete: all 33 graph scenes passed parquet, schema, mapping, graph, task, and grading-isolation gates; exact nested IDs and separate primary/supplementary task manifests are frozen.

### T05 — P0 SCD and projection decision

Complete: preregistered 18 mixed-data configurations, selected `BOSS + BasisFunctionBicScore` (`penalty_discount=1.0`, `truncation_limit=3`) using only eight graph-development scenes, froze raw CPDAG as primary, and implemented/tested deterministic consistent extension for sensitivity.

## Current sequence

### T06 — Canonical graph contract

Complete: froze `fourgraph.graph.v1` plus the separate variable map, canonical serialization and structure/artifact hashes, exact DAG/CPDAG validators, evidence allowlists, projection/Hybrid parent checks, provenance-blind reasoner view, metrics view, adapters, schemas, reproducible fixtures, and byte-check manifest without accessing holdout data or rewriting T05 artifacts.

### T07 — Oracle loader

Complete: implemented the typed grading-only CausalDS Oracle loader, canonical public-schema mapping, DAG validation, edge-free deterministic development audit, SCD grading-dependency removal, and negative architecture/leakage tests on eight frozen development scenes without holdout access.

### T08 — LLM graph builder

Complete: the public-story/schema-only loader, all-pairs prompt/response schema, strict DAG parser, no-repair retry policy, T06 adapter, OpenAI Responses live adapter, raw-call contract, and deterministic replay are frozen. Snapshot `gpt-5.4-nano-2026-03-17` produced 8/8 valid development DAGs in one attempt each; holdout was not accessed. T10 reused this exact semantic configuration without consuming the T08 graph artifacts.

### T09 — SCD graph builder

Complete: reran the T05-frozen BOSS/BasisFunctionBicScore configuration from anonymized same-scene observations only; emitted 8/8 canonical raw CPDAGs and 8/8 parent-linked projected-DAG sensitivity artifacts; exact full rerun and T05 graph regression pass without holdout, semantic, task, LLM, or Oracle access.

### T10 — Hybrid H1

Complete: preserved every raw T09 CPDAG skeleton and compelled direction, used only the T08-frozen semantic model/configuration to orient the 27 unresolved development edges, and emitted 8/8 parent-linked canonical Hybrid DAGs. Every orientation has confidence and rationale; T06 validation proves exact parent hashes and equivalence-class membership. All calls passed without validation retry, replay is byte-exact, and no holdout, table, T08 graph, projected DAG, task, or Oracle input was accessed. Next is T11 graph metrics.

### T11 — Graph metrics

Complete: froze skeleton, CPDAG, DAG, SHD, normalization, zero-denominator, applicability, and scene-macro conventions; evaluated 5 graph views on each of 8 development scenes; emitted 40 byte-reproducible records plus Hybrid error attribution. Oracle edges remained in memory, holdout/tasks/builders were untouched, and no LLM calls occurred. SID/AID are explicitly unavailable rather than zero because no implementation is pinned and validated. Next is T12.

### T12 — Fixed reasoner and scorers

Complete at the implementation/development-evaluation level: froze the graph+query+ID/type-only glossary view, implemented exact compatible-DAG enumeration and conservative CPDAG `undetermined` semantics, added isolated official-target loading and both scorers, and produced 175 replay-verifiable development records with no holdout access. The Gemma `G_ORACLE` sanity result is only 19/35, so the contract is ready but this model is explicitly not holdout-ready; T12 must be refined/versioned before T13/T14.

T12 v2 model-independent amendment complete: preserves v1 as a diagnostic baseline, adds 150 answer-free synthetic conformance cases, five task-specific response schemas, canonical identical-input caching, and a Pearl back-door construct-validity sensitivity. The first separately frozen GPT-5.4 Mini candidate failed its engineering smoke because three attempts exhausted the 4096-token reasoning budget before visible JSON. It was stopped before the 150-case and Oracle-development gates; no holdout call occurred. A new candidate must be pre-registered before continuing.

Mini-B was then pre-registered with the sole runtime change `max_output_tokens: 8192`. It passed the 10-case technical smoke with 10/10 first-attempt parses and zero retries; diagnostic strict accuracy was 9/10. The run intentionally stopped before the 150-case prospective accuracy gate for budget review. No development or holdout evidence was accessed.

Mini-C increased only the ceiling to 10240 and added a pre-live <=0.80 utilization gate. One attempt consumed the full 10240 reasoning tokens without visible output, then the retry completed with 3324; therefore the headroom gate failed despite 10/10 eventual parses. The 150-case run remains blocked. Further work should test medium effort or a separately versioned prompt rather than repeatedly lifting the ceiling.

Mini-D performed that controlled effort test: it kept the 10240 ceiling and prompt v2 unchanged and changed only `reasoning_effort: high -> medium`. It passed the engineering smoke, then completed the approved 150-case conformance run with 150/150 first-attempt parses, zero retries and maximum utilization 0.5047. Scientific accuracy was 105/150 = 0.700: only CPDAG-answered accuracy passed, while overall, DAG, CPDAG-undetermined and per-task gates failed; forbidden-controls reached only 7/30. Mini-D is therefore not eligible for Oracle-development, full matrix, or holdout. A separately versioned candidate is required before T13/T14.

T12 v3 prompt contract is implemented as a separately versioned candidate design. It preserves Mini-D's model/runtime and canonical graph encoding while replacing the generic prompt with a shared base plus one routed task module. The base operationalizes compatible-DAG enumeration, CausalDS edge removal, subset enumeration, d-separation and sentinel precedence; internal `no_valid_adjustment_set` is serialized only as official `no_backdoor`. The opened v2 suite remains diagnostic-only.

The sealed v3 suite was subsequently generated with seed 1203 and frozen before live inference: 150 five-node cases, 30 per task, with 90 answered DAG, 30 invariant CPDAG and 30 undetermined CPDAG cases. It contains no CausalDS story, answer or holdout evidence, has zero exact v2 case overlap, and its production/independent solvers agree 150/150. The frozen 10-case smoke passed every engineering gate.

The authorized full conformance run reused the ten smoke responses, added 140 new case calls and five registered retries, and reached 146/150 = 0.9733 strict accuracy. DAG was 87/90, invariant CPDAG 29/30, undetermined CPDAG 30/30, and all five task accuracies were at least 28/30. Every prospective scientific gate passed. Five incomplete attempts reached the 10240-token ceiling before successful retries; retain this failed headroom diagnostic in the audit.

The separately registered `G_ORACLE` development gate then ran exactly 35 tasks over the seven frozen primary development scenes. It reached 34/35 = 0.9714, with 35/35 first-attempt schema compliance, no retries, every task at least 6/7, and all 12 required empty-sentinel records correct.

The separately registered full development matrix is complete: 7 scenes × 5 tasks × 5 graph conditions = 175 records, but only 105 unique canonical inputs. It inherited 35 Oracle identities, made 70 new calls, and reused one response for every identical canonical input. All 175 records passed schema on the first attempt with zero retry/incomplete calls. Oracle-answer results were Oracle 34/35, LLM 33/35, Hybrid 31/35, projected SCD 6/35, and raw SCD 4/35; uncertainty-aware results were 34/35, 34/35, 32/35, 33/35, and 35/35. These are descriptive development results and were not used to retune T08–T10 or the reasoner. All integrity gates passed; `reasoner_frozen_for_holdout: true`, `holdout_reasoner_ready: true`, and `t13_eligible: true`. T13 and holdout remain unstarted.

### T13 — Frozen task manifest

Confirm the T04-frozen primary and supplementary task manifests against implemented loaders/scorers before holdout; any change requires a new experiment version.

### T14 — Released P0

Run development, freeze all settings, then run the graph-cohort 25-scene holdout once. Primary downstream results use its nested 20-scene panel; the nested 5-scene supplement remains exploratory and separate.

### T15 — Clustered analysis

Compute scene-macro summaries, paired scene-clustered bootstrap, BH correction, projection sensitivity, and applicable A–D outcomes.

### T16 — P0 findings

Publish `reports/p0_findings.md` with GO/REFINE/STOP based on feasibility and research quality.

### T17 — Fresh P1 generation

Generate and audit 100 homogeneous linear non-Gaussian scenes at the frozen commit/config.

### T18+ — P1, robustness, and replication

Run the primary P1 study, then optional nonlinear SCM, SID/AID, perturbation, observation robustness, and CLadder replication phases.

## Research integrity checklist

- [x] reasoner never sees causal story or observational table
- [ ] no oracle leakage
- [ ] raw CPDAG distinguished from projected DAG
- [x] hybrid cannot change skeleton in H1
- [x] same reasoner across graph conditions
- [ ] scene-level inference without pseudo-replication
- [ ] holdout configuration frozen
- [ ] all co-equal outcomes reported, including null/adverse results
