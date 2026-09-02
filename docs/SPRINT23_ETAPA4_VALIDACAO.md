# Sprint 23 — Etapa 4: Relatório de validação

Data da validação: 1º de setembro de 2026.

## Escopo

- RBAC com cinco funções corporativas;
- política separada por organização;
- allowlists derivadas de receitas revisadas pela TI;
- bloqueio de caminhos do sistema e comandos livres;
- dupla trava para execução real;
- separação entre solicitante, aprovador e executor;
- auditoria SQLite sanitizada, limitada e com retenção;
- cancelamento e rollback já fornecidos pelo executor supervisionado;
- piloto integral somente em dry-run.

## Segurança automatizada

Os testes novos cobrem:

- negação por função e por organização;
- falha fechada quando não existe política;
- perfil, pacote, configuração, diretório e quantidade fora da allowlist;
- recusa de execução real sem permissão explícita;
- executor igual ao aprovador;
- consulta de tarefas e auditoria limitada à empresa;
- ausência do nome do ator e referência do funcionário nos eventos;
- banco sem coluna de metadados, token ou dados pessoais;
- retenção por idade e quantidade;
- indisponibilidade da auditoria impedindo a mutação.

## Comandos reproduzíveis

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q atlas edge_governance_pilot.py atlas_validation.py
.\.venv\Scripts\python.exe -m atlas_validation run --domain edge
.\.venv\Scripts\python.exe edge_governance_pilot.py
```

Mantenha a execução real desativada durante a validação:

```env
ATLAS_PROVISIONING_DRY_RUN=1
ATLAS_EDGE_EXECUTION_ENABLED=0
```

## Resultado final

- suíte completa: **957 testes aprovados**;
- testes novos da Etapa 4: **30 aprovados**;
- testes direcionados do Atlas Edge: **62 aprovados**;
- Ruff: aprovado no projeto inteiro;
- compilação: todos os módulos Python aprovados;
- Validation Lab: `EDGE-001`, `EDGE-003`, `EDGE-005` e `EDGE-007` aprovados;
- cenários manuais: `EDGE-002`, `EDGE-004`, `EDGE-006` e `EDGE-008` registrados;
- piloto: isolamento confirmado, três etapas simuladas e dez eventos auditados;
- nenhuma alteração real no computador.

Os dois avisos são de módulos descontinuados carregados pela dependência externa
SpeechRecognition (`aifc` e `audioop`). Eles não são falhas da Sprint 23.
