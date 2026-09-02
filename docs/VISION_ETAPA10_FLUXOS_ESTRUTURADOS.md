# Atlas Vision — Etapa 10: Fluxos Estruturados Verificados

## Objetivo

A Etapa 10 adiciona duas capacidades ao pipeline híbrido do Atlas Vision:

1. preenchimento estrutural de campos no navegador e no Windows;
2. sequências curtas de 2 a 3 ações, com verificação obrigatória entre passos.

## Preenchimento web

O Atlas localiza o campo pelo DOM/Playwright, exige confiança mínima de 85%,
revalida o fingerprint e usa `locator.fill()`. Campos `type=password` são
bloqueados. Não há fallback para `pyautogui`, teclado físico ou coordenadas.

Exemplo:

```text
Atlas, digite Atlas Vision 10 na barra de pesquisa.
```

## Preenchimento Windows

Quando DOM não se aplica, o Atlas tenta Windows UI Automation. O campo é
revalidado por janela, PID, HWND e fingerprint. O texto só é aplicado quando
o controle expõe um mecanismo estrutural de edição/Value Pattern. Campos de
senha são recusados.

## Sequências verificadas

Exemplo:

```text
Atlas, clique no campo de texto e depois digite Teste Atlas no campo de texto.
```

Regras:

- mínimo de 2 e máximo de 3 passos;
- cada passo passa novamente pelo pipeline normal de grounding, confiança,
  execução e pós-verificação;
- o próximo passo só começa se o anterior foi confirmado;
- falha ou resultado inconclusivo interrompe a cadeia;
- ações sensíveis em sequência são bloqueadas e precisam de comando separado;
- Qwen/Vision continua apenas como fallback de compreensão/localização, nunca
  como executor de escrita por coordenadas.

## Segurança

Sequências bloqueiam termos de compromisso/alto impacto, incluindo envio,
confirmação, salvamento, exclusão, compra, pagamento, transferência e campos
de senha. A Etapa 10 é deliberadamente conservadora: uma cadeia incompleta é
preferível a uma automação que avance sem confirmação.
