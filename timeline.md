# Timeline dự án Causal Inference: T00–T21

## 1. Mục đích của tài liệu

Tài liệu này mô tả tuyến tính quá trình phát triển dự án từ T00 đến hết T21: mỗi task bắt đầu từ vấn đề nào, được thực hiện để làm gì, đã làm những gì, điều kiện hoàn thành ra sao và kết quả thực tế là gì.

Toàn bộ công việc được thực hiện trong môi trường Conda `cau`, dùng Python 3.10. Dự án tuân theo nguyên tắc không dùng holdout để điều chỉnh thiết kế, không trộn observations giữa các causal scene, và không để ground-truth Oracle rò rỉ vào các graph builder.

## 2. Các khái niệm xuyên suốt

- **Scene**: một causal system riêng, gồm tập biến, causal graph, cơ chế sinh dữ liệu, observational table, story và các task tương ứng.
- **SCM — Structural Causal Model**: mô hình nhân quả cấu trúc mô tả mỗi biến được sinh từ cha của nó và nhiễu ngoại sinh như thế nào.
- **SCD — Statistical Causal Discovery**: suy ra causal graph từ observational data bằng thuật toán thống kê.
- **DAG — Directed Acyclic Graph**: đồ thị có hướng không chứa chu trình có hướng.
- **CPDAG — Completed Partially Directed Acyclic Graph**: biểu diễn một lớp các DAG tương đương Markov. Cạnh có hướng là direction bị dữ liệu và các giả định ép buộc; cạnh vô hướng là direction chưa xác định được.
- **Skeleton**: tập adjacency của graph khi bỏ qua direction.
- **Compelled direction**: direction giữ nguyên trong mọi DAG thuộc cùng Markov equivalence class.
- **Projected DAG**: một DAG hợp lệ được chọn tất định từ CPDAG. Các direction bổ sung chỉ là quy tắc projection, không phải kết luận thống kê mới.
- **Development split**: phần dữ liệu được phép dùng để xây dựng, kiểm thử và đóng băng pipeline.
- **Holdout split**: phần dữ liệu chưa được mở, dành cho đánh giá cuối sau khi toàn bộ thiết kế đã đóng băng.
- **Oracle graph**: ground-truth causal DAG, chỉ được dùng ở đường grading/evaluation hoặc điều kiện `G_ORACLE` được khai báo rõ.
- **Canonical artifact**: artifact dùng một schema, serialization, thứ tự và hash thống nhất để có thể kiểm tra và tái lập.

Nghiên cứu sử dụng bốn nguồn graph chính:

1. `G_LLM`: LLM xây DAG chỉ từ public story và variable semantics.
2. `G_SCD`: thuật toán causal discovery học graph từ observational data đã đổi tên biến thành `X000...`.
3. `G_HYBRID`: giữ skeleton và compelled directions của raw SCD CPDAG, sau đó dùng semantics để định hướng các cạnh unresolved.
4. `G_ORACLE`: ground-truth DAG, chỉ dùng trong đường Oracle/grading đã được kiểm soát.

Ngoài ra, projected `G_SCD` DAG được giữ như một sensitivity view, không phải kết quả SCD chính.

## 3. Tóm tắt tuyến tính

| Mốc | Ngày hoàn thành | Vai trò trong tiến trình | Trạng thái |
|---|---|---|---|
| T00 | 2026-08-27 | Dựng bộ khung kỹ thuật tối thiểu | Hoàn thành |
| T01 | 2026-08-27 | Audit NoisyCausal và kiểm tra khả năng resampling/SCD | Hoàn thành, `scd_ready: false` |
| T02 | 2026-08-30 | Chuyển sang CausalDS, đóng băng thiết kế và provenance | Hoàn thành |
| T03 | 2026-08-30 | Inventory 100 scenes và sinh provisional nested split | Hoàn thành |
| T04 | 2026-08-30 | Audit toàn bộ dữ liệu P0 và freeze exact scene/task IDs | Hoàn thành |
| T05 | 2026-08-30 | Đánh giá và chọn phương pháp SCD/CPDAG | Hoàn thành |
| T06 | 2026-08-31 | Xây canonical graph contract chung | Hoàn thành |
| T07 | 2026-08-31 | Xây grading-only Oracle loader và chống leakage | Hoàn thành |
| T08 | 2026-08-31 | Xây và chạy public-story-only LLM graph builder | Hoàn thành |
| T09 | 2026-09-01 | Sinh development raw/projected `G_SCD` artifacts | Hoàn thành |
| T10 | 2026-09-02 | Sinh development Hybrid H1 artifacts | Hoàn thành |
| T11 | 2026-09-02 | Đánh giá structural graph metrics trên development | Hoàn thành |
| T12 | 2026-09-04–11 | Fixed reasoner, conservative CPDAG semantics, hai scorer và conformance refinement | V3 đạt 146/150 synthetic, 34/35 Oracle-development và hoàn tất matrix 175 records; reasoner đã freeze, chưa mở holdout |
| T13 | 2026-09-12 | Đóng băng toàn bộ cấu hình thực thi holdout | Khóa 25 graph scenes = 20 primary + 5 supplementary, 500 primary records dự kiến; 4 artifact replay byte-for-byte, 0 API call, holdout chưa mở |
| T14 | 2026-09-12–13 | Mở holdout đúng một logical resumable run | 98/100 non-Oracle graphs thành công, 2 Hybrid failures; 125 graph rows và 500 downstream rows terminal; replay offline đạt, chưa chạy T15 |
| T15 | 2026-09-13 | Phân tích thống kê P0 holdout đã seal | 225 scene summaries, 36 paired contrasts, 5.000 cluster bootstraps/contrast, BH và McNemar sensitivity; replay offline đạt |
| T16 | 2026-09-13 | Khóa findings và quyết định P0 | Chốt claim được/không được hỗ trợ, giữ null/adverse results, chọn `REFINE`; chỉ cấp quyền thiết kế protocol T17 |
| T17 | 2026-09-13 | Xây và đóng băng thiết kế P1 Hybrid trước generation/H2 | Khóa 100-scene fresh-SCM contract, semantic doses, BOSS CPDAG, H2 forced/selective, abstention, metrics/statistics và stage gates; 0 scene, 0 API call, chỉ cấp quyền T18 generator/inventory |
| T18 | 2026-09-13 | Sinh và đóng băng fresh-SCM substrate P1 | Sinh 100 SCM, 500 task với solver agreement 500/500, observations và exact split 20/80; replay 480 raw files byte-for-byte, 0 API/H2/holdout evaluation; chỉ cấp quyền T19 |
| T19 | 2026-09-13 | Sinh ba mức semantic evidence và kiểm định stimulus | 300 story full/partial/ambiguous, 100 alias maps, text-level truth audit, internal blinded QA 20/20 development scenes; 0 API/method/holdout manual review; chỉ cấp quyền T20 offline |
| T20 | 2026-09-14 | Triển khai H2 và kiểm định offline | 150/150 forced và 3.000/3.000 selective decisions khớp independent solver; từ chối 30/30 input lỗi; 0 API/P1 access; chỉ cấp quyền T21 development-only |
| T21 | 2026-09-15 | Chạy P1 development và chọn selective threshold | 20 scenes, 60 preferences, 80 API attempts; H2 valid nhưng best precision 0,90 < gate 0,95; không chọn threshold, holdout tiếp tục khóa |

---

## 4. T00 — Bootstrap repository

### Vấn đề ban đầu

Dự án mới chỉ có kế hoạch nghiên cứu. Chưa có package Python, CLI, cấu hình chạy, seed utility hoặc test để các task sau dựa vào.

### Mục đích

Tạo một bộ khung nhỏ nhưng chạy được trong môi trường `cau`, đủ để mọi task sau có cấu trúc code, config và kiểm thử thống nhất.

### Công việc đã thực hiện

- Khởi tạo package `fourgraph` dưới `src/fourgraph/`.
- Tạo CLI tối thiểu và lệnh kiểm tra cấu hình.
- Tạo YAML config loader.
- Tạo deterministic seed utility.
- Thiết lập `pyproject.toml`, `.gitignore` và test bootstrap.
- Giữ causal-discovery và LLM dependencies ngoài phạm vi T00 để chưa khóa công nghệ quá sớm.

### Điều kiện hoàn thành

- Package import được trong Conda `cau`.
- CLI hiển thị help và đọc được config.
- Seed utility hoạt động tất định.
- Test bootstrap đạt.

### Kết quả

- Package import thành công với version `0.1.0`.
- CLI và config validation chạy được.
- 4/4 tests ban đầu đạt.
- Bộ khung này trở thành nền kỹ thuật cho T01 trở đi.

### Chuyển sang bước tiếp theo

Sau khi có bộ khung, dự án cần xác minh benchmark NoisyCausal có thật sự cung cấp dữ liệu/SCM cần thiết hay không. Đây là nhiệm vụ của T01.

---

## 5. T01 — Audit artifact NoisyCausal

### Câu hỏi trung tâm

> Artifact chính thức của NoisyCausal có đủ thông tin để sinh nhiều observational samples độc lập từ cùng một SCM hay không?

Điểm cần phân biệt là một tập QA rows không tương đương với nhiều observations từ cùng causal system. Không thể gộp các QA rows thuộc những SCM khác nhau thành một bảng rồi chạy PC, GES hoặc một phương pháp SCD khác.

### Mục đích

Xác minh NoisyCausal có thể làm substrate cho thiết kế bốn graph hay không, đặc biệt là nhánh `G_SCD` cần repeated observations cùng SCM.

### Công việc đã thực hiện

- Audit các nguồn ACL, arXiv, OpenReview, repository của tác giả, GitHub search, Hugging Face và Zenodo.
- Kiểm tra paper, supplementary/source archive và các artifact tải được.
- Ghi URL, provenance, license, byte size và SHA-256.
- Tìm dataset schema, system/question identifiers, ground-truth graph, SCM equations, CPD, exogenous noise, official sampler và clean–noise linkage.
- Tách rõ readiness cho reasoning, graph evaluation, noise evaluation, Oracle và SCD.
- Lưu provenance vào `data/MANIFEST.json` và diễn giải vào `docs/data_audit.md`.

### Điều kiện hoàn thành

T01 phải đưa ra verdict dứt khoát `scd_ready: true|false`, không để trạng thái TBD.

### Kết quả

- Ba artifact publication được cache và khớp hash/size.
- Không xác minh được public benchmark records.
- Không có complete per-system SCM/CPD.
- Không có executable official sampler.
- Không có repeated observational samples được nhóm theo cùng SCM.
- Verdict cuối cùng: `scd_ready: false`.

### Ý nghĩa của kết quả

T01 không phải một task thất bại. Nó tạo bằng chứng âm quan trọng: NoisyCausal không đủ artifact công khai để triển khai nhánh SCD một cách khoa học và tái lập. Vì vậy dự án phải xin artifact từ tác giả, tự tạo một nghiên cứu regenerated có tên riêng, hoặc chuyển sang benchmark khác.

### Chuyển sang bước tiếp theo

Sau khi so sánh các phương án, dự án chọn CausalDS làm substrate mới. T02 chịu trách nhiệm audit nguồn mới và đóng băng lại toàn bộ thiết kế.

---

## 6. T02 — CausalDS design freeze và release audit

### Vấn đề cần giải quyết

Việc đổi từ NoisyCausal sang CausalDS có thể làm các tài liệu/config cũ xung đột. Đồng thời phải kiểm tra CausalDS có đủ story, observational data, tasks và ground-truth graph hay không.

### Mục đích

- Xác minh artifact CausalDS chính thức và pin version bất biến.
- Định nghĩa lại thiết kế nghiên cứu từ released P0 đến fresh homogeneous P1.
- Đóng băng evidence boundary giữa các graph builder và reasoner.
- Xác định cohort và task panel đủ rõ cho các task sau.

### Công việc đã thực hiện

- Pin GitHub commit `c74671d0a0924efc5bb021fc8966f856d5b80a4f`.
- Pin Hugging Face revision `2880dfa710d08e076055cb0248ef0c534a93b0fa`.
- Ghi license, source URL, file size và SHA-256 của source archive, public catalog và grading catalog.
- Audit 100 scenes, 2.589 tasks và 1.223 Rung-2 tasks.
- Xác định 48 clean scenes; trong đó 33 clean scenes không có latent node phù hợp graph evaluation.
- Đóng băng thiết kế `released P0 → fresh homogeneous P1`.
- Chọn labeling canonical `X000`, `X001`, ... thay vì để semantic names đi vào reasoner/SCD.
- Chọn raw CPDAG làm kết quả SCD chính và deterministic DAG projection làm sensitivity.
- Chọn Hybrid H1 là SCD skeleton + semantic orientation.
- Chọn năm task graph-sensitive theo frozen priority:
  - `one_valid_adjustment_set`;
  - `all_minimal_adjustment_sets`;
  - `minimal_adjustment_set_size`;
  - `n_valid_adjustment_sets`;
  - `forbidden_controls_list`.
- Chọn scene-level paired/clustered analysis và co-equal exploratory outcomes theo phase.

### T02 amendment — Nested P0 cohorts

Thiết kế P0 ban đầu chỉ nhìn 27 scenes có đủ năm task. Sau thảo luận, P0 được sửa thành ba cohort lồng nhau:

```text
Graph cohort: 33 scenes
├── Primary downstream: 27 scenes × 5 tasks
└── Supplementary: 6 scenes, exploratory only
```

Split mục tiêu:

- Graph: dev 8 / holdout 25.
- Primary: dev 7 / holdout 20.
- Supplementary: dev 1 / holdout 5.

Primary và supplementary phân hoạch đúng graph cohort; một scene luôn giữ cùng vai trò dev hoặc holdout ở mọi cohort mà nó thuộc về.

### Điều kiện hoàn thành

- Artifact và version chính thức được pin.
- Cấu trúc public/grading được ghi rõ.
- Bốn graph conditions, CPDAG policy, Hybrid policy và reasoner boundary nhất quán trong tài liệu/config.
- Cohort `33 = 27 + 6` được xác minh.

### Kết quả

- `p0_artifact_ready: true`.
- Cả 33 graph scenes có 16.000 observational rows/scene và 3–7 graph nodes.
- 27 primary scenes có đủ năm task chung.
- Sáu scenes còn lại được giữ lại cho graph metrics và supplementary exploratory analysis.
- P1 chưa bị thay đổi bởi nested-cohort amendment.

### Chuyển sang bước tiếp theo

T02 mới xác minh release-level metadata. T03 cần inventory chi tiết toàn bộ 100 scenes và tạo split tạm thời có thể tái sinh.

---

## 7. T03 — Scene inventory và provisional nested split

### Mục đích

Tạo một danh mục scene đầy đủ và một cách chia dev/holdout tất định, đủ cân bằng để dev đại diện tương đối cho graph cohort nhưng chưa đóng băng exact IDs trước khi kiểm tra parquet ở T04.

### Công việc đã thực hiện

- Inventory đủ 100 scenes.
- Ghi số node, số cạnh, density, loại biến, latent status, observation variant, số dòng, task availability và SCM/mechanism metadata có thể xác minh.
- Áp dụng eligibility rules để tái tạo:
  - graph cohort 33;
  - primary downstream 27;
  - supplementary 6.
- Chọn stratification features:
  - graph size band;
  - graph density band;
  - data type family;
  - structural label;
  - binary-node fraction;
  - special-mechanism-node fraction.
- Dùng thuật toán deterministic nested balance với seed `42`, 64 restarts và lexicographic tie-breaking.
- Bắt buộc primary/supplementary phân hoạch graph cohort và một scene chỉ có một split role.

### Provisional development IDs

Graph development gồm:

```text
scene_000098
scene_000172
scene_000402
scene_000415
scene_000511
scene_000719
scene_000792
scene_000814
```

`scene_000402` là supplementary development scene, nên primary development gồm bảy scene còn lại.

### Điều kiện hoàn thành

- Inventory đủ 100 scenes.
- Split có thể sinh lại từ seed/config.
- Đúng kích thước 8/25, 7/20 và 1/5.
- Không vi phạm nesting hoặc split-role consistency.
- Split vẫn là provisional, chưa tuyên bố freeze trước T04.

### Kết quả

- Selected objective loss `0.329`, thấp hơn seeded-start median `2.683`.
- Maximum numeric absolute standardized mean difference khoảng `0.079` cho graph cohort và `0.029` cho primary cohort.
- Common strata được phủ trong giới hạn kích thước dev.
- Supplementary chỉ có một dev scene nên không thể phủ mọi motif; kết quả của cohort này vẫn phải exploratory.

### Chuyển sang bước tiếp theo

T04 phải đọc và kiểm tra dữ liệu thực của toàn bộ 33 graph scenes. Chỉ khi mọi scene đạt integrity gates thì provisional IDs mới được freeze.

---

## 8. T04 — Data integrity và final cohort freeze

### Mục đích

Chứng minh 33 scenes thực sự dùng được ở cấp parquet/schema/mapping/task và sau đó đóng băng exact scene IDs cùng task manifests.

### Công việc đã thực hiện

- Kiểm tra toàn bộ clean `data.parquet` của 33 graph scenes.
- Đối chiếu số hàng/cột và column order với `schema.json`.
- Kiểm tra dtype, binary support, missingness, NaN, infinity và constant columns.
- Kiểm tra duplicate rows.
- Xác minh public-schema-to-canonical `X000...` mapping.
- Kiểm tra graph/node consistency và latent-free requirement.
- Xác minh đủ năm task trên 27 primary scenes.
- Inventory riêng các task của sáu supplementary scenes.
- Kiểm tra public/grading isolation.
- Sinh và freeze:
  - `p0_frozen_split.json`;
  - `p0_primary_task_manifest.jsonl`;
  - `p0_supplementary_task_manifest.jsonl`;
  - `p0_data_integrity.json`.
- Thêm chế độ `--check` để tái sinh artifact byte-for-byte.

### Điều kiện hoàn thành

- 33/33 scenes đạt mọi integrity gate.
- Không cần loại hoặc thay scene.
- Exact nested memberships và task manifests có hash ổn định.
- Reproduction check sinh lại đúng bytes.

### Kết quả

- `integrity_ready: true`; 33/33 scenes đạt.
- Tổng cộng 528.000 observational rows và 120 columns được kiểm tra.
- Không phát hiện null, NaN, infinity, constant column, binary-support mismatch hoặc duplicate row.
- Primary task manifest có 135 records, đúng `27 × 5`.
- Supplementary manifest có 89 exploratory task records.
- Graph split 8/25, primary split 7/20 và supplementary split 1/5 được freeze chính thức.

### Chuyển sang bước tiếp theo

Khi dev IDs đã freeze, T05 mới được phép so sánh các phương pháp SCD trên đúng tám development scenes.

---

## 9. T05 — Chọn phương pháp SCD/CPDAG và DAG projection

### Vấn đề cần giải quyết

Released P0 có mixed data và heterogeneous mechanisms. Không thể mặc định một thuật toán SCD bất kỳ đáp ứng mọi giả định. Đồng thời output chính phải thể hiện uncertainty thay vì ép thành một DAG tùy ý.

### Mục đích

- Chọn một phương pháp SCD thực thi được trên frozen development scenes.
- Đóng băng assumptions, implementation, parameters và software artifact.
- Giữ CPDAG làm primary output.
- Xác định một consistent DAG projection tất định cho sensitivity analysis.

### Công việc đã thực hiện

- Audit assumptions của các candidate families hỗ trợ mixed/nonlinear discovery.
- Pre-register 18 configurations trước khi dùng development Oracle scoring.
- Chạy toàn bộ configurations trên tám frozen development scenes.
- Exact rerun để kiểm tra determinism.
- Đánh giá ba finalists qua 240 fixed half-sample runs.
- Dùng skeleton F1, CPDAG SHD, compelled-direction precision/recall, half-sample skeleton Jaccard và endpoint agreement.
- Đổi public variable names thành `X000...` trước SCD.
- Không pool observations giữa scenes.
- Pin Tetrad JAR `7.6.11-SNAPSHOT` bằng SHA-256.
- Triển khai deterministic Dor–Tarsi consistent extension với lexicographic tie-breaking.

### Phương pháp được chọn

```text
Algorithm: BOSS
Score: BasisFunctionBicScore
penalty_discount: 1.0
truncation_limit: 3
num_starts: 1
use_data_order: true
primary output: CPDAG
```

### Điều kiện hoàn thành

- Có method/config thắng theo tiêu chí đã đăng ký trước.
- Kết quả hợp lệ và tái lập trên 8/8 dev scenes.
- Raw CPDAG và projection policy được phân biệt rõ.
- Không truy cập holdout hoặc downstream reasoner.

### Kết quả

- `p0_scd_ready: true`.
- Macro skeleton F1: `0.9594`.
- Macro CPDAG SHD: `0.375`.
- Compelled direction precision/recall: `1.0/1.0`.
- Half-sample skeleton Jaccard: `0.9972`.
- Endpoint agreement: `0.9970`.
- Khoảng 90% estimated adjacencies vẫn unresolved theo scene-macro average.

### Giới hạn được ghi nhận

- JAR được hash-pin nhưng vẫn mang nhãn snapshot.
- Basis functions chỉ xấp xỉ một số logic-gate/neural/heterogeneous mechanisms.
- Chỉ có tám development scenes cho method selection.
- Unresolved rate cao nghĩa là reasoner chính phải tôn trọng CPDAG uncertainty; projected DAG không được thay thế raw CPDAG.

### Chuyển sang bước tiếp theo

T05 mới tạo representation tối thiểu. T06 phải biến nó thành một graph contract dùng chung cho cả LLM, SCD, Hybrid, Oracle, reasoner và metrics.

---

## 10. T06 — Canonical graph contract

### Mục đích

Ngăn mỗi graph builder tự tạo schema, serialization, provenance và validation khác nhau. Mọi graph source phải đi qua một contract duy nhất trước khi reasoner hoặc metrics sử dụng.

### Công việc đã thực hiện

- Freeze `fourgraph.graph.v1` cho graph artifacts.
- Freeze `fourgraph.variable_map.v1` cho public-name-to-`X000...` mapping.
- Hỗ trợ cả directed và undirected edges.
- Canonicalize node/edge ordering và JSON serialization.
- Tách hai hash:
  - `graph_sha256`: chỉ hash cấu trúc graph;
  - `artifact_sha256`: hash cấu trúc cùng provenance/audit.
- Tạo evidence allowlists theo graph method.
- Tạo adapters riêng cho LLM, SCD, Hybrid và Oracle nhưng cùng output type.
- Validate DAG acyclicity.
- Validate CPDAG là completed PDAG thực sự, không chỉ là một PDAG orient được.
- Validate projected DAG và Hybrid child so với exact parent CPDAG:
  - cùng scene/node universe;
  - cùng skeleton;
  - không đảo compelled direction;
  - đúng parent hash;
  - đúng Markov equivalence class;
  - audit đúng từng unresolved edge.
- Tạo provenance-blind reasoner view và normalized metrics view.
- Khóa LF line endings cho hashed JSON/YAML/schema/manifest trên Windows.

### Điều kiện hoàn thành

- Mọi graph method tạo cùng artifact schema/version.
- Serialization và hash tất định.
- Validators bắt được DAG/CPDAG và parent-child violations.
- Reasoner không nhìn thấy provenance/evidence source.
- Artifact T05 không bị thay đổi.

### Kết quả

- Các fixture LLM/SCD/Hybrid/Oracle dùng chung node universe và artifact type.
- Hai artifact có cùng cấu trúc nhưng khác nguồn có cùng `graph_sha256` và khác `artifact_sha256`.
- Reasoner payload giống nhau khi cấu trúc giống nhau, bất kể provenance.
- Cả tám T05-selected CPDAGs được adapter sang contract v1.
- T05 freeze hashes giữ nguyên và holdout không bị truy cập.

### Chuyển sang bước tiếp theo

Sau khi có graph contract, T07 xây đường nạp ground truth riêng để Oracle không thể rò vào graph builders.

---

## 11. T07 — Grading-only Oracle loader

### Mục đích

Cung cấp `G_ORACLE` cho graph metrics và Oracle condition, đồng thời chứng minh LLM/SCD/Hybrid không thể dùng grading ground truth để xây graph.

### Công việc đã thực hiện

- Tạo typed grading purposes và artifact allowlists.
- Chỉ cho Oracle purpose đọc `ground_truth.json`.
- Dùng public schema order để tạo canonical `X000...` mapping.
- Kiểm tra observed nodes, latent nodes, mapping và named edges.
- Từ chối scene có latent node trong P0 graph cohort.
- Chuyển Oracle DAG sang `fourgraph.graph.v1`.
- Loader không trả raw grading document.
- Audit chỉ lưu count/hash/validity, không lưu edge list.
- Loại bỏ grading dependency khỏi runtime SCD module.
- Thêm negative runtime và AST dependency tests để chống Oracle leakage.

### Điều kiện hoàn thành

- 8/8 development Oracle graphs nạp thành canonical DAG hợp lệ.
- Không trả raw ground truth hoặc answer fields.
- Non-Oracle code path không có quyền grading.
- Không truy cập holdout.

### Kết quả

- `oracle_loader_ready: true`.
- Tám Oracle DAGs hợp lệ, có 3–7 nodes và 2–7 edges.
- Versioned audit không chứa edge list hoặc raw grading fields.
- Không đọc grading test values, graph images hoặc task scoring data.
- T05 freeze anchors giữ nguyên.

### Chuyển sang bước tiếp theo

T08 có thể xây `G_LLM` từ public semantics và dùng T06 adapter, trong khi T07 bảo đảm Oracle vẫn ở grading boundary.

---

## 12. T08 — Public-story-only LLM graph builder

### Mục đích

Sinh một scene-level `G_LLM` DAG chỉ từ public story, public variable semantics và schema types; không dùng observational data, task/query, gold answer hoặc Oracle.

### Thiết kế đã đóng băng

- Provider: OpenAI Responses API.
- Model snapshot: `gpt-5.4-nano-2026-03-17`.
- SDK: `openai==3.6.0`.
- `reasoning_effort=none`.
- `temperature=0`.
- `service_tier=default`.
- `store=false`.
- Strict JSON Schema output.
- API key lấy từ biến môi trường `OPENAI_API_KEY`, không ghi secret vào repo.

### Công việc đã thực hiện

- Tạo public-only loader cho story và schema.
- Tạo all-pairs prompt: LLM phải xét mọi unordered pair đúng một lần.
- Response cho mỗi cặp là `left_causes_right`, `right_causes_left` hoặc `no_direct_edge`, kèm confidence và rationale.
- Phân biệt direct edge với indirect ancestry.
- Strict parser kiểm tra exact pair coverage, unknown fields/nodes, duplicates và confidence range.
- Final graph phải là DAG.
- Invalid response chỉ được retry trong budget; không có heuristic repair/fallback graph.
- Raw prompt, response và provider payload được lưu ngoài Git.
- Tạo replay backend kiểm tra prompt hash và tái sinh artifact byte-for-byte.

### Live execution

- Smoke test xác nhận OpenAI key/project hoạt động.
- Structured-output schema được sửa trước successful graph run khi phát hiện thiếu `type` ở constant version field.
- Gate scene `scene_000098` chạy thành công.
- Resume mode replay gate và chỉ gọi bảy scenes còn lại.

### Điều kiện hoàn thành

- Đủ 8/8 development DAGs hợp lệ.
- Model/config/prompt/schema được hash-freeze.
- Raw logs ở ngoài Git nhưng replay được.
- Không truy cập holdout hoặc forbidden evidence.

### Kết quả

- `t08_complete: true`.
- `llm_graph_builder_ready: true`.
- 8/8 development DAGs hợp lệ.
- 8 API calls, 0 validation retries.
- 7.005 input tokens và 2.564 output tokens.
- Holdout: 0/25.

### Chuyển sang bước tiếp theo

T09 chạy chính xác phương pháp SCD đã freeze ở T05 để tạo graph artifacts cùng contract với `G_LLM`.

---

## 13. T09 — Development `G_SCD` graph artifacts

### Mục đích

Biến lựa chọn phương pháp ở T05 thành raw CPDAG artifacts và projected-DAG sensitivity artifacts cho tám development scenes.

### Evidence boundary

SCD chỉ được đọc:

- clean `data.parquet` của đúng scene;
- `schema.json` để lấy column order và variable types.

SCD không được đọc story, task/query, LLM graph, Oracle/grading hoặc holdout.

### Công việc đã thực hiện

- Đổi variable names thành `X000...`.
- Không pool scenes.
- Binary variables giữ exact `0/1` discrete categories.
- Continuous variables được per-scene sample z-score với `ddof=1`.
- Chạy đúng frozen `BOSS + BasisFunctionBicScore` configuration.
- Pin runtime Python, Java, JPype, NumPy, PyArrow và Tetrad JAR hash.
- Tạo raw SCD CPDAG artifact cho mỗi scene.
- Tạo deterministic Dor–Tarsi projected DAG sensitivity child.
- Ghi exact parent hash và audit mọi arbitrary orientation.
- Gate `scene_000098` chạy hai lần trước full build.

### Điều kiện hoàn thành

- 8/8 raw CPDAGs và 8/8 projected DAGs.
- Raw results trùng T05-selected graph set.
- Parent relationships và projection traces hợp lệ.
- Full rerun byte-for-byte.
- Không vi phạm evidence boundary.

### Kết quả

- `t09_complete: true`.
- `scd_graph_builder_ready: true`.
- Raw CPDAG: 8/8.
- Projected DAG: 8/8.
- Tổng raw graph có 31 adjacencies:
  - 4 directed;
  - 27 undirected.
- Pooled unresolved rate là 87,1%; T05 scene-macro unresolved rate là 90%.
- Holdout: 0/25.

### Chuyển sang bước tiếp theo

T10 dùng raw CPDAG của T09 làm parent và chỉ cho semantic LLM xử lý các direction còn unresolved.

---

## 14. T10 — Hybrid H1 development graph builder

### Câu hỏi của H1

> Khi SCD đã quyết định skeleton và compelled directions, public semantics có giúp chọn direction tốt hơn cho các cạnh thống kê chưa xác định hay không?

### Mục đích

Tạo `G_HYBRID` với attribution sạch: khác biệt giữa raw SCD và Hybrid chỉ nằm ở cách định hướng unresolved edges. Hybrid không phải union, voting hoặc graph repair giữa `G_LLM` và `G_SCD`.

### Evidence boundary

Hybrid được đọc:

- raw T09 SCD CPDAG;
- public story;
- public variable names/types/semantics và canonical mapping.

Hybrid không được đọc:

- observational table trực tiếp;
- T08 `G_LLM` artifact;
- T09 projected DAG;
- task/query/gold answer;
- Oracle/grading;
- holdout.

### Công việc đã thực hiện

- Tái sử dụng đúng T08 OpenAI model/configuration, nhưng không tái sử dụng T08 graph output.
- Prompt chỉ đưa compelled edges và exact unresolved edge list.
- LLM phải trả một direction cho mỗi unresolved pair, kèm confidence và semantic rationale.
- Không cho phép `no_edge` vì skeleton đã freeze từ SCD.
- Validate:
  - exact unresolved-pair coverage;
  - không thêm/xóa adjacency;
  - không đảo compelled direction;
  - không tạo cycle;
  - không tạo incompatible unshielded collider;
  - final DAG thuộc đúng parent CPDAG equivalence class;
  - exact parent artifact hash;
  - audit từng unresolved edge đúng một lần.
- Không dùng heuristic repair hoặc projected-DAG fallback.
- Chạy hardest gate `scene_000511` trước vì có chín unresolved edges.
- Resume gate rồi gọi bảy scenes còn lại.

### Điều kiện hoàn thành

- 8/8 Hybrid DAGs hợp lệ.
- 27/27 unresolved edges được định hướng và audit.
- Skeleton/compelled directions/parent relations không đổi.
- Raw logs replay byte-for-byte.
- Không truy cập holdout hoặc forbidden evidence.

### Kết quả

- `t10_complete: true`.
- `hybrid_graph_builder_ready: true`.
- 8/8 development Hybrid DAGs.
- 27/27 orientation decisions có confidence và rationale.
- 8 API calls, 0 validation retries.
- 7.350 input tokens và 1.857 output tokens.
- Skeleton changes: 0.
- Compelled-direction changes: 0.
- Parent/equivalence validation: 8/8.
- Holdout: 0/25.

### Chuyển sang bước tiếp theo

T10 chỉ chứng minh builder đúng contract, chưa đánh giá graph accuracy. T11 dùng grading-only Oracle để tính structural metrics mà không được sửa lại T08–T10 sau khi nhìn kết quả.

---

## 15. T11 — Development graph metrics

### Mục đích

So sánh chất lượng cấu trúc của năm graph views trên đúng tám development scenes:

1. `G_LLM` DAG;
2. raw `G_SCD` CPDAG;
3. projected `G_SCD` DAG sensitivity;
4. `G_HYBRID` DAG;
5. grading-only `G_ORACLE` DAG sanity baseline.

T11 không chạy reasoner, không đọc tasks và không dùng kết quả để điều chỉnh graph builders.

### Metric contract đã đóng băng

Metric chung:

- skeleton precision, recall và F1;
- adjacency false positives/false negatives;
- skeleton SHD;
- graph validity và node-set consistency.

Raw CPDAG metrics:

- correct/incorrect/missed compelled directions;
- compelled precision/recall;
- unresolved count/rate;
- CPDAG state SHD.

DAG metrics:

- directed-edge precision, recall và F1;
- orientation accuracy trên common true adjacencies;
- SHD và normalized SHD.

Conventions:

- Mọi metric đọc `GraphArtifact.metrics_view()`.
- Skeleton SHD = adjacency FP + FN.
- DAG reversal có SHD cost bằng 1.
- CPDAG state phân biệt absent, undirected, forward và reverse.
- SHD normalization chia cho `n choose 2`.
- Aggregation là equal-weight scene macro.
- Raw CPDAG không bao giờ bị âm thầm project để tính DAG metric.
- Projected SCD luôn được gắn nhãn sensitivity.

### Hybrid error attribution

T11 tách lỗi Hybrid thành:

- skeleton errors kế thừa từ SCD;
- compelled-direction errors kế thừa từ SCD;
- semantic decisions đúng/sai trên unresolved true adjacencies;
- unresolved edges không đánh giá được vì adjacency SCD vốn là false positive;
- khác biệt giữa semantic orientation và deterministic projection.

### Oracle boundary

- Oracle DAG được nạp trong memory qua T07 grading-only capability.
- Metric records chỉ lưu hashes, counts và metric values.
- Oracle edge list không được persist trong T11 outputs.

### SID/AID decision

SID và AID chưa có implementation được pin và kiểm chứng trong T11. Vì vậy:

- status là `unavailable`;
- value là `null`, không phải `0`;
- raw CPDAG không bị project ngầm để cố tính metric;
- Outcome E được giữ là unavailable cho tới khi compatibility gate đạt.

### Điều kiện hoàn thành

- Năm graph views × tám scenes = 40 records.
- CPDAG/DAG metric applicability đúng loại.
- Hybrid attribution đầy đủ.
- T07–T10 hashes giữ nguyên.
- Không LLM call, không task/query access, không builder tuning, không holdout.
- `--check` tái sinh outputs byte-for-byte.

### Kết quả mô tả trên development

| Condition | Skeleton F1 | Directed F1 | Orientation accuracy / unresolved rate |
|---|---:|---:|---:|
| `G_LLM` | 1.000 | 0.975 | Orientation accuracy 0.975 |
| `G_SCD_RAW` | 0.959 | Không áp dụng | Unresolved rate 0.900 |
| `G_SCD_PROJECTED` | 0.959 | 0.225 | Orientation accuracy 0.234 |
| `G_HYBRID` | 0.959 | 0.918 | Orientation accuracy 0.958 |
| `G_ORACLE` | 1.000 | 1.000 | Orientation accuracy 1.000 |

Hybrid attribution trên 27 unresolved edges:

- 24 edges có true Oracle adjacency và đánh giá được direction.
- Hybrid semantic orientation đúng 23/24, sai 1/24.
- Deterministic projection đúng 5/24, sai 19/24.
- Ba unresolved edges còn lại là inherited false-positive SCD adjacencies.
- Hybrid và projection khác nhau trên 18 edges.
- Semantics tốt hơn projection trên 18 edges và không tệ hơn trên edge nào trong development set.

### Cách diễn giải đúng

Các số trên chỉ là descriptive development diagnostics:

- chỉ có tám development scenes;
- chưa có clustered inference hoặc significance testing;
- gần-ceiling `G_LLM` và Hybrid có thể cho thấy public stories tương đối dễ;
- không được dùng kết quả T11 để sửa prompt, model, SCD hoặc Hybrid ở T08–T10;
- kết luận chính thức phải chờ frozen holdout workflow.

### Kết quả kỹ thuật

- `t11_complete: true`.
- `structural_graph_metrics_ready: true`.
- 40/40 records được sinh.
- 104/104 repository tests đạt tại thời điểm hoàn thành T11.
- T04 và T06–T11 freeze/replay checks đạt.
- Holdout: 0/25.

---

## 16. Trạng thái dự án sau T11

Sau T11, dự án đã hoàn thành ba lớp nền tảng theo đúng thứ tự:

```text
Artifact và dữ liệu
T01 → T02 → T03 → T04

Graph construction contract và builders
T05 → T06 → T07 → T08 → T09 → T10

Structural evaluation
T11
```

Các thành phần hiện đã sẵn sàng:

- official CausalDS provenance và raw artifact hashes;
- frozen nested P0 cohorts và task manifests;
- frozen SCD method và deterministic projection;
- canonical graph/variable-map contracts;
- grading-only Oracle loader;
- development `G_LLM`, raw/projected `G_SCD` và `G_HYBRID` artifacts;
- development structural metric records và Hybrid error attribution.

Các thành phần chưa thực hiện đến hết T11:

- fixed downstream reasoner;
- conservative CPDAG task semantics và scorers;
- development downstream reasoning results;
- holdout graph construction/evaluation;
- scene-clustered inference và BH correction;
- fresh homogeneous P1 generation;
- SID/AID implementation được pin và kiểm chứng.

Bước tiếp theo là refinement có version của T12 trước khi xác nhận T13 và mở holdout.

---

## 17. T12 — Fixed reasoner và scorers

### Mục đích

T12 nối các graph artifacts của T08–T10 với downstream tasks bằng đúng một reasoner cố định. Chỉ graph payload thay đổi; model, query, glossary, prompt, parser và scorer không đổi giữa các graph conditions.

### Thực hiện

- Rút treatment, outcome và candidate controls từ public query rồi đổi sang `X000...`; phần background/story không đi vào prompt.
- Glossary chỉ giữ canonical ID và variable type, không giữ public semantic name.
- Reasoner graph chỉ giữ graph type, nodes và edges; source label/provenance bị loại bỏ.
- Liệt kê chính xác mọi DAG extension tương thích với raw CPDAG và áp dụng conservative/invariance semantics.
- Tách grading-only official target khỏi reasoner path bằng capability `SCORING`.
- Chạy cùng Gemma `gemma-4-31b-it`, temperature 0, trên 7 scenes × 5 tasks × 5 graph conditions = 175 records.
- Lưu raw calls ngoài Git và xác nhận replay sinh records/audit byte-for-byte.

### Kết quả và kết luận

- 175/175 final responses parse được; 35 calls cần retry, tổng cộng 39 validation retry attempts.
- 31 raw-CPDAG targets là `undetermined`.
- Accuracy toàn bộ records: oracle-answer 0.446; uncertainty-aware 0.423.
- Riêng `G_ORACLE`: 19/35 = 0.543 cho cả hai metric.
- Holdout vẫn 0/25.

Contract, engine CPDAG và scorers đã hoàn thành, nhưng reasoner hiện tại không qua sanity gate khoa học. Cần đăng ký T12 v2 (prompt refinement có nguyên tắc hoặc reasoner mạnh hơn), kiểm tra lại trên development và chỉ freeze khi Oracle condition đủ tin cậy.

### T12 v2 design amendment

T12 v1 được giữ nguyên làm diagnostic baseline. Amendment bổ sung 150 synthetic conformance cases không dùng CausalDS answers, năm task-specific response schemas, cache theo canonical input và Pearl back-door sensitivity. Official và standards-based targets bất đồng 6/28 development adjustment cases. Chưa chọn/call model v2 và holdout vẫn chưa được truy cập.

### T12 v2 — kiểm tra lại Gemma

Gemma `gemma-4-31b-it` được chạy lại trên toàn bộ 150 synthetic cases sau khi đăng ký trước các sanity gate. Parser task-specific xử lý được 150/150 output, nhưng accuracy chỉ đạt 20/150 (0,133); DAG 0,107, CPDAG invariant 0,200 và CPDAG undetermined 0,114. First-attempt schema compliance đạt 0,867. Chỉ gate parse thành công, nên Gemma không được chuyển sang 35 Oracle-development tasks và holdout vẫn 0/25. Raw calls nằm ngoài Git; cache replay tái sinh score records/audit byte-for-byte.

### T12 v2 — candidate GPT-5.4 Mini

Candidate mới chỉ thay model/provider, còn prompt v2, graph encoding, nhãn `X000...`, năm schema, 150 synthetic cases và strict scorer đều giữ nguyên. Trước live run, một solver độc lập tái tạo đúng 150/150 targets và panel 20 cases xác nhận đủ năm task, DAG/CPDAG invariant/CPDAG undetermined cùng các sentinel đặc biệt.

OpenAI Structured Outputs cần một provider adapter cho tập con JSON Schema; local strict parser vẫn không đổi. Trong official smoke, `SYN001` hoàn tất và đúng, nhưng `SYN024` dùng hết 4096 reasoning tokens ở cả ba attempts mà không sinh visible JSON. Smoke dừng sau bốn captured calls, chi phí standard ước tính USD 0,059094. Vì technical gate thất bại, 150-case conformance, 35 Oracle-development calls, full development matrix và holdout đều không được chạy. Kết quả chưa cho biết accuracy của Mini; nó chỉ loại cấu hình `reasoning_effort=high, max_output_tokens=4096`. Bất kỳ thay đổi effort/token nào phải tạo candidate mới.

### T12 v2 — Mini-B high/8192 diagnostic

Mini-B được đăng ký riêng và chỉ tăng `max_output_tokens` từ 4096 lên 8192. Cả 10 smoke cases completed và parse được ngay attempt đầu, không retry; chi phí captured ước tính USD 0,147282. `SYN024` trả đúng sau 5414 reasoning tokens, xác nhận failure trước chủ yếu do token ceiling. Tuy nhiên `SYN144` dùng 7937 reasoning tokens, nên headroom 8192 vẫn mỏng. Smoke đúng 9/10 nhưng accuracy chỉ mang tính diagnostic; project dừng để review ngân sách trước 150-case gate. Oracle-development, full matrix và holdout vẫn chưa chạy.

### T12 v2 — Mini-C high/10240 headroom diagnostic

Mini-C chỉ tăng ceiling từ 8192 lên 10240 và đăng ký trước utilization gate <=80%. Mười case cuối cùng đều completed/parsed, nhưng `SYN054` attempt đầu dùng trọn 10240 reasoning tokens mà không sinh output; retry mới đúng với 3324 tokens. Vì all-call utilization đạt 100%, technical headroom gate thất bại. Diagnostic accuracy là 8/10 và tiếp tục cho thấy provider variability. Project không chạy tiếp 150 cases, Oracle-development, full matrix hay holdout.

### T12 v2 — Mini-D medium/10240 effort diagnostic

Mini-D giữ nguyên ceiling 10240, prompt v2 và mọi scientific contract của Mini-C; thay đổi duy nhất là reasoning effort từ high xuống medium. Cả 10 smoke cases completed/parsed ở attempt đầu, không retry; maximum utilization giảm từ 100% xuống 36,26%, tổng reasoning tokens giảm khoảng 52,6%, và estimated cost giảm từ USD 0,1674885 xuống 0,082014. Đây là bằng chứng có kiểm soát phù hợp với giả thuyết high effort gây reasoning runaway trong lượt smoke đã quan sát, nhưng chưa phải bằng chứng rằng high luôn thất bại.

Strict accuracy của Mini-D là 7/10 so với Mini-C 8/10 và Mini-B 9/10. Vì đây chỉ là 10 cases và API có biến thiên, accuracy không được dùng làm scientific gate. Sau khi có quyết định GO riêng, Mini-D được resume trên đủ 150 prospective cases mà không thay đổi candidate.

Full conformance hoàn tất 150/150 ngay attempt đầu, không retry/incomplete; maximum utilization 50,47% và chi phí ước tính USD 0,5458095. Strict accuracy đạt 105/150 = 70%: DAG 56%, CPDAG answered 92,5%, CPDAG undetermined 74,29%. Theo task, one-valid 26/30, all-minimal 25/30, minimal-size 24/30, count-valid 23/30, forbidden-controls 7/30. Chỉ các gate parse/schema và CPDAG-answered qua; overall, DAG, CPDAG-undetermined và per-task gates thất bại. Mini-D không được chạy Oracle-development, full matrix hay holdout.

### T12 v3 — task-specific prompt contract

V3 giữ nguyên Mini-D (`medium`, 10240) và canonical JSON edge list, nhưng thay prompt generic bằng shared base cộng đúng một module của task hiện tại. Base biến quy ước CausalDS thành tám bước thao tác trên từng DAG, giải thích nội bộ trường hợp không có valid set là `no_valid_adjustment_set`, rồi chỉ xuất chuỗi official `no_backdoor`. Bảng sentinel và các ví dụ synthetic ngắn phân biệt `[]`, `[[]]`, `0`, `no_backdoor` và `undetermined`; forbidden-controls có rule precedence riêng.

Assembler, component hashes và prompt manifest đã hoàn thành; không có API call. Suite v2 đã mở được hạ xuống diagnostic-only. Config khóa live execution cho tới khi suite v3 mới với seed 1203 được sinh deterministically, audit độc lập và pin hash. Holdout vẫn chưa được truy cập.

### T12 v3 — sealed suite, smoke và full conformance

Suite mới gồm 150 five-node cases, 30/task, chia 90 DAG answered, 30 CPDAG invariant và 30 CPDAG undetermined. Production scorer và independent solver khớp 150/150; sentinel balance là 40 valid-nonempty, 40 valid-empty, 40 no-valid và 30 undetermined. Không case nào dùng CausalDS story/answer hoặc holdout.

Live smoke đạt engineering gate với 10/10 parsed/schema-valid ở attempt đầu, diagnostic accuracy 9/10 và chi phí USD 0,1198875. Sau lifecycle-only authorization và preflight 150/150, full conformance giữ 10 smoke cache responses rồi gọi 140 cases còn lại.

Kết quả full: 146/150 = 97,33%; DAG 87/90, CPDAG invariant 29/30, CPDAG undetermined 30/30. Mọi prospective scientific gate đều đạt và mỗi task đạt ít nhất 28/30. Có năm incomplete attempts chạm ceiling 10240; cả năm retry thành công, nên first-attempt compliance vẫn đạt 145/150 nhưng full-run headroom diagnostic thất bại. Chi phí ước tính USD 1,53063675.

### T12 v3 — Oracle-development gate

Sau khi có authorization riêng, một candidate kế nhiệm đã khóa đúng 7 primary development scenes, 5 task/scene và duy nhất graph condition `G_ORACLE`. Preflight xác nhận 35/35 official targets tương đương với target tính từ Oracle DAG, 12 record bắt buộc dùng sentinel rỗng, và không truy cập holdout.

Live run hoàn tất 35/35 call ngay attempt đầu, không retry/incomplete. Kết quả đạt 34/35 = 97,14%; `one_valid_adjustment_set` đạt 6/7, bốn task còn lại đạt 7/7, và 12/12 sentinel rỗng đúng. Case sai duy nhất trả empty set cho một graph còn fork confounding qua `X000`. Chi phí standard ước tính USD 0,0847065; reasoning-token median 313 và maximum utilization chỉ 12,08%.

Mọi gate áp dụng đều đạt; cache replay tái sinh score/audit byte-for-byte mà không gọi API. T12 v3 chuyển sang full development matrix bằng một authorization riêng.

### T12 v3 — full development matrix

Matrix dùng đúng 7 primary development scenes, năm task và năm graph conditions, tạo 175 records. Canonical caching cho thấy chỉ có 105 input duy nhất: 35 identities được kế thừa từ Oracle gate, 70 calls mới được thực hiện, và 70 records trùng input dùng lại response. Tất cả output hợp lệ ngay attempt đầu, không retry hay incomplete.

Oracle-answer accuracy lần lượt là `G_ORACLE` 34/35, `G_LLM` 33/35, `G_HYBRID` 31/35, projected `G_SCD` 6/35 và raw `G_SCD` 4/35. Uncertainty-aware correctness lần lượt là 34/35, 34/35, 32/35, 33/35 và 35/35. Raw CPDAG đạt uncertainty-aware cao vì 31/35 query thực sự undetermined; projected DAG được reasoner đọc đúng nhưng thường không khớp Oracle answer. Đây mới là mô tả development, chưa phải phân tích thống kê cuối.

Incremental cost ước tính USD 0,5237385. Replay từ cache khớp byte-for-byte và mọi integrity gate đều đạt. Reasoner được freeze cho holdout, `t13_eligible: true`; T13 và holdout vẫn chưa được chạy.

---

## 18. T13 — Đóng băng P0 holdout execution

T13 khóa chính xác 25 graph-holdout scenes, gồm 20 primary và 5 supplementary. Năm task, năm graph conditions, model snapshots, prompts, schemas, cache/retry/failure policy, output counts và paired scene-clustered/BH analysis đều được hash-pin. Bước này không gọi API, không đọc holdout content/gold/Oracle edges và không tạo accuracy; nó chỉ cấp quyền chạy T14 đúng cấu hình.

## 19. T14 — Mở P0 holdout đúng một lần

T14 chạy logical resumable execution đã đăng ký: 25 LLM DAG, 25 raw CPDAG, 25 projected DAG và 23 Hybrid DAG thành công; hai Hybrid conditions kết thúc bằng terminal failure theo đúng no-fallback policy. Toàn bộ 125 graph rows và 500 downstream rows đạt trạng thái terminal và replay offline được; không có retry nghiên cứu hay retuning sau khi thấy kết quả.

## 20. T15 — Phân tích P0 holdout

T15 dùng scene làm đơn vị độc lập, chạy 5.000 paired cluster-bootstrap replicates và BH correction. Hybrid vượt deterministic projection rõ về directed F1 và official downstream accuracy; tuy nhiên Hybrid không chứng minh được ưu thế downstream so với standalone LLM. Uncertainty-aware correctness được báo riêng và không bị diễn giải nhầm thành graph truth.

## 21. T16 — Chốt findings và quyết định P0

T16 giữ cả kết quả thuận lợi, null, adverse, hai Hybrid failures và residual Oracle-reasoner error. Quyết định là `REFINE`: không mở rộng nguyên H1 thành P1, mà đăng ký một P1 mới tập trung vào global CPDAG consistency và selective abstention.

## 22. T17 — Đóng băng thiết kế P1 Hybrid

T17 khóa trước 100 fresh homogeneous SCMs, exact five-task contract, query/motif/noise balance, BOSS raw CPDAG chính, DirectLiNGAM structural sensitivity, ba semantic doses (`full`, `partial`, `ambiguous`), H1 baseline, H2-Forced và H2-Selective. H2-Selective trả nguyên raw CPDAG khi không đủ chắc chắn; không xóa observation như missing.

Protocol cũng khóa 12 structural views/scene, 11 downstream views/scene, hypotheses, metrics, scene-paired statistics, threshold grid và forbidden selection inputs. T17 tạo 0 scene, gọi 0 API, chưa implement H2 và không truy cập P1 holdout. Bước duy nhất được phép tiếp theo là T18 xây generator/inventory và đóng băng exact 20/80 IDs; live semantic calls và H2 vẫn bị chặn.

## 23. T18 — Sinh fresh-SCM substrate và exact split P1

T18 hiện thực hóa contract T17 thành 100 linear non-Gaussian SCMs có 5–7 observed continuous nodes, 500 task fixtures với hai solver khớp 500/500, `N=2000` cho mọi scene và nested raw samples trên 20 sensitivity scenes. Exact split được khóa ở 20 development / 80 holdout; toàn bộ 480 raw artifacts và versioned manifests replay byte-for-byte. Không model hay phương pháp nghiên cứu nào được chạy.

## 24. T19 — Semantic-story variants và blinded stimulus audit

T19 sinh cùng một alias map và clause order cho ba variants của mỗi SCM. `full` định hướng toàn bộ 684 edge claims; `partial` định hướng 367/684 theo round-half-up ở từng scene và dùng association language cho phần còn lại; `ambiguous` định hướng 0/684. Parser độc lập đọc ngược public text xác nhận không false direction, nonedge claim, canonical ID, arrow hay generator metadata.

Panel mù dùng đúng 20 development scenes, shuffle ba slot mỗi scene và loại scene/study ID, split, variant, mapping, graph truth cùng seed. Internal text QA đạt 20/20 scenes, phân loại đúng 60/60 evidence slots và naturalness tối thiểu 4/5. Đây không phải independent external human validation và không được trình bày như vậy. Holdout stories chỉ được sinh/kiểm tra tự động, không xuất hiện trong panel. T19 gọi 0 API, không chạy SCD/LLM/reasoner/H1/H2 và chỉ cấp quyền T20 offline conformance.

## 25. T20 — H2 offline implementation và conformance

T20 hiện thực hóa hai biến thể đã đăng ký. `H2-Forced` chọn DAG có tổng log-probability hướng cạnh lớn nhất trong toàn bộ các consistent extensions của CPDAG; vì tối ưu toàn cục, nó không được định hướng từng cạnh độc lập nếu lựa chọn đó tạo cycle hoặc collider trái CPDAG. `H2-Selective` chỉ trả DAG cưỡng ép khi normalized margin đủ lớn và conflict mass đủ thấp; nếu không, nó trả lại chính xác CPDAG cha để bảo toàn uncertainty.

Kiểm định hoàn toàn synthetic gồm 150 valid cases cân bằng theo 3–7 node, năm motif và sáu chế độ semantic preference; thêm 30 malformed cases cho strict validator. Production solver duyệt tổ hợp hướng cạnh, còn independent solver duyệt topological orders. Hai cách độc lập khớp 150/150 forced decisions và 3.000/3.000 selective decisions trên lưới 20 threshold pairs; 30/30 malformed inputs bị từ chối. Tất cả kết quả giữ nguyên node set, skeleton, compelled directions, acyclicity và unshielded colliders; input không bị mutate.

Trong 39/150 valid cases, chọn hướng mạnh nhất riêng lẻ cho từng cạnh tạo graph không hợp lệ, cho thấy nhu cầu của global consistency. Con số 1.783 accept và 1.217 abstain trên toàn lưới chỉ kiểm tra implementation; T20 không dùng chúng để chọn threshold hay claim hiệu quả khoa học. Bước này gọi 0 API, không đọc P1 SCM/story, không chạy development hoặc holdout. Audit chỉ cấp quyền T21 chạy trên development để xây graph và chọn threshold theo protocol đã đóng băng.

## 26. T21 — P1 development execution và threshold gate

T21 chạy đúng 20 development scenes, gọi snapshot GPT-5.4 Nano đã khóa để tạo 60 semantic-preference artifacts dùng chung cho H1/H2 và 20 standalone full-story DAGs. Tổng cộng có 80 API attempts, 50.362 input tokens và 25.080 output tokens; raw logs nằm ngoài Git. BOSS, deterministic projection và DirectLiNGAM cũng được chạy trên cùng observational samples. Không task answer, downstream ranking hay holdout input nào được dùng.

H2-Forced giữ graph hợp lệ trên 20/20 scenes cho cả ba evidence variants; H1 local chỉ hợp lệ 8/20 scenes. Orientation precision của H2-Forced giảm có thứ tự từ full `0,761`, partial `0,612` xuống ambiguous `0,463`. Mean directed F1 development lần lượt là projection `0,623`, H2-Forced-Full `0,724`, standalone LLM `0,812` và DirectLiNGAM `0,994`; đây chỉ là development diagnostics.

Không cặp nào trong lưới 20 thresholds đạt gate precision `0,95`. Candidate tốt nhất đạt `0,90` nhưng coverage chỉ khoảng `0,0498` (9/10 directions đúng). Vì vậy T21 không chọn threshold, không materialize H2-Selective chính thức và không cấp quyền T22/T23. Theo protocol, bước kế tiếp phải là amendment có version mới trên development; không được hạ gate sau khi nhìn kết quả hoặc mở holdout.

## 23. T18 — Fresh-SCM generator và inventory P1

T18 hiện thực hóa đúng protocol T17 bằng seed `1701`: 100 linear non-Gaussian SCMs với 5–7 observed continuous nodes, cân bằng năm motif và ba noise families. Mỗi scene có `N=2000`; 20 scene có thêm raw nested prefixes `N=500/10000`. Mỗi Oracle CPDAG còn ít nhất hai cạnh chưa định hướng, tạo variation cần thiết cho nghiên cứu uncertainty và semantic orientation.

Generator tạo đúng năm task cho mỗi scene. Production solver và một independent solver khớp 500/500 expected targets. Inventory cân bằng bốn query strata, split deterministic khóa 20 development / 80 holdout với maximum rounded marginal deviation bằng 1, thấp hơn gate 2. Hai namespace được ánh xạ một-một: `P1S000…P1S099` cho study và `scene_100000…scene_100099` cho graph contract.

Toàn bộ 480 raw files cùng manifests/config/seeds được hash; `--check` tái sinh byte-for-byte. Raw SCMs, gold task records và arrays nằm ngoài Git. T18 gọi 0 API, không chạy SCD/LLM/Hybrid/H2 và không chấm holdout. Audit chỉ cấp quyền T19 tạo ba semantic story variants; mọi live method execution vẫn bị khóa.

## 27. T21 Amendment v2 — tách lỗi elicitation, model và skeleton

Amendment v2 trước hết tạo 120 case synthetic không chứa P1 để kiểm tra ba nghĩa: story ủng hộ trái→phải, phải→trái, hoặc không xác định chiều. Prompt v2 và GPT-5.4 Nano đạt 120/120, nên lỗi development không thể giải thích đơn giản bằng việc model đảo nghĩa xác suất trái/phải.

Trên cùng 20 development scenes, hệ thống chỉ thay prompt preference sang v2, giữ nguyên BOSS, model, H1/H2, threshold grid và gate 0,95. Full H2-Forced đạt orientation precision `0,776`; best H2-Selective chỉ đạt `0,737` ở coverage `0,0945`, nên gate tiếp tục thất bại. Standalone LLM giảm theo lượng bằng chứng: directed F1 full `0,812`, partial `0,704`, ambiguous `0,471`.

Diagnostic thay BOSS CPDAG bằng Oracle CPDAG làm precision tăng từ `0,806` lên `0,903` với full evidence và từ `0,716` lên `0,847` với partial evidence. Kết quả cho thấy BOSS skeleton là một bottleneck, nhưng semantic orientation cũng chưa đủ chính xác ngay cả khi parent CPDAG đúng. Comparator và diagnostic không tham gia chọn threshold. Holdout vẫn đóng; T22 không được cấp quyền và không được tiếp tục prompt tuning thích nghi trong protocol này.

## 28. T21 Amendment v3-A — đóng băng P1-v2 Edge-Selective

Sau thất bại của scene-level H2-Selective, v3-A đóng băng phương án chỉ định hướng từng cạnh BOSS chưa rõ chiều khi cả semantic confidence và weighted global stability cùng đủ cao. Mọi candidate direction phải được chọn bằng tối ưu toàn cục exact, cùng tồn tại trong ít nhất một consistent DAG extension và qua Meek closure; cạnh không đủ bằng chứng được giữ undirected.

Gate mới vẫn nghiêm ngặt: graph validity 100%, end-to-end precision ít nhất 95%, tối thiểu 20 cạnh được trả lời và coverage tối thiểu 20%. False adjacency của BOSS nếu bị định hướng được tính là sai. Hai mươi development scenes cũ chỉ phục vụ engineering; một cohort validation mới 20 scenes sẽ được sinh ở stage sau, trong khi 80 holdout scenes cũ giữ nguyên và chưa được mở.

V3-A chỉ tạo protocol/schema/report/audit và chạy kiểm tra offline: 0 API call, 0 validation scene, chưa implement Edge-Selective và không đọc artifact của holdout. Bước duy nhất được cấp quyền tiếp theo là T21 v3-B xây implementation, independent solver và synthetic conformance suite hoàn toàn offline.

## 29. T21 Amendment v3-B — triển khai Edge-Selective và kiểm định offline

V3-B hiện thực hóa protocol bằng hai solver độc lập: production duyệt orientation của các cạnh chưa rõ chiều, còn reference duyệt thứ tự topo và brute-force mọi subset candidate. Hai bên cùng tạo partial graph hợp lệ sau Meek R1–R4 nhưng không dùng chung logic lựa chọn, giúp phát hiện lỗi triển khai chéo.

Suite synthetic gồm 180 CPDAG với 3–7 node và sáu chế độ semantic evidence cân bằng. Trên lưới 20 threshold đã đóng băng, 3.600/3.600 quyết định production/reference khớp; 40/40 artifact lỗi bị từ chối. Sáu stress probe ngoài grid còn buộc ba local directions tạo cycle để kiểm tra solver loại đúng cạnh xung đột; probe chỉ kiểm định thuật toán, không chọn threshold. Output giữ nguyên node/skeleton/compelled directions, ghi riêng semantic-selected, closure-propagated và unresolved.

Toàn bộ bước này offline: không gọi API, không sinh 20 validation scenes, không đọc development/80 holdout và chưa chọn threshold. V3-B chỉ cấp quyền cho T21 v3-C sinh và đóng băng cohort validation mới; live semantic calls vẫn chưa được phép.

## 30. T21 Amendment v3-C — sinh và đóng băng validation cohort

V3-C tạo một cohort hoàn toàn mới gồm 20 SCM linear non-Gaussian, không tái sử dụng 20 development hoặc 80 holdout scenes. Namespace mới là `P1V000–P1V019` và `scene_110000–scene_110019`; master seed 21301 cùng toàn bộ component seeds, SCMs, observations và mapping đều được hash-freeze.

Cohort cân bằng đúng protocol: node 5/6/7 là 7/7/6; năm motif có bốn scene mỗi loại; ba noise families là 7/7/6; bốn query strata có năm scene mỗi loại. Mỗi scene có N=2000 observations, năm task và ba story variants full/partial/ambiguous. Hai solver độc lập khớp 100/100 task targets; story truth audit đạt 60/60.

V3-C không gọi model, không chạy BOSS/SCD/H1/H2/reasoner, không chọn threshold và không đọc raw artifact của development/holdout cũ. Gold truth và story text nằm ngoài Git; manifests chỉ giữ exact IDs, queries và hashes. Bước tiếp theo được cấp quyền là T21 v3-D gọi semantic model trên cohort validation và đánh giá đúng 20 threshold candidates; 80 final holdout scenes tiếp tục đóng.

## 31. T21 Amendment v3-D — validation gate cho Edge-Selective

V3-D chạy BOSS trên đúng 20 P1V validation scenes, sau đó dùng GPT-5.4 Nano/prompt v2 đã đóng băng để tạo 60 semantic-preference artifacts cho ba story variants. Tất cả 60 responses hợp lệ ngay lần đầu; không gọi model trên development hoặc final holdout.

Runner đánh giá đúng 20 cặp semantic-confidence/global-stability thresholds. Mọi output partial graph đều hợp lệ, nhưng candidate tốt nhất theo precision chỉ đúng 83/97 directions, tương đương 0,8557 precision và 0,4554 coverage. Trong 14 direction sai có 13 direction nằm trên false adjacency của BOSS. Kết quả thấp hơn gate 0,95 dù số cạnh trả lời và coverage đều đủ.

Vì vậy V3-D không chọn threshold và không tạo G_HYBRID_H2_EDGE_SELECTIVE chính thức cho holdout. Đây là negative validation result theo đúng fail-closed protocol, không được hạ gate hay tiếp tục tune trên cùng cohort. T21 v3-E chỉ được phép ghi quyết định terminal; 80 final holdout scenes vẫn chưa mở.

## 32. T21 Amendment v3-E — đóng P1-v2 trước final holdout

V3-E chấp nhận kết quả `83/97 = 0,8557` như một negative validation result thay vì hạ gate `0,95` hoặc tiếp tục tối ưu trên cùng 20 scenes. Không threshold nào được chọn, selected-graph manifest vẫn rỗng và T22 không được cấp quyền.

Bước đóng này không gọi API và không đọc downstream answers hay final-holdout method results. Nó băm và khóa 70 artifact T21 v2/v3, chạy replay byte-for-byte và tiếp tục niêm phong nguyên 80 final-holdout scenes.

P1-v2 kết thúc tại đây. Hành động kế tiếp duy nhất là thiết kế protocol P1-v3 Evidence-Selective Hybrid độc lập: giữ GPT-5.4 Nano, gọi semantic model theo whole graph, dùng Bootstrap-BOSS làm statistical method chính và hoãn SCD ensemble sang robustness study. Chưa được chạy Bootstrap, sinh cohort hay gọi model cho đến khi protocol mới được đóng băng.

## 33. Đóng băng protocol P1-v3 Evidence-Selective Hybrid

Protocol mới thay một BOSS graph nhị phân bằng evidence ledger ở cấp cạnh. Mỗi scene dự kiến được resample 200 lần; từng resample vẫn có N=2000 dòng lấy có hoàn lại, được chuẩn hóa riêng rồi chạy BOSS. Với mỗi cặp node, hệ thống giữ bốn tần suất absent, undirected, A→B và B→A. Bootstrap frequency chỉ là độ ổn định khi resample, không phải xác suất nhân quả.

Semantic layer giữ GPT-5.4 Nano nhưng thay một lời gọi confidence bằng sáu cách hỏi cố định, cân bằng thứ tự hai biến 3–3 và batch toàn graph. Code gom phiếu thành Very High, High, Medium, Uncertain hoặc Conflict. Chỉ Very High/High đã chứng minh empirical reliability trên calibration độc lập mới được xem xét định hướng; Medium trở xuống giữ unresolved.

Hybrid áp dụng statistical veto trước semantic evidence, kiểm tra global consistency và ghi riêng direction do thống kê, semantic selection hay Meek closure. Lưới 5 adjacency thresholds × 3 direction thresholds được khóa trước. Learn-then-Test hoặc risk control tương đương phải chứng minh error không quá 5% với failure probability 5% và coverage hữu ích ít nhất 20% trước khi mở holdout.

Bước freeze chỉ tạo config, prompt bundle, bốn schema, report và hash manifest. Không Bootstrap run nào được thực hiện, không scene mới được sinh, không API được gọi và 80 holdout scenes vẫn đóng. Bước tiếp theo duy nhất là implement Bootstrap-BOSS aggregator cùng production/reference synthetic conformance hoàn toàn offline.

## 34. Bootstrap-BOSS aggregator và synthetic conformance

Implementation mới có thể tạo deterministic bootstrap indices, lấy đúng N dòng có hoàn lại, chuẩn hóa từng resample và nhận 200 CPDAG do một runner BOSS tương lai cung cấp. Aggregator không tự chạy Tetrad/BOSS. Với mọi cặp node, nó đếm bốn trạng thái absent, undirected, A→B và B→A trên toàn bộ 200 runs; sau đó 15 threshold pairs tạo các statistical parent graphs hoặc fail closed nếu graph không có consistent extension.

Suite offline gồm 60 trường hợp tổng hợp × 200 graph states, phủ stable/unstable adjacency, stable direction hai chiều, direction conflict và thường absent trên graph 3–7 nodes. Production và reference khớp 60/60 aggregate và 900/900 parent decisions. Thứ tự runs, thứ tự node đầu vào và input immutability đều đạt 60/60; 30/30 malformed fixtures bị từ chối.

Bước này không đọc observational study data và không thực sự chạy một BOSS search nào. Nó cũng không sinh cohort, không gọi LLM và không mở holdout. Tiếp theo chỉ được xây semantic vote/reliability cùng statistical-veto decision table và kiểm định synthetic hoàn toàn offline.

## 35. Six-vote semantic reliability và statistical veto

Lớp semantic offline mới nhận sáu response whole-graph đã được chuẩn hóa. Với từng cạnh, code gom phiếu thành Very High, High, Medium, Uncertain hoặc Conflict; direction chỉ hợp lệ khi `evidence_quote` trích nguyên văn một câu causal trực tiếp trong story. Association-only, sai alias, thiếu/trùng pair và quote không khớp direction đều bị từ chối.

Suite tổng hợp có 90 cases, tương ứng 180 edge records và 1.080 judgments qua sáu prompt. Production và reference classifier khớp 180/180; validator chấp nhận 810 directional quotes cùng 270 abstentions có evidence null, và từ chối 48/48 malformed fixtures. Chín empirical-reliability groups giữ trạng thái `pending_risk_control`; chúng không thể tự biến point estimate thành chứng nhận an toàn. Statistical-veto production/reference khớp 36/36 quyết định và không cho semantic evidence hồi sinh adjacency yếu hoặc không tồn tại.

Toàn bộ bước này dùng story/response tổng hợp: không gọi GPT, không chạy BOSS, không đọc study observations, không sinh cohort và không mở holdout. Bước tiếp theo chỉ là thiết kế prospective power và các cohort calibration/validation tách biệt; việc thực thi nghiên cứu vẫn chưa được cấp quyền.

## 36. Prospective power và thiết kế cohort độc lập

Power design coi mỗi scene/SCM là một đơn vị độc lập. Những edge nằm trong cùng scene được gộp thành một error fraction giới hạn từ 0 đến 1, sau đó kiểm định bằng Hoeffding–Bentkus và Bonferroni. Nhờ vậy, nhiều cạnh từ cùng một graph không bị đếm giả như nhiều mẫu độc lập.

Failure budget `δ=0,05` được chia đôi: `0,025` cho sáu nhóm semantic reliability và `0,025` cho 15 threshold candidates. Với giả định phương pháp thật sự chỉ sai 1%, minimum 280 calibration scenes đem lại power khoảng 0,849; minimum 340 validation scenes đem lại power khoảng 0,872. Đây chỉ là giả định planning, không phải accuracy đã quan sát.

Thiết kế khóa ba cohort mới: 40 method-development scenes, 400 semantic-calibration scenes và 400 threshold-validation scenes. Calibration chỉ chứng nhận nhóm Full/Partial/Ambiguous × Very High/High; validation chỉ được mở một lần để chứng nhận/chọn trong 15 candidates đã khóa. Ba cohort có namespace, seed và vai trò tách biệt; 80 final holdout cũ vẫn đóng.

Bước này chưa tạo 840 scene hay exact IDs. Nó cũng không chạy 168.000 Bootstrap-BOSS fits dự kiến, không thực hiện 15.120 semantic calls dự kiến và không đọc cohort/holdout cũ. Tiếp theo chỉ được implement generator/split allocator và synthetic conformance offline.

## 37. Successor generator và split allocator synthetic conformance

Generator/allocator mới có thể phân bổ chính xác node count, motif, noise family và query stratum bằng seed cố định, sau đó tạo blueprint SCM linear non-Gaussian thỏa connectivity, motif, CPDAG uncertainty và task-query constraints. Tuy nhiên code offline hard-block ba namespace thật `P1V3D`, `P1V3C`, `P1V3T`; vì vậy nó chưa thể vô tình sinh cohort nghiên cứu.

Conformance chỉ dùng 24 synthetic fixtures thuộc `SYNDEV`, `SYNCAL`, `SYNVAL`. Allocation production/reference khớp; 12/12 marginal checks, 24/24 deterministic replays, 3/3 seed perturbations và 120/120 task-solver agreements đều đạt. Ba mươi malformed fixtures bị từ chối.

Không observation row, story hay exact study ID nào được tạo; không BOSS/bootstrap/API chạy và holdout vẫn đóng. Bước kế tiếp duy nhất là thiết kế runtime/cost pilot offline trước khi cân nhắc cấp quyền thực thi pilot.
