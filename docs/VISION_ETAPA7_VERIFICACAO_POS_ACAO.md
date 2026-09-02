# Atlas Vision — Etapa 7: Verificação Pós-Ação

## Objetivo

A Etapa 7 adiciona uma camada de confirmação depois do clique DOM controlado.
O Atlas deixa de considerar o retorno do Playwright, sozinho, como prova final de
sucesso. Ele compara o estado da interface antes e depois da ação e só confirma
sucesso quando encontra evidência observável.

## Fluxo

```text
Comando explícito de clique
        ↓
Grounding DOM >= 85%
        ↓
Snapshot pré-ação (somente leitura)
        ↓
Clique DOM revalidado
        ↓
Snapshot(s) pós-ação (somente leitura)
        ↓
Verificador pós-ação
        ↓
VERIFICADO ou INCONCLUSIVO
```

## Evidências aceitas nesta etapa

- mudança de URL/navegação;
- foco confirmado no campo alvo;
- mudança de estado `checked`;
- mudança de `aria-pressed`, `aria-expanded` ou `aria-selected`;
- abertura/fechamento de diálogo;
- mudança global de estado expandido;
- mudança do título da página;
- substituição do alvo acompanhada de mudança estrutural da UI.

Para `search_input`/`text_input`, o foco do campo é tratado como a pós-condição
esperada. Isso permite validar de forma confiável comandos como "clique na barra
de pesquisa".

## Regra de segurança

Se o clique foi enviado, mas a mudança não pode ser confirmada, o Atlas retorna
o resultado como inconclusivo e **não repete o clique**. Isso evita ações
duplicadas em botões de compra, envio, confirmação ou outros controles com
efeito não idempotente.

A Etapa 7 continua sem autorizar cliques por coordenadas produzidas pelo modelo
visual. A execução continua restrita ao DOM/Playwright controlado e revalidado.

## Arquivos principais

- `atlas/vision/post_action.py`
- `atlas/automation/browser.py`
- `atlas/gui/service.py`
- `atlas/tests/test_vision_post_action.py`
- `atlas/tests/test_vision_post_action_structure.py`
- `validation/scenarios/vision.json`

## Teste manual recomendado

1. Feche totalmente o Atlas e abra novamente.
2. Abra o Google usando o navegador controlado pelo Atlas.
3. Diga: `Atlas, clique na barra de pesquisa.`
4. O Atlas deve localizar o campo via DOM, clicar e confirmar que o campo está
   com foco após a ação.
5. A resposta esperada contém uma confirmação semelhante a:

```text
Cliquei em ... pelo DOM com ... de confiança e confirmei o resultado:
o elemento alvo está com foco após o clique.
```

Também teste um botão/link conhecido. Se a página navegar, abrir um diálogo ou
alterar um estado observável, a ação deve ser confirmada. Se nenhuma evidência
for detectável, o Atlas deve informar que a ação ficou inconclusiva e não deve
clicar novamente.
