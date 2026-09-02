# Atlas Vision — Etapa 13: Controles de Estado

## Objetivo

A Etapa 13 permite marcar e desmarcar checkboxes, ativar switches e selecionar
radio buttons por interfaces estruturais. O DOM usa `set_checked`; aplicativos
Windows continuam usando os padrões de Toggle/Selection do UI Automation.

## Garantias

- confiança estrutural mínima de 85%;
- pós-verificação obrigatória pelo estado `checked/selected`;
- operação idempotente quando o estado já está satisfeito;
- radio buttons não podem ser desmarcados isoladamente;
- sem `pyautogui`, coordenadas, bbox do modelo ou teclado físico;
- termos de compra, pagamento, exclusão, envio e publicação são bloqueados.

## Exemplos

```text
Atlas, marque a caixa de seleção receber novidades
Atlas, desmarque o checkbox receber novidades
Atlas, selecione a opção contato por email
```

Se uma alteração reversível for enviada mas não puder ser confirmada, o Atlas
tenta restaurar uma vez o estado anterior e não repete a ação solicitada.

