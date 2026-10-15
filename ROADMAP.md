# Roadmap

Atualizado em 15/10/2026. Prioridades baseadas no código e nas evidências disponíveis; publicação na AWS é uma etapa separada. A [revisão de preparação](FUTURE-READINESS-REVIEW.md), o [mapa de ambientes](docs/ENVIRONMENTS.md) e o [V2 Foundation Plan](docs/V2-FOUNDATION-PLAN.md) são as fontes para a próxima fase.

## Marcos de evolução

São marcos de planejamento, não promessa de release/data.

| Marco                           | Prioridade e gate                                                                                                                   |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| V1 — base estável candidata     | P0: suites finais e aceite de conta nova/saída/reentrada/isolamento sobre `db775dc`; tag/release somente depois dos gates           |
| V1.1 — infraestrutura/ambientes | P1: instalar dependências fixas em ambiente limpo, homologar imagens, conferir n8n→API na AWS e cobertura de backup/restore isolado |
| V1.2 — Funil/Oportunidades      | P1 após aprovação: protótipo isolado → ajustes → critérios/pesos/fontes do responsável → contrato/testes → integração autorizada    |
| V1.3 — WhatsApp                 | P0 condicional: A12/A13, identidade/canal, idempotência, chip/sessão e homologação isolada antes de cliente real                    |
| V1.x — demais features          | P2/P3: requisitos da equipe, multi-MEI produto/serviço/misto e integrações aprovadas; protótipo antes de feature visual grande      |

## Próxima etapa

| Prioridade     | Ação                                                                   | Evidência / conclusão esperada                                                                                                                        |
| -------------- | ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| P0             | Confirmar cadastro novo, saída/reentrada e isolamento da V1            | Cadastro sem convite publicado em `db775dc` segundo recibo do responsável; falta aceite humano final. Não repetir publicação.                         |
| P1             | Homologar o caminho n8n → API Python e conferir runner                 | `/processar` exige `texto`; testar export manual fictício na AWS. PRs #44/#45 seguem separados; preparação de backup não comprova execução.           |
| P1             | Revisar a exploração de Oportunidades                                  | `prototypes/opportunities.html` isolado; aprovar UX e definir regras antes de API/banco/integração.                                                   |
| P1             | Consolidar as sugestões da equipe                                      | O responsável aguarda respostas; transformar ideias em requisitos/aceite antes de criar funcionalidades.                                              |
| P0 condicional | Fechar identidade, autorização e idempotência do atendimento (A12/A13) | O export legado agrupa por nome/canal e não deduplica eventos externos. Exigir IDs estáveis, tenant/canal e reenvio seguro antes de atendimento real. |

## Curto prazo

| Prioridade | Ação                                              | Evidência / conclusão esperada                                                                                                                              |
| ---------- | ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1         | Separar roles de API, migration/backup e consulta | Role team foi observada com superuser; inventariar grants e testar em destino isolado antes de reduzir privilégios.                                         |
| P1         | Conferir backup e recuperação por serviço         | Team, n8n/chave/volume, WAHA e Caddy têm necessidades distintas. Verificar execução automática, retenção, cópia externa e restore isolado de backup real.   |
| P1         | Reconciliar exports com workflows publicados      | Sete exports no Git; inventário remoto anterior de 24 workflows. Registrar versão, credenciais por finalidade e resultado de teste sem ativar canais reais. |
| P1         | Homologar versões fixas de imagens/dependências   | Python passa a ter versões diretas/transitivas fixadas aos testes. Conferir runtime e homologar imagem nova; tags base/n8n/WAHA/Caddy ainda flutuam.        |
| P2         | Tornar o desenvolvimento local mais explícito     | Setup, migrations e modo público dos stores são etapas distintas. Testar o onboarding completo no Windows com o próximo integrante.                         |

## Médio prazo

| Prioridade                  | Ação                                              | Evidência / conclusão esperada                                                                                                                  |
| --------------------------- | ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| P2                          | Reduzir arquivos grandes por responsabilidade     | Ainda há globais e inicialização compartilhada em app/experience/business-views. Extrair ao tocar uma área, com regressão do seu ciclo de vida. |
| P2                          | Consolidar CSS por componente                     | Overrides e valores próprios permanecem; usar tokens e capturas comparativas, sem apagar seletores apenas por repetição.                        |
| P2                          | Avaliar transporte compartilhado nos stores       | Comparar auth, erros, replay e importação antes de extrair; não perder recuperação de operação de Vendas/Financeiro.                            |
| P1 após definição funcional | Conectar Assistente e automações a serviços reais | Hoje são sugestões/regras locais. Definir contexto autorizado, custos, agenda, cancelamento, falhas e confirmação humana antes de integrar.     |

## Futuro

- **P1 após definição — Customer Score / chance de compra:** protótipo de Oportunidades disponível, sem integração. Visão geral própria e contexto futuro na Caixa; aguardar critérios/fontes/pesos e significado do percentual. Sem fórmula, campo ou migration aprovados.
- **P3 — Relatórios compartilhados e canais adicionais:** definir métricas, fontes e requisitos; não usar mensagens demo como histórico confiável.
- **P3 — Automação de deploy e staging:** escolher ambiente isolado e gates; os workflows manuais atuais não comprovam infraestrutura instalada.

## Dívida técnica

- Scripts clássicos/globais e arquivos de UI/CSS extensos.
- Transporte parcialmente repetido e contratos legados em português.
- Modo local, demo, snapshots e dados remotos ainda exigem atenção ao mudar configuração.
- Imagens base flutuantes; lock Python ainda sem hashes de distribuição.
- Grafos experimentais incompletos, atendimento externo sem homologação multiempresa.
- Grants, backup externo e restore operacional ainda com pendências de evidência.

API de gestão autenticada, migrations incrementais 001–011, separação de dados demo, replay/importações e testes HTTP/SQL já existem. Não são itens a recriar. Consulte [arquitetura](ARCHITECTURE.md), [contratos](docs/API-ENDPOINTS.md) e [persistência](docs/PERSISTENCE-MIGRATION.md).

Recuperação por e-mail, onboarding MEI com o professor, administração de GitHub/deploy, Google Sheets e WhatsApp real continuam adiados pelo responsável. Esta revisão não retoma essas integrações nem incorpora o protótipo de planilha de outro PR.

O planejamento histórico permanece no Git e nos relatórios datados; este arquivo contém somente o plano vigente.
