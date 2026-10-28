# Renovação segura da conexão Instagram

Preparação de backend em 28/10/2026. Sem implantação, agendamento ou chamada real
à Meta. OAuth, publicação, ingresso e remetentes existentes permanecem preservados.

## Contrato oficial conferido

Referências Meta consultadas via Context7:
[Instagram Business Login](https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/business-login)
e [refresh_access_token](https://developers.facebook.com/documentation/instagram-platform/reference/refresh_access_token).

A renovação usa `GET https://graph.instagram.com/refresh_access_token`, com
`grant_type=ig_refresh_token`. Exige token de longa duração válido, emitido há
pelo menos 24 horas e permissão `instagram_business_basic`. O prazo é informado
pela Meta, normalmente aproximadamente 60 dias; não é inventado pelo servidor.
Token expirado exige nova autorização OAuth.

## Endpoint preparado

`POST /api/v1/instagram/meta/connection/refresh-token`, corpo `{}`.

- Sessão owner/admin válida, Origin e CSRF; o negócio é resolvido no servidor.
- Exige `SOCIALMEI_INSTAGRAM_TOKEN_REFRESH_ENABLED=true`, desligado por padrão.
  Configuração OAuth/runtime/vault válida continua obrigatória.
- Nada de token, conta de destino ou workspace fornecido pelo navegador. Não
  devolve credencial, URL com segredo ou resposta bruta da Meta.
- Token novo precisa manter identidade/escopos, continuar longo e ampliar o prazo
  anterior. A identidade é confirmada novamente com a Meta antes da persistência.
- Token cifrado, prazo, revisão e auditoria são gravados na mesma transação. Não
  requer migration nova nem invalida as senhas/sessões existentes.
- Antes de salvar, revalida sessão, papel, vínculo e revisão. Uma desconexão,
  revogação de sessão ou rotação concorrente não é desfeita pela renovação tardia.
- Resposta contém apenas status, connection_id, expires_at e revision. O GET de
  status existente continua sendo a consulta da conexão.

Uma lease exclusiva de renovação por negócio evita chamadas concorrentes. Ela
usa uma conexão PostgreSQL dedicada que fecha em todos os caminhos. Locks de
sessão/associação são liberados antes do HTTP e obtidos novamente na confirmação;
desconectar não precisa aguardar a resposta da Meta.

Rate limiting persistente limita solicitações por negócio e globalmente. O helper
de autenticação aceita timeout opcional para essa transação; chamadas de login
existentes conservam o comportamento anterior. Esperas SQL têm limite explícito,
incluindo a transação dos contadores. O transporte HTTPS existente conserva seus
timeouts, allowlist, validação TLS e proteção de logs.

## Resultados e falhas

| Resposta | Significado                                                                                      |
| -------- | ------------------------------------------------------------------------------------------------ |
| 200      | Meta e persistência confirmadas; metadados da conexão renovada.                                  |
| 401/403  | Sessão ausente/revogada ou papel sem permissão.                                                  |
| 409      | Token recente/expirado, conexão ausente/alterada ou outra renovação ativa.                       |
| 429      | Limite persistente de tentativas atingido.                                                       |
| 503      | Função desabilitada, configuração/provedor/vault/banco indisponível ou renovação não confirmada. |

Falha mantém os dados da conexão anterior no banco. Isso **não garante** validade
continuada da credencial na Meta: timeout pode ocorrer depois de o provedor
processar a solicitação. Não repetir automaticamente nem apresentar sucesso
presumido; consultar a conexão e, se necessário, refazer OAuth.

Não há worker/cron nem botão novo instalado nesta entrega. O contrato permite
renovação explícita pelo operador autenticado; agendamento automático e exposição
na interface são etapas separadas, depois de homologar a conexão real.

## Aplicação futura e rollback

Conferir CI no SHA exato, backup, imagens e overlays da API. A flag deve entrar
somente no override privado autorizado; o Compose versionado deixa-a desligada.
Nenhuma configuração deste arquivo conecta contas ou habilita Direct/publicação.

Testar com conta profissional autorizada, sem enviar mensagem ou conteúdo. Para
rollback, desligar a flag e voltar à imagem/configuração anterior da API. O token
renovado conserva o mesmo formato de armazenamento/vínculo e é compatível com a
versão anterior. Não restaurar banco ou apagar conexões para desfazer o código.

Os testes usam provedor sintético e PostgreSQL descartável; não comprovam renovação
real ou permanência indefinida da conexão do proprietário.
