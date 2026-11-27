# Consolidação de produção — 27/11/2026

O manifesto em `deploy/production-overlay/20261127/manifest.json` registra a imagem base e o SHA-256 dos arquivos efetivos alterados em cada função. As variantes de API principal, API do menu, worker WhatsApp e edge têm destinos distintos. A imagem Instagram inspecionada não apresentou alterações Python na camada do container e ficou registrada pelo ID.

`python tools/build-production-overlay.py` verifica os bytes. Com a imagem base original carregada localmente, `python tools/build-production-overlay.py --build api` constrói uma camada offline. Use `--build gateway`, `--build menu`, `--build worker` ou `--build edge` para os componentes correspondentes. Guarde as imagens base por ID antes de limpar o cache. Um bind ativo prevalece sobre a imagem construída. Para publicar, confira cada bind com o manifesto e preserve os arquivos privados que o runtime usa.

O app versionado incorpora o frontend servido na AWS. Os arquivos identificados de Agenda, Relatórios e Caixa v7.9.5 coincidem byte a byte com o pacote disponível. O Hero aprovado permanece na imagem base capturada. O manifesto omite a configuração privada do frontend e as credenciais do runtime.

O ledger produtivo registra a migration 041. A cadeia SQL versionada foi preservada. O ledger comprova o registro da migration e não certifica a equivalência de todo o schema instalado. Antes da próxima release, compare a estrutura efetiva com uma restauração descartável e ensaie a recriação com os mounts e aliases reais.

Os overlays reproduzem o delta de arquivos observado sobre as imagens fixadas. A promoção exige validar as imagens construídas, as configurações privadas por serviço e os fluxos reais. Para rollback, preserve a imagem, configuração e mounts anteriores de cada componente. Pare qualquer remetente novo antes de restaurar o anterior e mantenha o ledger e os journals de envio.
