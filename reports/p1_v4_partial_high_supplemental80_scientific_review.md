# P1V4 supplemental 80 — scientific review

The separately registered supplemental study reached **PASS_SUPPLEMENTAL_CONFIRMATION** under its frozen continuation rule. This is **not** a retroactive change to the original 440-scene `STOP_FOR_FUTILITY` result, nor is it independent validation or a holdout result.

## Evidence provenance

- Response freeze: 960/960 Mini-medium responses, 6,528 pair votes, 1,088 six-vote groups; production/reference disagreement 0; byte replay PASS. No Oracle was read until after this gate.
- Oracle scoring: exactly 80 new supplemental SCM commitments verified. The historical 440-scene results and fixed 120-scene Ambiguous diagnostic were reused as previously frozen.
- The same scene-level e-process components, mixture weights and alpha were continued; no alpha reset, new threshold, model change, closure or extra scene was used.

## Primary Constrained-BOSS

| Scope / variant | Published correct | Scene-mean coverage | HIGH contributing scenes | FP-adjacency orientations |
|---|---:|---:|---:|---:|
| New 80, Full | 443/443 | 81.91% | 23 | 0 |
| New 80, Partial | 252/252 | 46.51% | 11 | 0 |
| Combined 520, Full | 2,778/2,778 | 79.50% | 145 | 0 |
| Combined 520, Partial | 1,638/1,638 | 46.91% | **64** | 0 |

For Partial, **53 historical + 11 new = 64 HIGH-contributing scenes**, exceeding the registered minimum of 60. The continued HIGH guardrail e-value is 229.40, crossing the registered alpha 0.025 boundary. Full and Partial precision confidence sequences and coverage gates also cross. Published overlays are valid after fail-closed suppression in 520/520 scenes; the fixed historical Ambiguous diagnostic remains PASS. Thus the *registered joint supplemental decision* is PASS.

In the new 80 Partial scenes, 128/128 certified-compelled directions and 124/124 semantic-selected directions were correct. In Full, the corresponding counts were 234/234 and 209/209. These are observed counts on synthetic SCMs, not a promise of 100% performance elsewhere.

## Robustness and limitations

Constrained-FGES had no published direction errors in the new 80 scenes: Full 379/379 at 71.01% scene-mean coverage; Partial 222/222 at 42.27%. Combined Partial HIGH has **58** contributing scenes, below the registered 60-scene minimum, so the FGES robustness track does **not** independently satisfy that guardrail. It is not the primary certification condition.

The supplemental protocol was designed after observing the original stop and explicitly preserves it. The continued anytime-valid interpretation depends on the registered conditional-mean/stationarity assumptions, which these synthetic data cannot prove. The fresh 80 results are descriptive, not a separately powered independent replication. The next scientific step is to freeze the confirmed policy and obtain separate authorization for independent validation; validation and holdout remain unopened.

Source artifacts: `data/manifests/p1_v4_partial_high_supplemental80_response_freeze_rescore_audit.json`, `data/manifests/p1_v4_partial_high_supplemental80_overlay_oracle_metric_results.json`, `data/manifests/p1_v4_partial_high_supplemental80_overlay_oracle_metric_audit.json`.

Verification: byte-for-byte response and Oracle-scoring replay passed; post-execution tests passed 6/6. Two historical pre-materialization tests intentionally no longer pass on a materialized cohort because they assert that the reserved output directories are empty. They were not changed or used as post-execution gates.
