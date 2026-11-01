# Direct persistido antes da IA — candidata da issue #177

## Mudança e evidência

No teste autorizado, Meta→n8n recebeu o marcador, mas a API/Caixa não recebeu
mensagens. A inspeção estrutural da **versão publicada** confirmou webhook→switch→IA→envio,
sem chamada de persistência Team. O webhook respondia imediatamente. A versão
salva difere da publicada: não publicar o rascunho inadvertidamente.

Esta candidata acrescenta `POST /webhooks/instagram/n8n`, desabilitado por padrão.
Não depende de IA, Groq/Gemini ou permissão de envio. Reutiliza a transação,
deduplicação e listagem da Caixa existentes; nenhuma migration nova.
Neste incremento, Direct de **texto** é persistido. Anexos não suportados continuam
ignorados pelo contrato existente; não declarar suporte a imagens recebidas.

```text
Webhook existente (bytes originais + assinatura Meta)
  → HMAC próprio com timestamp → API: autenticar ambos → transação PostgreSQL
  → validar recibo → HTTP 200 → fluxo anterior, somente para mensagens novas
Falha antes da confirmação → HTTP 503, sem IA/envio; retry não duplica mensagem.
```

A assinatura própria cobre `timestamp + "\n" + corpo original`, janela de 300s.
A API exige também `X-Hub-Signature-256` original e segredo do aplicativo Meta que
realmente assinou o webhook. Assim, n8n não transforma um POST público forjado em
mensagem confiável. Nunca reconstruir JSON para verificar a assinatura Meta.
Conta→workspace vem da configuração privada e deve coincidir com o OAuth no banco.
Retries exatos são idempotentes e não repetem IA/resposta. Lotes mistos são persistidos,
mas não retomam a automação. Uma resposta perdida pode deixar a automação sem execução;
o histórico fica preservado para atendimento humano.

## Preparar o workflow existente, sem publicar

`tools/prepare-instagram-persistence.mjs` recebe um export **privado da revisão
publicada**, hash SHA-256 e versionId conferidos. Não consulta nem altera n8n.
Mantém ID, webhook, nós, credenciais/referências e expressões anteriores; insere
a barreira de persistência e remove a cópia binária bruta do webhook antes de retomar a IA, preservando seu
JSON anterior. Produz um pacote de atualização para **o mesmo** workflow
`LHlqroY2xzvpYAmD`, não um novo receptor/respondedor. Recusa transformação repetida,
origem sem HTTPS e caminho legado com outro ACK alcançável.

```powershell
node tools/prepare-instagram-persistence.mjs `
  --input 'CAMINHO_PRIVADO\instagram-publicado.json' `
  --output 'CAMINHO_PRIVADO\instagram-candidato.json' `
  --expected-sha256 HASH_SHA256_DO_EXPORT `
  --published-version VERSION_ID_PUBLICADO `
  --api-origin https://socialmei-ia.54-94-213-7.sslip.io
```

Não usar `n8n export:workflow` sem verificar se exportou a revisão **salva** em vez
da publicada. Guardar ambas as revisões separadamente. Export/candidato podem conter
dados privados: pasta com ACL individual no Windows, fora do Git/OneDrive; `0600`
do Node não substitui ACL Windows. A ferramenta não imprime o conteúdo do workflow.

Foi validada em memória contra o grafo publicado real: 9→16 nós, ID preservado,
sem salvar/publicar nada na AWS. Crypto v1 existe no n8n instalado. Isso não prova
execução completa dos nós no n8n: testar rawBody, saída de erro e ACK em ambiente
isolado da mesma versão antes do cutover. Não é necessário liberar `require('crypto')`
no Code: a assinatura usa o nó Crypto existente.

## Implantação proposta — exige autorização específica

1. Escolher a SHA integral desta PR com **Repository checks e imagens aprovados**
   para a mesma SHA. Usar stage/bundle/recibos correspondentes, perfil 035. As
   allowlists aceitam somente a branch exata; gates de origem, hashes, restauração
   e migrations permanecem. Não reaplicar 034/035 nem alterar migrations.
2. Registrar imagens/configuração atuais `266e59b…`, backup atual com restauração
   isolada e export privado de **publicado e rascunho** do n8n. Preservar overlays,
   mounts, volumes, Caddy privado, dados e alterações não commitadas do host.
3. Preparar configuração privada adicional da API, inicialmente desligada:
   `SOCIALMEI_INSTAGRAM_N8N_INGRESS_ENABLED=false`,
   `SOCIALMEI_INSTAGRAM_N8N_INGRESS_KEY` (32–256 caracteres ASCII sem espaços),
   `SOCIALMEI_INSTAGRAM_N8N_META_APP_SECRET` (segredo do aplicativo **assinante**),
   `SOCIALMEI_INSTAGRAM_N8N_ACCOUNT_BINDINGS` (JSON com ID da conta profissional
   existente→workspace 1, obtido do servidor). Chaves de relay e Meta devem diferir.
   A chave do relay também será disponibilizada privadamente ao nó Crypto no n8n;
   o segredo Meta fica somente na API. Não alterar credenciais de IA/OAuth.
   O Compose versionado repassa essas variáveis, mas os overlays privados efetivos
   devem ser reconciliados. Não colocar valores em chat, CLI, logs ou PR.
4. O ID inscrito observado foi `18118497451741626`, diferente do app administrador
   informado `1062521390004147`. Confirmar o aplicativo que assina o evento antes
   de configurar seu segredo. Sem essa confirmação, manter ingresso desligado;
   não usar o segredo OAuth por aproximação, nem reinscrever Meta por tentativa.
5. Atualizar somente API/gateway necessários, preservando configuração privada.
   Reconciliar a rota POST `/webhooks/instagram/n8n` no Caddy **efetivamente montado**
   e proxy público. Limite 65.536 bytes, sem Cookie/Authorization encaminhados;
   assinatura Meta e do relay preservadas. Usar HTTPS existente: não unir bancos,
   publicar 5432 ou abrir `/internal/*`. Revisar logs para não registrar bodies/headers.
6. Em ambiente isolado da mesma versão n8n, provar: assinatura/bytes intactos,
   API indisponível→503 sem IA, IA indisponível após gravação→mensagem preservada,
   replay→uma mensagem e nenhuma segunda resposta. Ambiente privado deve permitir
   acesso do Crypto à variável específica; não relaxar proteções globais às cegas.
7. Após aprovação do plano e credenciais privadas prontas, habilitar somente a
   nova recepção da API. Conferir rota protegida. Preparar e revisar o candidato
   sobre a revisão publicada atual; se o versionId mudou, interromper e reconciliar.
   Publicar atualização no workflow existente apenas sob autorização, preservando
   o rascunho divergente e todas as referências. Sem segundo respondedor.
   Dashboard send e publicações permanecem OFF.
8. Só então pedir **um novo teste real autorizado com marcador novo**. Conferir
   baseline zero, depois um evento/mensagem/conversa em team/1, zero em outro
   workspace, replay sem duplicação e login→Caixa→Instagram com a mensagem. Não
   reutilizar nem reproduzir o marcador anterior. Falha de IA não invalida recepção.

Rollback: restaurar primeiro a revisão publicada anterior do mesmo workflow (assim
cessam chamadas novas); desligar o relay da API e reverter apenas imagens/configuração
alteradas se necessário. Preservar mensagens novas: não restaurar dump sobre o banco
nem apagar ledger para repetir respostas. A revisão 035 anterior lê o mesmo schema.
Mensagens recebidas apenas no n8n legado durante rollback exigem conciliação própria;
não prometer recuperação automática. Nenhuma dessas operações foi executada.

## Testes e limites

Testes API em PostgreSQL descartável cobrem assinatura dupla, corpo alterado,
timestamp, binding, autorização, concorrência, replay, conflito, rollback e leitura
da Caixa sem IA. Testes do preparador cobrem bytes originais, ordem de persistência,
ACK, erro da API, retries, credenciais preservadas e recusa de drift. Gateway é
testado em contêineres descartáveis. CI e imagem não equivalem a implantação ou
homologação real. A prova real de Direct na Caixa continua pendente de cutover autorizado.
