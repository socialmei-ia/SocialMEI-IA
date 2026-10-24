# Instagram — OAuth persistente preparado, operação externa fechada

Continuação funcional das PRs #104/#105, sem alteração visual. Reutiliza
`InstagramAdapter`, os contratos de Instagram Login e `TokenVault`; não substitui
nem habilita o laboratório fictício existente. Não é uma integração homologada
com uma conta real da Meta.

## Ativação e limites

Sem transporte, keyring ou configuração de produção padrão. A dependência
`instagram_persistent_oauth.oauth_service` responde 503 até uma aplicação de teste
injetar explicitamente `InstagramOAuthService`. Mesmo com a injeção, as rotas
exigem `SOCIALMEI_INSTAGRAM_OAUTH_MODE=isolated` e
`SOCIALMEI_INSTAGRAM_LAB_ENVIRONMENT=isolated`, além de autenticação ativa.
Nenhuma flag instala um cliente HTTP nem lê uma chave privada automaticamente.

O serviço recebe o adaptador HTTP já existente, vault/keyring e embed de
Instagram Login fornecidos pelo servidor. Callback e client ID devem corresponder
ao adaptador; escopos ficam na configuração, nunca no payload do navegador.
Não reutilizar credenciais n8n, fixtures ou tokens de Facebook Login.

Não há GET público de callback, bridge de frontend, worker, refresh automático,
webhook Meta, envio de Direct ou publicação. O retorno OAuth de um navegador
precisará de uma ponte própria revisada: ela encaminhará state/código/erro à rota
POST autenticada, preservando Origin/CSRF e sem registrar parâmetros sensíveis em
logs. Não expor uma rota GET que receba código em query sem revisar os logs do
proxy/API, cookies e a autorização da Meta. O callback HTTPS cadastrado deve ser
fixo e permitido; esta entrega não cadastra URL/app nem conecta contas.

## Endpoints preparados

Prefixo `/api/v1/instagram/meta`. Respostas mantêm `Cache-Control: no-store` pelo
middleware de contas. Não retornar código OAuth, token ou envelope criptografado.

| Método/caminho                | Contrato                                                                                                                                                                                |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| POST `/oauth/start`           | Corpo `{}`; owner/admin. Retorna state, authorization_url, expires_in=300 e provider.                                                                                                   |
| POST `/oauth/callback`        | `{state, callback_uri, code}` OU `{state, callback_uri, error}`; owner/admin e mesma sessão. Nunca os dois resultados. Erro/negação consome o state sem HTTP e responde 400 sanitizado. |
| GET `/status`                 | Membro autenticado; status, connection_id, tipo, escopos, expiração, revision, credential_available. Somente leitura; sem tokens nem nomes de conta.                                    |
| POST `/connection/disconnect` | Corpo `{}`; owner/admin. Cancela states, desconecta e remove ciphertext. `provider_revoked:false`: não revoga remotamente.                                                              |
| POST `/connection/rotate-key` | Corpo `{}`; owner/admin. Recriptografa localmente com a chave ativa, usando o keyring injetado. Falha de abertura não substitui o ciphertext anterior.                                  |

As escritas exigem sessão, Origin e CSRF existentes. Cada transação confere também
sessão não revogada/expirada, credencial ativa e membership atual no banco. O
workspace vem da identidade autenticada, não do corpo. Member/viewer não gerenciam
a conexão. Falhas de campos retornam a mensagem genérica já usada pelo app.

## Persistência e concorrência

Migration **019_instagram_persistent_oauth.sql**, somente aditiva, sem edição das
migrations anteriores:

- `ig_meta_oauth_states`: hash SHA256 de state aleatório de 32 bytes, vínculo
  composto a sessão/usuário/workspace BIGINT, callback, escopos, prazo, status e
  consumo. Não armazena state bruto nem código. Índice único adicional em
  `auth_sessoes` permite a FK composta impedir vínculos entre sessões/negócios.
- `ig_meta_connections`: UUID por conexão, workspace BIGINT, identidade externa
  validada, escopos e prazo; token longo somente como envelope AES-256-GCM do
  vault. AAD vincula workspace, UUID, conta, provedor e versão da chave. Índices
  parciais permitem somente uma conta conectada por negócio e somente um vínculo
  conectado global por conta externa.
- `ig_meta_audit`: ações sem código, token, ciphertext ou payload bruto, com FK
  composta que impede apontar para a conexão de outro workspace.

Iniciar outra autorização cancela states pendentes/em troca anteriores do negócio.
Limite: 20 inícios em dez minutos por workspace. Retenção/expurgo desses registros
é uma tarefa futura; não há limpeza destrutiva automática nesta entrega.

O callback faz claim condicional e **commita antes de chamar HTTP**. Concorrentes
não podem trocar o mesmo código; falha, negação ou timeout não reabre o state.
Não há retry automático. Após exchange → token longo → identidade, uma nova
transação confere sessão/role e estado novamente antes de persistir. Desconectar
ou iniciar outro fluxo durante HTTP impede uma conclusão tardia de reconectar.
Falhas assíncronas do provedor são auditadas como ação do sistema (`user_id`
nulo), pois o ator pode ter perdido membership durante HTTP. Revogação de
sessão, desativação, remoção de membership ou perda da role também
impedem a conclusão. Falha após consumo exige uma autorização nova.

Reconectar não apaga histórico: a conexão anterior perde ciphertext e ganha
estado disconnected/auditoria; uma conexão nova recebe outro UUID. Se a conta
validada estiver conectada a outro negócio, a operação falha sem perder o vínculo
atual do solicitante. Não se divulga o negócio proprietário no erro.

Expiração é derivada sem escrita em GET status. Nas escritas autorizadas ocorre
reconciliação de vínculos expirados: status expired, ciphertext removido e
histórico/auditoria preservados. Um OAuth novo validado pelo provedor pode liberar
um vínculo global expirado e conectar aquela conta a outro negócio. Uma conexão
ativa não pode ser transferida desta forma. O status continua indisponível se
faltar uma chave antiga, se o envelope for alterado ou se o AAD não corresponder.

Desconexão e expiração locais não são revogação na Meta. Renovação remota,
revogação remota, outbox e ingresso de mensagens exigem unidades posteriores,
revisão do contrato e autorização de contas. Não afirmar que Direct/publicação
estão funcionando por causa deste status.

## Testes e aplicação

`test_instagram_persistent_oauth.py` usa HTTP falso injetado e PostgreSQL
**descartável** via `TEST_DATABASE_URL`. Cobre hash/vínculos/FKs, expiração,
concorrência, consumo antes do HTTP, negação, 401 do provedor, timeout, revogação
ou perda de acesso durante HTTP, desconexão tardia, isolamento/global binding,
reconexão/histórico, rotação/falta de chave/tampering, rate limit e defaults fechados.

```sh
python -m unittest discover -s python-service -p 'test_instagram_persistent_oauth.py'
```

Sem PostgreSQL, os casos de persistência ficam **SKIP**, não PASS. O CI com
PostgreSQL16 deve passar no head final antes de revisão da PR. O ensaio de
migrations/dump/restore inclui fixtures das três tabelas; seu sucesso em banco
isolado não autoriza aplicar 019 no banco team/produção.

Nenhuma migration real, credencial, conta Meta, n8n, WAHA, AWS ou frontend foi
alterado nesta entrega. A operação externa permanece desabilitada.
