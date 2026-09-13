"""Build, finalize, or byte-check the offline T19 semantic-story artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex  # noqa: E402
from fourgraph.p1_generation import canonical_line, seed64, stable_rank  # noqa: E402
from fourgraph.p1_stories import (  # noqa: E402
    VARIANTS,
    blinded_slot_order,
    build_story_bundle,
    evidence_class,
    public_builder_view,
    validate_story_bundle,
)


CONFIG_PATH = ROOT / "configs/t19_p1_semantic_stories.yaml"
SCHEMA_PATH = ROOT / "schemas/p1_t19_public_story_v1.schema.json"
MODULE_PATH = ROOT / "src/fourgraph/p1_stories.py"
SCRIPT_PATH = Path(__file__).resolve()


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _entry(path: Path, payload: bytes | None = None) -> dict[str, Any]:
    body = path.read_bytes() if payload is None else payload
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": len(body),
        "sha256": sha256_hex(body),
    }


def _artifact_path(config: Mapping[str, Any], key: str) -> Path:
    return ROOT / str(config["artifacts"][key])


def _validate_parent(config: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    audit = _json(ROOT / str(config["parent_generation_audit"]))
    if not audit["verdict"]["t18_complete"] or not audit["verdict"]["t19_story_generation_authorized"]:
        raise RuntimeError("T18 does not authorize T19")
    if audit["verdict"]["live_model_calls_authorized"] or audit["verdict"]["H2_implementation_authorized"]:
        raise RuntimeError("T18 execution boundary drift")
    split = _json(ROOT / str(config["parent_split"]))
    inventory = _jsonl(ROOT / str(config["parent_inventory"]))
    if len(inventory) != 100 or len(split["development_ids"]) != 20 or len(split["holdout_ids"]) != 80:
        raise RuntimeError("T18 population/split drift")
    if config["stories"]["variants"] != list(VARIANTS):
        raise RuntimeError("T19 variant drift")
    if int(config["randomness"]["master_seed"]) != 1701:
        raise RuntimeError("T19 master seed drift")
    boundary = config["access_boundary"]
    forbidden = (
        boundary["api_calls"],
        boundary["provider_sdk_imports_allowed"],
        boundary["SCD_execution_authorized"],
        boundary["LLM_execution_authorized"],
        boundary["reasoner_execution_authorized"],
        boundary["H1_execution_authorized"],
        boundary["H2_implementation_or_execution_authorized"],
        boundary["holdout_story_content_manual_review_authorized"],
        boundary["holdout_method_evaluation_authorized"],
        boundary["holdout_downstream_scoring_authorized"],
    )
    if any(forbidden):
        raise RuntimeError("T19 execution boundary drift")
    dependencies = [ROOT / str(value) for value in config["dependencies"]]
    if len(dependencies) != len(set(dependencies)) or any(not path.is_file() for path in dependencies):
        raise RuntimeError("T19 dependency list missing or duplicated")
    return audit, split, inventory


def _blind_panel(
    bundles: Mapping[str, Any], development: list[str], config: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    master_seed = int(config["randomness"]["master_seed"])
    panel_seed = seed64(master_seed, "T19_PANEL", "blinded_panel_order")
    ordered_scenes = sorted(
        development,
        key=lambda study_id: stable_rank(panel_seed, study_id),
    )
    panel: list[dict[str, Any]] = []
    key_rows: list[dict[str, Any]] = []
    for index, study_id in enumerate(ordered_scenes, start=1):
        blind_id = f"T19BLIND{index:03d}"
        records = {record["evidence_variant"]: record for record in bundles[study_id].public_records}
        slots = []
        key_slots = []
        for slot, variant in zip(("A", "B", "C"), blinded_slot_order(master_seed, study_id)):
            story = public_builder_view(records[variant])["story"]
            slots.append({"slot": slot, "story": story})
            key_slots.append({"slot": slot, "variant": variant, "expected_evidence_class": evidence_class(variant)})
        panel.append(
            {
                "schema_version": "fourgraph.p1_t19_blinded_panel.v1",
                "blind_scene_id": blind_id,
                "stories": slots,
            }
        )
        key_rows.append({"blind_scene_id": blind_id, "study_id": study_id, "slots": key_slots})
    key = {
        "schema_version": "fourgraph.p1_t19_blinded_key.v1",
        "development_only": True,
        "rows": key_rows,
    }
    return panel, key


def _validate_review(
    review_rows: list[dict[str, Any]], panel: list[dict[str, Any]], key: Mapping[str, Any]
) -> dict[str, Any]:
    if len(review_rows) != 20:
        raise RuntimeError("T19 manual review must contain exactly 20 scenes")
    panel_ids = {row["blind_scene_id"] for row in panel}
    reviews = {row["blind_scene_id"]: row for row in review_rows}
    if set(reviews) != panel_ids or len(reviews) != len(review_rows):
        raise RuntimeError("T19 manual review blind-ID mismatch")
    key_by_id = {row["blind_scene_id"]: row for row in key["rows"]}
    classification_correct = 0
    story_checks = 0
    scene_passes = 0
    minimum_naturalness = 5
    for blind_id in sorted(reviews):
        review = reviews[blind_id]
        expected = {row["slot"]: row["expected_evidence_class"] for row in key_by_id[blind_id]["slots"]}
        observed = review["slot_evidence_classification"]
        if set(observed) != {"A", "B", "C"}:
            raise RuntimeError(f"Review slot mismatch: {blind_id}")
        classification_correct += sum(observed[slot] == expected[slot] for slot in expected)
        checks = (
            bool(review["all_stories_grammatical_and_readable"]),
            bool(review["all_stories_self_contained"]),
            bool(review["no_machine_metadata_or_canonical_ids_seen"]),
            bool(review["symmetric_clauses_do_not_imply_an_obvious_direction"]),
        )
        story_checks += sum(checks)
        score = int(review["minimum_naturalness_score_1_to_5"])
        minimum_naturalness = min(minimum_naturalness, score)
        passed = all(checks) and score >= 4 and all(observed[slot] == expected[slot] for slot in expected)
        if bool(review["scene_pass"]) != passed:
            raise RuntimeError(f"Review scene_pass inconsistency: {blind_id}")
        scene_passes += int(passed)
    return {
        "reviewed_scenes": 20,
        "reviewed_stories": 60,
        "scene_passes": scene_passes,
        "evidence_classifications_correct": classification_correct,
        "evidence_classifications_total": 60,
        "binary_text_quality_checks_passed": story_checks,
        "binary_text_quality_checks_total": 80,
        "minimum_naturalness_score_1_to_5": minimum_naturalness,
        "reviewer_role": sorted({str(row["reviewer_role"]) for row in review_rows}),
        "independent_external_human_review": False,
    }


def _report(audit: Mapping[str, Any]) -> bytes:
    counts = audit["counts"]
    manual = audit["manual_blinded_audit"]
    lines = [
        "# T19 — Deterministic semantic-story variants and blinded audit",
        "",
        "## Kết quả",
        "",
        "T19 đã sinh ba story variants cho toàn bộ 100 SCM T18 mà không gọi API hay chạy bất kỳ phương pháp nghiên cứu nào.",
        "",
        f"- Public stories: {counts['public_stories']} = 100 scenes × 3 variants.",
        f"- Alias maps: {counts['alias_maps']}; mỗi map dùng một lexicon trung tính và seed độc lập với graph.",
        f"- Full directional claims: {counts['full_directional_claims']}/{counts['full_edge_claims']}.",
        f"- Partial directional claims: {counts['partial_directional_claims']}/{counts['partial_edge_claims']}; số cạnh mỗi scene dùng round-half-up.",
        f"- Ambiguous directional claims: {counts['ambiguous_directional_claims']}/{counts['ambiguous_edge_claims']}.",
        "- Automated truth audit: không false direction, không nonedge claim, không canonical ID/arrow/generator metadata trong story.",
        f"- Internal blinded text audit: {manual['scene_passes']}/20 scenes, {manual['evidence_classifications_correct']}/60 evidence classifications, minimum naturalness {manual['minimum_naturalness_score_1_to_5']}/5.",
        "",
        "## Blinding và giới hạn",
        "",
        "Panel chỉ dùng 20 development scenes. Mỗi scene có ba slot A/B/C được shuffle; panel không chứa scene/study ID, split, variant label, canonical mapping, truth edge hay seed. Kết quả trên là internal implementation-quality review, không phải independent external human validation; giới hạn này phải được giữ khi báo cáo và nên bổ sung reviewer độc lập trước publication nếu claim mở rộng sang natural-language realism.",
        "",
        "## Evidence boundary",
        "",
        "Holdout stories được sinh và kiểm tra tự động theo protocol, nhưng không story holdout nào được mở trong manual panel. T19 gọi 0 API, không chạy SCD, LLM, reasoner, H1 hoặc H2, không đọc method result và không chấm holdout.",
        "",
        "## Quyền tiếp theo",
        "",
        "T19 chỉ cấp quyền T20 triển khai và kiểm thử H2 offline về consistent-extension constraints, global optimization và abstention. Live model calls và P1 holdout evaluation vẫn bị khóa.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def build(require_review: bool) -> tuple[dict[Path, bytes], dict[Path, bytes], dict[str, Any]]:
    config = _yaml(CONFIG_PATH)
    _, split, inventory = _validate_parent(config)
    raw_root = _artifact_path(config, "raw_root")
    inventory_by_study = {row["study_id"]: row for row in inventory}
    roles = {study_id: "development" for study_id in split["development_ids"]}
    roles.update({study_id: "holdout" for study_id in split["holdout_ids"]})
    raw: dict[Path, bytes] = {}
    bundles: dict[str, Any] = {}
    story_manifest: list[dict[str, Any]] = []
    alias_manifest: list[dict[str, Any]] = []
    directional_totals = Counter()
    edge_totals = Counter()
    alias_exposure = Counter()
    for study_id in sorted(inventory_by_study):
        scene_inventory = inventory_by_study[study_id]
        scm_path = ROOT / next(
            item["path"] for item in scene_inventory["artifacts"] if item["path"].endswith("/scm.json")
        )
        scm_entry = next(item for item in scene_inventory["artifacts"] if item["path"].endswith("/scm.json"))
        if _entry(scm_path)["sha256"] != scm_entry["sha256"]:
            raise RuntimeError(f"T18 SCM hash drift: {study_id}")
        scm = _json(scm_path)
        bundle = build_story_bundle(scm, config)
        counts = validate_story_bundle(bundle, config)
        bundles[study_id] = bundle
        scene_dir = raw_root / study_id
        alias_record = {
            "schema_version": "fourgraph.p1_alias_map.v1",
            "study_id": study_id,
            "scene_id": bundle.scene_id,
            "adapter_only_not_model_input": True,
            "mapping": [
                {"canonical_id": canonical, "public_alias": alias}
                for canonical, alias in bundle.alias_map
            ],
        }
        alias_payload = canonical_line(alias_record)
        alias_path = scene_dir / "alias_map.json"
        raw[alias_path] = alias_payload
        alias_manifest.append(
            {
                "schema_version": "fourgraph.p1_t19_alias_manifest.v1",
                "study_id": study_id,
                "scene_id": bundle.scene_id,
                "split": roles[study_id],
                "mapping_sha256": sha256_hex(alias_payload),
                "mapping_entries": len(bundle.alias_map),
                "public_aliases_not_persisted_in_manifest": True,
                "model_visible": False,
                "reasoner_visible": False,
            }
        )
        alias_exposure.update(alias for _, alias in bundle.alias_map)
        truth_path = scene_dir / "story_truth.json"
        raw[truth_path] = canonical_line(bundle.truth_record)
        edge_count = len(bundle.truth_record["oracle_edges"])
        for record in bundle.public_records:
            variant = record["evidence_variant"]
            story_path = scene_dir / f"story_{variant}.json"
            payload = canonical_line(record)
            raw[story_path] = payload
            story = public_builder_view(record)["story"]
            directional_totals[variant] += counts[variant]
            edge_totals[variant] += edge_count
            story_manifest.append(
                {
                    "schema_version": "fourgraph.p1_t19_story_manifest.v1",
                    "artifact_id": record["artifact_id"],
                    "study_id": study_id,
                    "scene_id": bundle.scene_id,
                    "split": roles[study_id],
                    "variant": variant,
                    "artifact_path": story_path.relative_to(ROOT).as_posix(),
                    "artifact_bytes": len(payload),
                    "artifact_sha256": sha256_hex(payload),
                    "builder_view_sha256": sha256_hex(canonical_json_bytes({"story": story})),
                    "alias_map_sha256": sha256_hex(alias_payload),
                    "edge_claim_count": edge_count,
                    "directional_claim_count": counts[variant],
                    "symmetric_claim_count": edge_count - counts[variant],
                    "public_names_or_story_persisted_in_manifest": False,
                    "gold_graph_persisted_in_manifest": False,
                }
            )
    panel, blind_key = _blind_panel(bundles, list(split["development_ids"]), config)
    key_path = _artifact_path(config, "blinded_key")
    raw[key_path] = canonical_line(blind_key)
    story_manifest.sort(key=lambda row: (row["study_id"], VARIANTS.index(row["variant"])))
    alias_manifest.sort(key=lambda row: row["study_id"])
    preliminary: dict[Path, bytes] = {
        _artifact_path(config, "story_manifest"): b"".join(canonical_line(row) for row in story_manifest),
        _artifact_path(config, "alias_manifest"): b"".join(canonical_line(row) for row in alias_manifest),
        _artifact_path(config, "blinded_panel"): b"".join(canonical_line(row) for row in panel),
    }
    if not require_review:
        return preliminary, raw, {
            "review_pending": True,
            "scenes": 100,
            "stories": 300,
            "panel_scenes": 20,
            "api_calls": 0,
        }

    review_path = _artifact_path(config, "blinded_review")
    if not review_path.is_file():
        raise RuntimeError(f"Missing blinded review: {review_path.relative_to(ROOT)}")
    review_rows = _jsonl(review_path)
    review_audit = _validate_review(review_rows, panel, blind_key)
    raw_entries = [_entry(path, payload) for path, payload in sorted(raw.items(), key=lambda item: item[0].as_posix())]
    raw_tree_hash = sha256_hex(canonical_json_bytes(raw_entries))
    dependencies = [CONFIG_PATH, SCHEMA_PATH, MODULE_PATH, SCRIPT_PATH, review_path]
    dependencies.extend(ROOT / str(path) for path in config["dependencies"])
    dependencies = list(dict.fromkeys(dependencies))
    audit: dict[str, Any] = {
        "schema_version": "fourgraph.p1_t19_story_audit.v1",
        "task": "T19",
        "experiment_id": config["experiment_id"],
        "dependencies": [_entry(path) for path in dependencies],
        "outputs": [],
        "raw_artifact_tree": {
            "root": raw_root.relative_to(ROOT).as_posix(),
            "file_count": len(raw_entries),
            "bytes": sum(item["bytes"] for item in raw_entries),
            "sha256": raw_tree_hash,
        },
        "counts": {
            "scenes": 100,
            "development_scenes": 20,
            "holdout_scenes": 80,
            "public_stories": len(story_manifest),
            "alias_maps": len(alias_manifest),
            "full_edge_claims": edge_totals["full"],
            "full_directional_claims": directional_totals["full"],
            "partial_edge_claims": edge_totals["partial"],
            "partial_directional_claims": directional_totals["partial"],
            "ambiguous_edge_claims": edge_totals["ambiguous"],
            "ambiguous_directional_claims": directional_totals["ambiguous"],
            "false_directional_claims": 0,
            "nonedge_direct_claims": 0,
            "canonical_ids_in_story": 0,
            "manual_panel_holdout_scenes": 0,
        },
        "alias_exposure": dict(sorted(alias_exposure.items())),
        "manual_blinded_audit": review_audit,
        "evidence_boundary": {
            "api_calls": 0,
            "provider_SDK_imported_or_called": False,
            "SCD_executed": False,
            "LLM_executed": False,
            "reasoner_executed": False,
            "H1_executed": False,
            "H2_implemented_or_executed": False,
            "holdout_stories_generated_and_automatically_validated": True,
            "holdout_story_content_manually_reviewed": False,
            "holdout_method_results_accessed": False,
            "holdout_downstream_scored": False,
        },
        "limitations": {
            "stories_are_controlled_synthetic_stimuli_not_domain_narratives": True,
            "manual_review_is_internal_not_independent_external_human_review": True,
            "external_human_review_recommended_before_natural_language_realism_claim": True,
        },
        "verdict": {
            "t19_complete": True,
            "all_300_stories_valid": True,
            "directional_evidence_doses_exact": True,
            "blinded_internal_audit_20_of_20": review_audit["scene_passes"] == 20,
            "generator_reproducible": True,
            "t20_h2_offline_conformance_authorized": True,
            "live_model_calls_authorized": False,
            "H2_live_execution_authorized": False,
            "p1_holdout_evaluation_authorized": False,
        },
    }
    report_payload = _report(audit)
    report_path = _artifact_path(config, "report")
    outputs_without_audit = {**preliminary, report_path: report_payload}
    audit["outputs"] = [
        _entry(path, payload)
        for path, payload in sorted(outputs_without_audit.items(), key=lambda item: item[0].as_posix())
    ]
    versioned = {**outputs_without_audit, _artifact_path(config, "audit"): canonical_line(audit)}
    return versioned, raw, {
        "t19_complete": True,
        "scenes": 100,
        "stories": 300,
        "manual_scene_passes": review_audit["scene_passes"],
        "raw_files": len(raw_entries),
        "raw_tree_sha256": raw_tree_hash,
        "t20_authorized": True,
    }


def _compare(path: Path, payload: bytes) -> None:
    if not path.is_file():
        raise RuntimeError(f"Missing artifact: {path.relative_to(ROOT)}")
    actual = path.read_bytes()
    if actual != payload:
        raise RuntimeError(
            f"Byte drift: {path.relative_to(ROOT)} expected={sha256_hex(payload)} actual={sha256_hex(actual)}"
        )


def _write(path: Path, payload: bytes, replace: bool) -> None:
    if path.exists() and not replace:
        _compare(path, payload)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true", help="Generate stories and blinded panel before review.")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--replace-provisional", action="store_true")
    args = parser.parse_args()
    if args.check and (args.prepare or args.replace_provisional):
        raise ValueError("--check cannot be combined with write lifecycle flags")
    versioned, raw, summary = build(require_review=not args.prepare)
    if args.check:
        for path, payload in {**raw, **versioned}.items():
            _compare(path, payload)
        config = _yaml(CONFIG_PATH)
        raw_root = _artifact_path(config, "raw_root")
        expected = {path.resolve() for path in raw}
        actual = {path.resolve() for path in raw_root.rglob("*") if path.is_file()}
        if actual != expected:
            raise RuntimeError("T19 raw artifact file-set drift")
    else:
        for path, payload in raw.items():
            _write(path, payload, args.replace_provisional)
        for path, payload in versioned.items():
            _write(path, payload, args.replace_provisional)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
