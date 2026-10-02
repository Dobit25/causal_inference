from fourgraph.p1v3_ensemble_amendment import bootstrap_method_level_skeleton, primary_ensemble_from_methods


def test_bootstrap_method_level_threshold_and_direction_invariance():
    nodes = ["X000", "X001", "X002", "X003"]
    rates = {("X000", "X001"): 0.80, ("X000", "X002"): 0.7999, ("X001", "X002"): 0.95}
    expected = {("X000", "X001"), ("X001", "X002")}
    assert bootstrap_method_level_skeleton(nodes, rates) == expected


def test_outer_three_of_five_majority():
    nodes = ["X000", "X001", "X002"]
    edge = [("X000", "X001")]
    assert primary_ensemble_from_methods(nodes, single_boss=edge, bootstrap_boss=edge, pc=edge, mmpc=[], fges=[]) == {("X000", "X001")}
