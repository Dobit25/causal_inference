# Look 120 semantic execution incident

Execution stopped fail-closed before producing a usable semantic response.
The first provider attempt for `P1V3SC241/full/P1` reported 2,262 total
tokens, while the runner had reserved 1,726 from the diagnostic preflight.
The token ledger therefore rejected the commit. The response body and request
metadata were not persisted, so this attempt is a missing semantic response,
not a valid observation.

- Planned calls: 2,640
- Provider attempts: 1
- Usable semantic responses: 0
- Retry: none
- Tokens observed in ledger: 2,262
- Oracle/holdout access: 0
- Statistical reruns: 0

The existing raw cache and append-only token ledger are retained. No response
was substituted and no further API call was made. A separate runner-remediation
amendment is required before resuming; it must account for the observed usage
and preserve the registered retry/idempotency policy.
