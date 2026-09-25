# Etapa 11 — exportação de pesquisa OBJ/STL

Extraia o patch na raiz atlas_OFICIAL e execute tools/radiology_stage11.ps1.
O script instala os requisitos já fixados, roda pytest/Ruff e cria um LAB novo.
Não conecta banco, rede ou aplicativo. A integração futura recebe o contrato
JSON atlas_radiology_research_bundle_v1, descrito abaixo.

## Dois resultados do laboratório

- blocked-export: avaliação rejeitada, relatório sem malhas.
- diagnostic-export: exportação explícita para investigação, com arquivos
  REJECTED_envelope.obj e REJECTED_envelope.stl. Continua rejeitada.

O exemplo sintético da Etapa 10 tem alta sensibilidade aos contornos e é
rejeitado. Código 2 significa rejeição registrada, não erro operacional.
O script aceita esse código no LAB e termina com sucesso, exibindo o estado.
Nenhum desses arquivos representa osso real ou aprovação clínica.

## Outro caso

```powershell
& .\.venv-radiology\Scripts\python.exe -m atlas.radiology export-bundle .\caso\case.json --annotation .\annotations.json --geometry .\geometry.json --settings .\reconstruction-settings.json --output .\exportacao_nova
```

O comando recalcula a avaliação com raio 1 pixel e política contour_screen_v1;
não aceita relatório editado nem resultado antigo como aprovação. Se rejeitado,
exporta somente assessment.json, README.txt e bundle.json. Para investigação
explícita, acrescente --diagnostic: as malhas levam REJECTED no nome e o estado
rejected_diagnostic_only. Esse modo não remove motivos nem altera approved=false.
Sem rejeição, o estado é research_review_required e os nomes levam UNVALIDATED.

## Contrato local

bundle.json inclui schema_version, contract, status, mesh_included,
assessment_status, reasons, units, coordinate_system, axes, approved=false,
clinical_use_validated=false, inputs_sha256 e files (nome, SHA-256 e bytes).
O manifesto lista todos os arquivos de conteúdo; não inclui o próprio hash.
O consumidor deve verificar hashes e estados e nunca interpretar ausência de
rejeição como aprovação clínica. SHA-256 não autentica o autor do pacote.
O relatório de reconstrução preserva o hash do OBJ original; o OBJ exportado
recebe um comentário de estado, portanto seu hash correto é o de bundle.json.

Coordenadas preservadas em LPS: x esquerda, y posterior, z superior; mm.
STL ASCII não define unidades; OBJ também pode ser interpretado sem escala
pelo programa receptor. Confira mm no importador e mantenha manifesto e
relatórios junto das malhas. Não há transformação automática para RAS.
Triângulos e orientação são preservados; sem suavização ou reparo topológico.
Não há certificação de manifold, impressão, fabricação ou planejamento cirúrgico.
Exportações têm limite herdado de 100000 vértices e 100000 triângulos.

Imagens originais não são copiadas; isso não torna geometria e relatórios
automaticamente anônimos. Preserve o ambiente autorizado de pesquisa.
O mapa NPZ de sensibilidade acompanha as malhas, sem virar probabilidade clínica.
Etapa 8: CT real e treinamento neural continuam pendentes. Próxima: Etapa 12,
protocolo de piloto independente. Aplicativo e conexões permanecem posteriores.
