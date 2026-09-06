# Atlas Integration Framework — Fundação

Esta etapa substitui a integração específica do Business Lab por uma
arquitetura genérica de conectores.

## Arquitetura

```text
Atlas Core
    |
    v
IntegrationManager
    |
    v
ConnectorRegistry
    |
    +--> BusinessLabConnector
            |
            +--> API Driver      prioridade 10
            +--> Browser Driver  prioridade 20
            +--> Vision Driver   prioridade 30
```

O Atlas Core não importa código do Nexyra Business Lab e não acessa
o SQLite do laboratório.

## Instalação importante

A etapa anterior criou:

`atlas/integrations/business_lab.py`

Agora `business_lab` vira um pacote. Antes de extrair este ZIP,
remova apenas o arquivo antigo:

```powershell
Remove-Item .\atlas\integrations\business_lab.py -Force
```

Não remova a pasta `atlas\integrations`.

Depois extraia o pacote sobre `C:\Atlas_OFICIAL`.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_integration_framework.py
.\.venv\Scripts\python.exe -m pytest -q tests\test_business_lab_connector.py
.\.venv\Scripts\python.exe -m ruff check .
```

## Teste real

Com o Business Lab rodando:

```powershell
.\.venv\Scripts\python.exe tools\test_integration_framework.py
```

A ação `health` deve usar o API Driver.

## Compatibilidade

`atlas.integrations.business_lab.BusinessLabBridge` continua
temporariamente disponível para não quebrar o teste da etapa anterior.

## Próxima etapa

Criar a REST API operacional do Business Lab:
leads, atendimentos, retornos, matrículas, cursos e relatórios.

Depois o `BusinessLabApiDriver` passará a suportar essas ações.
