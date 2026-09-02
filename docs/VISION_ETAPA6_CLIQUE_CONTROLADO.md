# Atlas Vision — Etapa 6: Clique Controlado

## Escopo inicial

A primeira versão de ação visual permite um único clique explícito em um
elemento confirmado pelo DOM do navegador controlado pelo Atlas.

Exemplos:

- `Atlas, clique no campo de pesquisa`
- `Atlas, clique em Imagens`
- `Atlas, pressione o botão Entrar`

## Regras de segurança

O clique somente ocorre quando:

1. o usuário pediu explicitamente um clique;
2. existe apenas uma ação no comando;
3. o navegador Playwright do Atlas está em foco;
4. o elemento continua visível;
5. o elemento foi identificado pelo DOM;
6. a confiança do ranking é de pelo menos 85%.

Se qualquer regra falhar, nenhuma ação é executada.

## O que ainda NÃO clica

Nesta etapa, o Atlas não transforma coordenadas produzidas pelo Qwen/Vision
em clique. O Vision continua sendo excelente fallback de percepção, mas uma
posição visual incerta não deve virar uma ação real.

Também não executamos clique na GUI Qt do próprio Atlas nesta versão.

## Por que usar DOM

O DOM oferece identidade e estado reais do elemento. O Atlas guarda o índice
do elemento na mesma NodeList usada no grounding e, imediatamente antes da
ação, confirma que:

- a página continua com foco;
- o elemento ainda existe;
- o elemento ainda está visível.

Então o Playwright executa o clique diretamente no elemento, sem depender
de coordenadas do mouse.

## Próximos incrementos

Depois de validar esta etapa:

1. verificação pós-clique;
2. Windows UI Automation;
3. clique visual com confirmação e confiança alta como último fallback.
