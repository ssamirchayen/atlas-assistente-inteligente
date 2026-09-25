# Atlas — Sprint 28.12
## Validação final da integração visual

Esta etapa fecha a Sprint 28 consolidada: Enterprise Integration + Business Lab + Copilot.

O objetivo é validar o fluxo completo:

```text
Business Lab HTML
↓
Widget Atlas
↓
Atlas Copilot Bridge
↓
Integration Framework
↓
Business Lab API
```

## O que valida

- Business Lab online em `http://127.0.0.1:5055`
- Atlas Copilot Bridge online em `http://127.0.0.1:8765`
- Envio de contexto de página com `lead_code`
- Resumo de lead
- Sugestão de próxima ação
- Consulta de cursos
- Consulta de dashboard
- Simulação segura de atendimento
- Simulação segura de retorno

As ações de atendimento e retorno são executadas com `dry_run=True` nesta validação,
para não poluir a base durante o teste final.

## Como rodar

1. Abra o Business Lab:

```powershell
cd C:\Nexyra_Business_Lab
.\.venv\Scripts\python.exe app.py
```

2. Abra o Atlas Copilot Bridge:

```powershell
cd C:\Atlas_OFICIAL

$env:ATLAS_BUSINESS_LAB_URL="http://127.0.0.1:5055"
$env:ATLAS_BUSINESS_LAB_EMAIL="consultor@nexyra.lab"
$env:ATLAS_BUSINESS_LAB_PASSWORD="Consultor123!"

.\.venv\Scripts\python.exe tools\run_atlas_copilot_bridge.py
```

3. Em outro PowerShell, rode a validação:

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe tools\run_atlas_copilot_visual_validation.py
```

## Saída

O relatório será salvo em:

```text
C:\Atlas_OFICIAL\data\business_lab_benchmark
```

Arquivos gerados:

```text
atlas_copilot_visual_validation_*.json
atlas_copilot_visual_validation_*.md
```

## Resultado esperado

```text
Resultado: APROVADO
Etapas: 8/8
```

Se passar, a Sprint 28 está pronta para ser fechada e a próxima sprint será:

```text
Sprint 29 — Site oficial Atlas/Nexyra
```
