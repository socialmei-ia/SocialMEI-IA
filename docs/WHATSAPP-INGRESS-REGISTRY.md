# Registry privado de recebimento WAHA

O receptor existente pode carregar os vínculos de canal por arquivo privado,
sem depender de alteração de código ou de `dependency_overrides`. A configuração
é explícita em `SOCIALMEI_WAHA_REGISTRY_FILE`, com caminho absoluto dentro da API.
Não existe registry de demonstração ou vínculo padrão. Configuração ausente ou
inválida mantém HTTP503 com mensagem genérica, sem caminho, identificadores,
segredos ou detalhes do parser.

## Arquivo e contrato

O operador prepara um JSON privado com exatamente `version: 1` e `bindings`,
uma lista de1 a100 registros. Cada registro possui os campos de `WahaBinding`:

| Campo          | Origem e finalidade                                              |
| -------------- | ---------------------------------------------------------------- |
| `instance`     | Alias interno da instância, igual ao cadastro do canal           |
| `session`      | Sessão WAHA confiável do número autorizado                       |
| `account_id`   | ID da conta do próprio negócio confirmado pelo WAHA              |
| `workspace_id` | Negócio previamente conferido no servidor                        |
| `channel_id`   | Canal existente desse negócio                                    |
| `hmac_key`     | Segredo dedicado de assinatura do webhook, guardado privadamente |
| `revision`     | Versão atual do canal; padrão1 se omitida                        |

Chaves desconhecidas ou repetidas, tipos inválidos e registros conflitantes
são recusados. Conta, canal e segredo não podem se repetir entre registros;
o alias da instância também é único. O arquivo precisa ser regular, até64KiB,
sem link simbólico, pertencente a root ou ao usuário efetivo da API e com modo
0400 ou0600. FIFO, diretório e arquivo acessível ao grupo/outros são recusados.

O arquivo deve ser montado somente leitura, por exemplo em
`/run/secrets/waha-registry.json`, pelo overlay privado revisado do servidor.
O caminho do mount e a variável são configuração; o conteúdo nunca vai para
GitHub, frontend, chat ou logs. Não gravar o JSON dentro da imagem Docker.
Para trocar o arquivo, manter as mesmas proteções de propriedade e permissão
e conferir como o bind mount escolhido reflete sua substituição no container.
O loader não mantém cache: a próxima requisição relê os bytes visíveis no mount.

## Proteções que continuam obrigatórias

Carregar o registry não inicia sessão, não pareia número, não cria canal,
não liga flags, não configura webhook, não envia mensagem e não instala bot.
O código conserva as flags de recepção isolada já existentes; uma configuração
de produção distinta exige revisão e homologação próprias.

O POST `/internal/waha/{instance}/webhook` continua validando HMAC SHA512 do
corpo bruto, sessão, conta e engineWEBJS antes de gravar. Se o n8n intermediar,
deve preservar os bytes e os cabeçalhos de assinatura originais. Recriar JSON
em outro formato invalida a assinatura; não desabilitar HMAC para contornar isso.

Em cada evento, o receptor revalida o canal no PostgreSQL: negócio, conta,
sessão, instância, versão, `ingress_provisioned`, `ativo` e envio desabilitado.
Alteração ou revogação no banco invalida o vínculo mesmo com arquivo antigo.
Os filtros de eco, grupo, mídia não suportada e deduplicação continuam iguais.
O parser não foi ampliado para replies de botões sem payload da engine validado.

Não publicar uma rota `/internal/*` genérica no Caddy. O encaminhamento específico,
os workflows ativos e a responsabilidade de resposta precisam de inspeção antes
de qualquer corte. Esta mudança não altera Compose, Caddy, n8n ou WAHA reais.

## Verificação e reversão

Os testes usam arquivos temporários privados e segredos sintéticos. Conferem
arquivo válido, rotação sem cache, chaves duplicadas, limites, links, permissões,
propriedade, erro sanitizado e manutenção da revalidação do canal. Nenhum número
real ou serviço externo é acessado por esses testes.

Para desativar uma instalação futura, desligar a flag de recepção e retirar a
configuração do registry no overlay autorizado, preservando banco e histórico.
Não apagar migrations nem volumes. O remetente existente no n8n não é alterado
automaticamente por essa operação.
