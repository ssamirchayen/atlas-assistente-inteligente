# Atlas Vision — Etapa 1: Fundação e captura segura

## Objetivo

Criar a base visual do Atlas antes de conectar interpretação por IA,
Planner ou Executor.

## Entregas

- novo pacote `atlas/vision/`;
- modelo imutável de captura;
- serviço de captura da tela principal;
- armazenamento local separado em `data/vision`;
- limpeza controlada de capturas;
- capturas ignoradas pelo Git;
- configurações via `.env`;
- piloto manual;
- testes sem capturar a tela real durante o Pytest.

## Segurança e privacidade

Nesta etapa o Vision **não executa ações** a partir do conteúdo visual.
Ele apenas captura a tela quando o serviço é chamado explicitamente.

As imagens ficam em `data/vision`, que não deve ser versionado.
`ATLAS_VISION_KEEP_CAPTURES=0` é o padrão preparado para uso transitório.

## Teste manual

```powershell
C:\Atlas_OFICIAL\.venv\Scripts\python.exe vision_capture_pilot.py
```

O terminal deverá mostrar o caminho do PNG e a resolução detectada.

## Próxima etapa

Vision Etapa 2: interpretação visual. A captura será enviada a um backend
multimodal de forma isolada, retornando uma descrição estruturada antes
de qualquer integração com comandos ou automação.
