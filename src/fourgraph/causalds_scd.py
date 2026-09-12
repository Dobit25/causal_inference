from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any, Iterable

from fourgraph.causalds_access import resolve_public_artifact
from fourgraph.partial_graph import PartialGraph, consistent_extension


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    family: str
    eligible_for_primary: bool
    parameters: dict[str, Any]


@dataclass(frozen=True)
class SceneData:
    scene_id: str
    anonymous_names: tuple[str, ...]
    binary_flags: tuple[bool, ...]
    values: Any


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def expand_candidates(config: dict[str, Any]) -> list[CandidateSpec]:
    candidates = config["candidates"]
    expanded: list[CandidateSpec] = []

    pc_basis = candidates["eligible"]["pcmax_basis_lrt"]
    for alpha, truncation in product(
        pc_basis["alpha"], pc_basis["truncation_limit"]
    ):
        alpha_label = str(alpha).replace(".", "p")
        expanded.append(
            CandidateSpec(
                f"pcmax_basis_lrt__a{alpha_label}__t{truncation}",
                "pcmax_basis_lrt",
                True,
                {"alpha": float(alpha), "truncation_limit": int(truncation)},
            )
        )

    boss_basis = candidates["eligible"]["boss_basis_bic"]
    for penalty, truncation in product(
        boss_basis["penalty_discount"], boss_basis["truncation_limit"]
    ):
        penalty_label = str(penalty).replace(".0", "").replace(".", "p")
        expanded.append(
            CandidateSpec(
                f"boss_basis_bic__p{penalty_label}__t{truncation}",
                "boss_basis_bic",
                True,
                {
                    "penalty_discount": float(penalty),
                    "truncation_limit": int(truncation),
                },
            )
        )

    for family in (
        "pcmax_conditional_gaussian_lrt",
        "pcmax_degenerate_gaussian_lrt",
    ):
        baseline = candidates["stress_baselines"][family]
        for alpha in baseline["alpha"]:
            alpha_label = str(alpha).replace(".", "p")
            expanded.append(
                CandidateSpec(
                    f"{family}__a{alpha_label}",
                    family,
                    False,
                    {"alpha": float(alpha)},
                )
            )
    return sorted(expanded, key=lambda item: item.candidate_id)


def _read_schema(source_root: Path, scene_id: str) -> dict[str, Any]:
    path = resolve_public_artifact(source_root, scene_id, "clean", "schema")
    return json.loads(path.read_text(encoding="utf-8"))


def load_scene_data(
    source_root: Path,
    scene_id: str,
    row_indices: Iterable[int] | None = None,
) -> SceneData:
    """Load the public table, apply the frozen anonymous typed view, and z-score."""

    import numpy as np
    import pyarrow.parquet as pq

    schema = _read_schema(source_root, scene_id)
    columns = list(schema["columns"])
    anonymous_names = tuple(f"X{index:03d}" for index in range(len(columns)))
    binary_flags = tuple(
        bool(schema["columns"][column].get("is_binary", False))
        for column in columns
    )
    parquet_path = resolve_public_artifact(
        source_root, scene_id, "clean", "data"
    )
    table = pq.read_table(parquet_path, columns=columns)
    values = np.column_stack(
        [
            np.asarray(
                table.column(column).combine_chunks().to_numpy(zero_copy_only=False),
                dtype=np.float64,
            )
            for column in columns
        ]
    )
    if row_indices is not None:
        indices = np.asarray(list(row_indices), dtype=np.int64)
        values = values[indices]
    values = values.copy()
    for column_index, is_binary in enumerate(binary_flags):
        column = values[:, column_index]
        if is_binary:
            if not np.isin(column, [0.0, 1.0]).all():
                raise ValueError(f"Binary support violation in {scene_id}")
            continue
        standard_deviation = float(column.std(ddof=1))
        if not np.isfinite(standard_deviation) or standard_deviation <= 0:
            raise ValueError(f"Non-scalable continuous column in {scene_id}")
        values[:, column_index] = (
            column - float(column.mean())
        ) / standard_deviation
    if not np.isfinite(values).all():
        raise ValueError(f"Non-finite preprocessed value in {scene_id}")
    return SceneData(scene_id, anonymous_names, binary_flags, values)


def deterministic_half_sample_indices(
    row_count: int,
    global_seed: int,
    scene_id: str,
    replication: int,
) -> list[int]:
    import numpy as np

    material = f"{global_seed}|{scene_id}|{replication}".encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(material).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    return sorted(
        int(value)
        for value in rng.choice(row_count, size=row_count // 2, replace=False)
    )


class TetradBackend:
    def __init__(self, jar_path: Path, expected_sha256: str):
        self.jar_path = jar_path.resolve()
        if not self.jar_path.is_file():
            raise FileNotFoundError(f"Pinned Tetrad jar not found: {self.jar_path}")
        actual_hash = file_sha256(self.jar_path)
        if actual_hash != expected_sha256.upper():
            raise ValueError(
                f"Tetrad jar hash mismatch: {actual_hash} != {expected_sha256}"
            )
        self.jar_sha256 = actual_hash
        self._start_jvm()
        self._load_classes()

    def _start_jvm(self) -> None:
        import jpype
        import jpype.imports  # noqa: F401

        if not jpype.isJVMStarted():
            jpype.startJVM(
                jpype.getDefaultJVMPath(),
                "-ea",
                "-Xmx4g",
                classpath=[str(self.jar_path)],
            )

    def _load_classes(self) -> None:
        from jpype import JClass

        self.ArrayList = JClass("java.util.ArrayList")
        self.BoxDataSet = JClass("edu.cmu.tetrad.data.BoxDataSet")
        self.ContinuousVariable = JClass("edu.cmu.tetrad.data.ContinuousVariable")
        self.DiscreteVariable = JClass("edu.cmu.tetrad.data.DiscreteVariable")
        self.DoubleDataBox = JClass("edu.cmu.tetrad.data.DoubleDataBox")
        self.MixedDataBox = JClass("edu.cmu.tetrad.data.MixedDataBox")
        self.Parameters = JClass("edu.cmu.tetrad.util.Parameters")
        self.Params = JClass("edu.cmu.tetrad.util.Params")
        self.Pc = JClass(
            "edu.cmu.tetrad.algcomparison.algorithm.oracle.cpdag.Pc"
        )
        self.Boss = JClass(
            "edu.cmu.tetrad.algcomparison.algorithm.oracle.cpdag.Boss"
        )
        self.BasisFunctionLrt = JClass(
            "edu.cmu.tetrad.algcomparison.independence.BasisFunctionLrt"
        )
        self.BasisFunctionBicScore = JClass(
            "edu.cmu.tetrad.algcomparison.score.BasisFunctionBicScore"
        )
        self.ConditionalGaussianLrt = JClass(
            "edu.cmu.tetrad.algcomparison.independence.ConditionalGaussianLrt"
        )
        self.DegenerateGaussianLrt = JClass(
            "edu.cmu.tetrad.algcomparison.independence.DegenerateGaussianLrt"
        )

    def to_java_dataset(self, scene_data: SceneData) -> Any:
        import jpype

        row_count, column_count = scene_data.values.shape
        variables = self.ArrayList()
        for name, is_binary in zip(
            scene_data.anonymous_names, scene_data.binary_flags
        ):
            if is_binary:
                categories = self.ArrayList()
                categories.add("0")
                categories.add("1")
                variables.add(self.DiscreteVariable(name, categories))
            else:
                variables.add(self.ContinuousVariable(name))
        if any(scene_data.binary_flags):
            data_box = self.MixedDataBox(variables, row_count)
        else:
            data_box = self.DoubleDataBox(row_count, column_count)
        for column_index, is_binary in enumerate(scene_data.binary_flags):
            column = scene_data.values[:, column_index]
            if is_binary:
                for row_index, value in enumerate(column):
                    data_box.set(
                        row_index, column_index, jpype.JInt(int(value))
                    )
            else:
                for row_index, value in enumerate(column):
                    data_box.set(
                        row_index, column_index, jpype.JDouble(float(value))
                    )
        return self.BoxDataSet(data_box, variables)

    def run(self, dataset: Any, spec: CandidateSpec) -> tuple[PartialGraph, float]:
        import jpype

        params = self.Parameters()
        params.set(self.Params.DEPTH, jpype.JInt(-1))
        params.set(self.Params.STABLE_FAS, jpype.JBoolean(True))
        params.set(self.Params.ALLOW_BIDIRECTED, jpype.JBoolean(False))
        params.set(self.Params.COLLIDER_ORIENTATION_STYLE, jpype.JInt(3))

        if spec.family == "pcmax_basis_lrt":
            params.set(self.Params.ALPHA, jpype.JDouble(spec.parameters["alpha"]))
            params.set(
                self.Params.TRUNCATION_LIMIT,
                jpype.JInt(spec.parameters["truncation_limit"]),
            )
            params.set(self.Params.EFFECTIVE_SAMPLE_SIZE, jpype.JDouble(-1.0))
            algorithm = self.Pc(self.BasisFunctionLrt())
        elif spec.family == "boss_basis_bic":
            params.set(
                self.Params.TRUNCATION_LIMIT,
                jpype.JInt(spec.parameters["truncation_limit"]),
            )
            params.set(
                self.Params.PENALTY_DISCOUNT,
                jpype.JDouble(spec.parameters["penalty_discount"]),
            )
            params.set(self.Params.SINGULARITY_LAMBDA, jpype.JDouble(0.0))
            params.set(self.Params.DO_ONE_EQUATION_ONLY, jpype.JBoolean(False))
            params.set(self.Params.NUM_STARTS, jpype.JInt(1))
            params.set(self.Params.USE_BES, jpype.JBoolean(False))
            params.set(self.Params.USE_DATA_ORDER, jpype.JBoolean(True))
            params.set(self.Params.OUTPUT_CPDAG, jpype.JBoolean(True))
            algorithm = self.Boss(self.BasisFunctionBicScore())
        elif spec.family == "pcmax_conditional_gaussian_lrt":
            params.set(self.Params.ALPHA, jpype.JDouble(spec.parameters["alpha"]))
            params.set(self.Params.DISCRETIZE, jpype.JBoolean(False))
            params.set(self.Params.NUM_CATEGORIES_TO_DISCRETIZE, jpype.JInt(3))
            params.set(self.Params.MIN_SAMPLE_SIZE_PER_CELL, jpype.JInt(4))
            params.set(self.Params.EFFECTIVE_SAMPLE_SIZE, jpype.JDouble(-1.0))
            algorithm = self.Pc(self.ConditionalGaussianLrt())
        elif spec.family == "pcmax_degenerate_gaussian_lrt":
            params.set(self.Params.ALPHA, jpype.JDouble(spec.parameters["alpha"]))
            params.set(self.Params.SINGULARITY_LAMBDA, jpype.JDouble(0.0))
            algorithm = self.Pc(self.DegenerateGaussianLrt())
        else:
            raise ValueError(f"Unknown candidate family: {spec.family}")

        started = time.perf_counter()
        graph = algorithm.search(dataset, params)
        elapsed = time.perf_counter() - started
        parsed = self._parse_graph(graph)
        consistent_extension(parsed)
        return parsed, elapsed

    @staticmethod
    def _parse_graph(java_graph: Any) -> PartialGraph:
        nodes = tuple(sorted(str(node.getName()) for node in java_graph.getNodes()))
        directed: set[tuple[str, str]] = set()
        undirected: set[tuple[str, str]] = set()
        for edge in java_graph.getEdges():
            left = str(edge.getNode1().getName())
            right = str(edge.getNode2().getName())
            left_mark = str(edge.getEndpoint1().name())
            right_mark = str(edge.getEndpoint2().name())
            if left_mark == "TAIL" and right_mark == "ARROW":
                directed.add((left, right))
            elif left_mark == "ARROW" and right_mark == "TAIL":
                directed.add((right, left))
            elif left_mark == "TAIL" and right_mark == "TAIL":
                undirected.add((left, right))
            else:
                raise ValueError(
                    f"Non-CPDAG edge marks: {left} {left_mark}-{right_mark} {right}"
                )
        return PartialGraph.build(nodes, directed, undirected)
