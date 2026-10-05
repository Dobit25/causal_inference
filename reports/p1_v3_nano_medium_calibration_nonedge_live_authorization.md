# Look 120 successor live authorization

This checkpoint is the successor authorization after the public-story non-edge
amendment. It pins the exact 80-scene/240-pair diagnostic manifest and keeps
the previously registered 2,640-call workload unchanged. No semantic request
was made while creating this checkpoint.

## Workload

- 1,440 certification calls: 120 scenes × full/partial × six prompts.
- 720 ambiguous diagnostic calls: 120 scenes × six prompts.
- 480 public-story non-edge diagnostic calls: 80 scenes × six prompts; each
  whole-graph request contains the three frozen pair IDs for that scene.
- Total: **2,640 logical calls**, concurrency 1.

## Frozen safety rules

The model, prompt, schema, reasoning effort, token hard stop, retry policy,
cache identity and output contract are unchanged. Non-edge pairs come only from
the complement of direct pair mentions in the frozen public full story. Oracle,
SCM, statistical parent graphs, validation and holdout data are not used for
pair selection or model input. Missing provider usage or a token-limit risk
fails closed.

## Pinned artifacts

- Authorization config SHA-256: `55BEE4D5B8ADE427B2919882526ED0BC1DD4DE67DDA4988CAD9D4E95EB877FB8`
- Authorization audit: `data/manifests/p1_v3_nano_medium_calibration_nonedge_live_authorization_audit.json`
- Pair manifest SHA-256: `1181D674CC4209CBF3619123045FB04A08512B959416A9F13F25766B45A638B9`
- Amendment config SHA-256: `81AB1F92D533CBFF78FBDF7861A8D70118E7791AB727F7AEBA970B71FB5B8E8A`
- Amendment audit SHA-256: `A271D8D8C7BCB16E7EB759111F22915244B6CA1308BC046967E64C3FA944DC6D`

Status: `PASS_LIVE_AUTHORIZED`; semantic API calls before authorization: `0`.
The next permitted action is look-120 semantic execution, followed by a stop
before any later look, calibration decision, downstream reasoner or holdout.
