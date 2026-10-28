# P1V4 Partial High supplemental 80 — execution summary

Status: statistical execution **PASS**; Mini-medium semantic execution **PASS**. This is an independent supplemental cohort, not a revision of the negative/inconclusive look-440 decision. No Oracle scoring, validation, holdout access, closure, or downstream reasoning was performed here.

## Materialization and statistical layer

- Exact cohort: 80 frozen `P1V4SH` scenes; 240 public Full/Partial/Ambiguous story artifacts materialized. Only Full and Partial were used for new semantic calls.
- Planned/recorded statistical identities: **16,480/16,480**: Single-BOSS 80, Bootstrap-BOSS 16,000, PC 80, MMPC 80, FGES 80, Constrained-BOSS 80, Constrained-FGES 80.
- Raw/normalized artifacts: **16,480/16,480** each. Ensemble aggregate artifacts: **80/80**. Execution error artifacts: **0**.
- One PC output on `P1V4SH078` was `INVALID_NO_VOTE` because its PDAG had no consistent DAG extension; the frozen fallback used **3/4** votes for that scene. The other 79 scenes used **3/5**. Both constrained parents were `VALID` on all 80 scenes.
- Shared semantic pool: **544** scene–pair records, **4–9** pairs per scene. This includes all adjacencies from Constrained-BOSS ∪ Constrained-FGES, including compelled and undirected edges; no non-edge calls.

## Mini-medium provider and study execution

- One synthetic provider preflight, 7 nodes/21 pairs: **PASS**, model `gpt-5.4-mini-2026-03-17`, reasoning effort `medium`, no truncation; **1,833** provider-reported total tokens.
- Exact frozen study plan: **80 scenes × 2 variants × 6 prompts = 960 logical calls**. Completed **960/960**, with **960 distinct IDs**, **0 provider errors**, and **0 retries**.
- Response-level operational validation: **846** completely valid responses; **114** responses with one or more invalid pairs. Pair-level operational validation: **6,201/6,528** valid pair judgments; **327** invalid. These are contract checks, not Oracle direction accuracy.
- Provider-reported study usage: **627,198 input**, **781,962 output** (including **537,863 reasoning**), **1,409,160 total** tokens. Including preflight: **1,410,993 / 2,500,000** total-token cap; **1,089,007** remained. Reasoning tokens are a subset of output tokens and must not be added a second time.
- All 960 request IDs are present and all returned the pinned Mini snapshot.

## Hash-pinned audit trail

| Artifact | SHA-256 |
|---|---|
| Statistical final audit | `798D133BAFB8836FEC6141AEAA18DC6D8D33ADB75B8877451E1A19A775867082` |
| Shared semantic plan | `45FCA525134C475A2847975887EFA315A3999D496E60C79906CB42BD70A23091` |
| Synthetic provider preflight | `EC81278F11076E08D130E4C6C0D3A303C07BB21383B4DF1600443A20BA37540F` |
| Mini live authorization | `F8786E28BD51AA604B52DE5C4BC65BB92765B4A5383E536A90E3D2FC2A8141F8` |
| Mini execution audit | `B221918CCD7D8BD5B02E78AA8F9E02A593370F2B6F44E6CDC576C8A2972C1229` |
| Raw response cache | `68B3A00AFD6425751DA7F116A0F35B880D389B631FB4C8463B33FE108326FC44` |
| Token ledger | `A65E6DD830FE0840884379E83D4955D7D4C28853B62C2AC724D629A83BF4EBBF` |

The exact 960 planned IDs and 960 cached IDs match with no duplicates; the token ledger has 961 rows (one preflight plus 960 study responses). The next protocol step is a separate response-freeze and offline pair-level/six-vote re-score. Oracle scoring of this supplemental cohort requires its own authorization after that audit.
