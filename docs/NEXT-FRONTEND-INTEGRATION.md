# Próxima entrega: integrar o frontend do proprietário

Este é o ponto de continuidade da tarefa. O proprietário está preparando o visual separadamente e enviará um ZIP. Até recebê-lo, preservar o frontend atual; não criar outro layout, protótipo, aplicação ou autenticação.

## Referência preparada

- PR111 Draft: https://github.com/socialmei-ia/SocialMEI-IA/pull/111
- Branch: `feat/backend-provider-readiness`.
- Base funcional desta preparação: `084107726c00d20eb6de5118490213bb208130c5`.
- Aplicação oficial: `frontend/socialmei-app.html`, HTML/CSS/JS vanilla.
- Banco candidato: migrations001–026. Não significa migrations instaladas na AWS.
- Autenticação, workspace, stores e API existentes são a fonte de verdade. O frontend novo modifica a apresentação; adaptações de conexão serão implementadas conforme os arquivos reais, sem antecipar uma arquitetura desconhecida.
- Contratos: [handoff](BACKEND-FRONTEND-HANDOFF.md), [operação/sessões/fila](BACKEND-OPERATIONS-READINESS.md), [recuperação](ACCOUNT-RECOVERY.md), [API](API-ENDPOINTS.md).

## Pendências que não podem ser esquecidas

| Pendência             | Estado e próximo passo                                                                                                                                                                                                                            |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CI da candidata       | Conferir no último HEAD, não herdar aprovação de outro commit. Run0841077: https://github.com/socialmei-ia/SocialMEI-IA/actions/runs/40233981929                                                                                                  |
| AWS compartilhada     | Usuário quer AWS como base da equipe. Restabelecer acesso seguro, inventariar imagens/API/checkout/schema e só depois atualizar o conjunto compatível com backup/rollback. Não afirmar instalação a partir do GitHub.                             |
| Hotfixes publicados   | Preservar landing primeiro para anônimos e gateway público sem Basic. Não reconstruir usando configuração antiga nem desativar autenticação individual.                                                                                           |
| Gmail                 | Código SMTP pronto, mas conta remetente, credencial privada, entrega e quotas não homologadas. Não pedir credenciais no chat nem incluí-las no ZIP.                                                                                               |
| Worker de recuperação | Fila026 preparada; instalar/agendar o worker explicitamente após homologação. Não está executando na AWS. Código de recuperação não é persistido em texto puro.                                                                                   |
| Instagram/n8n         | Conferir workflows vivos do colega em leitura. Definir workspace, autenticação, eventos, catálogo, idempotência e um único responsável pelos envios. Runtime opcional desligado. Não conectar ou publicar automaticamente ao importar o frontend. |
| WhatsApp              | Alinhar GOWS/WEBJS e edição/HMAC do WAHA. Número, pareamento e envio ainda não homologados.                                                                                                                                                       |
| Banco/backup          | Conferir migrations e privilégios reais, backup atual e restauração. Ensaios descartáveis001–026 não substituem a inspeção da VPS.                                                                                                                |
| Segurança/usuários    | APIs de sessões prontas; controles visuais poderão vir no ZIP. Verificação/troca de e-mail, MFA, notificações, LGPD e alertas operacionais continuam etapas próprias.                                                                             |

## Recebimento do ZIP

1. Confirmar HEAD remoto/branch, árvore limpa e instruções AGENTS aplicáveis. Registrar SHA e hash do pacote recebido.
2. Inspecionar o ZIP em diretório temporário separado: estrutura, arquivos, dependências, links externos e licença dos assets. Rejeitar caminhos que escapam do diretório, symlinks perigosos e extrações desproporcionais. Não executar scripts de instalação apenas por estarem no pacote.
3. Identificar o HTML de entrada e comparar o conteúdo com o frontend atual. Não presumir que o ZIP contém backend atualizado ou configuração segura.
4. Não copiar `.env`, credenciais, dumps, dados reais, configurações privadas do gateway ou `config.js` contendo segredos. Preservar o `config.js` efetivo privado da AWS; a configuração pública do Git hoje inicia módulos em modo local.
5. Mapear seletores/IDs/eventos usados pelos scripts existentes. Reaproveitar controllers/stores; se o HTML novo usa outros IDs, adaptar explicitamente os vínculos em vez de criar gravações paralelas.
6. Preservar ordem de scripts clássicos. Não adicionar `async`, `defer` ou módulos em lote. Não importar CSS global sem verificar colisões entre módulos/temas.
7. Integrar por fluxo completo: shell/navegação → contas/onboarding → gestão → Caixa/Oportunidades → Divulgação → Relatórios/Configurações, ajustando a ordem conforme o pacote. Concluir/testar cada parte antes de declarar pronta.
8. Fazer commits específicos na candidata, sem sobrescrever trabalho alheio. Revisão/publicação são operações distintas; não executar merge/deploy automaticamente ao receber o ZIP.

## Contratos essenciais para conectar o visual

| Tela                                | Integração a preservar                                                                                                                                                                             |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Visitante/login                     | Landing pública; `auth/session` retorna200/null para visitante; autenticação remota com cookie HttpOnly/Secure, same-origin HTTPS.                                                                 |
| Cadastro                            | Consultar `auth/registration`; não assumir aberto. Nome/e-mail/telefone e senha8–128, bloqueio de senhas comuns. Não simular conta persistida.                                                     |
| Esqueci minha senha                 | `auth/recovery/request`202 genérico; `auth/recovery/confirm`204. Não mostrar conta encontrada, código, envio concluído ou entrega garantida.503 significa indisponibilidade/configuração pendente. |
| Sessões                             | Listar acessos próprios; UUID público não autentica. Revogar outros exige senha atual. Não guardar senha/código em localStorage.                                                                   |
| Perfil/Home/catálogo                | Mesma sessão/workspace e revisão do perfil. Sugestões não criam produtos; serviços não têm estoque físico.                                                                                         |
| Clientes/produtos/vendas/financeiro | Stores e modelos existentes; versões/operações idempotentes; preservar dados e formulário em erro, sem fallback remoto→local.                                                                      |
| Caixa/Oportunidades                 | Identidades estáveis do servidor, revisão humana, evidências e planejamento. Não registrar mensagens ou vendas fictícias como reais.                                                               |
| Divulgação                          | Distinguir rascunho/prévia/simulação de publicação aceita/entregue. Consultar capacidades; conexão externa não é implícita no login.                                                               |
| Relatórios                          | Motor financeiro existente; não duplicar receitas/vendas nem importar a amostra sintética do ZIP como dados reais. Preservar CSV, impressão/PDF e histórico por identidade.                        |
| Configurações                       | Manter limites local/remoto e segurança; diagnóstico global exclusivo de administrador da plataforma, nunca de qualquer dono de negócio.                                                           |

Escritas autenticadas usam Origin e `X-SocialMEI-CSRF`; login/cadastro/recuperação usam JSON e `X-SocialMEI-Client: browser`. `SocialMEIAuth.request` centraliza o transporte no frontend existente. Nunca enviar workspace arbitrário como autorização.

## Aceite da integração

- API/modelos e erros401/403/409/422/503 respeitados; nenhuma gravação fictícia ou integração inventada.
- Duas contas/negócios isolados, troca de usuário e persistência local existente preservadas.
- Cadastro/login, recuperação, perfil, CRUD de gestão, Caixa/Oportunidades, Divulgação e Relatórios testados no modo realmente suportado.
- Desktop/mobile320/360/390/768/1024/1440, Light/Dark, teclado/foco, zoom e movimento reduzido. Capturas da aplicação oficial integrada e comparação com o ZIP, sem exigir que o design novo repita o antigo.
- `npm test`, `npm run format:check`, testes backend em PostgreSQL descartável, browser/preview e ensaio de migrations/restore pertinentes. Nenhuma asserção removida para esconder falha.
- CI do HEAD final, contratos de deploy/hotfixes e rollback conferidos. Não chamar preview de produção ou considerar um botão visual como conexão real.

## Não antecipar agora

Não adicionar React, outro hub/iframe, layout substituto, autenticação paralela, banco novo ou migração para acomodar um HTML ainda não recebido. Não alterar o frontend atual para tentar adivinhar o conteúdo do ZIP. A preparação é dos contratos, do histórico e dos critérios de integração.
