# Segurança

## Dados que nunca devem ser publicados

- arquivo `.env` real;
- tokens, senhas, chaves de API ou certificados;
- bancos de memória em `data/`;
- sessões e agendamentos locais;
- logs de execução;
- gravações de voz ou informações pessoais;
- caminhos que revelem nomes de usuários do Windows.

O `.gitignore` cobre os arquivos gerados normalmente pelo Atlas. Antes de cada
publicação, confirme o conteúdo com:

```powershell
git status
git diff --cached
```

## Relato de vulnerabilidades

Não publique detalhes de uma vulnerabilidade em uma issue aberta. Entre em
contato de forma privada com o mantenedor do projeto e inclua:

- descrição do problema;
- passos mínimos para reprodução;
- impacto esperado;
- sugestão de correção, se disponível.

## Escopo atual

O Atlas é um projeto em desenvolvimento e executa automações no computador do
usuário. Revise toda ação destrutiva antes do uso e não execute o projeto com
privilégios administrativos sem necessidade.
