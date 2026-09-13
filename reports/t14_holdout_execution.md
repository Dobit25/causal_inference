# T14 — Thực thi holdout P0

## Kết luận

T14 đã hoàn tất đúng một logical resumable run theo manifest T13. Holdout được mở cho 25 graph scenes; downstream reasoner chỉ xử lý 20 primary scenes. Năm supplementary scenes chỉ tham gia graph construction/evaluation và không được gộp vào primary downstream.

T14 chỉ tạo per-record graph/downstream scores và audit kỹ thuật. Aggregate ranking, paired bootstrap, confidence intervals, hypothesis tests và BH correction chưa được thực hiện; đó là T15.

## Graph construction

- `G_LLM`: 25/25 canonical DAGs, 25 attempts, không retry.
- `G_SCD_RAW`: 25/25 CPDAGs từ BOSS/BasisFunctionBicScore.
- `G_SCD_PROJECTED`: 25/25 deterministic consistent extensions.
- `G_HYBRID`: 23/25 canonical DAGs, 29 attempts.
- Hai Hybrid terminal failures: `scene_000281` và `scene_000699`. Sau ba attempts, hướng semantic vẫn tạo child DAG ngoài parent CPDAG equivalence class. Không fallback graph và không sửa prompt.
- Bốn graph sources phi-Oracle được seal trước lần grading-only Oracle access đầu tiên.

Graph metric schedule có đúng 125 rows: 123 available và hai Hybrid rows unavailable. Oracle được load trong memory cho 25 scenes; không có Oracle edge hoặc Oracle graph artifact nào được persist.

## Fixed reasoner

- Scheduled: 500 records = 20 scenes × 5 tasks × 5 graph conditions.
- Một primary Hybrid graph failure tạo 5 downstream records được tính incorrect mà không gọi model.
- 495 graph/query records còn lại rút thành 245 canonical identities.
- 243 identities trả response hợp lệ; hai identities terminal failure sau ba incomplete attempts, đều thuộc `scene_000281`.
- Final records: 493 answered, 5 graph failures và 2 reasoner failures.
- API attempts: 258, gồm 13 validation retries.
- Canonical reuse: 250 records dùng lại đúng response của một identical input.

Reasoner usage: 412.964 input tokens, trong đó 212.480 cached; 438.415 output tokens gồm 432.647 reasoning tokens. Captured estimated reasoner cost là USD 2,1391665. Builder usage riêng là 49.680 input và 13.341 output tokens; T13 không pin bảng giá builder nên audit không tự suy ra chi phí của phần này.

## Reproducibility và failure handling

Terminal wrapper bị timeout trong lúc reasoner chạy, nhưng worker con tiếp tục cùng raw log/cache. Không worker thứ hai được khởi chạy; logical run được resume/check theo exact canonical identity. Không identity đã cache nào bị gọi lại.

Offline replay sau khi chạy đã:

- tái dựng byte-for-byte 25 LLM DAGs;
- chạy lại byte-for-byte 25 raw CPDAG và 25 projected DAG;
- replay đúng 23 Hybrid DAG và hai terminal Hybrid failures;
- tái sinh byte-for-byte 500 reasoner score records từ cache/raw attempts;
- tái sinh byte-for-byte audit T14.

Versioned audit: `data/manifests/t14_holdout_execution_audit.json`. Raw graph, prompt, response, cache, scoring và metric records nằm dưới ignored `results/raw/t14_holdout/` và được tham chiếu bằng SHA-256.

## Gate tiếp theo

`t14_complete: true`, `t15_authorized: true`, `t15_started: false`. T15 phải dùng nguyên 125 graph schedule rows và 500 downstream rows, bao gồm failure-as-incorrect/unavailable đúng pre-registration; không được gọi lại failures hoặc sửa T08–T12 sau khi xem holdout.

