# Atlas Vision — Etapa 11: Formulários Contextuais

## Objetivo

Permitir o preenchimento explícito de múltiplos campos sem perder o contexto
estrutural entre os passos. O Atlas continua sem submeter, salvar ou confirmar
o formulário automaticamente.

## Fluxo

```text
comando explícito com 2–5 campos
        ↓
parser de formulário
        ↓
campo 1: grounding + confiança >= 85% + fill + verificação
        ↓
vincula contexto (aba DOM ou janela UIA)
        ↓
campo 2..N: re-grounding no MESMO contexto + fill + verificação
        ↓
resumo final
        ↓
SEM submit / salvar / confirmar
```

## Exemplos

```text
Atlas, preencha o formulário com nome: Ssamir; cidade: Manaus; email: teste@atlas.local
```

ou:

```text
Atlas, preencha o campo nome com Ssamir e o campo cidade com Manaus
```

## Proteções

- máximo de cinco campos por comando;
- cada campo é revalidado e confirmado individualmente;
- confiança estrutural mínima de 85%;
- o formulário para na primeira falha;
- a aba/janela deve permanecer a mesma durante toda a operação;
- campos de senha, PIN, token, CVV/cartão e equivalentes são bloqueados;
- campos identificados estruturalmente como senha continuam bloqueados;
- não existe `submit`, clique final, teclado físico ou fallback por coordenadas;
- Vision/Qwen não executa escrita.

## Laboratório local

O patch inclui `tools/vision_form_lab.html`, uma página local com Nome, Cidade e
Email. O botão de envio é desabilitado de propósito.

Uma forma simples de servir a página:

```powershell
cd C:\Atlas_OFICIAL
C:\Atlas_OFICIAL\.venv\Scripts\python.exe -m http.server 8765
```

No navegador controlado pelo Atlas, abrir:

```text
http://127.0.0.1:8765/tools/vision_form_lab.html
```

Teste sugerido:

```text
Atlas, preencha o formulário com nome: Ssamir; cidade: Manaus; email: teste@atlas.local
```

Resultado esperado: três campos confirmados no mesmo contexto e nenhuma ação
de envio.
