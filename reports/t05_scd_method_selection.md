# T05 — P0 SCD/CPDAG Method Selection

## Verdict

```yaml
p0_scd_ready: true
selected_method: BOSS + BasisFunctionBicScore
selected_id: boss_basis_bic__p1__t3
penalty_discount: 1.0
truncation_limit: 3
primary_output: raw CPDAG
projected_DAG_role: sensitivity_only
holdout_accessed: false
downstream_reasoner_used_for_selection: false
```

The selected configuration passed all preregistered execution, graph-contract, deterministic-rerun, structural-quality, half-sample stability, and runtime gates on the eight frozen graph-development scenes. This is an operational readiness verdict for released P0, not a claim that one exact parametric SCM family generated every heterogeneous CausalDS scene.

## Frozen boundary

The shortlist, parameter grid, hard gates, metrics, and ranking rule were written to `configs/t05_scd_selection.yaml` before any T05 oracle scoring. Discovery received only each scene's public clean `data.parquet`, schema-derived conceptual types, and anonymous names `X000`, `X001`, etc. Scenes were never pooled.

The grading DAG was opened only after each discovery run, under the `scoring` access purpose, to calculate development structural metrics. The causal story, semantic variable names, tasks, gold answers, downstream reasoner, and all 25 graph-holdout scenes were excluded from method selection.

## Compatibility and assumption audit

Seven development scenes are mixed binary/continuous and one is continuous-only. Their verified mechanisms include logic gates, logistic-softsign, noisy-OR, handcrafted continuous functions, interactions, linear additive functions, and a neural black-box mechanism, with Gaussian, Laplace, Student-t, and mixed noise. A linear-Gaussian or homogeneous ANM claim therefore does not cover P0.

The [Tetrad tests/scores guide](https://tetrad-manual.readthedocs.io/en/latest/choosing-tests-and-scores.html) identifies basis-function tests/scores as the scalable option for mixed nonlinear data, while Conditional Gaussian and Degenerate Gaussian methods are mixed-data options with narrower model assumptions. The [Basis Function BIC documentation](https://tetrad-manual.readthedocs.io/en/latest/tests-and-scores/basis-function-bic-score.html) describes continuous basis expansions and discrete indicator bases, with finite-basis and residual assumptions. The [PC documentation](https://tetrad-manual.readthedocs.io/en/latest/algorithms/pc.html) requires i.i.d. data, acyclicity, causal sufficiency, Markov, and faithfulness; the [PC-Max documentation](https://tetrad-manual.readthedocs.io/en/latest/algorithms/pc-max.html) explains its maximum-p collider rule.

| Family | Mixed | Nonlinear | CPDAG | T05 role | Main limitation |
|---|---:|---:|---:|---|---|
| PC-Max + BasisFunctionLrt | Yes | Smooth finite basis | Yes | Primary-eligible | CI calibration and faithfulness; finite truncation |
| BOSS + BasisFunctionBicScore | Yes | Smooth finite basis | Yes | Primary-eligible | Greedy order search; local BIC adequacy |
| PC-Max + ConditionalGaussianLrt | Yes | No | Yes | Stress baseline only | Gaussian-within-discrete-cells assumption is violated |
| PC-Max + DegenerateGaussianLrt | Approximate | No | Yes | Stress baseline only | Indicator-Gaussian approximation does not cover mechanisms |
| PC + KCI | Limited mixed support | Flexible | Yes | Excluded before scoring | Kernel CI is computationally expensive at `N=16000` |
| DirectLiNGAM | No, continuous only | Linear | DAG | Excluded from P0 | Does not match mixed nonlinear released scenes; retained for P1 |

All eligible methods still rely on causal sufficiency, Markov/faithfulness, stable i.i.d. rows, and no selection or measurement error. CausalDS verifies no latent nodes for the graph cohort, but finite data cannot prove faithfulness or exact basis adequacy.

## Implementation pin and data view

The current `py-tetrad` README requests Python 3.12+, whereas this project is frozen to Python 3.10. T05 therefore does not import that wrapper. It calls the official Tetrad Java jar directly through JPype:

| Component | Pin |
|---|---|
| Python | 3.10.20 |
| OpenJDK | 21.0.10 |
| JPype | 1.6.0 |
| NumPy | 1.26.4 |
| py-tetrad source commit | `092a8cf13a9b31809d4256fd9aa3c98c52b88002` |
| jar implementation | `7.6.11-SNAPSHOT` |
| jar SHA-256 | `5A3BA56ADECE35DA8A209B39DB8B8BF29D4037FB79ED56C4B63F8D3B4C1A7051` |

The jar is cached below ignored `data/raw/`; it is not redistributed in Git. Continuous columns are z-scored independently inside each scene. Binary columns remain explicit two-category variables based on schema/mechanism metadata, even though parquet stores all physical columns as `float64`.

## Registered grid and hard gates

T05 ran 18 configurations:

- PC-Max + BF-LRT: `alpha ∈ {0.001, 0.01, 0.05}` × truncation `{2, 3}`;
- BOSS + BF-BIC: penalty `{1, 2, 4}` × truncation `{2, 3}`;
- PC-Max + CG-LRT: three alpha values, stress-only;
- PC-Max + DG-LRT: three alpha values, stress-only.

Every configuration had to run 8/8 scenes, return the exact anonymous node set with only directed/undirected marks, admit a consistent DAG extension, reproduce the exact graph on an immediate rerun, and remain below 120 seconds per scene. All 18 passed these operational gates.

The three top primary-eligible configurations by preregistered structural ranking then received 10 deterministic without-replacement half-samples per scene: `3 × 8 × 10 = 240` stability runs.

## Results

Metrics are macro-averaged over scenes. CPDAG SHD counts pairwise absent/undirected/directed state disagreements against the exact oracle CPDAG. Compelled-direction precision treats unsupported over-orientation as an error. Runtime is descriptive and machine-specific.

| Configuration | Skeleton F1 | CPDAG SHD ↓ | Direction P/R | Unresolved | Half-sample skeleton Jaccard | Endpoint agreement |
|---|---:|---:|---:|---:|---:|---:|
| **BOSS BF-BIC p=1, t=3** | **0.9594** | **0.375** | **1.000 / 1.000** | 0.900 | 0.9972 | 0.9970 |
| BOSS BF-BIC p=2, t=3 | 0.9594 | 0.375 | 1.000 / 1.000 | 0.900 | 0.9026 | 0.8458 |
| BOSS BF-BIC p=1, t=2 | 0.9529 | 0.750 | 0.875 / 1.000 | 0.850 | **0.9989** | **0.9994** |
| Best PC-Max BF-LRT: α=.001, t=3 | 0.9438 | 1.375 | 0.875 / 1.000 | 0.7889 | — | — |
| Best DG stress baseline: α=.001 | 0.9472 | 0.625 | 1.000 / 1.000 | 0.900 | — | — |
| Best CG stress baseline: α=.01 | 0.9375 | 0.875 | 1.000 / 1.000 | 0.900 | — | — |

The DG baseline scored well structurally but remained ineligible because its indicator-Gaussian approximation contradicts the registered heterogeneous nonlinear mechanism audit. It cannot displace an assumption-eligible basis-function method after seeing oracle scores.

Selected per-scene results:

| Scene | Skeleton F1 | CPDAG SHD | Unresolved rate |
|---|---:|---:|---:|
| `scene_000098` | 1.000 | 0 | 1.000 |
| `scene_000172` | 1.000 | 0 | 1.000 |
| `scene_000402` | 1.000 | 0 | 1.000 |
| `scene_000415` | 1.000 | 0 | 0.200 |
| `scene_000511` | 0.875 | 2 | 1.000 |
| `scene_000719` | 1.000 | 0 | 1.000 |
| `scene_000792` | 0.800 | 1 | 1.000 |
| `scene_000814` | 1.000 | 0 | 1.000 |

The high unresolved rate is material, not a failure to serialize a DAG. It means observational equivalence leaves most directions unidentified. Primary downstream evaluation must use the already-chosen conservative/invariance CPDAG semantics; the projected DAG cannot replace it.

## Deterministic DAG projection

`fourgraph.partial_graph.consistent_extension` implements deterministic Dor--Tarsi sink elimination. At each step it selects the lexicographically smallest eligible sink, directs its undirected incident edges into that sink, and validates:

- identical node set and skeleton;
- preservation of all CPDAG directed edges;
- acyclicity;
- no new unshielded collider.

All 144 full-run CPDAGs admitted a valid extension. The projection is frozen for sensitivity analysis only and adds arbitrary orientation where the CPDAG is unresolved.

## Selection decision

`boss_basis_bic__p1__t3` and `boss_basis_bic__p2__t3` tied on full-sample structural metrics. The penalty-1 configuration won because its half-sample stability was substantially higher. The truncation-2 finalist was slightly more stable but lost on the preregistered structural-priority criteria and introduced one over-orientation on the scene-macro evaluation.

The selected method therefore satisfies T05's purpose: a reproducible, mixed-data, nonlinear-capable CPDAG builder for P0 whose limitations are explicit. It does not validate a universal causal-discovery assumption over all released mechanisms.

## Artifacts and reproducibility

| Artifact | SHA-256 |
|---|---|
| Preregistration `configs/t05_scd_selection.yaml` | `6DDB755A2E3D2BE2F2BBCC21DFD9B78A677E69C0894CAC2C08EDD13F5D97ECCA` |
| Full/stability graph records `data/manifests/t05_dev_graphs.jsonl` | `60AE168B4D06AE1BD2C22B3D262D71D4CDC149CAFBA8A7013737135A62D08261` |
| Selection result `data/manifests/p0_scd_selection.json` | `45BAACE1E4289786F927771BF37041A57A2A81D436541B1795D9D903839282F1` |
| Frozen selected config `configs/t05_scd_frozen.yaml` | `729861541366775AFDCFB302E008C34866D2F2282D3614BA6578B79051330A33` |

`scripts/evaluate_causalds_t05.py --check` verifies config/split/jar/graph hashes and reruns the selected full-sample graph on every development scene. Automated tests cover anonymous data contracts, exact DAG-to-CPDAG scoring for the small P0 graphs, deterministic projection invariants, frozen run counts, and selected-method gates.

## Definition of Done

- [x] Official assumptions and implementations audited.
- [x] Shortlist/grid/gates frozen before development oracle scoring.
- [x] Only eight frozen graph-development scenes used.
- [x] 18 configurations × 8 scenes run and exactly rerun.
- [x] CPDAG validity, structural metrics, runtime, and determinism recorded.
- [x] Three finalists evaluated with 240 fixed half-sample runs.
- [x] One primary method selected by registered criteria.
- [x] Raw CPDAG retained as primary output.
- [x] Deterministic consistent extension implemented and tested as sensitivity only.
- [x] `p0_scd_ready: true` recorded with limitations.
- [x] Configs, manifests, report, tests, and coding log synchronized.
