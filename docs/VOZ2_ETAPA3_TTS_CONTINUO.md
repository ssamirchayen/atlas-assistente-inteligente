# Voz 2.0 — Etapa 3: TTS contínuo

Objetivo: remover a pausa artificial percebida depois de `.` em respostas longas.

## Estratégia

A síntese deixa de funcionar apenas em série:

`sintetiza A -> toca A -> sintetiza B -> toca B`

e passa a usar prefetch de um trecho:

`sintetiza A -> toca A`
`                 + sintetiza B em background`
`termina A -> toca B`

A ordem continua determinística e não há sobreposição de áudio.

## Novas configurações

- `ATLAS_TTS_PREFETCH=1`
- `ATLAS_TTS_PREFETCH_WORKERS=1`
- `ATLAS_TTS_SENTENCE_PAUSE_MS=90`

O valor de 90 ms preserva uma pausa natural curta entre frases sem introduzir
o atraso de geração do próximo áudio.

## Segurança

A etapa não altera classificação de intenção, Planner ou Executor.
O guard CHAT -> automação permanece intacto.
