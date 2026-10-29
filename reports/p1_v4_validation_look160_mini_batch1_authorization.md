# P1V4 validation look 160 — Mini preflight and batch-1 authorization

The single synthetic 7-node / 21-pair Mini-medium provider preflight passed. It used 1,047 input tokens, 971 output tokens (290 reasoning tokens), and 2,018 total tokens; provider request ID `req_52e0842e3535475989292475ce6cad3d` completed without truncation. No study scene, Oracle, or holdout was accessed.

The original semantic plan v1 is retained as incident evidence and superseded before any study call because its `story_content_sha256` represented the artifact rather than the exact public story text. Plan v2 corrects only that deterministic content-hash contract; model, prompt, schema, stories, pair pools, parent graphs, logical IDs, and scientific policy are unchanged. Dry-run passed for all 2,640 logical calls.

Batch 1 authorizes exactly the first 480 frozen logical IDs. The project limit is a hard stop at USD 18.00; the runner also uses provider-reported usage with a 3,000,000-token daily window resetting at 07:00 Asia/Ho_Chi_Minh. It writes a per-call ledger and batch audit. Transport or validation retry is forbidden without separate authorization. At this checkpoint, 0/480 study calls have run; Oracle and holdout access remain zero.
