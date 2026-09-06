# Hotfix — Executive Report Latest Sort

Corrige a função `load_latest_value_report()` para escolher o relatório mais recente pelo timestamp presente no nome do arquivo, e não pelo `st_mtime` do sistema de arquivos.

## Arquivo alterado

- `atlas/integrations/business_lab/executive_report.py`

## Motivo

Em alguns ambientes Windows, dois arquivos criados muito rapidamente podem ficar com `mtime` igual ou impreciso. O teste cria:

- `business_lab_value_report_20260905_010000.json`
- `business_lab_value_report_20260905_020000.json`

A função deve escolher o `020000`, ou seja, o mais recente pelo timestamp do nome.
