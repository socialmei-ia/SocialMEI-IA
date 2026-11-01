# Instagram: Gate 9, recebimento real

Base instalada informada e confirmada por label da imagem da API:
`266e59b6a766c07f60c83b7b3053b33fc91cc135` (035). Não repetir deploy/migrations.

`tools/instagram-direct-proof.py` é um coletor somente leitura para executar no
host team, inclusive via entrada padrão do Python. Exige alvo e SHA completos;
interrompe se a imagem instalada divergir. Não instala arquivos, envia mensagens,
reproduz webhooks, altera flags ou modifica n8n/Meta. A credencial permanece no
processo privado da API. Não imprime mensagens, contatos ou IDs do provedor.

```sh
python3 tools/instagram-direct-proof.py --target team \
  --expected-sha 266e59b6a766c07f60c83b7b3053b33fc91cc135 \
  --check-subscription
```

Sem `--check-subscription`, consulta somente a imagem e o banco em transação
somente leitura. Com essa opção, realiza um GET da inscrição da conta na Meta,
sem redirects, proxy, paginação automática ou token na URL. Isso verifica a
inscrição da conta; não verifica o callback do aplicativo nem sua revisão na Meta.
Use `--meta-app-id ID_PUBLICO` somente após conferir o ID do aplicativo pai no
painel Meta. O ID do cliente OAuth Instagram pode ser diferente; sem essa
confirmação, o coletor não certifica a identidade do aplicativo inscrito.

## Bloqueio observado em 01/11/2026

Consulta SSH somente leitura: imagem da API corresponde à SHA acima; ingresso
habilitado, envio do dashboard desligado, uma conexão válida com permissões de
mensagens; zero eventos de ingresso e zero mensagens Instagram na Caixa. GET
`/{conta}/subscribed_apps` retornou um aplicativo com `messages`, cujo ID difere do
cliente OAuth Instagram. A identidade do aplicativo pai e o callback ainda não
foram confirmados. Isso **não comprova falta de inscrição**; não reinscrever por
tentativa. A conferência no navegador não foi possível nesta sessão porque o host
de acesso ao navegador estava indisponível.
Feed real e deploy anteriores permanecem evidências separadas de Direct.

### Mudança operacional proposta, ainda não autorizada

Somente se a conferência da identidade comprovar ausência de inscrição/campo.
Alvo: única conta profissional conectada ao workspace `team`/1 e aplicativo pai
verificado no painel Meta. Após autorização específica, repetir GET imediatamente
antes da mudança, preservar campos previamente inscritos e solicitar somente
`messages` adicional por POST `https://graph.instagram.com/{versão}/{conta}/subscribed_apps`.
Token via header privado; não copiar a credencial nem imprimir resposta bruta.
Não alterar o workflow `LHlqroY2xzvpYAmD`, flags de envio ou publicações.

Verificação: novo GET confirma aplicativo e campo `messages`. Rollback limitado
à inscrição alterada: restaurar campos anteriores; se não existia inscrição,
remover somente a inscrição deste aplicativo, sob autorização de rollback.
Não restaurar banco ou recriar containers para essa mudança.

## Teste manual, somente após autorização do remetente e da operação

1. Confirmar o callback/assinatura e inscrição na Meta. O n8n existente pode
   responder automaticamente; informar isso ao responsável antes de testar.
2. Gerar um marcador novo `SOCIALMEI-G9-` com 16 caracteres hexadecimais maiúsculos.
   Executar o coletor com `--marker MARCADOR`: todas as contagens devem ser zero.
3. A conta autorizada envia **uma** mensagem com esse texto exato, manualmente.
4. Repetir a consulta: `one_persisted_inbound_message` exige uma mensagem, um evento
   processado, uma conversa e vínculo da conta/workspace, sem cópia em outro negócio.
5. Abrir Caixa → Instagram no site com sessão do negócio e conferir a mensagem.
   Registrar separadamente se foi observado pelo operador ou pelo agente.

Um marcador encontrado sem baseline zero não prova recebimento novo. Esta consulta
não prova a assinatura HTTP original, callback do aplicativo, ausência de todos os
tipos de duplicação ou renderização no navegador. Flags dessas evidências permanecem
falsas na saída. Testes de assinatura/replay com fixtures são evidência automatizada
separada, nunca homologação real. Não habilitar respostas/publicações para passar Gate 9.
