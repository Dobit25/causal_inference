# P1V4 validation look-160 provider-incident overlay disposition

Status: **PASS_OVERLAY_DISPOSITION**. The effective view replaces exactly six raw `provider_error` records with their separately hashed, one-attempt retry-overlay responses. The original raw records are unchanged. The effective view has 1,440 records: 1,250 fully valid, 190 pair-invalid and zero unresolved provider-error records. This checkpoint performs no re-score, agreement aggregation, Oracle access, metric calculation or new API call.
