# T12 v3 — G_ORACLE development gate

## Mục tiêu và phạm vi

Gate này kiểm tra reasoner T12 v3 trên graph đúng của CausalDS trước khi cho phép chạy toàn bộ development matrix. Phạm vi được đăng ký trước và giới hạn ở:

- 7 scene thuộc `primary_downstream.dev` đã đóng băng;
- 5 task/scene, tổng cộng 35 record;
- chỉ graph condition `G_ORACLE` và graph type `dag`;
- không dùng story, public semantic names, observational table hay graph provenance;
- không truy cập holdout, không tự động chạy full development matrix hoặc T13.

Candidate giữ nguyên `gpt-5.4-mini-2026-03-17`, `reasoning_effort: medium`, `max_output_tokens: 10240`, prompt bundle v3, canonical JSON edge list, năm response schema và strict scorer đã vượt synthetic conformance.

## Đăng ký và preflight

Candidate nằm tại `configs/t12_v3_openai_mini_oracle_dev.yaml`. Nó pin parent conformance audit, split manifest, task manifest, Oracle-loader config, prompt contract và response schemas bằng SHA-256.

Offline preflight xác nhận:

- đúng 7 development scene và 35 prompt;
- đúng 5 task cho mỗi scene;
- official target và target tính trực tiếp từ Oracle DAG tương đương 35/35;
- 20 record thuộc lớp valid non-empty, 15 record thuộc lớp valid empty;
- 12 record bắt buộc dùng biểu diễn rỗng cụ thể: 6 `[]`, 3 `[[]]`, 3 `0`;
- không có target `no_backdoor`; gate này được ghi `not_applicable_zero_targets`;
- Oracle là DAG nên không có target CPDAG `undetermined`; gate này được ghi `not_applicable_oracle_is_dag`;
- holdout access bằng 0.

## Kết quả

Reasoner hoàn tất 35/35 request, tất cả parse/schema-valid ngay attempt đầu, không retry và không có response incomplete.

| Chỉ số | Kết quả |
|---|---:|
| Oracle-answer accuracy | 34/35 = 97,14% |
| Uncertainty-aware correctness | 34/35 = 97,14% |
| One valid adjustment set | 6/7 |
| All minimal adjustment sets | 7/7 |
| Minimal adjustment set size | 7/7 |
| Number of valid adjustment sets | 7/7 |
| Forbidden controls list | 7/7 |
| Required empty sentinels | 12/12 |
| First-attempt schema compliance | 35/35 |

Mọi gate áp dụng đều đạt: tổng ít nhất 30/35, mỗi task ít nhất 5/7, empty sentinel ít nhất 10/12, đúng snapshot, đầy đủ usage telemetry và không truy cập holdout. Vì vậy:

```yaml
oracle_development_passed: true
full_development_matrix_eligible: true
holdout_reasoner_ready: false
holdout_accessed: false
```

`holdout_reasoner_ready` vẫn là `false` vì gate này chỉ cho phép bước kế tiếp là full development matrix; reasoner chưa được freeze cho holdout.

## Case sai duy nhất

Case `scene_000511:identification__one_valid_adjustment_set` có treatment `X005`, outcome `X006`, và Oracle DAG chứa cả `X000 → X005`, `X000 → X006`, `X005 → X006`. Sau khi bỏ causal-path edge `X005 → X006`, fork `X005 ← X000 → X006` vẫn mở, nên một valid adjustment set phải chứa `X000`. Model trả `[]`, trong khi các đáp án official hợp lệ đều chứa `X000`.

Đây là lỗi suy luận, không phải lỗi parser hay scorer. Bốn task khác trên cùng scene đều đúng, gồm minimal size `1` và count `16`, cho thấy một bất nhất cục bộ giữa các request task-specific. Kết quả này được giữ nguyên; prompt/model không được chỉnh lại từ case development này vì candidate đã vượt gate đăng ký trước.

## Token, thời gian và chi phí

- Input tokens: 55.210, trong đó 28.160 cached input tokens.
- Output tokens tính cả reasoning: 13.846; reasoning tokens: 13.038.
- Reasoning-token distribution: min 203, median 313, max 1.213.
- Maximum output-token utilization: 12,08% của trần 10.240.
- Latency: min 2.341 ms, median 3.729 ms, max 26.109 ms.
- Chi phí standard ước tính theo pricing đã pin: USD 0,0847065.

Không có dấu hiệu chạm trần hay runaway reasoning trong gate này.

## Reproducibility và hashes

Runner `--check` đã tái sinh score records và audit byte-for-byte từ cache với `live_calls_this_run: 0`.

- Candidate config: `328DF4A6B76A71BA4B5C5890EC772B26FD87B0403323168C1C53D742BF3ED70C`.
- Runner: `CE75D95A4BB12421EF1DAA17D926B2CBF4E10F69A7A376A246C73CC164E54A17`.
- Score records: `CB31DC9179DFCD9F4C1EA56500806875EA2BDF7CAF07D5D1CEBD6083D04E20EA`.
- Audit artifact: `3CEBE2329EEA2664F37449FF499BD0C323FDB09E9149D736FDA6F69DF0DB71D8`.
- Raw log và cache tiếp tục nằm trong `results/raw/` và không đưa vào Git.

## Quyết định

T12 v3 đã vượt Oracle-development gate và đủ điều kiện để đăng ký full development matrix. Bước này chưa chạy full matrix, chưa freeze reasoner cho holdout, chưa bắt đầu T13 và chưa mở bất kỳ holdout scene nào.

## Trạng thái kế nhiệm

Sau boundary của gate này, full development matrix đã được đăng ký và chạy trong một candidate riêng. Matrix đạt toàn bộ integrity gates và reasoner hiện đã freeze/holdout-ready; xem `reports/t12_v3_full_development.md`. T13 và holdout vẫn chưa được chạy.
