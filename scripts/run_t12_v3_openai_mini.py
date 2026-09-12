"""Run/replay the frozen T12 v3 GPT-5.4 Mini candidate."""

from pathlib import Path

from run_t12_v2_openai_mini import main


if __name__ == "__main__":
    raise SystemExit(main(Path("configs/t12_v3_openai_mini.yaml")))
