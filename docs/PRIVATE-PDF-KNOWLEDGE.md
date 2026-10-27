# PDFs privados e consulta por fontes

A base existente029 continua imutável. Os bytes originais, metadados e trechos ficam no PostgreSQL privado do próprio negócio, cobertos pelo dump do banco; não dependem do disco temporário do container. A flag `SOCIALMEI_KNOWLEDGE_PDF_ENABLED` segue desligada por padrão.

Em **Configurações → Perfil da IA → Documentos da IA**, o responsável pode enviar, baixar, substituir, reprocessar e excluir PDFs. A lista mostra nome, páginas, tamanho, data e estado. Busca e download exigem sessão/autorização; não há URL pública do arquivo. `report_viewer` não acessa documentos. Busca retorna trechos com documento/página, sem gerar afirmações ou executar instruções do conteúdo.

## Limites e processamento

- Até2MiB/PDF,100páginas,500trechos,500mil caracteres extraídos,25documentos por negócio.
- Extração em worker Python separado: máximo5s de CPU,8s de relógio,192MiB de espaço de memória,sem core dump/arquivos produzidos. Até2 extrações simultâneas por processo API. Requer Linux com `resource`; ambiente sem esses limites recusa o processamento.
- O worker recebe somente o PDF por stdin. Não herda `DATABASE_URL`, tokens Meta, SMTP ou outras variáveis privadas; stdout contém apenas o resultado e stderr não é publicado.
- Upload/armazenamento saem do event loop; nenhuma chamada externa de OCR/LLM/embeddings é realizada. PDFs criptografados, ações/JavaScript e anexos incorporados são recusados. Limites estourados retornam erro sanitizado.
- Arquivos sem texto extraível permanecem em `no_text`, com aviso de OCR necessário. OCR **não** foi implementado, e uma digitalização não vira conhecimento fictício.

## Contratos adicionais

`GET /api/v1/knowledge/pdf` inclui `size_bytes` e `sha256` além dos campos existentes.

`GET /api/v1/knowledge/pdf/{id}/download` exige acesso ao workspace e retorna attachment, `no-store`, `nosniff` e CSPsandbox.

`PUT /api/v1/knowledge/pdf/{id}?filename=...` recebe `application/pdf` e `If-Match` com sha256 conhecido. `POST /api/v1/knowledge/pdf/{id}/reprocess` recebe `{"sha256":"..."}`. Ambos exigem owner/admin, sessão, Origin e CSRF. O servidor confere novamente o hash/permissão sob trava antes de trocar bytes/trechos atomicamente. Conflito409 preserva o documento atual. Falha de parsing não apaga o índice anterior.

Substituição mantém o identificador do documento. Upload/substituição/reprocessamento/exclusão registram ator/ação na auditoria sem conteúdo PDF. Excluir remove bytes e trechos do banco ativo via FKcascade; cópias históricas em backups seguem a política privada de retenção. Não prometer apagar backups automaticamente.

## Estado verificado

Testes usam PDFs gerados, banco descartável e duas contas: persistência após novo login, referências de página, isolamento, leitura/restrição de escrita, substituição, índice anterior, conflitos, exclusão e download privado. Testes de navegador usam API controlada e verificam os controles nativos. São evidências de código; não implantação, OCR ou homologação de um modelo de IA.
