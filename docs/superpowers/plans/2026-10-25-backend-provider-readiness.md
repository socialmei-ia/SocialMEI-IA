# Backend preparado para o frontend futuro

Base: #110 b83e998 + #102 f2a8534, reunidas sem alterar os visuais. Desenvolvimento autorizado; nenhuma operação de produção ou provedor real autorizada nesta rodada.

## Decisões de implementação

- Reutilizar FastAPI, sessões, PostgreSQL e migrations001–023 existentes; sem cadastro, Caixa ou catálogo paralelos.
- Usar Instagram Login oficial e o adaptador/vault/OAuth/ingress/outbox existentes. Implementar transporte HTTP limitado e configuração de servidor explicitamente desligada por padrão.
- Callback OAuth GET autenticado, com state de uso único já persistido e sem code/state em redirects ou logs ASGI. Callback e origem vêm exclusivamente da configuração do servidor.
- Expor alias de webhook assinado reutilizando a persistência existente. Flags não conectam contas automaticamente nem ativam envio/publicação.
- Permitir preparar respostas na outbox; despacho exige configuração separada e aprovação humana existente. Nenhum envio será executado nesta rodada.
- WAHA preserva contrato fechado da #110. Registrar preparo/limitações para configuração futura, sem número, QR, sessão real ou envio.
- Disponibilizar contrato de capacidades para o novo frontend sem segredos e documentar os endpoints de conta, catálogo e gestão já existentes.

## Validação

1. Testes novos antes da implementação para URL/host/método/TLS, redirects, tamanho, timeout, logs e defaults.
2. Testes de configuração/callback: autenticação, CSRF, query privada, state/replay, isolamento e falhas sem credenciais em respostas.
3. PostgreSQL descartável com dois negócios, cadastro8/login, catálogo e conexão/recebimento sintéticos; nenhuma chamada externa.
4. Regressões backend/frontend, migrations e CI completo no HEAD final. PR Draft única sobre a cadeia atual, com #102 preservada.

## Portões externos

Aplicativo Meta, conta profissional, callback/domínio aprovado, permissões e segredos de servidor ainda dependem de configuração/homologação. Sem deploy, migrations reais, Meta/n8n/WAHA/AWS ou mensagens/publicações. Preparação técnica não é comprovação de conexão em produção. Renovação automática, publicação de mídia e armazenamento remoto de arquivos ficam explicitamente fora da primeira unidade se não houver contrato seguro disponível.

## Esclarecimento do proprietário durante a implementação

O colega já opera atendimento com IA e publicação de Reels/Stories no n8n. A integração deve reutilizar esses workflows; a instância/versões e contratos atuais ainda estão sendo confirmados. O runtime direto Meta é uma opção de backend fechada, não substitui nem ativa esses workflows. Evitar duas automações respondendo ao mesmo cliente. A ponte n8n não pode inventar endpoint, conta autorizada, callback ou confirmação; preparar handoff dos contratos existentes e preservar o núcleo de CRM enquanto a equipe confirma esses dados.
