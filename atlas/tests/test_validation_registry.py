import json

from atlas.validation.registry import ScenarioRegistry


def test_registry_loads_json_files(tmp_path) -> None:
    payload = [
        {
            "id": "CORE-001",
            "title": "Core",
            "domain": "core",
            "execution": "automated",
        }
    ]
    (tmp_path / "core.json").write_text(json.dumps(payload), encoding="utf-8")

    scenarios = ScenarioRegistry(tmp_path).load()

    assert len(scenarios) == 1
    assert scenarios[0].scenario_id == "CORE-001"


def test_registry_rejects_duplicate_ids(tmp_path) -> None:
    payload = [
        {
            "id": "DUP-001",
            "title": "One",
            "domain": "core",
            "execution": "manual",
        },
        {
            "id": "DUP-001",
            "title": "Two",
            "domain": "voice",
            "execution": "manual",
        },
    ]
    (tmp_path / "duplicates.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    try:
        ScenarioRegistry(tmp_path).load()
    except ValueError as exc:
        assert "Duplicate scenario id" in str(exc)
    else:
        raise AssertionError("duplicate ids should fail")
