from atlas.validation.models import ScenarioDefinition, ScenarioStatus
from atlas.validation.runner import ScenarioRunner


def test_runner_passes_existing_path(tmp_path) -> None:
    (tmp_path / "atlas.txt").write_text("ok", encoding="utf-8")
    scenario = ScenarioDefinition.from_dict(
        {
            "id": "SMOKE-001",
            "title": "Smoke",
            "domain": "core",
            "execution": "automated",
            "checks": [{"type": "path_exists", "path": "atlas.txt"}],
        }
    )

    result = ScenarioRunner(tmp_path).run(scenario)

    assert result.status is ScenarioStatus.PASS


def test_runner_fails_missing_path(tmp_path) -> None:
    scenario = ScenarioDefinition.from_dict(
        {
            "id": "SMOKE-002",
            "title": "Smoke",
            "domain": "core",
            "execution": "automated",
            "checks": [{"type": "path_exists", "path": "missing.txt"}],
        }
    )

    result = ScenarioRunner(tmp_path).run(scenario)

    assert result.status is ScenarioStatus.FAIL


def test_runner_does_not_execute_manual_scenario(tmp_path) -> None:
    scenario = ScenarioDefinition.from_dict(
        {
            "id": "MANUAL-001",
            "title": "Manual",
            "domain": "vision",
            "execution": "manual",
        }
    )

    result = ScenarioRunner(tmp_path).run(scenario)

    assert result.status is ScenarioStatus.MANUAL


def test_runner_rejects_path_escape(tmp_path) -> None:
    scenario = ScenarioDefinition.from_dict(
        {
            "id": "SEC-001",
            "title": "Escape",
            "domain": "security",
            "execution": "automated",
            "checks": [{"type": "path_exists", "path": "../outside.txt"}],
        }
    )

    runner = ScenarioRunner(tmp_path)
    try:
        runner.run(scenario)
    except ValueError as exc:
        assert "escapes project root" in str(exc)
    else:
        raise AssertionError("path escape should fail")
