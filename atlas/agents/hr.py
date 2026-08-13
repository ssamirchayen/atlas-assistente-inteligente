from __future__ import annotations

import re
import unicodedata

from atlas.agents.base import AgentMetadata
from atlas.planner.actions import Action


class HRAgent:
    """Planeja documentos de recrutamento baseados em critérios profissionais."""

    metadata = AgentMetadata(
        name="hr",
        display_name="RH Agent",
        description=(
            "Cria documentos estruturados para recrutamento e seleção."
        ),
        domains=("hr", "recruiting", "people", "talent-acquisition"),
        priority=280,
    )

    _SEARCH_PREFIXES = ("busque ", "pesquise ", "procure ")
    _JOB_TERMS = (
        "anuncio de vaga",
        "descricao da vaga",
        "descricao de cargo",
        "descricao de vaga",
        "divulgacao de vaga",
        "divulgar uma vaga",
    )
    _MESSAGE_TERMS = (
        "convite para entrevista",
        "feedback para candidato",
        "mensagem ao candidato",
        "mensagem de candidato",
        "mensagem para candidato",
        "retorno ao candidato",
        "retorno para candidato",
    )
    _INTERVIEW_TERMS = (
        "perguntas de entrevista",
        "perguntas para entrevista",
        "roteiro da entrevista",
        "roteiro de entrevista",
    )
    _SCREENING_TERMS = (
        "criterios de selecao",
        "criterios de triagem",
        "matriz de triagem",
        "triagem de candidatos",
        "triagem de curriculos",
    )

    def plan(self, command: str) -> list[Action]:
        original = command.strip()

        if not original:
            return []

        normalized = self._normalize(original)

        if normalized.startswith(self._SEARCH_PREFIXES):
            return []

        document_type = self._identify_document_type(normalized)

        if document_type is None:
            return []

        parameters = {
            "document_type": document_type,
            "role": self._extract_role(original, document_type),
        }

        if document_type == "candidate_message":
            parameters["status"] = self._identify_candidate_status(normalized)

        return [Action(type="hr.generate_document", parameters=parameters)]

    def _identify_document_type(self, command: str) -> str | None:
        if any(term in command for term in self._JOB_TERMS):
            return "job_description"

        if any(term in command for term in self._MESSAGE_TERMS):
            return "candidate_message"

        if any(term in command for term in self._INTERVIEW_TERMS):
            return "interview_guide"

        if any(term in command for term in self._SCREENING_TERMS):
            return "screening_criteria"

        return None

    @staticmethod
    def _identify_candidate_status(command: str) -> str:
        if any(
            term in command
            for term in ("nao aprovado", "nao selecionado", "reprovado")
        ):
            return "not_selected"

        if any(
            term in command
            for term in ("aprovado", "selecionado", "passou no processo")
        ):
            return "approved"

        if any(
            term in command
            for term in ("agendar entrevista", "convite", "para entrevista")
        ):
            return "interview_invitation"

        return "process_update"

    @classmethod
    def _extract_role(cls, command: str, document_type: str) -> str:
        clean_command = command.strip().rstrip(" .?!")
        patterns_by_type = {
            "job_description": (
                r"vaga\s+(?:para|de|do|da)\s+(.+)$",
                r"cargo\s+(?:de|do|da)?\s*(.+)$",
            ),
            "candidate_message": (
                r"vaga\s+(?:para|de|do|da)\s+(.+)$",
                r"cargo\s+(?:de|do|da)?\s*(.+)$",
            ),
            "interview_guide": (
                r"entrevista\s+(?:para|de|do|da)\s+"
                r"(?:a\s+)?(?:vaga\s+(?:para|de)\s+)?(.+)$",
            ),
            "screening_criteria": (
                r"triagem\s+(?:para|de|do|da)\s+"
                r"(?:a\s+)?(?:vaga\s+(?:para|de)\s+)?(.+)$",
                r"selecao\s+(?:para|de|do|da)\s+"
                r"(?:a\s+)?(?:vaga\s+(?:para|de)\s+)?(.+)$",
            ),
        }

        for pattern in patterns_by_type.get(document_type, ()):
            match = re.search(pattern, clean_command, flags=re.IGNORECASE)

            if match:
                role = match.group(1).strip().rstrip(" .?!")

                if role:
                    return role

        return "cargo a definir"

    @staticmethod
    def _normalize(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text.casefold().strip())
        normalized = "".join(
            character
            for character in normalized
            if not unicodedata.combining(character)
        )
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()
