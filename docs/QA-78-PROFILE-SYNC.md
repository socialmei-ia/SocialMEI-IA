# Issue #78 — perfil e preferências autenticados

## Entrega e dependência

Base: `5d542e2fa675519d99bfcfea5bc899a7225ed885`, HEAD da #77, que já inclui #75. A branch `feat/workspace-profile-sync` acrescenta os contratos documentados em [PROFILE-SYNC-API.md](PROFILE-SYNC-API.md) e o comportamento descrito em [PROFILE-SYNC-IMPLEMENTATION.md](PROFILE-SYNC-IMPLEMENTATION.md). Não modifica as PRs anteriores, a main ou produção. A PR Draft depende da revisão da #77; o diff contra main inclui essa ancestralidade, sem cherry-picks duplicados. A investigação #73 continua separada e aberta.

## Comportamento concluído

- Perfil comercial compartilhado entre membros do negócio; somente responsáveis e administradores podem alterá-lo. Preferências essenciais separadas por usuário/workspace.
- Temas oficiais, avisos locais e horário silencioso carregados da conta; atualização em outro dispositivo após recarga. Seis etapas, IDs e personalização existentes preservados.
- Revisões otimistas impedem sobrescrita entre sessões. Conflitos mostram a versão salva e preservam o formulário até uma escolha explícita. Falhas não geram sucesso fictício nem fallback de escrita local.
- Perfil local legado preservado, sem importação automática; revisão, cancelamento e confirmação explícitos. Preferências locais antigas são preservadas antes da aplicação da versão remota. Troca de identidade invalida caches, respostas atrasadas e tentativas pendentes.
- Modo local mantém o repositório e as chaves anteriores. API ausente informa indisponibilidade sem simular sincronização.

## Verificações executadas

- Node: 271 testes aprovados, incluindo 13 do novo store (CAS, offline, isolamento, respostas atrasadas, snapshots e troca de workspace).
- Backend: 172 testes aprovados sobre PostgreSQL 16 descartável, incluindo autenticação, Origin/CSRF, papéis, isolamento, concorrência, validação e limite canônico de 32 KiB.
- Navegador focado: onboarding adaptativo, personalização, contas, sincronização, Configurações (990 estados) e regressões de layout. A suíte completa e os checks remotos são registrados na PR com seu SHA final; resultados pendentes não são considerados aprovação.
- Prova HTTPS real: cadastro nativo e duas sessões com cookies distintos no mesmo negócio, confirmação da alteração após recarga, conflito 409 sem perda, falha de conexão/retentativa, tema e notificações compartilhados entre dispositivos do mesmo usuário; uma terceira conta prova isolamento. Nenhum serviço externo ou dado real.
- Capturas na navegação oficial: 320, 390, 768 e 1440 px, claro/escuro; conflito preservado e indisponibilidade. Teclado e movimento reduzido cobertos na suíte de navegador.

Os ajustes de fixtures representam os novos recursos de API e o perfil compartilhado; as verificações de autorização e de ausência de escritas comerciais permanecem. O teste de Oportunidades agora espera a inicialização autenticada concluir antes de navegar, evitando concorrência com a navegação inicial.

## Rollout e rollback — documentação, sem execução

1. Revisar #77 e esta PR, obter CI verde no HEAD final e autorização específica para publicação. Fazer o backup documentado do ambiente e registrar imagens/checkout anteriores.
2. Aplicar a migration incremental `013_workspace_profile_sync.sql` com a rotina de migrations existente e publicar backend compatível antes do frontend. Nunca usar as rotinas de teste, que apagam dados descartáveis, em outro banco.
3. Conferir sessão, papel e isolamento com contas de teste autorizadas, sem importar valores locais automaticamente. Na ausência do contrato novo, o frontend informa indisponibilidade.
4. Se necessário, reverter as imagens de frontend/backend para a versão registrada. Manter as duas tabelas novas e seus registros; versões anteriores não as utilizam. Não executar DROP nem desfazer migrations destrutivamente como rollback automático. Dados confirmados devem ser preservados para retomada posterior.

Nenhuma migration, imagem, credencial ou infraestrutura de produção foi alterada nesta tarefa.

## Limitações e pendências

- Não há atualização em tempo real nem mesclagem automática de conflitos: é necessário recarregar e decidir explicitamente.
- Rascunhos e tentativas pendentes são mantidos na sessão aberta; fechar/recarregar a página pode descartá-los. Não há fila offline persistente.
- Temas personalizados, arquivos, rascunhos Instagram, canais e demais preferências continuam locais. Um tema personalizado local ativo tem precedência visual; suas definições não são enviadas ao servidor.
- Avisos configurados continuam sendo preferências do aplicativo; não representam envio de WhatsApp, push ou e-mail.
- Publicação depende de revisão humana, migration 013 e deploy autorizados separadamente. Não houve merge, deploy, AWS, n8n, Meta ou banco real.
