# P1V4 validation look-160 — Mini batch 4 execution

Status: **INCOMPLETE_OR_PROVIDER_INCIDENT**. The explicitly authorized next 480 logical IDs were visited exactly once. The effective cache now contains 1,920/2,640 logical records; 720 calls remain pending. No automatic retry was performed.

## Batch result

| Status | Count |
|---|---:|
| `completed_valid` | 417 |
| `completed_pair_invalid` | 56 |
| `provider_error` | 7 |
| Total | 480 |

The seven provider incidents were recorded as transport/watchdog failures and remain unresolved. They are not silently converted to abstentions or replaced by new responses.

Provider-reported usage for this batch was 324,293 input, 391,013 output, 265,083 reasoning and 715,306 total tokens. The cumulative execution audit reports 2,860,383 total tokens; Oracle and holdout access remain zero.

The post-run dry-run is deterministic: 1,920 records are cached, 720 logical IDs remain pending, and no API call is made by the dry-run. No response freeze, re-score, six-vote aggregation, closure or metric calculation was performed.
