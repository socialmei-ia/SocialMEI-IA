# Demonstração final — roteiro e estado comprovado

Inventário SSH de 19/11/2026, America/Fortaleza (20/11 UTC). Base candidata
`17cfd1956416c2d4c8431fec11800f73254bde12`, PR #233 aberta/Draft.
Atualização20/11: CRM233 publicado, API17cfd19 e premium preservado.
Este roteiro é um critério de homologação. A apresentação integral ainda não foi
homologada em produção; confira a tabela de pendências antes de agendá-la.

## Destino e acesso

Existe no banco efetivo da API o negócio **Brilho&Limpeza Service**, workspace
**60**, proprietário individual **33**, ativo e sem privilégio de plataforma.
Ele é o cenário preferencial Brilho Limpeza. Não renomear nem criar duplicata.
Não há clientes, catálogo, recursos ou reservas desse negócio no inventário.
O login dessa conta ainda exige validação pelo responsável; nenhum segredo foi
obtido, redefinido ou registrado nesta entrega.

Bella Store não foi encontrada nesse banco. A referência histórica de Instagram
Bella pertence a outro checkpoint/conexão e não prova um workspace atual.
SorriaOdonto e She Style são fixtures de `test_business_fixture_flows.py`.
O banco Prisma do worker Instagram/serviço antigo de menu não pôde ser consultado (OperationalError); a
ausência desses negócios ali permanece não confirmada. Não criar Bella antes
de reconciliar esse inventário e aprovar seu cadastro independente.

O [provisionador](MEI-DEMO-PROVISIONER.md) usa as APIs autenticadas existentes.
[Manifesto preparado](../tools/mei-demo-brilho.prepared.json): workspace60/user33,
nome exato e data fixa. Sua existência **não autoriza aplicar em produção**.
Aplicação depende da confirmação do destino e de autenticação privada da conta
proprietária. Não enviar senha ou cookie pelo chat. O dry-run autentica e cria
uma sessão, mas não escreve dados comerciais; previews são somente consulta.

Para acesso do professor, usar conta individual e papel `report_viewer` para
relatórios, ou `member` somente se a participação operacional for aprovada.
Um proprietário concede acesso a conta existente em `/api/v1/team/members`;
o mesmo fluxo permite revogar acesso sem compartilhar a senha administrativa.
Convites por `/api/v1/team/invitations` dependem da ativação de identidade e
worker SMTP próprios. O runtime atual tem `SOCIALMEI_IDENTITY_MODE=disabled`;
configuração SMTP para recuperação não certifica convites/ativação funcionando.
Nunca dar ao professor acesso PostgreSQL, role de infraestrutura ou Basic
administrativo compartilhado como substituto da conta individual.

## Pré-requisitos de homologação

1. Publicar correção CRM sob aprovação própria, mantendo gateway premium.
2. Confirmar conta33/destino60 e executar dry-run; aplicar o manifesto aprovado
   com inventário privado e repetir para comprovar ausência de duplicações.
3. Reconciliar fontes de banco: API/recuperação usam PostgreSQL17 realocado;
   o worker WhatsApp ativo chama essa API por hotfix. O worker Instagram ainda
   usa Prisma. O menu antigo também aponta para Prisma, mas não é o destino
   HTTP atual do worker WhatsApp; não reconfigurá-lo por suposição.
4. Aprovar vínculos de canal por empresa. Atualmente WhatsApp/Instagram
   estão no workspace1; nenhum deles foi transferido para workspace60.
5. Verificar filas/recibos incertos, registry WAHA, HMAC, uma instância de
   respondedor por conta, política de horários e autorização do contato de teste.
6. Validar envio/recebimento com o responsável e destinatário autorizado.
   Não usar mensagens sintéticas como prova de WhatsApp ou Meta reais.

O worker WhatsApp tem imagem e arquivos efetivos diferentes por hotfix:
`public_worker.py` aponta para `team-api:8000`, conforme arquivo e variável
efetivamente instalados. Preservar esse caminho até uma consolidação autorizada.
Há11 workflows n8n ativos;2 grafos contêm POST para a Graph API. Isso não prova
duplicação de resposta (podem ter outra finalidade), mas exige mapear conta,
receptor e caminhos alcançáveis antes de ligar ou substituir sender Instagram.

Transferência eventual do canal1→60: inventariar canal/registry/sessão e versões;
registrar mensagens/conversas/jobs pendentes e recibos incertos; preservar o
histórico no workspace original; preparar snapshot privado/rollback do binding;
provar exclusividade de respondedor e recusa do workspace antigo após corte.
Usar operações de domínio suportadas, sem alterar workspace_id de conversas
históricas ou compartilhar sessão entre negócios. Se não houver transferência
atômica suportada, preparar janela controlada e implementação/testes próprios.
Executar somente após aprovação do responsável, com retorno/rollback ensaiado.

## Roteiro observável

| Ação                                               | Resultado esperado                                            | Evidência necessária                               |
| -------------------------------------------------- | ------------------------------------------------------------- | -------------------------------------------------- |
| Entrar como proprietário do negócio fictício       | Sessão informa user33/workspace60                             | Login e `/auth/session`                            |
| Abrir perfil empresarial                           | Nome existente, descrição fictícia e segmento persistidos     | Recarregar em outra sessão                         |
| Consultar clientes e catálogo                      | 4 clientes fictícios; 3 serviços, preços e durações           | Leitura remota e inventário                        |
| Abrir Agenda                                       | 2 recursos; reservas pending/done/cancelled                   | Leitura da API e histórico                         |
| Enviar WhatsApp autorizado e abrir Ver opções      | Uma entrada persistida, menu do negócio correto               | Evento/recibo sem duplicação                       |
| Associar contato ao CRM                            | Cliente escolhido por ID; telefone validado quando disponível | Revisão de conversa atualizada                     |
| Selecionar serviço/profissional/dia/horário        | Disponibilidade da agenda comum                               | Nenhuma reserva antes de confirmar                 |
| Confirmar                                          | Uma reserva e histórico no workspace60                        | Agenda atualizada após leitura                     |
| Meus agendamentos, alterar/cancelar                | Autorização por contato; vaga liberada no cancelamento        | Histórico e disponibilidade                        |
| Dois clientes disputam horário em canais distintos | Um confirmado, outro409                                       | Um agendamento/histórico                           |
| Consultar catálogo/preço, humano/menu/encerrar     | Consulta termina; pausa humana impede automação               | Uma resposta por entrada                           |
| Enviar Direct autorizado                           | Uma conversa no mesmo negócio                                 | Webhook HMAC, persistência, no máximo uma resposta |
| Responder manualmente                              | Sem resposta concorrente do bot/n8n                           | Recibo e estado da pausa                           |
| Registrar venda fictícia                           | Venda persistida; produto baixa estoque; serviço não baixa    | Operação e estoque conferidos                      |
| Consultar Financeiro/Relatórios                    | Pago separado de pendente; filtros do workspace               | Totais da API e CSV                                |
| Alternar para segundo negócio                      | Nenhum cliente/venda/reserva/conversa do primeiro             | Sessão e IDs; tentativa cruzada recusada           |

O provisionador cria histórico **interno manual** de atendimento, nunca mensagens
externas. Cria 2 vendas (uma paga/uma pendente), 3 lançamentos financeiros,
2 oportunidades e 2 lembretes. Brilho tem receitas180 recebida/240 pendente,
despesa50 paga; Bella tem59,90 recebida/89,90 pendente, despesa25 paga.
Venda e lançamento financeiro são contratos distintos: não somar ambos como
dinheiro recebido. No ensaio isolado, Bella terminou com estoque19,19,20.

Para repetir: usar os mesmos IDs, origem, data e conteúdo do manifesto. O
provisionador reconcilia por contratos duráveis; alterações feitas manualmente
permanecem preservadas ou causam conflito explícito. Ele não reinicializa o banco,
não apaga reservas e não força estado antigo sobre edições do proprietário.

## Contratos para o frontend em finalização

Todos abaixo usam prefixo `/api/v1`. Escritas autenticadas precisam dos headers
Origin/CSRF/identidade existentes. Workspace é resolvido pela sessão no servidor.

| Elemento                    | Contrato existente                                                                                  |
| --------------------------- | --------------------------------------------------------------------------------------------------- |
| Conta/negócio ativo         | `/auth/session`, `/auth/workspaces`, `/auth/workspaces/switch`                                      |
| Identidade comercial/perfil | `/auth/profile`, `/workspace-profile`                                                               |
| Clientes/catálogo           | `/clientes`, `/produtos`; importações preview/confirmar                                             |
| Profissionais e agenda      | `/agenda/resources`, `/agenda/appointments`; expected_revision nas mudanças                         |
| Horários/política de canal  | `/agenda/channel-booking`                                                                           |
| Publicação do site          | Configuração de agenda; `/public/booking/{slug}` e verificação de contato                           |
| Vínculo CRM da Caixa        | `/message-enrichment/conversations/{id}/customer-suggestions` e `/customer`                         |
| Vendas e pagamento          | `/vendas`, `/vendas/{id}/pagar`; operation_id/expected_version                                      |
| Financeiro/oportunidades    | `/financeiro`, `/opportunities`                                                                     |
| Indicadores/CSV             | `/reporting/overview`, `/sales`, `/appointments`, `/products`, `/overview.csv` no prefixo reporting |
| Equipe/acesso do professor  | `/team/members`; convites somente com identidade habilitada                                         |

A publicação restrita alterou somente `v22-inbox-customer.js` por bind readonly.
Hero, layout, animação, navegação e imagem premium foram preservados.

## Pendências priorizadas

| Prioridade | Pendência                                     | Estado/evidência atual                                                                 |
| ---------- | --------------------------------------------- | -------------------------------------------------------------------------------------- |
| P0         | Publicar CRM233 preservando premium           | Publicado20/11: API17cfd19, premium preservado, saúde/site200                          |
| P0         | Popular Brilho existente                      | Destino60/33 validado; dry-run aguarda credenciais privadas; carga real não autorizada |
| P0         | Fontes de banco e vínculos WhatsApp/Instagram | WhatsApp ativo→API PG17/schema040; IGworker→Prisma indisponível; canais no workspace1  |
| P0         | Jornada real de reserva e respondedor único   | Corrida WA/IG testada localmente; provedor real/workspace60 pendentes                  |
| P0         | Segundo negócio independente                  | Bella ausente na API; Prisma não inventariado; não criar duplicata                     |
| P1         | Professor/equipe e e-mails                    | Fluxos testados sinteticamente; identity disabled; nenhum convite/envio feito          |
| P1         | Consulta segura e backup atual externo        | Role readonly ausente; pgAdmin aponta n8n; S3 AccessDenied                             |
| P1         | Relatórios e segurança em produção            | Regressão isolada; homologação do destino/canais após P0                               |
| P2         | Autoconfiguração/escala/IA adicional          | Preservar contratos; não bloqueia primeira apresentação validada                       |

Estados separados: provisionador implementado/testado; CRM233 publicado;
API ativa17cfd19; gateway premium preservado. Nenhum desses fatos
certifica a jornada completa do professor. A evidência desta retomada fica em
`docs/evidence/20261119-mei-demo-readiness.json`.

Atualização de publicação e testes de saúde/site:
`docs/evidence/20261120-crm233-publication.json`. O inventário anterior permanece
como evidência histórica. O dry-run autenticado não foi executado sem a conta
proprietária; nenhum cliente ou outro dado comercial foi criado.
