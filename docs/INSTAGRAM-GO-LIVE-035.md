# Instagram no ar — liberação controlada da candidata 035

Este documento acompanha a **branch consolidada** `feat/instagram-direct-durable-recovery-20261101` (PR #176), que contém as mudanças das PRs #173–#175 em sua ancestralidade. **Não presuma que uma PR aprovada foi implantada:** o GitHub Actions apenas produz artefatos fora da AWS.

## Escopo e critérios de funcionamento

| Recurso | Contrato e prova necessária |
| --- | --- |
| Conexão profissional | Sessão autenticada, OAuth ligado à empresa certa e token não expirado, com `instagram_business_basic` |
| Feed | Configurações → Integrações → Instagram → Ver publicações; dados da Meta, não de uma fixture |
| Recepção Direct | GET do desafio Meta, webhook POST assinado, mensagem de uma **conta de teste autorizada** na Caixa Unificada, persistência no workspace certo e idempotência de eventos |
| Resposta Direct | Rascunho preservado, aprovação explícita, somente um respondedor n8n/dashboard, confirmação do ID da Meta e nenhuma repetição em caso incerto |
| Publicar foto | Perfil confirmado, permissão `instagram_business_content_publish`, foto armazenada temporariamente e acessível à Meta, legenda e confirmação humana, recibo da Meta e publicação visível no feed |
| Segurança | Nenhuma credencial no frontend/log; autenticação, CSRF, assinatura Meta, separação de empresas e backup comprovados |

O Instagram exige conta profissional e escopos específicos, conforme a coleção de documentação da Meta: https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api .

## Preparação — não muda a AWS

1. Confirmar que PR #176 aponta para o commit **exato** desejado e que os workflows **Repository checks** e **Team v33 candidate images (off-VPS)** estão verdes para a **mesma SHA de 40 caracteres**.
2. Baixar o artefato `SocialMEI-Team-<SHA>` desse run. Conferir integridade do ZIP, `image-receipt.json`, `SHA256SUMS`, perfil 035 e prova da restauração descartável. Não usar artefato de uma SHA anterior.
3. Em sessão administrativa já autorizada na AWS, fazer inventário **somente leitura** do checkout legado e team, banco/migrations, redes/serviços e n8n. Não sobrescrever `/home/ubuntu/socialmei-team`, `/home/ubuntu/socialmei`, arquivos `.env`, credenciais ou os volumes existentes.
4. Preparar checkout Git **separado/limpo** do commit exato em pasta privada. O script de stage `tools/team-v33-stage.py` exige **branch allowlisted e HEAD remoto exato**; o importador `tools/team-v33-import-images.py` exige o seu recibo. Usar as versões desses scripts correspondentes à SHA da candidata; as cópias antigas do servidor não reconhecem esta branch. Não atualizar o checkout ativo só para executar o stage.
5. Conservar o comprovante de restauração/migration 033→035 do CI. O stage exige `--migration-rehearsal` correspondente ao mesmo commit. Os hashes das migrations 001–035 são verificados, e nenhuma migration antiga pode ser editada.

Exemplo **somente leitura** de inventário, para operador já conectado à EC2:

```sh
cd /home/ubuntu/socialmei-team
git status --porcelain=v1
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
python3 tools/team-v33-stage.py --target team --inspect
```

**Não execute** `git reset --hard`, `git clean`, `git stash`, `docker compose down -v` ou exclusão de volumes. O script de stage é uma etapa de **preparação**, não um deploy.

## Antes de recriar qualquer contêiner

- Backup consistente, datado, protegido e **restaurado de verdade em PostgreSQL descartável**; confirmar contas, conversas, clientes, pedidos e migrations. Registrá-lo fora do diretório de publicação.
- Guardar imagens e configuração da versão atualmente ativa, `compose.team.yaml`, Caddy e referências de secrets **sem copiar valores para relatórios**.
- Preparar plano de rollback com as imagens atuais. Se forem aplicadas migrations, reversão das imagens antigas exige compatibilidade comprovada; caso contrário, recuperar o banco de um backup íntegro em operação coordenada. Não apagar dados recentes implicitamente.
- Conferir se o Caddy público já encaminha `/webhooks/instagram` (GET/POST) para o gateway correto. O gateway team da candidata encaminha para `team-api`, onde HMAC + token de desafio são validados. Nunca publicar `/internal/*`.
- Confirmar a rede interna `socialmei_team_automation` e, se necessária a ponte existente com n8n, revisar o `compose.team-n8n-bridge.yaml` **sem substituir** o banco ou os volumes do n8n legado.

## Ativação em fases — env privado do team API

Validar previamente no provedor, sem postar e sem responder:

- `SOCIALMEI_INSTAGRAM_RUNTIME_MODE=connect`, `SOCIALMEI_INSTAGRAM_RUNTIME_ENABLED` conforme contrato de `settings.py` e `SOCIALMEI_INSTAGRAM_PROXY_PRIVACY_REVIEWED=true` **somente se a revisão foi feita de fato**.
- OAuth: cliente, segredo, URL HTTPS de callback, versão Graph, escopos, keyring criptográfico, id da chave ativa e token de verificação Meta, todos **privados** e já cadastrados na conta correta.
- `SOCIALMEI_INSTAGRAM_SCOPES` deve incluir `instagram_business_basic`, `instagram_business_manage_messages` e, para feed/publicação, `instagram_business_content_publish`. Verificar a concessão real no token persistido; alterar apenas a variável não concede permissão.
- Deixar inicialmente **desligados** `SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED`, `SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED` e `SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED`. Ligar recepção isoladamente, após conferir assinatura, inscrição correta de webhooks e ausência de outro consumidor concorrente.
- O projeto possui um respondedor Instagram legado no n8n. **Não definir** `SOCIALMEI_INSTAGRAM_DIRECT_OWNER=dashboard` nem ativar envio até comprovar que o workflow anterior deixou de responder à mesma conta/rota. Registrar esse estado antes da mudança. Não desligar workflows indiscriminadamente.
- Só habilitar `SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED=true` após validar a janela de mensagem, consentimento, um único respondedor e conta destinatária de teste. A UI nunca deve enviar automaticamente.
- Só habilitar `SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED=true` após confirmar a foto pública temporária, credenciais, revisão humana e autorização da publicação específica.

**Observação:** o processo de inicialização lê as flags quando o serviço inicia. Atualizar `.env.team` sem uma recriação/reinicialização cuidadosamente planejada **não ativa** o runtime.

## Aceite depois do deploy — conta de teste e autorização

1. Abrir o site real em janela anônima; entrar como usuário autorizado. A conta Instagram deve estar conectada e o perfil profissional certo deve aparecer.
2. **Feed:** abrir *Ver publicações* e conferir imagem, legenda, data, link e paginação com publicações que já existiam, sem criar posts.
3. **Direct recebido:** a conta de teste envia uma mensagem original; conferir **uma** conversa e **uma** mensagem recebida na Caixa. Reentregar o mesmo evento assinado e confirmar que a mensagem não duplica.
4. **Direct enviado:** depois de consentimento específico e exclusividade do respondedor, preparar, revisar e confirmar **uma** resposta para a conta de teste; conferir o recibo no painel e no aplicativo Instagram. Falhas incertas devem permanecer bloqueadas, nunca ser reenviadas automaticamente.
5. **Publicação:** depois de consentimento específico, preparar e confirmar **uma** foto/legenda de teste no perfil previamente identificado; confirmar ID da Meta e aparição no feed, evitando repetições.
6. Confirmar que usuários de outra empresa não veem conversas, mídia ou registros da equipe; testar login, página inicial, clientes, histórico e integridade do banco depois da migração.
7. Guardar somente evidências sanitizadas (sem tokens, payloads privados, telefones ou nomes de clientes). Se falhar qualquer gate, **interromper** os envios e seguir o plano de rollback.

## Estado de entrega

A **versão no GitHub** implementa leitura de feed, uploads e publicação com confirmação, webhook Meta, Direct com recibos duráveis e retomada de rascunhos. Isto **não comprova** que a AWS, n8n, Meta webhook, env, rede ou permissões estejam configurados. O deploy real precisa de operador com acesso à EC2 e à configuração Meta; **nenhuma credencial deve ser enviada em chats nem commitada**.

As PRs são empilhadas: #173 → #174 → #175 → #176, e a candidata integral é o HEAD de #176. O workflow de relatórios recebeu ajuste de rota no gateway para preservar o Bearer técnico em GET, sem expor outras rotas.
