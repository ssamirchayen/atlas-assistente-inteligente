# Sprint 26 — Hotfix Voice Pack V3

Este hotfix restaura a versão madura do monitor de interrupção por voz que existia antes do empacotamento final.

## Contrato restaurado

- `detect_voice_interruption(..., allow_without_wake=True)`
- suporte a `Atlas para`
- busca de comando de parada no meio de transcrições/eco
- alternativas em múltiplas linhas
- wake word isolado seguido de comando em outra captura
- `wake_followup_timeout`
- validação de parâmetros do monitor

## Validação local do pacote

O teste histórico `atlas/tests/test_voice_interruption.py` foi executado contra o módulo restaurado e obteve `26 passed`.

O arquivo também foi validado com `compileall`.
