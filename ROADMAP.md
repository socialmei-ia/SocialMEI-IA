# Roadmap

Atualizado em 19/10/2026. Prioridades baseadas no código e nas evidências disponíveis; publicação na AWS é uma etapa separada. A [revisão de preparação](FUTURE-READINESS-REVIEW.md) e o [mapa de ambientes](docs/ENVIRONMENTS.md) substituem afirmações antigas sobre ausência de API, migrations e isolamento de negócio.

## Próxima etapa

| Prioridade     | Ação                                                                   | Evidência / conclusão esperada                                                                                                                                                                                                       |
| -------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| P1             | Revisar a estabilização frontend e preparar a próxima funcionalidade   | [Estabilização](docs/FRONTEND-STABILIZATION.md) e [mapa de extensão](docs/PROJECT-STRUCTURE.md#como-adicionar-uma-feature); conferir CI do SHA final. A publicação terá alvo/imagens próprios, sem usar o deploy genérico para team. |
| P1             | Consolidar as sugestões da equipe                                      | O responsável aguarda respostas; transformar ideias em requisitos/aceite antes de criar funcionalidades.                                                                                                                             |
| P0 condicional | Fechar identidade, autorização e idempotência do atendimento (A12/A13) | O export legado agrupa por nome/canal e não deduplica eventos externos. Exigir IDs estáveis, tenant/canal e reenvio seguro antes de atendimento real.                                                                                |

## Curto prazo

| Prioridade | Ação                                              | Evidência / conclusão esperada                                                                                                                              |
| ---------- | ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1         | Separar roles de API, migration/backup e consulta | Role team foi observada com superuser; inventariar grants e testar em destino isolado antes de reduzir privilégios.                                         |
| P1         | Conferir backup e recuperação por serviço         | Team, n8n/chave/volume, WAHA e Caddy têm necessidades distintas. Verificar execução automática, retenção, cópia externa e restore isolado de backup real.   |
| P1         | Reconciliar exports com workflows publicados      | Sete exports no Git; inventário remoto anterior de 24 workflows. Registrar versão, credenciais por finalidade e resultado de teste sem ativar canais reais. |
| P1         | Homologar versões fixas de imagens/dependências   | Existem tags flutuantes e requirements sem pins. Conferir versões efetivas e testar a fixação sem atualizar por conveniência.                               |
| P2         | Tornar o desenvolvimento local mais explícito     | Setup, migrations e modo público dos stores são etapas distintas. Testar o onboarding completo no Windows com o próximo integrante.                         |

## Médio prazo

| Prioridade                  | Ação                                              | Evidência / conclusão esperada                                                                                                                  |
| --------------------------- | ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| P2                          | Reduzir arquivos grandes por responsabilidade     | Ainda há globais e inicialização compartilhada em app/experience/business-views. Extrair ao tocar uma área, com regressão do seu ciclo de vida. |
| P2                          | Consolidar CSS por componente                     | Overrides e valores próprios permanecem; usar tokens e capturas comparativas, sem apagar seletores apenas por repetição.                        |
| P2                          | Avaliar transporte compartilhado nos stores       | Comparar auth, erros, replay e importação antes de extrair; não perder recuperação de operação de Vendas/Financeiro.                            |
| P1 após definição funcional | Conectar Assistente e automações a serviços reais | Hoje são sugestões/regras locais. Definir contexto autorizado, custos, agenda, cancelamento, falhas e confirmação humana antes de integrar.     |

## Futuro

- **P3 — Customer Score / chance de compra:** aguardar critérios do responsável. Contexto de Clientes, regra no backend e persistência por negócio apenas se necessária. Não existem fórmula, campos ou pesos aprovados.
- **P3 — Relatórios compartilhados e canais adicionais:** definir métricas, fontes e requisitos; não usar mensagens demo como histórico confiável.
- **P3 — Automação de deploy e staging:** escolher ambiente isolado e gates; os workflows manuais atuais não comprovam infraestrutura instalada.

## Dívida técnica

- Scripts clássicos/globais e arquivos de UI/CSS extensos.
- Transporte parcialmente repetido e contratos legados em português.
- Modo local, demo, snapshots e dados remotos ainda exigem atenção ao mudar configuração.
- Dependências/imagens flutuantes.
- Grafos experimentais incompletos, atendimento externo sem homologação multiempresa.
- Grants, backup externo e restore operacional ainda com pendências de evidência.

API de gestão autenticada, migrations incrementais 001–011, separação de dados demo, replay/importações e testes HTTP/SQL já existem. Não são itens a recriar. Consulte [arquitetura](ARCHITECTURE.md), [contratos](docs/API-ENDPOINTS.md) e [persistência](docs/PERSISTENCE-MIGRATION.md).

Recuperação por e-mail, onboarding MEI com o professor, administração de GitHub/deploy, Google Sheets e WhatsApp real continuam adiados pelo responsável. Esta revisão não retoma essas integrações nem incorpora o protótipo de planilha de outro PR.

O planejamento histórico permanece no Git e nos relatórios datados; este arquivo contém somente o plano vigente.
