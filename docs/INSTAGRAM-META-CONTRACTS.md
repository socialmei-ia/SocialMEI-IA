# Instagram — contratos de segurança para a futura integração Meta

## Escopo desta entrega

Extensão **exclusivamente funcional** da PR #101 (laboratório fictício). Os arquivos
`python-service/instagram_meta_contract.py` e
`python-service/test_instagram_meta_contract.py` implementam e testam:

- Validação do **embed OAuth obtido no painel Instagram Login**: host HTTPS
  `instagram.com`, caminho esperado, `client_id`, redirect URI exatamente
  cadastrada, `response_type=code`, escopos mínimos sem composição arbitrária,
  parâmetros únicos e state URL-safe de alta entropia fornecido pelo chamador.
- Assinatura `X-Hub-Signature-256`: HMAC-SHA256 sobre **bytes originais**, tamanho
  máximo de 64 KiB e comparação em tempo constante. JSON não é interpretado
  antes de uma assinatura válida.
- Challenge de verificação de webhook: devolve o desafio somente se o modo e
  token configurado coincidirem, sem vazar o segredo.
- Inspeção inicial do envelope assinado: somente `object=instagram`, limite
  de entradas/eventos, IDs de conta bem formados e bloqueio de chaves JSON
  duplicadas. Retorna **apenas contagens**, sem inserir mensagens no banco.

**Não existem novas rotas HTTP**, novos segredos, token storage, migrações,
clientes de rede, callbacks públicos, mensagens enviadas ou publicação remota.
O módulo é passivo e não é carregado pela API em produção. O laboratório
`/api/v1/instagram/provider-lab` permanece isolado, desabilitado por padrão.

## Separação do Instagram Login e Facebook Login

Esta camada tem como contrato **Instagram API with Instagram Login**; não
usa scopes `business_*` antigos nem `instagram_basic` da modalidade
Facebook Login. Primeiro solicitar `instagram_business_basic` e incluir
`instagram_business_manage_messages` ou
`instagram_business_content_publish` **somente quando os recursos forem
aprovados e necessários**. O conjunto de scopes do embed deve corresponder
exatamente ao conjunto exigido para a operação.

Referência oficial: https://www.postman.com/meta/instagram/folder/6raa77c/instagram-api-with-instagram-login

## O que ainda falta para Instagram real

1. Confirmar conta profissional, aplicação Meta autorizada, API/versão,
   callback HTTPS e escopos concedidos/App Review. Não pedir segredo em chat.
2. Criar um registro durável, de uso único, para `state`, vinculado a sessão,
   usuário, workspace, prazo e redirect cadastrado; somente então expor OAuth.
3. Trocar código por token **no backend**, guardar token criptografado em cofre
   seguro e testar revogação/renovação sem logar valores nem colocá-los em URLs.
4. Expor webhook sob configuração desligada por padrão, validar o par
   app/conta/workspace e registrar eventos idempotentes em transação antes
   de fazer o mapeamento para `me_conversations` / `me_messages` existentes.
   Nunca inferir vínculo só pelo nome de contato.
5. Implementar outbox, retries, controle de janela de mensagens, revisão
   humana e auditoria; homologar com contas de teste autorizadas antes de
   habilitar envio/publicação real.
6. Preparar rollback e backup no ambiente autorizado, sem afetar n8n,
   WAHA, PostgreSQL ou o beta público nesta PR.

A inspeção de envelope **não autoriza processar payload pessoal**. Eventos sem
identidade confirmada, assinatura válida e vínculo de conta devem permanecer
rejeitados. Nunca combinar dados reais e fixtures do laboratório.

## Testes

`python -m unittest discover -s python-service -p 'test_instagram_meta_contract.py'`

Os testes não fazem solicitações de rede ou conexão ao banco, usam somente
segredos sintéticos e são incorporados à descoberta `test_*.py` do CI.

## Validação da PR dependente

A branch base desta PR é `feat/instagram-provider-lab` (PR #101), não `main`.
O CI deve ser verificado no SHA da PR #103, incluindo testes Python e demais
regressões. Um resultado verde da PR #101 não substitui esse gate.
