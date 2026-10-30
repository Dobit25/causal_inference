# P1V4 validation look-160 Mini: watchdog retry and resume execution

The separately authorized retry of `P1V4SV475/ambiguous/P2` succeeded. The runner then completed all 562 remaining logical IDs in the original batch-2/3 scope. The execution scope therefore wrote 563 terminal records and brought the cache to 1,440/2,640 calls.

The external watchdog recorded six provider incidents without retrying them: five `APIConnectionError` records and one provider-side `InternalServerError` 520. These records remain in the immutable cache. They are not converted into abstentions, valid responses, or replacement calls.

Across all 1,440 cached calls, 1,245 responses are fully valid, 189 are pair-invalid, and six are provider errors. Provider-reported usage across response-bearing records is 2,136,299 total tokens. The current daily window used 1,427,176/3,000,000 tokens.

Oracle and holdout access remain zero. No response freeze, re-score, six-vote aggregation, closure, or metric calculation has occurred. An incident-disposition checkpoint is required before the remaining 1,200 calls or downstream analysis.
