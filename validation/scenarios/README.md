# Scenario Catalog

Arquivos JSON declarativos usados pelo Atlas Validation Lab.

Campos obrigatórios: `id`, `title`, `domain`, `execution`.

`execution` aceita `automated`, `manual` ou `planned`.

Checks automatizados disponíveis nesta fundação:

- `path_exists`
- `path_not_exists`
- `text_contains`
- `text_not_contains`

Novos checks devem ser determinísticos, não destrutivos e testáveis sem depender de serviços externos.
