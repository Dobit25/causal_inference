# T12 v3 — task-specific prompt contract

## Mục tiêu

V3 sửa đúng failure mode của Mini-D mà không thay model hoặc graph encoding. Runtime vẫn là `gpt-5.4-mini-2026-03-17`, reasoning effort `medium`, `max_output_tokens=10240`; graph vẫn là canonical JSON edge list với nhãn `X000...`. Thay đổi khoa học duy nhất là prompt v2 generic được thay bằng một shared base và đúng một task-specific module cho mỗi request.

Kết quả v2/Mini-D được giữ bất biến. Suite v2 đã mở chỉ được dùng làm diagnostic development evidence, không còn đủ điều kiện làm final v3 conformance gate.

## Shared base

Base khóa quy trình trên từng DAG:

1. Dùng đúng treatment, outcome và candidate variables.
2. Liệt kê mọi directed treatment-to-outcome path.
3. Tính descendants, internal path nodes và eligible controls theo released CausalDS convention.
4. Xóa mọi edge thuộc các directed causal paths.
5. Liệt kê candidate subsets theo cardinality/lexicographic order, size tối đa 5, và kiểm tra d-separation.
6. Nếu valid-set family rỗng, dùng khái niệm nội bộ `no_valid_adjustment_set`.
7. Map nội bộ đó thành chuỗi official `"no_backdoor"`; không được xuất tên nội bộ.
8. Với CPDAG, làm toàn bộ quy trình độc lập trên mọi compatible DAG rồi áp dụng invariance rule của task.

Base đóng băng sự khác nhau giữa `[]`, `[[]]`, `0`, `"no_backdoor"` và `"undetermined"`, kèm sentinel precedence. Năm ví dụ synthetic năm-node minh họa empty set, direct outcome-to-treatment, CPDAG invariant/non-invariant và forbidden controls. Chúng không dùng CausalDS story hoặc answer và không sao chép nguyên record ba/bốn-node của suite v2.

## Năm task modules

- `one_valid_adjustment_set`: DAG chọn valid set nhỏ nhất/lexicographic để reproducible; CPDAG dùng giao của valid-set families, chỉ trả một set tồn tại trong mọi compatible DAG.
- `all_minimal_adjustment_sets`: tính toàn bộ minimum-cardinality sets cho từng DAG; CPDAG chỉ answered nếu toàn bộ list giống hệt nhau.
- `minimal_adjustment_set_size`: phân biệt integer `0` với `"no_backdoor"`; CPDAG so sánh integer/sentinel giữa mọi DAG.
- `n_valid_adjustment_sets`: empty set được tính là một; nếu family rỗng phải trả `"no_backdoor"`, không trả 0.
- `forbidden_controls_list`: kiểm tra valid-set family trước; `no_backdoor` có precedence. Chỉ khi family không rỗng mới tính forbidden descendants và query-relevant unshielded colliders; CPDAG so sánh complete lists/sentinels.

Mỗi request chỉ chứa module đúng với `task_id`. Assembler từ chối thiếu/thừa module, task mismatch, marker lỗi, graph có provenance hoặc glossary chứa trường ngoài ID/type.

## Reproducibility và leakage boundary

- Config: `configs/t12_v3_prompt.yaml`.
- Builder/checker: `scripts/build_t12_v3_prompt.py`.
- Contract manifest: `data/manifests/t12_v3_prompt_contract.json`.
- Prompt bundle SHA-256: `B56769130309CC64CAD8A356F3D74E437F2C30B6DD42C76DDF3873A9714A10F6`.
- Contract manifest SHA-256: `65912960D159191E8EF2FD0BBBBB425D9F8384C80733040B6ABE6EC40EE53B93`.
- Story, semantic names, observational data, graph provenance và gold answers đều bị cấm.
- Holdout chưa được truy cập.

## Synthetic conformance suite đã đóng băng

Suite v3 được sinh offline với seed `1203`, gồm 150 case mới và không trùng định danh graph/query/task với suite v2. Mỗi task có 30 case: 18 DAG answered, 6 CPDAG invariant và 6 CPDAG undetermined. Bốn lớp answer được cân bằng toàn suite: 40 valid non-empty, 40 valid empty, 40 `no_valid_adjustment_set` (serialize thành `no_backdoor`) và 30 `undetermined`.

Production scorer và independent solver dùng hai triển khai graph/path khác nhau đã khớp target và answer class 150/150. Panel 20 case (4/task) đã được đọc trực tiếp; smoke manifest có 10 ID cố định (2/task). Các motif đều vượt minimum đã đăng ký, gồm 10 mediation, 70 collider, 55 confounding, 62 direct outcome-to-treatment, 42 forbidden-control và 72 multiple-set case.

- Suite SHA-256: `55B8B8DBB5024E8F4A815FDB5227A8E5EDD53E5B5F86AB2D3D5BB07B9022EECD`.
- Audit SHA-256: `D1AA8919430216C3D1BA2B878AF94359C1F99D19D8D5042FD4050EA75F504F8F`.
- Manual panel SHA-256: `C722793A502A512CD8E699508E92CB6D6CFD817509837D1955A787DDA8EC3760`.
- Smoke manifest SHA-256: `BFA81876301C223631B6E5CF6A02EE117E7510DE9BCCC47BDAD7D3CE1F15B49C`.
- Live candidate config: `configs/t12_v3_openai_mini.yaml`, SHA-256 `8CD0CC03BDF998DB40B959A95B513568816136524A6F2897C61EAAFFA5E920C6`.

Không có API call và không truy cập holdout trong bước này. Candidate chỉ cho phép hành động live kế tiếp là smoke 10 case; không tự động chạy đủ 150 case.

## Live smoke 10 case

Runner v3 đã xác minh toàn bộ frozen hashes trước khi gọi Responses API và từ chối chế độ full conformance theo candidate hiện tại. Live smoke gọi đúng 10 case, không retry: 10/10 response hoàn tất, parse được và hợp lệ schema ngay attempt đầu; exact model snapshot và usage telemetry đều khớp. Maximum output-token utilization là `0.70195312`, dưới gate `0.80`. Tổng usage là 16,330 input tokens và 24,304 output tokens (trong đó 24,061 reasoning tokens); chi phí ước tính theo pricing đã pin là USD `0.1198875`.

Smoke đạt toàn bộ engineering gate. Diagnostic accuracy là 9/10, không phải scientific gate. Case sai duy nhất `V3SYN103` là `n_valid_adjustment_sets` với direct `Outcome → Treatment`: expected `{"n":"no_backdoor"}`, model trả `{"n":8}`. Điều này cho thấy sentinel-precedence vẫn cần được đánh giá trên đủ 150 case; không được sửa prompt v3 từ một smoke observation đã mở.

Audit đã replay byte-for-byte từ cache, SHA-256 `81AB3F0E40C239EFD4A96BB19DAF3F518619E3A8FFAF35A04724B8D703B29F53`. Raw prompt/response vẫn nằm ngoài Git. Không có CausalDS Oracle-development call và không truy cập holdout.

## Full 150-case conformance

Một candidate kế nhiệm chỉ thay lifecycle authorization đã được tạo tại `configs/t12_v3_openai_mini_full.yaml`; model, runtime, prompt, graph encoding, suite, schemas, scorer và prospective gates khớp byte-for-byte với smoke parent. Offline preflight xác nhận 150 prompts, 10 cache hits, 140 cases cần gọi mới và không truy cập benchmark/holdout.

Full run hoàn thành 150/150 records và vượt toàn bộ scientific gates:

- parse `150/150 = 1.000`;
- first-attempt compliance `145/150 = 0.9667`;
- overall `146/150 = 0.9733`;
- DAG answered `87/90 = 0.9667`;
- CPDAG invariant `29/30 = 0.9667`;
- CPDAG undetermined `30/30 = 1.000`;
- one-valid `30/30`, all-minimal `30/30`, minimal-size `29/30`, count-valid `29/30`, forbidden-controls `28/30`.

Theo answer class: `no_valid_adjustment_set` 38/40, `undetermined` 30/30, valid-empty 39/40 và valid-nonempty 39/40. Bốn lỗi là `V3SYN076`, `V3SYN103`, `V3SYN128`, `V3SYN139`; hai lỗi đầu liên quan `no_backdoor`, hai lỗi sau thuộc forbidden-controls.

Engineering caveat: 155 calls được ghi cho 150 cases vì năm attempts dùng hết 10240 reasoning tokens và trả incomplete; cả năm retry đều hoàn tất. Vì thế full-run headroom diagnostic `<=0.80` thất bại, nhưng first-attempt compliance vẫn vượt prospective scientific gate 0.95 và mọi case có final parsed response. Tổng chi phí telemetry ước tính USD `1.53063675`.

Records hash `5E707CD91354F73B26963FF020EA18A88B39CF15F7FA50A32ECDC01A1F44F975`; audit hash `7A9721F6F13A940BE176FEAF2AD4ED3E7EDC14D3100B46A8F744EFC327B5C6E1`. Replay `--check` tái sinh cả hai byte-for-byte từ cache. `causalds_oracle_development_eligible: true`; full-conformance runner đã dừng đúng boundary trước Oracle-development và holdout.

## Trình tự triển khai tiếp theo

1. Dùng suite v2 đã mở để làm diagnostic regression, không báo nó như prospective v3 accuracy.
2. Giữ prompt bundle, suite, schemas và smoke IDs v3 bất biến theo live candidate đã pin.
3. Chạy smoke bằng Mini-D runtime để kiểm tra parse, schema, token headroom, cache/resume và chi phí.
4. Nếu smoke đạt và có quyết định GO riêng, chạy đủ sealed 150 cases và áp dụng nguyên các gate v2: overall/DAG/CPDAG tối thiểu 0.90, mỗi task tối thiểu 0.80.
5. Oracle-development gate đã được đăng ký và chạy riêng: 34/35, mọi gate áp dụng đều đạt. Chi tiết nằm trong `reports/t12_v3_oracle_development.md`.
6. Full development matrix đã được đăng ký và hoàn tất: 175 records, mọi integrity gate đạt, reasoner đã freeze. Chi tiết nằm trong `reports/t12_v3_full_development.md`.
7. Bước kế tiếp là T13 để xác nhận task manifests và toàn bộ holdout configuration. Holdout vẫn chưa mở.

Hiện trạng: prompt contract và suite đã hoàn thành, independently audited, hash-pinned và byte-reproducible. Live candidate đã mở riêng cho smoke 10 case; chưa có API call.
