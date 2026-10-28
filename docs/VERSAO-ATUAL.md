# SocialMEI.IA — versão e entregas atuais

Atualização de 28/10/2026. Este documento distingue a candidata de desenvolvimento, os relatos de implantação e a homologação com serviços externos. Não é uma nova inspeção da AWS.

## Qual versão acompanhar

| Referência                                                                      | Finalidade                                                                                 | Situação                                                                                                    |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| [PR #136 — Frontend V25](https://github.com/socialmei-ia/SocialMEI-IA/pull/136) | Entrada V25, integração de contas e consolidação das melhorias funcionais.                 | Draft; HEAD 849ead4; CI aprovado.                                                                           |
| [PR #137 — WhatsApp](https://github.com/socialmei-ia/SocialMEI-IA/pull/137)     | Registry privado, catálogo/menu persistente, atendimento humano e tentativas idempotentes. | Draft sobre a PR #136; HEAD e8e0dc8; CI aprovado.                                                           |
| `main`                                                                          | Base publicada no repositório.                                                             | As candidatas acima ainda não foram mescladas. Atualizar esta documentação não incorpora seu código à main. |
| AWS                                                                             | Piloto do produto, com imagens e configurações próprias.                                   | Imagens efetivas precisam ser conferidas antes de novo corte. Um checkout ou CI não comprova o runtime.     |

A versão visual V25 usa a nova entrada enviada pelo proprietário. O app/Oportunidades/Divulgação do pacote preserva as telas aprovadas já integradas; não foi reconstruído em outro framework.

## Entregas recentes

### Interface e contas

- Nova landing e fluxos de entrada V25, com temas, responsividade e animações preservados.
- Cadastro transacional: usuário, credencial Argon2, negócio próprio, papel owner e sessão.
- Login/logout, cookies protegidos, Origin/CSRF, revogação de sessões e isolamento entre negócios.
- Senha de 8 a 128 caracteres, sem obrigar apenas números; senhas extremamente comuns são recusadas.
- Recuperação por código temporário de uso único e fila persistente. SMTP e worker precisam de configuração e entrega real comprovada.

### Instagram

- Corrigidos retorno visual OAuth, formato das permissões, saída HTTPS da API e consulta de status de publicação.
- O proprietário confirmou a conexão após a correção 93163f9 e nova autorização no site. Isso é evidência relatada, não uma inspeção atual do servidor.
- Upload de imagem, legenda, processamento e confirmação de publicação estão implementados, com proteção contra duplicação e estado incerto.
- Webhook com assinatura, vínculo por conta/negócio, persistência e atualização periódica da Caixa estão implementados.
- **Direct recebido e foto publicada em conta real ainda não foram comprovados.** Ingresso, envio e publicação permaneciam desativados no último procedimento conhecido.
- Reels, Stories, carrosséis e gestão de perfil/exclusão de posts não estão concluídos. Não confundir os seletores visuais do produto com capacidades reais já ativadas.

### Banco, documentos e relatórios

- Clientes, produtos/serviços, estoque, vendas e financeiro têm persistência por negócio.
- PDFs privados: armazenamento no PostgreSQL, extração isolada, busca com documento/página, download, substituição, reprocessamento e exclusão.
- OCR e geração de respostas por LLM não estão implementados; a busca retorna fontes, não uma resposta inventada.
- Relatórios usam agregados e CSV, com papel de consulta restrito e concessão/revogação por responsável.
- As migrations 001–031 integram a candidata funcional anterior; a 032 acrescenta a preparação do bot e **não foi aplicada na AWS nesta entrega**.

### WhatsApp

- O número de teste está disponível segundo o proprietário; pareamento e sessão WAHA ainda precisam de conferência.
- Registro privado de canais: arquivo restrito, HMAC, instância/sessão/conta e revalidação no banco.
- Menu com produtos, preço/disponibilidade, serviços, orçamento e atendente; consultas usam o catálogo ativo do negócio.
- Estado persistente da conversa; pedido de humano pausa o bot até retomada explícita.
- Credencial específica, separada da consulta de catálogo; reserva única e recibo impedem que o mesmo comando autorize repetição automática.
- Subworkflow n8n inativo, sem credenciais e com trava adicional. Não foi importado ou executado na instância real.
- Texto numerado é o padrão. Renderer de lista está preparado para suporte explicitamente verificado; botões/listas no aparelho ainda dependem da engine e de payload homologado.

## Testes e limites da evidência

Candidata [`e8e0dc8`](https://github.com/socialmei-ia/SocialMEI-IA/commit/e8e0dc8fb677a62d6b1c0b8394882aea6a7da4eb), na PR #137:

| Verificação                           | Resultado                                                                                                                  |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Backend com PostgreSQL 16 descartável | 513 testes aprovados.                                                                                                      |
| Frontend/contratos Node               | 341 testes aprovados.                                                                                                      |
| Operação                              | 155 casos; 14 opcionais não executados na chamada geral.                                                                   |
| Migrations 001–032 e restauração      | 864 verificações aprovadas, com dados sintéticos de dois negócios.                                                         |
| Navegador                             | Entrada V25, publicador com provedor sintético, 286 estados de layout e 5 fluxos de entrada aprovados.                     |
| CI                                    | [Validação/backend, navegador e preview aprovados](https://github.com/socialmei-ia/SocialMEI-IA/actions/runs/40720042774). |

Essas suítes não usaram banco, credenciais, documentos ou mensagens de clientes reais. CI e capturas locais não comprovam integração real com Meta, WAHA ou SMTP.

## Próximos aceites

1. Conferir imagens, overlays, ledger, flags e backups efetivos da AWS.
2. Preservar os workflows n8n existentes e definir um único responsável por cada envio.
3. Comprovar Direct entrando na Caixa e uma imagem/legenda previamente autorizadas publicadas no Instagram correto.
4. Parear o número de teste e homologar o menu WhatsApp, catálogo e encaminhamento humano.
5. Confirmar recuperação por e-mail e acesso de dois usuários aos seus dados persistidos.
6. Habilitar e homologar PDFs e relatórios no ambiente autorizado.

## Fontes de implementação

Os links abaixo apontam para o código exato da candidata, mesmo enquanto ela não está na main:

- [Integração visual V25](https://github.com/socialmei-ia/SocialMEI-IA/blob/e8e0dc8fb677a62d6b1c0b8394882aea6a7da4eb/docs/FRONTEND-V25-INTEGRATION.md)
- [Estado funcional](https://github.com/socialmei-ia/SocialMEI-IA/blob/e8e0dc8fb677a62d6b1c0b8394882aea6a7da4eb/docs/FUNCTIONAL-CONTINUATION-STATUS.md)
- [WhatsApp: contratos e operação](https://github.com/socialmei-ia/SocialMEI-IA/blob/e8e0dc8fb677a62d6b1c0b8394882aea6a7da4eb/docs/WHATSAPP-BOT-OPERATIONS.md)
- [PDFs privados](https://github.com/socialmei-ia/SocialMEI-IA/blob/e8e0dc8fb677a62d6b1c0b8394882aea6a7da4eb/docs/PRIVATE-PDF-KNOWLEDGE.md)
- [Relatórios e permissões](https://github.com/socialmei-ia/SocialMEI-IA/blob/e8e0dc8fb677a62d6b1c0b8394882aea6a7da4eb/docs/REPORTING-ACCEPTANCE.md)
- [Recuperação de conta](https://github.com/socialmei-ia/SocialMEI-IA/blob/e8e0dc8fb677a62d6b1c0b8394882aea6a7da4eb/docs/ACCOUNT-RECOVERY.md)

## Capturas da apresentação

As imagens em [showcase-v25](assets/showcase-v25/source.json) foram capturadas diretamente da interface local da candidata e8e0dc8 em 28/10/2026, com dados fictícios e solicitações externas bloqueadas. Não são montagens da interface nem capturas do ambiente de produção. O banner é um asset editorial exclusivo do README; imagens de compartilhamento usadas pelo site foram preservadas.
