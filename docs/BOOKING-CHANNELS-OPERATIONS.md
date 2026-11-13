# Agendamentos e respostas automáticas — fechamento sem Prisma

## No site

A seção **Agenda → Agendamentos de serviços** permite cadastrar serviços,
profissionais/recursos, registrar agendamentos internos e alterar horários.
O botão **Configurar horários dos canais** fica disponível para proprietários
e administradores autenticados. Ele configura a política já existente do
negócio, sem novas tabelas: fuso, turnos por dia, intervalo, antecedência e
janela máxima. O mesmo calendário é consultado por WhatsApp e Instagram.
Uma reserva interna **não** envia mensagens automaticamente.

Para confirmar agendamento a partir de mensagem, o contato precisa estar
associado ao cliente correto do CRM. Na Caixa Unificada, o vínculo é uma ação
humana explícita. O sistema pode sugerir um cadastro único por telefone
WhatsApp verificado, mas nunca associa automaticamente nem usa identificador
Instagram como telefone.

## WhatsApp

Os fluxos de catálogo, serviço, profissional, dia, horário e confirmação estão
implementados. Antes de habilitar o envio real, conferir o WAHA conectado,
webhook assinado, sessão WEBJS/GOWS selecionada, um único respondedor,
mensagens pendentes e recibos. Validar primeiro com remetentes da equipe.
Não confundir testes de API com recebimento confirmado no celular do cliente.

## Instagram

O backend persiste o estado do menu e só responde Directs autenticados,
recentes e associados à conta do mesmo negócio. Respostas manuais pausam a
automação. Os códigos internos de agendamento não são exibidos ao cliente.

`compose.team-instagram-auto.yaml` adiciona perfis separados
`instagram-menu-primary` e `instagram-menu-secondary`. Os perfis são
inativos na composição padrão e não publicam portas. Cada worker tem volume
próprio e precisa de um ID de workspace autorizado, horário de corte UTC,
chave privada, OAuth válido e modo de envio ativo. A lista de workspaces
permitidos e as flags de habilitação devem ser idênticas na API e nos workers.

**Não iniciar** um novo worker se existir um respondedor n8n/Instagram ativo
para a mesma conta. Conciliar mensagens `dispatching` e `uncertain`,
confirmar a propriedade exclusiva do Direct e somente depois ativar cada
perfil. O modo padrão é desativado; perfis sem parâmetros válidos ficam
indisponíveis e não devem ser usados em produção.

## Recuperação de acesso

O e-mail de redefinição e o código de uso único já estão implementados.
O processamento contínuo da fila depende do override opcional
`compose.team-recovery.yaml`, SMTP privado e destinatário de homologação.
Ver `docs/ACCOUNT-RECOVERY.md`.

## Agendamento público opcional (continuação de 12/11)

O fluxo real está em `/frontend/agendar.html?negocio=<slug>`. A demonstração
isolada continua em `docs/prototypes/public-booking/`. A API de visitantes usa
`/api/v1/public/booking/{slug}`; não recebe autorização administrativa.
O responsável publica serviços e profissionais explicitamente pelo botão
**Agendamento público** na Agenda. Os horários são os da política compartilhada
dos canais. Alterações invalidam ofertas antigas; a confirmação revalida tudo
na mesma transação e no mesmo bloqueio de recurso da Agenda.

Desativado por padrão. Antes de habilitar, configurar no servidor privado
`SOCIALMEI_PUBLIC_BOOKING_ENABLED=true`, `SOCIALMEI_PUBLIC_BOOKING_KEY` aleatória
com pelo menos 32 bytes, origem HTTPS e SMTP válido (465/TLS ou 587/STARTTLS).
Não colocar a chave no frontend. `compose.team-public-booking.yaml` prepara
somente saída de rede para SMTP; não habilita o recurso. Conciliar esse override
com as redes privadas instaladas antes de qualquer publicação.

O visitante verifica seu e-mail por código de dez minutos, vinculado à oferta.
Somente e-mail verificado e único pode associar cliente existente, se o
responsável permitir explicitamente; novos cadastros também exigem opção
explícita. Duplicidade ou cadastro inativo encaminha ao atendimento humano.
Não há associação por nome/telefone. Referências são cifradas; limites persistem
em `auth_limites` (leitura, envio, código e reservas). O mesmo comprovante
retorna a reserva persistida em retries, inclusive cancelada/concluída.

Usa somente schema039 existente, sem nova tabela ou migration. Homologação
SMTP real, entrega ao destinatário controlado e banco atualizado continuam
obrigatórios antes da ativação; testes simulados não comprovam entrega.

## Aceitação de produção

A validação automatizada usa dados fictícios, banco descartável e provedores
simulados. Para finalizar em produção, faltam conferência atual do servidor,
backup restaurável, contas Meta/WAHA/SMTP reais, verificação de isolamento
entre negócios e confirmação do recebimento das mensagens de teste.
Nenhuma etapa desta entrega exige alterar Prisma ou executar migrations.
