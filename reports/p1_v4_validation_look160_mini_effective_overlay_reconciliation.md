# P1V4 look-160 effective overlay reconciliation

Status: **PASS_EFFECTIVE_VIEW_RECONCILED**

This was an offline reconciliation. Raw provider-error records remain immutable; retry responses are applied only in the derived effective view.

- Raw terminal records: **1920/1920**
- Effective records: **1920/1920**
- Raw provider errors replaced by overlays: **13/13**
- Effective provider errors remaining: **0**
- Effective statuses: `{'completed_pair_invalid': 246, 'completed_valid': 1674}`
- Overlay statuses: `{'completed_pair_invalid': 1, 'completed_valid': 12}`
- Effective response SHA-256: `6FD42F1E0B64BCDE2A85040AB1853A519E02F222CE1089D1925C217FE1B9D6F7`
- Audit SHA-256: `F21A10208665390AA98285C5CE11E82F3808B06939F218C03F1BAD72BA7A05E7`
- Byte-for-byte replay: **PASS**
- API calls: **0**; Oracle/holdout: **0**; metrics/re-score: **not run**

Next gate: complete the remaining 720 logical calls under a separate authorization before response freeze.
