# Instagram Login — adaptador HTTP isolado

Continuação funcional da PR #103, sem frontend, credenciais reais, persistência,
endpoints públicos ou transporte de rede instalado. Não é OAuth completo nem
integração homologada com a Meta. O laboratório fictício existente foi preservado.

## Contrato de integração

`python-service/instagram_meta_adapter.py` exige `transport(ProviderRequest) ->
ProviderResponse`, callback HTTPS registrado, ID/segredo de app e versão Graph
explícitos. Não lê variáveis de ambiente e não tem cliente HTTP padrão. Importar
ou iniciar a aplicação não habilita operações externas.

- `exchange_code(code, required_scopes=...)`: POST com formulário ao host fixo
  `api.instagram.com/oauth/access_token`; valida um único grant no envelope
  `data`, ID, permissões e prazo curto. Só deve receber um código depois do
  consumo durável do state vinculado à sessão/workspace/usuário.
- `get_identity(grant)`: consulta `/me` no `graph.instagram.com`, exige conta
  BUSINESS/MEDIA_CREATOR e igualdade estrita com o ID recebido na troca. A
  compatibilidade dos namespaces de ID precisa ser comprovada em staging;
  diferenças são recusadas, nunca compensadas por nome ou workspace do browser.
- `extend_token(grant)`: troca token curto por longo, preservando identidade e
  scopes previamente validados. Prazo recebido deve ser positivo e até 60 dias.
- `refresh_token(grant)`: exige token longo ainda válido, com pelo menos 24 horas
  e permissão básica; valida a resposta sem realizar retry automático.

`ProviderRequest` separa URL fixa de parâmetros/formulário sensíveis. `TokenGrant`,
respostas e identidade omitem segredos/dados pessoais de `repr`. **Esses objetos
não são DTOs públicos:** não serializar com `asdict`, não devolver ao frontend,
não registrar query/form/body nem encaminhar ao n8n.

O transporte futuro é uma fronteira de confiança: deve respeitar timeout de 10s,
limite de 32 KiB durante streaming/descompressão, TLS, hosts fixos, redirects
proibidos e zero retries automáticos. A verificação após recebimento não impede
um transporte mal implementado de alocar um corpo excessivo antes da validação.
Não usar hooks de log de URLs completas: os endpoints de token documentados
pela Meta carregam valores sensíveis nos parâmetros internos do transporte.

## Erros e recuperação

Erros locais não incluem corpo do provedor, código, token ou exceção original.
`status_code`, `retry_after` inteiro limitado a 1–3600s, `retryable` e
`outcome_unknown` permitem que a futura fila decida o próximo passo. Datas HTTP
em Retry-After ainda não são interpretadas; nenhum atraso produz retry sozinho.
Somente leitura de identidade admite metadado de retry em429/5xx. Código OAuth,
extensão e renovação nunca são repetidos automaticamente. Resultado inutilizável
após troca de código é desconhecido; iniciar nova autorização, não reenviar o
mesmo código. O erro não afirma que uma operação remota deixou de acontecer.

## Verificação

Fixtures sintéticas e transporte determinístico, sem socket ou conta externa:

```sh
python -m unittest discover -s python-service -p 'test_instagram_meta_*.py' -v
```

27 testes focados passaram: oito existentes e19 novos. A suite backend local
registrou280 testes:112 passaram e168 skips por ausência de PostgreSQL. Não contar
skips como passes. PostgreSQL/Docker e regressão Node/browser completos dependem
do CI no head final. A imagem/versão runtime da produção não foi consultada.

Uma revisão independente encontrou validação de tipo ausente em `account_type`
e `TokenGrant.kind`; testes reproduziram TypeError e a correção preserva
ProviderError sanitizado. Também tornou explícito o resultado desconhecido de
respostas inutilizáveis na troca. Nenhuma assertiva antiga foi removida.

## Fontes e limites oficiais

Em23/10/2026, páginas diretas da Meta retornaram429. Documentação oficial indexada
pelo Context7 foi consultada:

- [Business Login](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/business-login): troca, permissões, extensão e renovação.
- [Me](https://developers.facebook.com/documentation/instagram-platform/reference/me): identidade por token.

Não misturar Facebook Login, hosts ou scopes de outro produto. A versão usada
nas fixtures não é uma escolha de versão homologada para produção. App Review,
Advanced Access, tipos de conta elegíveis e contratos reais de respostas exigem
validação com app/contas de teste expressamente autorizados.

## Próxima unidade

State Meta real durável de uso único, token vault criptografado fora do frontend,
account binding exclusivo por negócio e testes com dois workspaces em banco
isolado. Depois: webhooks autenticados com ledger, Caixa existente, outbox e
worker. Até lá, sem callback público, feature flag de provedor real, conexão de
contas, Direct, envio, publicação ou alegação de persistência de tokens.

A mudança de CI adiciona apenas as bases das PRs dependentes à lista de
`pull_request.branches`; mantém jobs, assertivas e permissões `contents: read`.
Não altera workflows de deploy nem administra o GitHub.
