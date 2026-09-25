# Etapa 10 — sensibilidade e rejeição para revisão de pesquisa

Extraia o patch na raiz do Atlas. Execute:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\radiology_stage10.ps1
if ($LASTEXITCODE -ne 0) { throw "Falha na Etapa 10." }
```

O script roda pytest e Ruff, gera um elipsoide sintético e grava assessment.json
e sensitivity.npz. Não usa imagens de pacientes. Não é o aplicativo final.
Neste LAB, a faixa sensível é aproximadamente 54,08%: o resultado é rejeitado
por high_contour_sensitivity. Isso demonstra o critério funcionando. O script
termina com sucesso após mostrar a rejeição; não significa aprovação do modelo.

O avaliador reconstrói novamente os dados validados. Erode e dilata os contornos
das três vistas com uma janela quadrada de raio 1 pixel (configurável de 1 a 3).
Calcula três envelopes na mesma grade: núcleo erodido, nominal e expandido.
A diferença entre expandido e núcleo é a faixa sensível, exportada como máscara
3D booleana. Não é probabilidade, intervalo de confiança ou mapa clínico.
Pixels fora do detector são tratados como fundo; contornos próximos da borda
geram rejeição. O método não altera a calibração nem mede sua incerteza.

Política experimental contour_screen_v1, sem validação clínica dos limiares:

- núcleo erodido vazio;
- faixa sensível maior que 50% do envelope expandido;
- envelope expandido encosta na borda da região reconstruída;
- contorno a até raio+1 pixels da borda do detector;
- IoU de reprojeção menor que 0,70 ou cobertura menor que 0,80 em qualquer vista.

Essas condições produzem rejected_for_research_review e código de saída 2.
Sem condições, o estado é research_review_required e código 0: ainda exige
revisão humana. Código 1 indica entrada inválida ou erro operacional.
Um resultado rejeitado mantém seu relatório e máscaras para investigação.
Não há aprovação clínica automática e não foram adicionados bloqueios aos
visualizadores anteriores. Futuras exportações deverão consultar a avaliação.

Uso em outro caso (arquivos previamente preparados nas etapas anteriores):

```powershell
& .\.venv-radiology\Scripts\python.exe -m atlas.radiology sensitivity .\caso\case.json --annotation .\annotations.json --geometry .\geometry.json --settings .\reconstruction-settings.json --radius-px 1 --output .\avaliacao_nova
```

O NPZ contém core, nominal, outer, sensitive_shell, origin_lps_mm e voxel_size_mm.
Eixos e unidades seguem a grade LPS/mm. assessment.json vincula entradas e NPZ
por SHA-256; isso não é assinatura digital. Use pasta nova, sem sobrescrever.

A reprojeção reutiliza os contornos de entrada; não é validação independente.
Fraturas, lesões, anatomia, erros sistemáticos e preservação de detalhes não são
verificados. O visualizador da Etapa 9 não colore esta máscara automaticamente.
Dados CT reais autorizados e treino neural da Etapa 8 continuam pendentes.
Próxima: Etapa 11, exportações e preparação de integração. Aplicativo final e
conexões continuam após as 12 etapas.
