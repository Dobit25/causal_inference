from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fourgraph.causalds_scd import CandidateSpec, SceneData, TetradBackend

from .common import graph_record, sha256_file


class TetradAdapterError(RuntimeError):
    pass


class TetradAdapter:
    """Translate frozen Python scene data to the pinned Tetrad JAR."""

    def __init__(self, jar_path: Path, expected_sha256: str, *, fixture: bool = False):
        self.jar_path = jar_path.resolve()
        self.expected_sha256 = expected_sha256.upper()
        self.fixture = fixture
        if not self.jar_path.is_file():
            raise TetradAdapterError(f"Tetrad JAR missing: {self.jar_path}")
        actual = sha256_file(self.jar_path)
        if actual != self.expected_sha256:
            raise TetradAdapterError(f"Tetrad JAR hash mismatch: {actual} != {self.expected_sha256}")
        self.jar_sha256 = actual
        if not fixture:
            self.backend = TetradBackend(self.jar_path, self.expected_sha256)
            self._load_extra_classes()
        else:
            self.backend = None

    def _load_extra_classes(self) -> None:
        from jpype import JClass

        self.FisherZ = JClass("edu.cmu.tetrad.algcomparison.independence.FisherZ")
        self.SemBicScore = JClass("edu.cmu.tetrad.algcomparison.score.SemBicScore")
        self.Fges = JClass("edu.cmu.tetrad.algcomparison.algorithm.oracle.cpdag.Fges")
        self.Gfci = JClass("edu.cmu.tetrad.algcomparison.algorithm.oracle.pag.Gfci")

    def _fixture_graph(self, scene: SceneData, algorithm: str) -> dict[str, Any]:
        nodes = list(scene.anonymous_names)
        return graph_record(nodes, [], [nodes[:2]] if len(nodes) >= 2 else [], graph_type="pag" if algorithm == "GFCI" else "cpdag")

    def run(self, scene: SceneData, algorithm: str, parameters: dict[str, Any]) -> tuple[dict[str, Any], float]:
        if self.fixture:
            return self._fixture_graph(scene, algorithm), 0.0
        if self.backend is None:
            raise TetradAdapterError("adapter not initialized")
        started = time.perf_counter()
        if algorithm == "BOSS":
            spec = CandidateSpec("single_boss", "boss_basis_bic", True, {"penalty_discount": float(parameters["penalty_discount"]), "truncation_limit": int(parameters["truncation_limit"])})
            graph, _ = self.backend.run(self.backend.to_java_dataset(scene), spec)
            normalized = graph_record(list(graph.nodes), [list(e) for e in graph.directed], [list(e) for e in graph.undirected])
        else:
            normalized = self._run_non_boss(scene, algorithm, parameters)
        return normalized, time.perf_counter() - started

    def _run_non_boss(self, scene: SceneData, algorithm: str, parameters: dict[str, Any]) -> dict[str, Any]:
        import jpype

        dataset = self.backend.to_java_dataset(scene)
        params = self.backend.Parameters()
        params.set(self.backend.Params.DEPTH, jpype.JInt(int(parameters.get("depth", -1))))
        if algorithm == "PC":
            params.set(self.backend.Params.ALPHA, jpype.JDouble(float(parameters["alpha"])))
            params.set(self.backend.Params.STABLE_FAS, jpype.JBoolean(bool(parameters["stable_fas"])))
            searcher = self.backend.Pc(self.FisherZ())
            graph_type = "cpdag"
        elif algorithm == "FGES":
            params.set(self.backend.Params.PENALTY_DISCOUNT, jpype.JDouble(float(parameters["penalty_discount"])))
            params.set(self.backend.Params.MAX_DEGREE, jpype.JInt(int(parameters["max_degree"])))
            params.set(self.backend.Params.SYMMETRIC_FIRST_STEP, jpype.JBoolean(bool(parameters["symmetric_first_step"])))
            params.set(self.backend.Params.FAITHFULNESS_ASSUMED, jpype.JBoolean(bool(parameters["faithfulness_assumed"])))
            searcher = self.Fges(self.SemBicScore())
            graph_type = "cpdag"
        elif algorithm == "GFCI":
            params.set(self.backend.Params.PENALTY_DISCOUNT, jpype.JDouble(float(parameters["penalty_discount"])))
            params.set(self.backend.Params.MAX_DEGREE, jpype.JInt(int(parameters["max_degree"])))
            params.set(self.backend.Params.ALPHA, jpype.JDouble(float(parameters["alpha"])))
            params.set(self.backend.Params.FAITHFULNESS_ASSUMED, jpype.JBoolean(bool(parameters["faithfulness_assumed"])))
            # The pinned Tetrad API constructor is (IndependenceWrapper,
            # ScoreWrapper), i.e. Fisher-Z first and Sem-BIC second.
            searcher = self.Gfci(self.FisherZ(), self.SemBicScore())
            graph_type = "pag"
        else:
            raise TetradAdapterError(f"unsupported Tetrad algorithm: {algorithm}")
        return self._parse(searcher.search(dataset, params), graph_type)

    @staticmethod
    def _parse(java_graph: Any, graph_type: str) -> dict[str, Any]:
        nodes = sorted(str(node.getName()) for node in java_graph.getNodes())
        directed: list[list[str]] = []
        undirected: list[list[str]] = []
        for edge in java_graph.getEdges():
            left = str(edge.getNode1().getName())
            right = str(edge.getNode2().getName())
            mark_left = str(edge.getEndpoint1().name())
            mark_right = str(edge.getEndpoint2().name())
            if graph_type == "pag":
                if left != right:
                    undirected.append(sorted([left, right]))
            elif mark_left == "TAIL" and mark_right == "ARROW":
                directed.append([left, right])
            elif mark_left == "ARROW" and mark_right == "TAIL":
                directed.append([right, left])
            elif mark_left == "TAIL" and mark_right == "TAIL":
                undirected.append(sorted([left, right]))
            else:
                raise TetradAdapterError(f"invalid CPDAG endpoint marks: {mark_left}-{mark_right}")
        return graph_record(nodes, directed, undirected, graph_type=graph_type)
