# Atlas Vision — Etapa 5: Overlay e Validação Visual

## Objetivo

Transformar o grounding em uma validação visual observável antes de
permitir qualquer ação de mouse.

Quando o Atlas localiza um elemento, a GUI recebe uma especificação
read-only com a bounding box normalizada. A thread principal do Qt
desenha por alguns segundos:

- contorno do elemento;
- ponto central;
- nome do alvo;
- confiança do grounding, quando disponível.

## Segurança

O overlay:

- não move o mouse;
- não clica;
- não recebe eventos de mouse;
- não ativa a janela;
- desaparece automaticamente;
- é ocultado antes do próximo comando.

## Apps externos

O grounding de widgets PySide6 da própria interface do Atlas agora
só é considerado quando o Atlas é a aplicação ativa.

Se Chrome, VS Code, Bloco de Notas ou outro aplicativo estiver em
primeiro plano, o fluxo cai no Atlas Vision em vez de confundir o
elemento externo com um widget da própria GUI.

## DPI / escala do Windows

O overlay preserva coordenadas normalizadas 0..1000 e só converte para
o tamanho lógico da tela no momento da renderização. Isso reduz erros
causados por escala de 125%, 150% etc.
