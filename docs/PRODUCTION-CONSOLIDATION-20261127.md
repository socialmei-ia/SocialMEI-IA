# Consolidação de produção — 27/11/2026

O manifesto em `deploy/production-overlay/20261127/manifest.json` registra a imagem base e o SHA-256 dos arquivos efetivos alterados em cada função. As variantes de API principal, API do menu, worker WhatsApp e edge têm destinos distintos. A imagem Instagram inspecionada não apresentou alterações Python na camada do container e ficou registrada pelo ID.

`python tools/build-production-overlay.py` verifica os bytes. Com a imagem base original carregada localmente, `python tools/build-production-overlay.py --build api` constrói uma camada offline. Use `--build gateway`, `--build menu`, `--build worker` ou `--build edge` para os componentes correspondentes. Guarde as imagens base por ID antes de limpar o cache. Um bind ativo prevalece sobre a imagem construída. Para publicar, confira cada bind com o manifesto e preserve os arquivos privados que o runtime usa.

O app versionado incorpora o frontend servido na AWS. Os arquivos identificados de Agenda, Relatórios e Caixa v7.9.5 coincidem byte a byte com o pacote disponível. O Hero aprovado permanece na imagem base capturada. O manifesto omite a configuração privada do frontend e as credenciais do runtime.

O ledger produtivo registra a migration 041. A cadeia SQL versionada foi preservada. O ledger comprova o registro da migration e não certifica a equivalência de todo o schema instalado. Antes da próxima release, compare a estrutura efetiva com uma restauração descartável e ensaie a recriação com os mounts e aliases reais.

Os overlays reproduzem o delta de arquivos observado sobre as imagens fixadas. A promoção exige validar as imagens construídas, as configurações privadas por serviço e os fluxos reais. Para rollback, preserve a imagem, configuração e mounts anteriores de cada componente. Pare qualquer remetente novo antes de restaurar o anterior e mantenha o ledger e os journals de envio.

Para a candidata com as correções autenticadas, use `python tools/build-production-overlay.py --build gateway --gateway-fixes` a partir do commit revisado. A ferramenta valida a captura original e imprime os hashes dos quatro arquivos de aplicação incorporados na candidata.

O primeiro ensaio local reconstruiu as seis funções com as imagens-base por ID. A verificação sem rede comparou os arquivos e a sintaxe dos módulos. No gateway, conferiu o app com os binds de `config.js` sintético e CRM capturado. No worker, conferiu o guard, os caminhos de secrets, o journal e a configuração GOWS sem iniciar o remetente. O `index.html` e os arquivos principais do Hero têm os mesmos bytes da imagem base.

O navegador passou pela Agenda como proprietário e como visualizador em duas larguras. A jornada inclui recuperação de leitura, registro idempotente, conclusão e cancelamento com dois cliques. O relatório somente leitura passou com sessão simulada.

A API ativa depende de arquivos privados que estão na camada gravável do container e não integram a imagem-base. Preserve a montagem de CA e os mounts existentes. Exija também um bind privado somente leitura para `/app/.human-gows-key.private`, lido na inicialização. Preserve as configurações de Agenda e IA em `/app/.socialmei-booking-signing.private`, `/app/.instagram-ai-runtime.private.json`, `/app/.socialmei-content-ai.private.json` e `/app/.socialmei-commercial-analysis.private.json`. A API privada do menu usa seu próprio arquivo de assinatura de Agenda, `/app/.everson-pilot.private.json` e `/tmp/.socialmei-typing.private.json`. Confira a presença e as permissões desses arquivos nos dois sentidos do rollback. Mantenha valores, chaves e tokens fora de artefatos de imagem e do Git.

A recuperação de conversas usa uma candidata combinada de API (`--build api --inbox-fixes`) e gateway (`--build gateway --gateway-fixes`) com migrations 042 e 043. A migration 043 mantém o registro da ocultação e torna a recuperação explícita e repetível. Em rollback para uma API anterior à 043, a lista antiga pode voltar a ocultar itens restaurados. Preserve a coluna e o registro para que a recuperação reapareça com a API compatível. A promoção ainda exige backup verificável e ensaio integrado dos serviços com os mounts equivalentes, incluindo rollback. Nenhuma migration desta candidata foi aplicada na AWS.

O ensaio em rede Docker interna restaurou o schema da AWS em PostgreSQL 17, aplicou 042 e 043 e verificou a consulta da API ao banco, o HTTP do app pelo Caddy e a resolução DNS das seis funções. A reversão do gateway para a imagem-base fixada repetiu os mesmos health checks. Menu, edge e workers ficaram em espera, sem consumir eventos. A reversão conjunta com os serviços e mounts produtivos completos ainda precisa ser ensaiada.

## Candidata da Missão 05

- Menu privado: `python tools/build-production-overlay.py --build menu --whatsapp-media`.
- API: `python tools/build-production-overlay.py --build api --inbox-fixes --media-commercial`.
- Gateway: `python tools/build-production-overlay.py --build gateway --gateway-fixes`.

Os builds preservam os arquivos capturados e aplicam as mudanças da candidata separadamente. Aplique em homologação a cadeia de migrations até 046 antes de iniciar a API candidata. A 045 reconcilia o campo de intenção comercial já presente no schema capturado. As preferências pessoais da Caixa usam 044 e 046. Em rollback, preserve esses registros para que voltem a aparecer com a versão compatível.

A automação por áudio é restrita ao vínculo revisado de Brilho60. O menu privado lê `SOCIALMEI_WHATSAPP_MEDIA_START_UTC` para permitir novos eventos por áudio depois de um corte explícito. A análise comercial de mídia usa `SOCIALMEI_WHATSAPP_MEDIA_COMMERCIAL_ENABLED=YES` na API, além das permissões já exigidas. Habilite cada opção somente após homologar o fluxo com os provedores autorizados e revisar a configuração privada. O agendamento iniciado por áudio apresenta serviços. A seleção e a confirmação usam mensagens explícitas e as validações transacionais existentes.

`tools/test-whatsapp-media-candidate.py` e `tools/test-whatsapp-media-commercial-candidate.py` exercitam os contratos HTTP em sequência, com as respectivas imagens, PostgreSQL 17 descartável `media_candidate_test` e rede Docker interna. Use uma chave sintética em um bind somente leitura para `/app/.human-gows-key.private` na API. Nenhum dos ensaios envia mensagens ou chama Gemini, Meta ou n8n.

## Candidata da Missão 06

Compile a API com `--build api --inbox-fixes --media-commercial --instagram-media`, o menu com `--build menu --whatsapp-media` e o gateway com `--build gateway --gateway-fixes`. A migration 047 adiciona a fila de anexos do Instagram. Respostas rápidas usam a configuração versionada do próprio negócio.

O ingresso de imagens e áudios do Instagram fica desligado até definir `SOCIALMEI_INSTAGRAM_INBOUND_MEDIA_ENABLED=YES`. O comando `python -m instagram_inbound_media --workspace ID` processa um anexo elegível por vez. Use armazenamento privado compartilhado no caminho `/run/socialmei/private/inbound-media-v1/instagram`, com escrita só para o worker e leitura pela API sob UID compatível. O comando não envia mensagens. Antes de ativar, valide os hosts de mídia com eventos reais autorizados, a política de retenção e a capacidade de disco. Para reverter, pare o worker e desligue a opção na API. Preserve os eventos, arquivos e a migration para manter a recuperação possível.
