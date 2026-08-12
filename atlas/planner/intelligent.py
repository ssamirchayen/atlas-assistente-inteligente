from __future__ import annotations

import json
import re
from typing import Any

from atlas.brain.ollama import OllamaBrain
from atlas.context.manager import ContextManager
from atlas.planner.actions import Action
from atlas.planner.safety import SafetyGuard
from atlas.planner.task_planner import TaskPlanner
from atlas.planner.tools import ToolRegistry


class IntelligentPlanner:
    """
    Usa o modelo local do Ollama para transformar comandos
    do usuário em uma lista estruturada e segura de ações.
    """

    MAX_ACTIONS = 10

    def __init__(
        self,
        context: ContextManager,
        brain: OllamaBrain | None = None,
        tools: ToolRegistry | None = None,
        safety: SafetyGuard | None = None,
        task_planner: TaskPlanner | None = None,
    ) -> None:
        self.context = context
        self.brain = brain or OllamaBrain(context)
        self.tools = tools or ToolRegistry()
        self.safety = safety or SafetyGuard(self.tools)
        self.task_planner = task_planner or TaskPlanner()

    def plan(
        self,
        user_text: str,
    ) -> list[Action]:
        """
        Recebe um comando simples ou composto e retorna
        uma lista validada e segura de objetos Action.

        Comandos compostos são divididos pelo TaskPlanner.
        As ações são reunidas na ordem original e limitadas
        por MAX_ACTIONS.
        """

        if not user_text or not user_text.strip():
            return []

        tasks = self.task_planner.split(user_text)

        if not tasks:
            return []

        planned_actions: list[Action] = []

        for task in tasks:
            remaining_slots = self.MAX_ACTIONS - len(planned_actions)

            if remaining_slots <= 0:
                break

            task_actions = self._plan_single(task)
            planned_actions.extend(task_actions[:remaining_slots])

        return planned_actions

    def _plan_single(
        self,
        user_text: str,
    ) -> list[Action]:
        """
        Cria e valida o plano de uma única tarefa.
        """

        prompt = self._build_prompt(user_text)

        try:
            response = self.brain.respond(prompt)
            raw_actions = self._extract_json(response)
            validated_actions = self._validate_actions(raw_actions)

            return self.safety.filter_actions(
                user_text,
                validated_actions,
            )

        except Exception as error:
            print(
                "[IntelligentPlanner] "
                f"Erro ao criar plano para '{user_text}': {error}"
            )

            return []

    def _build_prompt(
        self,
        user_text: str,
    ) -> str:
        """
        Cria o prompt enviado ao modelo do Ollama.
        """

        available_actions = self.tools.build_prompt()

        return f"""
Você é o planejador de automações do Atlas.

Sua tarefa é transformar o pedido do usuário em uma lista JSON
de ações que o computador deve executar.

REGRAS OBRIGATÓRIAS:

1. Responda somente com JSON válido.
2. Não escreva explicações.
3. Não use blocos de código Markdown.
4. A resposta sempre deve ser uma lista JSON.
5. Cada ação deve possuir:
   - "type"
   - "parameters"
6. Use somente as ações disponíveis no catálogo.
7. Não invente ações.
8. Gere no máximo {self.MAX_ACTIONS} ações.
9. Preserve nomes de arquivos, pastas, sites e pesquisas
   informados pelo usuário.
10. Organize as ações na ordem correta de execução.
11. Quando um arquivo precisar ficar dentro de uma pasta,
    inclua o caminho da pasta no parâmetro "path".
12. Não execute nada. Apenas produza o plano.
13. Caso o pedido não possa ser resolvido usando as ferramentas
    disponíveis, responda somente:
    []
14. Não use ações destrutivas sem que o usuário peça
    explicitamente para excluir, apagar ou remover algo.
15. O campo "parameters" deve sempre ser um objeto JSON,
    mesmo quando não houver parâmetros.
16. Nunca invente caminhos do sistema.
17. Nunca tente apagar pastas do Windows, arquivos do sistema
    ou a raiz do disco.
18. Use process.start apenas para abrir programas conhecidos
    ou iniciar processos claramente solicitados.
19. Não use comandos de terminal destrutivos.
20. Para abrir o Bloco de Notas, use:
    ["notepad.exe"]
21. Quando o usuário pedir apenas para abrir o navegador, sem
    informar site ou endereço, use browser.open com a URL:
    "https://www.google.com"
22. Nunca gere browser.open com "parameters" vazio.
23. Para "maximize a tela", "maximize a janela" ou frases
    equivalentes sem título específico, use window.maximize.
24. Para "minimize a tela", "minimize a janela" ou frases
    equivalentes sem título específico, use window.minimize.
25. Ações window.maximize e window.minimize atuam sobre a janela
    ativa e não precisam de parâmetros.
26. Quando uma ação depender de um programa ou navegador que acabou
    de ser aberto, insira system.wait com 1 segundo antes da ação
    seguinte, quando necessário.

CATÁLOGO DE FERRAMENTAS:

{available_actions}

EXEMPLO 0:

Pedido do usuário:
Abra o navegador

Resposta:
[
  {{
    "type": "browser.open",
    "parameters": {{
      "url": "https://www.google.com"
    }}
  }}
]

EXEMPLO 0.1:

Pedido do usuário:
Maximize a tela

Resposta:
[
  {{
    "type": "window.maximize",
    "parameters": {{}}
  }}
]

EXEMPLO 1:

Pedido do usuário:
Crie uma pasta chamada Estudos e dentro dela crie um arquivo
chamado python.txt

Resposta:
[
  {{
    "type": "file.create_folder",
    "parameters": {{
      "path": "Estudos"
    }}
  }},
  {{
    "type": "file.create_file",
    "parameters": {{
      "path": "Estudos/python.txt"
    }}
  }}
]

EXEMPLO 2:

Pedido do usuário:
Abra o YouTube e pesquise por curso de Python

Resposta:
[
  {{
    "type": "browser.youtube_search",
    "parameters": {{
      "query": "curso de Python"
    }}
  }}
]

EXEMPLO 3:

Pedido do usuário:
Abra o bloco de notas, espere dois segundos e escreva Olá Ssamir

Resposta:
[
  {{
    "type": "process.start",
    "parameters": {{
      "command": ["notepad.exe"]
    }}
  }},
  {{
    "type": "system.wait",
    "parameters": {{
      "seconds": 2
    }}
  }},
  {{
    "type": "keyboard.write",
    "parameters": {{
      "text": "Olá Ssamir"
    }}
  }}
]

EXEMPLO 4:

Pedido do usuário:
Exclua o arquivo teste.txt

Resposta:
[
  {{
    "type": "file.delete",
    "parameters": {{
      "path": "teste.txt"
    }}
  }}
]

EXEMPLO 5:

Pedido do usuário:
Organize meus arquivos

Resposta:
[]

PEDIDO DO USUÁRIO:

{user_text}
""".strip()

    def _extract_json(
        self,
        response: str,
    ) -> list[dict[str, Any]]:
        """
        Extrai uma lista JSON da resposta do modelo.

        Também tenta corrigir o caso em que o modelo adiciona
        texto ou blocos Markdown antes ou depois do JSON.
        """

        if not response:
            return []

        cleaned = response.strip()

        cleaned = re.sub(
            r"^```(?:json)?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = re.sub(
            r"\s*```$",
            "",
            cleaned,
        )

        try:
            parsed = json.loads(cleaned)

        except json.JSONDecodeError:
            json_match = re.search(
                r"\[[\s\S]*\]",
                cleaned,
            )

            if not json_match:
                print(
                    "[IntelligentPlanner] "
                    "Nenhuma lista JSON encontrada."
                )

                return []

            try:
                parsed = json.loads(
                    json_match.group(0)
                )

            except json.JSONDecodeError as error:
                print(
                    "[IntelligentPlanner] "
                    f"JSON inválido: {error}"
                )

                return []

        if not isinstance(parsed, list):
            print(
                "[IntelligentPlanner] "
                "A resposta não é uma lista JSON."
            )

            return []

        valid_items: list[dict[str, Any]] = []

        for item in parsed:
            if isinstance(item, dict):
                valid_items.append(item)

        return valid_items

    def _validate_actions(
        self,
        raw_actions: list[dict[str, Any]],
    ) -> list[Action]:
        """
        Valida as ações produzidas pelo modelo antes
        de enviá-las para a camada de segurança.
        """

        validated_actions: list[Action] = []

        for raw_action in raw_actions[: self.MAX_ACTIONS]:
            action_type = raw_action.get("type")
            parameters = raw_action.get(
                "parameters",
                {},
            )

            if not isinstance(action_type, str):
                print(
                    "[IntelligentPlanner] "
                    "Ação ignorada: type inválido."
                )

                continue

            action_type = action_type.strip()

            if not action_type:
                continue

            if not self.tools.exists(action_type):
                print(
                    "[IntelligentPlanner] "
                    f"Ação não permitida ignorada: "
                    f"{action_type}"
                )

                continue

            if not isinstance(parameters, dict):
                print(
                    "[IntelligentPlanner] "
                    f"Parâmetros inválidos em {action_type}."
                )

                continue

            required_parameters = (
                self.tools.required_parameters(
                    action_type
                )
            )

            received_parameters = set(
                parameters.keys()
            )

            if not required_parameters.issubset(
                received_parameters
            ):
                missing_parameters = (
                    required_parameters
                    - received_parameters
                )

                print(
                    "[IntelligentPlanner] "
                    f"Parâmetros ausentes em "
                    f"{action_type}: "
                    f"{missing_parameters}"
                )

                continue

            clean_parameters = self._clean_parameters(
                action_type,
                parameters,
            )

            if clean_parameters is None:
                print(
                    "[IntelligentPlanner] "
                    f"Parâmetros recusados em "
                    f"{action_type}."
                )

                continue

            validated_actions.append(
                Action(
                    type=action_type,
                    parameters=clean_parameters,
                )
            )

        return validated_actions

    def _clean_parameters(
        self,
        action_type: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any] | None:
        """
        Limpa, normaliza e limita os parâmetros
        antes da verificação de segurança.
        """

        tool = self.tools.get(action_type)

        if tool is None:
            return None

        allowed_parameter_names = set(
            tool.required_parameters.keys()
        )

        allowed_parameter_names.update(
            tool.optional_parameters.keys()
        )

        cleaned: dict[str, Any] = {}

        for parameter_name in allowed_parameter_names:
            if parameter_name not in parameters:
                continue

            value = parameters.get(parameter_name)

            if parameter_name == "seconds":
                try:
                    seconds = float(value)

                except (TypeError, ValueError):
                    return None

                if seconds < 0:
                    return None

                cleaned[parameter_name] = min(
                    seconds,
                    30.0,
                )

                continue

            if parameter_name == "command":
                clean_command = self._clean_command(
                    value
                )

                if clean_command is None:
                    return None

                cleaned[parameter_name] = (
                    clean_command
                )

                continue

            if not isinstance(value, str):
                return None

            clean_value = value.strip()

            if not clean_value:
                return None

            if parameter_name in {
                "path",
                "source",
                "destination",
            }:
                clean_value = (
                    self._normalize_spoken_path(
                        clean_value
                    )
                )

            cleaned[parameter_name] = clean_value

        required_parameters = (
            self.tools.required_parameters(
                action_type
            )
        )

        if not required_parameters.issubset(
            cleaned.keys()
        ):
            return None

        return cleaned

    @staticmethod
    def _clean_command(
        command: Any,
    ) -> str | list[str] | None:
        """
        Valida o comando utilizado por process.start.
        """

        if isinstance(command, str):
            command = command.strip()

            if not command:
                return None

            return command

        if isinstance(command, list):
            cleaned_parts: list[str] = []

            for item in command:
                if not isinstance(item, str):
                    return None

                clean_item = item.strip()

                if not clean_item:
                    return None

                cleaned_parts.append(clean_item)

            if not cleaned_parts:
                return None

            return cleaned_parts

        return None

    @staticmethod
    def _normalize_spoken_path(
        path: str,
    ) -> str:
        """
        Converte caminhos e nomes de arquivos falados
        para o formato correto.

        Exemplos:
        ideias ponto txt -> ideias.txt
        programa ponto py -> programa.py
        projetos barra teste ponto txt
        -> projetos/teste.txt
        """

        normalized_path = path.strip()

        normalized_path = re.sub(
            r"\s+ponto\s+",
            ".",
            normalized_path,
            flags=re.IGNORECASE,
        )

        normalized_path = re.sub(
            r"\s+dot\s+",
            ".",
            normalized_path,
            flags=re.IGNORECASE,
        )

        normalized_path = re.sub(
            r"\s+barra\s+",
            "/",
            normalized_path,
            flags=re.IGNORECASE,
        )

        normalized_path = re.sub(
            r"\s+",
            " ",
            normalized_path,
        )

        return normalized_path.strip()
