# P1V4 validation look-160 — batch-4 provider-error disposition

Status: **PASS_PROVIDER_ERROR_DISPOSITION**.

Exactly seven new provider errors from batch 4 were classified as missing semantic responses: six transport connection errors and one transport timeout. The raw records remain immutable. No retry, API call, Oracle access, holdout access, re-score or metric calculation occurred in this disposition checkpoint.

The effective cache remains 1,920/2,640 logical records, with 720 calls pending. The seven records are eligible for a separately authorized retry decision; they are not treated as valid semantic judgments or as pair-level abstentions.
