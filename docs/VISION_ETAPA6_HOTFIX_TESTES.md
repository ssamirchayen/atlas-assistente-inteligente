# Etapa 6 — Hotfix de compatibilidade dos testes

Este patch não altera a lógica de clique.

Ele resolve duas incompatibilidades da suíte:

1. testes históricos esperam um marcador `# INTERAÇÃO` depois do método
   `click_interactive_element()`;
2. o teste novo do hotfix procurava `\n` como texto literal em vez de validar
   a estrutura real do arquivo.

A segurança continua igual:

- clique apenas via DOM;
- página precisa estar em foco;
- elemento precisa estar visível;
- confiança mínima de 85%;
- Qwen/Vision não gera clique por coordenadas.
