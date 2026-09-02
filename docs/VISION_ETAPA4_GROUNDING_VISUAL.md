# Atlas Vision — Etapa 4: Grounding visual

## Objetivo

Permitir que o Atlas responda onde está um elemento visual.

Exemplos:

- "Atlas, onde está o botão Enviar?"
- "Atlas, localize o campo de mensagem."
- "Atlas, encontre o menu na tela."

## Como funciona

Tela
→ Qwen2.5-VL
→ elementos visuais + bounding boxes
→ ranking do alvo pedido
→ conversão da caixa normalizada para pixels
→ resposta textual/voz

O modelo retorna coordenadas normalizadas entre 0 e 1000. O Atlas converte
essas coordenadas para a resolução real da captura.

## Segurança

Esta etapa continua read-only.

O Atlas pode localizar e descrever a posição, mas ainda NÃO move o mouse,
NÃO clica e NÃO digita.

Comandos de ação continuam fora deste fluxo.

## Próxima etapa

Etapa 5: overlay visual e validação de grounding antes de qualquer
automação visual controlada.
