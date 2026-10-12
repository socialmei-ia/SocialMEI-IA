# Roadmap

## Atualização de 12/10/2026

API de gestão dos quatro módulos, migrations incrementais, transferência inicial, gateway protegido, leitura técnica do n8n e backups da equipe já foram implementados. O CI inclui PostgreSQL real, navegador, autenticação HTTPS e restauração de backup isolada. O planejamento original abaixo é histórico; itens que dizem que essas bases não existem foram superados.

Próximos passos atuais:

1. Decidir acesso compartilhado ou contas individuais com o dono; manter a proteção atual até a decisão.
2. Obter chip dedicado e conectar WAHA; recebimento/envio ainda depende dessa etapa.
3. Definir IDs estáveis, deduplicação e autenticação do atendimento antes de conectar canais reais.
4. Preparar regras de orçamento/atendimento; leitura técnica do CRM não autoriza escrita por automações.
5. Automatizar cópias externas de novos backups e ensaiar recuperação dos backups reais em destino separado.
6. Fixar versões de imagens/dependências após validá-las, separar dados de demonstração e reduzir gradualmente o acoplamento dos scripts.

Veja [a revisão atual](docs/REVISAO-PROJETO-2026-10-12.md) e [a operação da equipe](docs/OPERACAO-EQUIPE.md).

## Planejamento original de 10/10/2026

Prioridades: **P0** bloqueia uso real do fluxo principal; **P1** prepara a próxima fase; **P2** manutenção/polimento; **P3** exploração futura. Cada item abaixo deriva do código auditado, não de disponibilidade presumida de serviços.

## Próxima etapa

| Prioridade | Mudança                                                     | Evidência e conclusão esperada                                                                                                                       |
| ---------- | ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| P0         | Validar n8n/PostgreSQL em ambiente isolado                  | Export inativo, credenciais externas e SQL não automático. Reproduzir POST → banco → GET → Inbox e registrar versão do n8n/configuração.             |
| P0         | Proteger leitura/recebimento de mensagens                   | Export sem autenticação e CORS `*`; login local não protege dados remotos. Definir autenticação, autorização, origem e rate limit fora do frontend.  |
| P0         | Definir fronteira de dados e identidade do CRM              | Gestão usa localStorage e não há multiempresa/backend CRUD. Especificar usuários/negócios e migração sem perder backups existentes.                  |
| P1         | Confirmar regressão no CI e revisar a interface visualmente | AST/cascata preservados; regressão local passou em 88 estados e oito fluxos. Exigir sucesso do job remoto e revisar movimento normal antes do merge. |
| P1         | Conferir WAHA/Compose na VPS sem redefinir volumes          | Compose anterior inválido e flags sem senha conflitavam com docs. Validar versão, credenciais, bind local e destino do hook com alvos de teste.      |

## Curto prazo

| Prioridade | Mudança                                                  | Evidência                                                                                                                                                          |
| ---------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| P0         | IDs estáveis e idempotência no atendimento               | Frontend agrupa por nome/canal; GET não retorna IDs de conversa/cliente; INSERT não deduplica evento externo. Evitar mistura de homônimos e duplicação em reenvio. |
| P1         | Integrar envio externo com confirmação/falha/retry       | Composer apenas adiciona mensagem local. Usar API autenticada/adaptador, estado de envio e testes de canal em sandbox.                                             |
| P1         | Persistir gestão em backend com migração de dados locais | Só histórico de atendimento tem tabelas. Criar contratos e migrations depois da decisão de identidade, preservando exportação/importação.                          |
| P1         | Fixar versões de imagens e dependências Python testadas  | n8n/WAHA/pgAdmin usam `latest`; requirements não fixa versões. Registrar versões realmente validadas e processo de atualização.                                    |
| P1         | Ensaiar restauração e ampliar cobertura dos backups      | Script cobre PostgreSQL/config/n8n, não sessões WAHA. Definir política por volume, cópia fora do host, concorrência e recuperação documentada.                     |

## Médio prazo

| Prioridade | Mudança                                                  | Evidência                                                                                                                                                         |
| ---------- | -------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1         | Conectar o Assistente a serviço de IA com revisão humana | Sugestões são locais; os exports Gemini de Instagram não atendem o Assistente do app. Adicionar contexto autorizado, erro/custo e rascunho antes de envio.        |
| P1         | Vincular automações do app ao executor                   | Regras e histórico são simulados. Definir persistência, agenda, cancelamento, retries e eventos auditáveis.                                                       |
| P2         | Separar `experience.js` e `app.js` por ciclo de vida     | Ainda concentram várias responsabilidades; introduzir fronteiras graduais com testes de inicialização.                                                            |
| P2         | Consolidar CSS por componente com comparação visual      | 4.437 regras originais, 834 seletores repetidos e 203 `!important`. Nem toda repetição é defeito; revisar por escopo, não apagar em lote.                         |
| P2         | Separar dados de demonstração da sessão remota           | Atividade e conversas demo vivem em `sessionData`; definir modo demo explícito sem contaminar uma conta real.                                                     |
| P2         | Testes HTTP/SQL e observabilidade                        | Testes atuais de Python são de modelo/função; falta execução real de consultas, autorização e recuperação. Acrescentar testes isolados e logs sem dados pessoais. |

## Futuro

- **P3 — Relatórios compartilhados:** depois de persistir gestão e definir métricas reais; gráficos atuais misturam dados locais/demonstração.
- **P3 — Integração oficial adicional de canais:** comparar APIs/providers depois de validar recebimento/envio e requisitos do produto.

## Dívida técnica

- Globais compartilhados e ordem de carregamento entre scripts clássicos.
- `experience.js`, `app.js`, `business-views.js` e CSS ainda grandes.
- Classes/IDs antigos e campos persistidos em português requerem migração, não renomeação mecânica.
- Ausência de migrations incrementais, multiempresa e API de gestão autenticada.
- Exports experimentais com nós não conectados/incompletos; preservados para revisão manual.
- Endereços históricos da VPS e versões `latest` dificultam reprodução de um deploy validado.

Próxima entrega recomendada: **um ambiente de teste reproduzível de atendimento, com identidade/autorização definidas e critérios de aceite de dados**, antes de ampliar a integração de IA ou redesenhar a interface.

## Plano de persistência compartilhada

A sequência detalhada para tirar gestão do `localStorage` sem perder compatibilidade está em
[docs/PERSISTENCE-MIGRATION.md](docs/PERSISTENCE-MIGRATION.md).
