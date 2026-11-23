# Política de reinício GOWS

O contêiner instalado `socialmei-waha-gows-piloto` não possui vínculo Compose. Docker guarda sua política de reinício em disco; `unless-stopped` sobrevive ao reinício do daemon/host, respeitando uma parada manual. Não é necessário recriar o contêiner ou a sessão.

`tools/gows-restart-policy.py --directory <pasta privada nova>` prepara snapshot e plano, sem alterar o serviço. `--verify` compara imagem, configuração, mounts, redes e instante de início. Depois da aprovação específica do hash, `--apply --approved-plan <hash>` executa somente `docker update --restart unless-stopped <id congelado>`. Resultado incerto é conciliado por inspeção, sem repetir a atualização. `--rollback --approved-plan <hash>` restaura a política anterior e exige o mesmo contêiner intacto.

Uma recriação futura deve declarar `restart: unless-stopped`. Antes de qualquer deploy que passe a gerenciar o GOWS por Compose, renderizar seu JSON e executar `python tools/gows-restart-policy.py --check-compose <compose-renderizado.json>`. O gate exige um único serviço com o nome exato do contêiner e a política correta; não adota o contêiner existente nem executa Compose. A migração de gerenciamento permanece uma operação separada.

Preflight privado desta execução: `%LOCALAPPDATA%\SocialMEI-Privado\gows-restart-final-private.json`. Nenhuma política foi alterada na preparação. Esse escopo não inclui transferência para workspace60, workers, credenciais, mensagens ou mudanças de rede.
