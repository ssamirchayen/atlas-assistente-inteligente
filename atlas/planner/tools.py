from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolDefinition:
    """
    Representa uma ferramenta disponível para o Planner Inteligente.
    """

    action_type: str
    description: str
    required_parameters: dict[str, str] = field(
        default_factory=dict
    )
    optional_parameters: dict[str, str] = field(
        default_factory=dict
    )
    dangerous: bool = False

    def prompt_description(self) -> str:
        """
        Retorna a descrição da ferramenta em formato adequado
        para ser enviada ao modelo de IA.
        """

        parts = [
            f"Ação: {self.action_type}",
            f"Descrição: {self.description}",
        ]

        if self.required_parameters:
            required = ", ".join(
                f"{name}: {description}"
                for name, description
                in self.required_parameters.items()
            )

            parts.append(
                f"Parâmetros obrigatórios: {required}"
            )
        else:
            parts.append(
                "Parâmetros obrigatórios: nenhum"
            )

        if self.optional_parameters:
            optional = ", ".join(
                f"{name}: {description}"
                for name, description
                in self.optional_parameters.items()
            )

            parts.append(
                f"Parâmetros opcionais: {optional}"
            )

        if self.dangerous:
            parts.append(
                "Atenção: esta ação é potencialmente destrutiva."
            )

        return "\n".join(parts)


class ToolRegistry:
    """
    Registro central das ferramentas disponíveis no Atlas.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

        self._register_default_tools()

    def register(self, tool: ToolDefinition) -> None:
        """
        Adiciona ou atualiza uma ferramenta no registro.
        """

        self._tools[tool.action_type] = tool

    def unregister(self, action_type: str) -> None:
        """
        Remove uma ferramenta do registro.
        """

        self._tools.pop(action_type, None)

    def get(
        self,
        action_type: str,
    ) -> ToolDefinition | None:
        """
        Retorna uma ferramenta pelo nome da ação.
        """

        return self._tools.get(action_type)

    def exists(self, action_type: str) -> bool:
        """
        Verifica se uma ação está registrada.
        """

        return action_type in self._tools

    def all(self) -> list[ToolDefinition]:
        """
        Retorna todas as ferramentas registradas.
        """

        return list(self._tools.values())

    def action_types(self) -> set[str]:
        """
        Retorna o nome de todas as ações disponíveis.
        """

        return set(self._tools.keys())

    def required_parameters(
        self,
        action_type: str,
    ) -> set[str]:
        """
        Retorna os parâmetros obrigatórios de uma ação.
        """

        tool = self.get(action_type)

        if tool is None:
            return set()

        return set(tool.required_parameters.keys())

    def build_prompt(self) -> str:
        """
        Cria o catálogo completo das ferramentas para o modelo.
        """

        descriptions = [
            tool.prompt_description()
            for tool in self.all()
        ]

        return "\n\n".join(descriptions)

    def _register_default_tools(self) -> None:
        """
        Registra as ferramentas que o Atlas já possui.
        """

        # ==================================================
        # NAVEGADOR
        # ==================================================

        self.register(
            ToolDefinition(
                action_type="browser.open",
                description=(
                    "Abre o navegador padrão do computador."
                ),
            )
        )

        self.register(
            ToolDefinition(
                action_type="browser.open_site",
                description=(
                    "Abre um site conhecido pelo nome."
                ),
                required_parameters={
                    "name": (
                        "Nome do site, como github, youtube, "
                        "google, gmail ou instagram."
                    ),
                },
            )
        )

        self.register(
            ToolDefinition(
                action_type="browser.search",
                description=(
                    "Realiza uma pesquisa no Google."
                ),
                required_parameters={
                    "query": "Texto que deve ser pesquisado.",
                },
            )
        )

        self.register(
            ToolDefinition(
                action_type="browser.youtube_search",
                description=(
                    "Realiza uma pesquisa diretamente no YouTube."
                ),
                required_parameters={
                    "query": "Texto que deve ser pesquisado.",
                },
            )
        )

        # ==================================================
        # ARQUIVOS E PASTAS
        # ==================================================

        self.register(
            ToolDefinition(
                action_type="file.create_folder",
                description=(
                    "Cria uma pasta no computador."
                ),
                required_parameters={
                    "path": (
                        "Caminho ou nome da pasta que será criada."
                    ),
                },
            )
        )

        self.register(
            ToolDefinition(
                action_type="file.create_file",
                description=(
                    "Cria um arquivo vazio no computador."
                ),
                required_parameters={
                    "path": (
                        "Caminho completo ou nome do arquivo."
                    ),
                },
            )
        )

        self.register(
            ToolDefinition(
                action_type="file.copy",
                description=(
                    "Copia um arquivo ou uma pasta."
                ),
                required_parameters={
                    "source": "Caminho de origem.",
                    "destination": "Caminho de destino.",
                },
            )
        )

        self.register(
            ToolDefinition(
                action_type="file.move",
                description=(
                    "Move um arquivo ou uma pasta."
                ),
                required_parameters={
                    "source": "Caminho de origem.",
                    "destination": "Caminho de destino.",
                },
            )
        )

        self.register(
            ToolDefinition(
                action_type="file.rename",
                description=(
                    "Renomeia um arquivo ou uma pasta."
                ),
                required_parameters={
                    "source": "Caminho atual.",
                    "destination": "Novo caminho ou nome.",
                },
            )
        )

        self.register(
            ToolDefinition(
                action_type="file.delete",
                description=(
                    "Exclui um arquivo ou uma pasta."
                ),
                required_parameters={
                    "path": (
                        "Caminho do arquivo ou da pasta."
                    ),
                },
                dangerous=True,
            )
        )

        # ==================================================
        # TECLADO
        # ==================================================

        self.register(
            ToolDefinition(
                action_type="keyboard.write",
                description=(
                    "Digita um texto na janela que estiver ativa."
                ),
                required_parameters={
                    "text": "Texto que deve ser digitado.",
                },
            )
        )

        self.register(
            ToolDefinition(
                action_type="keyboard.press",
                description=(
                    "Pressiona uma tecla do teclado."
                ),
                required_parameters={
                    "key": (
                        "Nome da tecla, como enter, tab, esc "
                        "ou space."
                    ),
                },
            )
        )

        # ==================================================
        # MOUSE
        # ==================================================

        self.register(
            ToolDefinition(
                action_type="mouse.click",
                description=(
                    "Realiza um clique na posição atual do mouse."
                ),
            )
        )

        # ==================================================
        # PROCESSOS
        # ==================================================

        self.register(
            ToolDefinition(
                action_type="process.start",
                description=(
                    "Abre um programa ou inicia um processo."
                ),
                required_parameters={
                    "command": (
                        "Comando, executável ou lista de argumentos."
                    ),
                },
            )
        )

        # ==================================================
        # JANELAS
        # ==================================================

        self.register(
            ToolDefinition(
                action_type="window.minimize",
                description=(
                    "Minimiza a janela ativa."
                ),
            )
        )

        self.register(
            ToolDefinition(
                action_type="window.maximize",
                description=(
                    "Maximiza a janela ativa."
                ),
            )
        )

        self.register(
            ToolDefinition(
                action_type="window.restore",
                description=(
                    "Restaura a janela ativa."
                ),
            )
        )

        self.register(
            ToolDefinition(
                action_type="window.close",
                description=(
                    "Fecha a janela ativa."
                ),
            )
        )

        self.register(
            ToolDefinition(
                action_type="window.next",
                description=(
                    "Alterna para a próxima janela aberta."
                ),
            )
        )

        self.register(
            ToolDefinition(
                action_type="window.previous",
                description=(
                    "Alterna para a janela anterior."
                ),
            )
        )

        self.register(
            ToolDefinition(
                action_type="window.desktop",
                description=(
                    "Mostra ou restaura a área de trabalho."
                ),
            )
        )

        self.register(
            ToolDefinition(
                action_type="window.focus",
                description=(
                    "Coloca uma janela específica em primeiro plano."
                ),
                required_parameters={
                    "title": (
                        "Título ou parte do título da janela."
                    ),
                },
            )
        )

        self.register(
            ToolDefinition(
                action_type="window.minimize_title",
                description=(
                    "Minimiza uma janela pelo título."
                ),
                required_parameters={
                    "title": (
                        "Título ou parte do título da janela."
                    ),
                },
            )
        )

        self.register(
            ToolDefinition(
                action_type="window.maximize_title",
                description=(
                    "Maximiza uma janela pelo título."
                ),
                required_parameters={
                    "title": (
                        "Título ou parte do título da janela."
                    ),
                },
            )
        )

        self.register(
            ToolDefinition(
                action_type="window.close_title",
                description=(
                    "Fecha uma janela pelo título."
                ),
                required_parameters={
                    "title": (
                        "Título ou parte do título da janela."
                    ),
                },
                dangerous=True,
            )
        )

        # ==================================================
        # SISTEMA
        # ==================================================

        self.register(
            ToolDefinition(
                action_type="system.wait",
                description=(
                    "Espera alguns segundos antes da próxima ação."
                ),
                required_parameters={
                    "seconds": (
                        "Quantidade de segundos de espera."
                    ),
                },
            )
        )
