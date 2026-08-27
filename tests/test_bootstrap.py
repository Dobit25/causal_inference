import random

import pytest

from fourgraph.cli import main
from fourgraph.config import load_config
from fourgraph.reproducibility import set_seed


def test_pilot_config_loads() -> None:
    config = load_config("configs/pilot.yaml")

    assert config["experiment"]["seed"] == 42
    assert config["graphs"]["methods"] == ["llm", "scd", "hybrid", "oracle"]


def test_config_rejects_non_mapping(tmp_path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text("- item\n", encoding="utf-8")

    with pytest.raises(ValueError, match="YAML mapping"):
        load_config(path)


def test_seed_reproduces_python_randomness() -> None:
    set_seed(42)
    first = [random.random() for _ in range(3)]
    set_seed(42)
    second = [random.random() for _ in range(3)]

    assert first == second


def test_validate_config_command(capsys) -> None:
    exit_code = main(["validate-config", "configs/pilot.yaml"])

    assert exit_code == 0
    assert "Valid config" in capsys.readouterr().out

