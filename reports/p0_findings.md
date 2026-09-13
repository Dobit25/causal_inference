# T16 — Kết luận P0 và quyết định nghiên cứu

## Kết luận điều hành

P0 hoàn tất với quyết định **REFINE**. Kết quả đủ mạnh để tiếp tục nghiên cứu semantic–statistical Hybrid, nhưng chưa đủ để tuyên bố H1 là phương pháp tốt nhất hoặc triển khai P1 cũ mà không sửa thiết kế.

T16 không gọi API, không chạy lại failure, không sửa graph/score T14–T15 và không bắt đầu P1. Nó chỉ diễn giải các outcome A–D đã đăng ký và khóa phạm vi claim trước khi thiết kế phương pháp mới.

## Bằng chứng P0

### Graph quality trên 25 holdout scenes

| Condition | Skeleton F1 | Directed F1 | Completion |
|---|---:|---:|---:|
| `G_ORACLE` | 1.000 | 1.000 | 25/25 |
| `G_LLM` | 0.982 | 0.949 | 25/25 |
| `G_HYBRID` | 0.964 | 0.918 | 23/25 |
| `G_SCD_RAW` | 0.959 | không áp dụng | 25/25 |
| `G_SCD_PROJECTED` | 0.959 | 0.296 | 25/25 |

Trên 23 Hybrid graphs thành công, semantic orientation đúng 52/54 unresolved edges có thể đánh giá, trong khi deterministic projection đúng 5/54. Hybrid cao hơn projection 0.614 directed-F1, 95% CI [0.447, 0.767], BH-adjusted p=0.000600. LLM cao hơn Hybrid 0.027 nhưng CI [-0.055, 0.112] chứa 0.

Hai H1 failures, `scene_000281` và `scene_000699`, tạo semantic directions ngoài parent CPDAG equivalence class sau đủ ba attempts. Chúng được giữ nguyên, không fallback và không rerun chọn lọc.

### Downstream trên 20 primary holdout scenes

| Condition | Official Oracle-answer accuracy | Uncertainty-aware correctness |
|---|---:|---:|
| `G_ORACLE` | 0.930 | 0.940 |
| `G_LLM` | 0.820 | 0.910 |
| `G_HYBRID` | 0.710 | 0.910 |
| `G_SCD_PROJECTED` | 0.110 | 0.980 |
| `G_SCD_RAW` | 0.080 | 0.940 |

Hybrid cao hơn projection 0.600 official accuracy, 95% CI [0.390, 0.790], BH-adjusted p=0.000667. LLM cao hơn Hybrid 0.110 nhưng CI [-0.090, 0.320] chứa 0 và BH-adjusted p=0.275. Oracle cao hơn LLM 0.110 và Hybrid 0.220 sau BH correction.

Không có uncertainty-aware contrast nào còn significant sau BH. Metric này đo reasoner có suy luận nhất quán với graph được cấp hay không; nó không đo graph có đúng Oracle hay không. Projected SCD đạt 0.980 ở metric này nhưng chỉ 0.110 official accuracy, cho thấy reasoner thường tuân theo ngay cả một projection sai/arbitrary.

Oracle vẫn sai 7/100 official tasks. Vì vậy graph đúng là điều kiện hữu ích nhưng chưa đủ để bảo đảm downstream reasoner đúng hoàn toàn.

## Claims được P0 hỗ trợ

1. Semantic evidence có giá trị lớn trong việc định hướng các adjacency mà SCD để unresolved, so với lexicographic deterministic projection.
2. Cải thiện direction chuyển thành cải thiện rõ ràng trên adjustment/control answers so với projection.
3. H1 không được chứng minh tốt hơn standalone LLM downstream ở quy mô 20 primary scenes.
4. Pairwise semantic decisions có thể hợp lý cục bộ nhưng không hợp lệ toàn graph; global consistency là một yêu cầu phương pháp thực sự.
5. Preserving uncertainty và matching Oracle truth là hai mục tiêu khác nhau, cần hai scorer và cách diễn giải riêng.

## Claims P0 không hỗ trợ

- Hybrid H1 là phương pháp tốt nhất.
- Hybrid H1 vượt standalone LLM.
- CPDAG luôn tốt hơn một DAG hoặc ngược lại.
- Kết quả tổng quát sang graph lớn, latent confounding, dữ liệu thực tế hoặc domain high-stakes.
- Có thể bỏ qua hoặc chạy lại hai Hybrid failures mà không thay đổi estimand.

## Vì sao quyết định là REFINE?

Không chọn `GO` vì H1 còn 8% graph-level failure, không vượt LLM downstream và P1 cũ dùng DirectLiNGAM làm trọng tâm sẽ để lại quá ít unresolved CPDAG edges cho câu hỏi semantic orientation. Không chọn `STOP` vì Hybrid cải thiện rất lớn so với projection và failures chỉ ra một vấn đề phương pháp có thể giải quyết rõ ràng.

`REFINE` nghĩa là giữ fresh homogeneous substrate của P1 cũ nhưng thiết kế lại trọng tâm:

- CPDAG-producing SCD là đầu vào chính cho Hybrid.
- DirectLiNGAM là sensitivity comparator, không phải SCD duy nhất.
- H2 nhận semantic direction preferences nhưng dùng global constrained solver để tạo consistent extension.
- Khi semantic evidence yếu hoặc xung đột, H2 phải có preregistered abstention policy.
- Full, partial và ambiguous semantic evidence được can thiệp có kiểm soát trên cùng SCM.
- Đánh giá đồng thời accuracy, validity, completion, coverage và uncertainty preservation.

## Giới hạn P0

- Chỉ 25 graph scenes và 20 downstream scenes.
- Released CausalDS có heterogeneous mechanisms và graph nhỏ, story thường mô tả causal direction khá rõ.
- H1 edge attribution chỉ tính trên 23 graph thành công.
- Raw CPDAG và DAG không có cùng direction metric.
- Outcome E không khả dụng; F–G chưa thuộc clean P0.
- P0 là exploratory pilot có holdout discipline, không phải bằng chứng triển khai thực tế.

## Trạng thái và bước kế tiếp

P0 execution, analysis và findings đã hoàn tất. Bước duy nhất được cấp tiếp là **T17 — thiết kế và đăng ký P1 Hybrid protocol**. T17 chưa được phép sinh fresh scenes, gọi H2 API hoặc mở P1 holdout.

Kiểm tra tái lập:

```powershell
python scripts/freeze_t13_holdout_execution.py --check
python scripts/audit_t14_execution.py --check
python scripts/analyze_t15.py --check
python scripts/finalize_t16_p0.py --check
```
