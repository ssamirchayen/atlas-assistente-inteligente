# Sprint 25 — Etapa 1: perfis e diagnóstico de recursos

## Objetivo

Esta etapa inicia o Atlas Core 1.0 com uma decisão única e transparente sobre o
perfil de execução. Antes de instanciar voz, memória, modelo ou visão, o
`AtlasKernel` obtém métricas agregadas do equipamento e seleciona um perfil.

O diagnóstico não enumera processos, não lê arquivos do usuário, não coleta
nome, conta, serial, endereço de rede ou conteúdo pessoal e não executa comandos
externos.

## Perfis

| Perfil | Classe de RAM observada | CPU lógica | Workers | Tarefas | Contexto preparado |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lite | a partir de 7 GB observados | 2 ou mais | 1 | 1 | 4.096 |
| Standard | a partir de 14 GB | 4 ou mais | 2 | 2 | 8.192 |
| Full | a partir de 28 GB | 8 ou mais | 4 | 4 | 16.384 |

O piso observado de 7 GB representa computadores comercializados com 8 GB nos
quais parte da memória pode estar reservada para hardware. Abaixo desse piso, o
estado é `unsupported`. Uma única CPU lógica também é incompatível. Menos de
1 GB disponível ou menos de 2 GB livres em disco gera estado `limited`.

Os limites são contratos para as próximas etapas. Eles ainda não reduzem
contexto, workers ou funcionalidades do Atlas.

## Seleção

`ATLAS_RUNTIME_PROFILE=auto` é o padrão. O seletor recomenda:

- Lite abaixo da classe Standard;
- Standard com pelo menos 14 GB observados e quatro CPUs lógicas;
- Full com pelo menos 28 GB, oito CPUs lógicas e, quando o disco puder ser
  medido, 20 GB livres.

O usuário pode solicitar Lite, Standard ou Full. Um perfil inferior é respeitado.
Se o perfil solicitado exceder a recomendação, a decisão usa a recomendação e
registra `fallback_applied=True` com `requested_profile_reduced`. Não existe
redução silenciosa.

## Métricas

O `SystemResourceProbe` coleta apenas:

- RAM total e disponível;
- CPUs lógicas e físicas;
- espaço livre no volume do Atlas;
- VRAM, somente quando um leitor opcional seguro for fornecido.

Falha de disco, CPU física ou VRAM não inventa um valor. A métrica fica
indisponível. Falha de RAM interrompe apenas o diagnóstico porque ela é a métrica
essencial para selecionar um perfil com segurança.

## Integração atual

O `AtlasKernel` publica a decisão em `kernel.runtime_profile` antes de construir
os componentes pesados. O objeto contém snapshot, perfil solicitado,
recomendado e selecionado, estado de suporte, motivos e orçamento.

Esta etapa não altera o comportamento dos módulos existentes. O Resource Manager
das próximas etapas consumirá os orçamentos somente depois de testes específicos
de regressão, concorrência e pressão de memória.

## Limites deliberados

- não há aplicação automática dos limites ainda;
- VRAM não é consultada por executáveis externos;
- a detecção não substitui benchmark real em uma VM Windows com 8 GB;
- carga instantânea não é usada para promover um perfil;
- disponibilidade temporária baixa apenas sinaliza estado limitado;
- valores inválidos no `.env` retornam com segurança para `auto`.
