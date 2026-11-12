# Finalização sem Prisma — 12/11/2026

## Resultado e limites

O projeto ainda não está integralmente homologado em produção. Esta execução
corrigiu falhas reais da candidata e validou os componentes independentes do
banco real. Não houve deploy, envio real, alteração do Prisma, execução ou
alteração de migrations, restauração, modificação de schema ou de credenciais.
Nenhum dado real foi usado nos testes.

## Estado reconhecido antes das alterações

- GitHub: PR #223 aberta/draft, HEAD `cfb4011434f2def012e0abb2addac39f1fc8b017`.
  PRs #227 e #228 já incorporadas. Repository checks
  [43281891369](https://github.com/socialmei-ia/SocialMEI-IA/actions/runs/43281891369)
  e imagens [43281891212](https://github.com/socialmei-ia/SocialMEI-IA/actions/runs/43281891212)
  concluídos com sucesso nessa base. Os 913 testes Python conhecidos pertencem
  à validação anterior, não foram repetidos nesta sessão.
- Já implementados: menu/catálogo e agendamento WhatsApp/Instagram, núcleo de
  disponibilidade compartilhada, política da agenda administrativa, vínculo
  humano CRM, recuperação de senha e workers opcionais.
- Pasta principal em `main` antiga, com alterações locais preservadas. Trabalho
  desta execução em `.preview/finalization-20261112`, branch
  `fix/integrated-finalization-20261112`, criada a partir da candidata remota.

## Correções e implementação desta execução

- `76f6cf2`: Instagram exige que preço, duração, nomes e horário final continuem
  iguais ao resumo apresentado antes de persistir a reserva.
- `d8924f8`: preserva também o vínculo original de cliente/canal, política e
  revisões do serviço/recurso. Mudanças exigem nova consulta; somente a expiração
  da oferta pode ser renovada. O token completo não aparece no Direct.
- `79908c5`: inspector consulta a conexão efetiva da API, com transação somente
  leitura, timeout SQL, rollback e erros sanitizados. O PostgreSQL local legado
  deixa de produzir um falso resultado positivo. Registra image IDs imutáveis,
  presença dos campos SMTP e exige o schema039 já existente para esta candidata.
- `476470e`: protótipo público isolado, responsivo, com dados fictícios Bella
  Store/Brilho Limpeza, escolha de serviço/recurso/data/horário, resumo e estados
  de falha/conflito. Não consulta API, armazena dados ou cria reservas.
- `9a7dfc5`: fixture Windows testa rejeição de junction sem exigir privilégio de
  symlink. Mantida a verificação de segurança; Linux mantém o caso de symlink.
- Revisão independente aprovou as correções de identidade e do inspector.

## Validação executada agora

| Verificação             | Resultado                                             | Limite da evidência                                                         |
| ----------------------- | ----------------------------------------------------- | --------------------------------------------------------------------------- |
| JavaScript completo     | 424 aprovados, 2 pulados, 0 falhas                    | Dois casos de exportação Docker já eram condicionais; não foram habilitados |
| Python focado sem banco | 42 aprovados                                          | Inclui 11 casos Instagram; transportes sintéticos, sem persistência real    |
| Inspector offline       | 11 aprovados                                          | Inclui retorno psycopg texto/JSON, falha sanitizada e ausência de fallback  |
| Navegador existente     | Aprovado; 286 estados de layout e 5 fluxos de entrada | API controlada; agenda, recuperação, CRM e canais em mobile/desktop         |
| Protótipo público       | 24 jornadas aprovadas                                 | 390/768/1440 px, claro/escuro, normal/vazio/erro/conflito; nenhuma reserva  |
| Formatação e diff       | Aprovados                                             | Sem alteração de schema/migrations/Prisma                                   |
| SSH de produção         | Somente leitura concluída                             | Nenhuma mensagem ou e-mail enviado                                          |

As suites PostgreSQL usuais preparam o banco executando migrations. Não foram
executadas nesta sessão por essa proibição explícita. Concorrência real entre
WhatsApp/Instagram/site, persistência e revogação de sessões continuam dependendo
de nova homologação em infraestrutura apropriada. Nenhum teste foi desabilitado.

## Produção observada por SSH

Coleta em 12/11/2026, aproximadamente 19:00 UTC, com o inspector corrigido.

- Checkout do host: `6f4c8e1795cbb2e9074845edd9ac099a8ea3925b`, com alterações locais.
- API: `unhealthy`; label de revisão `86cdd5b`, image ID
  `sha256:8aaa6f0f14fdabbe219eebdaf06c0688ab2f2248a05188cef812e192ee1dd45e`.
  Labels e conteúdo de patches podem divergir; não confundir label com imagem.
- Gateway: label `8159c17`, image ID
  `sha256:f9e43dfc3cdfd3d6eb556c53d9f7839ab28f31a5aa6f089009b94df17535c2f4`.
- Conexão efetiva da API: indisponível, classificação fixa
  `provider_account_limit` (`planLimitReached`), sem impressão do erro bruto.
- PostgreSQL local saudável não certifica o banco externo usado pela API.
- Recuperação na API: `disabled`; campos SMTP completos ausentes. Porta padrão
  TLS válida não prova configuração nem entrega.
- Instagram na API: conexão/ingresso/envio habilitados e proprietário `dashboard`.
  Isso não comprova que o worker atual consegue processar com o banco indisponível.
- WEBJS legado identificado; a saúde de GOWS e a exclusividade do respondedor
  exigem inspeção específica antes de qualquer ativação. Nenhuma sessão alterada.

Não foi publicado nada nesta execução. Não houve teste real de recebimento de
WhatsApp/Direct, reserva ou e-mail. Homologações históricas não são prova atual.

## Classificação por funcionalidade

| Funcionalidade                             | Classificação                                        | Pendência real                                                                |
| ------------------------------------------ | ---------------------------------------------------- | ----------------------------------------------------------------------------- |
| WhatsApp: menu, catálogo e resposta humana | Implementada e aprovada, aguardando ativação         | Reconciliar runtime atual, banco, único respondedor e recebimento controlado  |
| Agendamento WhatsApp                       | Implementada e aprovada, aguardando ativação         | Publicar núcleo/fluxo correto e provar reserva persistida e visível na Agenda |
| Instagram Direct e agendamento             | Implementada e aprovada, aguardando ativação         | Publicar correções, conferir conta/worker e provar reserva/recebimento        |
| Agenda administrativa e CRM                | Implementada e aprovada, aguardando ativação         | Publicar candidata coerente e homologar sincronização real entre canais       |
| Recuperação por e-mail                     | Implementada e aprovada, aguardando ativação         | SMTP, worker com a mesma conexão efetiva da API e teste real de destinatário  |
| Isolamento Bella/Brilho e pausa humana     | Implementada e aprovada, aguardando ativação         | Homologação simultânea real dos dois negócios; evidência atual é automatizada |
| Agendamento público                        | Parcialmente implementada, com bloqueio identificado | Protótipo pronto; falta contrato seguro de visitante e revisão/aprovação      |

Nenhuma funcionalidade recebe a classificação “Concluída em produção e
verificada” nesta execução.

## Configuração externa e próximos passos

1. Preservar o runtime enquanto o banco efetivo estiver indisponível. Resolver a
   restrição do provedor fica fora desta etapa; não trocar conexão ou credencial.
2. No ambiente privado do servidor, o responsável precisa configurar
   `SOCIALMEI_RECOVERY_MODE=smtp`, `SOCIALMEI_SMTP_HOST`, `SOCIALMEI_SMTP_PORT`
   (465 ou 587), `SOCIALMEI_SMTP_USER`, `SOCIALMEI_SMTP_PASSWORD` e
   `SOCIALMEI_SMTP_FROM` autorizado. Não colocar valores no Git ou no chat.
   Validar origem HTTPS/autenticação e remetente no provedor.
3. Antes de ativar `recovery-mail`, conferir que API e worker consultam o mesmo
   banco efetivo. O override padrão usa PostgreSQL local; um overlay externo da
   API não é automaticamente herdado pelo worker. Ajustar somente a configuração
   privada autorizada, sem alterar credenciais existentes. Homologar TLS, fila,
   reinício, recebimento, uso único, nova senha, revogação e novo login.
4. O publicador antigo `gows-catalog-release.py` não inclui toda a candidata:
   faltam módulos novos de agendamento, Instagram e recuperação. Não usá-lo como
   publicação integral. Preparar pacote coerente preservando patches instalados,
   imagens anteriores, filas e respondedor exclusivo; renovar backup/rollback.
5. Para página pública real, definir publicação explícita do negócio/serviços,
   identificação de visitante, contato verificado, prevenção de abuso,
   idempotência e transação compartilhada. Não reutilizar autorização do painel
   nem associar CRM por nome/e-mail apenas digitado. Não foi comprovado bloqueio
   inevitável de schema ou necessidade de migration. O contrato seguro ainda é
   trabalho pendente; o protótipo deve ser revisado antes de integrar.
6. Homologar cenários A–G com contatos/destinatário controlados assim que houver
   conexão saudável, contas autorizadas e publicação coerente. Testar disputa
   entre canais, replay, pausa humana, falha de rede/SMTP e duas empresas.

Antes de voltar ao Prisma, ficam preparados código, protótipo, testes locais e
diagnóstico. Permanecem a configuração privada SMTP, o contrato público seguro
e a homologação/ativação real; não declarar o produto 100% concluído.

## Consolidação no GitHub

A candidata #223 não foi substituída nem integrada à `main`. Esta branch é uma
continuação direta de `cfb4011`. Os workflows de PR para essa base executam
migrations em fixtures e ensaio de restauração; abrir/atualizar uma PR os acionaria.
Por isso esta sessão prepara commits e branch separada, sem acionar esses
workflows nem dispensar suas verificações. A evidência CI anterior continua
restrita à base `cfb4011`.
