# Piloto WhatsApp da equipe — provisionamento do canal

Objetivo: conectar **somente o número de testes autorizado** ao
workspace **1 (SocialMEI Equipe)**, sem mexer no bot Gemini que já envia
mensagens pelo n8n. Este procedimento prepara a identidade do canal e seu
registro HMAC; **não habilita recebimento, bot, rede, webhook nem envio**.

## Estado de referência (29/10/2026)

- WAHA com uma sessão WORKING e um webhook apontando para `/webhook-test/`.
- Workflow publicado do n8n: `NFcJfjvpaUsjh1x1`, com WAHA Send Text,
  Gemini e Google Sheets. A versão publicada não equivale a entrega real.
- API Team v33 com `whatsapp_bot`, `waha_ingress` e migração 032.
- Workspace ID1 existente, mas não há canal WAHA nem credencial do bot.
- API e n8n/WAHA em redes Docker separadas; o overlay opcional de ponte
  existe no GitHub, mas a rede `socialmei_team_automation` não foi criada
  no runtime inspecionado.
- Flags WAHA ingress, catálogo e bot permanecem desligadas.

## Ferramenta para o operador Ubuntu

Arquivo `tools/team-whatsapp-pilot.py` no branch do PR deste plano.
Usa somente bibliotecas Python padrão e a CLI Docker. Deve ser executado
**no host Ubuntu**, não dentro do container.

Primeira execução obrigatória (somente leitura):

```bash
python3 tools/team-whatsapp-pilot.py
```

O comando valida a única sessão WORKING, engine WEBJS, final autorizado
**5976**, existência do workspace, estado do webhook/HMAC, contadores de
canais, mount privado e redes Docker. Não imprime o telefone completo,
segredos, conteúdo de mensagens ou URL do webhook.

Se houver qualquer divergência, interromper o procedimento. Uma sessão
WORKING não prova o número sem conferir `me.id` do WAHA; este script falha
fechado quando não consegue validar a identidade.

Após um backup atual e revisão do resultado, existe uma etapa **explícita
que altera o PostgreSQL**:

```bash
python3 tools/team-whatsapp-pilot.py --prepare-channel --confirm TEAM-1
```

Essa etapa exige zero canais WAHA anteriores e registry ausente; cadastra
um canal inicialmente inativo, grava o registry privado em
`deploy/team/private/waha-registry.json` (0600, sem sobrescrever), e só
depois marca o vínculo `ativo/ingress_provisioned=true`.
O envio continua desabilitado. O arquivo é montado em
`/run/socialmei/private` dentro da API, e o loader não usa cache.

Se falhar depois da reserva, **não repetir** sem conferir o estado: uma
linha inativa e/ou registry parcial podem ter sido preservados para
recuperação segura. Não copiar nem mostrar o registry.

## O que permanece pendente

1. Confirmar que o workspace da equipe possui um usuário owner/admin
   autorizado a administrar o piloto. Se não houver, resolver a associação
   pela gestão autenticada antes de emitir credenciais.
2. Anexar n8n/WAHA à rede privada `socialmei_team_automation` por Compose
   efetivo e revisado, preservando a rede/volumes/banco legados.
   Usar `compose.team-n8n-bridge.yaml` para n8n e\n   `compose.team-waha-bridge.yaml` para WAHA, preservando os serviços atuais.\n   `docker network connect` improvisado não é implantação persistente.
3. Preferir um **segundo webhook WAHA direto** pela rede privada para\n   `http://team-api:8000/internal/waha/{instance}/webhook`, mantendo\n   temporariamente o webhook n8n existente. Assim a assinatura HMAC SHA512\n   valida os bytes originais, sem reserialização pelo n8n. Antes da mudança,\n   conferir suporte a múltiplos webhooks e se alterar a sessão causa reinício.\n4. Alterar e ativar flags isoladas somente após o receptor responder com
   compromisso de gravação na Caixa Unificada e validação de negócio.
5. Usar um único sender, com claim/recibo; verificar se o bot antigo ainda
   envia mensagens, preservar opção de atendimento humano. Não ativar
   dois respondentes.
6. Menu inicial de texto (0–5) e catálogo real; listas nativas dependem
   da engine GOWS/NOWEB e de homologar o payload de resposta. Não trocar
   engine WEBJS de número em uso só para exibir botão.
7. Criar produto de demonstração pelo site no workspace escolhido e
   conferir o caminho completo com mensagem autorizada.

Não expor `/internal/*` publicamente, não compartilhar API keys, segredo
HMAC, tokens ou registros privados e não migrar o número para outra conta
sem conferência do vínculo.
