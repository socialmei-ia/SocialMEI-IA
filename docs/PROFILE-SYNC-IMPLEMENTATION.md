# Issue #78 — sincronização do perfil e preferências

Base exata: PR #77, `5d542e2fa675519d99bfcfea5bc899a7225ed885`, que já contém #75. Branch independente; não reaplicar commits das dependências. Sem produção, merge ou deploy.

O perfil adaptativo pertence ao workspace; responsáveis/admins podem editar, membros/viewers consultam. Nome oficial continua no contrato de identidade existente. Preferências essenciais pertencem ao par usuário/workspace: tema oficial claro/escuro/automático e avisos locais/horário silencioso. Temas personalizados e demais preferências, arquivos, rascunhos, canais e automações continuam locais.

A API separa os dois recursos e exige revisão na escrita. O frontend mantém o repositório de perfil já consumido pela Home e catálogo; no modo autenticado ele apresenta dados confirmados pela API em memória. O modo local mantém a API síncrona e as chaves existentes. Leituras antigas e respostas de outra identidade são descartadas. Falha remota não vira escrita local.

Perfis locais anteriores nunca são importados automaticamente nem apagados. A importação abre a revisão nativa e só envia após confirmação final; cancelar não escreve. Um snapshot limitado das preferências locais é preservado antes da aplicação das preferências remotas; se o navegador não conseguir preservá-lo, a aplicação remota fica bloqueada até a recuperação; importá-lo exige revisão/confirmação separada.

Onboarding mantém respostas em caso de erro. No conflito, exibe a versão salva e exige escolha explícita para descartar o formulário e carregá-la. Preferências com falha ficam pendentes na sessão e podem ser reenviadas com a mesma revisão; conflito oferece carregar a versão salva. Formulários de notificações guardam a revisão de quando foram abertos. Não há sobrescrita automática nem sincronização em tempo real: outra sessão recebe alterações ao recarregar.

Testes: Node do store, Python/PostgreSQL de autorização/isolamento/CAS, navegador com API controlada para erros e regressões, e duas sessões reais sobre HTTPS/FastAPI/PostgreSQL descartáveis. Capturas na navegação oficial em320/390/768/1440 e claro/escuro. Contrato e rollout/rollback documentados em PROFILE-SYNC-API.md. CI final e evidências constam na PR Draft. #73 permanece investigação separada.
