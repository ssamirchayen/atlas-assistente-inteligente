# Sprint 29 — Bloco H — Fechamento final Nexyra + Atlas

A Sprint 29 fecha a integração bidirecional entre o Atlas e a edição `Nexyra_CRM_Atlas`. O `Nexyra_CRM` padrão permanece independente.

## Canais finais

- **Atlas -> Nexyra:** contrato `nexyra-crm-atlas/1.0`, contexto operacional, inteligência e ações supervisionadas com prévia, revalidação, confirmação e auditoria.
- **Nexyra -> Atlas:** Copilot Bridge local e chat lateral global com contexto da tela atual.

## Portas locais padrão

- `8000`: backend Nexyra;
- `5173`: frontend Nexyra em desenvolvimento;
- `8765`: API normal do Atlas;
- `8766`: Copilot Bridge Nexyra -> Atlas.

## Segredos

Use dois segredos diferentes:

- `ATLAS_NEXYRA_TOKEN` no Atlas = `ATLAS_INTEGRATION_TOKEN` no Nexyra;
- `ATLAS_COPILOT_TOKEN` no Atlas = `ATLAS_COPILOT_TOKEN` no Nexyra.

Nunca versione `.env`.

## Validação final

```powershell
cd C:\Atlas_OFICIAL
.\.venv\Scripts\python.exe tools\validate_sprint29_nexyra.py --nexyra-root C:\Nexyra_CRM_Atlas --online
```

Regressão completa:

```powershell
cd C:\Atlas_OFICIAL
.\tools\validate_sprint29_final.ps1 -NexyraRoot C:\Nexyra_CRM_Atlas -Online
```

O validador não imprime tokens.
