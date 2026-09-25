# Etapa 8 — Infraestrutura de referência, projeções e comparação

Esta entrega prepara o caminho para usar CT como referência e avaliar modelos.
Ela inclui importação de volume numérico canônico, projeções aproximadas por
integração de raios, comparação de máscaras 3D e auditoria de divisões de dados.
O LAB usa exclusivamente um fantoma sintético. **Não inclui importador direto
de séries DICOM CT, dataset clínico, treinamento ou modelo neural pronto.**
A avaliação com dados reais e modelos neurais permanece pendente dessas entradas.
Aplicativo final e conexões continuam para depois das 12 etapas.

## Instalar e validar

Extraia o patch na raiz de atlas_OFICIAL, substituindo os arquivos do pacote.

```powershell
cd "C:\PROJETOS NEXYRA + ATLAS\atlas_OFICIAL"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\radiology_stage8.ps1
if ($LASTEXITCODE -ne 0) { throw "Falha na Etapa 8." }
```

O script executa pytest das Etapas 1–8, Ruff e pip check, gera um LAB novo e abre
a pasta de resultados. Não precisa de Docker, GPU, PyTorch ou dependências novas.

## Entrada de referência

Arquivo NPZ contendo **somente** os quatro arrays abaixo, sem objetos Python:

| Array | Contrato |
| --- | --- |
| hu | Volume [x,y,z], numérico, HU de -1024 a 10000 |
| reference_mask | Mesma grade, máscara binária 0/1, não vazia, de uma estrutura |
| origin_lps_mm | Vetor [x,y,z] do canto inferior da célula [0,0,0], em mm |
| spacing_mm | Vetor positivo [sx,sy,sz], entre 0,25 e 20 mm |

Eixos alinhados com LPS: X esquerda, Y posterior, Z superior. O centro de uma
célula é `origin + (índice + 0.5) * spacing`. Arrays de 2 a 128 células por eixo.
NPZ de até 32 MiB, cada membro descompactado de até 16 MiB. Cabeçalhos e tamanho
de alocação são conferidos antes do carregamento; pickle e campos extras rejeitados.

Um volume externo precisa ser convertido e reorientado corretamente antes de
entrar. Não confunda índice [slice,row,column] com [x,y,z], nem posição do centro
do primeiro voxel com o canto usado neste contrato. Volumes oblíquos requerem
reamostragem externa documentada, que este módulo não executa automaticamente.

HU não é o valor bruto do pixel DICOM: sua transformação depende dos metadados
da aquisição. A conversão de séries CT, ordenação das fatias, orientação,
espaçamento e máscara de referência precisam de conferência própria. Não use
imagens PNG de visualização ou intensidades CBCT não calibradas como HU.

Exemplo estrutural de gravação após uma conversão já validada:

```python
np.savez_compressed(
    "volume_canonico.npz", hu=volume_hu_xyz,
    reference_mask=mascara_binaria_xyz,
    origin_lps_mm=canto_inferior_lps_mm, spacing_mm=espacamento_xyz_mm,
)
```

Para registrar dados reais autorizados, use um código pseudônimo:

```powershell
$Python = ".\.venv-radiology\Scripts\python.exe"
& $Python -m atlas.radiology reference-import .\volume_canonico.npz --subject S001 --split test --authorized --privacy-reviewed --output .\data\radiology-lab\referencia-S001
if ($LASTEXITCODE -ne 0) { throw "Referencia rejeitada." }
```

As opções registram declarações do operador; não verificam documentos nem
anonimizam dados. Volume, máscara e código podem continuar sendo identificáveis.
Guarde-os em ambiente de pesquisa restrito. Originais não são modificados.

## Projeções sintéticas aproximadas

Use câmeras virtuais no contrato da Etapa 5, `origin: synthetic`, com detector
até 256×256. O geometry.json do LAB desta etapa já está nesse formato.

```powershell
& $Python -m atlas.radiology reference-project .\data\radiology-lab\referencia-S001\reference.json --geometry .\cameras-virtuais.json --step-mm 1 --water-mu 0.02 --output .\data\radiology-lab\projecoes-S001
if ($LASTEXITCODE -ne 0) { throw "Falha nas projecoes." }
```

O simulador integra ao longo do trecho de cada raio dentro do volume, por
amostras no ponto médio, usando o voxel mais próximo. Modelo simplificado:
`mu = max(1 + HU/1000, 0) * water_mu`, `I/I0 = exp(-integral(mu ds))`.
water_mu tem unidade mm^-1; 0,02 é um parâmetro experimental, não calibração de
um aparelho ou espectro específico. O passo é limitado a 0,25–10 mm e até 1024
amostras por raio. Amostragem grossa pode perder estruturas finas.

PNG usa escala fixa: transmissão 1 branca, 0 preta. NPZ conserva integral de
linha e transmissão float32. Não modela espalhamento, espectro policromático,
ruído, detector ou pós-processamento de radiografia. É uma aproximação de DRR,
não reprodução fiel de um exame. Não implementa Siddon ou diferenciação automática.
O corpo fora do volume é tratado como ausência de material.

## Comparar resultados 3D

Para a saída da Etapa 7, converta explicitamente para o contrato de comparação:

```powershell
& $Python -m atlas.radiology reference-adapt-stage7 .\resultado-etapa7\volume.npz --output .\predicao-baseline.npz
if ($LASTEXITCODE -ne 0) { throw "Falha na conversao." }
& $Python -m atlas.radiology reference-compare .\referencia\reference.json --prediction .\predicao-baseline.npz --output .\comparacao-baseline.json
if ($LASTEXITCODE -ne 0) { throw "Comparacao rejeitada." }
```

Uma predição externa, inclusive neural, deve conter somente `prediction` binária,
`origin_lps_mm` e `spacing_mm`. Limiarize probabilidades externamente e registre
o limiar no seu protocolo. Forma, origem e espaçamento precisam coincidir
exatamente com a referência; não há registro ou reamostragem automáticos.

Relatório: Dice, IoU, precisão, recall, falsos positivos/negativos, volumes e erro
assinado de volume. Referência vazia é rejeitada. Predição vazia tem Dice/IoU 0
e precisão null. Não calcula distância de superfície, identifica modelo ou prova
qualidade clínica. Use arquivos de saída novos e preserve a procedência do modelo.

## Separação de treino, validação e teste

```powershell
& $Python -m atlas.radiology reference-audit .\ref-treino\reference.json .\ref-teste\reference.json --output .\dataset-audit.json
if ($LASTEXITCODE -ne 0) { throw "Sobreposicao ou referencia invalida." }
```

Bloqueia o mesmo código de sujeito em divisões diferentes e volumes numericamente
idênticos, mesmo com compressão/dtype diferente. Não reconhece que códigos distintos
representam a mesma pessoa nem detecta todo derivado reamostrado. Mantenha um
cadastro consistente por sujeito; códigos e divisões devem ser definidos antes do
treinamento. A ferramenta valida até 1000 referências por chamada.

## O que o LAB entrega

- Baseline geométrico da Etapa 7 e sua máscara predita.
- Fantoma em HU artificiais: elipsoide uniforme de 1000 HU, exterior -1000 HU.
- Referência binária e projeções aproximadas AP/LATERAL/OBLIQUE.
- Comparação baseline × referência e auditoria de uma referência sintética.
- `lab-report.json` explicita que não houve CT real nem treinamento neural.

Para completar a avaliação neural desta etapa, ainda faltam dataset autorizado,
máscaras revisadas, partições independentes e predições de um modelo treinado.
O teste sintético valida funcionamento, não generalização anatômica.

Referências técnicas:
https://dicom.nema.org/medical/dicom/2025e/output/chtml/part03/sect_C.8.15.3.10.html
https://arxiv.org/abs/2208.12737

Próxima etapa do roadmap: visualizador integrado RX ↔ 3D. As pendências de dados
reais e treinamento acima devem continuar registradas mesmo ao avançar no software.
