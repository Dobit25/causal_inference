# Nano-medium calibration execution-control amendment

## Frozen hard stop

The calibration runner has a strict, runner-local ceiling of **3,000,000
provider-reported total tokens per budget window**. A window runs from 07:00 to
07:00 the following day in `Asia/Ho_Chi_Minh`. The runner reserves an
upper-bound token amount before each request, so it refuses a request that could
overshoot the ceiling. Missing or inconsistent provider usage is a fail-closed
halt, not a zero-token result.

The limit applies to this calibration runner only; it cannot observe unrelated
API processes using the same OpenAI project. Automatic next-day or next-phase
resume is disabled.

## Ledger and idempotency

The append-only ledger records window, logical identity, attempt, input tokens,
output tokens, reasoning tokens, total tokens, cost and remaining budget after
each committed response. A retry is allowed only after an explicit release of
the failed attempt and receives a new attempt identity. A completed logical
call cannot be run again. Dangling reservations, duplicate identities and
provider usage without `total_tokens` halt the run.

The frozen runner is `scripts/run_p1_v3_nano_medium_calibration.py` and its
control module is `src/fourgraph/nano_calibration_control.py`; both hashes are
recorded in the amendment manifest and audit. `--dry-run`, `--check`, and
`--resume` are read-only plumbing modes. No live provider adapter is enabled by
this amendment.

## Offline verification

The controller tests exact boundary behavior, the 07:00 Vietnam-time reset,
missing usage, retry/duplicate prevention and a zero-call dry run. No provider
adapter is enabled by this amendment.

## Next authorization requirements

Before live calibration, obtain a fresh spend/limit attestation, run a provider
preflight using the exact Nano prompt/schema hashes, and request a separate
live authorization. This amendment itself has made no API call, materialized
no scene and accessed no Oracle, validation or holdout data.
