# Sprint 23 — Etapa 2: Relatório de validação

Data da validação: 1º de setembro de 2026.

## Resultado

- suíte completa: **904 testes aprovados**;
- testes novos da Etapa 2: **15 aprovados**;
- Ruff: aprovado no projeto inteiro;
- compilação: todos os módulos Python aprovados;
- Validation Lab: `EDGE-001` e `EDGE-003` aprovados;
- cenários manuais: `EDGE-002` e `EDGE-004` registrados;
- piloto local: dois perfis listados, plano autorizado e nenhuma etapa executada.

Os dois avisos da suíte completa são de módulos descontinuados carregados pela
dependência externa SpeechRecognition (`aifc` e `audioop`). Eles não são falhas
da Sprint 23.

## Cobertura de segurança

Os testes comprovam:

- catálogo fechado, ordenado e limitado de perfis;
- pacotes declarados por ID exato e pastas relativas ao workspace;
- rejeição de perfil criado livremente pelo usuário;
- referências privadas normalizadas e convertidas em SHA-256;
- token temporário, de uso único e ausente dos payloads;
- separação obrigatória entre solicitante e aprovador;
- bloqueio para dispositivo não cadastrado ou pausado;
- revalidação do vínculo, perfil e inventário;
- revogação da solicitação anterior quando um novo plano é gerado;
- ausência de executor, rede, subprocesso e comandos arbitrários.

## Comandos reproduzíveis

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m compileall -q atlas edge_profile_pilot.py atlas_validation.py
.\.venv\Scripts\python.exe -m atlas_validation run --domain edge
.\.venv\Scripts\python.exe edge_profile_pilot.py
```

O piloto exige `SIM` nas duas confirmações. Ele usa estado temporário e
inventário sintético, sem instalar programas ou criar pastas corporativas.

## Conteúdo do pacote

O ZIP é incremental em relação à Etapa 1 da Sprint 23. Não inclui `.env`, bancos,
logs, caches, bytecode, ambiente virtual, tokens ou estado local do dispositivo.
