# Workers Instagram — preparação para Brilho60 e Bella61

O worker existente continua utilizando os adaptadores, OAuth, eventos e recibos persistentes da API. Cada processo atende um único `SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACE_ID`; a lista autorizada `SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACES` é independente. Não iniciar processos novos com o banco Prisma histórico.

## Controle implementado

`instagram_worker_lease.worker_lease` exige `SOCIALMEI_INSTAGRAM_WORKER_DATABASE_NAME`, comparado a `current_database()` antes de processar mensagens. O operador deve conferir o endereço privado e database de `DATABASE_URL` contra a configuração efetiva da API; nome coincidente sozinho não comprova o mesmo servidor. Não colocar a URL, senha ou tokens no plano público.

Uma conexão dedicada mantém advisory lock por workspace durante toda a execução. Outro worker Python no mesmo PostgreSQL/workspace é recusado, inclusive com volume local diferente. A perda da conexão interrompe o processamento antes da próxima resposta. Workspaces diferentes podem manter locks simultaneamente. O outbox persistente e seus controles de resultado incerto continuam necessários durante falhas de rede. A trava não coordena um n8n que não utiliza esse contrato.

O lançamento deve usar a imagem compatível com a API, o mesmo PostgreSQL privado e volumes de estado distintos para60/61. O arquivo de estado contém o corte inicial; não reutilizar o volume do workspace1. Manter desligado o worker histórico até o plano de substituição ser aprovado. A configuração nova é obrigatória para o código novo; o worker instalado não foi reiniciado nem modificado.

## Dependências operacionais não concluídas

1. Aprovar e realizar OAuth individual das contas profissionais corretas, verificando identidade, escopos e assinatura Meta. O aplicativo compartilhado não substitui os vínculos separados.
2. Conferir qual sender n8n atende cada identidade. Só autorizar `SOCIALMEI_INSTAGRAM_DIRECT_OWNER=dashboard` e envio depois de eliminar a concorrência daquela conta, preservando os demais workflows.
3. Preparar configuração privada, cortes temporais, backup e rollback do worker antigo. Não copiar seus tokens/URL Prisma por conveniência. Uma falha de inicialização deve permanecer bloqueada.
4. Com aprovação própria, ativar um processo por workspace e homologar Direct recebido, evento persistido, conversa no negócio correto e resposta entregue uma única vez. Brilho deve alcançar serviços/Agenda; Bella, catálogo/interesse comercial. Testar handoff humano e recuperação sem repetir envios incertos.

Os quatro testes de `test_instagram_worker_lease.py` validam nome de banco, exclusão mútua, separação por workspace e falha da conexão sem Meta real. Essa evidência não comprova OAuth, recebimento externo, entrega ou exclusividade com n8n.
