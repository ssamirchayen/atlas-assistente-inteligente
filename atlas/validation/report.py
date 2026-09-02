"""Console, JSON and Markdown reports for Atlas Validation Lab."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .models import ScenarioResult


def summarize(results: list[ScenarioResult]) -> dict[str, int]:
    counts = Counter(result.status.value for result in results)
    return dict(sorted(counts.items()))


def render_console(results: list[ScenarioResult]) -> str:
    lines = ["ATLAS VALIDATION LAB", "=" * 72]
    for result in results:
        lines.append(
            f"[{result.status.value:7}] {result.scenario_id:16} "
            f"{result.domain:12} {result.title}"
        )
        if result.metrics:
            lines.append(
                "          "
                f"p50={result.metrics['latency_p50_ms']:.3f} ms | "
                f"p95={result.metrics['latency_p95_ms']:.3f} ms | "
                f"CPU={result.metrics['cpu_percent']:.2f}% | "
                f"RAM delta={result.metrics['memory_delta_mb']:.3f} MB"
            )
    lines.append("-" * 72)
    summary = summarize(results)
    summary_text = " | ".join(f"{key}: {value}" for key, value in summary.items())
    lines.append(summary_text or "No scenarios selected.")
    return "\n".join(lines)


def write_json(results: list[ScenarioResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summarize(results),
        "results": [
            {
                **asdict(result),
                "status": result.status.value,
            }
            for result in results
        ],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_markdown(results: list[ScenarioResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Atlas Validation Report",
        "",
        "| Status | ID | Domain | Scenario |",
        "|---|---|---|---|",
    ]
    for result in results:
        lines.append(
            f"| {result.status.value} | {result.scenario_id} | "
            f"{result.domain} | {result.title} |"
        )
    lines.extend(["", "## Summary", ""])
    for status, count in summarize(results).items():
        lines.append(f"- **{status}:** {count}")

    measured = [result for result in results if result.metrics]
    if measured:
        lines.extend(
            [
                "",
                "## Performance",
                "",
                "| ID | Iterations | p50 ms | p95 ms | CPU % | RAM delta MB |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for result in measured:
            metrics = result.metrics
            lines.append(
                f"| {result.scenario_id} | {metrics['iterations']} | "
                f"{metrics['latency_p50_ms']:.3f} | "
                f"{metrics['latency_p95_ms']:.3f} | "
                f"{metrics['cpu_percent']:.3f} | "
                f"{metrics['memory_delta_mb']:.3f} |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
