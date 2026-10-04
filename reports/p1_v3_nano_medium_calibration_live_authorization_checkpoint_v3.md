# Nano-medium calibration live-authorization checkpoint v3

## Verdict

The checkpoint is **PASS and ready for explicit live authorization**. The
updated user attestation confirms that the `$18.00` project limit is enforced;
current reported spend is `$0.00`, with the project reset reported in 27 days.
No API key is stored in the attestation.

## Frozen dependencies

The checkpoint pins the calibration execution-control amendment, its audit, the
provider preflight, Nano snapshot `gpt-5.4-nano-2026-03-17`, reasoning effort
`medium`, and the frozen prompt/schema hashes. The runner-local hard stop is
`3,000,000` provider-reported total tokens per 07:00–07:00 window in
`Asia/Ho_Chi_Minh`; missing usage or a possible overshoot remains fail-closed.

## Execution boundary

Provider preflight: one non-study request, already completed successfully.
Study calibration calls: `0`; scenes materialized: `0`; Oracle, validation and
holdout access: `0`. This checkpoint does **not** authorize live execution.

After a separate explicit authorization, the only next scientific action is the
registered calibration look at 120 scenes. No validation, holdout, prompt
tuning or automatic phase transition is permitted.
