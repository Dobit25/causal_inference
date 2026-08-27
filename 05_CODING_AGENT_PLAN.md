# Coding Agent Plan

## Rules

- Work task-by-task.
- Do not start the next task until Definition of Done is met.
- Update `codinglog.md` after every task.
- Never use oracle information in non-oracle graph builders.
- Never pool observations from different SCMs.
- Store raw inputs/outputs and hashes.
- All stochastic code uses explicit seeds.
- Version all experiment configs.

## Suggested repo

```text
repo/
├─ README.md
├─ context.md
├─ literature_map.md
├─ experiment_plan.md
├─ data_protocol.md
├─ metrics.md
├─ codinglog.md
├─ pyproject.toml
├─ configs/
│  ├─ pilot.yaml
│  └─ prompts/
├─ data/
│  ├─ raw/
│  ├─ interim/
│  ├─ processed/
│  └─ MANIFEST.json
├─ src/fourgraph/
│  ├─ data/
│  ├─ graphs/
│  ├─ reasoner/
│  ├─ metrics/
│  └─ logging/
├─ tests/
└─ results/
```

# T00 — Bootstrap
Deliver:
- Python package skeleton;
- pytest;
- config loader;
- deterministic seed utility;
- codinglog.

DoD:
- tests pass;
- package imports;
- CLI help works.

# T01 — NoisyCausal artifact audit
Record:
- official URLs;
- downloadable artifacts;
- retrieval date;
- hashes;
- schema;
- whether clean/noisy linkage exists;
- whether `G_true` exists;
- whether SCM equations/CPDs/sampler exist.

Write `docs/data_audit.md`.

Critical output:

```yaml
scd_ready: true|false
reason: ...
```

If false, STOP SCD implementation.

# T02 — Canonical data model
Implement contracts for:
- `CausalSystem`;
- variables;
- graph;
- SCM;
- question;
- noise;
- observational dataset.

Validate DAGs and IDs.

# T03 — Observational sampler
Only if T01 confirms resampling information.

Requirements:
- topological sampling;
- seed;
- configurable N;
- marginal/conditional sanity checks.

# T04 — Four graph builders

## Oracle
Exact normalized `G_true`.

## LLM-only
Semantic/text input only.
Strict JSON graph output.
Persist prompt/output/retries.

## SCD-only
Observational table only.
Anonymize semantics if required.

## Hybrid
Combine SCD uncertainty with LLM guidance.
Persist edge-level arbitration logs.

DoD:
- all outputs satisfy one graph contract;
- no oracle leakage;
- integration tests pass.

# T05 — Metrics
Implement:
- skeleton F1;
- directed F1;
- orientation accuracy;
- SHD;
- SID/AID if compatible.

# T06 — Frozen graph-guided reasoner
One prompt, one model, one encoding, four graph conditions.

DoD:
- only graph payload differs;
- prompt/template hashes confirm this.

# T07 — Clean pilot
Dev 10 SCMs.
Holdout 30–50 SCMs.

Produce:
- graph metrics table;
- reasoning accuracy;
- oracle gap;
- metric-to-reasoning correlations.

# T08 — Noise pilot
Frozen graphs from T07.
Start with IV/CS/CI.

Produce:
- accuracy by graph × noise;
- clean-to-noise drops;
- clustered bootstrap CIs.

# T09 — Statistics
Implement:
- paired bootstrap by SCM;
- McNemar;
- multiple-testing correction;
- Spearman correlations.

# T10 — Pilot decision report
Create `reports/pilot_findings.md` with:
1. data readiness;
2. graph quality;
3. downstream reasoning;
4. metric-vs-reasoning results;
5. oracle decomposition;
6. noise robustness;
7. failure cases;
8. limitations;
9. paper viability;
10. next experiment.

## codinglog template

```markdown
## TXX — Task
- Status:
- Started:
- Finished:
- Commit:
- Config:
- Files changed:
- Summary:
- Tests:
- Results:
- Risks:
- Next:
```

## Research-integrity checklist

- [ ] no test-set prompt tuning
- [ ] no oracle leakage
- [ ] same reasoner across graph conditions
- [ ] same graph encoding
- [ ] same question/evidence
- [ ] no pooling across SCMs
- [ ] raw outputs retained
- [ ] seeds/configs logged
- [ ] retries/parser failures reported
