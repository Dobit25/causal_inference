# T12 v2 — Design amendment trước model selection

## Quyết định

T12 v1 được giữ nguyên như `development_diagnostic_baseline` và không đủ điều kiện chạy holdout. Không file v1 nào bị ghi đè: config, 175 score records và audit vẫn giữ đúng các SHA-256 đã phát hành trong T12.

T11 vẫn cung cấp tín hiệu khoa học có ích: LLM DAG gần Oracle, SCD chủ yếu nhận ra adjacency nhưng để lại nhiều direction chưa xác định, còn Hybrid semantic orientation tốt hơn deterministic projection trên development. Tuy nhiên đây là mô tả từ tám scene nhỏ, story rõ và chưa phải holdout finding.

Ranking downstream T12 v1 không được diễn giải như ranking graph source. Oracle condition chỉ đạt 19/35, generic response contract cần nhiều retry, và các lần gọi độc lập còn chứa provider nondeterminism. T12 v1 vì vậy là chẩn đoán measurement instrument, không phải kết quả chính.

## Construct-validity sensitivity

Primary scoring tiếp tục dùng official CausalDS convention để bảo toàn benchmark comparability. Sensitivity mới dùng Pearl back-door criterion cho total effect:

- adjustment set không chứa descendant của treatment;
- kiểm tra d-separation trong graph bỏ các outgoing arrows của treatment;
- giới hạn enumeration 5 biến/100 sets giống giới hạn released implementation để so sánh công bằng.

Trên 7 primary development Oracle DAGs và 4 adjustment tasks, hai conventions đồng ý 22/28 targets và bất đồng 6/28: 3 `one_valid_adjustment_set`, 3 `n_valid_adjustment_sets`. `all_minimal` và minimal size không đổi trong panel này vì empty set vẫn là minimum ở các scene liên quan. `forbidden_controls_list` được ghi `not_applicable_construct_differs`, không bị ép vào một định nghĩa chuẩn không tương đương.

## Synthetic conformance suite

`t12_v2_synthetic_conformance.jsonl` chứa 150 cases được sinh từ exhaustive small-DAG/query pools với seed 1202:

- 30 cases cho mỗi task;
- 75 DAG answered;
- 40 CPDAG answered/invariant;
- 35 CPDAG undetermined;
- bao phủ chain, fork, collider, mediation, confounding, multiple/empty adjustment sets và forbidden descendants.

Generator không đọc CausalDS story, task file hoặc answer. Mỗi case chứa canonical graph, scene-free query, ID/type glossary, expected target, exact task-specific response và schema path. Artifact có thể sinh lại byte-for-byte bằng `scripts/build_t12_v2_conformance.py --check`.

## Response và cache contract

Generic `{schema_version,status,answer}` được thay trong v2 bằng năm JSON Schemas, mỗi schema chỉ cho phép đúng một task field: `adjust`, `adjustment_sets`, `k`, `n`, hoặc `forbidden`. Sentinel `undetermined` được suy thành status ở parser, nên model không phải đồng bộ hai field.

Canonical cache key gồm model version, prompt hash, stripped graph hash, scene-free query hash, glossary hash và decoding-config hash. Nó không nhận `graph_condition`. Hai sources tạo cùng canonical input bắt buộc dùng lại exact raw response; cache từ chối overwrite cùng key bằng response khác.

## Gemma conformance rerun

Gemma `gemma-4-31b-it` qua Google AI Studio được đăng ký làm candidate retest với `google-genai==2.21.0`, temperature 0. Các gate được chốt trước khi chạy: parse 100%, first-attempt schema compliance 95%, accuracy tổng/DAG/CPDAG-answered/CPDAG-undetermined 90%, và accuracy từng task 80%.

Lượt chạy hoàn tất 150/150 cases, replay từ cache tái sinh score records và audit byte-for-byte. Kết quả:

- parse success: 1.000;
- first-attempt schema compliance: 0.867;
- overall accuracy: 0.133;
- DAG answered: 0.107;
- CPDAG answered: 0.200;
- CPDAG undetermined: 0.114;
- task accuracy từ 0.033 đến 0.300.

Gemini constrained decoding lặp ký tự khi schema chứa nested array. Adapter vì vậy chỉ nới schema gửi provider cho `adjustment_sets`, trong khi schema chuẩn và parser cục bộ vẫn kiểm tra list-of-lists, canonical IDs và candidate membership. Thay đổi này là provider compatibility, không thay prompt hoặc target sau khi thấy accuracy.

Verdict: chỉ gate parse thành công; sáu gate còn lại thất bại. Candidate này không đủ điều kiện chạy 35 Oracle-development tasks và không đủ điều kiện holdout. T12 v1 và lượt conformance v2 đều được giữ như diagnostic evidence; chưa thay đổi T08–T10 và holdout chưa được truy cập.

## Trạng thái và bước kế tiếp

Hạ tầng T12 v2 và Gemma conformance retest đã hoàn tất, nhưng reasoner cho nghiên cứu chính vẫn chưa được chọn. Bước kế tiếp là đăng ký một candidate mạnh hơn, chạy cùng synthetic suite và chỉ chuyển sang Oracle-development gate nếu candidate vượt toàn bộ threshold.
