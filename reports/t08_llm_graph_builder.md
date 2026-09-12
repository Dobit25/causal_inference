# T08 Public-Story-Only LLM Graph Builder Report

## Verdict

```yaml
t08_complete: true
implementation_ready: true
llm_graph_builder_ready: true
public_development_inputs_valid: 8/8
development_graphs_generated: 8/8
holdout_accessed: false
blocker: null
```

T08 is complete on the frozen graph-development cohort. Eight live OpenAI responses produced eight valid canonical `G_LLM` DAGs; every scene passed on its first attempt. The raw prompts, complete provider responses, request metadata, and outputs are retained below ignored `results/raw/`, while the versioned audit retains hashes and non-secret metadata.

## Frozen live backend

- provider/endpoint: OpenAI Responses API, `/v1/responses`;
- immutable model snapshot: `gpt-5.4-nano-2026-03-17`;
- SDK: `openai==3.6.0`;
- inference: strict JSON Schema, `reasoning_effort=none`, `temperature=0`, `max_output_tokens=6000`;
- transport: `service_tier=default`, `store=false`, timeout 120 seconds, at most two SDK transport retries;
- validation: at most two model retries, with no graph repair or fallback;
- credential: `OPENAI_API_KEY` loaded from ignored `.env`; no secret or reusable key fingerprint is versioned.

## Evidence boundary

The builder receives a dedicated `PublicLLMGraphInput` containing only:

- the public `story.md` text;
- the public variable name, type, and semantic mapping derived from `schema.json`;
- hashes of those two public inputs.

It cannot receive observational parquet data, tasks/queries, gold answers, grading files, Oracle graphs, SCD graphs, or holdout scenes. Tests place poison markers in each forbidden artifact and prove that neither the input view nor rendered prompt contains them. An architecture test also rejects Oracle, SCD, task, data, and grading dependencies in the graph-builder module.

## Prompt and response contract

One model call constructs one scene-level graph; it is not conditioned on a downstream task. The frozen prompt asks for every unordered node pair exactly once and requires one of:

- `left_causes_right`;
- `right_causes_left`;
- `no_direct_edge`.

Each decision includes confidence and a short public-story rationale. The strict parser rejects Markdown wrappers, unknown fields/nodes, missing or duplicate pairs, reversed canonical pairs, invalid confidences, self-loops, and directed cycles. Invalid output is retried at most twice with the validator error and previous response. There is no heuristic repair and no fallback graph after exhaustion.

Valid output is passed through the T06 LLM adapter and emitted as a canonical `fourgraph.graph.v1` DAG with complete edge/non-edge audit records, input hashes, model identity, retry count, structure hash, and artifact hash. Raw prompts/responses are kept outside Git; the versioned manifest stores their hashes and call metadata.

## Reproducibility and replay

The replay backend requires an exact `(scene_id, attempt, prompt_sha256)` match and preserves the raw prompt, full provider-response JSON, provider/model/version, request ID, fingerprint, token counts, tier, SDK version, and latency. It also rejects any scene set other than the exact eight frozen development IDs. Replay therefore regenerates canonical graph artifacts without another paid call while detecting prompt drift or accidental holdout records.

Reproduce the completed development graph set without another paid call:

```powershell
conda run -n cau python scripts/audit_causalds_t08.py <extracted-causalds-source-root> --replay-log results/raw/t08_llm_graph/gpt-5.4-nano-2026-03-17_dev.jsonl
conda run -n cau python scripts/audit_causalds_t08.py <extracted-causalds-source-root> --replay-log results/raw/t08_llm_graph/gpt-5.4-nano-2026-03-17_dev.jsonl --check
```

## Live result

The deterministic audit validates all eight T04-frozen public inputs and records their story, schema, variable-map, and initial-prompt hashes. The run used 8 API calls with 7,005 input tokens and 2,564 output tokens (9,569 total); median observed call latency was 3,117.5 ms. All eight calls used the default tier and required no validation retry. The emitted graphs contain 3–7 nodes and 2–7 directed edges.

`data/manifests/t08_dev_graphs.jsonl` contains the eight canonical graph artifacts. `data/manifests/t08_llm_graph_builder_audit.json` records `complete_llm_graph_builder_ready`, 8/8 successes, zero holdout access, the raw-log hash, and the development graph-set hash. A write followed by `--check` reproduced both versioned artifacts byte-for-byte.

T08 does not evaluate graph accuracy, downstream causal answers, the Gemma reasoner, Hybrid orientation, or holdout scenes. Those are later tasks; successful schema-valid graph construction is a readiness result, not evidence that the learned graphs are scientifically accurate.
