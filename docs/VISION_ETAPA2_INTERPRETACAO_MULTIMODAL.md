# Atlas Vision — Etapa 2: Interpretação multimodal

## Objetivo

Fazer o Atlas interpretar a captura da tela com um modelo multimodal local
do Ollama, sem permitir que essa interpretação execute ações.

## Arquitetura

Tela
→ `ScreenCaptureService`
→ PNG temporário
→ `OllamaVisionAnalyzer`
→ JSON estruturado
→ `VisionAnalysis`
→ resposta para o usuário

## Modelo

O padrão configurado é:

`qwen2.5vl:3b`

Ele pode ser trocado pelo `.env`:

`ATLAS_VISION_MODEL=outro-modelo-multimodal`

Antes do primeiro uso:

```powershell
ollama pull qwen2.5vl:3b
```

## Privacidade

A imagem é enviada somente ao Ollama local configurado em `OLLAMA_URL`.
Por padrão, a captura é apagada depois da análise:

`ATLAS_VISION_KEEP_CAPTURES=0`

## Segurança

A Etapa 2 é **read-only**:

- não clica;
- não digita;
- não abre programas;
- não envia a interpretação ao Executor;
- não cria ações automaticamente.

## Teste manual

```powershell
C:\Atlas_OFICIAL\.venv\Scripts\python.exe vision_understand_pilot.py
```

O Atlas deverá descrever a janela atual, listar textos relevantes e destacar
erros que estejam claramente visíveis.

## Próxima etapa

Etapa 3: integração de Vision com o diálogo do Atlas, permitindo comandos
como:

- "Atlas, o que você está vendo?"
- "Atlas, tem algum erro nessa tela?"
- "Atlas, qual programa está aberto?"

A integração continuará read-only antes de qualquer futura automação visual.
