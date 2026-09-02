# Atlas Vision — Etapa 3: diálogo + Voz 2.0

## Objetivo

Transformar Vision em uma capacidade nativa do Atlas.

Perguntas visuais read-only agora entram no ciclo principal antes de
Planner e ReasoningEngine:

comando de voz/texto
→ detector Vision
→ captura
→ Qwen2.5-VL
→ resposta estruturada
→ interface/conversa
→ Voz 2.0

## Exemplos

- "Atlas, o que você está vendo?"
- "Atlas, o que tem nessa tela?"
- "Atlas, tem algum erro nessa tela?"
- "Atlas, qual programa está aberto?"
- "Atlas, o que está escrito aqui?"
- "Atlas, descreva minha tela."

## Guard de segurança

A Etapa 3 reconhece apenas consultas visuais.

Frases com ações como clicar, abrir, digitar, pressionar, fechar, arrastar
ou executar NÃO entram no Vision read-only. Elas continuam seguindo o
pipeline normal e suas proteções.

Isso evita transformar uma descrição visual em automação acidental.

## Teste

Depois de Pytest/Ruff, execute o Atlas normalmente e fale:

`Atlas, o que você está vendo?`

O Atlas deve capturar a tela naquele momento, interpretar localmente e
responder usando a Voz 2.0.

## Próxima etapa

Etapa 4: grounding visual — localizar elementos da interface com
coordenadas/caixas, ainda sem clicar automaticamente.
