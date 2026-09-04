# Sprint 25 — Etapa 4: Model Router

## Objetivo

Selecionar o modelo local do Ollama de forma previsível, considerando:

- perfil ativo (`lite`, `standard` ou `full`);
- classe da tarefa (`chat`, `planning`, `coding` ou `analysis`);
- modelos realmente disponíveis no Ollama;
- RAM total e disponível;
- VRAM, quando a métrica estiver disponível;
- pressão atual informada pelo Resource Manager;
- limite de contexto do perfil.

## Comportamento padrão

Nenhum modelo novo é presumido ou baixado. `ATLAS_MODEL=atlas` continua sendo
o fallback e também é o padrão dos três níveis. Isso preserva instalações já
funcionais.

Modelos diferentes podem ser ativados depois de instalados e validados:

```env
ATLAS_MODEL_LITE=atlas
ATLAS_MODEL_STANDARD=atlas
ATLAS_MODEL_FULL=atlas
```

## Política de seleção

| Perfil | Conversa | Planejamento/código/análise |
|---|---|---|
| Lite | Lite | Lite |
| Standard | Balanceado | Balanceado |
| Full | Balanceado | Grande |

Sob pressão de recursos:

- `warning`: uma solicitação grande é reduzida para balanceada;
- `critical`: qualquer solicitação é reduzida para lite.

O candidato também precisa respeitar o hardware e constar no inventário local.
Quando o inventário não pode ser consultado, o roteador não adivinha modelos:
usa o `ATLAS_MODEL` já configurado.

## Integração

O Model Router nasce dentro da factory lazy do Brain. Portanto, inicializar o
Kernel não consulta o Ollama nem carrega um modelo. A consulta de inventário
ocorre somente no primeiro uso real do Brain e é reutilizada em memória.

Cada requisição envia ao Ollama:

- o modelo decidido;
- `num_ctx` limitado pelo perfil e pelo candidato;
- o mesmo histórico e prompt já usados pelo Atlas.

## Privacidade e segurança

- não armazena prompts, respostas ou conteúdo de memória nas decisões;
- não executa downloads ou comandos de terminal;
- aceita apenas nomes de modelo com formato restrito;
- falhas do inventário são reduzidas a códigos públicos;
- não enumera processos nem coleta identidade do computador;
- mantém apenas a última decisão técnica em memória.

