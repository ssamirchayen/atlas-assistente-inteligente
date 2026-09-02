# Sprint 23 — Etapa 2: Perfis de funcionário e planos autorizados

## Objetivo

Permitir que a TI escolha um perfil corporativo para um novo funcionário e
obtenha um plano de configuração exato, revisável e aprovado por uma segunda
pessoa. Esta etapa não instala programas nem modifica o computador.

## Fluxo

1. O computador precisa estar cadastrado e ativo no Atlas Edge.
2. A TI escolhe um perfil presente no catálogo autorizado.
3. O Atlas captura o inventário somente para os pacotes daquele perfil.
4. O planner gera etapas declarativas com IDs exatos e pastas relativas.
5. Funcionário e solicitante são convertidos em hashes SHA-256.
6. Um responsável diferente do solicitante confirma o token temporário.
7. Perfil, vínculo do dispositivo e inventário são revalidados.
8. O Atlas emite um recibo de autorização com validade de 15 minutos.

O recibo não é uma execução. Ele prepara a base para a próxima etapa da Sprint
23, que introduzirá uma fila local controlada e aplicação supervisionada.

## Catálogo inicial

O catálogo reutiliza os perfis corporativos já revisados:

| ID | Uso | Requisitos principais |
| --- | --- | --- |
| `school-sales` | Atendimento e vendas | Chrome, Teams, Acrobat e workspace escolar |
| `school-helpdesk` | Suporte de TI | Perfil comum, 7-Zip, PowerToys e workspace de TI |

Adicionar um perfil exige alteração de código, revisão e testes. O usuário não
pode enviar um script, comando de shell, URL de instalador ou pacote arbitrário
durante a solicitação.

## Controles de segurança

- allowlist imutável de perfis;
- máximo de 32 perfis e 25 requisitos por perfil;
- aprovação temporária e de uso único;
- separação entre solicitante e aprovador;
- revalidação do inventário e do digest do perfil;
- novo plano revoga qualquer solicitação pendente anterior do dispositivo;
- referências privadas são armazenadas apenas como SHA-256;
- nenhum token aparece no payload do plano ou da autorização;
- dispositivo pausado ou não cadastrado não pode gerar planos;
- ausência de executor, transporte HTTP, subprocesso e comandos livres.

## Piloto seguro

```powershell
.\.venv\Scripts\python.exe edge_profile_pilot.py
```

Digite `SIM` nas duas confirmações. O piloto usa uma pasta temporária e um
inventário Windows sintético. A saída deve terminar com:

```text
Piloto concluído. Nenhuma etapa do plano foi executada.
```

## Validation Lab

```powershell
.\.venv\Scripts\python.exe -m atlas_validation run --domain edge
```

`EDGE-003` é automatizado. `EDGE-004` descreve o piloto manual supervisionado.
