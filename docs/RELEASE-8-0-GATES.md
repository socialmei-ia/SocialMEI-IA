# Candidata 8.0

A referência de produção disponível é a Missão 07 com schema 046. A candidata precisa do aceite manual dessa versão, da homologação integrada e das autorizações de publicação. A execução local usa dados sintéticos e mantém os envios externos desativados.

## Preparar as imagens

```powershell
python tools/build-production-overlay.py --build api --inbox-fixes --editorial --commercial --management
python tools/build-production-overlay.py --build gateway --gateway-fixes --editorial --commercial --management
```

Use os IDs base do manifesto congelado. Registre o SHA do Git, os IDs das imagens prontas, os hashes dos mounts e as referências atuais de rollback. A opção editorial inclui o worker de fotos, com ativação separada. As candidatas de mídia dos canais exigem ensaio próprio, partindo dos workers efetivos.

## Gates para produção

1. Confirmar em produção o aceite manual da Missão 07, o ledger, a saúde e os mounts efetivos.
2. Validar backup fresco com restauração isolada. Verificar instalação limpa e atualização de 046 até 059 com as permissões do papel da API. Conferir a view de caixa, o histórico de estoque (incluindo a escrita do gatilho e o acesso à sequência) e a biblioteca privada de imagens.
3. Aprovar separadamente as migrations, o corte de API e gateway e qualquer ativação externa. Revalidar CI, uso de memória, isolamento, idempotência e journaling.
4. Ensaiar reversão de API e gateway juntos com os mounts equivalentes. Antes de aceitar escritas da candidata, usar as imagens e configurações congeladas se houver regressão. Após escritas de parcelas e recebíveis, congelar as operações afetadas e manter o ledger. A versão anterior desconhece os vínculos e poderia aceitar baixas conflitantes. Corrigir na versão compatível ou manter Financeiro e Vendas indisponíveis até a recuperação.
5. Testar HTTPS, autenticação, troca de empresa e as jornadas abaixo. Testar provedores somente com contas autorizadas e aprovação do envio. Preservar WAHA e n8n durante o corte da aplicação.

## Roteiro do responsável e do professor

| Área            | Ação e resultado esperado                                                                                                                                                                                                              |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sessão          | Alternar entre Brilho e Bella e recarregar. Cada empresa mostra somente seus próprios registros.                                                                                                                                       |
| Caixa           | Na versão publicada, testar leitura, arquivo, recuperação, fixação, adiamento, respostas rápidas e o controle de automação. Registrar o aceite da Missão 07.                                                                           |
| Agenda e CRM    | Registrar e cancelar um agendamento no ambiente de teste. Conferir o histórico do cliente, os filtros e a liberação do horário.                                                                                                        |
| Venda e estoque | Converter uma oportunidade em venda. Uma repetição do mesmo pedido mantém uma venda e uma baixa de estoque.                                                                                                                            |
| Financeiro      | Criar um recebível para a venda em ambiente de teste, registrar uma parcela e conferir caixa e saldo aberto. Quitar o restante, consultar a venda e estornar uma parcela com motivo. A venda volta a pendente e o caixa é recalculado. |
| Negócio e DAS   | Conferir o corte do faturamento anterior. Declarar um DAS fictício no ambiente de teste, consultar a revisão e revogar a declaração. O registro é interno.                                                                             |
| Divulgação      | Salvar, recarregar, editar, duplicar e arquivar um rascunho de texto. Conferir o agendamento de foto sem ativar a publicação externa.                                                                                                  |
| Professor       | Usar a conta individual autorizada. Conferir os relatórios permitidos e a troca de empresa. Operações de escrita exigem papel próprio e autorização.                                                                                   |

## Pendências de liberação

- Aceite manual da Missão 07, CI do commit de release e rollback conjunto com mounts equivalentes.
- Homologação e autorizações para áudio/mídias, Meta e Brevo. Lembretes, presença e agendamento público exigem seus próprios testes e autorizações.
- Manter no backlog os formatos de publicação e as métricas da Meta, atendimento por mídias, jornada da Agenda pelos canais, notificações e homologação de onboarding/Brevo.

## Continuação da Missão 10

- **Estoque.** A migration 055 registra movimentos posteriores à instalação. Em um produto novo, a primeira entrada registra o saldo inicial. Em produtos preexistentes, a primeira linha indica o saldo real anterior àquela operação. Faça uma venda, repita a solicitação, cancele e confira a reposição e o vínculo no histórico do produto. Confira o estoque mínimo atual e a movimentação do período no relatório.
- **Divulgação.** A migration 056 guarda imagens compatíveis por negócio. Selecione uma foto, salve o rascunho, recarregue com outra sessão autorizada e confira a imagem e o enquadramento. Reutilize a imagem em outro rascunho e confira que o outro negócio não tem acesso. Limites de 2 MiB por imagem e de 50 imagens ou 24 MiB por negócio. Vídeos permanecem na prévia local. Dados legados de navegador continuam preservados no navegador.
- **Texto na Divulgação.** Os botões de legenda e ideia chamam o contrato existente de geração de texto depois de um clique explícito. A sugestão de legenda tem botão próprio para aplicação. A validação isolada usa transporte sintético. A homologação com o provedor exige autorização de consumo.

### CI do commit candidato

O workflow `Repository checks` dispara por push em `main` ou por pull request para as branches-base listadas no arquivo. O push para a branch de consolidação, sem PR, não dispara essa CI. Os workflows manuais de deploy têm outra finalidade.

Depois de confirmar orçamento do GitHub Actions, permissão e a base de revisão, abrir um PR em rascunho para uma base coberta pelo workflow e verificar a execução do SHA candidato. Revisar primeiro o diff acumulado, pois a branch contém a consolidação desde as missões anteriores. Disparos manuais de deploy ficam fora da validação. Conservar a evidência dos testes isolados até a confirmação da CI remota.

### Evidências desta continuação

- PostgreSQL 17 descartável. Instalação limpa 001–056 e restauração de cópia sintética do schema 046 seguida de atualização até 056. O saldo legado foi preservado, sem movimentos retroativos. Um papel SQL restrito registrou uma alteração pelo gatilho e teve a exclusão do histórico negada.
- 43 testes Python passaram em catálogo, estoque, vendas, oportunidades, biblioteca, agendamento editorial e relatórios. Navegador em 390 px e 1280 px verificou o histórico de estoque, o novo gerenciamento do rascunho com imagem e a sugestão de texto com resposta de teste.
- AWS permanece na publicação conhecida da Missão 07. Os bots e os serviços externos mantêm o estado anterior à candidata. O corte da aplicação, o aceite manual, a homologação real de provedores e o ensaio de rollback conjunto continuam pendentes.

## Fechamento das integrações da Missão 10

### Instagram e Agenda

- A migration 057 adiciona uma interpretação por mensagem e vincula o resultado ao anexo, negócio, mensagem e hash. O anexo já pertence ao evento autenticado e à conta Meta. A legenda original continua intacta. Resultado incerto fica registrado sem nova tentativa.
- A ativação requer o ingresso de anexos habilitado, o opt-in `SOCIALMEI_INSTAGRAM_MEDIA_AI_ENABLED=YES`, a lista de negócios em `SOCIALMEI_INSTAGRAM_MEDIA_AI_WORKSPACES`, um corte ISO 8601 com fuso em `SOCIALMEI_INSTAGRAM_MEDIA_AI_START_UTC` e a credencial privada `SOCIALMEI_INSTAGRAM_MEDIA_AI_KEY`. Rodar `python -m instagram_media_interpretation --workspace ID` processa no máximo um anexo elegível por execução. O limite por negócio é de 12 tentativas em 24 horas, com uma em andamento e 2 MiB por arquivo. Mídias fora da janela de dois minutos não entram na fila de interpretação.
- Respostas de mídia e evidências comerciais têm flags próprias e desativadas por padrão: `SOCIALMEI_INSTAGRAM_MEDIA_AI_REPLIES_ENABLED` e `SOCIALMEI_INSTAGRAM_MEDIA_AI_COMMERCIAL_ENABLED`. Apenas intenções permitidas viram opções do menu ou descrições comerciais padronizadas. A interpretação de imagem permanece como contexto privado. Um pedido de horário em áudio pode listar serviços, e a confirmação exige uma resposta textual separada.
- A política da Agenda aceita `special_days` pela configuração existente. A data substitui os intervalos semanais daquele dia. Uma lista `hours` vazia fecha o dia. Intervalos separados preservam pausas. A mesma política controla apresentação de datas, oferta e revalidação do horário. O agendamento público permanece desativado.
- O delta foi portado para os arquivos capturados da API e do remetente, preservando a personalização do menu, a seleção de conversas e as regras comerciais congeladas. As flags de mídia e despacho permanecem desativadas em produção.

```powershell
python tools/build-production-overlay.py --build api --inbox-fixes --editorial --commercial --management --media-commercial --instagram-media --booking-special-days --instagram-media-ai
python tools/build-production-overlay.py --build menu --whatsapp-media --booking-special-days
```

Os builds verificaram os 62 arquivos congelados e usaram as bases fixadas no manifesto. O gateway permanece o da candidata anterior. Identidades locais:

- API `sha256:92eefdb2f8a7cec7b69341fc48d01c39808feae9ff46e712834a1574a02b8374`
- Remetente WhatsApp `sha256:ecf7c82f5b1ee1440d9ccc27b4d3f28d94a76277d7a0200cdb3489600f946db1`
- Gateway `sha256:c08e80bd6f15bb03a38c285cfcee43bdbbb1688a279702e8533e456b425ba02d`

A API passou em seis testes empacotados com PostgreSQL isolado, chave sintética em mount somente leitura e sem Internet. A imagem do remetente passou nos dois testes de horários especiais, sem rede. O próximo gate da release é o ensaio conjunto com mounts equivalentes e reversão compatível após escritas financeiras.

### PR e CI

- Rascunho proposto: **SocialMEI-IA 8.0 — consolidação e homologação**. Base de revisão `release/functional-completion-20261112`, ancestral da consolidação, com gatilhos de `Repository checks`, `MEI demo isolated gates` e `WhatsApp GOWS release gates`. A abertura do PR nessa base aciona validações. Os workflows de publicação exigem disparo manual.
- O repositório é público, o acesso consultado permite escrita e Actions está habilitado. Os workflows de validação usam runners padrão. Segundo [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), a execução desses runners é gratuita em repositórios públicos. Há etapas de upload de artefatos, cuja margem de armazenamento ainda não foi confirmada. A consulta de cobrança retornou 404. O PR e a CI aguardam a confirmação dessa margem.
- Checklist do rascunho: CI no SHA candidato, ensaio integrado com os mounts, rollback compatível depois de escritas financeiras e aceite manual da Missão 07. Manter mídia, envios, publicação na Meta e agendamento público desativados até homologação e autorizações correspondentes.

- PostgreSQL 17 descartável: instalação limpa até 057 e restauração sintética do schema 046 seguida de atualização até 057 com dados preservados e gravação da interpretação autorizada pelo papel restrito. A instalação não enfileira mídias antigas.
- A regressão de mídia, Agenda e publicação pública de horários em isolamento passou. O ensaio final sem rede externa confirmou deduplicação do anexo, evidência comercial sem transcrição, atendimento humano, abertura da lista real de serviços por áudio sem criar reserva, confirmação textual e regras de dias especiais.
- Nenhuma ativação da Meta, do Gemini ou da publicação externa foi executada. A decisão para produção continua bloqueada até validar os serviços e mounts efetivos, o rollback conjunto, a CI e as autorizações.

## Ensaio conjunto desta candidata

Rode `python tools/rehearse-8-0-rollback.py`. O ensaio fixa os IDs locais e cria um PostgreSQL 17 descartável com o ledger no formato efetivo. A rede Docker interna não publica portas. Configurações sintéticas entram por mounts somente leitura. Edge, Instagram e worker despachante permanecem ociosos. O ensaio cobre a API principal, o gateway e a API privada do menu. O processamento dos workers com o conjunto final de mounts ainda é um gate separado.

- **Antes de escritas.** A API e o gateway legados e a API privada do menu voltaram com saúde no schema 057. O estado do banco ficou igual.
- **Depois de escritas.** Pelo gateway, o ensaio registrou uma venda com repetição concorrente da chave, vinculou o recebível, reaplicou a mesma parcela e verificou o isolamento. Durante a reversão, o gateway retornou 503 e o papel legado ficou sem login. A recuperação iniciou as imagens compatíveis e conferiu os hashes de vendas, recebíveis, parcelas, movimentos de estoque e ledger. Nenhuma restauração de banco foi executada nessa reversão.
- **Condição para repetir em produção.** Vincular os IDs e mounts efetivos, identificar credenciais compartilhadas e provar que a imagem antiga não consegue autenticar depois do bloqueio. Drenar os serviços e desligar consumidores antes da transição. Manter a borda em manutenção e preservar o ledger enquanto os componentes compatíveis são recuperados. Se uma credencial for compartilhada, não reaproveitá-la na versão antiga. Testar segregação ou suspensão no plano produtivo antes de liberar escritas.
- **Agenda no navegador.** Em Funcionamento e disponibilidade, abra Horários especiais e feriados. Registre um dia fechado, configure dois intervalos separados para outro dia e confira as opções oferecidas nos canais. O ensaio de interface passou em 390 px e 1280 px, incluindo proteção por revisão e troca de negócio. Não altera o horário descritivo do perfil, a habilitação dos canais ou o agendamento público.
- **Gateway deste incremento.** `sha256:5c0a593957309d1e0b920ae086725971abffbc9767e71419f0c93c7035ed296e`. A API e o remetente mantêm os IDs da seção anterior. O ensaio verifica o carregamento de `agenda-hours.js` no gateway.

### Confirmação de armazenamento para abrir o PR

Na conta proprietária, abra **Settings → Billing & Licensing → Usage** e filtre por **Actions** e pelo SKU de armazenamento de artefatos no período atual. Confira a franquia, o consumo e o orçamento aplicável. Em **Settings → Actions → General** do repositório, confira **Artifact and log retention**. O workflow define 14 dias para `SocialMEI-public-demo`. `release-candidate-readiness`, `frontend-regression` e `isolated-preview` herdam a retenção do repositório. Valide margem para esses uploads antes de abrir o rascunho. [Orientação de uso e cobrança do GitHub](https://docs.github.com/en/billing/how-tos/products/view-productlicense-use) [Retenção de artefatos e logs](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository)

## Workers e presença — schema 058

- Execute `python tools/rehearse-8-0-workers.py` para o observer e o edge. O ensaio usa a imagem de observação revisada, dois negócios sintéticos e CA temporária montada em `/run/database-ca.crt`. Verifica TLS `verify-full`, contagens separadas, exclusividade do lease no PostgreSQL, recuperação do checkpoint após reinício e rejeição da credencial legada. O observer tem papel somente leitura. Os envios ficaram em zero.
- O edge rejeitou permissões abertas no registry e assinaturas inválidas. Quatro entregas concorrentes da mesma entrada criaram uma linha. Uma falha 503 manteve o evento no spool. Após reabrir a fila, a repetição preservou os bytes e aceitou o recibo de duplicata como entrega. O teste do menu empacotado passou em ingresso assinado de áudio, seleção e claim únicos e pausa humana. A ligação conjunta do despachante com os aliases e mounts efetivos da AWS permanece um gate.
- Na Agenda, um responsável confirma presença ou registra ausência depois do horário. O registro tem revisão e recibo idempotente, aparece no histórico da Agenda e no CRM, e fica associado ao horário original. Reagendar limpa a presença vigente e conserva o histórico. A migration 058 não cria presença para reservas anteriores. Lembretes externos, agendamento público e envio pelos provedores permanecem desativados.

```powershell
python tools/build-production-overlay.py --build api --inbox-fixes --editorial --commercial --management --media-commercial --instagram-media --booking-special-days --instagram-media-ai --attendance
python tools/build-production-overlay.py --build gateway --gateway-fixes --editorial --commercial --management --attendance
```

Identidades locais deste incremento:

- API `sha256:b8088831064d175523f067499abb8f0442f390fb71e58d116a9bb8fb1f3e94de`
- Gateway `sha256:ff2a4781e63297cb97baabf13d5b43b53625762d835a7919ad734b19fc57741c`
- Menu `sha256:ecf7c82f5b1ee1440d9ccc27b4d3f28d94a76277d7a0200cdb3489600f946db1`

O ensaio de rollback financeiro continua congelado nos artefatos e no schema 057 usados na sua homologação. Para o corte produtivo, aprove a sequência **manutenção → drenagem → backup e restauração isolada → migrations aditivas → API privada, API e gateway → smoke tests → liberação das escritas**. Em caso de falha antes de escritas, use os artefatos anteriores homologados. Após escritas novas, preserve o ledger e os recibos e mantenha bloqueada a credencial legada até a recuperação compatível. Reavalie a permissão de alteração da Agenda antes de reabrir o tráfego. A ativação dos workers e provedores tem autorização separada.

### CI e teste manual

Na amostra dos 100 artefatos mais recentes, a soma dos maiores tamanhos observados para os quatro uploads do workflow foi de 24.251.450 bytes (23,13 MiB) por execução como estimativa, sujeita à variação dos testes. A retenção observada foi de 14 dias para o demo público e 90 dias para os outros três. A margem de cobrança pertence à conta proprietária. O rascunho fica pronto para abertura após essa confirmação. [Histórico de artefatos pela API do GitHub](https://api.github.com/repos/socialmei-ia/SocialMEI-IA/actions/artifacts?per_page=100)

Checklist de presença para o responsável: em ambiente de teste, confirme presença em uma reserva futura, recarregue, confira o detalhe e o CRM. Reagende e confira que o horário novo pede outra confirmação. Depois do fim de uma reserva passada, registre ausência e confira o histórico. Para o professor, use conta autorizada de leitura e confira a Agenda e o histórico do cliente de cada negócio permitido.

Validações do incremento. 29 testes Python de Agenda e gerenciamento por canal, teste direcionado na imagem da API, caso de áudio na imagem do menu e navegador a 390 px e 1280 px. PostgreSQL 17 passou em instalação limpa e numa atualização da restauração isolada de 046 para 058, preservando a reserva anterior e restringindo a edição do histórico.

## Presença por canal, histórico e som — schema 059

- A migration 059 associa confirmações do cliente à mensagem autenticada, ao canal e ao negócio. A seleção que abre o resumo não grava presença. Somente a confirmação textual ou a seleção interativa verificada pode criar o recibo. Repetições retornam o resultado existente e o atendimento humano continua bloqueando o fluxo. Ativação por `SOCIALMEI_CHANNEL_ATTENDANCE_ENABLED=YES` e `SOCIALMEI_CHANNEL_ATTENDANCE_WORKSPACES`, desativada por padrão.
- O histórico da Divulgação usa registros de publicações da conta ativa. A consulta opcional lê apenas curtidas e comentários do identificador confirmado pela publicação. Campo ausente aparece como indisponível. Uma publicação incerta continua identificada como incerta. [Campos oficiais de mídia da Meta](https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/v21.0/)
- O som da Caixa é uma preferência deste navegador, por usuário e negócio. Reaproveita a consulta existente da Caixa e ignora a primeira carga, mensagens antigas, repetições e conversas adiadas.

```powershell
python tools/build-production-overlay.py --build api --inbox-fixes --editorial --commercial --management --media-commercial --instagram-media --booking-special-days --instagram-media-ai --attendance --channel-attendance
python tools/build-production-overlay.py --build menu --whatsapp-media --booking-special-days --channel-attendance
python tools/build-production-overlay.py --build gateway --gateway-fixes --editorial --commercial --management --attendance
```

Identidades locais:

- API `sha256:61377123f8820c589912d3c2533022195f6d18d10b8f6ba0f3b352243ce98c14`
- Menu `sha256:7d3467523deed357b6d9069193f0d6d85c424f4290835e48d98c098e32676f59`
- Gateway `sha256:7bde4e950b269c70ba1d30c94a7374b1e2ec3b066c537490a39df0fd41e881b5`

A aplicação voltou a respeitar as variáveis já fornecidas ao container para validar o vínculo WAHA, mantendo os valores capturados como padrões. Antes do corte, compare a configuração efetiva de API e menu com o mesmo registry e com o hash revisado. Ambientes com divergência permanecem bloqueados pelo contrato existente.

As duas rodadas de regressão passaram com 18 e 20 testes Python. O Chrome passou nas jornadas de som e histórico editorial com transporte controlado. O PostgreSQL descartável passou na instalação limpa e na atualização de uma restauração de 046 até 059, preservando as confirmações manuais de 058. Os testes de métricas e despacho permanecem confinados ao ambiente isolado.

### Ensaio isolado do despachante

`python tools/rehearse-8-0-dispatcher.py` executa o despachante congelado com o menu reconstruído e PostgreSQL 17. A rede interna não publica portas. Os aliases do menu e do GOWS são equivalentes aos do runtime e as credenciais sintéticas são montadas somente para leitura.

O ensaio comprovou a recusa do token legado, o isolamento do segundo negócio, a recuperação após falha de leitura do GOWS, um único recibo confirmado e a preservação de um resultado incerto sem reenvio em uma nova execução. O provedor do ensaio é local. A execução cobre o modo `--run-once`. Os mounts privados efetivos e a continuidade do journal no serviço final ainda precisam ser confirmados antes do corte.
