# Atlas Vision — Etapa 14: Ação Final Supervisionada

## Objetivo

Ações finais de formulário passam a exigir duas mensagens independentes. O
primeiro comando apenas localiza o botão, revalida o DOM com confiança mínima
de 90% e cria uma confirmação temporária.

```text
Atlas, enviar o formulário
CONFIRMAR VISÃO <código exibido pelo Atlas>
```

## Garantias

- código em memória, de uso único e válido por 120 segundos;
- confirmação vinculada à aba, índice e fingerprint estrutural do botão;
- mudança de aba ou página cancela a ação;
- botão desabilitado ou alterado é recusado;
- compra, pagamento, exclusão, publicação e transferência permanecem fora do
  fluxo;
- depois que uma ação final é enviada, ela nunca é repetida automaticamente;
- sucesso só é declarado com evidência pós-ação observável.

