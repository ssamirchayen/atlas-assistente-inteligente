# Sprint 26 — Hotfix Voice Pack no EXE/Instalador

## Problema
A build instalada estava usando o TTS legado do Windows (`System.Speech`), produzindo a voz robótica antiga.

## Restauração
- Edge TTS neural como provedor oficial.
- Voz padrão `pt-BR-AntonioNeural`.
- Perfil `fast`: pausa final 0,9 s, calibração 0,5 s, timeout de escuta 6 s.
- Pipeline em trechos com pré-síntese do próximo trecho em background.
- Reprodução MP3 nativa pelo Windows MCI, sem janela externa.
- Suporte a interrupção e sessão/latência do Voice Pack.
- PyInstaller coleta explicitamente `edge_tts` e certificados.
- Build executa `Atlas.exe --voice-selftest` antes de criar o instalador.

## Critério de aceite
A mesma voz neural deve ser ouvida ao executar pelo Python, pelo `dist/Atlas/Atlas.exe` e depois de instalar o `AtlasCoreSetup-1.0.0.exe`.
