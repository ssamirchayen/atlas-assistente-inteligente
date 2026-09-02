# Atlas Vision — Etapa 6.2: Precisão de Clique em Pesquisa

As expressões:

- campo de pesquisa;
- barra de pesquisa;
- caixa de busca;
- onde eu digito no Google;

agora convergem para a intenção canônica `search_input`.

Para `search_input`, o clique prioriza diretamente elementos DOM como:

1. `role=searchbox`;
2. `name=q`;
3. `type=search`;
4. `textarea`;
5. `combobox`;
6. `textbox`;
7. `input`.

Isso impede que "campo de pesquisa" termine em links ou botões contendo
"Pesquisar".

O clique real continua sendo executado pelo Playwright no elemento DOM.
Logo, tela cheia, resolução e posição X/Y não participam da ação real.
Coordenadas continuam servindo apenas ao overlay.
