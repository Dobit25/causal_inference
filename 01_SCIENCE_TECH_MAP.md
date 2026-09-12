# Science & Technology Map

## Scientific pipeline

```text
Story / observational data
          |
          v
   graph construction
          |
          v
 DAG or honest CPDAG representation
          |
          v
 fixed graph-guided LLM reasoner
          |
          v
 adjustment/control answer and audit
```

The project studies the bridge:

\[
\boxed{\text{graph provenance} \rightarrow \text{graph quality} \rightarrow \text{causal reasoning utility}}
\]

## Four information regimes

| Regime | Permitted source | Forbidden source |
|---|---|---|
| `G_LLM` | Public story and variable semantics | Observational table, grading truth |
| `G_SCD` | Anonymized same-scene observations | Story, semantic labels, grading truth |
| `G_HYBRID` | SCD CPDAG/skeleton plus story semantics | Grading truth |
| `G_ORACLE` | Grading-only ground-truth graph | Use outside explicit oracle evaluation |

All four regimes terminate at the same `fourgraph.graph.v1` adapter boundary. The artifact validator enforces the evidence allowlist recorded for each regime; the reasoner view then removes method and provenance fields so only graph structure varies experimentally.

For `G_LLM`, T08 uses a separate public-only loader and strict all-pairs JSON/DAG contract. The frozen OpenAI Responses adapter (`gpt-5.4-nano-2026-03-17`, SDK `3.6.0`) generated and replay-validated canonical DAGs for all eight development scenes without retries or holdout access.

## P0 and P1 roles

### Released CausalDS P0

- Tests the complete four-graph pipeline on a real released artifact.
- Uses all 33 clean/no-latent scenes for graph construction and structural evaluation.
- Uses a nested 27-scene, five-task panel for primary downstream evaluation.
- Retains the remaining 6 scenes as a separately reported exploratory supplement.
- Uses heterogeneous released SCM mechanisms, so its result is exploratory.
- Uses T05-selected BOSS with a mixed/nonlinear basis-function BIC score; assumptions and the eight-scene development selection remain explicit limitations.
- Preserves the SCD CPDAG as the primary statistical representation.
- Uses deterministic DAG projection only as sensitivity.
- T09 materializes both views for all eight frozen development scenes under the shared T06 contract; the SCD builder reads only anonymized same-scene observations and schema types.

### Fresh homogeneous CausalDS P1

- Generates linear, acyclic, non-Gaussian, causally sufficient SCMs.
- Matches those assumptions to DirectLiNGAM.
- Provides the primary controlled scientific result.
- Adds nonlinear additive-noise SCMs only as a later robustness extension.

## Hybrid scope

The first hybrid is deliberately narrow:

```text
SCD skeleton + compelled orientations
                |
                v
LLM orients only unresolved edges from story semantics
                |
                v
acyclicity and CPDAG-consistency checks
```

H1 cannot add or delete adjacency. It evaluates semantic resolution of statistically unresolved direction, not general learned hybrid causal discovery.

T10 implements this intervention on the frozen development split: 8/8 Hybrid DAGs and 27/27 edge-level semantic audits passed the T06 parent/equivalence validator. The semantic model/configuration matches T08 exactly, while the T08 graph artifacts themselves are forbidden inputs.

The T06 relationship validator also requires the Hybrid DAG to remain in the parent CPDAG's Markov equivalence class and logs every formerly undirected edge exactly once. Projected SCD DAGs use the same parent checks but label their lexicographic orientations as arbitrary sensitivity choices.

## Evaluation layers

1. Structural: skeleton scores, compelled-orientation scores, DAG-projection scores, SHD where valid.
2. Causal-functional: SID/AID only when graph types and implementations are compatible.

T11 completes the development structural layer with 40 type-aware records and an H1 attribution split between inherited SCD adjacency/compelled errors and semantic choices on unresolved edges. SID/AID are null/unavailable, not zero, because a validated implementation is not yet pinned.
3. Downstream: oracle-answer accuracy and uncertainty-aware correctness.
4. Audit: leakage, invalid graph, parser failure, cost, latency, and sensitivity to projection.

## Scientific claims boundary

The released P0 may establish feasibility and an exploratory signal. General claims require fresh P1. A null or adverse result remains valid when the design, exclusions, and analysis are frozen before holdout evaluation.
