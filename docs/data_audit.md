# T01 — NoisyCausal Artifact Audit (Historical)

> This negative audit is retained as project history. CausalDS is now the active substrate; see `reports/causalds_release_audit.md` and `data/manifests/causalds.json`.

## Verdict

As of **2026-08-27**, the official NoisyCausal publication is verified, but a public, author-linked dataset/code artifact is not. The publicly retrievable first-party materials are the ACL paper, its Responsible NLP Checklist, and the arXiv LaTeX/figure source. They describe how NoisyCausal was generated, but they do not contain the 10,617 records, a per-system SCM serialization, an executable sampler, or repeated observational tables.

Therefore, the current artifact is **not sufficient to generate multiple observational samples from the same SCM**, and the statistical causal-discovery branch must stop at this gate.

```yaml
readiness:
  artifact_verified: false
  reasoning_ready: false
  graph_eval_ready: false
  noise_eval_ready: false
  scd_ready: false
  oracle_ready: false

scd_ready: false
reason: >
  The public first-party materials contain the paper, checklist, and
  LaTeX/figure source, but no dataset records, complete per-system SCM/CPD
  files, executable sampler, or repeated observational samples grouped by
  causal system. Paper descriptions and example probabilities are not a
  resampleable artifact.
```

`artifact_verified: false` means that the **benchmark data artifact** could not be verified or acquired. It does not mean that the paper or its reported experiments are unverified publications.

## Audit question and decision rule

The audit asks:

> Does the official NoisyCausal artifact contain enough information to generate multiple observational samples from the same SCM?

The required structure is:

```text
SCM_001 -> observation_001
        -> observation_002
        -> ...
        -> observation_N
```

The following is invalid for SCD:

```text
QA row from SCM_001
QA row from SCM_002
QA row from SCM_003
        -> pooled as one observational table
```

Paper claims are used to understand intended composition. Readiness is based only on fields and behavior that can be inspected in the released artifact.

## Official-source audit

| Source | Version/status | What was available | Artifact outcome |
|---|---|---|---|
| [ACL Anthology landing page](https://aclanthology.org/2026.acl-long.1833/) | ACL 2026, DOI `10.18653/v1/2026.acl-long.1833` | Paper PDF and checklist | No dataset/code/supplementary-data link listed |
| [ACL paper PDF](https://aclanthology.org/2026.acl-long.1833.pdf) | Proceedings version | Method, aggregate statistics, examples, prompt templates | Descriptive evidence only |
| [Responsible NLP Checklist](https://aclanthology.org/attachments/2026.acl-long.1833.checklist.pdf) | ACL 2026 | Confirms that scientific artifacts were created/used | Does not provide an artifact URL or dataset license |
| [arXiv abstract](https://arxiv.org/abs/2605.04313) | `2605.04313v1`, 2026-05-05 | Paper metadata and PDF/source links | No repository or dataset link |
| [arXiv HTML](https://arxiv.org/html/2605.04313) | `v1`, CC BY 4.0 | Searchable paper content | No availability statement |
| arXiv source archive | `v1` | 12 files: LaTeX, bibliography, styles, and five PDF figures | No dataset records, code, or sampler |
| [OpenReview submission](https://openreview.net/forum?id=9kGjeJIBiE) | Public submission discoverable | Paper PDF/search metadata | No downloadable data/code verified; direct access was challenged |
| [Author GitHub profile](https://github.com/zhix9767) | Checked 2026-08-27 | Two unrelated public repositories | No NoisyCausal repository |

Additional exact-name searches returned zero GitHub repositories, zero Hugging Face datasets, and zero Zenodo records. Search absence alone cannot prove that a private or unindexed artifact does not exist. It does establish that no downloadable public artifact was verified through the official publication chain or the checked public hosts at the audit date.

### Version and license conclusion

- Official paper: ACL 2026 proceedings version; arXiv `2605.04313v1`.
- Code/dataset release or commit: none verified.
- Paper/source license: CC BY 4.0.
- Dataset/code license: unknown because no release was found. The paper license must not be assumed to license unreleased data or code.

## Artifact inventory and hashes

Raw downloads are cached under `data/raw/noisycausal/` and ignored by Git. Their versioned inventory is [data/manifests/noisycausal.json](../data/manifests/noisycausal.json); [data/MANIFEST.json](../data/MANIFEST.json) is now the multi-source index.

| File | Bytes | SHA-256 | Git policy |
|---|---:|---|---|
| `2026.acl-long.1833.pdf` | 489,369 | `BF79980CEC2607EE381BBE8AC86333F29E4D04EF0E5425E98652E10BDC9A132B` | Ignore raw; record manifest |
| `2026.acl-long.1833.checklist.pdf` | 63,766 | `D79696033DA996276875F7A406C71C4A4B3AD5554A340B23C6E2374B883224DB` | Ignore raw; record manifest |
| `2605.04313v1-source.tar` | 297,368 | `AE25FAFA3DE9B51F2DD2BA9FDB5CDAE527F4941F4A50C13FD0E01F73B6FF0896` | Ignore raw; record manifest |

The separately supplied local copy at `D:\Downloads\NEU\Causal_AI\2026.acl-long.1833.pdf` has the same SHA-256 as the downloaded ACL proceedings PDF.

## Schema audit

No dataset record was available, so there is no actual serialized schema to report. The table below separates paper-reported composition from fields verified in an artifact. It must not be treated as a proposed or reconstructed schema.

| Required concept | Paper reports | Verified field/schema in released artifact | Audit conclusion |
|---|---|---|---|
| `system_id` or equivalent | Not specified | No | Cannot group questions or observations by SCM |
| `question_id` | Not specified | No | Stable question identity unavailable |
| Variables | Variables have semantic labels | No serialized record | Names/IDs cannot be enumerated |
| Variable type | Binary, categorical, continuous | No serialized field name or values | Type metadata unavailable operationally |
| Observed/latent status | Reported as variable metadata | No serialized field | Cannot construct the observed-only SCD table |
| Ground-truth graph | Corresponding graph `G` per instance | No graph files/records | `G_true` cannot be loaded or scored |
| Structural equations | Logic/probabilistic rules described | No per-instance equations | Not resampleable |
| CPDs | Example conditional probabilities shown | No complete per-instance CPDs | Examples are insufficient |
| Exogenous noise distribution | Not fully specified | No | Independent resampling semantics undefined |
| Assignment/observation | Clean and noisy assignments reported | No records | Cannot determine whether this is one draw or repeated data |
| Clean question | Natural-language question reported | No records | Reasoning evaluation cannot run |
| Noisy variant | Parallel clean/noisy variants reported | No records | Variant payload unavailable |
| Noise type | `VP`, `IV`, `PM`, `CS`, `CI`, `QP`; composition allowed | No serialized labels | Counts and combinations cannot be validated |
| Gold answer | Derived from clean SCM and graph | No records | Scoring unavailable |
| Clean/noisy parent linkage | “Stored in parallel” | No IDs or linkage fields | Pairing cannot be validated |
| Split membership | Validation set is referenced | No split files or IDs | Dev/holdout construction cannot be reproduced |

An “actual record example” is intentionally absent: producing one without a released record would fabricate field names and nesting, violating the data protocol.

## Ground-truth graph audit

### What the paper establishes

- Graphs are directed, connected DAGs with 3–7 nodes.
- Chains, forks, colliders, and multiple-converging-parent motifs are used.
- Variables receive semantic labels, type, observability, and causal-role metadata.
- Appendix A says each instance has a corresponding causal graph that may optionally be shown to a model.
- The oracle and controlled graph-perturbation experiments require internal ground-truth graphs.

### What the release does not establish operationally

- No `G_true` records were released for loading.
- Graph scope cannot be verified as a reusable causal-system object versus a duplicated per-QA payload.
- Node identifiers cannot be checked against question variables.
- Acyclicity and edge validity cannot be checked across the reported 10,617 rows.
- Latent-node representation cannot be inspected.
- Clean/noisy variants cannot be confirmed to reference the same graph through stable IDs.

Result: `graph_eval_ready: false` and `oracle_ready: false`.

## Resampling audit

| Requirement | Status | Evidence |
|---|---|---|
| Complete structural equations per system | Missing | The paper describes rule families, not released per-system equations |
| Complete CPDs per system | Missing | Only illustrative probabilities appear in the paper |
| Root-node distributions | Missing as an artifact | An example root probability is not a dataset-wide specification |
| Conditional distributions | Missing as an artifact | No CPD files or tables |
| Exogenous-noise distributions | Missing | No generator implementation or complete mathematical specification |
| Topological sampling order | Described conceptually | No per-system order records or runnable sampler |
| Binary/categorical/continuous implementation | Described conceptually | Exact functions and parameterization unavailable |
| Latent-variable sampling/withholding | Described conceptually | No executable behavior or records to inspect |
| Seed handling | Missing | No official generator or reproducibility configuration |
| Repeated samples from one SCM | Missing | No grouped observational tables and no callable sampler |

The prompt template in the appendix asks an LLM to define CPDs and a topological recipe. A prompt is not an SCM artifact: without its generated per-system outputs and an executable, seeded sampling contract, it cannot reproduce the authors’ causal systems or generate defensible repeated observations.

Result: `scd_ready: false`.

## Clean–noise linkage audit

The paper reports six noise codes:

- `VP`: Value Perturbation.
- `IV`: Irrelevant Variable Injection.
- `PM`: Partial Masking.
- `CS`: Causal Swap.
- `CI`: Latent Confounders.
- `QP`: Question Perturbation.

It states that noises may be composed and that clean/noisy variants are stored in parallel. It also states that answers are derived from the clean SCM and causal graph even when distractors or inconsistent evidence are present.

The release does not expose:

- clean or noisy sample IDs;
- a parent/link field;
- composition labels or severity values;
- which payload component changed per record;
- whether every variant retains one stable `system_id` and graph reference;
- whether a perturbation changes the expected answer for any exceptional query type.

Result: `noise_eval_ready: false`.

## Oracle-leakage boundary

If an artifact becomes available, the ingestion layer must enforce this access matrix:

| Information | `G_LLM` | `G_SCD` | `G_HYBRID` | `G_ORACLE` | Reasoner evaluation |
|---|---:|---:|---:|---:|---:|
| Variable semantics / clean text | Yes | No | Yes | No | Same across graph conditions |
| Observational table | No | Yes | Yes | No | No |
| Ground-truth graph | No | No | No | Yes | Only as the oracle graph payload |
| Gold answer | No | No | No | No | Scoring only after inference |
| Holdout results | No tuning | No tuning | No tuning | No tuning | No tuning |

The raw artifact should remain immutable. Derived views must be created by explicit field allowlists, not by passing a full record to each builder and relying on prompts not to use forbidden fields.

## Decision branches

### Current branch — `scd_ready: false`

1. Stop T03 and the SCD/hybrid portions of T04.
2. Contact the authors and request:
   - the 10,617 QA records and split IDs;
   - stable causal-system/question/variant identifiers;
   - per-system `G_true`;
   - complete SCM equations/CPDs and exogenous-noise definitions;
   - generator/sampler code with seeds and dependency versions;
   - clean/noisy linkage and noise metadata;
   - dataset/code license and release version.
3. Re-run T01 against the received or newly published immutable release and append its hashes to the manifest.
4. If no artifact becomes available, choose explicitly between:
   - a **NoisyCausal-compatible regenerated study**, with a new dataset identifier and no claim that it is the official release; or
   - a different benchmark with resampleable SCMs.

Because no QA artifact was acquired, even LLM-only/oracle reasoning evaluation on official NoisyCausal is not operationally ready today.

### Future branch — if a complete artifact is released

Before changing `scd_ready` to `true`, verify at least one system end to end:

1. Load its graph and full mechanism.
2. Generate two batches with the same seed and confirm equality.
3. Generate a batch with a different seed and confirm non-degenerate variation.
4. Confirm variable domains and graph-parent dependencies.
5. Remove latent variables from the SCD view while retaining them in the oracle contract.
6. Confirm clean/noisy records share stable causal-system provenance.

Only then proceed to T02/T03 and select an SCD family after inspecting the actual data types and assumptions.

## Definition of Done

- [x] Official publication sources verified.
- [x] URLs, retrieval date, versions, and available licenses recorded.
- [x] Every downloaded artifact used in the audit hashed with SHA-256.
- [x] Actual schema availability assessed without inventing fields.
- [x] `system_id`, `question_id`, and QA-variant availability determined.
- [x] `G_true` release status determined.
- [x] SCM/CPD/sampler release status determined.
- [x] Same-SCM repeated-observation feasibility determined.
- [x] Observed/latent metadata availability determined.
- [x] Clean/noisy linkage and noise-label claims assessed.
- [x] Oracle-leakage risks and access policy documented.
- [x] `data/MANIFEST.json` records provenance, hashes, searches, and readiness.
- [x] Final `scd_ready: false` verdict contains a concrete reason.
- [x] Both true/false follow-up branches documented.
- [x] `codinglog.md` updated.

T01 is complete with a negative readiness result. This is a valid completion of the audit gate, not a failed implementation task.
