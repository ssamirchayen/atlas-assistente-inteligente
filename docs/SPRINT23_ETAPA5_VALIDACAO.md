# Sprint 23 — Etapa 5: Relatório de validação

Data da validação: 1º de setembro de 2026.

## Resultado

- suíte completa: **994 testes aprovados**;
- testes novos da Etapa 5: **37 aprovados**;
- testes direcionados de onboarding, perfis e governança: **70 aprovados**;
- Ruff: aprovado nos arquivos direcionados e no projeto inteiro;
- compilação: todos os módulos Python aprovados;
- Validation Lab: `EDGE-001`, `EDGE-003`, `EDGE-005`, `EDGE-007` e
  `EDGE-009` aprovados;
- pilotos manuais: `EDGE-002`, `EDGE-004`, `EDGE-006`, `EDGE-008` e
  `EDGE-010` registrados;
- piloto final: três etapas simuladas, um relatório e dez eventos auditados;
- nenhuma alteração real no computador.

Os dois avisos vêm dos módulos descontinuados `aifc` e `audioop`, carregados
pela dependência externa SpeechRecognition. Eles não são falhas do Atlas.

## Cobertura automatizada

- serialização e validação de todos os estados do workflow;
- escrita atômica, limite de tamanho e rollback da memória após falha;
- rejeição de arquivo corrompido, duplicado ou acima do limite;
- revisão monotônica contra sobrescrita antiga;
- remoção apenas de registros terminais ao atingir o limite;
- fluxo completo com operador, aprovador e executor diferentes;
- múltiplos funcionários com aprovações independentes;
- bloqueio de duplicidade por referência ativa;
- isolamento entre organizações;
- tokens, autorização e referência pessoal ausentes do disco;
- cancelamento antes e depois da fila;
- recuperação segura de sessão de aprovação perdida;
- retomada de onboarding já enfileirado;
- reconciliação idempotente;
- falha de inventário refletida no workflow;
- relatório por organização e limite de workflows ativos.
- aprovação concorrente consome o token somente uma vez;
- execução concorrente conclui a tarefa somente uma vez.

## Comandos reproduzíveis

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q atlas edge_onboarding_pilot.py atlas_validation.py
.\.venv\Scripts\python.exe -m atlas_validation run --domain edge
.\.venv\Scripts\python.exe edge_onboarding_pilot.py
```

Mantenha durante a validação:

```env
ATLAS_PROVISIONING_DRY_RUN=1
ATLAS_EDGE_EXECUTION_ENABLED=0
```

O pacote da Etapa 5 é incremental sobre a Etapa 4 e contém somente arquivos
novos ou modificados. Não inclui `.env`, bancos, logs, caches, bytecode, ambiente
virtual, tokens ou estado local do dispositivo.
