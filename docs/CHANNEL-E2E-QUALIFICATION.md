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
