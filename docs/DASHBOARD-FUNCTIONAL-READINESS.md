# Atualização funcional do dashboard

Base: `feat/isolated-preview` em `ecaa4bdd6746e7ebebd719513d0a31dcdd42fcc1`, descendente das PRs #83 e #89. A branch `feat/dashboard-functional-readiness` preserva essa ancestralidade. Não é atualização da main ou implantação em produção.

## Funcionalidades

- Divulgação acessível diretamente na barra lateral, inclusive no celular. Abas Criar conteúdo, Rascunhos, Agenda e Conexões.
- Agenda com filtros por estado e dia no fuso escolhido, edição e cancelamento de simulações; estados locais e do servidor identificados. Resumo de próximas simulações na página inicial.
- Preparação de Instagram por negócio: usuário público, tipo de conta informado, situação do aplicativo Meta e participantes de teste. Somente responsável/admin salva; outros acessos leem. Sem senha, token, OAuth ou ativação. O servidor sempre informa que receber, enviar e publicar estão indisponíveis.
- Acompanhamento comercial persistido em Oportunidades. Interesse Em análise/Frio/Morno/Quente separado do resultado Em andamento/Venda realizada/Não avançou. Encerradas saem dos contadores de interesse. Falta de resposta não encerra automaticamente.
- Motivos de perda, observação, reabertura com motivo e histórico com autor/revisão. Novas negociações do mesmo cliente podem ser registros independentes.
- Vínculo explícito com venda existente do mesmo cliente e negócio, sem duplicar venda, registrar pagamento ou movimentar estoque. Venda cancelada permanece identificada para conferência. Escritas têm autorização, proteção CSRF, revisão esperada e identidade de operação para repetição segura.

A análise heurística demonstrativa permanece separada dos registros comerciais do servidor. Contadores se referem aos até 100 registros recentes carregados. A conta de Instagram que recebe as mensagens representa o negócio; as contas dos participantes que enviam mensagens representam clientes de teste.

## Conferir localmente

No PowerShell, dentro da pasta do repositório, execute `npm.cmd run preview -- up`. Usar `npm.cmd` evita o bloqueio de execução do arquivo `npm.ps1`; não exige mudar a política do Windows.

Abra `https://127.0.0.1:8443`, aceite o certificado local se necessário e cadastre uma conta fictícia. Use somente dados de teste. O preview inicia frontend, FastAPI e PostgreSQL descartável isolados; não inicia n8n/WAHA e não usa o banco de produção. As migrations 001–017 pertencem a esse banco de preview.

1. Cadastre um cliente fictício em Clientes.
2. Em Oportunidades, crie uma negociação Quente, encerre como Não avançou, informe o motivo e confira os filtros. Reabra com motivo; consulte o histórico e recarregue a página.
3. Em Divulgação, crie um rascunho, revise mídia/legenda e abra Agenda para agendar, editar ou cancelar uma simulação. Nada é publicado.
4. Em Conexões, salve as informações públicas conhecidas da conta. Os bloqueadores reais continuam visíveis mesmo com todos os campos preenchidos.

`npm.cmd run preview -- status` consulta a saúde. `npm.cmd run preview -- down` encerra o preview preservando o volume de teste. Não apagar volumes como tentativa de corrigir migrations. Mais detalhes em [LOCAL-PREVIEW.md](LOCAL-PREVIEW.md).

## Dependências externas

Instagram real ainda precisa da conta profissional e autorização oficial com permissões e webhook homologados. WhatsApp aguarda número/provedor de teste. Imagens, legendas e sentimento da equipe precisam de contratos e conferência autenticada da instância n8n; veja [N8N-CAPABILITY-MATRIX.md](N8N-CAPABILITY-MATRIX.md). Upload de mídia, modelos locais e simulações disponíveis não comprovam integração com IA ou Meta.

A atualização visual ampla fica para a próxima etapa. Nenhum recurso desta entrega autoriza publicação automática, envio automático, deploy AWS, alteração do Caddy existente, migrations em banco produtivo ou mudanças no n8n/WAHA vivo.
