# Look 120 semantic execution audit

The run stopped fail-closed after a provider connection incident. The batch
hard-stop interpretation was applied correctly: batches 0 and 1 completed at
796,245 and 816,957 tokens, both below 3,000,000. Batch 2 reached 178 usable
logical responses before `P1V3SC220/partial/P5` failed twice with
`APIConnectionError`. The registered transport retry ceiling was one, so no
third attempt was made.

- Planned: 2,640 logical calls
- Completed: 898 logical calls
- Provider attempts: 902 (including two historical runner incidents)
- Observed tokens including the historical carry-in: 2,012,585
- Committed cost: approximately `$1.7465`
- Oracle/holdout/statistical reruns: 0
- Phase E metrics: not calculated

The raw cache and append-only batch ledger remain available for resume. A third
attempt for the failed logical call requires a separate authorization or a
registered incident-handling amendment; it was not issued automatically.
