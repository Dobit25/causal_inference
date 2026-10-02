# Phase D execution plumbing — readiness checkpoint

Trạng thái: **READY FOR SEPARATE LIVE AUTHORIZATION ONLY**

Tài liệu này chỉ xác nhận execution plumbing offline. Nó không phải kết quả khoa học và không cấp quyền chạy Phase D.

## Phạm vi đã khóa

- Cohort: đúng 30 scene method-development `P1V3SD000`–`P1V3SD029` từ exact identity manifest; các role calibration/validation/holdout bị loại trước khi lập job.
- Planned fits: `6.150` = 30 Single-BOSS + 6.000 Bootstrap-BOSS (200/scene) + 30 PC + 30 MMPC + 30 FGES + 30 GFCI.
- Bootstrap candidates C1–C6 được giữ trong protocol để aggregate/report sau này; 200 bootstrap repetitions là một statistical method-level input, không bị nhân thành 200 method votes.
- Concurrency mặc định: `1`; retry mặc định: `0`; resume chỉ nhận execution identity còn thiếu.
- Oracle, holdout và semantic API bị chặn trong execution config.

## Plumbing

- `scripts/run_p1v3_statistical_ensemble.py`: lập execution identity, dry-run/execute/resume/audit, idempotency và hash dependency.
- `scripts/adapters/tetrad_adapter.py`: Python → pinned Tetrad JAR cho BOSS/PC/FGES/GFCI; GFCI chỉ chuẩn hóa adjacency PAG, không suy diễn direction.
- `scripts/adapters/mmpc_adapter.py`: Python → R subprocess → `bnlearn::mmpc`; kiểm tra version, node universe và fail-closed.
- `scripts/materialize_p1v3_development.py`: chỉ materialize đúng role method-development khi live authorization được cấp; không ghi Oracle artifact.
- `scripts/audit_p1v3_statistical_execution.py`: kiểm tra completeness, identity, raw/normalized hash và execution boundary.

Mỗi fit khi chạy thật sẽ có raw output, normalized graph, run/config/seed/input/output hashes, runtime/status và error artifact nếu thất bại. Cùng `(scene, algorithm, candidate, seed, config_hash)` luôn có một `run_id` duy nhất.

## Kiểm định offline đã đạt

| Kiểm định | Kết quả |
|---|---:|
| Python compile | PASS |
| Adapter fixture E2E: BOSS, PC, MMPC, FGES, GFCI | PASS |
| Graph schema rejects self-loop/unknown node | PASS |
| Tetrad wrong-hash fail-closed | PASS |
| R/bnlearn missing-runtime fail-closed | PASS |
| Job identity/reproducibility | PASS |
| Planned jobs | `6.150` |
| Dry-run actual fits | `0` |
| Dry-run materialized study scenes | `0` |
| Oracle/holdout access | `0/0` |
| Semantic API calls | `0` |
| Audit after dry-run | `PASS_DRY_RUN_AUDIT` |

Các kiểm định chạy trong `tests/test_p1v3_statistical_execution.py` với Python 3.10.20. Plan và audit được sinh tại:

- `data/manifests/p1v3_statistical_execution_plan.json`
- `data/manifests/p1v3_statistical_execution_audit.json`

## Quyết định freeze

Phase D execution plumbing đã sẵn sàng về mặt kỹ thuật, nhưng live execution vẫn fail-closed vì:

```yaml
authorization:
  execute: false
```

Do đó chưa có 6.150 fits, chưa có scene study materialized và chưa có kết quả graph. Bước tiếp theo hợp lệ là checkpoint cấp quyền live riêng; không được coi readiness này là authorization.
