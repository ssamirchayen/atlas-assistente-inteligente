# Sprint 27 - Etapa 8 - School Lead Simulation

## Objetivo

Criar o primeiro laboratório empresarial específico do Atlas Benchmark: uma escola técnica sintética com leads, cursos, fontes, atendimento fora do horário, follow-ups, CRM e carga dos consultores.

## Premissa de segurança comercial

Todos os números desta etapa são projeções sintéticas baseadas em premissas explícitas. O School Lab mede carga operacional, capacidade e tempos esperados. Ele não promete matrículas, conversão, faturamento, economia real, redução de quadro ou qualquer resultado comercial de cliente.

## Cenário padrão

- 2.000 leads por mês;
- 5 consultores;
- 8 cursos;
- 4 fontes de lead;
- 30% dos leads fora do horário;
- 80% de automação simulada;
- 2 follow-ups por lead;
- comparação Manual x Atlas;
- geração de leads 100% sintéticos, sem dados pessoais reais.

## Casos

1. `school.lead_generation`
2. `school.baseline_vs_atlas`
3. `school.first_response`
4. `school.followup_coverage`
5. `school.workload_capacity`
6. `school.scale`
7. `school.frontend_contract`

## Mini frontend

A etapa já entrega `school_dashboard_payload()` com contrato JSON estável para a interface da Sprint 27. O payload possui seções para cenário, mix de leads, resposta, follow-ups, carga humana, qualidade, economia potencial e cards recomendados.

O frontend visual será implementado na Etapa 12, mas o School Lab já fica pronto para ser exibido sem reconstruir a lógica.

## Execução

```powershell
.\.venv\Scripts\python.exe tools\run_atlas_benchmark.py run school_leads --version 1.0.0
```

Resultado esperado: `7 PASS`, sem falhas ou erros.
