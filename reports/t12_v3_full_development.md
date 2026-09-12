# T12 v3 — full development matrix

## Mục tiêu và đăng ký

Full development matrix đo cùng một reasoner đã vượt synthetic conformance và Oracle-development gate trên năm nguồn graph. Candidate `configs/t12_v3_openai_mini_full_development.yaml` được đóng băng trước live execution và chỉ cho phép:

```text
7 primary development scenes
× 5 frozen tasks
× 5 graph conditions
= 175 records
```

Năm conditions là `G_LLM`, `G_SCD_RAW`, `G_SCD_PROJECTED`, `G_HYBRID`, và `G_ORACLE`. Model snapshot, medium reasoning effort, giới hạn 10.240 token, prompt v3, canonical JSON edge list, X000 labels, năm response schemas, parser và hai scorer không thay đổi.

Không đặt accuracy threshold cho ranking giữa graph sources: đây là kết quả development mang tính mô tả, và dùng một kết quả “đẹp” làm gate sẽ tạo selection bias. Gate chỉ kiểm tra tính hoàn chỉnh, schema, model identity, canonical response reuse, quan hệ với Oracle parent và ranh giới holdout.

## Preflight và canonical caching

Preflight xác nhận đủ 175 records nhưng chỉ có 105 canonical inputs duy nhất. Một canonical input được xác định bởi model/prompt, canonical graph view, query, non-causal glossary, response schema và decoding config; graph-source label không nằm trong cache key.

- 35 identities đã có từ Oracle-development parent.
- Các identities đó bao phủ 90 matrix records vì nhiều graph sources có input giống Oracle hoặc giống nhau.
- Còn đúng 70 API calls mới trước retry.
- 70 records dư thừa được tái sử dụng response thay vì gọi provider lần nữa.
- Không có holdout access.

Toàn bộ 35 `G_ORACLE` records dùng nguyên response của Oracle-development gate. Audit canonical sau replay khớp parent 35/35.

## Kết quả theo graph condition

| Graph condition | Oracle-answer accuracy | Uncertainty-aware correctness | Ý nghĩa trực tiếp |
|---|---:|---:|---|
| `G_ORACLE` | 34/35 = 97,14% | 34/35 = 97,14% | Reasoner gần như đọc đúng graph chuẩn |
| `G_LLM` | 33/35 = 94,29% | 34/35 = 97,14% | Graph LLM gần Oracle trên development |
| `G_HYBRID` | 31/35 = 88,57% | 32/35 = 91,43% | Hybrid tốt nhưng có lỗi graph và một số lỗi reasoner |
| `G_SCD_PROJECTED` | 6/35 = 17,14% | 33/35 = 94,29% | Reasoner đọc projection khá đúng, nhưng DAG projection không phù hợp Oracle answer |
| `G_SCD_RAW` | 4/35 = 11,43% | 35/35 = 100% | 31/35 target là `undetermined`; reasoner xử lý uncertainty đúng nhưng official scorer không thưởng abstention |

Oracle-answer accuracy hỏi “câu trả lời có khớp benchmark hay không”. Uncertainty-aware correctness hỏi “câu trả lời có đúng với graph thực sự được cung cấp, kể cả `undetermined`, hay không”. Vì vậy `G_SCD_RAW` đạt 100% uncertainty-aware không có nghĩa nó tốt nhất cho official QA; nó có nghĩa reasoner không giả vờ biết direction mà CPDAG chưa xác định.

Tương tự, khoảng cách lớn của `G_SCD_PROJECTED` giữa hai metric cho thấy reasoner phần lớn làm đúng theo graph đầu vào, nhưng lexicographic consistent extension bổ sung các direction tùy ý và dẫn đến câu trả lời khác Oracle. Đây là bằng chứng development ủng hộ việc giữ CPDAG chính và chỉ dùng projected DAG như sensitivity analysis.

Các con số này chưa phải kết luận thống kê: chỉ có 7 development scenes, nhiều canonical inputs trùng nhau, và không có paired/scene-clustered confidence intervals hay BH correction ở bước này.

## Engineering và usage

- 175/175 final records parse/schema-valid ngay attempt đầu.
- 105 unique captured calls: 35 inherited và 70 incremental.
- Không validation retry, không incomplete response.
- 50 canonical-equivalence groups; 70 records tái sử dụng response.
- Maximum output-token utilization: 77,90%.
- Reasoning tokens/call: min 203, median 459, max 7.954.
- Latency/call: min 2.243 ms, median 4.338 ms, max 45.713 ms.
- Incremental usage: 111.650 input tokens, 67.840 cached input tokens, 107.954 output tokens gồm 106.268 reasoning tokens.
- Incremental estimated standard cost: USD 0,5237385.
- Tổng cost kể cả 35 inherited Oracle calls: USD 0,608445.

## Gate và quyết định

Mọi integrity/engineering gate đã đăng ký đều đạt:

```yaml
full_development_matrix_passed: true
reasoner_frozen_for_holdout: true
holdout_reasoner_ready: true
t13_eligible: true
holdout_accessed: false
```

“Holdout-ready” chỉ có nghĩa reasoner/model/prompt/parser/scorers đủ điều kiện được khóa trước holdout. Nó không cho phép bỏ qua T13 hoặc tự động mở holdout. Bước kế tiếp là T13 để xác nhận/freeze toàn bộ holdout task manifests và execution configuration; T14 mới mở holdout đúng một lần.

## Reproducibility

Cache-only `--check` tái sinh score records và audit byte-for-byte với 0 API calls.

- Candidate config: `B687B9AA3D46B7F013B57DC23052B52987F129661580BD44C324F74045B2AF47`.
- Runner: `9E3D8C41A4A3998A9326318105A7C474102229ABE48DEF860C909E7E4B7D1D61`.
- Score records: `BACD53AB9CD7B184CDB65D017864DD998800BB84ED4388C23F7723102C5F1037`.
- Audit artifact: `F13738A8FD4CB17B52E298DB569467B095FA4F506C47CCF72D3485AA8A0FA503`.
- Incremental raw/cache remain under `results/raw/` and outside Git.

Không thay đổi T08–T10 hoặc reasoner dựa trên ranking development vừa quan sát.
