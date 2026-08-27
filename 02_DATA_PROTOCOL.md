# NoisyCausal Data Protocol

## Hard gate: verify the artifact first

The paper reports 10,617 QA pairs generated from ground-truth DAGs and SCMs with clean and noisy variants.

At handoff time, a public author-linked downloadable dataset/code repository was **not verified** from the ACL Anthology/arXiv landing pages. Therefore the first coding task is an artifact audit.

Do not fabricate missing fields.

## Required data per base causal system

Ideally:

```yaml
system_id:
domain:
variables:
  - id:
    label:
    type:
    observability:
ground_truth_graph:
  nodes: []
  edges: []
structural_model:
  equations_or_cpds: ...
clean_questions: []
noisy_questions: []
noise_metadata: ...
```

## Critical rule: QA rows are NOT observational samples

Never pool benchmark rows generated from different SCMs into one table and run causal discovery.

SCD requires repeated observations from the **same SCM**:

```text
SCM_k -> row1, row2, ..., rowN
```

not:

```text
SCM_1 -> one row
SCM_2 -> one row
...
```

## Readiness decision tree

### Case A — full SCM / CPDs / sampler exists
Proceed:
- load `G_true`;
- generate observational table for each SCM;
- build four graphs;
- evaluate associated clean/noisy questions.

### Case B — equations/CPDs exist, no sampler
Implement topological resampling from those rules.

### Case C — only graph + single assignments / QA text
STOP the SCD study.
A single assignment is insufficient for statistical causal discovery.

Next:
1. re-check official artifact;
2. contact authors;
3. if unavailable, create a clearly labeled **NoisyCausal-compatible regenerated study** rather than claiming it is the official released dataset.

## Pilot selection

- Dev: 10 base SCMs.
- Frozen holdout: 30–50 base SCMs.
- Stratify by node count, motif, query type, domain, and variable type if available.

## Observational sample size

Primary: `N=2000` per SCM.

Sensitivity:
- `N=500`;
- `N=10000` on ~10 systems.

## Primary clean/noise design

### Primary analysis — fixed graph, varying reasoning noise
Build all graphs from clean graph-construction evidence and freeze them.

Evaluate the same graph-guided reasoner on:
- clean;
- IV;
- CS;
- CI.

This isolates:
`graph provenance -> reasoning robustness`.

### Secondary analysis — noisy graph induction
Rebuild `G_LLM` and `G_HYBRID` from noisy contexts and measure:
`noise -> graph induction -> reasoning`.

Do not mix these two analyses.

## Validation checks

- unique system/question IDs;
- graph acyclicity;
- node schema consistency;
- clean/noisy parent linkage;
- gold answers present;
- no oracle leakage;
- observational tables contain only allowed observed variables;
- raw source hashes stored.

## Manifest

Store `data/MANIFEST.json` with source URL, retrieval date, file hashes, source commit if available, filters, selected IDs, and regeneration status.
