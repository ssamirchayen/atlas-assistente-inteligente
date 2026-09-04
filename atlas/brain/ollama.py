from __future__ import annotations

import requests

from atlas.brain.model_router import ModelRouteDecision, ModelRouter
from atlas.context.manager import ContextManager
from atlas.core.config import (
    OLLAMA_MODEL,
    OLLAMA_URL,
    SYSTEM_PROMPT,
)


class OllamaBrain:
    def __init__(
        self,
        context: ContextManager,
        *,
        model_router: ModelRouter | None = None,
    ) -> None:
        self.history: list[dict[str, str]] = []
        self.context = context
        self.model_router = model_router
        self.last_model_decision: ModelRouteDecision | None = None

    def respond(
        self,
        user_text: str,
        memory_context: str = "",
    ) -> str:
        user_text = user_text.strip()

        if not user_text:
            return "Não recebi nenhuma mensagem."

        self.context.session.save_last_command(user_text)

        prompt = SYSTEM_PROMPT

        context_text = self.context.build_prompt_context()

        prompt += (
            "\n\n"
            "=== CONTEXTO ATUAL DA SESSÃO ===\n"
            f"{context_text}\n"
            "=== FIM DO CONTEXTO DA SESSÃO ===\n"
            "\n"
            "Use esse contexto somente quando ele for relevante "
            "para compreender a solicitação atual do usuário. "
            "Não invente informações que não estejam no contexto."
        )

        if memory_context:
            prompt += (
                "\n\n"
                "=== MEMÓRIAS POSSIVELMENTE RELEVANTES ===\n"
                f"{memory_context}\n"
                "=== FIM DAS MEMÓRIAS ===\n"
                "\n"
                "Utilize essas memórias somente se forem "
                "pertinentes à solicitação atual."
            )

        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": prompt,
            }
        ]

        messages.extend(self.history[-12:])

        messages.append(
            {
                "role": "user",
                "content": user_text,
            }
        )

        model_name = OLLAMA_MODEL
        context_limit: int | None = None
        if self.model_router is not None:
            self.last_model_decision = self.model_router.route(
                self.model_router.classify(user_text)
            )
            model_name = self.last_model_decision.model_name
            context_limit = self.last_model_decision.context_limit

        payload: dict[str, object] = {
            "model": model_name,
            "messages": messages,
            "stream": False,
        }
        if context_limit is not None:
            payload["options"] = {"num_ctx": context_limit}

        try:
            response = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=180,
            )

            response.raise_for_status()

            response_data = response.json()
            answer = response_data["message"]["content"].strip()

        except requests.ConnectionError:
            return (
                "Não consegui conectar ao Ollama. "
                "Verifique se ele está aberto."
            )

        except requests.Timeout:
            return (
                "O Ollama demorou mais do que o esperado "
                "para responder."
            )

        except requests.HTTPError as error:
            error_details = ""
            status_code = "desconhecido"

            if error.response is not None:
                status_code = error.response.status_code

                try:
                    error_data = error.response.json()

                    error_details = error_data.get(
                        "error",
                        error.response.text,
                    )

                except ValueError:
                    error_details = error.response.text

            print(
                "[OLLAMA ERRO] "
                f"Status: {status_code}"
            )

            print(
                "[OLLAMA ERRO] "
                f"Detalhes: {error_details}"
            )

            return (
                "O Ollama encontrou um erro interno: "
                f"{error_details or error}"
            )

        except requests.RequestException as error:
            return (
                "Ocorreu um erro durante a comunicação "
                f"com o Ollama: {error}"
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            return (
                "O Ollama enviou uma resposta "
                "em formato inesperado."
            )

        self.history.append(
            {
                "role": "user",
                "content": user_text,
            }
        )

        self.history.append(
            {
                "role": "assistant",
                "content": answer,
            }
        )

        return answer

    def clear_history(self) -> None:
        self.history.clear()
