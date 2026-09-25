# Sprint 27 — Etapa 4 — Voice Benchmark

Esta etapa adiciona a suíte técnica `voice` ao Atlas Benchmark & Validation Lab.

## O que é medido automaticamente

- imports do stack de voz;
- disponibilidade de `edge_tts`, `speech_recognition` e `pyaudio`;
- configuração do Voice Pack neural;
- reparo/normalização de comandos vindos do ASR;
- detecção de intenções de interrupção;
- transições da `VoiceSession` e telemetria de latência;
- divisão de respostas em blocos de TTS;
- síntese neural real via Edge TTS quando `--live` é usado.

## Limite metodológico

A suíte não chama precisão acústica de STT ou latência física de interrupção de
"medida" sem áudio controlado. Esses indicadores serão adicionados com fixtures
de áudio ou protocolo manual do Validation Lab, evitando números artificiais.

## Execução

```powershell
.\.venv\Scripts\python.exe tools\run_atlas_benchmark.py run voice --version 1.0.0
```

Para habilitar a síntese neural real:

```powershell
.\.venv\Scripts\python.exe tools\run_atlas_benchmark.py run voice --version 1.0.0 --live
```

O caso `voice.neural_synthesis` gera o MP3 somente no workspace temporário do
benchmark e mede a duração pelo runner. O arquivo é descartado ao final.
