# Qualificação conjunta WhatsApp e Instagram

## Escopo

Ensaio descartável da candidata PR #212, SHA
`345a074310673640084c7634e3da75dd72491813`. A aplicação e suas imagens não são
recompiladas nem alteradas por esta branch. O pacote fixado é o artefato
`13414736091`, SHA256
`0ff6d5364e54f003016c70c2408412006e981fe3bf30831f44eb5c4970e1767a`.

O ensaio combina n8n **2.40.5 real**, API da imagem exata e PostgreSQL **16 real**.
WAHA e Meta são substituídos por envelopes assinados e um transporte de teste.
Não há números reais, tokens de provedores ou acesso à AWS. A rede Docker é
interna, sem portas publicadas; o harness não faz pull nem aceita daemon remoto.
O CI obtém as imagens públicas de dependência antes de criar essa rede.

## Cenários

- Mensagem WAHA assinada é persistida e aparece na Caixa do negócio correto.
- O planner existente produz menu e catálogo com preço/estoque cadastrados.
- Repetir o evento e o pedido ao planner não provoca segundo envio.
- Assinatura inválida e tentativa de escolher workspace pelo payload são recusadas.
- HTTP 500/timeout do transporte termina em recibo incerto, sem reenvio.
- O workflow Instagram preparado pelo helper existente conserva corpo/HMAC e
  newline, persiste antes de confirmar e deduplica o replay.
- Assinatura Meta inválida ou API indisponível não recebem confirmação de sucesso.
- O ramo legado de IA/envio permanece inalcançável no modo receive-only.
- Sessão de outro negócio não enxerga essas conversas.

## Execução

Pré-requisitos: Linux com Docker local, Python 3.12, Node 22+, imagens
`postgres:16-alpine` e `n8nio/n8n:2.40.5` previamente obtidas, checkout limpo da
SHA da aplicação e ZIP do artefato exato. Não usar servidor de produção.

Plano sem Docker:

```sh
python3 tools/channel-e2e-lab.py
```

Execução em executor descartável:

```sh
python3 tools/channel-e2e-lab.py --run \
  --source /caminho/checkout-limpo-da-aplicacao \
  --candidate-bundle /caminho/artefato-13414736091.zip \
  --receipt /caminho/novo/channel-qualification.json
```

`read_bundle038` é uma entrada explícita de verificação; o caminho antigo de
importação continua recusando perfil 038. O verificador OCI é reutilizado da
PR #185. ZIP, SHA256SUMS, prova de migrations, revisão e imagem API precisam
corresponder antes de carregar e executar o artefato.

Recursos são rotulados com identidade exclusiva e removidos por essa identidade.
Falha de limpeza reprova o ensaio. O recibo é sanitizado e separa resultados
efetivamente observados das limitações.

## Limites e implantação

Sessões e conexão OAuth são fixtures, não login/OAuth reais dos provedores. O
trigger do planner é adaptado somente na cópia de teste para receber uma
referência pelo webhook; isso não homologa o poller/subworkflow de produção.
O salto interno Instagram usa HTTP na rede isolada; TLS e Caddy públicos não
são homologados por este ensaio. Nenhuma alteração é feita nos templates ou no
workflow publicado de produção.

Resultado aprovado comprova os cenários na fixture. Não significa implantação,
sessão WAHA conectada, inscrição Meta correta, resposta entregue ou leitura por
um cliente. Ativar respostas reais continua exigindo acesso autorizado,
inventário/backup frescos, um único respondedor e destinatários de teste definidos.

## Checkpoint

Preparação inicial: 11 testes de guardas/workflows do harness, três testes do
importador 038, 15 testes OCI, 13 testes do importador legado e nove contratos
do preparador Instagram aprovados localmente. A execução combinada pertence ao
workflow dedicado `channel-e2e-checks.yml`; seu resultado deve ser consultado
para a SHA exata da PR. Não substituir resultado pendente/falho por testes
isolados ou por evidências de revisões anteriores.

## Continuidade operacional — 05/11/2026

Branch de qualificação: `test/channel-e2e-212`, PR Draft #213. Base de aplicação:
PR #212, `345a074310673640084c7634e3da75dd72491813`. Não usar o operador da
PR #211 diretamente para esta candidata: ele fixa a PR #210, outra identidade.
A PR #212 prepara **recebimento** Instagram; não habilita respostas automáticas
nem demonstra publicação de posts. O ensaio WhatsApp exercita respostas de menu e
catálogo, mas o provider é sintético. Nenhum dos dois estados comprova operação
no site oficial.

O ambiente remoto desta sessão não tem identidade AWS, segredo SSH ou rota de
produção configurados. Um caminho de chave no notebook Windows não concede
acesso a esta máquina. Nenhuma inspeção atual dos containers/contas publicados
foi realizada. Relatos anteriores de versão instalada não substituem inventário
fresco.

### Sequência quando o acesso estiver disponível

1. Inventariar de forma privada SHA/revisão e IDs das imagens da API/gateway,
   schema aplicado, saúde, Compose efetivo, redes e volumes. Inspecionar n8n e
   WAHA sem reiniciar nem recriar serviços. Registrar somente IDs/resultados
   sanitizados. Confirmar versão real do n8n antes de promover os templates.
2. Revalidar CI e artefato da candidata exata. Preparar um operador com os mesmos
   SHA/IDs e schema observado; não reaproveitar um pin de outra candidata.
   Preservar a configuração e os serviços n8n/WAHA. Backup PostgreSQL e restore
   em cópia descartável são gates anteriores a qualquer corte. Não fazer
   downgrade ou restaurar dump sobre dados novos como recuperação automática.
3. Homologar login, Origin/CSRF, negócio e Caixa com sessão humana. Sessões do
   laboratório são fixtures e não comprovam esse gate.
4. WhatsApp: confirmar sessão existente `WORKING`, canal/registry corretos e
   ingresso HMAC assinado persistindo **antes** do planner. Conferir qual fluxo
   responde atualmente; deixar um único remetente. O poller/subworkflow real e
   a lista de contatos autorizados precisam de homologação. Não substituir a
   sessão, trocar engine ou presumir autorização de contatos.
5. Instagram: exportar a revisão publicada do fluxo existente; gerar e revisar
   o diff do preparador receive-only sobre essa revisão. Inspecionar vínculo da
   conta, validade/permissões OAuth e inscrição Meta sem imprimir tokens. Não
   retomar o ramo legado de IA/envio como efeito da implantação de recebimento.
6. Depois de corte aprovado, uma mensagem de cada contato/conta de teste deve
   aparecer uma única vez na Caixa do negócio correto. Reenvio do mesmo evento
   não pode duplicar persistência/resposta; outro negócio não pode ler os dados.
   Testar menu/catálogo WhatsApp com preço e estoque conhecidos e transferência
   para humano. Confirmar aceite e, separadamente, entrega no aparelho.
7. Antes de declarar Instagram respondendo, homologar a saída humana/automática
   autorizada, janela/permissões e entrega na conta de teste. Publicações exigem
   sua própria homologação; recebimento Direct não comprova posts publicados.
8. Falha: suspender o novo remetente, preservar ingressos, schema e decisões.
   Conciliar `claimed`/`uncertain` sem reabrir tentativa. Só voltar binários
   anteriores se a compatibilidade com o schema atual estiver comprovada.

Critério de conclusão operacional: evidência datada de SHA/imagens/schema,
backup e restore, saúde e jornadas autenticadas no site oficial, junto do ID
sanitizado da mensagem recebida e do recibo/entrega de resposta. CI verde sozinho
não satisfaz esse critério. Até lá, manter produção como **não homologada nesta
sessão**.
