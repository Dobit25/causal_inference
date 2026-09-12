"""Task-routed T12 v3 prompt contract without changing v2 artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from fourgraph.graph_contract import canonical_json_bytes, sha256_hex
from fourgraph.reasoner import TASKS


TASK_MODULE_FILENAMES = {
    TASKS[0]: "one_valid_adjustment_set.txt",
    TASKS[1]: "all_minimal_adjustment_sets.txt",
    TASKS[2]: "minimal_adjustment_set_size.txt",
    TASKS[3]: "n_valid_adjustment_sets.txt",
    TASKS[4]: "forbidden_controls_list.txt",
}

EVIDENCE_MARKERS = ("{{GRAPH_JSON}}", "{{QUERY_JSON}}", "{{GLOSSARY_JSON}}")
TASK_MARKER = "{{TASK_MODULE}}"


@dataclass(frozen=True)
class PromptV3Bundle:
    base_path: Path
    base_template: str
    module_paths: Mapping[str, Path]
    modules: Mapping[str, str]

    @classmethod
    def load(
        cls,
        *,
        base_path: Path,
        module_paths: Mapping[str, Path],
    ) -> "PromptV3Bundle":
        if set(module_paths) != set(TASKS):
            raise ValueError("V3 prompt bundle requires exactly the five frozen tasks")
        base = base_path.read_text(encoding="utf-8")
        if base.count(TASK_MARKER) != 1:
            raise ValueError("V3 base must contain exactly one task-module marker")
        for marker in EVIDENCE_MARKERS:
            if base.count(marker) != 1:
                raise ValueError(f"V3 base must contain exactly one marker: {marker}")
        modules = {
            task: Path(path).read_text(encoding="utf-8")
            for task, path in module_paths.items()
        }
        for task, module in modules.items():
            if not module.strip():
                raise ValueError(f"Empty V3 task module: {task}")
            if any(marker in module for marker in (*EVIDENCE_MARKERS, TASK_MARKER)):
                raise ValueError(f"V3 task module contains a reserved marker: {task}")
            if task not in module:
                raise ValueError(f"V3 task module does not identify its task: {task}")
        return cls(Path(base_path), base, dict(module_paths), modules)

    def template_for(self, task_id: str) -> str:
        if task_id not in self.modules:
            raise ValueError(f"Task is outside the frozen V3 family: {task_id}")
        template = self.base_template.replace(TASK_MARKER, self.modules[task_id].strip())
        if TASK_MARKER in template:
            raise ValueError("Task-module marker survived V3 assembly")
        return template

    def render(
        self,
        *,
        task_id: str,
        graph_reasoner_view: Mapping[str, Any],
        query_view: Mapping[str, Any],
        glossary: list[dict[str, str]],
    ) -> str:
        if query_view.get("task_id") != task_id:
            raise ValueError("V3 task module and query task_id disagree")
        if set(graph_reasoner_view) != {
            "schema_version",
            "graph_type",
            "nodes",
            "edges",
        }:
            raise ValueError("V3 requires the stripped canonical reasoner graph view")
        if any(set(item) != {"id", "type"} for item in glossary):
            raise ValueError("V3 glossary must contain canonical ID and type only")
        prompt = self.template_for(task_id)
        replacements = {
            "{{GRAPH_JSON}}": canonical_json_bytes(dict(graph_reasoner_view)).decode(
                "utf-8"
            ),
            "{{QUERY_JSON}}": canonical_json_bytes(dict(query_view)).decode("utf-8"),
            "{{GLOSSARY_JSON}}": canonical_json_bytes(glossary).decode("utf-8"),
        }
        for marker, value in replacements.items():
            if prompt.count(marker) != 1:
                raise ValueError(f"V3 assembled template marker mismatch: {marker}")
            prompt = prompt.replace(marker, value)
        if any(marker in prompt for marker in EVIDENCE_MARKERS):
            raise ValueError("V3 evidence marker survived rendering")
        return prompt

    def manifest_components(self) -> dict[str, Any]:
        modules = {
            task: {
                "path": self.module_paths[task].as_posix(),
                "sha256": sha256_hex(self.modules[task].encode("utf-8")),
                "assembled_template_sha256": sha256_hex(
                    self.template_for(task).encode("utf-8")
                ),
            }
            for task in TASKS
        }
        components = {
            "base": {
                "path": self.base_path.as_posix(),
                "sha256": sha256_hex(self.base_template.encode("utf-8")),
            },
            "modules": modules,
        }
        return {
            **components,
            "bundle_sha256": sha256_hex(canonical_json_bytes(components)),
        }
