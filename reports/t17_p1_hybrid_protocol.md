# T17 — Frozen P1 Hybrid protocol

## Trạng thái

T17 hoàn tất ở mức thiết kế và đăng ký trước. Không scene nào được sinh, không API nào được gọi, H2 chưa được triển khai và P1 holdout chưa được truy cập. Bản `configs/p1_fresh.yaml` cũ được giữ nguyên làm lịch sử; `configs/p1_hybrid_v1.yaml` là protocol kế nhiệm có version riêng.

Quyền tiếp theo chỉ là **T18 — xây fresh-SCM generator, inventory và deterministic split**. T18 không được gọi LLM hay triển khai H2.

## Câu hỏi và claim chính

P1 hỏi liệu semantic orientation có thể cải thiện adjustment/control decisions so với arbitrary CPDAG projection khi mọi hướng được kiểm tra bằng ràng buộc toàn graph, đồng thời giữ uncertainty khi semantics yếu hoặc xung đột.

Claim chính được đăng ký:

> Constraint-aware semantic augmentation cải thiện official downstream accuracy so với deterministic CPDAG projection mà không tạo graph không hợp lệ.

Claim selective:

> Preregistered abstention đánh đổi coverage để giảm confident error khi semantic evidence yếu dần.

Không được claim H2 là hybrid tối ưu toàn cục, text chứng minh causal truth, hoặc P1 đủ cho autonomous real-world decision making.

## Fresh homogeneous substrate

- 100 DAG/SCM mới: `P1S000`–`P1S099`.
- Dev 20, holdout 80; exact IDs được tạo và khóa tại T18 bằng inventory chỉ dùng Oracle structural/task properties, trước method development.
- 5–7 continuous observed nodes, connected DAG, không latent confounding. Node counts được phân bổ 34/33/33; năm primary motifs chain/fork/collider/mediator/diamond có đúng 20 scene mỗi loại (một graph có thể chứa thêm motif khác).
- Linear acyclic SCM với independent non-Gaussian errors; trọng số có độ lớn 0.5–2.0 và dấu cân bằng.
- Mỗi scene dùng một trong Laplace, logistic hoặc Student-t(df=5), phân bổ 34/33/33 và chuẩn hóa variance.
- Primary `N=2000`; nested sensitivity `N=500/10000` trên 20 scenes.
- Eligibility yêu cầu Oracle CPDAG có ít nhất hai unresolved edges. Không được chọn scene dựa trên output của SCD, LLM, Hybrid hoặc reasoner.

Generator lấy một topological order seeded, lấy đúng số cạnh từ các forward pairs rồi rejection-sample deterministically cho tới khi graph connected, có assigned motif, có ít nhất hai Oracle-CPDAG unresolved edges và có query thuộc assigned stratum. Mỗi scene có trần 10.000 attempts; chạm trần làm T18 fail đóng thay vì đổi tiêu chí hoặc thay scene thủ công.

Mỗi scene có đúng năm task cố định trên cùng treatment/outcome/candidate set. Bốn query strata có 25 scenes mỗi loại: valid empty, một minimal non-empty, nhiều minimal sets và không có valid adjustment set. Query được chọn từ toàn bộ ordered treatment/outcome pairs theo seeded order; không có pair phù hợp thì graph candidate bị loại. Production và independent solver phải khớp 500/500 targets.

## Controlled semantic evidence

Cùng một SCM/data/query có ba story variants:

| Variant | Directional evidence | Vai trò |
|---|---:|---|
| `full` | 100% true edges | Upper-bound semantic condition |
| `partial` | 50% seeded true edges | Incomplete domain knowledge |
| `ambiguous` | 0%; association-only language | Abstention stress test |

Với số cạnh lẻ, `partial` dùng đúng `round_half_up(|E|/2)` cạnh được chọn bằng scene seed; vì vậy “50%” là dose gần nhất có quy tắc, không phải lựa chọn thủ công.

Alias được lấy từ role-balanced lexicon độc lập với vị trí graph; reasoner không thấy alias/story. Main P1 không đưa câu causal sai; conflicting/misleading semantics là robustness extension sau này.

Story được sinh bằng deterministic templates từ ground-truth DAG để tạo stimulus có kiểm soát. Việc generator dùng truth phải tách khỏi evidence boundary: semantic builder chỉ nhận story public tương ứng, không nhận DAG hoặc generator metadata.

## Statistical và semantic components

Primary SCD là BOSS + BasisFunctionBicScore theo config T05, nhận standardized anonymous observations và trả CPDAG. Dor–Tarsi lexicographic extension là arbitrary projection baseline. DirectLiNGAM khớp assumptions của fresh SCM nhưng chỉ là structural sensitivity, không đi qua downstream reasoner trong P1 v1.

Semantic backend giữ snapshot GPT-5.4 Nano của P0. Mỗi scene/story variant chỉ gọi một lần để tạo preference artifact cho mọi unresolved edge. H1, H2-Forced và H2-Selective dùng chung artifact, nhờ vậy khác biệt giữa chúng đến từ integration rule thay vì API nondeterminism.

Standalone `G_LLM_FULL` dùng full story và config T08. Fixed reasoner giữ GPT-5.4 Mini, prompt v3, canonical edge-list `X000...`, medium effort và provenance/story blindness như P0.

## H1, H2-Forced và H2-Selective

H1 chọn argmax cho từng cạnh độc lập và không repair toàn cục. Một tổ hợp ngoài equivalence class là terminal graph failure.

H2-Forced xét mọi consistent DAG extension của parent CPDAG và tối đa hóa tổng log-probability của semantic edge preferences. Nó phải giữ skeleton, compelled directions, acyclicity và unshielded-collider equivalence; canonical lexicographic serialization phá tie deterministically.

H2-Selective dùng H2-Forced làm candidate. Nếu global best/second-best score margin quá nhỏ hoặc solver phải đi ngược semantic preferences quá nhiều, nó trả lại nguyên raw CPDAG. P1 v1 abstain toàn graph; partial-edge PDAG chưa được đưa vào contract.

Threshold được chọn trên 20 development scenes từ grid đã đăng ký. Candidate phải graph-valid 100% và orientation precision ít nhất 95%; sau đó tối đa coverage với tie-breakers cố định. Không candidate nào đạt thì phải amend protocol và vẫn ở pre-holdout. Downstream ranking và mọi holdout evidence bị cấm trong threshold selection.

## Evaluation matrix

Mỗi scene có 12 structural graph views:

- Raw SCD, projected SCD, DirectLiNGAM và grading-only Oracle.
- Full-story LLM và full-story H1.
- H2-Forced ở full/partial/ambiguous.
- H2-Selective ở full/partial/ambiguous.

DirectLiNGAM là structural-only, nên 11 views/scene đi vào năm downstream tasks:

- 1,200 structural records.
- 5,500 downstream records toàn P1.
- 1,100 development và 4,400 holdout downstream records.

Canonical cache loại graph-source label khỏi identity. Trước live development phải có cost forecast và authorization riêng; T17 không cấp quyền gọi model.

## Hypotheses và metrics

Hai primary hypotheses:

1. H2-Forced-Full có official downstream accuracy cao hơn deterministic projection.
2. H2-Forced có invalid-graph rate thấp hơn H1 trên cùng full semantic preferences.

Key secondary hypotheses kiểm tra selective confident-error, ordered full > partial > ambiguous benefit và direction recovery. Chiều so sánh LLM–H2 và DirectLiNGAM–semantic methods không được đăng ký trước.

Structural metrics gồm skeleton/direction/SHD phù hợp graph type, validity, completion, orientation precision/coverage, net orientation utility, solver conflict và abstention. Downstream metrics gồm official accuracy, uncertainty-aware correctness, response coverage, selective error, confident wrong và failure rate. Token/cost/latency/retry tiếp tục được audit.

Scene là independent unit. Mọi condition/variant/sample size được giữ paired trong scene. Dùng equal-weight scene macro, 5,000 paired scene-cluster bootstrap với seed 17015, percentile 95% CI, two-sided tests và BH correction trong từng declared metric family. Failure không bị xóa; CPDAG abstention không phải missing.

## Freeze boundary và các bước kế tiếp

T17 khóa protocol nhưng không khóa exact 20/80 IDs hoặc abstention thresholds vì cả hai chỉ tồn tại sau T18 inventory và T21 development selection. Nó khóa trước thuật toán sinh/chọn chúng, candidate grid và forbidden inputs.

Chuỗi tiếp theo:

```text
T18 generator + 100-scene inventory + exact split freeze
→ T19 deterministic semantic-story variants and audit
→ T20 offline H2 implementation/conformance
→ T21 development-only model calls and threshold selection
→ T22 P1 holdout execution freeze
→ T23 one-time holdout
→ T24 paired analysis
```

Mọi thay đổi protocol sau T17 phải tạo version mới và audit rõ lý do; không sửa `p1_hybrid_v1` tại chỗ sau khi T18 bắt đầu.
