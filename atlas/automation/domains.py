"""Respostas consultivas dos agentes de domínio, sem efeitos externos."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class DomainAutomation:
    """Usa o modelo local apenas para texto; não oferece ferramentas a ele."""

    _PROGRAMMING_MODES = {"create", "debug", "review", "security"}
    _WHOLESALE_MODES = {
        "demand",
        "inventory",
        "logistics",
        "operations",
        "pricing",
    }
    _INDUSTRY_MODES = {
        "maintenance",
        "operations",
        "production",
        "quality",
        "safety",
    }
    _RADIOLOGY_MODES = {"clinical_support", "quality_check", "worklist"}

    def __init__(
        self,
        responder: Callable[[str], str] | None = None,
    ) -> None:
        self._responder = responder

    def programming_assist(self, parameters: dict[str, Any]) -> str:
        mode = self._mode(parameters, self._PROGRAMMING_MODES)
        language = self._text(
            parameters.get("language", "não informada"),
            field="language",
            maximum=64,
        )
        request = self._request(parameters)
        prompt = (
            "Você é o agente consultivo de programação do Atlas. "
            f"Modo: {mode}. Linguagem: {language}. "
            "Ajude a criar, revisar ou depurar o código solicitado. "
            "Não execute código, não invente resultados de testes, não peça "
            "segredos e destaque validação, testes e riscos de segurança. "
            "Quando faltarem requisitos, faça perguntas objetivas.\n\n"
            f"Solicitação: {request}"
        )
        fallback = (
            f"Assistência de programação preparada ({mode}, {language}).\n"
            "O código não será executado automaticamente. Para continuar, "
            "informe requisitos, entrada esperada, saída esperada e, em caso "
            "de bug, inclua o código e a mensagem de erro."
        )
        return self._respond(prompt, fallback)

    def radiology_support(self, parameters: dict[str, Any]) -> str:
        mode = self._mode(parameters, self._RADIOLOGY_MODES)

        if parameters.get("human_review_required") is not True:
            raise ValueError("A revisão profissional deve ser obrigatória.")

        messages = {
            "clinical_support": (
                "Apoio radiológico iniciado. Esta versão do Atlas não recebe "
                "pixels do exame, não identifica patologias e não emite "
                "diagnóstico ou laudo. Registre modalidade, região anatômica, "
                "projeções, indicação clínica e qualidade técnica para revisão "
                "obrigatória por profissional habilitado."
            ),
            "quality_check": (
                "Checklist de qualidade radiográfica: confirme identificação "
                "do exame, região e lateralidade, projeções, posicionamento, "
                "colimação, exposição, artefatos e completude. A decisão sobre "
                "repetição pertence ao profissional responsável."
            ),
            "worklist": (
                "A fila radiológica pode ser organizada por horário, status, "
                "modalidade e prioridade definida pelo serviço. O Atlas não "
                "atribui urgência clínica sozinho; casos críticos exigem "
                "protocolo e validação humana."
            ),
        }
        return messages[mode]

    def wholesale_analysis(self, parameters: dict[str, Any]) -> str:
        mode = self._mode(parameters, self._WHOLESALE_MODES)
        request = self._request(parameters)
        prompt = (
            "Você é o agente consultivo de comércio atacadista do Atlas. "
            f"Modo: {mode}. Analise o pedido com métricas, premissas e dados "
            "que ainda precisam ser informados. Não altere preços, estoque, "
            "pedidos ou cadastros; produza apenas recomendação para aprovação "
            f"humana.\n\nSolicitação: {request}"
        )
        fallback = (
            f"Análise atacadista preparada ({mode}). Para calcular uma "
            "recomendação confiável, forneça período, vendas, estoque atual, "
            "custo, preço, prazo de reposição e nível de serviço desejado. "
            "Nenhum preço, pedido ou saldo foi alterado."
        )
        return self._respond(prompt, fallback)

    def industry_analysis(self, parameters: dict[str, Any]) -> str:
        mode = self._mode(parameters, self._INDUSTRY_MODES)

        if parameters.get("machine_control") is not False:
            raise ValueError("Controle de máquina não é permitido.")

        request = self._request(parameters)
        safety = (
            "Não controle máquinas, não altere PLC, não desative intertravamentos "
            "e não substitua procedimentos de segurança. "
        )
        prompt = (
            "Você é o agente consultivo industrial do Atlas. "
            f"Modo: {mode}. {safety}Estruture hipóteses, dados necessários, "
            "indicadores e uma sequência segura para avaliação por engenharia, "
            f"manutenção e segurança do trabalho.\n\nSolicitação: {request}"
        )
        fallback = (
            f"Análise industrial preparada ({mode}). {safety}Informe ativo, "
            "processo, sintomas, alarmes, histórico, impacto e medições. A "
            "equipe responsável deve validar qualquer intervenção."
        )
        return self._respond(prompt, fallback)

    def _respond(self, prompt: str, fallback: str) -> str:
        if self._responder is None:
            return fallback

        answer = self._responder(prompt)

        if not isinstance(answer, str) or not answer.strip():
            return fallback

        return answer.strip()[:12_000]

    @staticmethod
    def _mode(parameters: dict[str, Any], allowed: set[str]) -> str:
        mode = str(parameters.get("mode", "")).strip().casefold()

        if mode not in allowed:
            raise ValueError(f"Modo de domínio não suportado: {mode or 'vazio'}")

        return mode

    def _request(self, parameters: dict[str, Any]) -> str:
        return self._text(
            parameters.get("request", ""),
            field="request",
            maximum=12_000,
        )

    @staticmethod
    def _text(value: object, *, field: str, maximum: int) -> str:
        text = str(value).strip()

        if not text:
            raise ValueError(f"{field} é obrigatório.")
        if len(text) > maximum:
            raise ValueError(f"{field} excede o limite permitido.")

        return text
