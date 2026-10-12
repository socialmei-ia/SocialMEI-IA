# Revisão do projeto — 12/10/2026

Base: `94feb5fa816157b9727a24cdd4e206f302ecbd11`, após o guia WAHA da equipe. Revisão do código, configuração e testes do frontend, stores locais/remotos, API de gestão, migrations/importações, integração de leitura, Compose/gateway, ferramentas de operação, backups e guias. Não é uma auditoria exaustiva de segurança nem uma inspeção direta do servidor em produção.

## Problemas confirmados e correções

| Área                       | Problema                                                                             | Correção                                                                                                                    |
| -------------------------- | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| Relatórios                 | Gráfico de vendas usava rótulos de entrada/saída financeira.                         | Uma série de faturamento, com tooltip e descrição acessível próprios.                                                       |
| Relatórios                 | Rankings juntavam clientes/itens distintos com nomes iguais.                         | Agrupamento por IDs no modo remoto; quantidade agregada por grupo.                                                          |
| Atendimento nos relatórios | Comparações por nome ignoravam vínculos por ID e podiam atribuir vendas a homônimos. | Vínculo remoto explícito pelo cliente da conversa; nomes continuam apenas no modo local.                                    |
| SVG antigo                 | Barras eram concatenadas depois do fechamento do SVG.                                | Elementos permanecem dentro do SVG; a função não é o gráfico ativo da tela.                                                 |
| Fonte dos dados            | Rodapés e resumo copiado diziam “local” em ambientes remotos.                        | Textos distinguem armazenamento local, compartilhado ou misto, conforme cada módulo.                                        |
| Cadastros novos            | Criação remota não preenchia a data original de cadastro.                            | Novas criações recebem data estável, preservada na repetição após resposta perdida. Importações não inventam datas antigas. |
| Mensagens pausadas         | URL nula ainda gerava busca e polling contra um endereço inválido.                   | Estado “não configurada”, sem requisições/polling; CRM continua disponível.                                                 |
| Windows                    | Docker/Git eram executados por shell desnecessário, gerando aviso de depreciação.    | Executáveis chamados diretamente, com argumentos separados.                                                                 |
| Clone no Windows           | Dois templates de PR diferiam apenas pela caixa das letras.                          | Um template consolidado, preservando os checklists; verificação de colisões no repositório.                                 |
| GitHub Actions             | Backticks no resumo de deploy eram interpretados como comandos do shell.             | Texto literal e SHA formatado, sem executar os valores. O procedimento de deploy permanece igual.                           |
| Documentação               | Guias descreviam a fase anterior, sem API/migrations/servidor da equipe.             | Orientações atualizadas; revisões e planejamento antigos identificados como históricos.                                     |

## Verificação

Os testes novos cobrem integração de mensagens desativada, identidade/data de criação recuperável e nomes de arquivos compatíveis com Windows. A regressão de navegador inclui relatórios com fontes remotas, nomes repetidos, cliente renomeado, datas de cadastro no fuso do app, períodos, totais pagos, privacidade e estrutura SVG, sem acessar serviços externos.

A validação local executa Node, contratos Python disponíveis, ferramentas de backup/administração, sintaxe e formatação. Testes que exigem PostgreSQL, Docker ou Chromium são executados no CI. O resultado final da revisão deve ser conferido no PR correspondente; testes de navegador usam API simulada, enquanto os contratos Python do CI usam PostgreSQL real. Nenhum teste grava no banco da AWS.

## Pendências mantidas

- Decisão de contas/acesso público com o dono; a proteção atual continua necessária.
- Chip dedicado e conexão da sessão WAHA. Nenhum fluxo de envio foi ativado.
- Identidade estável e deduplicação do atendimento: o webhook legado ainda agrupa por nome/canal. Isso exige contrato/migração próprios, além destas correções de relatórios.
- Regras reais do n8n e escrita por automações; a credencial instalada é somente de leitura.
- Cópias externas recorrentes e recuperação dos backups reais. A cópia inicial no notebook não é sincronização automática diária.
- Versões flutuantes de imagens e dependências Python, dados demonstrativos de atendimento e acoplamento dos scripts. Mudanças maiores devem ser tratadas separadamente.

## Aplicação e rollback

Merge publica o código/guia na `main`; não atualiza o servidor da equipe automaticamente. Não há alteração de schema, credenciais, volumes, estoque ou regras de pagamento nesta revisão. No servidor, faça backup e atualize o worktree conforme o procedimento da equipe; reconstrua somente `team-gateway` para aplicar o frontend. Preserve os arquivos privados. Para rollback, volte ao commit anterior e reconstrua esse gateway; não restaure o banco para desfazer estas correções de interface.
