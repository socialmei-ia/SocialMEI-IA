# Instagram Direct antes da IA — preparo e cutover da PR #180

## Contrato

O webhook existente passa por persistência autenticada antes da IA e do envio.
`POST /webhooks/instagram/n8n` permanece desligado por padrão. Não há migrations.
A transação, o ledger e a listagem da Caixa são os existentes; texto é suportado,
anexos ainda não suportados permanecem ignorados. Não declarar Direct de imagens pronto.

A candidata usa `SOCIALMEI_INSTAGRAM_N8N_AUTH_MODE=header`: credencial nativa
**httpBearerAuth** criptografada do n8n, restrita ao nó HTTP, mais assinatura Meta
original obrigatória sobre os bytes originais. Timestamp tem janela de 300s;
o ledger evita reprocessamento. O modo HMAC anterior continua como padrão da API,
sem alteração retroativa. A escolha do modo vem exclusivamente da configuração privada.

O corpo é enviado como `binaryData`, não texto: no n8n 2.40.5 o parâmetro textual
removeu o newline final e invalidou assinaturas. Não reconstruir JSON na entrega.
A cópia binária é removida antes de retomar a IA. Segredos não entram em parâmetros
textuais do workflow, Code, Git ou logs; não liberar `$env` globalmente.

Conta → workspace vem do registro privado. Meta confirmou que o webhook usa
`user_id`, enquanto o OAuth existente guarda `id`, para o mesmo perfil. Usar vínculo
explícito: `{"ID_WEBHOOK":{"workspace_id":1,"connection_account_id":"ID_OAUTH"}}`.
A conexão OAuth ativa e o workspace são conferidos na transação. O formato
`{"ID":1}` continua aceito quando os IDs são iguais. Não alterar registros OAuth.
Fingerprint original é preservado: retry exato deduplica; mesmo MID com identidade
de origem diferente retorna 409, sem segundo append.

```text
Webhook existente → preparar bytes → HTTP autenticado → transação da API
→ validar recibo → ACK 200 → IA anterior, somente quando tudo for novo
Falha de API/autenticação → 503, sem IA; retry não duplica mensagem/resposta.
```

## Evidências de preparação

- O segredo OAuth atual validou criptograficamente a assinatura do evento real
  registrado no n8n, em memória, sem revelar/alterar valores. Pode ser provisionado
  privadamente como segredo Meta dedicado; não solicitar novo segredo em chat.
- O app Meta informado é `1062521390004147`. O produto Instagram informado é
  `2781698107131523`, mas o cliente real do runtime é `27816981071315232`.
  Confirmar a transcrição completa com o administrador. `18118497451741626` foi
  retornado por `subscribed_apps`; não inferir equivalência numérica entre eles.
  Confirmar também o modo Publicado versus desenvolvimento, sem mudar por tentativa.
- Backup atual 035 restaurado manualmente em PostgreSQL 16 local: 35 migrations,
  71 tabelas legíveis, zero constraints não validadas. Dump SHA-256:
  `8a395ed9c088c09709ae9bee85b3dccc4886b2f1d67968bac4a437bcf0139d8c`.
  Transferência binária de pg_dump sem arquivo criado na AWS; restauração em tmpfs,
  sem rede/portas. Roles/grants não restaurados. Renovar antes de cutover posterior
  se houver novas escritas. Dump/logs privados com ACL individual, fora de Git/OneDrive.
- Ensaio com n8n **2.40.5 real**, mesma imagem da produção, credencial nativa cifrada,
  sem liberação de `$env`: primeiro evento 200/uma gravação; IA falhou depois;
  retry 200 sem segunda gravação/IA; API fora 503 sem IA. Bytes/newline e assinatura
  Meta preservados. API desse ensaio era SQLite simulada; FastAPI/PostgreSQL real
  foi validado separadamente. HTTP só na rede interna descartável, sem provedores.
- O publicado mudou durante a preparação: agora 17 nós e dois webhooks POST.
  Atual versão observada: `d141350e-4074-4cfe-8084-154811259287`.
  O receptor do teste tem node ID `f21afb01-56c0-4998-8dfc-9e69c6746d96`.
  Preparação privada seleciona somente esse receptor: 17 → 23 nós, outro webhook
  intacto. Revalidar versão/hash imediatamente antes de atualizar; preservar rascunho.

## Preparador offline

`tools/prepare-instagram-persistence.mjs` não acessa/publica/importa n8n. Exige export
**publicado**, hash, versão e ID da credencial nativa; com múltiplos POSTs exige
seleção inequívoca do node. Preserva o mesmo workflow `LHlqroY2xzvpYAmD`, credenciais
anteriores, expressões e demais receptores. O resultado é pacote de atualização,
nunca um novo receptor/respondedor. A credencial contém só a chave do relay, não o
segredo Meta, e deve pertencer ao projeto autorizado do workflow.

```powershell
node tools/prepare-instagram-persistence.mjs `
  --input 'PASTA_PRIVADA\workflow.published.json' `
  --output 'PASTA_PRIVADA\workflow.candidate.json' `
  --expected-sha256 HASH_DO_EXPORT `
  --published-version VERSION_ID_ATUAL `
  --webhook-node-id f21afb01-56c0-4998-8dfc-9e69c6746d96 `
  --credential-id ID_DA_CREDENCIAL_NATIVA `
  --api-origin https://socialmei-ia.54-94-213-7.sslip.io
```

Guardar publicado/rascunho/candidato fora do Git/OneDrive, com ACL individual.
`mode:0600` do Node não substitui ACL Windows. Não usar export da versão salva
como se fosse a publicada. Candidato privado com `REVIEW_REQUIRED...` como ID de
credencial é apenas revisão: precisa ser refeito com a referência real autorizada.

## Plano operacional — somente após autorização final

1. Usar SHA integral aprovada da PR #180 com checks/imagens da mesma SHA. O HEAD
   `a22c1a9` foi superado pelas correções descobertas no ensaio; não misturar artefatos.
   Conferir bundle/recibos, perfil 035, hashes e restauração. Nenhuma migration nova.
2. Registrar estado anterior e backup recente. Preservar todos os Compose privados
   (12 arquivos API, 11 gateway e 2 legado n8n observados), imagens anteriores,
   mounts, PostgreSQL, WAHA, redes e volumes. Não restaurar dump para rollback de código.
3. Provisionar chave nova e distinta para relay: privada na API e em UMA credencial
   `httpBearerAuth` cifrada no n8n, com permissão do projeto correto. Não trocar
   credenciais existentes de IA/OAuth, liberar ambiente global ou inserir chave em
   parâmetro do workflow. N8n não precisa reiniciar nem trocar imagem para isso.
4. Configurar somente API: `SOCIALMEI_INSTAGRAM_N8N_AUTH_MODE=header`,
   `SOCIALMEI_INSTAGRAM_N8N_INGRESS_ENABLED=false`,
   `SOCIALMEI_INSTAGRAM_N8N_INGRESS_KEY`, `SOCIALMEI_INSTAGRAM_N8N_META_APP_SECRET`
   (segredo atual comprovado) e `SOCIALMEI_INSTAGRAM_N8N_ACCOUNT_BINDINGS` verificado.
   Renovar somente API/gateway necessários usando imagens exatas; deixar envios e
   publicações OFF. Não depender de interpolação de segredo antigo possivelmente
   sobrescrito por overlays: o valor provisionado deve ser o atual comprovado.
5. Aplicar patch mínimo no Caddy **privado montado**, após conferir hash da origem.
   Rota POST exata `/webhooks/instagram/n8n`, limite 65.536 bytes, preservar
   Authorization e assinatura Meta, remover Cookie. Demais rotas continuam com
   política anterior. O proxy público observado preserva Authorization e não
   precisa ser alterado. Conferir redação de headers/bodies em logs.
   Não publicar `/internal/*`, abrir 5432 ou unir redes de bancos.
6. Habilitar somente ingresso novo após verificar saúde/autenticação. Revalidar
   versão publicada, hash e receptor selecionado. Refazer pacote com ID real da
   credencial; publicar no MESMO workflow somente se estado esperado coincidir.
   Preservar cópias privadas de publicado e rascunho divergente. Nenhum novo bot.
7. Sob autorização, solicitar mensagem nova com marcador novo de conta autorizada.
   Conferir baseline zero → uma mensagem/evento/conversa em team/1, zero em outro
   workspace e exibição em login → Caixa → Instagram. IA indisponível não pode
   impedir a persistência. Não reutilizar/reproduzir o marcador anterior.

Rollback: restaurar primeiro a versão publicada anterior do mesmo workflow,
desligar relay, restaurar Caddy/imagens/configuração afetados. Não apagar ledger,
mensagens, volumes ou restaurar dump sobre escritas novas. A revisão 035 anterior
usa o mesmo schema. Eventos recebidos só no legado durante rollback exigem
conciliação própria; não prometer recuperação automática. WhatsApp #179 permanece
separado, com seu mount/registro/flags preservados. Nenhuma ação acima foi executada.
