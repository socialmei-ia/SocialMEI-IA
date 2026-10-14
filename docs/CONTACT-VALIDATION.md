# Contatos e conversas locais

## Comportamento

- Nova conversa apresenta **Telefone · Brasil (+55)** para WhatsApp e **Usuário do Instagram** para Instagram. Cada canal mantém seu próprio rascunho enquanto o modal está aberto.
- Telefone brasileiro aceita DDD existente, celular com nove dígitos iniciado em 9 ou fixo com oito dígitos iniciado em 2–5. Telefones fixos comerciais com dígitos repetidos, como `(11) 3333-3333`, são aceitos.
- Outro país exige `+` e código internacional; a conferência é de sintaxe (8–15 dígitos), sem validar o plano de numeração daquele país.
- A máscara aparece durante a digitação. Letras e inserções que ultrapassem 10 dígitos para fixo ou 11 para celular no Brasil (mais dois quando se informa +55) ou 15 em outro país são bloqueadas. Colagens incompatíveis são rejeitadas integralmente, sem truncar para produzir um número aparentemente válido.
- Instagram aceita usuário ou `@usuário`, até 30 caracteres, letras ASCII, números, ponto e sublinhado. Links, espaços e telefone sem `@` são rejeitados. Um identificador explicitamente numérico com `@` é permitido.
- Cadastro pergunta **“Este número está correto?”** antes de continuar. Editar ou Escape retorna ao campo, preservando os demais dados. Esta confirmação não envia SMS nem comprova existência ou titularidade.
- Em uma conversa local, o menu **… → Excluir conversa local…** abre a confirmação. Excluir remove o histórico local, favoritos, eventos e rascunhos; mantém o cliente, vendas e financeiro.
- Conversas de demonstração removidas não reaparecem ao recarregar. Conversas que contêm mensagens integradas não oferecem exclusão: não há contrato de exclusão remota homologado.
- Erro ao persistir a exclusão mantém a conversa. A exclusão não altera backups já exportados.

## Implementação e limites

`frontend/scripts/contact-validation.js` centraliza as regras de entrada e a confirmação acessível com diálogo nativo. Os campos novos e existentes de telefone/Instagram usam a mesma validação nos formulários. A transição respeita os tokens de motion e `prefers-reduced-motion`.

`python-service/contact_validation.py` aplica as mesmas regras na API. Cadastro/perfil de conta e configurações do negócio validam o telefone; criação/alteração de clientes validam contatos enviados, antes de escrever no banco. Campos vazios continuam compatíveis com o contrato opcional da API. O frontend exige telefone no cadastro.

Valores legados permanecem legíveis. Uma alteração que não envia o contato não é bloqueada por um valor antigo inválido. Ao reenviar um contato inválido, é necessário corrigi-lo. Nenhuma migration ou correção automática de registros foi adicionada.

**Publicação:** requer atualizar frontend e API. Publicar somente o gateway não instala as validações do backend. PostgreSQL, n8n e WAHA não precisam ser atualizados.

## Verificação

- `npm test`: contratos e regras de contato.
- `CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:browser`: cadastro local/API simulada, confirmação, troca de canal, formatos inválidos, exclusão/cancelamento/persistência, preservação do cliente e falha de armazenamento. Desktop/mobile, claro/escuro e reduced motion.
- `python -m unittest discover -s python-service -p 'test_*.py'` com `TEST_DATABASE_URL` apontando para banco **isolado de testes**: API, autenticação, contratos, rejeição de contatos e leitura de registros legados.

Os testes de banco limpam dados no destino de testes. Nunca aponte `TEST_DATABASE_URL` para produção.
