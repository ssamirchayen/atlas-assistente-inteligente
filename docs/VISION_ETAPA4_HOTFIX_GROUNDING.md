# Vision Etapa 4 — Hotfix de Grounding

## Problema

O modelo reconhecia o elemento pedido, mas frequentemente retornava `bbox`
nula ou em um formato diferente do esperado. O Atlas corretamente recusava
inventar uma posição.

## Correção

1. O parser agora aceita bbox em vários formatos:
   - `[x1,y1,x2,y2]`
   - escala 0..1
   - escala 0..100
   - escala 0..1000
   - dicionário `x1/y1/x2/y2`
   - dicionário `x/y/w/h`
   - string simples com quatro valores

2. Se a análise geral não fornecer bbox confiável, o Atlas faz uma segunda
passagem no mesmo screenshot pedindo somente a localização do alvo.

3. A posição só é retornada se existir bbox válida.

## Segurança

O Atlas continua sem mover mouse, clicar ou digitar.
Se as coordenadas continuarem incertas, a resposta permanece conservadora.
