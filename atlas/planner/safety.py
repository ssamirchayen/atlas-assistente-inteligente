from __future__ import annotations

import re
import unicodedata

from atlas.planner.actions import Action
from atlas.planner.tools import ToolRegistry


class SafetyGuard:
    """
    Verifica se as ações criadas pelo Planner Inteligente
    são seguras antes de enviá-las ao Executor.
    """

    DESTRUCTIVE_WORDS = {
        "apague",
        "apagar",
        "apaga",
        "delete",
        "deletar",
        "deleta",
        "exclua",
        "excluir",
        "exclui",
        "remova",
        "remover",
        "remove",
    }

    BLOCKED_COMMAND_PARTS = {
        "format c:",
        "format c:\\",
        "del /f /s /q c:",
        "rd /s /q c:",
        "rmdir /s /q c:",
        "remove-item c:\\ -recurse",
        "shutdown /s",
        "shutdown -s",
    }

    PROTECTED_PATHS = {
        "c:",
        "c:\\",
        "c:/",
        "c:\\windows",
        "c:/windows",
        "c:\\program files",
        "c:/program files",
        "c:\\program files (x86)",
        "c:/program files (x86)",
        "c:\\users",
        "c:/users",
    }

    def __init__(
        self,
        tools: ToolRegistry | None = None,
    ) -> None:
        self.tools = tools or ToolRegistry()

    def filter_actions(
        self,
        user_text: str,
        actions: list[Action],
    ) -> list[Action]:
        """
        Retorna somente as ações consideradas seguras.

        Ações perigosas são recusadas quando o usuário não
        demonstrou claramente a intenção de executá-las.
        """

        safe_actions: list[Action] = []

        for action in actions:
            allowed, reason = self.check_action(
                user_text,
                action,
            )

            if allowed:
                safe_actions.append(action)
                continue

            print(
                "[SEGURANÇA] "
                f"Ação bloqueada: {action.type}. "
                f"Motivo: {reason}"
            )

        return safe_actions

    def check_action(
        self,
        user_text: str,
        action: Action,
    ) -> tuple[bool, str]:
        """
        Verifica uma ação individual.
        """

        tool = self.tools.get(action.type)

        if tool is None:
            return False, "ferramenta não registrada"

        if action.type == "process.start":
            return self._check_process_start(action)

        if action.type == "file.delete":
            return self._check_file_delete(
                user_text,
                action,
            )

        if tool.dangerous:
            normalized_text = self._normalize(user_text)

            if not self._has_destructive_intent(
                normalized_text
            ):
                return (
                    False,
                    "o usuário não pediu uma ação destrutiva",
                )

        return True, "ação permitida"

    def _check_file_delete(
        self,
        user_text: str,
        action: Action,
    ) -> tuple[bool, str]:
        """
        Protege arquivos e diretórios importantes.
        """

        normalized_text = self._normalize(user_text)

        if not self._has_destructive_intent(
            normalized_text
        ):
            return (
                False,
                "o pedido não contém intenção explícita de exclusão",
            )

        path = action.parameters.get("path")

        if not isinstance(path, str):
            return False, "caminho de exclusão inválido"

        normalized_path = (
            path.strip()
            .lower()
            .replace("/", "\\")
            .rstrip("\\")
        )

        protected_paths = {
            item.replace("/", "\\").rstrip("\\")
            for item in self.PROTECTED_PATHS
        }

        if normalized_path in protected_paths:
            return (
                False,
                "o caminho informado é protegido pelo sistema",
            )

        if not normalized_path:
            return False, "caminho vazio"

        return True, "exclusão solicitada explicitamente"

    def _check_process_start(
        self,
        action: Action,
    ) -> tuple[bool, str]:
        """
        Bloqueia comandos de terminal claramente perigosos.
        """

        command = action.parameters.get("command")

        if isinstance(command, str):
            command_text = command

        elif isinstance(command, list):
            command_text = " ".join(
                str(item)
                for item in command
            )

        else:
            return False, "comando de processo inválido"

        normalized_command = self._normalize(
            command_text
        )

        for blocked_part in self.BLOCKED_COMMAND_PARTS:
            normalized_blocked = self._normalize(
                blocked_part
            )

            if normalized_blocked in normalized_command:
                return (
                    False,
                    "comando potencialmente destrutivo",
                )

        return True, "processo permitido"

    def _has_destructive_intent(
        self,
        normalized_text: str,
    ) -> bool:
        """
        Verifica se o usuário realmente pediu uma exclusão.
        """

        words = set(
            re.findall(
                r"\b[\w]+\b",
                normalized_text,
            )
        )

        return bool(
            words.intersection(
                self.DESTRUCTIVE_WORDS
            )
        )

    @staticmethod
    def _normalize(text: str) -> str:
        """
        Remove acentos e normaliza espaços.
        """

        normalized = unicodedata.normalize(
            "NFKD",
            text.lower().strip(),
        )

        normalized = "".join(
            character
            for character in normalized
            if not unicodedata.combining(character)
        )

        normalized = re.sub(
            r"\s+",
            " ",
            normalized,
        )

        return normalized.strip()