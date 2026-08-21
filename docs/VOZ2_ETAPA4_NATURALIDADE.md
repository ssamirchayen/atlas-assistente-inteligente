# Voz 2.0 — Etapa 4: Naturalidade

A etapa melhora a fala sem alterar o roteamento de comandos.

## Mudanças

- remove Markdown e URLs da versão falada;
- mantém o texto visual intacto na interface;
- segmenta frases longas por cláusulas naturais;
- adiciona pausas curtas de prosódia;
- efetiva o prefetch de TTS: o próximo trecho é sintetizado em background;
- preserva cache, interrupção e fallback do Windows.

## Segurança

Esta etapa não altera `IntentAnalyzer`, `Planner` nem `Executor`.
A correção CHAT -> automação permanece separada e não é sobrescrita.

## Configuração

- `ATLAS_TTS_PREFETCH=1`
- `ATLAS_TTS_PREFETCH_WORKERS=1`
- `ATLAS_TTS_SENTENCE_PAUSE_MS=90`

Os padrões internos já habilitam as opções.
