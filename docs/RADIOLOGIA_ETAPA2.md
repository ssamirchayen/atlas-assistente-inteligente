# Atlas Radiologia — Etapa 2: importação e visualização 2D

Entrega incremental sobre a Etapa 1 validada no Windows, incluindo sua correção
de IDs curtos nos testes. É uma etapa interna do módulo Radiologia/Saúde.

## Aplicar e executar

Extraia todos os arquivos na raiz do Atlas, substituindo os correspondentes.
Os arquivos `requirements-radiology.txt` e `requirements-radiology-dev.txt` devem
ficar ao lado de `gui_main.py`, e não dentro de `tools/`.

```powershell
cd "C:\PROJETOS NEXYRA + ATLAS\atlas_OFICIAL"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\radiology_stage2.ps1
if ($LASTEXITCODE -ne 0) { throw "Falha na Etapa 2 da Radiologia." }
```

O script usa `.venv-radiology`, instala versões fixadas, executa `pip check`,
pytest das Etapas 1 e 2 e Ruff. Depois cria um laboratório novo dentro de
`data/radiology-lab/etapa2-<identificador>/` e abre `viewer/index.html` no navegador
padrão. Não precisa de Docker, servidor web, Internet para visualizar ou GPU.
A instalação das dependências requer acesso ao índice de pacotes.

O laboratório contém **padrões artificiais** PNG, JPEG e DICOM DX de 12 bits.
Eles testam formatos, pixels e apresentação; não são radiografias nem DRRs
geradas a partir de anatomia. A página os identifica como demonstração sintética.

## O que está disponível

- Leitura real dos pixels e criação de prévias derivadas.
- Importação das três imagens para uma pasta nova, preservando os arquivos-fonte.
- Originais copiados byte a byte, com SHA-256 e manifesto da Etapa 1.
- Conferência de conflitos de PatientID, StudyInstanceUID e ImageLaterality
  quando esses campos DICOM estão presentes. Campos ausentes e imagens comuns
  não permitem provar que é o mesmo paciente, lado ou aquisição.
- Relatório somente com metadados técnicos permitidos.
- Visualizador local com três painéis, zoom, rolagem, brilho, contraste e reset.
- Prévias incorporadas no HTML, sem scripts, fontes ou imagens remotos.

O agente consultivo, voz, roteador do Atlas e CRM permanecem fora desta alteração.
A abertura é pelo script/CLI; a integração pela conversa será uma etapa posterior.

## Formatos e transformações

PNG e JPEG são decodificados com Pillow. JPEG recebe correção de orientação EXIF.
PNG de maior profundidade recebe normalização min/max para prévia. Os originais
mantêm todos os seus bytes, incluindo metadados e intensidades originais.

DICOM aceito nesta etapa:

- Arquivo Part 10 com preâmbulo e File Meta Information.
- Modalidade CR ou DX, um quadro, uma amostra por pixel.
- MONOCHROME1 ou MONOCHROME2; 8 ou 16 bits alocados, inteiros com/sem sinal.
- Implicit VR Little Endian, Explicit VR Little Endian ou Explicit VR Big Endian.
- Modality LUT/rescale, VOI LUT ou primeira janela LINEAR/LINEAR_EXACT.
- Sem janela: min/max dos pixels que não são padding; imagens constantes
  recebem intensidade uniforme. MONOCHROME1 é invertido para apresentação.

DICOM comprimido, deflated, multiframe, colorido, CT/MR, VOI SIGMOID e Presentation
LUT adicional/inversa são rejeitados explicitamente. Não há instalação automática
de codecs nem tentativa de adivinhar uma sintaxe ausente. A conferência da
Transfer Syntax ocorre antes da leitura que poderia descomprimir um dataset.

Limites: 50 MiB por arquivo, até 16 milhões de pixels por imagem. Prévias com
8 bits e no máximo 1600 pixels por lado. Elas não servem para recuperar a precisão
dos originais. Os controles de brilho/contraste são ajustes visuais da prévia;
não são edição dos pixels originais nem novos valores de janela DICOM.

PixelSpacing, quando disponível e válido, é informado como dado técnico. Não
equivale à calibração multivista, à correção da magnificação ou a uma autorização
para medir estruturas anatômicas. Importações desta etapa deixam `geometry=null`.

## Comandos individuais

Inspecionar uma imagem (relatório técnico no terminal):

```powershell
.\.venv-radiology\Scripts\python.exe -m atlas.radiology inspect "C:\ExamesPesquisa\ap.dcm"
```

Importar imagens previamente autorizadas para pesquisa, atribuindo as projeções
manualmente e escolhendo uma pasta de destino ainda inexistente:

```powershell
.\.venv-radiology\Scripts\python.exe -m atlas.radiology import `
  --ap "C:\ExamesPesquisa\ap.dcm" `
  --lateral "C:\ExamesPesquisa\lateral.dcm" `
  --oblique "C:\ExamesPesquisa\obliqua.dcm" `
  --side L --origin research `
  --output ".\data\radiology-lab\pesquisa-001"
if ($LASTEXITCODE -ne 0) { throw "Importacao rejeitada." }

.\.venv-radiology\Scripts\python.exe -m atlas.radiology viewer `
  ".\data\radiology-lab\pesquisa-001\case.json" `
  --output ".\data\radiology-lab\pesquisa-001\viewer"
if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar visualizador." }
Start-Process ".\data\radiology-lab\pesquisa-001\viewer\index.html"
```

Use `--side R` para o lado direito. Esses caminhos são exemplos. Não atribua
`synthetic` a exames reais. Os rótulos AP/LATERAL/OBLIQUE são declarados pelo
operador; ainda não há identificação automática das projeções ou da anatomia.

Para repetir somente testes e Ruff após qualquer alteração:

```powershell
.\.venv-radiology\Scripts\python.exe -m pytest atlas/tests/test_radiology_cases.py atlas/tests/test_radiology_imaging.py -q
if ($LASTEXITCODE -ne 0) { throw "Falha no pytest." }
.\.venv-radiology\Scripts\python.exe -m ruff check atlas/radiology atlas/tests/test_radiology_cases.py atlas/tests/test_radiology_imaging.py
if ($LASTEXITCODE -ne 0) { throw "Falha no Ruff." }
```

## Dados e limitações

Esta entrega **não anonimiza exames**. As cópias originais conservam os metadados.
Embora os relatórios e as prévias não copiem tags identificadoras, identificação
gravada nos pixels pode continuar visível. O HTML incorpora essas prévias: trate-o
com o mesmo cuidado dos exames e não o compartilhe como se fosse anonimizado.
A etapa seguinte implementará o fluxo próprio de desidentificação e revisão.

Não há reconstrução 3D, laudo, diagnóstico, medição anatômica ou validação clínica.
São arquivos de pesquisa e uma base técnica para as próximas etapas. A leitura
dos pixels não comprova qualidade diagnóstica, orientação clínica ou calibração.

Referências técnicas consultadas:
- https://pydicom.github.io/pydicom/stable/reference/pixels.html
- https://pydicom.github.io/pydicom/stable/reference/generated/pydicom.pixels.apply_voi_lut.html
- https://pillow.readthedocs.io/en/stable/handbook/security.html
