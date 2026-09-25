# Atlas — Sprint 29 / Bloco F
## Ações Operacionais Supervisionadas no Nexyra + Atlas

Este bloco mantém o Nexyra padrão independente. As ações abaixo só são suportadas
pela edição `Nexyra_CRM_Atlas`.

### Novas ações
- `lead.assign`: atribui um lead a um usuário ativo da empresa.
- `lead.prioritize`: altera a prioridade de um lead.
- `lead.followup`: agenda um retorno futuro para um lead.
- `distribution.run`: executa a fila de distribuição automática já configurada no CRM.

### Segurança
Todas as ações:
1. geram uma prévia sem escrita;
2. ficam vinculadas à prévia e ao payload normalizado;
3. expiram em 2 minutos no Atlas;
4. são revalidadas no Nexyra imediatamente antes da escrita;
5. exigem confirmação explícita (`sim`);
6. respeitam as permissões nativas do CRM;
7. são auditadas no Nexyra.

`distribution.run` guarda na prévia os pares lead/responsável esperados. Se a fila
mudar antes da confirmação, a ação é recusada e uma nova prévia é necessária.

### Permissões adicionais
- `lead.assign` e `distribution.run`: `leads.assign`
- `lead.prioritize`: `leads.update`
- `lead.followup`: `activities.create`

A execução continua exigindo `atlas.execute`, portanto a edição integrada deve
usar um ator gerente ou administrador.

### Comandos amigáveis
```text
Nexyra prévia atribuir LEAD-ID USER-ID
Nexyra prévia priorizar LEAD-ID urgente
Nexyra prévia retorno LEAD-ID 2099-09-20T14:00:00-04:00
Nexyra prévia distribuir 25
Nexyra prévia distribuir fila 25
```

O formato técnico também continua disponível:
```text
Nexyra prévia lead.assign LEAD-ID {"user_public_id":"USER-ID"}
Nexyra prévia lead.prioritize LEAD-ID {"priority":"alta"}
Nexyra prévia lead.followup LEAD-ID {"due_at":"2099-09-20T14:00:00-04:00"}
Nexyra prévia distribution.run {"limit":25}
```

### Fora do escopo deste bloco
- envio automático de WhatsApp;
- aplicação automática de recomendações;
- comunicação sem consentimento;
- alteração do Nexyra padrão.

Esses itens continuam bloqueados ou exigem fluxos específicos de consentimento e
confirmação.

### Validação no ambiente de construção
- Atlas `tests/`: 189 passed, 7 skipped.
- Contrato real Atlas ↔ Nexyra + Atlas: 7 passed.
- Nexyra + Atlas completo: 224 passed em três blocos.
- `compileall`: passou.
- Ruff: executar no Windows do projeto.
