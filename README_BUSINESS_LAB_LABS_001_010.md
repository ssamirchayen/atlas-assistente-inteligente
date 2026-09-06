# Atlas — Etapa 13.2

## Business Lab LAB-001 a LAB-010 via Integration Framework

Esta etapa adiciona um runner operacional para o Atlas executar os cenários
LAB-001 a LAB-010 contra o Nexyra Business Lab usando o conector `business_lab`.

O runner não consulta gabaritos oficiais, não usa `/api/v1/cenarios` e não expõe
respostas internas do Business Lab. Ele só executa ações reais via API:

- consultar lead;
- filtrar leads;
- consultar atendimentos;
- registrar atendimento;
- criar retorno;
- criar matrícula;
- atualizar matrícula;
- consultar relatórios;
- validar bloqueio de ações proibidas de gabarito.

## Instalação

Extraia este patch na raiz do Atlas:

```powershell
cd C:\Atlas_OFICIAL
Expand-Archive "$env:USERPROFILE\Downloads\atlas_business_lab_labs_001_010.zip" `
  -DestinationPath "C:\Atlas_OFICIAL" -Force
```

## Testes unitários

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_business_lab_lab_runner.py
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

## Execução real

Com o Business Lab aberto em `http://127.0.0.1:5055`:

```powershell
$env:ATLAS_BUSINESS_LAB_URL="http://127.0.0.1:5055"
$env:ATLAS_BUSINESS_LAB_EMAIL="consultor@nexyra.lab"
$env:ATLAS_BUSINESS_LAB_PASSWORD="Consultor123!"

.\.venv\Scripts\python.exe tools\run_business_lab_labs_001_010.py
```

Resultado esperado:

```text
Resumo: 10/10 cenários operacionais passaram.
```
