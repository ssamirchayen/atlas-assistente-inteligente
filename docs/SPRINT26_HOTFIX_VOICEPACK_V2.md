# Sprint 26 — Hotfix Voice Pack V2

Este hotfix corrige a regressão introduzida pelo primeiro hotfix do Voice Pack e
resolve o comportamento do TTS neural dentro de uma aplicação congelada pelo
PyInstaller.

## Compatibilidade preservada

O pacote restaura os módulos maduros de voz construídos nas etapas anteriores:
VoiceSession, escuta contínua, interrupção por voz, Edge TTS, perfis de latência,
cache, prefetch, naturalidade, endpointing e normalização ASR.

## Frozen-safe TTS

A síntese neural e o playback não dependem mais de `sys.executable -m ...` no
fluxo de produção. A síntese usa a API Python do `edge_tts` e a reprodução usa
MCI diretamente. Isso é necessário porque `sys.executable` aponta para
`Atlas.exe` numa build PyInstaller.

## Segurança de distribuição

O pacote não contém `.env`, chaves, bancos, logs ou dados pessoais.
