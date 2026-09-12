from fourgraph.graph_adapters import make_hybrid_graph_artifact, make_oracle_graph_artifact, make_scd_graph_artifact
from fourgraph.graph_contract import EdgeAuditRecord, project_cpdag_artifact
from fourgraph.graph_metrics import cpdag_metrics_frozen, dag_metrics_frozen, hybrid_attribution, skeleton_metrics
from fourgraph.partial_graph import PartialGraph


SHA = "A" * 64
NODES = ("X000", "X001", "X002")


def test_skeleton_metrics_freeze_fp_fn_and_empty_conventions():
    truth = PartialGraph.build(NODES, directed=(("X000", "X001"),))
    estimate = PartialGraph.build(NODES, directed=(("X000", "X002"),))
    result = skeleton_metrics(estimate, truth)
    assert result == {
        "true_positive": 0, "false_positive": 1, "false_negative": 1,
        "precision": 0.0, "recall": 0.0, "f1": 0.0, "shd": 2,
    }
    empty = PartialGraph.build(NODES)
    assert skeleton_metrics(empty, empty)["f1"] == 1.0


def test_dag_metrics_count_reversal_once_in_shd_but_twice_in_edge_errors():
    truth = PartialGraph.build(NODES, directed=(("X000", "X001"), ("X001", "X002")))
    estimate = PartialGraph.build(NODES, directed=(("X001", "X000"), ("X001", "X002")))
    result = dag_metrics_frozen(estimate, truth)
    assert result["directed_true_positive"] == 1
    assert result["directed_false_positive"] == 1
    assert result["directed_false_negative"] == 1
    assert result["orientation_accuracy_on_common_adjacencies"] == 0.5
    assert result["shd_reversal_cost_one"] == 1
    assert result["normalized_shd_by_possible_pairs"] == 0.33333333


def test_cpdag_metrics_keep_unresolved_distinct_from_direction_error():
    truth = PartialGraph.build(NODES, directed=(("X000", "X001"), ("X002", "X001")))
    estimate = PartialGraph.build(NODES, undirected=(("X000", "X001"), ("X001", "X002")))
    result = cpdag_metrics_frozen(estimate, truth)
    assert result["oracle_compelled_count"] == 2
    assert result["predicted_compelled_count"] == 0
    assert result["missed_compelled"] == 2
    assert result["unresolved_rate"] == 1.0
    assert result["state_shd"] == 2


def test_hybrid_attribution_separates_inherited_and_semantic_errors():
    parent = make_scd_graph_artifact(
        scene_id="scene_000001",
        graph=PartialGraph.build(NODES, undirected=(("X000", "X001"), ("X001", "X002"))),
        graph_type="cpdag", builder_id="test.scd", builder_version="v1",
        config_sha256=SHA, input_artifact_sha256=("B" * 64,), seed=None,
    )
    projected = project_cpdag_artifact(parent, config_sha256=SHA)
    hybrid_graph = PartialGraph.build(NODES, directed=(("X000", "X001"), ("X001", "X002")))
    audit = tuple(
        EdgeAuditRecord.build(
            step=step, source=source, target=target, action="orient",
            before_mark="undirected", after_mark="directed", actor="hybrid",
            reason="public semantic fixture", arbitrary=False, confidence=0.9,
        )
        for step, (source, target) in enumerate(sorted(hybrid_graph.directed))
    )
    hybrid = make_hybrid_graph_artifact(
        parent_scd=parent, graph=hybrid_graph, builder_id="test.hybrid",
        builder_version="v1", config_sha256=SHA,
        input_artifact_sha256=("C" * 64,), seed=None, edge_audit=audit,
    )
    oracle = make_oracle_graph_artifact(
        scene_id="scene_000001", graph=hybrid_graph, builder_id="test.oracle",
        builder_version="v1", config_sha256=SHA,
        input_artifact_sha256=("D" * 64,),
    )
    result = hybrid_attribution(parent, projected, hybrid, oracle)
    assert result["unresolved_evaluable"] == 2
    assert result["semantic_orientation_correct"] == 2
    assert result["semantic_orientation_incorrect"] == 0
    assert result["inherited_skeleton_false_positive"] == 0
    assert result["inherited_skeleton_false_negative"] == 0
