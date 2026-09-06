"""Launch the Atlas Benchmark mini frontend."""

from pathlib import Path

from atlas.benchmark.dashboard_window import run_dashboard


if __name__ == "__main__":
    raise SystemExit(run_dashboard(Path(__file__).resolve().parent))
