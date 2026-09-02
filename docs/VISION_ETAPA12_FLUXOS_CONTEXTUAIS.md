# Atlas Vision — Etapa 12: Fluxos Contextuais Verificados

## Objetivo

A Etapa 12 amplia os formulários da Etapa 11 com seleção estrutural de opções
em controles web nativos (`<select>`), mantendo todos os passos presos à mesma
aba DOM e verificando cada alteração antes de continuar.

## Novidades

- `StructuredOptionSelectionRequest` para comandos como `selecione Amazonas no campo estado`.
- `StructuredContextualFormRequest` para combinar preenchimento + seleção no mesmo comando.
- `BrowserAutomation.select_interactive_option()` usa Playwright `select_option`, sem mouse/teclado físico.
- O estado DOM passa a registrar `selected_label` e `selected_value` para pós-verificação.
- O fluxo contextual é interrompido se a aba mudar, se a confiança cair abaixo de 85% ou se um passo ficar inconclusivo.
- Nenhum envio, salvamento ou confirmação final é executado automaticamente.

## Exemplo

```text
Atlas, preencha o campo nome com Ssamir e o campo cidade com Manaus
 e selecione Amazonas no campo estado.
```

Resultado esperado:

```text
Nome = Ssamir
Cidade = Manaus
Estado = Amazonas
```

O botão Enviar permanece intocado.

## Segurança

A seleção por Vision/Qwen/coordenadas continua proibida para ações. Nesta etapa,
a seleção contextual exige um `select` DOM nativo estruturalmente confirmado.
