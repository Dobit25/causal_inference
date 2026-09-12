# Timeline dự án Causal Inference: T00–T12

## 1. Mục đích của tài liệu

Tài liệu này mô tả tuyến tính quá trình phát triển dự án từ T00 đến hết T12: mỗi task bắt đầu từ vấn đề nào, được thực hiện để làm gì, đã làm những gì, điều kiện hoàn thành ra sao và kết quả thực tế là gì.

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
