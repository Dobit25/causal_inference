# P1V4 validation look-160 Mini batches 2–3: transport incident

The run recorded 184 of the 960 newly authorized logical calls, bringing the immutable cache to 664/2,640 calls. The next request, `P1V4SV303/ambiguous/P5`, remained in transport without a recordable response, request ID, or provider usage for an extended period. The process was stopped to prevent an indefinite unaudited run.

No retry was made because transport retries require separate explicit authorization. The 664 completed responses and their token ledger were preserved byte-for-byte. Exactly 776 calls from the authorized slice remain pending, beginning with the incident logical call.

For the 184 newly recorded calls, 164 responses were fully valid and 20 contained at least one pair-level validation failure. There were 1,231 valid and 61 invalid pair judgments. Provider-reported usage was 276,701 total tokens. Oracle and holdout access remained zero; no metric or closure calculation occurred.

The next action is a narrow transport-retry authorization for the single incident call, followed by cache-resume of the remaining 775 calls in the already authorized batch-2/3 identity set.
