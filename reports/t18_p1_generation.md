# T18 — Fresh-SCM generator, inventory và frozen P1 split

## Kết quả

T18 đã sinh deterministically 100 linear non-Gaussian SCMs mà không gọi API, không chạy SCD/LLM/Hybrid và không chấm holdout. Mỗi scene có đúng năm task; production solver và independent active-path solver khớp 500/500 targets.

- 100 scenes: 20 development / 80 holdout.
- 5–7 observed continuous nodes; connected DAG; không latent node.
- Mỗi Oracle CPDAG có ít nhất hai unresolved edges.
- Primary observations: `N=2000` trên 100/100 scenes.
- Nested `N=500/10000`: 20 scenes, gồm 4 development và 16 holdout.
- Raw ignored artifact tree: 40,383,896 bytes.
- Generation attempts: tổng 376, median 2.0, tối đa 26 / 10.000.
- Split maximum rounded marginal deviation: 1 scene; gate cho phép tối đa 2.

## Exact development IDs

`P1S000`, `P1S019`, `P1S022`, `P1S023`, `P1S026`, `P1S032`, `P1S034`, `P1S035`, `P1S036`, `P1S046`, `P1S048`, `P1S065`, `P1S067`, `P1S072`, `P1S074`, `P1S076`, `P1S077`, `P1S083`, `P1S085`, `P1S092`

80 ID còn lại được đóng băng là holdout trong `data/manifests/t18_p1_frozen_split.json`. Mapping `P1Sxxx` sang `scene_100xxx` là một-một để tương thích graph contract T06.

## Artifact và leakage boundary

SCM equations, Oracle DAG/CPDAG, component seeds và expected answers nằm dưới `data/generated/p1_hybrid_v1/t18/`, bị Git ignore. Inventory được version hóa chỉ chứa metadata và hashes; task manifest chứa query cùng target commitment hash nhưng không chứa gold answer. Loader ở các bước sau vẫn phải enforce evidence boundary, vì hash/inventory không tự thay thế access control.

T18 được phép dùng Oracle-only structural/task properties để tạo split trước method development. Không output nào của BOSS, DirectLiNGAM, LLM, H1, H2 hoặc reasoner được tạo hay dùng khi chọn split.

## Kết luận và quyền tiếp theo

T18 đạt mọi generation, nesting, solver-agreement, balance và byte-replay gate. Chỉ T19 deterministic semantic-story variants/manual audit được cấp quyền tiếp theo. Live model calls, H2 implementation/execution và P1 holdout evaluation vẫn chưa được cấp quyền.
