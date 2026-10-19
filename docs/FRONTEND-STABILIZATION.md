# Estabilização do frontend — 19/10/2026

Baseline de `main`: `4336181fc9156d386cc46158ced708b6efda7be5`, com #67/#68 integradas. Branch `fix/frontend-stabilization`, criada dessa base limpa. Escopo: frontend, testes e documentação; sem acesso ou alterações em produção. Próxima funcionalidade ainda não especificada.

## Correções e preservação

- Reproduzido: sete colunas financeiras tinham cerca de 25 px em 320 px e ~32 px em 390 px. A área interativa agora tem mínimo de 44 px, independente da barra visual; rolagem limitada ao gráfico, eixo fixo e aviso de mais períodos quando necessário. Sem sobreposição de alvos ou overflow da página.
- Tooltip único fora da área rolável evita cortes; seleção por toque/clique, mouse, Tab, setas, Home/End, Escape e toque externo. Leitura textual e estado selecionado perceptíveis. Resize reposiciona o tooltip; listeners/ResizeObserver são descartados na substituição ou mudança de escopo.
- Relatórios: título/intervalos mais compactos, origem e perfil no recolhível junto dos períodos, opções completas acessíveis por teclado. Fonte indisponível continua se abrindo automaticamente. Datas completas mantidas.
- Botão “Explorar valores” leva ao primeiro ponto e mostra valores pelo controlador existente; teclado/toque/tooltip e leitura acessível preservados.
- Sem mudança de fórmulas, agrupamentos, fonte, snapshots, comparações, CSV, PDF/impressão ou armazenamento. Animações geométricas existentes e redução de movimento preservadas.
- Demais módulos: regressões existentes de onboarding, personalização, CRUD, Caixa/rascunhos, Oportunidades, Divulgação, Assistente, automações, ajuda e temas. Não foram reimplementados achados já corrigidos. A composição da landing e a ausência de integração externa não são novos defeitos.

## PRs antigas — consulta GitHub na baseline

Base histórica é o SHA registrado pela PR; a comparação usa `main` atual. Estado limpo/mergeável é técnico, não aprovação. Nenhuma PR foi modificada, fechada, integrada ou copiada nesta rodada.

| PR  | Estado                  | Base histórica → HEAD      | Sobreposição / recomendação                                                                                              |
| --- | ----------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| #43 | Aberta, conflito        | main `92d4c20` → `5a6f740` | README/tour e capturas antigas. Atualizar isoladamente apenas se ainda desejado.                                         |
| #44 | Aberta, mergeável       | main `92d4c20` → `c266dfe` | Helper do runner não integrado. Manter separada até inventário e homologação operacional.                                |
| #45 | Aberta, mergeável       | main `92d4c20` → `fef6cc5` | API/README experimental de planilha. Recomendar arquivamento; retomada exige contrato próprio multiempresa/idempotência. |
| #48 | Aberta, conflito        | main `db775dc` → `755c8df` | CI/docs/workflows e fundação experimental. Não integrar em bloco; extrair proposta mínima atualizada se priorizada.      |
| #54 | Draft, conflito         | main `82dd52b` → `9dd185e` | Frontend/CI substituídos pela evolução nativa. Recomendar arquivamento preservando evidências.                           |
| #55 | Draft, limpa contra #54 | #54 `9dd185e` → `37655e5`  | Motores/testes reaproveitados; arquivar como referência histórica. Não significa limpa contra main.                      |
| #56 | Draft, limpa contra #55 | #55 `37655e5` → `e327b7e`  | Hub separado substituído pela apresentação nativa. Arquivar preservando roteiro/evidências.                              |

Reaproveitamento documentado em [NATIVE-INTEGRATION.md](NATIVE-INTEGRATION.md). Arquivar é recomendação ao responsável, não ação executada.

## Riscos e autorizações separadas

Revisão estática focada; não é auditoria de segurança completa nem nova coleta da VPS.

| Tema                    | Evidência atual ou histórica                                                                                                                                                            | Impacto / próximo gate                                                                                                                                                             |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sessão/tenant/CSRF      | `account_auth.py` valida sessão/associação, Origin e CSRF; cookie Secure/HttpOnly/Lax. `settings.py` falha fechado em flag inválida; `shared_data.py:ensure_workspace` usa o principal. | Nenhum bug novo comprovado nessa leitura. Basic é barreira adicional; modo sem auth não oferece isolamento individual. Preservar contratos e homologar contas reais separadamente. |
| Persistência local      | `auth-store.js` arquiva/restaura escopo; `business-profile.js` valida usuário/workspace.                                                                                                | LocalStorage não é cofre nem sincronização entre dispositivos. Retenção/dispositivo compartilhado exige política própria.                                                          |
| Falhas remotas          | Stores recusam escrita quando a fonte falha; clientes validam modo/estado e conflitos.                                                                                                  | Sem fallback local silencioso. Preservar versões e recuperação de operações; transporte duplicado é dívida, não motivo para reescrever.                                            |
| Atendimento externo     | `opportunity-data.js` bloqueia fonte remota sem contrato seguro; `config.js` mantém `n8nMessagesUrl:null`. Limites em [ARCHITECTURE](../ARCHITECTURE.md#caixa-unificada-e-n8n).         | P0 condicional: identidade por nome/canal e deduplicação incompleta no legado. Resolver autorização/IDs/idempotência antes de canal real multiempresa. Não ativar endpoint legado. |
| Intenção comercial      | `priority-engine.js` conserva janela de 24h experimental; revisões/alertas locais em [CLIENT-ANALYSIS-V2-NATIVE](CLIENT-ANALYSIS-V2-NATIVE.md).                                         | Recomendação supervisionada, sem probabilidade validada ou envio/resolução remotos.                                                                                                |
| Privilégios PostgreSQL  | [REMEDIATION-STATUS](REMEDIATION-STATUS.md) registra observação histórica de superuser/BYPASSRLS; grants atuais não reconfirmados.                                                      | Separação de roles exige inventário, teste isolado e autorização operacional. Frontend não homologa privilégios do banco.                                                          |
| Backup/restore          | [Arquitetura](../ARCHITECTURE.md#infraestrutura) e remediação documentam limites de cópia externa/cobertura por serviço.                                                                | Integridade do arquivo não comprova restore. Validar restauração isolada, retenção e cópia externa em rodada própria autorizada.                                                   |
| Versões/runtime/staging | Há tags flutuantes em `compose.yaml`; [ENVIRONMENTS](ENVIRONMENTS.md) mantém inventários datados e staging sem homologação atual.                                                       | Não presumir versão instalada ou staging independente. Pinagem/implantação exigem testes e autorização; nenhum runtime alterado.                                                   |
| Proteção de main        | Consulta somente leitura retornou GitHub 403 “Resource not accessible by integration”.                                                                                                  | Proteções não confirmadas; não inferir ausência nem alterar administração. Responsável pode verificar separadamente.                                                               |
| Deploy                  | Workflow genérico usa Compose completo; [ENVIRONMENTS](ENVIRONMENTS.md#publicação-e-rollback) distingue o gateway team.                                                                 | Não acionar workflow genérico. Nenhum deploy, n8n, WAHA, credencial, volume ou configuração efetiva alterado.                                                                      |

## Verificação e continuidade

Teste novo integrado a `npm run test:browser`: alvos >=44 px, ausência de sobreposição, rolagem interna, tooltip nas extremidades, toque/teclado/Escape, cinco larguras e claro/escuro; orçamento vertical de Relatórios, descoberta por botão, snapshot intacto e zero gravações externas. Data de teste fixada para comparar snapshots sem variação de `createdAt`.

Gates da PR: `npm test`, `npm run format:check`, `npm run test:browser` e CI no HEAD final, incluindo suites nativas de Relatórios/CSV/PDF, local/remoto/falhas, onboarding/personalização/isolamento e matrizes gerais de temas. Resultados finais são registrados na descrição da PR/Actions, evitando um commit apenas para carimbar CI.

Mapa executável da próxima adição atualizado em [PROJECT-STRUCTURE.md](PROJECT-STRUCTURE.md#como-adicionar-uma-feature): entrada, navegação/wrappers, renderização, ajuda, temas/motion, stores, identidade, rascunhos e testes. Nenhuma funcionalidade, API ou migration futura criada.

Parecer: **CONDITIONAL** para desenvolver a próxima funcionalidade após revisão/CI. Homologação em aparelhos físicos/leitor de tela e riscos operacionais acima permanecem separados da prontidão de desenvolvimento; esta rodada não certifica lançamento em produção.
