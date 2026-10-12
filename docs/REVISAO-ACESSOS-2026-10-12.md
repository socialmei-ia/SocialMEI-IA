# Conta, saída e administração

Esta revisão melhora a interface dos recursos entregues no PR #28. A conta ficava dentro de Ferramentas → Perfil, tornando difícil encontrar a saída. O painel administrativo usava uma página básica, sem a organização visual do aplicativo.

## Mudanças

- **Conta no cabeçalho:** avatar e menu próprios, sem entrar em Ferramentas. O menu mostra o e-mail autenticado e o perfil de acesso; “Meu perfil” abre Configurações → Conta.
- **Sair da conta:** ação identificada no menu lateral, menu da conta, configurações e administração. O app preserva o rascunho atual, chama a API de saída e retorna à tela pública após revogação. Se a API falhar, informa a falha e mantém a conta visível, sem fingir que encerrou a sessão. Após revogação confirmada, falta de espaço no armazenamento local não mantém o usuário dentro do app.
- **Minha conta:** cartão com identidade e negócio, dados pessoais, troca de senha com confirmação e acesso à administração para o administrador do projeto. O envio da senha permanece restrito aos campos aceitos pela API; divergência na confirmação é mostrada antes de enviar.
- **Administração:** resumo das contas carregadas, convite com instruções, resultado e botão de copiar, busca por nome/e-mail, filtro de situação, atualização da lista e confirmação de desativação em diálogo. Layout adaptado a celular, tema claro/escuro e opção de sair retornando ao login.
- **Recuperação de acesso:** orientação apresentada no formulário de login e nas configurações. O envio automático de código/e-mail ainda não está conectado; a interface informa o procedimento com o administrador. Convites também continuam sendo entregues manualmente.

A revisão não altera tabelas, senhas, permissões ou isolamento por negócio. Basic auth continua no piloto e o WhatsApp continua aguardando o chip. O painel usa os endpoints existentes; desativação preserva o negócio e encerra as sessões, enquanto reativação e recuperação continuam pelo procedimento privado. Os contadores refletem as contas carregadas pela API, limitada atualmente a 500, com aviso no limite.

## Conferência

A regressão de navegador cobre saída pelos botões visíveis, saída no painel, falha temporária da API, troca de conta, confirmação divergente de senha, convite/cópia, busca, filtros e confirmação/cancelamento de desativação. São capturadas imagens de configurações e administração em desktop/mobile e claro/escuro; as páginas são conferidas quanto a rolagem horizontal e erros de JavaScript. A demonstração pública segue com o fluxo local.

## Atualização da equipe

Depois de integrar esta revisão à `main`, crie um backup e confira alterações locais antes de atualizar o worktree `/home/ubuntu/socialmei-team` para o commit aprovado. Recrie apenas o frontend:

```bash
docker compose --env-file .env.team -f compose.team.yaml \
  up -d --build --no-deps --wait --wait-timeout 180 team-gateway
python3 tools/team-maintenance.py doctor
python3 tools/team-maintenance.py backup
```

O preparador de contas e a criação do administrador não devem ser executados novamente para esta revisão. A configuração privada já ativada é mantida. Após atualizar, recarregue o site e confira saída/entrada com sua conta; não envie senha, cookie ou código de convite para conferência.
