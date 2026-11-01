# Publicações da conta Instagram conectada

Implementação local após `0054a04`, sem implantação automática.

- Botão **Ver publicações** nas integrações e no módulo Divulgação.
- `GET /api/v1/instagram/media`, com `after` opcional: até cinco publicações por página, incluindo os campos que a Meta retornar. Legendas ausentes e imagens indisponíveis permanecem identificadas na interface.
- Reutiliza OAuth, conexão e cofre existentes. Exige conexão válida e `instagram_business_basic`; leitura permitida a owner/admin/member/viewer do workspace autenticado. `report_viewer` não acessa o canal.
- A leitura funciona com envio de Direct e publicação desativados. Só consulta o provedor quando o usuário solicita.
- Não permite escolher conta/token/URL pelo navegador. Cursores são validados; o backend constrói a próxima consulta, sem seguir ou expor `paging.next`.
- URLs de imagens aceitam somente HTTPS de CDNs Meta e links para publicações Instagram. Legendas usam texto; tokens e respostas privadas não são incluídos em erros.
- O limite existente de resposta do provedor permanece em 32 KB. Respostas acima desse limite falham explicitamente; não são transformadas em uma lista vazia.

Testes usam PostgreSQL descartável e provedor simulado. A leitura real é uma evidência separada, registrada de forma sanitizada em `.preview/aws-instagram-media-read.json`, sem conteúdo das publicações ou credenciais.

Depois da implantação autorizada, abrir **Configurações → Integrações → Instagram → Ver publicações**. A consulta não envia Direct nem publica conteúdo.
