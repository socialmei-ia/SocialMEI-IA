# Release040 — preparação, sem publicação

Código das imagens: `9b34ac80ee5f2d9d6a12aa1b5c7e254bccb0c4d8`.
Commits posteriores de ferramentas/evidência não substituem essa identidade.
Produção não foi publicada, migrada, reiniciada ou reconfigurada.

## Artefatos e configuração

- API: build local com `deploy/team/Dockerfile.release040-api`, contexto raiz,
  argumento `SOCIALMEI_RELEASE_SHA` completo. Inclui o worker Instagram.
- Gateway: `deploy/team/Dockerfile`, mesmo argumento SHA. Ambos possuem label OCI.
- Os arquivos `.dockerignore` específicos excluem configurações privadas do contexto.
- Renderizar configuração **em arquivo privado**, com `--env-file` privado e, nesta
  ordem: `compose.team.yaml`, `compose.team-recovery.yaml`,
  `compose.team-identity.yaml`, `compose.team-instagram-auto.yaml`,
  `compose.team-public-booking.yaml`, `compose.team-release040.yaml`.
- Informar IDs imutáveis em `SOCIALMEI_API_IMAGE`/`SOCIALMEI_GATEWAY_IMAGE` e
  `TEAM_AUTH_ENABLED=true`. Não exportar o JSON de configuração para logs/Git.
- `tools/release040-preflight.py --compose-json <privado> --rehearsal <recibo040>
--rollback-rehearsal <recibo de rollback> --source-sha <SHA completo>
--api-image <ID> --gateway-image <ID>` verifica
  artefatos locais, conexões iguais, redes, mounts, comandos e recursos desligados.
  Nunca aprova produção nem executa publicação. Perfis opcionais continuam inativos.
- O overlay exige Compose com suporte a `!reset`/`!override`, remove builds/bind de
  código e dependência implícita do migrador. Migrador fica em `maintenance040`.
  Isso não autoriza executar esse perfil. Não usar publicadores legados.

## Sequência obrigatória para uma publicação futura

1. Obter dados atuais acessíveis e comprovar identidade da origem. Backup038
   histórico não substitui dados atuais. Não reativar janela Prisma sem autorização.
2. Comprovar backup externo e restauração isolada, IAM e capacidade sob carga.
   A amostra AWS registra API antiga unhealthy e pouca RAM; não aprova capacidade.
3. Conciliar overlays, redes, sessões, filas, volumes, credenciais e patches
   instalados. Comparação de três arquivos não certifica toda a árvore instalada.
4. Após autorização de leitura do banco, usar `tools/schema040-premigration.sql`
   com o papel de migração sobre039: transação somente leitura, sem dados pessoais
   no resultado. Conferir também privilégios/locks do ambiente real.
5. Obter aprovações específicas para atualização040, eventual troca de provedor e
   publicação. Coordenar pausa dos escritores, dump final e integridade antes do
   corte. Nenhum desses passos foi executado nesta missão.
6. Publicar apenas IDs aprovados, incrementalmente e sem acionar dependências ou
   migrador automático. Validar readiness autenticado040, login, sessões, isolamento,
   Agenda e filas antes de liberar tráfego. Interromper em qualquer divergência.
7. Ativar SMTP/canais separadamente, após capacidade, conta/destinatário controlado,
   permissões Meta e exclusividade do respondedor comprovados.

Rollback aprovado em ensaio: candidata9b → imagemB2 com guarda040, preservando
o mesmo banco040, contas pendentes, sessões e filas. Não fazer downgrade de schema,
restaurar backup antigo sobre gravações novas ou repetir envios incertos. Reverter
somente imagens/configuração conciliada; conferir saúde, identidade e isolamento.
Falha de persistência, saúde, duplicação ou isolamento impede continuar a ativação.

Evidências sanitizadas em `docs/evidence/20261113-mission3-release.json`,
`20261113-runtime-capacity.json` e `20261113-schema040-rollback-rehearsal.json`.
