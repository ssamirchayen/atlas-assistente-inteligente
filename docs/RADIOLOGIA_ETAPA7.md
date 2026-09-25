# Etapa 7 — Reconstrução geométrica inicial

Esta entrega é o baseline geométrico da sprint. Ainda não contém modelo
estatístico anatômico treinado, rede neural ou aplicativo final. Aplicativo e
conexões ficam para depois das 12 etapas, conforme combinado.

## Executar

Extraia o patch na raiz de atlas_OFICIAL, sobre as etapas anteriores.

```powershell
cd "C:\PROJETOS NEXYRA + ATLAS\atlas_OFICIAL"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\radiology_stage7.ps1
if ($LASTEXITCODE -ne 0) { throw "Falha na Etapa 7." }
```

O script roda pytest das sete etapas, Ruff, pip check e gera um novo LAB. Não
precisa de Docker, GPU ou dependências novas. Abre a pasta de resultados.

## Método

Recebe contornos da mesma estrutura nas três vistas e geometria da Etapa 5.
Cria uma grade em LPS/mm e projeta o centro de cada voxel nas três máscaras.
Mantém células cujo centro está dentro das três silhuetas. Gera uma malha das
faces expostas desses voxels, com escala em milímetros da geometria fornecida.

É uma aproximação discreta do volume compatível com as silhuetas, ou visual hull.
Não equivale à tomografia. Não recupera densidade, estruturas internas, concavidades
invisíveis nos contornos ou fraturas sem evidência nas silhuetas. Não há garantia
de preservação de lesões; componentes podem se unir por ambiguidade ou resolução.
Não há suavização, preenchimento de buracos ou prior para normalizar a anatomia.

A ocupação usa centros de células. As faces podem ultrapassar os contornos por
discretização; reprojetamos o volume de cada célula para mostrar essa diferença.
Um bom resultado nas silhuetas não determina uma única anatomia 3D correta.

## LAB sintético

Usa um elipsoide com raios 20, 30 e 45 mm, contornos derivados de sua superfície
e três câmeras virtuais. O nome tibia é apenas um rótulo de teste, não representa
formato de tíbia. Não são imagens médicas, RX simulados por atenuação ou DRRs.

Com voxel de 5 mm, o teste local gerou 1216 voxels, 1596 triângulos e Dice de
aproximadamente 0,852 contra o elipsoide na mesma grade. IoU de reprojeção ficou
aproximadamente 0,789 / 0,826 / 0,789 nas três vistas. Esses números medem somente
este exercício; não são acurácia clínica. O gerador e o reconstrutor compartilham
o modelo de câmera; não substituem validação independente.

## Resultados

| Arquivo | Conteúdo |
| --- | --- |
| volume.npz | Grade booleana occupied[x,y,z], origem LPS e tamanho do voxel |
| envelope.obj | Superfície experimental de voxels, sem suavização |
| ap/lateral/oblique_reprojection.png | Silhuetas do volume estimado |
| reconstruction-report.json | Parâmetros, hashes, volume do envelope e métricas |
| synthetic-comparison.json (pasta LAB) | Comparação com o elipsoide conhecido |

As coordenadas do centro são `origin + (índice + 0.5) * voxel_size_mm`.
O volume calculado é o volume do envelope discretizado, não volume ósseo validado.
NPZ deve ser lido com `allow_pickle=False`. OBJ tem eixos LPS e unidade declarada
em milímetros no comentário; leitores OBJ podem assumir outras unidades.
O visualizador integrado RX↔3D continua previsto para a Etapa 9.

## Usar contornos próprios

São necessários o case.json, JSON original de anotações da Etapa 6, contrato
geometry.json da Etapa 5 e configuração de reconstrução. A estrutura precisa
estar contornada nas três vistas; marcos P1–P4 ainda não participam do cálculo.

Exemplo de configuração (substitua a região pelo referencial medido):

```json
{
  "schema_version": 1,
  "bone": "tibia",
  "bounds_lps_mm": [[-70, -70, -70], [70, 70, 70]],
  "voxel_size_mm": 5
}
```

```powershell
$Python = ".\.venv-radiology\Scripts\python.exe"
& $Python -m atlas.radiology reconstruct "C:\CASO\case.json" --annotation "C:\CASO\annotations.json" --geometry "C:\CASO\geometry.json" --settings "C:\CASO\reconstruction-settings.json" --output "C:\CASO\reconstrucao-nova"
if ($LASTEXITCODE -eq 2) {
    Write-Host "Volume toca o limite da regiao. Revise limites, contornos e geometria."
} elseif ($LASTEXITCODE -ne 0) {
    throw "Reconstrucao rejeitada. Consulte a mensagem acima."
}
```

Uma estrutura por execução; para outras estruturas use nova configuração e
pasta. Resultados existentes e originais não são sobrescritos.

## Restrições explícitas

- Para ligar as Etapas 5 e 6 com segurança, aceita apenas prévias com a mesma
  resolução da origem e da calibração. Prévia reduzida ou EXIF que gira/espelha
  a imagem é rejeitado. Conversão geral dessas coordenadas ainda está pendente;
  não altere hashes ou dimensões para contornar a rejeição.
- Origem synthetic/research deve coincidir. Pesquisa exige os hashes de vínculo
  da Etapa 5. Geometria precisa passar na comparação com marcadores.
- Não certifica calibração real nem substitui revisões de privacidade/qualidade.
  O comando não promove automaticamente os estados das etapas anteriores.
- Região inteira deve estar à frente das câmeras. Contornos sem interseção
  geram rejeição, não uma forma inventada.
- Voxel entre 0,25 e 20 mm; extensão múltipla do voxel; 2–128 células por eixo;
  até 262144 células totais e 20000 ocupadas. Limites mantêm o protótipo limitado
  em memória e processamento, sem objetivo de resolução clínica.
- `roi_boundary_warning` retorna código 2 com os artefatos para inspeção: o volume
  toca o limite e pode estar cortado. Não interprete como reconstrução aprovada.
- Métricas são descritivas; critérios de incerteza/rejeição aprofundados ficam
  na Etapa 10. Não há liberação de uso clínico.

Referência do método: Laurentini, The Visual Hull Concept for Silhouette-Based
Image Understanding, IEEE TPAMI 16(2), 1994, DOI 10.1109/34.273735.
https://iris.polito.it/handle/11583/1401917

Próxima etapa: referências CT autorizadas, projeções sintéticas e preparação
da comparação com métodos neurais. Treinamento depende de dados adequados.
