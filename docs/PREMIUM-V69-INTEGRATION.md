# Premium v6.9 integrada para teste

Branch `feat/premium-v69-test-20261120`, empilhada na PR #235. Produção permanece na API `17cfd1956416c2d4c8431fec11800f73254bde12` e no gateway premium personalizado. Nenhum deploy visual realizado.

Origem: `SocialMEI-IA-Premium-v6.9-Detalhes-que-Importam (1).zip`, SHA-256 `be40d188538781d4169f043b522516a0c6bf4c73fcc95c6450b20e875bb45872`. `LEIA-ME.md` e `RELATORIO-v6.9.md` conferidos; integração por comparação dos 166 arquivos do pacote.

## Compatibilidade preservada

- `config.js`, `auth-store.js` e `v22-inbox-customer.js` continuam na versão funcional anterior. Configuração de demonstração e CRM anterior do ZIP não foram importados.
- Preservados controle de sessões, verificação de identidade, troca de workspace, polling com recuperação, agendamento público, horários e catálogo inicial.
- Adaptados apenas os seletores necessários aos novos cabeçalhos: status real de recebimento, identificação do canal, controles de largura e textos de entrada.
- Complementos Premium carregam depois da autenticação. O complemento visual não executa recarga concorrente no logout/troca nem salva rascunho remoto no navegador. O backend existente controla o rascunho, envio e recibo.
- No modo remoto, o controle de largura existente continua responsável pelas preferências de usuário/workspace; divisórias concorrentes do pacote são suprimidas. No modo local estático, o comportamento original do pacote permanece.
- Corrigidos sobreposição dos botões CRM no celular, altura mínima do histórico, nome acessível da ação Agenda e abertura do formulário de oportunidades recolhido.
- O controller de oportunidades mantém carregamento, falhas, recuperação e escrita remota atuais; o visual v6.9 permanece. Os novos módulos opcionais com adaptadores incompletos não substituem os módulos funcionais existentes.

## Teste utilizável neste computador

Abra **https://127.0.0.1:8443/frontend/entrada.html#/login**. É um ambiente local isolado, identificado por `/__preview`; o certificado é local. Containers `socialmei-v69-preview-*`, banco e volumes exclusivos, portas somente em loopback, sem credenciais Meta/WAHA/SMTP nem envio externo.

Conta fictícia e senha exclusiva estão no arquivo privado `%LOCALAPPDATA%\SocialMEI-Privado\premium-v69-local.json`; não copiar seu conteúdo para Git, relatórios ou chat. Uma conta local possui Bella Store (workspace 7) e Brilho&Limpeza Service (workspace 8). Esses IDs são apenas locais; não representam a produção.

| Dados fictícios persistidos por empresa | Brilho | Bella |
| --------------------------------------- | -----: | ----: |
| Clientes                                |      4 |     4 |
| Serviços / produtos                     |      3 |     3 |
| Recursos                                |      2 |     0 |
| Reservas                                |      4 |     0 |
| Vendas                                  |      2 |     2 |
| Financeiro                              |      3 |     3 |
| Oportunidades                           |      2 |     2 |
| Lembretes                               |      2 |     2 |

Históricos de reservas em 17/18 de novembro; reservas pendentes em 23/24 de novembro de 2026. Data-base 19/11 preservada. Aplicação/repetição local pelo provisionador via APIs manteve IDs e operações. Inventário completo privado: `premium-v69-local-inventory.json`, na mesma pasta privada. Não foram criadas mensagens como se viessem de provedores.

Fluxo de revisão: entrar → selecionar Brilho → conferir perfil, serviços, agenda e relatórios → selecionar Bella → conferir produtos, estoque, vendas e financeiro → voltar ao Brilho → recarregar e confirmar isolamento. WhatsApp/Instagram desse ambiente são laboratório; não representam os canais reais.

## Publicação posterior

O incremento visual precisa de aprovação própria e de preflight no estado então instalado. Não copiar a pasta inteira. Conferir hashes dos arquivos previstos, manter o `config.js` efetivo, os mounts/Caddy e a imagem premium personalizada, salvar backup dos arquivos/configurações e rollback imutável. Não incluir migrations, carga de demonstração, troca de canais, n8n ou workers nessa publicação.

O pacote de revisão incremental e o inventário de hashes ficam em `test-results/`. Não são um instalador e não devem ser aplicados sem a comparação com o runtime e plano aprovado.

## Validação concluída

PR #236, fonte `889aec8`: 454 testes JavaScript aprovados e 2 ignorados; formatação aprovada. Regressão completa de navegador aprovada: 286 estados de layout, 5 fluxos de entrada, CRM233, teclado, temas, agenda, agendamento público, rascunhos, falhas/recuperação, respostas sintéticas dos canais, catálogo, vendas, financeiro e relatórios. O fluxo real local API/PostgreSQL comprovou duas contas isoladas, dois negócios no mesmo login, dados persistidos, duas abas, recarga e novo login. O provisionador passou em dry-run, resposta perdida e repetição sem duplicação no banco descartável. Outros 50 testes PostgreSQL de canais/agenda e 12 de concessão/rollback aprovados. Não representam homologação com os provedores reais.

Evidência verificável, hashes de 45 arquivos candidatos e 11 contratos preservados byte a byte: [20261120-premium-v69-integration.json](evidence/20261120-premium-v69-integration.json). A CI da PR #235 em `b02c7f2` passou; a CI visual própria da PR #236 acompanha a validação local.

## Dependências ainda reais

| Prioridade | Dependência                                            | Estado                                                                                                                    |
| ---------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| P0         | Conta do projeto e acesso aos dois negócios produtivos | Conta ausente; cadastro normal e concessão aditiva preparados, aguardando aprovação específica                            |
| P0         | Dados demonstrativos produtivos                        | Provisionador pronto e testado; dry-run depende da identidade legitimamente associada; aplicação exige aprovação separada |
| P0         | WhatsApp do Brilho                                     | Binding histórico no workspace 1; transferência com filas, backup e rollback exige aprovação                              |
| P0         | Dois Instagram reais                                   | OAuth por empresa e exclusividade com n8n/worker ainda precisam de homologação; nenhum novo sender habilitado             |
| P1         | Acesso individual do professor                         | Conceder por equipe/convite aprovado; não compartilhar proprietário nem acesso PostgreSQL                                 |
| P1         | Publicação v6.9, backup externo e operação             | Versão apenas local; infraestrutura produtiva preservada                                                                  |
| P2         | Automação adicional e escala                           | Após homologar as jornadas principais                                                                                     |
