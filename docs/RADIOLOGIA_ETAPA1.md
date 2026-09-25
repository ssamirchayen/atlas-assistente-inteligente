# Atlas Radiologia — RX 3D — Etapa 1

Esta é a fundação do módulo Radiologia/Saúde, uma única frente do roadmap com
etapas internas. Não renumera as sprints do Atlas. Atlas Dev permanece previsto
após Radiologia; os demais módulos (Educação, Comércio, Logística, Industrial,
Financeiro e RH) mantêm suas frentes próprias.

## Entrega desta etapa

- Pacote independente `atlas/radiology`, sem dependências adicionais de execução.
- Contrato versionado de casos, com três projeções: AP, LATERAL e OBLIQUE.
- Conferência de estudo e lado declarados, referências de arquivo e SHA-256.
- Rejeição de imagens repetidas, arquivos ausentes, caminhos externos, links
  simbólicos, chaves JSON repetidas e campos não previstos.
- Limite de 256 KiB para manifesto e 50 MiB por imagem.
- Registro opcional de matrizes de projeção: verifica formato, números finitos e
  degeneração básica da câmera; NÃO verifica a calibração física.
- CLI local, demonstração com padrões PNG e laboratório inicial de testes.
- Script PowerShell para instalar ferramentas em ambiente separado, executar
  pytest/Ruff e criar um caso sintético novo a cada execução.

A estrutura foi conferida no pacote `Atlas_OFICIAL(9).zip`, disponibilizado em
08/09/2026. Ele contém o agente consultivo `atlas/agents/radiology.py`. Este patch
acrescenta arquivos novos; não altera esse agente, o roteador de comandos, a voz,
a interface, as dependências principais, o CRM ou seu banco. Não declara validar
uma instalação do Atlas modificada posteriormente em outros chats.

## Instalação no Windows

Extraia o ZIP na raiz do **Atlas**, onde ficam `atlas/`, `tools/` e `gui_main.py`.
Não crie uma segunda pasta `atlas` dentro da pasta `atlas` existente.

Abra o PowerShell nessa raiz e execute, com Python 3.13 instalado:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\radiology_stage1.ps1
if ($LASTEXITCODE -ne 0) { throw "Falha na Etapa 1 da Radiologia." }
```

O script usa `.venv-radiology` e não depende de ativar ambientes virtuais nem de
Docker. Os padrões ficam em `data/radiology-lab/etapa1-<identificador>/`.

Comandos individuais, após a instalação das ferramentas:

```powershell
.\.venv-radiology\Scripts\python.exe -m pytest atlas/tests/test_radiology_cases.py -q
if ($LASTEXITCODE -ne 0) { throw "Falha no pytest." }
.\.venv-radiology\Scripts\python.exe -m ruff check atlas/radiology atlas/tests/test_radiology_cases.py
if ($LASTEXITCODE -ne 0) { throw "Falha no Ruff." }
.\.venv-radiology\Scripts\python.exe -m atlas.radiology demo --output .\data\meu-primeiro-caso
if ($LASTEXITCODE -ne 0) { throw "Falha na demonstracao. Use uma pasta ainda inexistente." }
.\.venv-radiology\Scripts\python.exe -m atlas.radiology validate .\data\meu-primeiro-caso\case.json
if ($LASTEXITCODE -ne 0) { throw "Caso rejeitado." }
```

Os testes acima são específicos desta entrega. A suíte completa do Atlas possui
suas próprias dependências e deverá continuar sendo executada no ambiente
principal quando houver alteração de componentes compartilhados.

## Como interpretar a demonstração

Os três PNG são **padrões artificiais de teste**, não radiografias, projeções
simuladas de um osso, reconstrução ou dados de treinamento. Servem para conferir
o fluxo de arquivos e contratos. Não é necessário enviar exames de pacientes.

Resultado esperado:

```json
{
  "status": "files_and_manifest_valid",
  "geometry_status": "missing",
  "reconstruction_available": false,
  "clinical_use_validated": false
}
```

`files_and_manifest_valid` significa estrutura do manifesto, assinatura inicial
do arquivo e integridade conferidas. Não comprova que os pixels sejam decodificáveis,
que o rótulo AP esteja correto, que seja o mesmo paciente ou que os dados estejam
anonimizados. A validação de estudo e lado compara apenas as declarações do JSON.

Quando todas as matrizes são informadas, o estado é `declared_not_verified`.
Mesmo matrizes individualmente válidas podem ser incompatíveis entre si ou com
a aquisição: nesta etapa não há recuperação de escala, verificação entre câmeras,
registro, calibração nem autorização para medir anatomia.

O reconhecimento `.dcm` exige preâmbulo e marcador DICM. Datasets DICOM sem esse
encapsulamento serão rejeitados nesta etapa; sua leitura especializada virá na
Etapa 2. JPEG/PNG também têm somente a assinatura inicial conferida aqui.

## Contrato do caso

O arquivo `case.json` define:

| Campo | Regra |
|---|---|
| `schema_version` | Inteiro 1. |
| `case_id`, `study_id` | Identificadores opacos, até 80 caracteres; não inserir nome ou documento de paciente. |
| `region` | `knee_lower_leg`. |
| `laterality` | `L` ou `R`. |
| `data_origin` | `synthetic` ou `research`; esta declaração não comprova anonimização. |
| `views` | Exatamente AP, LATERAL e OBLIQUE, sem duplicatas. |

Cada entrada de `views` possui `view`, `relative_path`, `sha256`, `study_id`,
`laterality` e `geometry`. Os caminhos usam `/`, são relativos à pasta do manifesto
e devem apontar a arquivos existentes dentro dela. SHA-256 detecta alteração em
relação ao manifesto; não autentica o autor nem protege contra alguém que altere
simultaneamente imagem e manifesto.

`geometry` é `null` nas três vistas ou contém, nas três:
- `calibration_id`: identificador comum de uma calibração declarada;
- `coordinate_system`: `LPS_mm`, convenção de coordenadas do objeto;
- `projection_matrix`: matriz de câmera perspectiva 3×4. A relação planejada é
  `s [u, v, 1]^T = P [x, y, z, 1]^T`, com coordenadas do objeto em mm e da imagem
  em pixels. Escala e convenção precisam corresponder à aquisição real.

Não transforme uma calibração ausente em válida preenchendo uma matriz arbitrária.
Nenhum texto livre de paciente é previsto no contrato. Dados de origem `research`
sempre retornam `privacy_review_required: true`; não existe anonimização automática
nesta entrega. Relatórios e erros de CLI omitem caminhos e identificadores do caso.

## Etapas internas seguintes

1. **Fundação e casos — esta entrega.**
2. Importação e decodificação DICOM/PNG/JPEG, metadados e visualização 2D.
3. Desidentificação e rastreabilidade, incluindo informações nos pixels.
4. Qualidade, projeções e lateralidade, com revisão manual.
5. Geometria física e calibração multivista.
6. Segmentação, pontos anatômicos e correção manual.
7. Primeiro reconstrutor geométrico/estatístico em casos controlados.
8. Dados de CT autorizados, projeções sintéticas e comparação de modelo neural.
9. Visualizador com correspondência RX ↔ 3D.
10. Erros, discrepâncias e avaliação de incerteza.
11. Exportações e operação pelo Atlas.
12. Validação independente e piloto de pesquisa.

Escopo anatômico planejado: fêmur distal, tíbia, fíbula e patela. A reconstrução
será estimada, sem equivalência a tomografia. A entrega atual não gera mesh,
diagnóstico, laudo, medições anatômicas ou resultado clínico. Fraturas e
deformidades exigirão avaliação específica para impedir que um modelo anatômico
oculte alterações reais.
