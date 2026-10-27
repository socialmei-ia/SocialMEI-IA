# SocialMEI.IA — implantação funcional por fases (Instagram, WhatsApp, contas e equipe)

**Esta candidata contém código de várias PRs. Não significa que todos os recursos estejam implantados ou homologados.**
Nenhum dado real deve ser criado/modificado como teste sem identificação do workspace, backup e operador autorizado.
É proibido publicar código, tokens Meta, credenciais SMTP, chave de cifragem, cookies ou URL privada de webhook em logs/PRs.

## Inventário confirmado no repositório

| Função                       | Código                                                                                       | O que ainda impede a declaração de funcionamento real                                                                           |
| ---------------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Cadastro/login/logout        | FastAPI + PostgreSQL (migrações 010, 024–026); testes de persistência                        | Conferência somente leitura na VPS da versão em execução e novo teste de conta com consentimento do operador                    |
| Redefinição de senha         | Solicitação e confirmação com código único, fila durável e worker `recovery_worker.py --run` | SMTP privado habilitado, worker executado periodicamente e entrega real de e-mail testada                                       |
| Instagram OAuth              | #130: grant plano + encapsulado, callback sem 404 e logs sem segredos                        | Deploy da imagem revisada; novo consentimento do perfil; `/meta/status` autenticado `connected` e `credential_available=true`   |
| Publicação de foto no feed   | #113: criação, processamento, confirmação e recibo idempotente                               | Migrações 027–028, gateway com mídia GET pública por chave temporária e homologação com Meta                                    |
| Stories, Reels, carrossel    | **Não implementados neste corte**                                                            | Definir formatos, limites de vídeo, processamento/hosting seguro, UI e fluxo de containers Meta, testes e homologação separados |
| Direct (receber)             | Webhook com HMAC, deduplicação, vínculo workspace e polling da Caixa                         | Definir fan-out ou cutover dos workflows ativos n8n; provar entrega real da Meta assinada e inscrição dos eventos               |
| Direct (responder)           | Outbox de respostas aprovadas com mitigação de resultado incerto                             | Um único remetente efetivo, permissões Meta, política de janela e teste real end-to-end; enviar continua desligado              |
| WhatsApp — consulta de itens | Endpoint GET autenticado por token SHA-256 por instância/canal, migração 030                 | Canal WAHA real ativo, token guardado no cofre n8n, workflow do colega enviando a consulta e devolvendo resposta real           |
| Equipe — relatórios          | `report_viewer` + troca de workspace e página restrita, migração 031                         | Validar 2 usuários/2 empresas e fazer concessão por owner/admin; **não** compartilhar acesso direto ao PostgreSQL               |
| PDFs de conhecimento         | Banco/consulta privativa por workspace, migração 029, UI de arquivos                         | Ativação controlada + validação de PDFs reais; isso **não** treina nem ativa automaticamente um modelo                          |

## Ordem de homologação e proteção da produção

1. **Preflight somente leitura**: identificar SHA e imagem da API e gateway, Caddy ativo e Caddy público, flags, PostgreSQL e migrations instaladas, saúde HTTPS, n8n/WAHA. Comparar Compose efetivo com todos os overlays privados. Não confiar no HEAD do checkout antigo.
2. **Backup verificável**: salvar dump, imagens e configuração cifrada/privada fora do Git, validar restauração descartável, registrar hashes e plano reversível. Nunca recriar n8n, seu banco, PostgreSQL do SocialMEI, WAHA ou volumes por conveniência.
3. **OAuth primeiro**: com backup revisado, implantar uma imagem que preserve a versão pública e permita apenas `runtime connect`. Manter `PUBLISH=false`, `INGRESS=false`, `SEND=false` e workflows n8n intactos. Reautorizar `@testefacep`, conferir escopos, estado `connected` e ciphertext sem revelar token; 401 anônimo continua correto.
4. **Cadastro/recuperação/equipe**: confirmar conta já cadastrada continua entrando e retém perfil/negócio; conferir migrações 024–026 e SMTP somente por estado, nunca por valores. Habilitar e supervisionar o worker de recuperação numa janela aprovada. Validar report_viewer restrito a dados agregados, owner/admin revoga sem deixar sessão antiga ativa.
5. **Foto no feed**: somente após OAuth real, aplicar 027/028 sob backup e validar rota anônima de mídia efêmera e resultado de publicação com **uma** foto escolhida pelo operador. Timeout incerto não pode gerar novo POST automático.
6. **WhatsApp**: aplicar 030 somente com a API protegida e canal correto; credencial uma vez para n8n, por canal/workspace. Reutilizar o fluxo atual do responsável pelo menu sem adicionar outro sender. Testar duas empresas, itens com estoque positivo e itens sem inventário confirmado. Não permitir `workspace_id` arbitrário na URL.
7. **Direct**: preservar fluxo n8n ativo até decisão documentada de fan-out/cutover, confirmar corpo bruto e HMAC da Meta, deduplicação e entrada automática na Caixa. Só depois habilitar resposta manual via outbox; não executar dupla resposta.
8. **Stories/Reels e PDFs**: implementar e homologar formatos de mídia e pipeline de vídeo separadamente; migração 029 e papel 031 requerem verificação de compatibilidade ao serem ativados, não migrar simplesmente todo o banco de uma vez.

## Critérios de aceitação mensuráveis

- Cadastro de teste com autorização, logout, login no mesmo e-mail, perfil e workspace preservados; redefinição por e-mail entregue e código usado uma única vez.
- `@testefacep` confirmado pelo provedor; nenhum 404 na volta; estado `connected` somente do backend e token cifrado disponível.
- Foto do feed publicada com comprovante Meta; Reels/Stories só entram como concluídos após vídeo/foto real e comprovante próprio.
- Mensagem externa real entra na Caixa do workspace correto, sem duplicação; uma resposta humana aprovada sai uma única vez e é recebida.
- Menu WAHA consulta item com permissão técnica restrita, retorno coerente de quantidade e preço, nenhuma fuga de dados entre workspaces.
- Usuário `report_viewer` vê somente relatórios autorizados; não acessa Direct, catálogo privado, PDFs, finanças detalhadas, segredos nem mutações.
- CI no commit final verde; deploy e rollback documentados; todos os serviços não envolvidos preservados.

## Limites dos preparadores de deploy

`tools/instagram-release-prepare.py` foi concebido para a candidata 001–028, por isso **não pode ser presumido compatível com a árvore 001–031**. Não o executar em produção com este HEAD sem adaptar, revisar e retestar suas invariantes. A PR conjunta agrupa código para QA, não autoriza ativação indiscriminada de 029/030/031.

**Acessibilidade da equipe:** use o acesso do aplicativo por usuário, workspace e permissão; não publique o PostgreSQL (porta 5432) ou pgAdmin na internet nem compartilhe a senha de administrador.
