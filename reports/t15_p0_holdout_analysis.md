# T15 — Phân tích P0 holdout

## Trạng thái

T15 hoàn tất hoàn toàn offline từ các artifact T14 đã seal. Không có API call, không rerun failure, không sửa graph/reasoner và không trộn supplementary vào downstream primary.

## Graph quality trên 25 scenes

| Condition | Complete | Skeleton F1 | Directed F1 | CPDAG state SHD | Unresolved rate |
|---|---:|---:|---:|---:|---:|
| `G_LLM` | 25/25 | 0.982 | 0.949 | — | — |
| `G_SCD_RAW` | 25/25 | 0.959 | — | 0.160 | 0.728 |
| `G_SCD_PROJECTED` | 25/25 | 0.959 | 0.296 | — | — |
| `G_HYBRID` | 23/25 | 0.964 | 0.918 | — | — |
| `G_ORACLE` | 25/25 | 1.000 | 1.000 | — | — |

Hai Hybrid failures được giữ là unavailable cho structural metrics; không impute.

## Downstream trên 20 primary scenes

| Condition | Oracle-answer accuracy | Uncertainty-aware | Answered | Graph/reasoner failures |
|---|---:|---:|---:|---:|
| `G_LLM` | 0.820 | 0.910 | 100/100 | 0/100 |
| `G_SCD_RAW` | 0.080 | 0.940 | 98/100 | 2/100 |
| `G_SCD_PROJECTED` | 0.110 | 0.980 | 100/100 | 0/100 |
| `G_HYBRID` | 0.710 | 0.910 | 95/100 | 5/100 |
| `G_ORACLE` | 0.930 | 0.940 | 100/100 | 0/100 |

Failure records được tính incorrect theo T13. Raw SCD có thể sai official Oracle answer nhưng đúng theo conservative CPDAG uncertainty. Metric uncertainty-aware đo reasoner có trả lời phù hợp với graph được cấp hay không, không phải graph đó đúng ground truth hay không.

## Các contrast chính

| Metric | Left − right | Effect | 95% CI | BH p |
|---|---|---:|---:|---:|
| `oracle_answer_accuracy` | `G_LLM` − `G_ORACLE` | -0.110 | [-0.230, -0.020] | 0.0275 |
| `oracle_answer_accuracy` | `G_SCD_RAW` − `G_SCD_PROJECTED` | -0.030 | [-0.060, 0.000] | 0.0747 |
| `oracle_answer_accuracy` | `G_SCD_RAW` − `G_ORACLE` | -0.850 | [-0.960, -0.710] | 0.0007 |
| `oracle_answer_accuracy` | `G_SCD_PROJECTED` − `G_HYBRID` | -0.600 | [-0.790, -0.390] | 0.0007 |
| `oracle_answer_accuracy` | `G_SCD_PROJECTED` − `G_ORACLE` | -0.820 | [-0.930, -0.680] | 0.0007 |
| `oracle_answer_accuracy` | `G_HYBRID` − `G_ORACLE` | -0.220 | [-0.390, -0.060] | 0.0046 |
| `uncertainty_aware_correctness` | `G_LLM` − `G_ORACLE` | -0.030 | [-0.080, 0.000] | 0.4992 |
| `uncertainty_aware_correctness` | `G_SCD_RAW` − `G_SCD_PROJECTED` | -0.040 | [-0.110, 0.010] | 0.4992 |
| `uncertainty_aware_correctness` | `G_SCD_RAW` − `G_ORACLE` | -0.000 | [-0.080, 0.070] | 1.0000 |
| `uncertainty_aware_correctness` | `G_SCD_PROJECTED` − `G_HYBRID` | 0.070 | [-0.010, 0.190] | 0.4972 |
| `uncertainty_aware_correctness` | `G_SCD_PROJECTED` − `G_ORACLE` | 0.040 | [0.000, 0.090] | 0.4972 |
| `uncertainty_aware_correctness` | `G_HYBRID` − `G_ORACLE` | -0.030 | [-0.150, 0.050] | 0.8513 |

## Diễn giải outcome A–D

- A: ranking skeleton và directed quality được báo riêng; không ép raw CPDAG vào DAG metric. Trên 23 Hybrid graphs thành công, semantic orientation đúng 52/54 cạnh unresolved có thể đánh giá, so với 5/54 của deterministic projection; hai terminal failures vẫn nằm ngoài tỷ lệ cạnh này.
- B: hai scorer downstream được xem là co-equal. Ranking official là G_ORACLE, G_LLM, G_HYBRID, G_SCD_PROJECTED, G_SCD_RAW; ranking uncertainty-aware là G_SCD_PROJECTED, G_ORACLE, G_SCD_RAW, G_HYBRID, G_LLM.
- C: Spearman giữa condition-level skeleton F1 và official downstream là 0.9746794345; đây là mô tả với chỉ năm conditions, không phải bằng chứng nhân quả.
- D: Oracle còn sai 7/100 official tasks và 6/100 uncertainty-aware tasks; graph đúng không tự bảo đảm reasoner đúng.

## Statistical contract

Primary effect là chênh lệch scene-macro có trọng số scene bằng nhau. CI percentile 95% dùng 5.000 paired scene-cluster bootstrap replicates, seed gốc 13015. Các kiểm định hai phía được BH-correct trong từng metric family. Exact McNemar ở cấp scene-task chỉ là sensitivity vì không mô hình hóa clustering.

## Giới hạn

P0 chỉ có 25 graph scenes và 20 primary downstream scenes. Hybrid có terminal failures, raw CPDAG và DAG không cùng loại direction metric, và kết quả chỉ áp dụng cho released heterogeneous CausalDS P0. SID/AID, perturbation và robustness chưa khả dụng trong phase này.
