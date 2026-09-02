import json

from atlas.validation.models import ScenarioResult, ScenarioStatus
from atlas.validation.report import render_console, write_json, write_markdown


def _result() -> ScenarioResult:
    return ScenarioResult(
        scenario_id="PERF-001",
        title="Benchmark",
        domain="performance",
        status=ScenarioStatus.PASS,
        metrics={
            "iterations": 10,
            "warmup_iterations": 1,
            "latency_min_ms": 1.0,
            "latency_p50_ms": 2.0,
            "latency_p95_ms": 3.0,
            "latency_max_ms": 4.0,
            "cpu_time_ms": 1.0,
            "cpu_percent": 5.0,
            "memory_start_mb": 100.0,
            "memory_end_mb": 101.0,
            "memory_peak_mb": 102.0,
            "memory_delta_mb": 2.0,
        },
    )


def test_console_renders_compact_performance_metrics() -> None:
    output = render_console([_result()])

    assert "p50=2.000 ms" in output
    assert "p95=3.000 ms" in output
    assert "RAM delta=2.000 MB" in output


def test_json_and_markdown_preserve_performance_metrics(tmp_path) -> None:
    json_path = tmp_path / "report.json"
    markdown_path = tmp_path / "report.md"

    write_json([_result()], json_path)
    write_markdown([_result()], markdown_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert payload["results"][0]["metrics"]["latency_p95_ms"] == 3.0
    assert "## Performance" in markdown
    assert "| PERF-001 | 10 | 2.000 | 3.000 |" in markdown
