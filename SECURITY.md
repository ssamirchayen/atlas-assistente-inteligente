# Política de segurança

## Escopo atual

O Atlas está em desenvolvimento e sua API foi projetada para execução local em
Windows. A configuração padrão usa apenas `127.0.0.1`. Não exponha a porta da
API à internet ou à rede corporativa sem TLS, gestão central de identidades,
rate limiting e revisão específica de implantação.

## Segredos

- mantenha `.env` fora do Git;
- use chaves aleatórias com pelo menos 32 caracteres;
- não publique capturas do Swagger que mostrem o `curl` autorizado;
- nunca registre chaves, senhas ou tokens em issues;
- ao suspeitar de exposição, gere uma nova chave e reinicie a API.

## Dados locais

Memórias, sessões, bancos e logs ficam em `data/`, `atlas_data/` e `logs/`.
Esses diretórios não devem fazer parte de commits, releases ou ZIPs públicos.
A auditoria da API registra somente metadados sanitizados, mas ainda deve ser
tratada como dado operacional da instalação.

## Relato responsável

Não abra uma issue pública contendo uma vulnerabilidade explorável, chave,
dados pessoais ou logs privados. Use o recurso **Security Advisories** do
repositório GitHub para relatar o problema de forma privada, incluindo versão,
impacto e passos mínimos para reprodução.

## Limites

Automação de navegador, arquivos e Windows pode produzir efeitos reais. Teste
em ambiente controlado, revise ações destrutivas e mantenha backups adequados.
O projeto ainda não é indicado para processos críticos de produção.
