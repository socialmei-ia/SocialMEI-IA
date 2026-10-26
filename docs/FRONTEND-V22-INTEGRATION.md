# Frontend V22 — integração à candidata #111

Recebido em 26/10/2026: `SocialMEI-Frontend-v22.zip`, SHA256 `2f7193bdef4dc482f60344085f334e54f2060f9f06a3406dd90232af5c977313`. 113 entradas, 4,65 MB descompactados. Inspeção de caminhos/duplicatas/symlinks/tamanho antes de extrair. Nenhuma credencial ou configuração privada foi importada.

## Fidelidade e entrada oficial

`frontend/socialmei-app.html` agora usa a composição original V22. `frontend/entrada.html` é a landing/cadastro/onboarding do mesmo pacote. CSS, fonte, assets e scripts de movimento do proprietário preservados; hashes e igualdade dos blocos CSS são testados. `frontend/reference/Frontend-V22-original.html` é referência imutável, não uma segunda aplicação de apresentação.

O pacote original já incorpora Oportunidades e Divulgação em iframes same-origin em `telas/`. Essa composição foi preservada por solicitação do proprietário; não foram criados hubs ou iframes de demonstração adicionais. Os scripts funcionais adaptam autenticação/persistência, mantendo renderização, gráficos, efeitos e handlers visuais nativos. `hero-wall.js` e `sections-anim.js` permanecem byte a byte iguais ao ZIP. Licença Inter incluída.

No modo remoto, o bootstrap só executa o shell após identificar a sessão. Visitantes seguem para a landing; links internos protegidos levam ao login. Não há flash de dados fictícios antes de carregar a conta. Quando o gateway serve o aplicativo em `/`, a sessão autenticada segue para `/frontend/socialmei-app.html`, preservando query/hash e os caminhos relativos das telas internas; visitantes continuam na landing. O preview HTTPS testa ambos os acessos pela raiz. O modo local conserva o exemplo original, sem chamadas reais a canais.

## Conexões funcionais

- Cadastro/login: APIs existentes; política aberto/convite, senha de 8–128, sem salvar senha ou criar sessão por localStorage. Recuperação usa código/API real e mostra indisponibilidade se SMTP/worker não estiverem configurados.
- Onboarding: perfil comercial com revisão/CAS, edição do nome/telefone, preservação de especialidades/capacidades anteriores. Falhas preservam respostas; dados extras sem contrato ficam somente no cache escopado, sem alegar sincronização.
- Gestão: clientes, produtos/serviços, vendas e financeiro carregados da conta. Cadastro/edição de cliente e catálogo; criação de venda pendente com preço real, pagamento e lançamento quitado; exclusão financeira pelo contrato existente. Formulários só confirmam após resposta da API; falha de atualização após gravação confirmada não permite repetir POST inadvertidamente.
- Produtos e serviços: serviços não exibem estoque físico; estoque é validado pelo backend. Sugestões não viram cadastros automaticamente.
- Conta: nome e nome/telefone do negócio usam persistência existente. Botão “Sair dos outros aparelhos” exige senha atual e chama a API de revogação.
- Preferência de tema: API autenticada com revisão, preservando as demais preferências. Marca/modo calmo e opções não mapeadas continuam locais por identidade.
- Avisos: somente pendências respaldadas pelos registros da conta. Dicas sintéticas não viram notificações; sem contrato de leitura, conversas não recebem marcação automática de “não lida”.
- Caixa: lê conversas autorizadas pela API existente quando a capacidade estiver disponível; vazia quando não há canais/dados. Não vincula cliente e conversa por nome nem inventa vínculos. Envio permanece bloqueado; mensagens reais não recebem respostas fictícias.
- Oportunidades: clientes do negócio, criação, interesse, valor, retorno, nota, contato, fechamento/reabertura e histórico usam API/revisões. Justificativa humana é preservada. Desfazer edição usa nova operação CAS; criar/excluir não tem undo remoto disponível e não simula remoção do servidor. Nova solicitação/erro remoto não grava em chave local compartilhada.
- Divulgação: editor, mídia/zoom, legendas locais, rascunhos e agenda simulada mantêm o funcionamento original. Armazenamento é por usuário/negócio; não apresenta publicação real ou sincronização de mídia. Instagram/n8n seguem dependentes de homologação.
- Relatórios: gráficos/contadores nativos alimentados por vendas válidas e financeiro quitado, períodos relativos à data atual no modo remoto. Sem somar vendas e receitas como uma só métrica. CSV neutraliza fórmulas e respeita o filtro. Protótipo local preserva os exemplos do pacote.

`X-SocialMEI-Identity` é um guard opcional adicional no backend: se o cookie mudou para outra identidade, rejeita 409 antes de consultar/gravar. Não substitui cookie, Origin, CSRF ou permissões. Chaves V22 `smei-*`/`smei4_*` ficam escopadas por usuário/workspace e não leem dados genéricos de outro usuário. Nenhum token de provedor é enviado ao frontend.

## Limites explícitos

- Categoria/descrição do produto e troca segura de e-mail não têm contrato disponível: controles preservados sem inventar gravação. Campos incompatíveis são somente leitura/desabilitados, com informação de indisponibilidade.
- Cidade, Instagram público, canais/foco adicionais do onboarding não têm todos os campos no perfil canônico; permanecem no cache local da identidade. O perfil suportado é compartilhado; esses extras não são anunciados como sincronizados.
- Vendas em rascunho/canceladas não entram nos indicadores de vendas ativas; financeiro mostra movimentações quitadas. Não há novo fluxo visual para quitar lançamentos abertos herdados.
- O V22 recebido não contém os controles de PDF/histórico da antiga interface de Relatórios. O código legado foi preservado, mas esses controles não foram acrescentados ao layout contra a solicitação de fidelidade. Exportação CSV nativa foi conectada e protegida.
- Agenda operacional, equipe, MFA e envio de respostas sem contrato permanecem indisponíveis ou explicitamente simulados. Não há criação de acesso, publicação ou segurança fictícia.
- Rotinas, sugestão local de IA e mídia do editor não executam workflows reais. Não há Gmail/Meta/WAHA configurados nem worker instalado na AWS nesta entrega.

## Testes e evidência

A suíte de layout foi adaptada para a nova árvore DOM: testes que exigiam IDs do HTML anterior não são apresentados como prova do V22. Scripts antigos de browser permanecem no repositório para referência; o CI agora executa a matriz V22 e o preview real. Testes de stores, motores, backend, permissões, migrations e recuperação continuam executados.

- Node: 334 testes aprovados, incluindo fonte original/hashes/CSS e contratos estruturais novos.
- Backend: 426 testes aprovados em PostgreSQL descartável, incluindo rejeição de identidade antiga após troca de cookie.
- Browser V22: 286 estados em 11 larguras/2 temas; entrada em 5 casos, CSV, isolamento, escrita confirmada seguida de erro de refresh, teclado, toque e movimento reduzido.
- Preview HTTPS real: duas contas, cliente/produto/venda/oportunidade, persistência após reload e isolamento. Capturas em 1440/768/390 claro/escuro, dentro da navegação oficial.
- Laboratório Instagram isolado: OAuth/CSRF, eventos assinados, Caixa V22, manifesto real do editor e fila fake com aprovação, sem transporte externo. Não é conexão Meta real.

Capturas: `test-results/v22/` e `test-results/v22-integrated/`. As capturas estabilizam as animações apenas durante a geração da imagem; o aplicativo mantém os efeitos originais. Uma seleção está em `docs/evidence/v22/`. CI deve ser conferido no HEAD final; testes locais não substituem sua conclusão.

## Publicação

Nenhum merge ou deploy. A candidata exige API compatível e migrations 001–026, configuração pública remota correta, backup/rollback e preservação dos hotfixes da AWS. Não substituir arquivos privados de configuração pelo `config.js` local do ZIP. O preview usado nesta rodada é descartável e separado; ajustes de CA/proxy da sessão ficaram fora do repositório. O endereço AWS não foi alterado.
