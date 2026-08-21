# Sprint 23 — Voz 2.0 e velocidade

## Etapa 1 — Perfil de desempenho e telemetria

A primeira etapa cria uma linha de base mensurável antes das otimizações de
reconhecimento e síntese. O Atlas passa a ter perfis declarativos e um rastreador
local para o ciclo completo:

```mermaid
flowchart LR
    L[Escutando] --> P[Processando]
    P --> S[Falando]
    S --> I[Concluído]
```

O `VoiceLatencyTracker` calcula o tempo de cada estado usando relógio monotônico.
Ele mantém no máximo 50 ciclos em memória e registra somente duração, resultado
e presença de reconhecimento. Transcrição, resposta, motivo completo e áudio
não entram nas métricas.

## Perfis

| Perfil | Uso recomendado | Pausa final | Calibração | Timeout |
| --- | --- | ---: | ---: | ---: |
| `balanced` | comportamento compatível atual | 1,70 s | 1,00 s | 10 s |
| `fast` | resposta curta e ambiente controlado | 0,90 s | 0,50 s | 6 s |
| `accurate` | fala pausada ou ambiente mais difícil | 2,00 s | 1,50 s | 12 s |

O padrão continua sendo `balanced`, portanto instalar esta etapa não muda o
ritmo atual. Para ativar o perfil rápido, altere somente o `.env` local:

```text
ATLAS_VOICE_PROFILE=fast
```

Reinicie o Atlas depois da alteração. Se ele começar a encerrar a frase antes
de você terminar, use novamente `balanced` ou escolha `accurate`.

## Acesso às métricas

Durante a execução, o snapshot pode ser consultado internamente por:

```python
kernel.speech.performance_snapshot()
```

Exemplo de estrutura:

```json
{
  "profile": "fast",
  "cycles": 3,
  "completed": 3,
  "interrupted": 0,
  "errors": 0,
  "average_total_ms": 2840.5,
  "maximum_total_ms": 3310.2
}
```

Os valores serão aproveitados nas próximas etapas para comparar reconhecimento,
resposta do modelo e síntese sem depender de impressão subjetiva.

## Limite desta etapa

Esta etapa reduz janelas de espera quando o perfil `fast` é escolhido, mas ainda
não troca o motor de reconhecimento nem faz streaming de áudio. Naturalidade da
voz, cache de síntese, início antecipado da reprodução e resposta instantânea
serão tratados nas próximas etapas da Sprint 23.

## Etapa 2 — início antecipado e cache de síntese

A segunda etapa reduz a percepção de espera do TTS neural sem trocar o provedor.
Respostas longas agora são divididas em blocos naturais. O primeiro bloco é
sintetizado e reproduzido antes de o Atlas precisar gerar um MP3 único para a
resposta inteira.

O Edge TTS também ganhou um cache local limitado. Frases já sintetizadas com a
mesma voz, velocidade, volume e pitch reutilizam o áudio existente. Os nomes dos
arquivos são hashes SHA-256 e não contêm a resposta em texto claro.

Configuração:

```text
ATLAS_TTS_CACHE=1
ATLAS_TTS_CACHE_MAX_ENTRIES=64
ATLAS_TTS_CHUNK_MAX_CHARS=260
```

O cache fica em `data/voice_cache/`, portanto permanece local e fora do Git. O
limite é aplicado por LRU aproximado; as entradas menos recentes são removidas
quando o máximo é excedido.

### Ganho esperado

- respostas longas começam a falar mais cedo;
- respostas repetidas deixam de aguardar nova síntese online;
- interrupção continua funcionando entre blocos;
- falha do Edge TTS continua usando o fallback do Windows.

Esta etapa ainda não implementa streaming de áudio em tempo real. Streaming será
uma evolução separada porque exige controlar reprodução e síntese simultâneas
sem enfraquecer o mecanismo atual de interrupção.
