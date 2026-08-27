# Metrics Protocol

Use three layers.

## Layer 1 — Structural graph quality

- Skeleton precision / recall / F1.
- Directed-edge precision / recall / F1.
- Orientation accuracy.
- SHD and normalized SHD.

These separate:
- adjacency mistakes;
- direction mistakes;
- overall edit distance.

## Layer 2 — Causal-functional graph quality

### SID — Structural Intervention Distance
Reference:
https://doi.org/10.1162/NECO_a_00708

SID measures discrepancies in intervention implications, not only edge edits.

### AID / Adjustment Identification Distance family
Reference:
https://proceedings.mlr.press/v244/henckel24a.html

These distances focus on differences in adjustment-based causal identification.

### Query-relevant structural error
Exploratory:
measure errors only in the treatment/outcome-relevant causal subgraph.

Do not present as a standard metric unless formally defined.

## Layer 3 — Downstream LLM utility

- Final-answer accuracy.
- Accuracy by query type.
- Accuracy by noise type.
- Robustness drop.

Define:

```text
NoiseDrop(method,z)
= Accuracy_clean(method) - Accuracy_noise_z(method)
```

### Oracle gap

```text
OracleGap(method)
= Accuracy(G_ORACLE) - Accuracy(G_method)
```

### Residual oracle error

```text
ResidualOracleError
= 1 - Accuracy(G_ORACLE)
```

## Optional structured causal-answer scoring

If the reasoner returns structured outputs, score:
- query type;
- treatment variable;
- outcome variable;
- identifiability;
- adjustment set;
- causal formula;
- final answer.

This distinguishes:
`correct graph + wrong reasoning`
from:
`wrong graph + internally consistent reasoning`.

## Cost logs

Always log:
- graph-builder calls;
- reasoner calls;
- latency;
- token usage if available;
- retries;
- invalid JSON/output count.

## Main analyses

1. Rank four graph methods by F1/SHD/SID/AID/downstream accuracy.
2. Compare ranking disagreement.
3. Spearman correlations from graph metrics to downstream accuracy.
4. Analyze error types: deletion, false edge, reversal, confounder, off-path.
5. Analyze graph condition × NoisyCausal noise type.

## Required per-item record

```json
{
  "system_id": "...",
  "question_id": "...",
  "graph_method": "llm|scd|hybrid|oracle",
  "noise_type": "clean|IV|CS|CI|...",
  "graph_hash": "...",
  "prompt_hash": "...",
  "model_id": "...",
  "raw_output": "...",
  "parsed_answer": "...",
  "gold_answer": "...",
  "is_correct": true,
  "latency_ms": null,
  "input_tokens": null,
  "output_tokens": null
}
```

Never retain only aggregate accuracy.
