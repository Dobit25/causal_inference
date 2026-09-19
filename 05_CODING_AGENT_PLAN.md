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

Complete: froze the exact 25-scene graph holdout (20 primary + 5 supplementary), the common five-task primary panel, all five graph conditions, model snapshots/API parameters, prompts/schemas/parser/scorers, SCD/Hybrid/graph contract, retry/cache/resume/failure rules, T14 order/paths/counts, metrics and paired scene-clustered/BH analysis. The 77 supplementary rows remain exploratory inventory with zero fixed-reasoner records. Four T13 artifacts replay byte-for-byte; zero API call or holdout/gold/Oracle-edge access occurred. T14 is authorized but not started; any change requires a new experiment version.

### T14 — Released P0

Complete: opened the graph-cohort 25-scene holdout as one logical resumable run after the T13 seal. Built 25 LLM, 25 raw SCD, 25 projected SCD and 23 Hybrid graphs; two Hybrid conditions terminated without fallback. Loaded 25 Oracle DAGs grading-only in memory and emitted 125 graph schedule rows without persisting Oracle edges. Completed all 500 primary downstream rows from 245 canonical identities; supplementary reasoner rows remained zero. Offline graph/reasoner/audit replay passes. T15 statistics have not started.

### T15 — Clustered analysis

Complete: computed scene-macro summaries, 5,000 paired scene-clustered bootstrap replicates, all compatible pairwise contrasts, BH correction, exact McNemar sensitivity, projection sensitivity and applicable A–D outcomes. The analysis replays byte-for-byte with zero API calls and leaves T14 unchanged.

### T16 — P0 findings

Complete: published `reports/p0_findings.md`, froze supported/unsupported claims, retained null/adverse findings and selected `REFINE`. This authorized T17 design only; T17 has since frozen that protocol without starting P1 execution.

### T17 — Freeze P1 Hybrid protocol

Complete: froze the fresh-SCM generator contract, exact task/query balance, three semantic-evidence doses, BOSS CPDAG primary substrate, DirectLiNGAM sensitivity role, global H2 forced/selective rules, abstention selection, evaluation schedule, statistics, evidence boundaries, and stage gates. No scene was generated and no model/H2/holdout execution occurred.

### T18 — Fresh SCM generator and inventory

Complete: implemented and audited the deterministic 100-scene generator, five tasks per scene, exact 20/80 split, primary `N=2000` samples, nested raw `N=500/10000` prefixes on 20 scenes, and Oracle-CPDAG eligibility. Production and independent solvers agreed 500/500; byte replay covers all 480 ignored raw artifacts and versioned manifests. No semantic model, SCD, Hybrid, H2, or holdout scoring ran.

### T19 — Controlled semantic-story variants

Complete: generated 300 deterministic stories for 100 scenes with exact full/partial/ambiguous evidence rules, 100 neutral alias maps assigned independently of graph position, a story-only model allowlist, public-text truth parsing, and a 20-development-scene blinded internal QA panel. QA passed 20/20 scenes and 60/60 evidence classifications, but is explicitly internal rather than independent external human validation. No API, SCD, LLM, reasoner, H1/H2 or holdout evaluation ran.

### T20 — H2 offline implementation and conformance

Complete: implemented strict semantic-preference input validation, global H2-Forced optimization over consistent CPDAG extensions, and H2-Selective exact-parent abstention. Production and independent solvers agreed on 150/150 forced and 3,000/3,000 selective decisions; 30/30 invalid inputs were rejected. No API or P1 scene was accessed.

### T21 — Development graph construction and threshold gate

Execution complete, gate not passed: 80 captured API attempts yielded 60 shared preference artifacts across 20 development scenes. H2-Forced remained valid on all scenes/variants, whereas H1 was valid on 8/20 full-story scenes. No selective candidate reached the frozen 0.95 orientation-precision minimum, so no threshold exists for P1 v1 and holdout remains sealed.

### T21 amendment, then T22–T24

T21 Amendment v2 complete, gate not passed. Prompt v2 passed a sealed 120-case semantic-preference suite at 100% for forward, reverse and ambiguous classes. The development rerun preserved the model, BOSS substrate, H1/H2 implementation and threshold grid, but no candidate met 0.95 orientation precision. The additional standalone partial/ambiguous graphs and Oracle-skeleton diagnostic were not used to select a threshold. Further prompt tuning and T22 are not authorized; the next scientific action is to revise the P1 claim/design as a new protocol version or close P1 with the negative development finding.

T21 Amendment v3-A complete: froze the P1-v2 Edge-Selective successor without implementation or execution. Only BOSS-undirected edges are mutable; exact credible-extension consensus and Meek closure must produce a provenance-labeled partial graph. The 20 existing development scenes are engineering-only, a new 20-scene validation cohort will select among 20 frozen threshold candidates, and the existing 80 holdout scenes remain sealed. Only T21 v3-B offline implementation and synthetic conformance are authorized next.

T21 Amendment v3-B complete: implemented the versioned partial-graph/decision contracts, exact credible-extension Edge-Selective production solver, independent topological-order/brute-subset reference, deterministic Meek R1–R4 closure and a 180-case synthetic suite. All 3,600 threshold decisions agreed and all 40 invalid fixtures failed closed. No P1 scene or API was accessed. T21 v3-C may now generate and freeze exactly 20 new validation SCMs offline; semantic calls and holdout access remain unauthorized.

T21 Amendment v3-C complete: generated and froze the prospective threshold-validation cohort with exact IDs `P1V000–P1V019`, seed 21301, N=2000 observations, 5 tasks/scene and 3 deterministic story variants/scene. All registered allocations and 100/100 independent target agreements passed; raw and versioned artifacts replay byte-for-byte. No model or causal method ran and existing development/holdout artifacts remained untouched. T21 v3-D may run the frozen semantic model on this cohort and evaluate exactly 20 threshold candidates; final holdout access remains unauthorized.

T21 Amendment v3-D complete, gate failed: 20 BOSS validation graphs and 60 frozen GPT-5.4 Nano preference artifacts were produced with no retry. Exactly 20 preregistered Edge-Selective candidates were evaluated. Graph validity was 100%, but the maximum observed precision was 0.8557 at 97 answered edges and 0.4554 coverage; therefore no candidate met the 0.95 safety gate and no threshold was selected. T21 v3-E must record the fail-closed terminal decision; T22/final holdout execution is not authorized.

T21 Amendment v3-E complete: closed P1-v2 as a retained negative result, froze 70 versioned v2/v3 artifacts by hash, prohibited post-validation gate changes and confirmed the final holdout remains sealed. T22 is not authorized. Only design of a separately frozen P1-v3 Evidence-Selective Hybrid is allowed; Bootstrap-BOSS execution, semantic API calls and new cohort generation remain blocked until that protocol exists.

P1-v3 Evidence-Selective protocol freeze complete: registered Bootstrap-BOSS as the sole primary statistical method with 200 size-N resamples, deferred the SCD ensemble, froze the five adjacency and three direction thresholds, six balanced whole-graph GPT-5.4 Nano prompts, deterministic evidence validation, empirical-reliability classes, statistical veto, partial-graph/ledger contracts and Learn-then-Test risk control. The next action is implementation and synthetic conformance only; study-scene Bootstrap execution, cohort generation, API calls and final holdout remain forbidden.

P1-v3 Bootstrap-BOSS offline conformance complete: the production aggregator and an independent reference counted four edge states identically on 60/60 synthetic cases and created identical valid parents on 900/900 registered threshold decisions. Deterministic bootstrap indices, independent standardization, completed-PDAG inputs, run/node ordering, immutability and 30 fail-closed fixtures are covered. No study method execution occurred. Next is offline semantic vote/reliability and statistical-veto conformance; power analysis, cohorts and API remain blocked.

The next action is to implement the six-vote semantic agreement classifier, evidence-quote validator, empirical-reliability records and statistical-veto decision table completely offline. The existing P1-v2 development/validation cohorts may not be reused for tuning, and the 80-scene final holdout remains sealed. T22/T23 remain unauthorized.

The offline semantic-reliability/statistical-veto implementation is complete. Before any study execution, the next authorized task is prospective power analysis and disjoint successor-cohort design. It must determine calibration/validation sample sizes and freeze split rules; it does not authorize 200-run Bootstrap-BOSS, scene generation, semantic API calls or final-holdout access.

Prospective power/cohort design is complete: 40 method-development, 400 semantic-calibration and 400 threshold-validation scenes are planned as disjoint roles. The next authorized task is offline implementation and synthetic conformance of the successor generator/split allocator only. It must not materialize the 840 study scenes, run Bootstrap-BOSS, call the semantic model or access the final holdout.

Successor generator/split conformance is complete using synthetic namespaces only. The next authorized task is to design and freeze a runtime/cost pilot offline. The pilot itself, real cohort generation, Bootstrap-BOSS execution, semantic API calls and final-holdout access remain unauthorized.

Runtime/cost-pilot design is complete and frozen offline. It preregisters a 9-scene synthetic panel, 270 measured Bootstrap-BOSS fits, 108 semantic calls, resource projections, feasibility gates and strict scientific-use boundaries. No pilot artifact was materialized and no execution occurred. The next authorized action is only an offline preflight freeze that must pin exact synthetic IDs, runners, environment, official rate card, approved budget and disk capacity; pilot execution still requires explicit user authorization.

Runtime/cost-pilot preflight is complete and frozen offline. Exact synthetic identities/blueprints, runner dependencies, environment, machine capacity, conservative cost ceiling and USD 1.50 pilot budget are pinned. Official current Nano pricing and remaining platform balance remain unverified offline, so `execution_ready` is false. Only a separate execution-authorization checkpoint may resolve those blockers; no pilot workload is currently authorized.

Execution-authorization checkpoint complete with `DENY_PENDING_BALANCE_VERIFICATION`. Official GPT-5.4 Nano Standard pricing and the budget-guarded semantic adapter are pinned. The project key cannot read the Admin-only organization-cost endpoint, so balance remains unknown and no pilot execution is authorized. Only a balance-attestation amendment is allowed next.

Balance-attestation amendment complete: USD 5.52 spend / USD 15.00 limit leaves USD 9.48 headroom, passing the technical budget gate against the USD 1.50 pilot cap. Because the platform hard limit is off, the internal controller and freshness recheck are mandatory. Execution remains unauthorized until a separate final GO/NO-GO instruction.

Final pilot GO/NO-GO complete with `GO_READY`. All blocking gates passed and the exact synthetic pilot is execution-eligible, but this checkpoint neither authorizes nor starts the workload. A separate explicit run order is required; attested spend must still be fresh at runtime and the 840-scene study remains forbidden.

## Research integrity checklist

- [x] reasoner never sees causal story or observational table
- [ ] no oracle leakage
- [ ] raw CPDAG distinguished from projected DAG
- [x] hybrid cannot change skeleton in H1
- [x] same reasoner across graph conditions
- [ ] scene-level inference without pseudo-replication
- [ ] holdout configuration frozen
- [ ] all co-equal outcomes reported, including null/adverse results
