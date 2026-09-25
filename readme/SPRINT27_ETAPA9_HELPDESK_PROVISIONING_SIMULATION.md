# Sprint 27 — Etapa 9 — Help Desk + Provisioning Simulation

Esta etapa adiciona ao Atlas Benchmark & Validation Lab um laboratório sintético
para suporte de TI e provisionamento de computadores.

## Objetivo

Comparar uma operação manual hipotética com uma operação assistida pelo Atlas,
sem modificar computadores reais e sem usar dados pessoais reais.

A suíte padrão simula:

- 1.200 chamados por mês;
- 4 técnicos;
- 100 dispositivos gerenciados;
- 15 novos onboardings/provisionamentos por mês;
- triagem, resolução, escalonamento e retrabalho;
- provisionamento manual versus assistido;
- capacidade humana reutilizável;
- payload JSON reservado para o mini frontend do benchmark.

## Segurança e interpretação

Todos os números comerciais e de operação são premissas sintéticas. A suíte não
executa instalação, clique, automação de desktop ou alteração de estação de
trabalho. Ela não garante SLA, redução de equipe, economia financeira ou taxa de
resolução em ambientes reais.

A futura validação com cliente poderá substituir premissas por observações
medidas mantendo o mesmo contrato de resultado.

## Casos

1. `helpdesk.ticket_generation`
2. `helpdesk.baseline_vs_atlas`
3. `helpdesk.first_response`
4. `helpdesk.automation_coverage`
5. `helpdesk.provisioning`
6. `helpdesk.workload_capacity`
7. `helpdesk.scale`
8. `helpdesk.frontend_contract`

## Mini frontend

`helpdesk_dashboard_payload()` gera um contrato JSON estável com:

- cenário;
- resposta;
- automação;
- provisionamento;
- workload;
- qualidade;
- economia potencial de capacidade;
- cards recomendados para a interface.

Esse payload será consumido na Etapa 12 pelo mini frontend do Atlas Benchmark.
