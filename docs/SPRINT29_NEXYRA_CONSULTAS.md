# Atlas — Sprint 29: conector Nexyra, consultas e ações supervisionadas

Entrega de 16/09/2026. Base: Atlas_OFICIAL(9).zip e contrato 1.0 do CRM enviado em 15/09/2026.

## O que foi entregue

Conector `nexyra_crm` registrado no framework de integração e ligado ao roteador prioritário que a GUI utiliza. Cada consulta verifica saúde, contrato, token, capacidades, empresa, usuário e permissão `atlas.use`. Não utiliza o cliente antigo `/lead-hub`.

Comandos disponíveis na conversa:

- `Nexyra diagnóstico`
- `Nexyra resumo`
- `Nexyra indicadores`
- `Nexyra pendências`
- `Nexyra fontes`

O diagnóstico informa a identidade acessada e as capacidades remotas. O resumo usa os indicadores calculados pelo CRM; a conversão é sobre oportunidades encerradas. As fontes contam leads ativos. As pendências são da empresa e exibem no máximo 25 itens, junto ao total informado pelo servidor. Não há filtro de período nem paginação nessa rota. Os valores são exibidos sem presumir moeda, pois esse contrato não a informa.

Também foi entregue o bloco C — ações supervisionadas. O Atlas reconhece apenas a prévia explícita abaixo; ele não transforma uma frase comum em alteração:

```text
Nexyra prévia lead.update LEAD-ID {"status":"contatado"}
Nexyra prévia opportunity.move OPP-ID {"to_stage":"qualificado"}
Nexyra prévia activity.create {"activity_type":"call","title":"Ligar","lead_public_id":"LEAD-ID"}
Nexyra prévia activity.complete ACT-ID
```

Opcionalmente, acrescente `; motivo: texto`. A prévia mostra a ação, alvo e payload normalizado e pede resposta `sim` ou `não`. Depois de `sim`, o Atlas faz uma nova prévia no CRM; se qualquer detalhe mudar, ele aborta sem executar. Só então envia `confirmed: true` à rota de execução. Falha de rede ou resposta incerta limpa o estado e não gera repetição automática. O CRM continua decidindo a permissão: consulta exige `atlas.use`; execução exige `atlas.execute`.

Os blocos A, B e C entregaram conector, consultas e ações supervisionadas. O Bloco D fecha o ciclo de segurança da confirmação: `route_priority()` intercepta a resposta antes do Planner, a prévia expira em 2 minutos, cancelamento/limpeza invalidam o estado e falhas de escrita nunca geram retry automático. Consulte `SPRINT29_BLOCO_D_FECHAMENTO.md`.

A Sprint 29 pode então avançar para ampliar o contrato com fila/SLA, canais e relatórios do Nexyra CRM 1.0 Desktop, mantendo a mesma política de autenticação, autorização e auditoria.

## Aplicar

1. Feche o Atlas e faça uma cópia da pasta atual.
2. Extraia o conteúdo deste ZIP na raiz `Atlas_OFICIAL`, onde ficam `gui_main.py`, `atlas/`, `tests/` e `tools/`. Não crie uma segunda pasta `Atlas_OFICIAL` dentro dela.
3. Os arquivos existentes alterados são `atlas/integrations/__init__.py` e `atlas/skills/router.py`. Os demais são novos. Se esses dois arquivos receberam alterações locais posteriores ao pacote base, compare-os antes de substituir.
4. Configure o Atlas e reinicie por `gui_main.py`.

Este ZIP não contém dados, credenciais, alterações do CRM nem um novo executável. Um EXE já instalado precisa de uma nova build para incorporar o código; para validar esta entrega, use o projeto Python.

## Configurar

No PowerShell, dentro da pasta do Atlas, descubra o arquivo de configuração usado pelo seu ambiente:

```powershell
.\.venv\Scripts\python.exe -c "from atlas.core.config import RUNTIME_PATHS; print(RUNTIME_PATHS.config_file)"
```

Acrescente nele as variáveis do exemplo abaixo, substituindo os valores pelos do seu CRM. Preserve as outras configurações existentes.

```dotenv
ATLAS_NEXYRA_URL=http://127.0.0.1:8000
ATLAS_NEXYRA_TOKEN=COLE_O_TOKEN_DA_INTEGRACAO_CRM
ATLAS_NEXYRA_WORKSPACE_ID=WS-ID_DA_EMPRESA
ATLAS_NEXYRA_ACTOR_USER_ID=USR-ID_DO_USUARIO
ATLAS_NEXYRA_TIMEOUT=10
```

- URL: endereço raiz do **backend Nexyra**, sem `/api/v1` e sem o caminho do frontend. Ajuste a porta ao seu ambiente. Para servidor remoto, utilize HTTPS.
- Token: o mesmo valor de `ATLAS_INTEGRATION_TOKEN` no backend Nexyra. Não é o token da Meta nem a sessão de login do CRM.
- Empresa: o `public_id` da empresa/workspace (`WS-...`).
- Usuário: o `user_public_id` de um membro ativo dessa empresa (`USR-...`), com `atlas.use`. Use os IDs retornados pelo CRM, não nomes ou IDs numéricos do banco.
- Timeout: tempo máximo em segundos por chamada (maior que zero e até 60). Uma consulta completa faz três chamadas; não há repetição automática.

Há também um arquivo `.env.nexyra.example` para copiar apenas essas linhas.

## Testar no Windows

Com o backend CRM iniciado:

```powershell
.\.venv\Scripts\python.exe tools\check_nexyra_crm.py
.\.venv\Scripts\python.exe tools\check_nexyra_crm.py --consulta resumo
.\.venv\Scripts\python.exe tools\check_nexyra_crm.py --consulta pendencias
.\.venv\Scripts\python.exe gui_main.py
```

Na conversa, use `Nexyra diagnóstico` e depois `Nexyra resumo`. Para uma escrita, use uma das prévias explícitas documentadas acima e só responda `sim` depois de conferir a ação.

Verificação automatizada local (usa dados sintéticos, sem acessar seu CRM):

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_nexyra_crm.py tests/test_integration_framework.py atlas/tests/test_skill_router_memory.py -q
.\.venv\Scripts\python.exe -m ruff check atlas/integrations/nexyra_crm atlas/integrations/__init__.py atlas/skills/router.py tests/test_nexyra_crm.py tests/test_nexyra_crm_contract.py tools/check_nexyra_crm.py
```

O teste opcional `tests/test_nexyra_crm_contract.py` usa o código do CRM via `NEXYRA_CRM_SOURCE`, FastAPI TestClient e um banco SQLite criado somente em memória. Precisa das dependências Python de testes do CRM nesse ambiente. Por padrão, fica ignorado quando a variável não está definida.

```powershell
$env:NEXYRA_CRM_SOURCE = "C:\Nexyra_CRM"
.\.venv\Scripts\python.exe -m pytest tests/test_nexyra_crm_contract.py -q
Remove-Item Env:NEXYRA_CRM_SOURCE
```

## Validação executada nesta entrega

- 83 testes aprovados: conector, validação do contrato, isolamento de identidade, erros HTTP/rede, prévia, confirmação, revalidação, limite, comandos, roteador de memória e framework de integração.
- 5 testes aprovados contra as rotas, schemas, segurança, serviço e modelos reais do CRM fornecido, com transporte ASGI e banco sintético em memória: consultas, token inválido, outra empresa, usuário desconhecido, prévia, bloqueio por `atlas.execute` e execução autorizada.
- Ruff: todos os arquivos Python novos/alterados aprovados.
- CLI sem configuração: mensagem útil e código de saída 1, como esperado.
- Dois avisos de depreciação nas dependências Starlette/httpx/AnyIO do ambiente de teste, sem falhas.

Ambiente desta validação: Linux, Python 3.12. Não foi testado um CRM em produção, microfone, interface gráfica Windows ou instalador. O teste do roteador verifica a entrada usada pela conversa; a abertura visual da GUI deve ser conferida no seu Windows. Não foi executada a suíte inteira de voz/Vision/hardware.

## Erros tratados

Ausência de configuração, URL inválida, timeout, conexão indisponível, 401, 403, 404, 409, 422, 429, falha do servidor, redirecionamento, JSON inválido, contrato diferente, capacidade ausente, divergência de empresa/usuário e mudança entre prévia e revalidação. Não são exibidos token, corpo de erro remoto ou exceções de transporte. O cliente não segue redirecionamentos e não repete consultas nem escritas automaticamente. A configuração é carregada sob demanda; não configurar Nexyra não impede os comandos comuns do Atlas.
