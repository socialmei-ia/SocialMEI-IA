# Relatórios e contas: verificação de persistência e permissão

A candidata131 já reúne cadastro transacional, sessão, recuperação por código e acesso `report_viewer`; não foi criado outro sistema de autenticação.

Corrigido o período dos agregados: **últimos N dias, incluindo hoje e excluindo o futuro**. Antes, a consulta tinha apenas limite inicial e contava vendas/lançamentos futuros. `as_of` passa a usar a mesma data do PostgreSQL que delimita a consulta. Vendas são por data de venda e financeiro por vencimento; não é soma de caixa/venda duplicada. O snapshot de leitura agora é REPEATABLE READ, sem escrita de dados de negócio.

Teste PostgreSQL descartável: duas contas/negócios com registros de hoje, limite29/30dias e amanhã. Confere valores, CSV sem nomes/descrições privadas, ausência de mistura entre negócios e exclusão dos futuros.

Outro teste cria duas contas reais descartáveis, concede leitura pelo owner, lista os negócios autorizados, troca a sessão para o negócio compartilhado e verifica `report_viewer`. O cookie anterior deixa de funcionar; CRM/PDF/Instagram e mutações são negados. Revogar o vínculo invalida a sessão desse negócio; o login posterior conserva a conta e seu negócio próprio. Isso usa os endpoints e o papel existentes, sem ampliar permissões nem expor PostgreSQL.

Cadastro/login/logout, senha7/8, Argon2, cookieHttpOnly/Secure, CSRF, perfis entre logins, revogação e fila single-use de recuperação são cobertos pelas suítes existentes executadas em banco descartável. Não há evidência nova de cadastro/SMTP na VPS. SMTP e execução do worker dependem de configuração privada e acesso operacional, ausentes neste ambiente. `sent` na fila significa aceitação SMTP, não confirmação de entrega.

Nenhuma migration nova, usuário SQL compartilhado, porta pública, merge ou deploy.
