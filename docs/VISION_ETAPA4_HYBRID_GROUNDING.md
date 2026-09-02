# Vision Etapa 4 — Grounding híbrido

Para a própria GUI do Atlas, o grounding usa a geometria real do PySide6
antes de recorrer ao modelo multimodal.

Isso elimina a dependência de o Qwen2.5-VL devolver coordenadas para
elementos como o botão Enviar.

Para programas externos, o fluxo visual existente continua como fallback.

A etapa permanece somente leitura: localizar não move mouse e não clica.
