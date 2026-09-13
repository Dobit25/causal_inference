# T20 — H2 offline implementation and conformance

## Kết quả

T20 đã triển khai H2-Forced và H2-Selective rồi kiểm thử hoàn toàn bằng synthetic CPDAG/preference fixtures.

- Valid cases: 150/150 production/reference agreements.
- Invalid cases: 30/30 bị từ chối fail-closed với đúng error code.
- Selective decisions: 3000/3000 khớp reference.
- Local independent argmax invalid: 39 cases; H2-Forced vẫn trả consistent extension hợp lệ.
- Selective accept/abstain across the frozen grid: 1783/1217.

Mọi H2-Forced output giữ node/skeleton/compelled directions, acyclic và không tạo unshielded collider ngoài equivalence class. Selective accept trả exact Forced DAG; abstention trả parent CPDAG byte-equivalent.

## Evidence boundary

Suite không dùng P1 SCM, story, development hay holdout scene. T20 gọi 0 API, không chạy SCD/LLM/reasoner, không chạy H2 trên P1 và không chọn threshold. T21 development-only execution/selection là bước duy nhất được cấp quyền tiếp theo.
