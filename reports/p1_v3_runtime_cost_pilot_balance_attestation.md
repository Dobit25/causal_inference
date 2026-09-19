# P1-v3 runtime/cost pilot balance attestation

The user read the `causal_builder` project limits UI on 2026-09-19 and attested current spend USD 5.52 against a USD 15.00 project limit. Exact arithmetic leaves USD 9.48, or 6.32 times the frozen USD 1.50 pilot cap. No prepaid credits are used; the displayed reset was 11 days away, represented as 2026-09-30.

The budget gate passes, but the platform hard limit is not enforced. The frozen internal pre-call budget controller is therefore mandatory, concurrent project spend remains a risk, and the balance must be rechecked if execution occurs after the reset or more than 24 hours after this attestation.

This amendment records technical budget readiness only. It does not contain an explicit pilot-execution order and cannot authorize itself. No model call, token, observation, Bootstrap/BOSS run, successor scene or holdout access occurred. The next action is a separate final GO/NO-GO checkpoint.
