from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_stage1_has_no_remote_transport_or_provisioning_executor() -> None:
    source = (ROOT / "atlas" / "edge" / "agent.py").read_text(
        encoding="utf-8"
    )

    for forbidden in (
        "ProvisioningExecutor",
        "subprocess",
        "shell=True",
        "requests.",
        "httpx.",
        "winget install",
    ):
        assert forbidden not in source


def test_stage1_uses_random_identity_and_atomic_storage() -> None:
    agent_source = (ROOT / "atlas" / "edge" / "agent.py").read_text(
        encoding="utf-8"
    )
    storage_source = (ROOT / "atlas" / "edge" / "storage.py").read_text(
        encoding="utf-8"
    )

    assert "uuid4" in agent_source
    assert "os.replace" in storage_source
    assert "max_bytes" in storage_source
