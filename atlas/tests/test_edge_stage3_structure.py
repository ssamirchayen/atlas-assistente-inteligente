from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_stage3_has_no_free_shell_or_remote_transport() -> None:
    paths = (
        ROOT / "atlas" / "edge" / "execution.py",
        ROOT / "atlas" / "edge" / "task_queue.py",
        ROOT / "atlas" / "provisioning" / "settings.py",
    )
    combined = "".join(path.read_text(encoding="utf-8") for path in paths)

    assert "shell=True" not in combined
    assert "os.system" not in combined
    assert "subprocess" not in combined
    assert "requests" not in combined
    assert "httpx" not in combined
