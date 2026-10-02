# P1V3 public story-generation amendment

**Status:** `PASS — frozen`  
**Scope:** exactly `P1V3SD000–P1V3SD029`  
**API calls:** 0

## Replayed protocol

The existing T19 protocol was traceable and was replayed without redesign:

- Story generator: `src/fourgraph/p1_stories.py`.
- Source-scene reconstruction: `scripts/materialize_p1v3_development.py` using the frozen identity manifest and successor generator parameters.
- T19 story configuration: `configs/t19_p1_semantic_stories.yaml`.
- Aliases: seeded per scene with T19 master seed `1701` and the registered alias stream.
- Full: every true SCM edge receives a directional public clause.
- Partial: the registered lowest-SHA256-ranked half of true edges is directional; the remainder is symmetric.
- Unlisted pairs: no direct-connection statement.
- Ambiguous: not enabled for this successor method-development protocol; it remains explicitly disabled rather than silently added.

The SCM truth is used only inside the registered synthetic data-generation protocol to construct the public story. It is not persisted in the public story artifacts, not exposed to a model, and not used for scoring in this checkpoint.

## Freeze audit

- Scenes: **30/30**.
- Public artifacts: **60/60** (`full` + `partial` for each scene).
- Missing or duplicate records: **0**.
- Deterministic replay: PASS.
- Hash stability: PASS.
- Story-to-statistical-scene mapping: PASS.
- Leakage audit: PASS; no Oracle/CPDAG metadata, canonical `X000...` identifiers, gold labels, holdout data, or statistical outputs in public artifacts.
- Holdout stories/access: 0.
- Semantic API calls: 0.

The machine-readable input manifest is `data/manifests/p1v3_public_semantic_inputs_manifest.json`; its records contain artifact paths, content hashes, generator/config provenance, source commitments, identity metadata and leakage flags. The audit is `data/manifests/p1v3_public_story_generation_audit.json`.

## Frozen hashes

- Amendment config: `565A1AEB304106C58A73D9E0CCFDA6A1FEF6EC922225710AAA258B9BA4DAAD16`
- T19 story config: `D718E142974BABE425FAB19CBD273DC8484A8845A99E9ADEAD651F86733009E7`
- Story generator: `73915B96BBD7E690FB95E6C7D8CDAB7B88C815655255FEC54E31597BED6A1F81`
- Source generator: `E0F9383CD96941033402A0F8F97C26480BF44BDBFB97DE46AACAB3C0A7A9693F`
- Identity manifest: `5957797094EE415FA898D82E3C5D660A1AB9323077BD1DA5E1A79D78F75E63F3`
- Public-input manifest: `352C437599A25B7875464E68922857096942F2993EA58B973391C9C81DD17A34`

This amendment is now frozen. It does not authorize Phase E; the next step is a new, separate Phase E authorization using this manifest.
