# P1V4 independent validation look-160 response freeze and re-score

Status: **PASS**.

- Effective responses: **2,640**
- Provider errors replaced by immutable overlays: **28/28**
- Pair records: **18,252**
- Six-vote groups: **3,042**
- Valid pair records: **17,053/18,252**
- Agreement: `{'HIGH': 168, 'MEDIUM': 7, 'UNCERTAIN': 1390, 'VERY_HIGH': 1477}`
- Completeness: `{'COMPLETE': 2153, 'INCOMPLETE': 241, 'NEAR_COMPLETE': 648}`
- Preliminary automatic-candidate rates: `{'full': {'automatic_candidates': 1068, 'review_candidates': 5, 'total_groups': 1104, 'automatic_candidate_rate': 0.9673913, 'abstention_rate_before_parent_filtering': 0.0326087}, 'partial': {'automatic_candidates': 577, 'review_candidates': 2, 'total_groups': 1104, 'automatic_candidate_rate': 0.52264493, 'abstention_rate_before_parent_filtering': 0.47735507}, 'ambiguous': {'automatic_candidates': 0, 'review_candidates': 0, 'total_groups': 834, 'automatic_candidate_rate': 0.0, 'abstention_rate_before_parent_filtering': 1.0}}`
- Production/reference validator agreement: **100%**
- Byte-for-byte replay: verified separately with `--check`
- API/Oracle/holdout/precision/closure: **not run**

Preliminary coverage is the fraction of shared semantic pair groups marked automatic before condition-specific parent filtering; it is not Oracle-scored coverage.
