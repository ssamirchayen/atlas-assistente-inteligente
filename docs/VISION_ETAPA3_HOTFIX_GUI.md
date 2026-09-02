# Vision Etapa 3 — Hotfix da GUI

## Causa

`gui_main.py` instancia `AtlasWindow`, que envia comandos para
`AtlasGuiService.execute()`.

A primeira integração da Etapa 3 foi adicionada em `AtlasApp.run()`, usada
pelo modo principal, mas a GUI possui um pipeline próprio. Por isso a frase
"o que você está vendo" ainda chegava ao Controller/Planner quando o Atlas
era aberto pela interface gráfica.

## Correção

`AtlasGuiService.execute()` agora consulta o detector Vision imediatamente
após o roteamento prioritário e **antes** de `controller.execute()`.

Fluxo da GUI:

voz/texto
→ AtlasGuiService
→ Vision read-only
→ captura
→ Qwen2.5-VL
→ `GuiCommandResult(source="vision")`
→ interface
→ Voz 2.0

Se não for consulta visual read-only, o pipeline continua normalmente para
Controller/Planner.

## Testes de regressão

- consulta visual não chama Controller;
- comando visual de ação não é absorvido pelo Vision read-only.
