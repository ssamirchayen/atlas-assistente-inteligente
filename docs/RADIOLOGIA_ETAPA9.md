# Etapa 9 — Visualizador integrado imagens ↔ 3D

Ferramenta local de pesquisa da sprint. Não é o aplicativo final e não cria
conexões, API ou base central. O plano continua: aplicativo após as 12 etapas.

## Executar

Extraia sobre a pasta atlas_OFICIAL, preservando todos os arquivos do pacote.

```powershell
cd "C:\PROJETOS NEXYRA + ATLAS\atlas_OFICIAL"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\radiology_stage9.ps1
if ($LASTEXITCODE -ne 0) { throw "Falha na Etapa 9." }
```

O script executa pytest das Etapas 1–9, Ruff, pip check, gera nova reconstrução
sintética e abre o visualizador. Sem servidor, Docker ou CDN. Node, quando no
PATH, permite executar o teste matemático JavaScript adicional; sem ele esse
teste é ignorado. O visualizador em si só precisa de navegador com JavaScript.

## Interagir

- Arraste a malha ou use Giro/Inclinação. Zoom ajusta a exibição; Arestas mostra
  os triângulos. Restaurar vista volta aos controles iniciais.
- Clique na superfície 3D: o ponto escolhido aparece em coordenadas LPS/mm e é
  projetado sobre AP, LATERAL e OBLIQUE, com coordenadas u/v em pixels.
- Clique numa imagem: seleciona a primeira interseção positiva do raio com a
  superfície da malha e mostra o mesmo ponto nas outras vistas.
- Limpar seleção remove os marcadores. Um clique sem interseção na imagem
  informa que o raio não encontra a malha estimada.

O LAB contém um elipsoide e silhuetas sintéticas, não ossos ou RX de pacientes.
Em caso de pesquisa, as três imagens exibidas são as prévias da origem importada.

## O que o vínculo significa

O cálculo usa a matriz de projeção fornecida, com interpolação em perspectiva
para selecionar a superfície pelo clique 2D. O 3D é exibido em projeção
ortográfica para inspeção, com referência LPS: esquerda, posterior e superior.
Os marcadores indicam compatibilidade geométrica, **não correspondência anatômica
confirmada**. A primeira superfície no raio pode não ser a estrutura de interesse;
há ambiguidade de profundidade e sobreposição nas radiografias.

O marcador projetado pode corresponder a uma superfície oculta atrás de outra
naquela vista. Não é um mapa de confiança, diagnóstico ou medida clínica.
Não há segmentação, suavização, edição da malha ou reconstrução nova no HTML.
A visualização usa desenho de triângulos ordenados por profundidade; é uma
ferramenta de inspeção do protótipo, não renderizador médico certificado.

## Resultados de etapas anteriores

A Etapa 9 acrescenta hashes de malha e volume aos novos relatórios da reconstrução.
Resultados antigos sem `mesh_sha256` são rejeitados: gere uma nova reconstrução
após instalar este patch. Isso preserva o resultado antigo e vincula os artefatos.
O script de demonstração faz essa geração automaticamente.

Para seu próprio caso compatível, primeiro repita o comando `reconstruct` da
Etapa 7 para uma pasta nova. Depois:

```powershell
$Python = ".\.venv-radiology\Scripts\python.exe"
& $Python -m atlas.radiology linked-viewer "C:\CASO\case.json" --geometry "C:\CASO\geometry.json" --result "C:\CASO\reconstrucao-nova" --output "C:\CASO\visualizador-novo"
if ($LASTEXITCODE -ne 0) { throw "Visualizador rejeitado. Confira a mensagem." }
Start-Process "C:\CASO\visualizador-novo\index.html"
```

Confere hashes do manifesto, geometria e malha. Não carrega arquivos externos
referenciados em OBJ, texturas ou materiais. Aceita apenas o subconjunto de
malha triangular exportado pelo módulo, com até 100000 vértices/triângulos.
Uma malha mais complexa exige reconstrução com voxel maior neste protótipo.

Mantém a restrição da Etapa 7: prévia sem redução, resolução igual à geometria,
sem rotação/espelhamento EXIF. Não infere transformações para corrigir entradas
incompatíveis. Arquivos de saída exigem pasta nova; originais permanecem intactos.

`roi_boundary_warning` é mostrado como aviso no visualizador, pois a reconstrução
pode ter sido cortada pela região de busca. Não representa aprovação do resultado.
Hashes detectam alterações acidentais, não são assinatura contra um operador que
possa editar tanto artefatos quanto relatórios.

## Privacidade e pendências

O index.html incorpora imagens e malha para funcionar offline. Ele pode conter
informação identificável nos pixels e na anatomia; mantenha-o restrito. Não usa
serviços de rede, não anonimiza os originais e não substitui a Etapa 3.

Continuam pendentes da Etapa 8: séries DICOM CT, dados reais autorizados e modelo
neural treinado. O visualizador não transforma essas pendências em validações.
Próxima etapa: avaliação de erros, incerteza e critérios de rejeição.
