# Sprint 25 — Etapa 5: Admin Console

## Objetivo

Disponibilizar uma visão profissional e local do Atlas Core sem criar um
segundo backend. A janela usa o mesmo `AtlasKernel` já utilizado por texto,
voz e GUI.

## Informações exibidas

| Área | Dados públicos |
|---|---|
| Saúde | saudável, atenção, crítico ou indisponível |
| Perfil | solicitado, recomendado, selecionado e suporte |
| Recursos | pressão, CPU, RAM disponível, RSS e capacidade |
| Lazy loading | nome, estado, tentativas e duração agregada |
| Model Router | modelo, tarefa, nível, contexto e motivos |
| Auditoria | totais de admissões, rejeições e liberações |

## Integração com a GUI

O botão **Admin Console** fica no cabeçalho da conversa. A janela é não modal,
atualiza a cada três segundos com `QTimer` e não usa threads externas para
alterar widgets.

## Segurança

- somente leitura;
- nenhuma ação administrativa ou destrutiva;
- nenhuma exposição adicional pela API;
- nenhuma leitura direta do `.env`;
- nenhuma exibição de tokens, chaves, caminhos, prompts ou respostas;
- auditoria apresentada somente em contagens agregadas;
- erros convertidos em códigos públicos;
- consulta do Brain por `peek()`, sem acionar o lazy loading.

## Estado dos componentes

Abrir a console não muda `unloaded` para `ready`. A última decisão do Model
Router só aparece depois que o Brain tiver sido usado normalmente pelo Atlas.

