# Ferramentas de IA e acesso do Codex — SocialMEI.IA

Este guia complementa [AGENTS.md](../AGENTS.md), [ambientes](ENVIRONMENTS.md) e [estrutura do projeto](PROJECT-STRUCTURE.md). **Não configura aplicativos externos nem comprova acesso ao servidor.**

## Ponto de entrada para o agente

- As regras do repositório já estão em `AGENTS.md`.
- Os especialistas do Codex já estão em `.codex/agents/`; o roteamento e limites estão em `.codex/config.toml`.
- As Skills versionadas estão em `.agents/skills/`. Reutilize as existentes antes de criar outra.
- Para falhas de proxy 403, host não liberado ou segredo indisponível entre tarefas, consulte `diagnosing-codex-network-access`.
- Para n8n real ou exports de workflows, consulte `n8n-workflow-review`; para interface, `visual-qa`; para entregas, `release-check`.

## Ferramentas opcionais

| Ferramenta | Uso sugerido | Observação |
| --- | --- | --- |
| GitHub | Código, branches, PRs, diffs e CI | Uma PR aprovada não significa deploy. |
| Superpowers | Planejamento, debugging, TDD e revisão | Aplicar somente às tarefas relevantes. |
| Product Design | Pesquisa de UX, auditoria visual, protótipos | Preservar design e contratos existentes. |
| Context7 | Consultar documentação atualizada de bibliotecas | Validar a resposta contra a versão usada no projeto. |
| Figma | Referências editáveis, componentes e design system | Não sincronizar ou sobrescrever telas sem escopo aprovado. |
| PostHog | Analytics, flags e erros de produto | Só após instrumentação e avaliação de privacidade; não enviar dados sensíveis. |
| Trello | Tarefas, responsáveis e documentação operacional | O Git continua sendo a fonte de verdade do código. |

**Importante:** uma ferramenta conectada no ChatGPT não fica automaticamente disponível em cada tarefa do Codex. Confirmar disponibilidade e permissões no contexto correto antes de usar. A instalação de um plugin não altera por si só o código, a AWS ou o n8n.

## Verificação segura de integrações

1. Definir serviço, tarefa, ambiente e se o usuário autorizou somente leitura ou também escrita.
2. Usar o nome exato do domínio aprovado e a associação correta do segredo de rede. Nunca colar tokens em prompts, commits, URLs, logs ou screenshots.
3. Fazer um smoke test mínimo de leitura; registrar resposta e distinguir erro de proxy de erro da API.
4. Só ampliar consultas depois do primeiro sucesso. Paginá-las sem consumir dados privados desnecessários.
5. Antes de qualquer mudança real: escopo, backup se necessário, rollback, aprovação explícita e verificação.
6. Nunca tomar a presença de um workflow no Git como prova de instalação/ativação na AWS.

## Direção de implantação

Manter a configuração dos especialistas/Skills em PRs pequenas, separadas das features do produto. O ideal é uma PR **Draft**, revisão da equipe, CI quando aplicável e merge autorizado. Configurar contas externas e credenciais diretamente no gerenciador de segredos aprovado, fora do Git.
