# Sprint 29 / Bloco G — Copilot Bridge Nexyra + Atlas

## Objetivo

Levar o Atlas para dentro da edição **Nexyra + Atlas**, sem alterar o Nexyra padrão.

## Fluxo

1. A GUI do Atlas inicia um bridge local em `127.0.0.1:8765` quando a integração Nexyra está habilitada.
2. O Nexyra + Atlas nunca expõe o token do bridge no frontend.
3. O frontend chama o próprio backend Nexyra.
4. O backend Nexyra faz proxy local para o Atlas.
5. O bridge reutiliza o mesmo `SerialCommandRunner` da GUI do Atlas.
6. Consultas e confirmações usam o mesmo estado do SkillRouter, inclusive a ação Nexyra pendente.

## Segurança

- Bridge restrito ao loopback local.
- Token opcional `ATLAS_COPILOT_TOKEN` recomendado.
- Rota do Nexyra protegida por sessão e permissão `atlas.use`.
- Vendedores podem consultar o Atlas, mas ações que exigem `atlas.execute` continuam limitadas a gerente/admin.
- Nexyra padrão permanece sem a página e sem as rotas Copilot.

## Configuração

Atlas:

```env
ATLAS_COPILOT_ENABLED=1
ATLAS_COPILOT_HOST=127.0.0.1
ATLAS_COPILOT_PORT=8765
ATLAS_COPILOT_TOKEN=troque-por-um-token-local
ATLAS_COPILOT_TIMEOUT_SECONDS=45
```

Nexyra + Atlas:

```env
ATLAS_COPILOT_BRIDGE_URL=http://127.0.0.1:8765
ATLAS_COPILOT_TOKEN=troque-por-o-mesmo-token-local
ATLAS_COPILOT_TIMEOUT_SECONDS=45
```

## Validação executada

- `tests/` do Atlas: 192 passed, 7 skipped.
- Estruturais Atlas relevantes: 23 passed.
- Contrato real Atlas ↔ Nexyra + Atlas: 7 passed.
- Nexyra + Atlas: 227 testes passaram em 3 blocos.
- `compileall` passou.
- Ruff deve ser validado no Windows do projeto.
- Frontend TypeScript/Vite deve ser validado no Windows, pois o ambiente de construção não possuía `node_modules` e não tem acesso ao registry.
