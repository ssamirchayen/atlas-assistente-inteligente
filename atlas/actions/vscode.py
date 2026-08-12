from __future__ import annotations

import os
import shutil
import subprocess


class VSCodeAction:
    """Ações relacionadas ao Visual Studio Code."""

    COMMANDS = {
        "abrir vs code",
        "abrir vscode",
        "iniciar vs code",
        "iniciar vscode",
        "abrir visual studio code",
    }

    @classmethod
    def can_handle(cls, command: str) -> bool:
        normalized_command = command.strip().lower()
        return normalized_command in cls.COMMANDS

    @staticmethod
    def execute() -> str:
        vscode_command = shutil.which("code")

        try:
            if vscode_command:
                subprocess.Popen(
                    [vscode_command],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return "Abrindo o Visual Studio Code."

            possible_paths = [
                os.path.expandvars(
                    r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"
                ),
                os.path.expandvars(
                    r"%PROGRAMFILES%\Microsoft VS Code\Code.exe"
                ),
                os.path.expandvars(
                    r"%PROGRAMFILES(X86)%\Microsoft VS Code\Code.exe"
                ),
            ]

            for path in possible_paths:
                if os.path.isfile(path):
                    subprocess.Popen(
                        [path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return "Abrindo o Visual Studio Code."

            return (
                "Não encontrei o Visual Studio Code instalado "
                "ou configurado no PATH."
            )

        except OSError as error:
            return f"Não consegui abrir o Visual Studio Code: {error}"