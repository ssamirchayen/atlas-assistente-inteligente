# Sprint 23 — Etapa 1: Fundação do Atlas Edge

## Objetivo

Criar o `ITProvisioningAgent`, agente local que futuramente permitirá à TI
configurar computadores de novos funcionários. Esta primeira etapa implementa
somente a identidade e o canal operacional mínimo; ela não instala programas,
não altera o Windows e não se comunica com servidores.

## Fluxo de cadastro

1. O agente cria uma identidade aleatória `edge_<uuid>`.
2. A TI informa um identificador de organização.
3. O agente captura um inventário sanitizado e produz um token temporário.
4. Um responsável confirma o token.
5. Antes de cadastrar, o inventário é capturado novamente.
6. Se o computador mudou, o cadastro é cancelado.
7. A associação aprovada é persistida localmente.

O token é de uso único, expira em dez minutos e existe somente em memória. O
nome do responsável não é armazenado: o estado guarda apenas seu SHA-256.

## Identidade e persistência

O identificador não é derivado de serial, hostname, usuário, IP ou endereço de
rede. O estado local usa JSON limitado a 64 KiB, escrita temporária e substituição
atômica. Um arquivo corrompido provoca falha segura; o agente não cria outra
identidade por cima dele silenciosamente.

Arquivo local:

```text
data/edge/device.json
```

Essa pasta está ignorada pelo Git e não entra no ZIP incremental.

## Heartbeat

Depois do cadastro, `heartbeat()` produz um objeto local com:

- ID aleatório do dispositivo;
- organização;
- sequência monotônica;
- estado `online` ou `paused`;
- versão do agente;
- fingerprint SHA-256 do inventário;
- sistema, versão, arquitetura e disponibilidade do WinGet;
- instante UTC.

Hostname, serial, usuário, IP, token e nome do aprovador não fazem parte do
payload. Heartbeats concorrentes são serializados e recebem números únicos.

## Limites de segurança

Nesta etapa não existem:

- transporte HTTP ou conexão remota;
- fila de tarefas;
- execução de WinGet;
- configuração de navegador, impressora, atalhos, VPN ou rede;
- reinício do computador;
- comandos livres, shell ou elevação administrativa.

Essas funções pertencem às próximas etapas e só serão liberadas por perfis
declarativos, aprovação da TI, revalidação e evidências.

## Piloto seguro

```powershell
.\.venv\Scripts\python.exe edge_agent_pilot.py
```

O piloto usa uma pasta temporária. Digite `SIM` em letras maiúsculas. A saída
deve terminar com:

```text
Piloto concluído. Nenhum programa ou configuração foi alterado.
```
