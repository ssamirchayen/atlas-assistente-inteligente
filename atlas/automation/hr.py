from __future__ import annotations

from typing import Any


class HRAutomation:
    """Produz documentos de RH sem tomar decisões sobre candidatos."""

    def generate_document(self, parameters: dict[str, Any]) -> str:
        document_type = str(
            parameters.get("document_type", "")
        ).strip().casefold()
        role = str(parameters.get("role", "cargo a definir")).strip()

        if not role:
            role = "cargo a definir"

        generators = {
            "job_description": self._job_description,
            "candidate_message": self._candidate_message,
            "interview_guide": self._interview_guide,
            "screening_criteria": self._screening_criteria,
        }
        generator = generators.get(document_type)

        if generator is None:
            raise ValueError(
                "Documento de RH não suportado: "
                f"{document_type or 'vazio'}"
            )

        return generator(role, parameters)

    @staticmethod
    def _job_description(role: str, _: dict[str, Any]) -> str:
        return (
            f"DESCRIÇÃO DA VAGA — {role}\n\n"
            "Objetivo do cargo:\n"
            f"Buscamos uma pessoa para atuar como {role}, contribuindo "
            "com qualidade, colaboração e foco em resultados.\n\n"
            "Responsabilidades:\n"
            "- Executar as atividades definidas para a função.\n"
            "- Colaborar com a equipe e comunicar impedimentos.\n"
            "- Registrar processos e acompanhar os resultados do trabalho.\n"
            "- Cumprir políticas internas, prazos e padrões de qualidade.\n\n"
            "Requisitos profissionais:\n"
            "- Conhecimentos técnicos compatíveis com a função.\n"
            "- Comunicação clara, organização e capacidade de aprender.\n"
            "- Experiência ou formação deve ser definida pela empresa.\n\n"
            "Antes de publicar, complete: senioridade, local, jornada, "
            "contratação, faixa salarial e benefícios."
        )

    @staticmethod
    def _candidate_message(role: str, parameters: dict[str, Any]) -> str:
        status = str(parameters.get("status", "process_update")).casefold()
        messages = {
            "interview_invitation": (
                "Olá! Tudo bem?\n\n"
                f"Gostaríamos de convidar você para uma entrevista da vaga "
                f"de {role}. Seu perfil avançou nesta etapa do processo.\n\n"
                "Por favor, informe sua disponibilidade para combinarmos "
                "data, horário e formato da conversa.\n\n"
                "Agradecemos seu interesse e ficamos à disposição."
            ),
            "approved": (
                "Olá! Tudo bem?\n\n"
                f"Temos a satisfação de informar que você foi aprovado no "
                f"processo para a vaga de {role}.\n\n"
                "Entraremos em contato com as orientações da próxima etapa, "
                "documentos e previsão de início. Parabéns!"
            ),
            "not_selected": (
                "Olá! Tudo bem?\n\n"
                f"Agradecemos sua participação no processo para a vaga de "
                f"{role}. Neste momento, seguiremos com outro perfil mais "
                "aderente aos requisitos definidos para a posição.\n\n"
                "Agradecemos seu tempo e desejamos sucesso em sua trajetória."
            ),
            "process_update": (
                "Olá! Tudo bem?\n\n"
                f"Estamos entrando em contato para atualizar você sobre o "
                f"processo da vaga de {role}. A avaliação ainda está em "
                "andamento e retornaremos assim que houver uma nova etapa.\n\n"
                "Agradecemos sua participação e disponibilidade."
            ),
        }

        message = messages.get(status)

        if message is None:
            raise ValueError(f"Status de candidato não suportado: {status}")

        return message

    @staticmethod
    def _interview_guide(role: str, _: dict[str, Any]) -> str:
        return (
            f"ROTEIRO DE ENTREVISTA — {role}\n\n"
            "1. Conte brevemente sobre sua trajetória profissional.\n"
            f"2. Qual experiência sua é mais relevante para atuar como {role}?\n"
            "3. Descreva um problema difícil que você resolveu.\n"
            "4. Como você organiza prioridades quando há várias demandas?\n"
            "5. Como comunica um erro, risco ou atraso para a equipe?\n"
            "6. Dê um exemplo de colaboração com pessoas de outras áreas.\n"
            "7. Como você aprende uma ferramenta ou processo novo?\n"
            "8. O que espera da função e do ambiente de trabalho?\n\n"
            "Avalie todas as pessoas com as mesmas perguntas e registre "
            "evidências objetivas nas respostas."
        )

    @staticmethod
    def _screening_criteria(role: str, _: dict[str, Any]) -> str:
        return (
            f"CRITÉRIOS DE TRIAGEM — {role}\n\n"
            "Use a mesma escala para todas as candidaturas:\n"
            "1. Requisitos técnicos essenciais: 0 a 4 pontos.\n"
            "2. Experiência relevante comprovada: 0 a 2 pontos.\n"
            "3. Comunicação e clareza das evidências: 0 a 2 pontos.\n"
            "4. Organização e resolução de problemas: 0 a 2 pontos.\n\n"
            "Registre a justificativa de cada nota e encaminhe a decisão "
            "final para revisão humana. Não utilize idade, gênero, raça, "
            "religião, deficiência, estado civil, endereço, fotografia ou "
            "qualquer característica pessoal sem relação com a função."
        )
