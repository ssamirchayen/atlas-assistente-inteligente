# Etapa 5 — Contrato físico e verificação de calibração fornecida

Instale sobre as etapas anteriores, na raiz de `atlas_OFICIAL`.

```powershell
cd "C:\PROJETOS NEXYRA + ATLAS\atlas_OFICIAL"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\radiology_stage5.ps1
if ($LASTEXITCODE -ne 0) { throw "Falha na Etapa 5." }
```

Roda pytest das Etapas 1–5, Ruff, pip check e um LAB geométrico sintético. O LAB
gera oito vértices de um cubo conhecido e três aquisições virtuais, separadas em
45/45/90 graus. Não gera RX, DRRs ou osso 3D. Usa as dependências já existentes.

## Escopo entregue

O módulo recebe geometria e correspondências 3D→2D previamente conhecidas.
Calcula matrizes de projeção e erros por vista; verifica rotações, coordenadas,
distribuição dos marcadores, profundidade positiva e separação das vistas.
**Não ajusta os parâmetros de câmera, não detecta marcadores e não estima a
calibração a partir de radiografias.** Essa aquisição/calibração externa precisa
ser fornecida e verificada antes do uso em dados reais.

A fórmula utilizada é `p ~ K R (X - C)`, ou `P = K [R | -R C]`.

| Campo | Convenção |
| --- | --- |
| coordinate_system | LPS_mm: X esquerda, Y posterior, Z superior, milímetros |
| K | Intrínseca 3×3; focais em pixels, ponto principal e skew |
| R_world_to_camera | Rotação 3×3 do mundo LPS para câmera, determinante +1 |
| center_lps_mm | Centro da fonte/câmera no mesmo referencial LPS, em mm |
| image_size | [largura, altura] em pixels da imagem original |
| points_lps_mm | 6–1000 marcadores 3D conhecidos, distintos e não coplanares |
| observed_px | Coordenadas [u,v] observadas, mesma ordem dos marcadores |
| pixel_convention | pixel_centers_zero_based: centro superior esquerdo (0,0) |
| distortion | rectified_pinhole: dados já retificados; não corrige distorção |
| max_error_px | Limite máximo por marcador, maior que 0 e até 10 pixels |

Eixos de câmera: x direita da imagem, y para baixo, z para frente. Intrínseca tem
última linha [0,0,1], elemento K[1,0]=0, focais positivas e ponto principal no
detector. Não infere unidades pelo valor: declarar mm em dados medidos em cm pode
produzir um resultado numericamente consistente e fisicamente incorreto.

O mesmo referencial 3D deve ser usado nas três vistas, sem movimento relativo do
objeto ou com transformação conhecida já incorporada. PixelSpacing isolado não
fornece K, pose ou distância fonte-objeto. Não use coordenadas das prévias de
1600 pixels ou das cópias de privacidade neste contrato. Se houver rotação,
recorte, espelhamento ou redimensionamento, transforme K e coordenadas de modo
coerente. Em JPEG com orientação EXIF, use coordenadas da matriz original; o
visualizador orientado não fornece automaticamente essas coordenadas.

## Critérios iniciais de engenharia

- Erro máximo de reprojeção por vista deve ficar dentro do limite informado.
- LAB usa 2 pixels; não é tolerância clínica validada.
- Centros devem estar separados por pelo menos 1 mm e eixos ópticos entre 5 e
  175 graus para cada par. Esses limites conservadores são regras deste protótipo,
  não uma classificação automática de AP/lateral/oblíqua.
- Pontos coplanares, repetidos ou com distribuição 3D quase degenerada são rejeitados.
- Correspondência errada entre marcadores pode bloquear o resultado.

`geometry_consistent` significa apenas concordância entre geometria e marcadores
fornecidos. Não comprova medição independente, escala real, equipamento calibrado,
projeção anatômica, qualidade clínica ou autorização de uso. O LAB usa pontos
produzidos pelo próprio modelo e serve como teste matemático, não validação externa.
`physical_calibration_verified`, `clinical_use_validated` e
`reconstruction_available` permanecem false.

## Comandos

```powershell
$Python = ".\.venv-radiology\Scripts\python.exe"
& $Python -m atlas.radiology geometry-demo --output .\geometry-demo-novo.json
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar exemplo." }
& $Python -m atlas.radiology geometry-check .\geometry-demo-novo.json --output .\geometry-report-novo.json
if ($LASTEXITCODE -ne 0) { throw "Geometria rejeitada ou inconsistente." }
```

Arquivos de saída precisam ser novos. Erros estruturais retornam 1; erros de
reprojeção acima da tolerância geram relatório com status blocked e código 2.

## Vincular pesquisa real

Prepare o contrato com `origin: research` e `case_binding` contendo:

```json
{
  "manifest_sha256": "SHA256_DO_CASE_JSON",
  "images": {
    "AP": "SHA256_ORIGINAL_AP",
    "LATERAL": "SHA256_ORIGINAL_LATERAL",
    "OBLIQUE": "SHA256_ORIGINAL_OBLIQUA"
  }
}
```

Os hashes estão no relatório da Etapa 4. Substitua todos os parâmetros virtuais
por dados de calibração medidos; não renomeie o LAB como pesquisa.

```powershell
& $Python -m atlas.radiology geometry-check .\geometria-pesquisa.json --manifest "C:\CAMINHO-DO-CASO\case.json" --output .\geometria-resultado-novo.json
if ($LASTEXITCODE -ne 0) { throw "Geometria rejeitada ou inconsistente." }
```

O comando verifica hashes e resolução; não aprova automaticamente os resultados
da revisão humana da Etapa 4. Essa revisão e a privacidade da Etapa 3 continuam
sendo verificações separadas. Os originais e o manifesto não são modificados.
Não injeta as matrizes no caso nem libera reconstrução automaticamente.

Referência matemática: OpenCV, Camera Calibration and 3D Reconstruction:
https://docs.opencv.org/4.12.0/d9/d0c/group__calib3d.html

Próxima etapa do módulo: segmentação, marcos anatômicos e correções manuais.
