# Teste completo local

Este ambiente reúne a candidata #83 e as funcionalidades da #89, preservando seus commits. Usa o HTML oficial, FastAPI e PostgreSQL reais, exclusivamente locais, com dados fictícios. Não atualiza o site da AWS ou a main.

## Abrir o site

Requisitos: Git, Node 22 ou superior e Docker Desktop aberto em modo Linux (ou Docker Engine local).

Na raiz deste checkout:

```sh
npm ci
npm run preview -- up
```

Abra **https://localhost:8443**. O certificado é da autoridade local deste preview: aceite a exceção somente para esse endereço local, ou instale a autoridade local conforme a política da sua máquina. Nenhuma autoridade é instalada automaticamente. Cadastre uma conta exclusiva de teste com nome/e-mail fictícios e senha de pelo menos 12 caracteres; não reutilize credenciais reais. O cadastro está aberto apenas na porta vinculada a 127.0.0.1. Outra conta cria outro negócio isolado.

Não abra o HTML por arquivo ou use HTTP: a autenticação exige HTTPS e cookie Secure. A primeira inicialização baixa imagens e constrói a API. A porta 8443 precisa estar livre. A API e o banco não publicam portas. Redes internas impedem transporte externo pelos serviços em execução; builds ainda precisam baixar dependências.

```sh
npm run preview -- status
npm run preview -- check
npm run preview -- down
```

O encerramento preserva o banco fictício para continuar depois. Migrations 001–015 são aplicadas automaticamente somente no volume `socialmei-preview_preview_database`, pelo migrador existente. Nenhuma migration foi modificada. Nunca combine este Compose com arquivos team/dev/legados. O launcher rejeita destinos Docker remotos e variáveis de conexão externas. A configuração local gerada em `.preview/.env` é ignorada pelo Git e não deve ser compartilhada. Não remova esse arquivo enquanto conservar o volume: ele contém a senha aleatória do banco local.

## O que testar

| Área                                           | Funcionamento neste ambiente                                                                                                    |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Conta, Clientes, Produtos, Vendas, Financeiro  | API e persistência no PostgreSQL local, com sessão e isolamento por negócio                                                     |
| Perfil e preferências                          | Contratos remotos existentes; importação local continua explícita                                                               |
| Oportunidades                                  | Frio → Morno → Quente, Em análise e revisão; classificação demonstrativa continua com os limites da #89                         |
| Divulgação                                     | Legendas por modelo local sem IA; rascunhos, histórico, agendamento, edição/cancelamento e execução manual simulada persistidos |
| Instagram                                      | Contas fictícias e recibos de simulação; nenhuma publicação real, somente metadados de mídia                                    |
| Caixa                                          | Laboratório de mensagens sintéticas, heurística e RAG lexical; aprovação salva sugestão, sem envio                              |
| Imagens                                        | Upload/prévia local; geração externa indisponível explicitamente                                                                |
| Automações, Assistente e demais módulos locais | Mantêm os limites da aplicação; não passam a executar integrações reais                                                         |

O agendamento não instala cron: use a execução manual de simulação na interface. Não há daemon de publicação, upload privado de mídia, Meta OAuth, gerador de imagens, embeddings ou transporte n8n/WAHA. Chaves locais de laboratório não são credenciais de fornecedores. Rotas `/internal/*` não são expostas pelo site.

## Verificar

Com o preview em execução:

```sh
npx playwright install chromium
npm run test:preview
```

O teste cria somente registros fictícios: dois negócios, auth/CSRF, tentativa de acesso cruzado, cliente persistido, agendamento simulado idempotente e cancelamento, indisponibilidade de imagem, ausência de transporte, recarga e interface 1440/390. Capturas e resultado ficam em `test-results/preview/`. O teste usa o backend real; as suítes anteriores com mocks continuam separadas. As contas sintéticas permanecem no banco local.

## Estado e riscos da integração

Conferido em 21/10/2026: main `4336181`, #83 `e81fd3e` e #89 `928b3c3`. #83 contém 73 commits sobre main; #89 acrescenta três. Não reaplicar essas branches por cherry-pick nem integrar as PRs ancestrais novamente. Esta extensão tem base na #89. A main continua separada. #72 não foi incorporada; #73 permanece aberta, com causa histórica do timeout Financeiro não confirmada.

Os jobs validate/browser das duas PRs anteriores passaram nos respectivos HEADs (runs 39611846107 e 39654011757); isso não certifica uma implantação. A nova PR deve registrar sua própria evidência. Dispositivo físico/leitor de tela e conectores externos não foram homologados. Contratos/credenciais dos geradores da equipe, mídia privada, permissões Meta e adaptação n8n/WAHA dependem de etapa específica. Produção exige autorização própria de alvo, backup e rollback; este roteiro não a concede.
