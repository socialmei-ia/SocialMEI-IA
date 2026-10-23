# PR100 — candidata de demonstração e integração nativa

Continuidade de23/10/2026, Fortaleza. Base remota conferida: PR100 Draft,
`release/integration-candidate-94-review` (#95). HEAD recebido `2d7f139`;
main conferida `4336181`. Novos commits preservam toda a cadeia anterior,
sem rebase/force-push. O SHA final é o HEAD da PR e o manifesto do artifact.

## Entregas

- Composição original V8/V4 extraída para as abas oficiais (sem iframe).
- V8 usa CRM autenticado para criar/editar/encerrar/reabrir, revisão, vínculo de
  venda e auditoria. Termômetro circular, Lista/Semana, busca e atalhos originais.
- Valor estimado/retorno/nota ficam em sidecar local isolado; nenhum campo ou
  migration de produção foi criado. Erro remoto nunca vira gravação local.
- V4 mantém telefone à esquerda, passos à direita, dock, edição da prévia,
  mídia local, enquadramento, modelos de legenda, rascunhos, import/export e agenda.
  Preparação compartilhada continua nos contratos existentes. Simular3publicações
  está desabilitado quando não há transação autorizada que preserve revisão.
- Pacote público independente contém apenas a entrada e golden masters com aviso,
  CSP por hashes e sem rede. Os golden masters versionados não foram alterados.
- Análise heurística anterior permanece em divulgação progressiva dentro de
  Oportunidades. Demais abas, autenticação, backend e schemas preservados.

## Evidências

- `test-results/exact-v8-v4/`: originais, integradas e canvas de comparação nos
  temas claro/escuro,320/390/768/1024/1440. V8 compara10combinações de estilos com
  golden master e operações reais no preview HTTPS descartável.
- `test-results/preview/result.json`: autenticação, CSRF,2negócios, persistência,
  isolamento, contratos simulados e transporte `none`.
- Revisão independente: histórico assíncrono sem apagar digitação, undo remoto
  com nova revisão e foco após mover ficha por teclado revalidados.
- Node:320testes. Python:245testes; manutenção30(5suites condicionais Docker não
  executadas nessa chamada, cobertura adicional no job validate). Ensaio de upgrade,
  dump/restore e integridade das migrations passou no banco descartável.
- Validação ampla de navegador e os3jobs no HEAD final são o gate da PR; verificar
  seus resultados atuais no Actions. Resultado anterior não autoriza publicação.

O HTTPS/Basic local inicialmente recebeu403 por proxy de saída aplicado aos aliases
Docker. Rerodado com NO_PROXY restrito aos aliases internos dos containers de teste:
aprovado. Nenhuma alteração no gateway real foi feita. O preview local também ganhou
`init:true` para coletar filhos encerrados pelo healthcheck HTTPS.

## Limites e aprovação

Não há URL pública nova. Preview local: `https://127.0.0.1:8443`, com banco próprio,
não compartilhável pela internet. O pacote estático pode ser aberto conforme
[PUBLIC-PROTOTYPE-BETA.md](PUBLIC-PROTOTYPE-BETA.md).

Próxima aprovação precisa escolher **origem HTTPS/provedor independente e SHA**.
Somente então publicar o artifact mínimo e validar sem login. Não utilizar Pages
atual, AWS/team, cookies do CRM, DNS ou secrets sem autorização específica.
Rollback estático: artifact anterior ou retirada da hospedagem, sem tocar no banco.

Instagram: preparação em [INSTAGRAM-META-INTEGRATION-READINESS.md](INSTAGRAM-META-INTEGRATION-READINESS.md).
OAuth, tokens, webhook e transportes reais continuam não conectados. Próxima etapa:
adaptador testado com provedor falso, assinatura, expiração, replay e2workspaces;
schema/App Review/contas reais exigem revisão própria.

## Correção confirmada no CI remoto

A execução39918451479 aprovou Validate/Preview e encontrou overflow da barra superior
na cópia pública V8 em768px. O ajuste de quebra de linha foi estendido a tablet na
cópia distribuída, sem modificar o golden master nem afrouxar a assertion. Regressão
pública cobre320/360/390/768/1024/1440 claro/escuro, mídia, legendas, rascunho,
agendamento/cancelamento e conexões fictícias. A contagem da agenda aguarda o estado
renderizado após a transição, preservando a exigência de14dias. Nova execução dos
3jobs é obrigatória no novo HEAD; o resultado da execução anterior não é aprovação.
