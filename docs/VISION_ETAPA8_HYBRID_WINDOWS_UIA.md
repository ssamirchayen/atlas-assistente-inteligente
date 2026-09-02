# Atlas Vision — Etapa 8: Estratégia Híbrida + Windows UI Automation

## Objetivo

Adicionar uma camada estrutural para aplicações Windows fora do navegador,
mantendo o Vision visual como fallback de observação e nunca como fonte de
coordenadas autorizada para ações.

## Ordem de grounding

```text
PySide6 / própria GUI do Atlas
        ↓
DOM / Playwright
        ↓
Windows UI Automation (UIA)
        ↓
Vision / Qwen (fallback read-only)
```

## Ordem de ação controlada

```text
DOM / Playwright
        ↓ (se não houver alvo DOM)
Windows UI Automation
        ↓
SEM fallback para clique visual
```

## Segurança da camada UIA

- somente a aplicação externa em primeiro plano é inspecionada;
- o processo do próprio Atlas é excluído;
- confiança mínima de 85% para ação;
- o elemento é re-resolvido por fingerprint imediatamente antes da ação;
- processo/janela ativa são revalidados;
- controles invisíveis ou desabilitados são rejeitados;
- ações usam padrões UIA (`Invoke`, `Toggle`, `SelectionItem`, `SetFocus`);
- não há `pyautogui.click`, `click_input` ou clique por bbox;
- Qwen/Vision continua proibido como fallback de ação;
- o pós-estado é observado sem repetir uma ação já enviada.

## Dependência Windows

```powershell
C:\Atlas_OFICIAL\.venv\Scripts\python.exe -m pip install pywinauto>=0.6.9
```

A dependência também foi incluída em `requirements.txt` apenas para Windows.

## Teste recomendado — grounding

1. Feche e abra o Atlas após instalar o patch/dependência.
2. Abra o Bloco de Notas.
3. Deixe o Bloco de Notas em primeiro plano.
4. Use **microfone/escuta contínua**, para que a aplicação alvo continue ativa.
5. Diga:

```text
Atlas, onde está o campo de texto?
```

Esperado: o Atlas deve localizar o controle pelo Windows UI Automation e
exibir o overlay na geometria real do controle.

## Teste recomendado — ação controlada

Use uma aplicação de teste e uma ação não destrutiva. Com a aplicação em
primeiro plano, diga por voz:

```text
Atlas, clique no campo de texto.
```

Para um campo de edição, a ação UIA segura é `SetFocus`. Para botões/controles
compatíveis, o Atlas tenta os padrões estruturais suportados pela UIA. Se o
controle não expuser um padrão seguro, a ação é recusada.

## Observação importante

Ao digitar o comando dentro da GUI do Atlas, a própria GUI pode se tornar a
janela em primeiro plano. Para validar UIA nesta etapa, prefira voz/escuta
contínua com o aplicativo externo ativo. Essa restrição é proposital e reduz o
risco de atuar na janela errada.
