# Research Context — Four-Graph Causal Reasoning Pilot

## Core direction

Construct four causal graphs for the causal system:

1. `G_LLM`: graph induced from semantic/natural-language information by an LLM.
2. `G_SCD`: graph induced only from observational data by a statistical causal discovery method.
3. `G_HYBRID`: graph induced by combining statistical evidence with LLM/domain-semantic constraints.
4. `G_ORACLE`: the NoisyCausal ground-truth graph.

Then inject each graph into the **same frozen graph-guided reasoner** using the same question, evidence, graph encoding, model/version, decoding settings, parser, and scoring code.

The main question is not only “which graph is structurally closest to ground truth?” but also:

> Which graph is most useful for downstream causal identification/reasoning by an LLM?

## Research questions

- **RQ1:** How do the four graph sources differ in graph quality?
- **RQ2:** With a fixed reasoner, how much does reasoning accuracy change across graph conditions?
- **RQ3:** Do SHD/edge-F1 predict downstream reasoning utility?
- **RQ4:** Do SID/AID predict downstream causal utility better than ordinary structural metrics?
- **RQ5:** Which graph errors are most harmful: deletion, false edge, reversal, confounder error, or off-path error?
- **RQ6:** Does graph provenance change robustness to NoisyCausal noise?

## Hypotheses

- H1: `G_ORACLE` should usually be best downstream.
- H2: `G_HYBRID` should outperform at least one non-oracle baseline.
- H3: lower SHD / higher F1 will not perfectly imply better reasoning.
- H4: SID/AID or query-relevant graph errors will correlate more strongly with downstream causal reasoning than global SHD.
- H5: direction-reversal and confounder-related errors will be disproportionately harmful.

A negative result is still valuable if the experiment is controlled and sufficiently powered.

## Non-negotiable controls

Downstream comparison must hold fixed:
- question set;
- context/evidence;
- reasoner model/version;
- reasoner prompt;
- graph serialization;
- decoding settings;
- answer parser;
- scoring code.

Only the graph changes.

Do not leak `G_ORACLE` into non-oracle graph construction.

## Literature anchors

- NoisyCausal, ACL 2026: https://aclanthology.org/2026.acl-long.1833/
- CausalGraph2LLM, Findings NAACL 2025: https://aclanthology.org/2025.findings-naacl.110/
- MATMCD, Findings ACL 2025: https://aclanthology.org/2025.findings-acl.36/
- LLM-CD, KDD 2025: https://www.cs.emory.edu/~jyang71/files/llmcd.pdf
- Reliability of LLMs for Causal Discovery, ACL 2025: https://aclanthology.org/2025.acl-long.471/
- SID, Neural Computation 2015: https://doi.org/10.1162/NECO_a_00708
- Adjustment Identification Distance, UAI 2024: https://proceedings.mlr.press/v244/henckel24a.html
- DoVerifier, EACL 2026/arXiv: https://arxiv.org/abs/2601.21210
