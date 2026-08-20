# Sprint 21 — Memória Operacional e Continuidade

## Objetivo

Permitir que o Atlas mantenha o estado do trabalho entre reinicializações,
distinguindo o histórico da conversa do estado operacional necessário para
continuar uma tarefa.

## Etapas

1. **Sessões persistentes**: identidade, estado, contexto, migração do JSON e
   armazenamento SQLite.
2. **Linha do tempo operacional**: comandos, etapas, resultados e falhas
   vinculados à sessão.
3. **Contexto de continuidade**: resumo compacto e relevante para o Planner e
   para o cérebro local.
4. **Retomada segura**: detectar interrupções, decidir o ponto retomável e
   impedir repetição indevida de ações.
5. **Operação e observabilidade**: histórico na API/GUI, documentação, testes
   de integração e encerramento da sprint.

## Etapa 1

A primeira etapa introduz o banco local `data/operational_sessions.db` e mantém
o `data/last_session.json` como espelho temporário de compatibilidade.

Cada sessão possui:

- identificador UUID;
- usuário e título;
- estado (`active`, `paused`, `completed`, `failed` ou `cancelled`);
- datas UTC de criação, atualização e encerramento;
- contexto operacional já usado pelo Atlas.

O `SessionManager` preserva os métodos existentes e adiciona operações para
listar, iniciar, pausar, retomar, concluir, falhar e cancelar sessões. Um JSON
existente é migrado automaticamente na primeira inicialização.

Esta etapa não tenta retomar automaticamente uma ação externa. Essa decisão só
será habilitada na Etapa 4, quando houver uma linha do tempo operacional capaz
de diferenciar ações concluídas, seguras para repetição e interrompidas.

## Etapa 2

A segunda etapa adiciona a tabela `operational_events` ao mesmo banco SQLite.
Cada evento possui:

- identificador UUID;
- sessão proprietária e sequência crescente;
- tipo e horário UTC;
- identificador de correlação do workflow;
- tipo da ação, mensagem e detalhes estruturados.

O `AtlasController` registra automaticamente:

- comando recebido ou não compreendido;
- tarefa agendada;
- início e encerramento do workflow;
- resultado de cada etapa;
- falhas, cancelamentos, duração e tentativas.

Início, pausa, retomada e encerramento de sessões também entram na linha do
tempo. Os eventos são gravados de forma transacional, isolados por usuário e
continuam disponíveis depois que o Atlas é reiniciado.

Exemplo de consulta interna:

```python
events = session_manager.get_timeline(limit=100)

for event in events:
    print(event.sequence, event.event_type, event.message)
```

Leituras incrementais podem usar `after_sequence`, permitindo que uma futura
tela carregue apenas os eventos novos. A exposição na API e na interface será
feita na Etapa 5. A Etapa 3 usará essa linha do tempo para construir um resumo
compacto de continuidade, sem reenviar todo o histórico ao modelo.

## Etapa 3

A terceira etapa transforma a sessão e a linha do tempo em um snapshot pequeno
e estruturado de continuidade. O novo `ContinuityContextBuilder` seleciona:

- projeto, tarefa, último comando, arquivo e janela atuais;
- apenas os cinco arquivos, abas e anotações mais recentes;
- últimas ações e resultados operacionais relevantes;
- falha mais recente;
- workflow iniciado que ainda não possui evento de encerramento.

O snapshot pode ser consumido como dicionário por componentes internos ou como
texto delimitado pelo método `to_prompt()`. A versão textual possui limite
rígido de tamanho, normaliza espaços, reduz mensagens extensas e informa ao
modelo que o conteúdo é somente dado de contexto, nunca uma ordem para executar
ou repetir uma ação anterior.

O `ContextManager` disponibiliza o snapshot estruturado em
`operational_continuity` e usa a versão compacta ao montar o prompt. Como o
`Planner` e o `OllamaBrain` já dependem do mesmo `ContextManager`, ambos passam
a receber a continuidade sem criar fontes de estado paralelas.

Exemplo de consulta interna:

```python
snapshot = session_manager.get_continuity_context()
prompt_context = snapshot.to_prompt(max_chars=6000)
```

Nesta etapa, um workflow sem encerramento é apenas identificado como
interrompido. Ele não é retomado nem repetido automaticamente. A decisão de um
ponto retomável e a confirmação das ações pertencem à Etapa 4.

## Etapa 4

A quarta etapa adiciona a retomada segura de workflows interrompidos. O evento
de início agora armazena a versão do plano e as ações necessárias para sua
reconstrução. Cada resultado de etapa também registra `step_index` e
`step_number`, permitindo diferenciar com precisão o que terminou do que ainda
estava pendente quando o processo foi encerrado.

O novo `WorkflowResumptionPlanner` analisa somente dados persistidos e produz
um `ResumptionPlan` imutável. Ele não executa ações. A decisão pode ser:

- `ready`: todas as etapas restantes são locais e reversíveis;
- `confirmation_required`: existe alteração possível de navegador, arquivos,
  processos, janelas ou outro estado externo;
- `blocked`: o plano contém exclusão, encerramento, entrada opaca ou dado
  sensível que não pode ser repetido com segurança;
- `not_available`: não existe workflow interrompido.

Ações já registradas como concluídas nunca entram no novo plano. O token de
confirmação é determinístico para o mesmo ponto de interrupção, mas muda quando
o plano ou as etapas concluídas mudam. Uma confirmação incorreta não executa
nada. Após a retomada ser aceita, o workflow original recebe o evento
`workflow.resumed` e deixa de ser candidato, impedindo uma segunda execução do
mesmo plano.

Parâmetros chamados `password`, `token`, `api_key`, `secret`, `cookie` e
equivalentes são substituídos por `[ATLAS_REDACTED]` antes de entrar na linha
do tempo. Como o valor original não é guardado, qualquer etapa que dependia
dele é bloqueada e deve ser recriada pelo usuário.

Exemplo de uso interno:

```python
plan = controller.get_resumption_plan()

if plan.requires_confirmation:
    actions, results = controller.resume_interrupted_workflow(
        confirmation_token=plan.confirmation_token,
    )
else:
    actions, results = controller.resume_interrupted_workflow()
```

A exposição do plano, da confirmação e dos eventos na API e na interface será
concluída na Etapa 5. Nenhuma retomada é disparada automaticamente durante a
inicialização do Atlas.

## Etapa 5

A quinta etapa conclui a Sprint 21 expondo a memória operacional para uso e
diagnóstico, sem permitir que uma consulta dispare ações silenciosamente.

### API local

Os novos endpoints autenticados são:

| Método | Endpoint | Finalidade | Escopo |
| --- | --- | --- | --- |
| `GET` | `/api/v1/sessions` | Lista sessões operacionais | `sessions:read` |
| `GET` | `/api/v1/sessions/{id}/timeline` | Consulta eventos cronológicos | `sessions:read` |
| `GET` | `/api/v1/resumption` | Inspeciona o plano de retomada | `sessions:read` |
| `POST` | `/api/v1/resumption` | Confirma e executa etapas pendentes | `workflows:resume` |

As consultas aceitam limites rígidos e a linha do tempo suporta
`after_sequence` para atualização incremental. O endpoint de retomada recebe
somente o token do plano atual, registra a solicitação na auditoria e passa a
execução pelo mesmo runtime serial usado pelos comandos. Isso preserva a
afinidade de thread do navegador e impede duas automações simultâneas.

As chaves de monitoramento continuam limitadas ao estado básico. Histórico,
detalhes de sessão e retomada exigem a chave administrativa, pois podem revelar
metadados operacionais ou alterar sistemas externos.

### Interface gráfica

O cabeçalho da conversa ganhou dois controles:

- **Histórico**: mostra os eventos recentes da sessão, com sequência e tipo;
- **Retomar pendência**: aparece habilitado somente quando existe um plano
  retomável.

Quando o plano contém qualquer ação que possa alterar estado externo, a GUI
exibe uma confirmação explícita antes de enviar o token. Ações concluídas não
são repetidas e planos bloqueados apenas mostram o motivo ao usuário.

### Garantias de encerramento

- nenhuma ação é retomada automaticamente ao iniciar o Atlas;
- a API e a GUI usam o mesmo `SessionManager` e o mesmo Controller;
- consultas não criam uma segunda fonte de estado;
- execução e retomada compartilham a thread operacional serial;
- tokens e parâmetros sensíveis permanecem sanitizados na linha do tempo;
- sessões, eventos e planos possuem contratos e testes de integração;
- o projeto completo é validado por Pytest e Ruff antes do fechamento.

Com esta etapa, a Sprint 21 fica concluída: o Atlas persiste a sessão, registra
o que ocorreu, reconstrói contexto, detecta trabalho interrompido e oferece uma
retomada explícita, auditável e segura pela API ou pela interface.
