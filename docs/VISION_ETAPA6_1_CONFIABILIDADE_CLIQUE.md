# Atlas Vision — Etapa 6.1: Confiabilidade do Clique

## Problema

Em páginas modernas, o grounding pode encontrar corretamente um elemento,
mas frameworks JavaScript podem recriar o nó DOM antes do clique.

Um índice como `nth(14)` pode deixar de representar o mesmo controle alguns
milissegundos depois.

## Solução

O Atlas agora guarda uma impressão digital do elemento:

- tag;
- role;
- type;
- name;
- aria-label;
- placeholder;
- title;
- texto.

Antes de clicar, ele procura novamente o elemento visível que mais combina
com essa identidade.

Atributos mais estáveis recebem maior peso:

1. `aria-label`;
2. `name`;
3. `placeholder`;
4. `role`;
5. `type`;
6. `tag`.

## Actionability

Antes do clique real, o Playwright executa um `trial=True`. Isso valida se
o elemento está visível e clicável sem realizar a ação.

## Recuperação

Se a primeira tentativa falhar:

1. o Atlas espera brevemente;
2. refaz o grounding completo;
3. exige novamente confiança >= 85%;
4. tenta apenas mais uma vez.

Não existe loop infinito.

## Foco

O Atlas aceita uma pequena janela de tolerância para oscilações transitórias
de foco, mas nunca força o navegador para primeiro plano.

## Segurança preservada

Continua proibido transformar coordenadas do Qwen em clique nesta etapa.
O caminho de ação continua exclusivamente DOM/Playwright.
