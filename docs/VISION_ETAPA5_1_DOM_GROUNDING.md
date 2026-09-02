# Vision Etapa 5.1 — DOM Grounding

O overlay revelou que o VLM consegue reconhecer elementos do Google,
mas pode errar a posição.

Para páginas controladas pelo navegador Playwright do Atlas, o fluxo
agora é:

1. Grounding da própria GUI do Atlas;
2. grounding pelo DOM da página em foco;
3. Vision/Qwen somente como fallback.

O DOM fornece o retângulo real do elemento na página. O Atlas converte
a geometria da viewport para coordenadas da tela considerando posição
da janela, chrome do navegador e `devicePixelRatio`.

O método é somente leitura nesta etapa.

Uma janela comum do Chrome aberta fora da sessão Playwright do Atlas
continua sem DOM disponível e usa Vision como fallback.
