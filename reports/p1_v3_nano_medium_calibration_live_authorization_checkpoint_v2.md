# Nano-medium calibration live-authorization checkpoint v2

## Verdict

The checkpoint is **ready but not live-authorized**. The user-provided spend
attestation reports `$0.00 / $18.00` for project `causal_builder`, with a reset
in 27 days. The screenshot did not expose whether a hard project limit is
enforced, so that field remains `unknown` and is not inferred.

## Provider preflight

One non-study provider preflight used the frozen Nano-medium contract on a
7-node/21-pair fixture. The provider completed the request without truncation:

- model: `gpt-5.4-nano-2026-03-17`;
- reasoning effort: `medium`;
- input/output/reasoning/total: `1,274 / 1,392 / 640 / 2,666` tokens;
- request ID: `resp_0f893cb36b10c652016ac26b3da78487d0bbb4d52b1b7fe177`;
- estimated cost: `$0.0019948`;
- study scenes and study calls: `0`.

## Frozen control

The calibration runner retains the `3,000,000` provider-reported total-token
hard stop, the 07:00 `Asia/Ho_Chi_Minh` reset window, fail-closed missing usage,
no overshoot, idempotent ledger and no automatic phase/day resume.

## Boundary

This checkpoint did not materialize calibration scenes and did not access
Oracle, validation or holdout data. A separate explicit live authorization is
still required before the registered sequential calibration looks begin.
