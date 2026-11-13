#Requires -Version 5.1
<#
.SYNOPSIS
  Diagnostico somente de leitura do SocialMEI-IA na AWS.
.DESCRIPTION
  Usa a chave SSH local e consulta recursos basicos no Ubuntu.
  Nao requer credenciais AWS no Windows e nao mostra variaveis de ambiente,
  dados de clientes, segredos, logs ou strings de conexao.
  Nao altera containers, bancos, regras de rede ou arquivos no servidor.
.EXAMPLE
  .\tools\socialmei-producao-somente-leitura.ps1
#>
[CmdletBinding()]
param(
    [string]$Servidor = 'ubuntu@54.94.213.7',
    [string]$Chave = (Join-Path $env:LOCALAPPDATA 'SocialMEI-SSH\socialmei-aws-key.pem'),
    [string]$Relatorio = ''
)

$ErrorActionPreference = 'Stop'
if ($Servidor -notmatch '^[a-z_][a-z0-9_-]*@[a-zA-Z0-9.-]+$') {
    throw 'Destino SSH invalido. Use usuario@host.'
}
if (-not (Test-Path -LiteralPath $Chave -PathType Leaf)) {
    throw 'Chave SSH nao encontrada. Informe -Chave com o caminho local correto.'
}
if (-not (Get-Command ssh.exe -ErrorAction SilentlyContinue)) {
    throw 'OpenSSH nao encontrado no Windows.'
}

$diagnostico = @'
set -eu

echo "=== SOCIALMEI: DIAGNOSTICO SOMENTE LEITURA ==="
echo "Data UTC: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "Servidor: $(hostname)"
echo

echo "=== RECURSOS ==="
uptime
free -h
df -h /
echo

echo "=== DOCKER ==="
if ! command -v docker >/dev/null 2>&1; then
    echo "Docker indisponivel."
    exit 3
fi
if ! docker info --format '{{.ServerVersion}}' >/dev/null 2>&1; then
    echo "Sem acesso de leitura ao Docker."
    exit 4
fi
docker ps --format 'table {{.Names}}\t{{.Status}}'
echo

echo "=== ESTADOS DOS SERVICOS PRINCIPAIS ==="
for name in \
    socialmei-team-team-api-1 \
    socialmei-team-team-postgres-1 \
    socialmei-postgres \
    socialmei-python \
    socialmei-n8n \
    socialmei-menu-worker-continuo \
    socialmei-instagram-menu-worker \
    socialmei-waha \
    socialmei-waha-gows-edge
do
    if docker inspect "$name" >/dev/null 2>&1; then
        docker inspect --format '{{.Name}} | processo={{.State.Status}} | saude={{if .State.Health}}{{.State.Health.Status}}{{else}}sem-healthcheck{{end}} | reinicios={{.RestartCount}}' "$name" | sed 's#^/##'
    else
        echo "$name | AUSENTE"
    fi
done
echo

echo "=== IDENTIDADE AWS DO SERVIDOR ==="
if command -v aws >/dev/null 2>&1 && aws sts get-caller-identity --region sa-east-1 --output json >/dev/null 2>&1; then
    echo 'IAM da instancia: autenticado'
else
    echo 'IAM da instancia: nao confirmado'
fi

echo
echo "=== LIMITES DA VERIFICACAO ==="
echo "O estado de saude do Docker nao substitui os testes reais de banco, WhatsApp, Instagram ou e-mail."
echo "Nenhuma conexao Prisma ou mensagem externa foi testada."
echo "Nenhuma alteracao foi aplicada."
'@

$entrada = $diagnostico.Replace([string][char]13, '') + [string][char]10
$saida = @($entrada | & ssh.exe -T -i $Chave -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=20 $Servidor 'bash -s' 2>&1)
$codigo = $LASTEXITCODE

$saida | ForEach-Object { Write-Output $_ }
if ($Relatorio) {
    $saida | Out-File -LiteralPath $Relatorio -Encoding UTF8
    Write-Host "Relatorio salvo em: $Relatorio"
}
if ($codigo -ne 0) {
    throw "Verificacao incompleta. Codigo SSH: $codigo"
}
