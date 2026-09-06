# Atlas — Sprint 28.16

## Relatórios inteligentes do Business Lab

Esta etapa adiciona ao Atlas a capacidade de gerar relatórios operacionais e gerenciais do Nexyra Business Lab diretamente pelo Copilot.

## O que entrou

- Relatório inteligente de leads.
- Relatório inteligente de matrículas.
- Relatório inteligente de atendimentos.
- Relatório inteligente de retornos.
- Filtros por curso, status, prioridade, pagamento e atrasos.
- Resumo executivo.
- Insights automáticos.
- Alertas operacionais.
- Próximos passos sugeridos.
- Exportação em Markdown, CSV, JSON e HTML.
- Leitura via Business Lab API, sem acesso direto ao banco.

## Exemplos de comandos

```text
Atlas, gere um relatório completo dos leads de Radiologia desta semana.
```

```text
Atlas, mostre matrículas por curso, status e pagamento.
```

```text
Atlas, liste retornos atrasados por prioridade.
```

```text
Atlas, analise atendimentos e diga onde estamos perdendo conversão.
```

```text
Atlas, gere um resumo executivo da operação comercial de hoje.
```

## Teste pelo painel

1. Rode o Business Lab.
2. Rode o Atlas Copilot Bridge.
3. Abra o painel Atlas dentro do Business Lab.
4. Envie um dos comandos de relatório.

## Teste pelo terminal

```powershell
cd C:\Atlas_OFICIAL

$env:ATLAS_BUSINESS_LAB_URL="http://127.0.0.1:5055"
$env:ATLAS_BUSINESS_LAB_EMAIL="consultor@nexyra.lab"
$env:ATLAS_BUSINESS_LAB_PASSWORD="Consultor123!"

.\.venv\Scripts\python.exe tools\run_business_lab_smart_report.py
```

Os arquivos serão salvos em:

```text
data\business_lab_benchmark
```

## Segurança

Esta etapa apenas consulta dados e gera relatório. Não altera leads, atendimentos, retornos ou matrículas.
