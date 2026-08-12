from __future__ import annotations

from pathlib import Path

from atlas.agents.coding import CodingAgent
from atlas.agents.desktop import DesktopAgent


def test_coding_agent_uses_configured_project_path(tmp_path: Path) -> None:
    agent = CodingAgent(project_path=tmp_path)

    actions = agent.plan("abra o projeto atlas")

    assert len(actions) == 1
    command = actions[0].parameters["command"]
    assert command == ["code", str(tmp_path.resolve())]


def test_coding_agent_runs_project_from_configured_path(
    tmp_path: Path,
) -> None:
    agent = CodingAgent(project_path=tmp_path)

    actions = agent.plan("execute o projeto")

    assert len(actions) == 1
    command = actions[0].parameters["command"]
    assert command[:5] == [
        "powershell.exe",
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
    ]
    assert str(tmp_path.resolve()) in command[5]
    assert "C:\\Atlas2" not in command[5]


def test_desktop_agent_opens_configured_project(tmp_path: Path) -> None:
    agent = DesktopAgent(project_path=tmp_path)

    actions = agent.plan("abra nosso projeto no vs code")

    assert len(actions) == 1
    assert actions[0].parameters["command"] == [
        "code",
        str(tmp_path.resolve()),
    ]


def test_desktop_agent_opens_main_from_configured_project(
    tmp_path: Path,
) -> None:
    agent = DesktopAgent(project_path=tmp_path)

    actions = agent.plan("abra o projeto atlas main py")

    assert len(actions) == 1
    assert actions[0].parameters["command"] == [
        "code",
        str(tmp_path.resolve()),
        str(tmp_path.resolve() / "main.py"),
    ]


def test_agents_default_to_existing_project_directory() -> None:
    coding = CodingAgent()
    desktop = DesktopAgent()

    assert coding.project_path.is_dir()
    assert desktop.project_path == coding.project_path
