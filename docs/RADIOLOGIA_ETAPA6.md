# Etapa 6 — Segmentação manual, marcos e correções

Esta entrega continua a sprint de Radiologia. Aplicativo, base central e API
ficam para depois de concluir as 12 etapas. O HTML desta etapa é uma ferramenta
local do LAB para anotação, não o aplicativo final.

Extraia na raiz de atlas_OFICIAL, substituindo os arquivos deste patch.

```powershell
cd "C:\PROJETOS NEXYRA + ATLAS\atlas_OFICIAL"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\radiology_stage6.ps1
if ($LASTEXITCODE -ne 0) { throw "Falha na Etapa 6." }
```

Roda pytest das seis etapas, Ruff, pip check, gera padrões sintéticos e abre o
editor. Não precisa de Docker, servidor ou novas dependências. Guarde o caminho
do LAB exibido no terminal. Padrões não são radiografias e não validam anatomia.

## Usar o editor

1. Escolha AP, LATERAL ou OBLIQUE e a estrutura: fêmur distal, tíbia, fíbula ou patela.
2. No modo Contorno, clique nos vértices ao longo do limite e use Fechar contorno.
3. Para corrigir um contorno, exclua-o na lista e redesenhe. Desfazer recupera
   alterações recentes; durante desenho remove o último vértice.
4. No modo Marco, selecione P1–P4 e clique. Repetir o mesmo rótulo na mesma
   estrutura/vista reposiciona esse ponto. Excluir e Desfazer também funcionam.
5. Use Baixar anotações JSON. O navegador salva `atlas-annotations.json` na pasta
   de downloads (ou pede destino, conforme sua configuração).
6. Para continuar outro dia, abra o mesmo editor e use Retomar JSON.

Sem autosave: baixar o JSON preserva o trabalho; fechar a página pode perder
alterações ainda não baixadas. Trocar vista, estrutura ou ferramenta descarta
o contorno ainda não fechado; feche-o antes. O editor avisa essa situação.

P1–P4 são **rótulos genéricos**, não pontos detectados ou homologados pelo sistema.
A equipe precisa definir e revisar o significado anatômico de cada rótulo por
estrutura. Usar P1 em duas vistas não comprova correspondência física.

São permitidos múltiplos contornos por estrutura, inclusive componentes separados
para não forçar continuidade onde há fratura ou dúvida. Estruturas distintas
podem se sobrepor na projeção. Não há preenchimento automático de lesões, modelo
neural treinado ou segmentação automática nesta entrega.

## Validar JSON e gerar máscaras

Substitua `$Lab` pelo caminho exibido pelo script. Se o navegador salvou com
outro nome, ajuste `$Anotacao`:

```powershell
$Python = ".\.venv-radiology\Scripts\python.exe"
$Lab = "C:\CAMINHO-DO-LAB-EXIBIDO"
$Anotacao = Join-Path $env:USERPROFILE "Downloads\atlas-annotations.json"
$Saida = Join-Path $Lab ("annotations-export-" + [guid]::NewGuid().ToString("N"))
& $Python -m atlas.radiology annotation-export (Join-Path $Lab "case\case.json") --annotation $Anotacao --output $Saida
if ($LASTEXITCODE -ne 0) { throw "Anotacao rejeitada. Confira a mensagem acima." }
```

O comando exige pelo menos um contorno; verifica os hashes do caso, imagens e
prévias, coordenadas, tipos, limites e contornos simples sem cruzamentos. Marcos
duplicados na mesma estrutura/vista são rejeitados. O limite JSON é 256 KiB;
cada vista admite até 40 contornos de até 200 vértices. O resultado contém:

- PNG binário por estrutura/vista anotada: fundo 0, contorno preenchido 255.
- `annotations.json`: contornos e marcos para retomar/corrigir.
- `annotation-report.json`: hashes das máscaras e limitações explícitas.

Vista/estrutura sem contorno não gera máscara: significa **não anotada**, não
ausência de osso. Contornos da mesma estrutura são unidos; buracos internos não
são suportados. A saída deve estar em pasta nova. Os originais são preservados.

## Coordenadas e limites

As anotações e máscaras usam a **prévia renderizada**, orientada pelo decodificador,
8 bits, até 1600 pixels. Zoom muda apenas a exibição; não muda as coordenadas.
Não use diretamente essas coordenadas como pixels originais da Etapa 5. Rotação
EXIF, redimensionamento e transformações precisam ser mapeados explicitamente
antes de reconstrução métrica. `ready_for_metric_reconstruction` permanece false.

Um contorno geometricamente válido não comprova que represente osso corretamente.
Anatomia, completude, qualidade e correspondência dos marcos exigem revisão.
Anotações parciais são permitidas para correção; não liberam reconstrução.

O HTML contém pixels incorporados que podem identificar pessoas. JSON e máscaras
contêm dados rastreáveis e anatômicos. Mantenha-os localmente; esta exportação
é um artefato de trabalho de pesquisa, não o fluxo de privacidade da Etapa 3.

## Caso próprio já importado

```powershell
& $Python -m atlas.radiology annotation-editor "C:\CAMINHO-DO-CASO\case.json" --output .\data\radiology-lab\editor-caso-novo
if ($LASTEXITCODE -ne 0) { throw "Falha ao preparar editor." }
```

Abra `index.html` nessa pasta e siga o mesmo fluxo. Não modifica o manifesto,
não sincroniza com Atlas principal e não cria API. Próxima etapa: reconstrução
3D inicial com modelo geométrico/estatístico e entradas compatíveis.
