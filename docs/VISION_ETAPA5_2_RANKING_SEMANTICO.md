# Vision Etapa 5.2 — Ranking Semântico do DOM

## Problema observado

No Google, a frase:

`onde está o campo de pesquisa?`

podia selecionar `Pesquisar imagens`, enquanto:

`onde está a barra de pesquisa?`

selecionava corretamente o campo principal.

O DOM estava correto; o ranking semântico é que tratava todos os elementos
com a palavra "pesquisa" como candidatos semelhantes.

## Correção

Quando a intenção representa uma área de digitação para pesquisa, o ranking
agora favorece fortemente:

- `role=searchbox`;
- `role=textbox`;
- `role=combobox`;
- `input`;
- `textarea`;
- `type=search`;
- `name=q`;
- `aria-label` ou `placeholder` com pesquisa/busca.

E penaliza:

- links;
- botões;
- menus;
- `Pesquisar imagens`;
- pesquisa por voz;
- pesquisa por imagem.

## Resultado esperado

As frases abaixo devem convergir para o mesmo campo principal:

- `onde está o campo de pesquisa?`
- `onde está a barra de pesquisa?`
- `onde está a caixa de busca?`
- `onde eu digito no Google?`

Nenhuma ação é executada. A etapa continua read-only.
