# T12 — Fixed reasoner và hai scorer

## Phạm vi đã triển khai

T12 xây một reasoner duy nhất cho năm graph-sensitive tasks trên bảy primary development scenes. Mỗi task được chạy với năm graph views: `G_LLM`, raw `G_SCD` CPDAG, projected `G_SCD` DAG, `G_HYBRID`, và grading-only `G_ORACLE`. Tổng cộng có 175 records; holdout không được truy cập.

Reasoner chỉ nhận:

- `fourgraph.reasoner_graph.v1`: node/cạnh/graph type, không có method hay provenance;
- query đã đổi hoàn toàn sang ID `X000...`;
- glossary chỉ có canonical ID và variable type;
- response schema.

Public story, semantic names, observational table, graph-source label và gold answer đều không vào prompt. Gold chỉ được loader riêng mở với `GradingPurpose.SCORING` sau khi model đã trả lời.

## CPDAG và scoring

Engine liệt kê toàn bộ DAG tương thích với một CPDAG (tối đa bảy node trong P0), giữ skeleton, compelled directions và unshielded colliders. Với `one_valid_adjustment_set`, một đáp án được xác định khi cùng một valid set tồn tại trong mọi DAG; với bốn task còn lại, toàn bộ đáp án phải giống nhau. Nếu không, target là `undetermined`.

Hai metric được lưu độc lập:

- `oracle_answer_accuracy`: đáp án model có khớp official CausalDS answer của true scene hay không;
- `uncertainty_aware_correctness`: đáp án có đúng theo thông tin mà graph được cung cấp thực sự xác định hay không, kể cả trả `undetermined` đúng lúc.

Engine graph-derived đã được đối chiếu với toàn bộ 35 official development targets và khớp 35/35 trước live run.

## Live development run

Configuration: Google AI Studio, `gemma-4-31b-it`, `google-genai==2.21.0`, temperature 0, tối đa ba validation retries. Sáu credential slots được đọc từ biến môi trường và chỉ rotation khi gặp quota error. Raw prompt/response nằm trong `results/raw/t12_reasoner/` và bị Git ignore.

Kết quả mô tả:

| Graph condition | Oracle-answer accuracy | Uncertainty-aware correctness |
|---|---:|---:|
| G_LLM | 20/35 = 0.571 | 20/35 = 0.571 |
| G_SCD raw CPDAG | 11/35 = 0.314 | 15/35 = 0.429 |
| G_SCD projected DAG | 11/35 = 0.314 | 5/35 = 0.143 |
| G_HYBRID | 17/35 = 0.486 | 15/35 = 0.429 |
| G_ORACLE | 19/35 = 0.543 | 19/35 = 0.543 |

Toàn bộ 175 calls cuối cùng parse được; 35 calls cần ít nhất một validation retry và tổng cộng có 39 retry attempts. Có 31 raw-CPDAG task targets là `undetermined`.

## Verdict

`t12_complete: true` ở mức triển khai: contract, CPDAG semantics, hai scorer, live development records và byte-for-byte replay đều hoàn tất. Tuy nhiên `holdout_reasoner_ready: false`: accuracy 19/35 ngay trên `G_ORACLE` là một floor/sanity problem, nên chưa được freeze model này để chạy holdout. Cần pre-register một T12 reasoner refinement hoặc model replacement trên development set; không được sửa T08–T10 theo các kết quả downstream này.
