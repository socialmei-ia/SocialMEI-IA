# Recuperação de conta por e-mail

Implementação opcional na candidata #111. Não instalada na AWS e nenhum e-mail real enviado nesta rodada.

## Fluxo

Na autenticação remota, “Esqueci minha senha” abre o formulário nativo. Solicite o código pelo e-mail cadastrado, cole o código completo e confirme a nova senha. O usuário retorna ao login; não há sessão automática. No modo local, não existe recuperação remota de contas.

POST `/api/v1/auth/recovery/request`: `{email}`; resposta202 genérica para contas existentes e inexistentes. POST `/api/v1/auth/recovery/confirm`: `{token,nova}`;204 em sucesso,400 se inválido/usado/expirado. Ambos exigem Origin oficial, JSON e `X-SocialMEI-Client: browser`, com no-store. Não exigem sessão para que usuários sem acesso consigam recuperar a conta.

Código aleatório de256bits,15 minutos, somente hash em PostgreSQL, um por conta, uso único transacional. Nova solicitação substitui o anterior; somente o código mais recente vale. Troca normal de senha também invalida códigos anteriores. A confirmação revoga todas as sessões da conta, preservando outras contas/negócios. Política Argon2id,8–128 caracteres e bloqueio de senhas extremamente comuns preservados. Senhas curtas aceitas recebem aviso no frontend.

Limites persistentes por e-mail/par socket e limite global. Cabeçalhos X-Forwarded-For não são confiados. Atrás de proxy, o limite por peer pode ser compartilhado pelos usuários e requer homologação de capacidade, sem passar a confiar em cabeçalhos arbitrários.

## Configuração Gmail/SMTP

Somente após autorização de implantação, configurar no ambiente privado do servidor:

- `SOCIALMEI_RECOVERY_MODE=smtp` (padrão `disabled`).
- `SOCIALMEI_SMTP_HOST=smtp.gmail.com`.
- `SOCIALMEI_SMTP_PORT=465` (TLS implícito) ou587 (STARTTLS obrigatório antes de autenticar).
- `SOCIALMEI_SMTP_USER`: conta remetente dedicada.
- `SOCIALMEI_SMTP_PASSWORD`: senha de aplicativo, se permitida pela política Google, com verificação em duas etapas. Nunca a senha comum da conta nem um segredo no frontend/Git/chat.
- `SOCIALMEI_SMTP_FROM`: remetente autorizado pela conta.

A conta Google, verificação em duas etapas, permissão de senha de aplicativo, quotas e entregabilidade precisam ser configuradas pelo responsável. OAuth do Gmail não está implementado. Gmail SMTP é adequado a um piloto, mas um provedor transacional poderá ser mais apropriado para escala. Não configurar n8n nem compartilhar tokens para essa finalidade.

O Compose team encaminha essas variáveis e mantém a função desligada. Não executar o Compose padrão completo na AWS: preservar os overrides e hotfixes públicos existentes. API autenticada, origem HTTPS e migrations024/026 são requisitos; configuração incompleta ou tabela ausente responde503.

## Operação e limites

As solicitações agora são persistidas na fila026 antes da resposta202. O worker explícito processa o envio sem guardar códigos em texto puro. Reinícios preservam pedidos pendentes; resultados incertos não são reenviados automaticamente. A função continua desligada até configurar SMTP e instalar/agendar o worker. Ver [operação do backend](BACKEND-OPERATIONS-READINESS.md) para estados, concorrência e rollback. Nenhum worker foi instalado na AWS.

Apenas o código mais recente válido funciona: uma nova solicitação pode invalidar um e-mail que já estava em trânsito. `sent` indica aceitação SMTP, não entrega confirmada.

Migration024 é incremental e foi aplicada somente em PostgreSQL descartável. Backup integral inclui a tabela; tratar seus hashes como dados sensíveis. Para rollback de código, desativar recuperação e voltar à imagem anterior, preservando a tabela aditiva. Não desfazer migrations nem apagar contas. Tokens pendentes expiram em15 minutos. Homologar a restauração e privilégios da role antes de habilitar em produção.

## Validação

Testes específicos: senha7/8, comum, expiração, replay, código inválido, isolamento, revogação, falha SMTP, mudança normal, concorrência de confirmação, migration ausente, limites e TLS465/587. Transporte e destinatários são sintéticos; nenhum acesso Google. Regressão de contas no Chromium cobre formulário, retorno, validação e capturas1440/390 claro/escuro com API controlada. Sessões e SQL reais são verificados separadamente nos testes backend.

Ensaio adicional de release executado em PostgreSQL16 Docker descartável: migrations001–024, preservação de valores/ledger, reexecução, falha transacional e pg_dump/pg_restore passaram. A fixture024 inclui dois hashes sintéticos de recuperação (pendente e usado); o snapshot integral confirmou seus estados após restauração. Nenhuma migration anterior foi modificada.
