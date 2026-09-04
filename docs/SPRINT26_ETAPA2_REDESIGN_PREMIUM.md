# Sprint 26 — Etapa 2 — Redesign Premium do Frontend

## Objetivo
Transformar o workspace do Atlas em uma interface desktop com identidade visual de produto premium, sem alterar o fluxo operacional do Core.

## Alterações
- Dark mode premium como identidade principal.
- Branding `ATLAS by NEXYRA` reforçado.
- Sidebar mais compacta e sofisticada.
- Header com indicadores de engine/runtime.
- Conversa reposicionada como elemento central do produto.
- Cabeçalho da conversa com identidade do Atlas e estado da sessão.
- Composer inferior mais compacto e moderno.
- Painel `System Pulse` para workflow e modo de interação.
- Telemetria de CPU/RAM redesenhada.
- Bloco de ações rápidas para Histórico e Admin Console.
- Estados de voz, execução, erro e conclusão adaptados ao novo tema.
- Mensagens do usuário, Atlas e sistema adaptadas ao dark mode.

## Arquivos alterados
- `atlas/gui/window.py`
- `atlas/gui/theme.py`
- `atlas/tests/test_frontend_theme.py`

## Preservado
A Etapa 2 não substitui `gui_main.py`, portanto o hotfix de instância única do instalador permanece intacto.

Também permanecem conectados ao backend oficial:
- `AtlasGuiService`
- `SerialCommandRunner`
- cancelamento de workflow
- retomada de execução
- Admin Console
- histórico operacional
- voz e escuta contínua
- interrupção por voz
- Vision Overlay
