# Science & Technology Map

## Pipeline

```text
Observational data / text / domain semantics
                    |
                    v
        [A. Causal Discovery]
                    |
             estimated graph
                    |
                    v
      [B. Graph Representation]
                    |
                    v
      [C. LLM Causal Reasoning]
                    |
                    v
      [D. Verification / Audit]
```

### A. Causal discovery
Relevant work: LLM-CD, MATMCD, classical SCD, LLM causal-discovery reliability.

### B. Graph representation
CausalGraph2LLM shows LLM causal performance can be highly sensitive to graph encoding. Therefore graph encoding must be held constant across all four graph conditions.

### C. Graph-guided reasoning
NoisyCausal shows explicit causal structure can improve reasoning robustness under structured noise, while wrong/random graphs can be harmful.

### D. Formal verification
DoVerifier verifies whether an LLM-generated causal expression is formally valid **given a graph**; it does not prove the graph itself is true.

## Exact position of this project

This project bridges A -> C:

```text
different graph-construction regimes
        -> graph quality
        -> same fixed LLM causal reasoner
        -> downstream causal-identification quality
```

The scientific object is **error propagation from graph construction to causal reasoning**.

## Scientific value

1. **Bridge intrinsic and functional graph evaluation.** A graph can have good SHD/F1 yet still imply the wrong causal adjustment for the query.
2. **Test causal-aware metrics.** SID evaluates intervention implications; AID evaluates adjustment-identification differences. Test whether they predict LLM downstream reasoning better than SHD/F1.
3. **Separate information sources.**
   - LLM = semantics/text;
   - SCD = observational data;
   - Hybrid = semantics + data;
   - Oracle = ground truth.
4. **Oracle decomposition.**
   - `Accuracy(G_ORACLE) - Accuracy(G_method)` estimates loss from graph construction under a fixed reasoner.
   - `1 - Accuracy(G_ORACLE)` estimates residual reasoning error after graph error is removed.
5. **Engineering value.** Quantifies trade-offs among cheap LLM-only graphs, data-only discovery, hybrid discovery, and expert/oracle curation.

## Paper-worthy outcomes

Any of the following can support a paper:
- Hybrid wins on graph quality and downstream reasoning.
- Better SHD/F1 does **not** mean better causal reasoning.
- SID/AID correlates more strongly with downstream utility.
- Oracle gap is small -> reasoning, not graph induction, is the main bottleneck.
- Oracle gap is large -> graph induction is a major bottleneck.
- Query-relevant orientation/confounder errors explain most downstream degradation.

## Novelty wording

Do not claim “no one has studied downstream utility of causal graphs.” LLM-CD and MATMCD contain downstream tasks.

A safer novelty target is:

> We study how graph provenance and graph error propagate into **fixed-LLM causal identification/reasoning**, using a controlled four-graph design and both structural and intervention/identification-aware graph metrics.
