# Radiologia — Etapa 3: privacidade e rastreabilidade

Instale este patch sobre as Etapas 1 e 2 na pasta `atlas_OFICIAL`.
Não altera CRM, banco de dados ou imagens originais.

## Validação no Windows

```powershell
cd "C:\PROJETOS NEXYRA + ATLAS\atlas_OFICIAL"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\radiology_stage3.ps1
if ($LASTEXITCODE -ne 0) { throw "Falha na Etapa 3." }
```

O script instala as mesmas dependências travadas, roda pip check, pytest das
Etapas 1–3, Ruff e prepara um LAB sintético em uma pasta nova. Abre a revisão
no navegador; não aprova imagens automaticamente. Os padrões do LAB não são RX.

## Escopo e limites

Este fluxo gera **derivados PNG de visualização, 8 bits e até 1600 pixels**.
Recria apenas pixels, sem copiar EXIF, tags DICOM, nomes, UIDs, datas ou campos
privados. Não gera DICOM desidentificado nem preserva a precisão necessária para
reconstrução quantitativa. Geometria não é transferida a essas cópias reduzidas.
Os originais continuam disponíveis no caso de origem para as próximas etapas.

A limpeza de metadados não remove texto desenhado nos pixels. A revisão humana
das três vistas é obrigatória para o comando de exportação. Máscaras substituem
pixels por preto de modo permanente nas cópias. Não são sobreposições visuais.
Não há OCR automático, garantia de anonimato ou conformidade DICOM PS3.15
certificada. Características visuais também podem permitir identificação.
Não use esses derivados para diagnóstico, medidas ou reconstrução 3D.

O registro local identifica o operador por código e data UTC. SHA-256 vincula
origem, máscaras, derivados e revisão; detecta mudanças acidentais, mas **não é
assinatura digital, autenticação do operador nem trilha inviolável**. Quem tem
acesso de escrita pode fabricar registros. Proteja a pasta por permissões locais.

## Revisão do LAB gerado

Copie a pasta de revisão exibida pelo script para `$Pasta` abaixo (sem usar os
caracteres de exemplo). Examine `review.html` e cada PNG em tamanho real, usando
rolagem para todas as bordas. Verifique nomes, datas, prontuários, códigos de
barras e outras informações identificáveis. Só marque clear após revisar.

```powershell
$Python = ".\.venv-radiology\Scripts\python.exe"
$Pasta = "C:\CAMINHO-EXIBIDO-PELO-SCRIPT\privacy"
$Revisao = Join-Path $Pasta ("review-" + [guid]::NewGuid().ToString("N") + ".json")
& $Python -m atlas.radiology privacy-review $Pasta --reviewer OP01 --ap clear --lateral clear --oblique clear --output $Revisao
if ($LASTEXITCODE -ne 0) { throw "Falha ao registrar revisao." }
$Exportacao = Join-Path (Split-Path $Pasta) ("export-" + [guid]::NewGuid().ToString("N"))
& $Python -m atlas.radiology privacy-export $Pasta --review $Revisao --output $Exportacao
if ($LASTEXITCODE -ne 0) { throw "Exportacao bloqueada." }
```

Use `reject` na vista com identificação ou dúvida. Uma única rejeição bloqueia
a exportação. Cada registro exige um arquivo novo; não sobrescreva revisões.

## Corrigir informações nos pixels

Prepare um JSON com retângulos nas coordenadas **dos PNGs de revisão**, não do
DICOM original. `[x0,y0,x1,y1]` usa origem no canto superior esquerdo; limites
direito e inferior exclusivos. Exemplo de sintaxe (não aplicar sem conferir):

```json
{"AP": [[0, 0, 120, 30]], "LATERAL": [], "OBLIQUE": []}
```

Salve como `mascaras.json` e prepare uma **nova pasta** a partir do caso original:

```powershell
& $Python -m atlas.radiology privacy-prepare "C:\CAMINHO-DO-CASO\case.json" --masks .\mascaras.json --output .\data\radiology-lab\revisao-corrigida-01
if ($LASTEXITCODE -ne 0) { throw "Falha ao aplicar mascaras." }
```

Abra o novo `review.html`, confira a limpeza e registre nova revisão. Evite
mascarar anatomia; se não conseguir remover identificação sem perda relevante,
rejeite a cópia. Alterar imagens, manifesto ou rastreabilidade invalida a revisão.

## Arquivos e compartilhamento

- Caso original: preservado; pode conter identificação completa.
- Pasta privacy: PNGs pendentes, HTML, manifesto e `provenance-private.json`.
  Guarde localmente; contém hashes de origem e histórico de máscaras.
- Arquivo de revisão: código do operador, decisões por vista e vínculo SHA-256.
- Pasta export: somente três PNGs aprovados e `export.json`, com hashes dos
  derivados e identificadores aleatórios. Não inclui originais, HTML, hashes de
  origem, código do operador ou arquivos extras da pasta privada.

O identificador aleatório bundle_id permite vincular a exportação à trilha
local. Isso é rastreabilidade pseudônima, não garantia de anonimato irreversível.
O comando protege o fluxo normal; não impede cópias manuais pelo sistema operacional.

Referência técnica: DICOM PS3.15, opção Clean Pixel Data:
https://dicom.nema.org/medical/dicom/current/output/chtml/part15/sect_E.3.html

Próxima etapa do módulo: qualidade, projeções e lateralidade com revisão assistida.
