from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_stage2_has_no_executor_network_or_arbitrary_commands() -> None:
    service = (ROOT / "atlas" / "edge" / "profile_service.py").read_text(
        encoding="utf-8"
    )
    profiles = (ROOT / "atlas" / "edge" / "profiles.py").read_text(
        encoding="utf-8"
    )
    combined = service + profiles

    assert "ProvisioningExecutor" not in combined
    assert "subprocess" not in combined
    assert "requests" not in combined
    assert "httpx" not in combined
    assert "shell=True" not in combined
    assert "INSTALL_WINGET_PACKAGE" not in service
