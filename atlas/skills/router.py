from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from atlas.memory.database import MemoryStore
from atlas.memory.lifecycle import MemoryLifecycleManager
from atlas.skills.windows import WindowsSkill
from atlas.utils.text import clean_politeness


@dataclass
class SkillResult:
    handled: bool
    message: str = ""
    needs_followup: bool = False
    followup_type: str = ""


class SkillRouter:
    def __init__(
        self,
        memory: MemoryStore,
        memory_lifecycle: MemoryLifecycleManager | None = None,
    ) -> None:
        self.memory = memory
        self.memory_lifecycle = (
            memory_lifecycle or MemoryLifecycleManager(memory)
        )
        self.pending_system_action: tuple[str, int] | None = None
        self.pending_open = False

    def route_priority(self, raw_text: str) -> SkillResult:
        """Trata comandos de memória antes que cheguem ao Planner."""

        text = clean_politeness(raw_text)
        remember_match = re.match(
            r"^(lembre|lembra|memorize)(?: se)?(?: de)? que\s+(.+)$",
            text,
        )

        if remember_match:
            return SkillResult(
                True,
                self.memory.remember(remember_match.group(2)),
            )

        memory_command = self.memory_lifecycle.handle_command(raw_text)

        if memory_command.handled:
            return SkillResult(True, memory_command.message)

        memory_admin = re.match(
            r"^(?:apaga|apague|apagar|deleta|delete|deletar|"
            r"exclui|exclua|excluir|remove|remova|remover|"
            r"esquece|esqueca|esquecer|restaura|restaure|restaurar|"
            r"recupera|recupere|recuperar|corrige|corrija|corrigir|"
            r"altera|altere|alterar|atualiza|atualize|atualizar|"
            r"lista|liste|listar|mostra|mostre|mostrar|"
            r"consolida|consolide|consolidar|otimiza|otimize|otimizar)\b",
            text,
        )

        if memory_admin and re.search(r"\bmemorias?\b", text):
            return SkillResult(
                True,
                "Não consegui identificar qual memória deve ser alterada. "
                "Diga 'liste minhas memórias' e use o número exibido.",
            )

        return SkillResult(False)

    def route(self, raw_text: str) -> SkillResult:
        text = clean_politeness(raw_text)

        if self.pending_open:
            self.pending_open = False
            if not text:
                return SkillResult(True, "Não ouvi o que você quer abrir.")
            return SkillResult(True, WindowsSkill.open_target(text))

        confirmation = self._confirmation(text)
        if confirmation.handled:
            return confirmation

        if text in {"ajuda", "comandos", "o que voce pode fazer"}:
            return SkillResult(
                True,
                "Posso conversar, abrir programas, sites e pastas, pesquisar, "
                "guardar memórias, informar data e hora e controlar desligamento "
                "com confirmação.",
            )

        if text == "status":
            return SkillResult(
                True,
                "O sistema de voz, memória, ferramentas e Ollama está carregado.",
            )

        priority_result = self.route_priority(raw_text)

        if priority_result.handled:
            return priority_result

        if "que horas" in text or text == "horas":
            return SkillResult(
                True,
                f"Agora são {datetime.now().strftime('%H:%M')}.",
            )

        if "que dia" in text or "data de hoje" in text:
            return SkillResult(
                True,
                f"Hoje é {datetime.now().strftime('%d/%m/%Y')}.",
            )

        open_match = re.match(
            r"^(abra|abrir|abre|inicie|iniciar|acesse|entre no|entre na)(?: o| a| os| as)?\s*(.*)$",
            text,
        )
        if open_match:
            target = open_match.group(2).strip()
            if not target:
                self.pending_open = True
                return SkillResult(
                    True,
                    "O que você quer que eu abra?",
                    needs_followup=True,
                    followup_type="open",
                )
            return SkillResult(True, WindowsSkill.open_target(target))

        search_match = re.match(
            r"^(pesquise|pesquisar|procure|buscar|busque)(?: por)?\s+(.+)$",
            text,
        )
        if search_match:
            return SkillResult(
                True,
                WindowsSkill.search_web(search_match.group(2)),
            )

        if "cancelar desligamento" in text or "abortar desligamento" in text:
            return SkillResult(True, WindowsSkill.cancel_shutdown())

        if "deslig" in text and ("computador" in text or "pc" in text):
            seconds = self._delay(text)
            self.pending_system_action = ("shutdown", seconds)
            return SkillResult(
                True,
                "Confirma o desligamento do computador?",
                needs_followup=True,
                followup_type="confirmation",
            )

        if "reinici" in text and ("computador" in text or "pc" in text):
            seconds = self._delay(text)
            self.pending_system_action = ("restart", seconds)
            return SkillResult(
                True,
                "Confirma a reinicialização do computador?",
                needs_followup=True,
                followup_type="confirmation",
            )

        return SkillResult(False)

    def _confirmation(self, text: str) -> SkillResult:
        if self.pending_system_action is None:
            return SkillResult(False)

        if text in {"nao", "cancelar", "cancela", "negativo"}:
            self.pending_system_action = None
            return SkillResult(True, "Ação cancelada.")

        if text not in {"sim", "confirmar", "confirmo", "pode", "positivo"}:
            return SkillResult(
                True,
                "Responda sim para confirmar ou não para cancelar.",
                needs_followup=True,
                followup_type="confirmation",
            )

        action, seconds = self.pending_system_action
        self.pending_system_action = None

        if action == "shutdown":
            return SkillResult(True, WindowsSkill.shutdown(seconds))
        return SkillResult(True, WindowsSkill.restart(seconds))

    @staticmethod
    def _delay(text: str) -> int:
        match = re.search(
            r"(\d+)\s*(segundo|segundos|minuto|minutos|hora|horas)",
            text,
        )
        if not match:
            return 0

        value = int(match.group(1))
        unit = match.group(2)

        if unit.startswith("minuto"):
            return value * 60
        if unit.startswith("hora"):
            return value * 3600
        return value
