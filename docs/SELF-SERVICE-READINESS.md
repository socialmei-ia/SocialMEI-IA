# Autosserviço — candidata para homologação

Implementação local; nenhuma publicação, migration real, pareamento ou mensagem
externa foi executada. Preserva os fluxos da Missão 1 e incorpora a continuidade
`ops/readiness-sem-codex-20261113` até `367a03c`.

## Contas, equipe e configuração

- A candidata requer **schema040**, inclusive com envio desativado. As migrations
  001–039 permanecem intactas. `--profile 040` valida a cadeia completa; os perfis
  antigos continuam recusando fontes incompatíveis.
- `SOCIALMEI_IDENTITY_MODE=disabled` é o padrão. Ativar `enforced` somente após
  aprovação da instalação040, SMTP privado e recebimento controlado. Cadastro
  obrigatório falha fechado sem configuração SMTP; não cria conta parcial.
- API e `compose.team-identity.yaml` usam a mesma `TEAM_APPLICATION_DATABASE_URL`.
  O perfil `identity-mail` é opcional. Worker explícito: `identity_worker.py --run
--watch --limit 10`. Poll60s ou LISTEN opt-in com reconciliação300s; fila durável.
- SMTP usa `SOCIALMEI_SMTP_HOST/PORT/USER/PASSWORD/FROM`, TLS465 ou STARTTLS587,
  credenciais fora do Git. Link no fragmento, hash persistente, validade30min,
  uso único, reenvio limitado e entrega incerta sem retry automático.
- Contas pendentes **continuam bloqueadas se o modo de envio for desligado**.
  Contas antigas sem solicitação não são marcadas falsamente como verificadas.
- Convites de equipe são separados do convite global da plataforma. Proprietário
  escolhe o papel; aceite confere empresa, destinatário e autorização atual.
  Conta existente exige sessão própria e CSRF, preservando senha e outros negócios.
  Conta nova não cria outro negócio. Revogação de acesso exige papel esperado.
- Catálogo inicial só é criado após confirmação de preço/duração; rascunho,
  recibo e retry são persistentes. Horários e profissionais reutilizam a Agenda.

## Canais e experiência

Instagram usa identidade OAuth verificada, permissões, expiração e recibos reais
da conexão. Metadados de preparação não significam conexão. Homologação Meta real
continua pendente; renovação e desconexão preservam os contratos existentes.

WAHA mantém registro privado e motor do piloto. Gerenciamento e inspeção são
opt-in, desativados; capacidade padrão2. Solicitações são duráveis e não executam
criação/start/stop/pareamento/transferência. Provisionamento, capacidade e
respondedor único precisam de aprovação operacional. Não há QR fictício.

Página pública preserva confirmação incerta e limita requisições a20s. Caixa
ganha larguras por conta/negócio, agrupamento seguro e espaço de leitura; landing
respeita movimento reduzido. Oportunidades consultam API e preservam dados em falhas.

## Publicação e rollback futuros

Executar o ensaio `tools/release040-migration-rehearsal.py` somente com checkout
limpo e imagem local de SHA exato. Ele cria PostgreSQL sem rede pública, restaura
039, aplica040 em cópia, confere integridade/reexecução/constraints e restaura040.
Não aceita DSN externa nem substitui o procedimento de corte do banco real.

Antes de publicar: dados atuais, backup externo restaurável, capacidade AWS,
privilégios/locks reais, overlays privados conciliados e aprovação específica.
Não usar publicador legado nem executar `compose up` que acione o migrador real.
Rollback deve usar imagem **compatível com040 e a guarda de verificação**; voltar
ao código039 poderia liberar contas pendentes. Preservar tabelas, filas, sessões,
volumes e credenciais; não fazer downgrade nem replay automático de mensagens.

## Evidência da entrega

Código e imagens locais: `b2b839b`. Regressão:986 Python,440 JavaScript
(2 skips existentes),11 testes operacionais de release e navegador completo
(286 estados,42 jornadas públicas e8 de identidade), com transportes controlados.
O ensaio040 dessa imagem restaurou039/040 e aprovou os gates de integridade.
Recibos sanitizados: `docs/evidence/20261113-selfservice-release.json` e
`docs/evidence/20261113-schema040-rehearsal.json`. Não comprovam produção.
