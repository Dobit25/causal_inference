# T21 v3-B — Edge-Selective offline conformance

T21 v3-B triển khai contract partial graph, production/reference solvers và Meek R1–R4 hoàn toàn offline.

- Valid synthetic cases: 180/180.
- Threshold decisions production/reference khớp: 3600/3600.
- Invalid fixtures bị từ chối đúng mã lỗi: 40/40.
- Closure-propagated direction observations: 579.
- Off-grid joint-selection cycle probes: 6/6.

Không gọi API, không sinh validation cohort, không đọc P1 development/holdout và chưa chọn threshold.
