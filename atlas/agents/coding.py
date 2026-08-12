from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from atlas.agents.base import AgentMetadata
from atlas.core.config import PROJECT_DIR
from atlas.planner.actions import Action
from atlas.session.manager import SessionManager


class CodingAgent:
    metadata = AgentMetadata(
        name="coding",
        display_name="Coding Agent",
        description="Planeja ações relacionadas a código e projetos locais.",
        domains=("coding", "development", "project"),
        priority=200,
    )

    def __init__(
        self,
        project_path: Path | str | None = None,
    ) -> None:
        self.project_path = Path(
            project_path or PROJECT_DIR
        ).expanduser().resolve()
        self.session = SessionManager()

        self.known_files: dict[str, Path] = {
            "main": self.project_path / "main.py",
            "main py": self.project_path / "main.py",

            "planner": (
                self.project_path
                / "atlas"
                / "planner"
                / "planner.py"
            ),

            "executor": (
                self.project_path
                / "atlas"
                / "planner"
                / "executor.py"
            ),

            "engine": (
                self.project_path
                / "atlas"
                / "automation"
                / "engine.py"
            ),

            "desktop": (
                self.project_path
                / "atlas"
                / "agents"
                / "desktop.py"
            ),

            "coding": (
                self.project_path
                / "atlas"
                / "agents"
                / "coding.py"
            ),

            "speech": (
                self.project_path
                / "atlas"
                / "voice"
                / "speech.py"
            ),

            "kernel": (
                self.project_path
                / "atlas"
                / "core"
                / "kernel.py"
            ),

            "app": (
                self.project_path
                / "atlas"
                / "core"
                / "app.py"
            ),

            "session manager": (
                self.project_path
                / "atlas"
                / "session"
                / "manager.py"
            ),
        }

    def plan(self, command: str) -> list[Action]:
        normalized = self._normalize(command)

        continue_plan = self._continue_session_plan(
            normalized
        )

        if continue_plan:
            return continue_plan

        run_plan = self._run_project_plan(
            normalized
        )

        if run_plan:
            return run_plan

        open_file_plan = self._open_file_plan(
            normalized
        )

        if open_file_plan:
            return open_file_plan

        open_project_plan = self._open_project_plan(
            normalized
        )

        if open_project_plan:
            return open_project_plan

        return []

    def _continue_session_plan(
        self,
        command: str,
    ) -> list[Action]:
        continue_phrases = (
            "vamos continuar",
            "continue de onde paramos",
            "continuar de onde paramos",
            "continue nosso projeto",
            "continuar nosso projeto",
            "retome o projeto",
            "retomar o projeto",
            "volte de onde paramos",
        )

        if not any(
            phrase in command
            for phrase in continue_phrases
        ):
            return []

        session_data = self.session.load()

        last_file = str(
            session_data.get(
                "last_file",
                "",
            )
        ).strip()

        command_arguments = [
            "code",
            str(self.project_path),
        ]

        if last_file:
            file_path = self._find_file(last_file)

            if file_path is not None:
                command_arguments.append(
                    str(file_path)
                )

        return [
            Action(
                type="process.start",
                parameters={
                    "command": command_arguments,
                },
            )
        ]

    def _run_project_plan(
        self,
        command: str,
    ) -> list[Action]:
        run_phrases = (
            "execute o projeto",
            "executar o projeto",
            "rode o projeto",
            "rodar o projeto",
            "inicie o atlas",
            "iniciar o atlas",
            "execute o atlas",
            "rodar atlas",
            "rode atlas",
        )

        if not any(
            phrase in command
            for phrase in run_phrases
        ):
            return []

        project_path = str(self.project_path).replace(
            "'",
            "''",
        )
        venv_python = (
            self.project_path
            / ".venv"
            / "Scripts"
            / "python.exe"
        )
        python_command = (
            str(venv_python)
            if venv_python.is_file()
            else "python"
        ).replace("'", "''")

        powershell_command = [
            "powershell.exe",
            "-NoExit",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            (
                f"Set-Location -LiteralPath '{project_path}'; "
                f"& '{python_command}' 'main.py'"
            ),
        ]

        return [
            Action(
                type="process.start",
                parameters={
                    "command": powershell_command,
                },
            )
        ]

    def _open_file_plan(
        self,
        command: str,
    ) -> list[Action]:
        open_words = (
            "abra",
            "abre",
            "abrir",
            "edite",
            "editar",
            "mostre",
        )

        if not any(
            word in command
            for word in open_words
        ):
            return []

        for file_name, file_path in self.known_files.items():
            mentions_file = (
                file_name in command
                or f"{file_name} py" in command
            )

            if not mentions_file:
                continue

            return [
                Action(
                    type="process.start",
                    parameters={
                        "command": [
                            "code",
                            str(self.project_path),
                            str(file_path),
                        ],
                    },
                )
            ]

        explicit_file = re.search(
            r"\b([\w-]+)\s*(?:ponto|\.)\s*py\b",
            command,
        )

        if not explicit_file:
            return []

        requested_name = (
            explicit_file.group(1)
            + ".py"
        )

        found_file = self._find_file(
            requested_name
        )

        if found_file is None:
            return []

        return [
            Action(
                type="process.start",
                parameters={
                    "command": [
                        "code",
                        str(self.project_path),
                        str(found_file),
                    ],
                },
            )
        ]

    def _open_project_plan(
        self,
        command: str,
    ) -> list[Action]:
        coding_phrases = (
            "vamos programar",
            "quero programar",
            "abra o projeto atlas",
            "abra nosso projeto",
            "continue o desenvolvimento",
            "continuar o desenvolvimento",
        )

        if not any(
            phrase in command
            for phrase in coding_phrases
        ):
            return []

        return [
            Action(
                type="process.start",
                parameters={
                    "command": [
                        "code",
                        str(self.project_path),
                    ],
                },
            )
        ]

    def _find_file(
        self,
        filename: str,
    ) -> Path | None:
        try:
            for path in self.project_path.rglob(filename):
                if ".venv" not in path.parts:
                    return path

        except OSError:
            return None

        return None

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.lower().strip()

        text = unicodedata.normalize(
            "NFKD",
            text,
        )

        text = "".join(
            character
            for character in text
            if not unicodedata.combining(character)
        )

        text = re.sub(
            r"[^\w\s.]",
            " ",
            text,
        )

        return re.sub(
            r"\s+",
            " ",
            text,
        ).strip()
