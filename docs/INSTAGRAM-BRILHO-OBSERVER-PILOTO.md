# Observer Brilho60 — operação pendente de aprovação

Plano privado congelado: `30ab1ec0c97d34c651102daf9a74e3597c1ac09c3cdfa6d3e9ea748e9a6957c8`.
Localizador: `SocialMEI-Privado/instagram-brilho-pilot-latest.private.json`.

- Impacto: carregar a imagem original verificada e iniciar **somente brilho-observer**, sem dependências, build ou pull. Bella61 permanece parada.
- Imagem: `sha256:fad45c4a9f644f51b694dd9799cea857bcb1eb77caf1bee02554a530a0d48636`, fonte `331cc1fce37133587235ff3672c6f5b8119e241b`.
- Arquivo OCI: 81.447.936 bytes; SHA-256 `ce4a9d96d4f55d74dd94f92a3bb503771f39d4e2426a46ba1a7eda19b7c7676f`. Índice, configuração executável, camadas e atestação verificados; sem rebuild. Ainda não carregado na AWS.
- Memória: teto 72 MiB, swap desabilitada, CPU 0,25; orçamento total 520 MiB com envelope do backup e reserva. Leitura da AWS nesta preparação: 573 MiB disponíveis. Exigir leitura fresca >= 520 MiB, disco livre >= 512 MiB e nenhum ciclo de backup em andamento antes da carga.
- Dados: consulta somente leitura da base efetiva, filtro workspace60, cutoff UTC explícito e volume exclusivo de checkpoint. Não confirma eventos, não consome jobs, não cria CRM nem dispara respostas. Flags de envio e menu automático falsas, sem credenciais Meta/SMTP/n8n. Nenhum OAuth ou vínculo de canal será alterado.
- Exclusividade: nenhuma instância declarada para workspace60 encontrada no inventário atual. Revalidar antes do início e obter lease exclusivo no PostgreSQL; falha no lease bloqueia o worker. O observer não disputa as filas dos respondedores existentes.
- Antes de iniciar: conferir plano, hashes dos scripts/Compose, imagem, CA verify-full e identidade do banco da API. Renderizar o Compose privado; iniciar apenas `brilho-observer` com `--no-deps --no-build --pull never`. Qualquer divergência interrompe a operação.
- Monitoramento: saúde pronta em até 90 segundos; amostras a cada 15 segundos por 5 minutos e nova verificação após 30 minutos. Conferir RSS/cgroup, ausência de OOM/reinício repetido, margem de memória, checkpoint60 e saúde/identidade dos serviços anteriores. Sem teste de mensagem externa.
- Rollback: parar **somente o ID novo registrado do Brilho**, preservando seu volume e a imagem para diagnóstico. Não executar `compose down`, não remover volumes nem reiniciar os serviços existentes. Falha crítica durante a observação inicial aciona esse rollback.

`tools/instagram-observer-pilot.py` é somente leitura e não contém comando de ativação. A aprovação deste piloto não autoriza Bella, envio externo, Meta, migrations, transferência de canais ou publicação da API. Observer saudável sem eventos não comprova Instagram Direct homologado.
