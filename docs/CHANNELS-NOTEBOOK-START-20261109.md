# Retomada rápida dos canais no notebook

Objetivo P0: preservar o WhatsApp WEBJS em funcionamento e preparar o recebimento real do Instagram. GOWS/listas ficam fora do caminho crítico até concluir o pareamento.

**Estado comprovado:** a PR #215 tem 74 testes focais aprovados ([CI](https://github.com/socialmei-ia/SocialMEI-IA/actions/runs/42738984826)); a PR #213 tem 21 cenários integrados isolados de WhatsApp/Instagram. Esses testes não substituem mensagens de aparelhos reais. A última coleta AWS relatou WEBJS WORKING, GOWS FAILED sem webhook, mas esse estado precisa ser reconfirmado.

**Bloqueio de publicação:** o operador da PR #211 foi preparado para a imagem da PR #210 (7ba3d632), não para a candidata Instagram receive-only #212 (345a0743). Não reaproveitar o operador errado.

## Primeiro comando no Windows PowerShell 5.1

O bloco abaixo baixa somente o script do commit imutável 2ab73ddb07519d9f7c792449ee4c4cad383933c0, valida seu hash Git de conteúdo e executa pela conexão SSH atual. O código é somente leitura e nunca imprime credenciais, telefones, nomes de sessão, QR, mensagens, URLs privadas ou logs. Nenhum arquivo fica no servidor.

[Inspecionar a fonte fixada](https://github.com/socialmei-ia/SocialMEI-IA/blob/2ab73ddb07519d9f7c792449ee4c4cad383933c0/tools/channel-live-preflight.py)

~~~powershell
$ErrorActionPreference='Stop'
$chave="$env:LOCALAPPDATA\SocialMEI-SSH\socialmei-aws-key.pem"
if (-not (Test-Path -LiteralPath $chave -PathType Leaf)) { throw 'Chave SSH nao encontrada.' }
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$ref='2ab73ddb07519d9f7c792449ee4c4cad383933c0'
$blobEsperado='5c6170a167bd7f7435d11f29ef74e5c03798042e'
$url="https://raw.githubusercontent.com/socialmei-ia/SocialMEI-IA/$ref/tools/channel-live-preflight.py"
$web=New-Object System.Net.WebClient
try { [byte[]]$bytes=$web.DownloadData($url) } finally { $web.Dispose() }
if ($bytes.Length -lt 1000 -or $bytes.Length -gt 50000) { throw 'Tamanho de script inesperado.' }
[byte[]]$cabecalho=[Text.Encoding]::ASCII.GetBytes("blob $($bytes.Length)" + [char]0)
$memoria=New-Object IO.MemoryStream
try {
  $memoria.Write($cabecalho,0,$cabecalho.Length)
  $memoria.Write($bytes,0,$bytes.Length)
  $sha=[Security.Cryptography.SHA1]::Create()
  try { $blobReal=-join ($sha.ComputeHash($memoria.ToArray()) | ForEach-Object { $_.ToString('x2') }) }
  finally { $sha.Dispose() }
} finally { $memoria.Dispose() }
if ($blobReal -ne $blobEsperado) { throw 'Hash do script nao confere.' }
$b64=[Convert]::ToBase64String($bytes)
& ssh.exe -T -i $chave -o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu@54.94.213.7 "echo '$b64' | base64 -d | sudo -n python3 -"
if ($LASTEXITCODE -ne 0) { Write-Host 'Auditoria parcial ou indisponivel. Nenhuma alteracao realizada.' }
~~~

Se houver erro de host SSH desconhecido, confirmar a fingerprint por canal administrativo antes de adicioná-la; nunca desativar a verificação.

## Como decidir a etapa seguinte

1. Conferir os indicadores de API, worker, WEBJS, GOWS, n8n, Caddy e as imagens Docker efetivamente instaladas. O inventário de flags do Instagram não prova OAuth/assinatura/webhook Meta válido.
2. Caso WEBJS não esteja WORKING, priorizar recuperação do atendimento existente e não ligar GOWS.
3. Se WEBJS estiver preservado, comparar schema/migrations e revisão da API atual com a candidata #212; preparar um operador específico para a identidade dela, sem migrações ou deploy automático.
4. Fazer auditoria privada da versão **publicada** do workflow n8n e configuração do callback da Meta; preservar o ramo legado de IA/envio inativo.
5. Só depois de autorização operacional, executar prova receive-only com mensagens reais dos perfis Instagram, cada uma persistida uma vez na Caixa do workspace correto.
6. Após esses gates, retomar GOWS com o aparelho do WhatsApp principal, QR atualizado e mudança de um único remetente.

## Limites

Backup existente não equivale a restauração ensaiada; um CI verde não prova entrega no telefone. A auditoria não executa Docker up/restart, mudança de webhook, SQL de escrita, importação n8n, pareamento ou envio. Não usar dados de produção para rodar testes com TRUNCATE/migrações.

Plano central: [issue #216](https://github.com/socialmei-ia/SocialMEI-IA/issues/216).
