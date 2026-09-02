# Vision Etapa 6 — Hotfix de Integração

Este hotfix corrige duas regressões encontradas pela suíte completa.

## 1. Compatibilidade com testes/fakes históricos

Testes antigos da GUI usam um `FakeVision` que possui apenas
`observe_screen()`. A Etapa 6 assumia que qualquer kernel tinha
`vision.capture_service` e `automation.browser`.

Agora o clique DOM só é interceptado quando o runtime realmente possui:

- `capture_primary_screen`;
- `inspect_visible_interactive_elements`;
- `click_interactive_element`.

Sem esses recursos, o comando continua pelo pipeline histórico normal.

## 2. Separação leitura x interação

O método `inspect_visible_interactive_elements()` continua estritamente
read-only.

`click_interactive_element()` agora fica fisicamente na seção `INTERAÇÃO`
da classe `BrowserAutomation`. Isso preserva a garantia estrutural dos
testes anteriores.

## Segurança

Nada foi relaxado:

- clique somente via DOM;
- navegador precisa estar em foco;
- elemento precisa estar visível;
- confiança mínima continua 85%;
- nenhuma coordenada do Qwen vira clique.
