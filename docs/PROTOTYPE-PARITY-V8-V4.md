# Funcionalidade dos protótipos V8 e V4 na PR #100

## Motivação

Os arquivos originais `SocialMEI.IA — Oportunidades V8.html` e `socialmei-divulgacao-v4.html` são protótipos independentes com chaves globais de localStorage, clientes/rascunhos simulados e campos que não pertencem à API real do CRM. A primeira integração da PR #100 cobriu somente aparência e alguns componentes. Esta correção acrescenta funções, sempre preservando o backend, a autenticação e a separação de negócios.

## Oportunidades V8

- **API real preservada:** os registros, suas revisões, alterações Frio/Morno/Quente, encerramento, reabertura, vinculação de vendas e histórico continuam usando `SocialMEIOpportunityLifecycle`; sem lista fictícia substituta e sem chamadas não autorizadas.
- **Adicionado:** busca, ordenação, retorno/valor na criação, anotação local, retorno +1/+3/+7 dias, lista de retornos vencidos, copiar pendências, Semana (7 dias, Depois, Sem data), drag-and-drop de interesse e retorno; cada cartão também mantém controles de seleção e teclado.
- **Limitação explícita:** valor estimado, nota e retorno usam `localStorage` por escopo `usuario|negocio|scope`. Não são persistidos no PostgreSQL, não são sincronizados em outras máquinas, não afetam financeiro/vendas e não aparecem no histórico autenticado. Nem o valor nem a data agendada são inventados ou carregados da API.
- **Sem dados fictícios novos:** criar uma oportunidade exige cliente cadastrado e conta autenticada, como antes. O protótipo standalone possui um comando de restaurar seus próprios clientes fictícios, mas o CRM não pode oferecer uma ação destrutiva equivalente sobre clientes reais.
- **Pendentes para paridade persistente:** campos valor/retorno no backend com migrations e testes de autorização; desfazer movimentações autenticadas; comandos globais compatíveis com a navegação atual; auditoria de acessibilidade do drag-and-drop em dispositivos reais.

## Divulgação V4

- **Preservado:** editor oficial, prévia Story/Feed/Reel, validação de mídia, rascunhos por negócio, ação de salvar/duplicar/excluir, preparação e agenda compartilhada fictícia, conexões pendentes; nenhuma publicação nem envio real.
- **Adicionado:** gerador de três legendas por regras locais com tema, serviço, objetivo e tom; confirmação antes de substituir texto; tela cheia, Feed claro, área segura, zoom/posição do enquadramento, descrição alternativa da prévia, cópia de publicação completa; busca/filtro/ordenação dos rascunhos; backup JSON exportável/importável em lote para o negócio atual.
- **Importação segura:** aceita tanto o backup JSON da Divulgação V4 standalone (`app: socialmei-divulgacao`, `v: 4`) quanto o backup nativo; formato versionado, limite 256 KB, validação de todos os rascunhos, ignorar IDs e URLs fornecidos pelo arquivo, novos IDs gerados no escopo corrente, commit atômico com limite máximo de 40. Mídias originais nunca acompanham backups e devem ser selecionadas de novo.
- **Pendentes para paridade completa:** simulação de uma semana inteira a partir de um único clique (a preparação compartilhada existente tem aprovações, idempotência e restrições próprias e não deve ser contornada); mídia posicionada e zoom salvos permanentemente como uma edição (hoje apenas prévia); controle completo de branding da conta; inspeção visual da tela cheia com leitor de tela.

## Teste local no Windows (somente depois de o CI passar)

Na cópia isolada `Downloads\SocialMEI-teste`, branch `feat/native-opportunities-v8-content-v4`:

```powershell
cd "$env:USERPROFILE\Downloads\SocialMEI-teste"
git status --short
git pull --ff-only
npm.cmd run preview -- up
```

Verifique `https://127.0.0.1:8443`, com conta **fictícia** e banco de testes. Utilize `Ctrl+Shift+R` para atualizar o cache. As alterações de frontend são montadas do checkout; a API e seu banco continuam isolados no projeto Docker `socialmei-preview`, sem tocar a AWS.

Não usar `docker compose down -v`, não executar migrations/integrações na AWS e não colocar senhas/chaves reais. O CI prova apenas o ambiente automatizado; a homologação humana ainda é necessária.
