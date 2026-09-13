"""Run or byte-check the preregistered T15 P0 holdout analysis."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.t15_analysis import (  # noqa: E402
    average_ranks,
    benjamini_hochberg,
    exact_mcnemar,
    mean,
    paired_cluster_bootstrap,
    spearman_from_values,
)

CONDITIONS = ["G_LLM", "G_SCD_RAW", "G_SCD_PROJECTED", "G_HYBRID", "G_ORACLE"]
DAG_CONDITIONS = ["G_LLM", "G_SCD_PROJECTED", "G_HYBRID", "G_ORACLE"]
DOWNSTREAM_METRICS = ["oracle_answer_accuracy", "uncertainty_aware_correctness"]
REPLICATES = 5000
ROOT_SEED = 13015


def obj(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def rounded(value: float | None) -> float | None:
    return None if value is None else float(f"{float(value):.10g}")


def jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(record, newline=True) for record in records)


def verify_t14(t13: dict[str, Any], audit: dict[str, Any]) -> tuple[Path, Path]:
    if not audit["verdict"]["t14_complete"] or not audit["verdict"]["t15_authorized"]:
        raise RuntimeError("T14 has not authorized T15")
    if audit["verdict"]["t15_started"] or audit["evidence_boundary"]["aggregate_ranking_computed"]:
        raise RuntimeError("T14 audit unexpectedly reports prior aggregate analysis")
    metric_path = ROOT / t13["execution"]["outputs"]["t14_graph_metrics"]
    score_path = ROOT / t13["execution"]["outputs"]["t14_primary_scores"]
    expected = audit["artifacts"]
    if sha256_hex(metric_path.read_bytes()) != expected["graph_metrics.jsonl"]["sha256"]:
        raise RuntimeError("T14 graph metric artifact drift")
    if sha256_hex(score_path.read_bytes()) != expected["primary_scores.jsonl"]["sha256"]:
        raise RuntimeError("T14 downstream score artifact drift")
    return metric_path, score_path


def build_scene_summaries(
    graph_rows: list[dict[str, Any]], score_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in graph_rows:
        record: dict[str, Any] = {
            "schema_version": "fourgraph.t15_scene_summary.v1",
            "analysis_layer": "graph",
            "scene_id": item["scene_id"],
            "graph_condition": item["graph_condition"],
            "status": item["status"],
        }
        metric = item["metric_record"]
        if metric is None:
            record.update({"skeleton_f1": None, "skeleton_shd": None, "directed_f1": None,
                           "dag_normalized_shd": None, "cpdag_normalized_state_shd": None,
                           "cpdag_unresolved_rate": None})
        else:
            record.update({
                "skeleton_f1": metric["skeleton"]["f1"],
                "skeleton_shd": metric["skeleton"]["shd"],
                "directed_f1": metric["dag"]["directed_f1"] if metric["dag"] else None,
                "dag_normalized_shd": metric["dag"]["normalized_shd_by_possible_pairs"] if metric["dag"] else None,
                "cpdag_normalized_state_shd": metric["cpdag"]["normalized_state_shd"] if metric["cpdag"] else None,
                "cpdag_unresolved_rate": metric["cpdag"]["unresolved_rate"] if metric["cpdag"] else None,
            })
        records.append(record)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in score_rows:
        grouped[(item["scene_id"], item["graph_condition"])].append(item)
    for scene_id, condition in sorted(grouped):
        items = grouped[(scene_id, condition)]
        statuses = Counter(item["status"] for item in items)
        records.append({
            "schema_version": "fourgraph.t15_scene_summary.v1",
            "analysis_layer": "downstream",
            "scene_id": scene_id,
            "graph_condition": condition,
            "scheduled_tasks": len(items),
            "answered_tasks": statuses["answered"],
            "graph_failure_tasks": statuses["graph_failure"],
            "reasoner_failure_tasks": statuses["reasoner_failure"],
            "oracle_answer_accuracy": rounded(mean([float(item["oracle_answer_accuracy"]) for item in items])),
            "uncertainty_aware_correctness": rounded(mean([float(item["uncertainty_aware_correctness"]) for item in items])),
        })
    return sorted(records, key=lambda item: (item["analysis_layer"], item["scene_id"], item["graph_condition"]))


def condition_summaries(scene_records: list[dict[str, Any]], score_rows: list[dict[str, Any]]) -> dict[str, Any]:
    graph = [item for item in scene_records if item["analysis_layer"] == "graph"]
    downstream = [item for item in scene_records if item["analysis_layer"] == "downstream"]
    graph_summary = {}
    for condition in CONDITIONS:
        selected = [item for item in graph if item["graph_condition"] == condition]
        available = [item for item in selected if item["status"] == "available"]
        def avg(field: str) -> float | None:
            values = [float(item[field]) for item in available if item[field] is not None]
            return rounded(mean(values)) if values else None
        graph_summary[condition] = {
            "scheduled_scenes": len(selected), "available_scenes": len(available),
            "completion_rate": rounded(len(available) / len(selected)),
            "scene_macro_skeleton_f1": avg("skeleton_f1"),
            "scene_macro_skeleton_shd": avg("skeleton_shd"),
            "scene_macro_directed_f1": avg("directed_f1"),
            "scene_macro_dag_normalized_shd": avg("dag_normalized_shd"),
            "scene_macro_cpdag_normalized_state_shd": avg("cpdag_normalized_state_shd"),
            "scene_macro_cpdag_unresolved_rate": avg("cpdag_unresolved_rate"),
        }
    downstream_summary = {}
    task_summary: dict[str, Any] = {}
    for condition in CONDITIONS:
        selected = [item for item in downstream if item["graph_condition"] == condition]
        raw = [item for item in score_rows if item["graph_condition"] == condition]
        downstream_summary[condition] = {
            "scene_count": len(selected), "scheduled_tasks": len(raw),
            "answered_tasks": sum(item["status"] == "answered" for item in raw),
            "graph_failure_tasks": sum(item["status"] == "graph_failure" for item in raw),
            "reasoner_failure_tasks": sum(item["status"] == "reasoner_failure" for item in raw),
            **{f"scene_macro_{metric}": rounded(mean([float(item[metric]) for item in selected])) for metric in DOWNSTREAM_METRICS},
        }
        for task in sorted({item["task_id"] for item in raw}):
            task_items = [item for item in raw if item["task_id"] == task]
            task_summary[f"{condition}|{task}"] = {
                "condition": condition, "task_id": task, "n": len(task_items),
                **{metric: rounded(mean([float(item[metric]) for item in task_items])) for metric in DOWNSTREAM_METRICS},
            }
    return {"graph": graph_summary, "downstream": downstream_summary, "downstream_by_task": task_summary}


def pairwise_results(scene_records: list[dict[str, Any]], score_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    graph = [item for item in scene_records if item["analysis_layer"] == "graph"]
    downstream = [item for item in scene_records if item["analysis_layer"] == "downstream"]
    specifications = [
        ("A_graph_skeleton_f1", "skeleton_f1", CONDITIONS, graph),
        ("A_graph_dag_directed_f1", "directed_f1", DAG_CONDITIONS, graph),
        ("B_downstream_oracle_answer_accuracy", "oracle_answer_accuracy", CONDITIONS, downstream),
        ("B_downstream_uncertainty_aware_correctness", "uncertainty_aware_correctness", CONDITIONS, downstream),
    ]
    output = []
    for family, metric, conditions, records in specifications:
        family_rows = []
        for left, right in combinations(conditions, 2):
            left_values = {item["scene_id"]: float(item[metric]) for item in records if item["graph_condition"] == left and item.get(metric) is not None}
            right_values = {item["scene_id"]: float(item[metric]) for item in records if item["graph_condition"] == right and item.get(metric) is not None}
            boot = paired_cluster_bootstrap(left_values, right_values, replicates=REPLICATES, root_seed=ROOT_SEED, namespace=f"{family}|{left}|{right}")
            row: dict[str, Any] = {
                "schema_version": "fourgraph.t15_pairwise_result.v1", "family": family, "metric": metric,
                "left_condition": left, "right_condition": right,
                **{key: rounded(value) if isinstance(value, float) else value for key, value in boot.items()},
            }
            if family.startswith("B_downstream"):
                keyed = {(item["scene_id"], item["task_id"], item["graph_condition"]): bool(item[metric]) for item in score_rows}
                keys = sorted((item["scene_id"], item["task_id"]) for item in score_rows if item["graph_condition"] == left)
                mc = exact_mcnemar([keyed[(scene, task, left)] for scene, task in keys], [keyed[(scene, task, right)] for scene, task in keys])
                row.update({f"mcnemar_{key}": rounded(value) if isinstance(value, float) else value for key, value in mc.items()})
            family_rows.append(row)
        adjusted = benjamini_hochberg([float(item["two_sided_bootstrap_p"]) for item in family_rows])
        for item, value in zip(family_rows, adjusted):
            item["bootstrap_bh_adjusted_p"] = rounded(value)
            item["bootstrap_bh_reject_alpha_0_05"] = value <= 0.05
        if family.startswith("B_downstream"):
            mc_adjusted = benjamini_hochberg([float(item["mcnemar_two_sided_exact_p"]) for item in family_rows])
            for item, value in zip(family_rows, mc_adjusted):
                item["mcnemar_bh_adjusted_p"] = rounded(value)
                item["mcnemar_bh_reject_alpha_0_05"] = value <= 0.05
        output.extend(family_rows)
    return output


def render_report(audit: dict[str, Any], pairs: list[dict[str, Any]]) -> str:
    summaries = audit["condition_summaries"]
    lines = [
        "# T15 — Phân tích P0 holdout", "", "## Trạng thái", "",
        "T15 hoàn tất hoàn toàn offline từ các artifact T14 đã seal. Không có API call, không rerun failure, không sửa graph/reasoner và không trộn supplementary vào downstream primary.", "",
        "## Graph quality trên 25 scenes", "",
        "| Condition | Complete | Skeleton F1 | Directed F1 | CPDAG state SHD | Unresolved rate |", "|---|---:|---:|---:|---:|---:|",
    ]
    for condition in CONDITIONS:
        item = summaries["graph"][condition]
        fmt = lambda value: "—" if value is None else f"{value:.3f}"
        lines.append(f"| `{condition}` | {item['available_scenes']}/25 | {fmt(item['scene_macro_skeleton_f1'])} | {fmt(item['scene_macro_directed_f1'])} | {fmt(item['scene_macro_cpdag_normalized_state_shd'])} | {fmt(item['scene_macro_cpdag_unresolved_rate'])} |")
    lines += ["", "Hai Hybrid failures được giữ là unavailable cho structural metrics; không impute.", "", "## Downstream trên 20 primary scenes", "",
              "| Condition | Oracle-answer accuracy | Uncertainty-aware | Answered | Graph/reasoner failures |", "|---|---:|---:|---:|---:|"]
    for condition in CONDITIONS:
        item = summaries["downstream"][condition]
        failures = item["graph_failure_tasks"] + item["reasoner_failure_tasks"]
        lines.append(f"| `{condition}` | {item['scene_macro_oracle_answer_accuracy']:.3f} | {item['scene_macro_uncertainty_aware_correctness']:.3f} | {item['answered_tasks']}/100 | {failures}/100 |")
    lines += ["", "Failure records được tính incorrect theo T13. Raw SCD có thể sai official Oracle answer nhưng đúng theo conservative CPDAG uncertainty. Metric uncertainty-aware đo reasoner có trả lời phù hợp với graph được cấp hay không, không phải graph đó đúng ground truth hay không.", "", "## Các contrast chính", ""]
    selected = [item for item in pairs if item["family"].startswith("B_downstream") and (item["right_condition"] == "G_ORACLE" or {item["left_condition"], item["right_condition"]} == {"G_SCD_RAW", "G_SCD_PROJECTED"} or {item["left_condition"], item["right_condition"]} == {"G_HYBRID", "G_SCD_PROJECTED"})]
    lines += ["| Metric | Left − right | Effect | 95% CI | BH p |", "|---|---|---:|---:|---:|"]
    for item in selected:
        lines.append(f"| `{item['metric']}` | `{item['left_condition']}` − `{item['right_condition']}` | {item['effect_left_minus_right']:.3f} | [{item['ci_lower']:.3f}, {item['ci_upper']:.3f}] | {item['bootstrap_bh_adjusted_p']:.4f} |")
    c = audit["outcomes"]["C"]
    d = audit["outcomes"]["D"]
    h = audit["hybrid_attribution_pooled"]
    lines += ["", "## Diễn giải outcome A–D", "",
              f"- A: ranking skeleton và directed quality được báo riêng; không ép raw CPDAG vào DAG metric. Trên 23 Hybrid graphs thành công, semantic orientation đúng {h['semantic_orientation_correct']}/{h['unresolved_evaluable']} cạnh unresolved có thể đánh giá, so với {h['projection_orientation_correct']}/{h['unresolved_evaluable']} của deterministic projection; hai terminal failures vẫn nằm ngoài tỷ lệ cạnh này.",
              f"- B: hai scorer downstream được xem là co-equal. Ranking official là {', '.join(c['oracle_answer_ranking'])}; ranking uncertainty-aware là {', '.join(c['uncertainty_aware_ranking'])}.",
              f"- C: Spearman giữa condition-level skeleton F1 và official downstream là {c['skeleton_vs_oracle_answer_spearman']}; đây là mô tả với chỉ năm conditions, không phải bằng chứng nhân quả.",
              f"- D: Oracle còn sai {d['oracle_answer_residual_errors']}/100 official tasks và {d['uncertainty_aware_residual_errors']}/100 uncertainty-aware tasks; graph đúng không tự bảo đảm reasoner đúng.",
              "", "## Statistical contract", "",
              "Primary effect là chênh lệch scene-macro có trọng số scene bằng nhau. CI percentile 95% dùng 5.000 paired scene-cluster bootstrap replicates, seed gốc 13015. Các kiểm định hai phía được BH-correct trong từng metric family. Exact McNemar ở cấp scene-task chỉ là sensitivity vì không mô hình hóa clustering.", "",
              "## Giới hạn", "",
              "P0 chỉ có 25 graph scenes và 20 primary downstream scenes. Hybrid có terminal failures, raw CPDAG và DAG không cùng loại direction metric, và kết quả chỉ áp dụng cho released heterogeneous CausalDS P0. SID/AID, perturbation và robustness chưa khả dụng trong phase này.", ""]
    return "\n".join(lines)


def build() -> dict[Path, bytes]:
    t13_path = ROOT / "data/manifests/t13_holdout_execution.json"
    t14_audit_path = ROOT / "data/manifests/t14_holdout_execution_audit.json"
    t13, t14_audit = obj(t13_path), obj(t14_audit_path)
    stats = t13["statistics"]
    if stats["bootstrap_replicates"] != REPLICATES or stats["bootstrap_seed"] != ROOT_SEED or stats["bh_alpha"] != 0.05:
        raise RuntimeError("T15 implementation disagrees with the frozen T13 statistics")
    metric_path, score_path = verify_t14(t13, t14_audit)
    graph_rows, score_rows = rows(metric_path), rows(score_path)
    if len(graph_rows) != 125 or len(score_rows) != 500:
        raise RuntimeError("T14 schedule count mismatch")
    scene_records = build_scene_summaries(graph_rows, score_rows)
    summaries = condition_summaries(scene_records, score_rows)
    pairs = pairwise_results(scene_records, score_rows)
    skeleton_values = {key: value["scene_macro_skeleton_f1"] for key, value in summaries["graph"].items()}
    official_values = {key: value["scene_macro_oracle_answer_accuracy"] for key, value in summaries["downstream"].items()}
    uncertainty_values = {key: value["scene_macro_uncertainty_aware_correctness"] for key, value in summaries["downstream"].items()}
    rank_list = lambda values: [key for key, _ in sorted(average_ranks(values).items(), key=lambda item: (item[1], item[0]))]
    hybrid_attrs = [item["metric_record"]["hybrid_attribution"] for item in graph_rows if item["graph_condition"] == "G_HYBRID" and item["status"] == "available"]
    attr_keys = sorted({key for item in hybrid_attrs for key in item})
    audit: dict[str, Any] = {
        "schema_version": "fourgraph.t15_analysis_audit.v1", "experiment_id": t13["experiment_id"],
        "inputs": {"t13_sha256": sha256_hex(t13_path.read_bytes()), "t14_audit_sha256": sha256_hex(t14_audit_path.read_bytes()), "graph_metrics_sha256": sha256_hex(metric_path.read_bytes()), "primary_scores_sha256": sha256_hex(score_path.read_bytes())},
        "implementation": {
            "scripts/analyze_t15.py": sha256_hex((ROOT / "scripts/analyze_t15.py").read_bytes()),
            "src/fourgraph/t15_analysis.py": sha256_hex((ROOT / "src/fourgraph/t15_analysis.py").read_bytes()),
        },
        "contract": {"unit": "scene", "primary_summary": "equal_weight_scene_macro", "comparison": "paired", "bootstrap_replicates": REPLICATES, "bootstrap_root_seed": ROOT_SEED, "confidence_interval": "percentile_95", "tests": "two_sided", "bh_alpha": 0.05, "bh_scope": "within_each_metric_family", "mcnemar_role": "record_level_binary_sensitivity_only", "failure_policy": "frozen_T13_incorrect_downstream_unavailable_structural"},
        "scope": {"graph_scenes": 25, "primary_downstream_scenes": 20, "supplementary_graph_scenes": 5, "supplementary_downstream_records": 0, "graph_schedule_records": 125, "downstream_schedule_records": 500, "api_calls": 0, "failures_rerun": False},
        "condition_summaries": summaries,
        "hybrid_attribution_available_scenes": len(hybrid_attrs),
        "hybrid_attribution_pooled": {key: sum(int(item[key]) for item in hybrid_attrs) for key in attr_keys},
        "outcomes": {
            "A": {"status": "analyzed", "note": "skeleton all conditions; directed DAG conditions; raw CPDAG state separately"},
            "B": {"status": "analyzed", "co_equal_metrics": DOWNSTREAM_METRICS},
            "C": {"status": "descriptive", "skeleton_ranking": rank_list(skeleton_values), "oracle_answer_ranking": rank_list(official_values), "uncertainty_aware_ranking": rank_list(uncertainty_values), "skeleton_vs_oracle_answer_spearman": rounded(spearman_from_values(skeleton_values, official_values)), "skeleton_vs_uncertainty_aware_spearman": rounded(spearman_from_values(skeleton_values, uncertainty_values))},
            "D": {"status": "analyzed", "oracle_answer_residual_errors": 100 - sum(bool(item["oracle_answer_accuracy"]) for item in score_rows if item["graph_condition"] == "G_ORACLE"), "uncertainty_aware_residual_errors": 100 - sum(bool(item["uncertainty_aware_correctness"]) for item in score_rows if item["graph_condition"] == "G_ORACLE")},
            "E": {"status": "unavailable", "reason": "SID/AID not pinned or validated"},
            "F": {"status": "not_in_P0_clean_phase"}, "G": {"status": "not_in_P0_clean_phase"},
        },
        "pairwise_family_counts": dict(Counter(item["family"] for item in pairs)),
        "evidence_boundary": {"t14_artifacts_modified": False, "api_calls_made": 0, "failures_rerun": False, "supplementary_pooled_downstream": False, "oracle_edges_persisted": False, "post_holdout_retuning": False},
        "verdict": {"t15_complete": True, "p0_holdout_analysis_complete": True, "t14_replay_preserved": True, "p1_started": False},
    }
    scene_payload, pair_payload = jsonl_bytes(scene_records), jsonl_bytes(pairs)
    audit["artifacts"] = {
        "scene_summaries": {"path": "data/manifests/t15_scene_summaries.jsonl", "sha256": sha256_hex(scene_payload), "records": len(scene_records)},
        "pairwise_results": {"path": "data/manifests/t15_pairwise_results.jsonl", "sha256": sha256_hex(pair_payload), "records": len(pairs)},
    }
    report = render_report(audit, pairs).encode("utf-8")
    audit["artifacts"]["report"] = {"path": "reports/t15_p0_holdout_analysis.md", "sha256": sha256_hex(report)}
    audit_payload = canonical_json_bytes(audit, newline=True)
    return {
        ROOT / "data/manifests/t15_scene_summaries.jsonl": scene_payload,
        ROOT / "data/manifests/t15_pairwise_results.jsonl": pair_payload,
        ROOT / "reports/t15_p0_holdout_analysis.md": report,
        ROOT / "data/manifests/t15_analysis_audit.json": audit_payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    outputs = build()
    for path, payload in outputs.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != payload:
                raise RuntimeError(f"T15 replay differs byte-for-byte: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    audit = json.loads(outputs[ROOT / "data/manifests/t15_analysis_audit.json"])
    print(json.dumps({"verdict": audit["verdict"], "pairwise_family_counts": audit["pairwise_family_counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
