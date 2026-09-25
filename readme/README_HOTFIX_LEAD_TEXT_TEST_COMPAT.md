# Hotfix — mensagem de erro compatível com teste antigo

Corrige a regressão onde o fluxo `resuma esse lead` sem lead aberto retornava uma mensagem válida, mas sem o trecho exato esperado pelo teste: `Nenhum lead aberto`.

## Arquivo alterado

- `atlas/copilot/business_lab.py`

## Comportamento esperado

- `Atlas, resuma essa tela` funciona em telas gerais como dashboard e lista de leads.
- `Atlas, resuma esse lead` continua exigindo um lead aberto ou `lead_code`.
