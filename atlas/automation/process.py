from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path


class ProcessAutomation:
    def start(
        self,
        command: str | Sequence[str],
    ) -> str:
        if isinstance(command, str):
            command = command.strip()

            if not command:
                return "Erro: comando vazio."

            if command.lower() in {
                "code",
                "code.exe",
                "code.cmd",
            }:
                vscode = self._find_vscode()

                if vscode is None:
                    return (
                        "Erro: não encontrei o VS Code "
                        "instalado neste computador."
                    )

                return self._open_arguments([vscode])

            try:
                subprocess.Popen(
                    command,
                    shell=True,
                )

                return f"Programa iniciado: {command}"

            except OSError as exc:
                return f"Erro ao iniciar programa: {exc}"

        if isinstance(command, (list, tuple)):
            arguments = [
                str(item).strip()
                for item in command
                if str(item).strip()
            ]

            if not arguments:
                return "Erro: comando vazio."

            if arguments[0].lower() in {
                "code",
                "code.exe",
                "code.cmd",
            }:
                vscode = self._find_vscode()

                if vscode is None:
                    return (
                        "Erro: não encontrei o VS Code "
                        "instalado neste computador."
                    )

                arguments[0] = vscode

            return self._open_arguments(arguments)

        return "Erro: tipo de comando inválido."

    def _open_arguments(
        self,
        arguments: list[str],
    ) -> str:
        try:
            subprocess.Popen(
                arguments,
                shell=False,
            )

            return (
                "Programa iniciado: "
                + " ".join(arguments)
            )

        except FileNotFoundError:
            return (
                "Erro: programa não encontrado: "
                f"{arguments[0]}"
            )

        except OSError as exc:
            return f"Erro ao iniciar programa: {exc}"

    @staticmethod
    def _find_vscode() -> str | None:
        command_path = shutil.which("code.cmd")

        if command_path:
            return command_path

        command_path = shutil.which("code.exe")

        if command_path:
            return command_path

        command_path = shutil.which("code")

        if command_path:
            return command_path

        possible_paths = [
            Path(
                os.environ.get(
                    "LOCALAPPDATA",
                    "",
                )
            )
            / "Programs"
            / "Microsoft VS Code"
            / "Code.exe",

            Path(
                os.environ.get(
                    "PROGRAMFILES",
                    "",
                )
            )
            / "Microsoft VS Code"
            / "Code.exe",

            Path(
                os.environ.get(
                    "PROGRAMFILES(X86)",
                    "",
                )
            )
            / "Microsoft VS Code"
            / "Code.exe",
        ]

        for path in possible_paths:
            if path.is_file():
                return str(path)

        return None