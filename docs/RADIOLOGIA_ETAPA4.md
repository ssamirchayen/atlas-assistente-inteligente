# Etapa 4 — Qualidade e revisão assistida

Extraia o patch na raiz de `atlas_OFICIAL`, sobre as etapas anteriores.

```powershell
cd "C:\PROJETOS NEXYRA + ATLAS\atlas_OFICIAL"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\radiology_stage4.ps1
if ($LASTEXITCODE -ne 0) { throw "Falha na Etapa 4." }
```

O script roda pytest das Etapas 1–4, Ruff e pip check, cria um novo LAB sintético,
abre o visualizador e informa os caminhos de `quality.json` e `quality-review.json`.
Não aprova imagens automaticamente e não precisa de Docker.

## O que é analisado

| Campo | Significado |
| --- | --- |
| source_width/height | Dimensões da imagem decodificada de origem |
| display_width/height | Dimensões da prévia analisada |
| display_p01/p99 | Percentis 1 e 99 dos tons da prévia |
| display_std | Variação dos tons da prévia |
| display_black/white_fraction | Fração em 0 e 255, de 0 a 1 |
| dicom_laterality | ImageLaterality L/R, ou unknown |
| flags | Alertas técnicos para revisão |

As métricas usam a **prévia renderizada de 8 bits, até 1600 pixels**. Dependem
da janela DICOM, normalização, redução e conversão para cinza. Não medem dose,
exposição do detector, qualidade diagnóstica, foco ou movimento do paciente.
Não alteram imagens de origem. Valores próximos de preto/branco não demonstram
por si só perda de informação: fundo e janela também influenciam.

Heurísticas versionadas `display_screen_v1`, sem calibração clínica:
- `constant_display_image`: todos os pixels da prévia iguais; bloqueia.
- `narrow_display_range`: diferença p99−p01 menor que 16; exige revisão.
- `small_display_image`: menor dimensão abaixo de 256; exige revisão.
- `dicom_laterality_conflict`: ImageLaterality diverge do manifesto; bloqueia.

Os dois limiares numéricos são regras iniciais de engenharia, não critérios
clínicos. A ausência de alertas não significa que a imagem esteja adequada.

## Revisão humana

Não há classificador anatômico, detector automático de projeção nem leitura
automática do marcador lateral. AP/LATERAL/OBLIQUE no manifesto são declarações.
O revisor examina imagens e dados de aquisição para preencher o modelo:

| Campo | Valores |
| --- | --- |
| observed_projection | AP, LATERAL, OBLIQUE ou unknown |
| observed_laterality | L, R ou unknown |
| anatomy_coverage | acceptable, reject ou unknown |
| positioning | acceptable, reject ou unknown |
| image_quality | acceptable, reject ou unknown |
| flags_reviewed | true após conferir alertas; false enquanto pendente |

Examine cobertura da região definida no protocolo, cortes de estruturas,
posicionamento, superposição, marcadores e informações de aquisição. Caso haja
dúvida, use unknown ou reject. Não presuma um ângulo oblíquo apenas pelo rótulo.
Esta etapa ainda não calcula ângulos físicos nem calibração.

Não edite os hashes do modelo: vinculam a revisão ao caso e aos arquivos.
O resultado é uma declaração humana local, não autenticação, assinatura ou
validação clínica. Registros não são invioláveis contra quem pode editar a pasta.

## Executar a revisão

Use a pasta LAB exibida pelo script no lugar do caminho de exemplo:

```powershell
$Python = ".\.venv-radiology\Scripts\python.exe"
$Lab = "C:\CAMINHO-DO-LAB-EXIBIDO"
notepad (Join-Path $Lab "quality-review.json")
```

Depois de salvar a revisão, gere um resultado novo:

```powershell
$Resultado = Join-Path $Lab ("quality-result-" + [guid]::NewGuid().ToString("N") + ".json")
& $Python -m atlas.radiology quality-review (Join-Path $Lab "case\case.json") --review (Join-Path $Lab "quality-review.json") --output $Resultado
if ($LASTEXITCODE -eq 2) {
    Write-Host "Revisao bloqueada ou pendente. Consulte blocking_reasons no resultado."
} elseif ($LASTEXITCODE -ne 0) {
    throw "Erro ao processar a revisao."
}
```

Código 2 significa bloqueio registrado, não falha no pytest. As imagens do LAB
são padrões artificiais e **não permitem confirmar anatomia real**: mantenha
unknown. Mesmo com respostas simuladas positivas, synthetic=true nunca fica
elegível para avançar como caso real.

Para um caso de pesquisa já importado, crie um relatório/modelo novo:

```powershell
& $Python -m atlas.radiology quality "C:\CAMINHO-DO-CASO\case.json" --output .\quality-novo.json --template .\quality-review-novo.json
if ($LASTEXITCODE -ne 0) { throw "Falha na triagem." }
```

Abra o visualizador correspondente ao caso antes de preencher o modelo. Não use
as cópias reduzidas da exportação de privacidade para substituir o caso original.
Manifesto ou imagem alterados exigem nova triagem e revisão. Resultados existentes
nunca são sobrescritos.

`eligible_for_geometry_stage` significa somente que as verificações desta etapa
e as declarações humanas passaram para um caso declarado de pesquisa. Não valida
consentimento, privacidade, aquisição física, uso clínico ou reconstrução.
Os fluxos da Etapa 3 continuam obrigatórios para exportar cópias de visualização.
Relatórios contêm hashes rastreáveis; mantenha-os na pasta de pesquisa restrita.

Próxima etapa: geometria física e calibração das aquisições.
