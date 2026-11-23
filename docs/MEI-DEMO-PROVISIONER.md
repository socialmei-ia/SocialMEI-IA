# Provisionamento do MEI fictício

O provisionador usa as APIs existentes e uma sessão normal do proprietário. Não
cria contas, verifica e-mail, muda permissões ou transfere canais. Brilho Limpeza é
o cenário de serviços; Bella Store é o cenário de catálogo e estoque. O frontend
e o gateway premium permanecem intactos.

Antes de aplicar, confira no inventário real se o negócio e o proprietário já
existem. Se faltarem, use o cadastro e a verificação de e-mail normais; não crie
outro negócio com o mesmo nome. O alvo deve ser uma conta independente, sem papel
de administrador da plataforma. A ferramenta recusa o workspace `team`, outros
nomes, conta divergente ou verificação pendente.

O inventário somente leitura de 19/11 localizou o negócio existente
`Brilho&Limpeza Service`, workspace 60, proprietário individual 33. O cenário
`Brilho Limpeza` aceita esse nome existente por meio de `expectedBusinessName`,
comparado exatamente com a sessão. O nome não é alterado. Não há cadastro novo
implícito. Antes de aplicar, reconfirme que esse inventário ainda corresponde ao
alvo autorizado; a ferramenta não conclui que canais estão vinculados por nome.

Copie `tools/mei-demo-target.example.json` para um arquivo privado, preencha a
origem HTTPS e os IDs reais autorizados. Os zeros do exemplo impedem execução
acidental. Fixe `anchorDate` uma única vez: ela ancora os históricos e deve ser
preservada em todas as reexecuções. Alterá-la depois provoca conflito nas
operações existentes em vez de criar registros novos.

Antes da primeira aplicação, `pendingStartDate` pode fixar uma data separada
para a primeira reserva pendente; a segunda fica no dia seguinte. O manifesto
Brilho preserva `anchorDate=2026-11-19`, históricos em17/18 e fixa as pendentes
em23/24 de novembro com `pendingStartDate=2026-11-23`. Não há avanço automático
pelo relógio. Preserve os dois campos nas reexecuções: os IDs não mudam e tentar
alterar a data de uma operação já persistida causa409, sem mover reservas.
Manifestos antigos sem esse campo mantêm o comportamento anterior.

Diagnóstico de20/11: o arquivo privado existe e é válido, porém seu e-mail
normalizado não corresponde ao usuário33. A credencial33 está ativa e possui
papel owner no workspace60. Não foi testada a senha, repetido login ou efetuado
reset. Corrigir a identidade no arquivo privado antes de tentar novamente.

Prepare separadamente um arquivo privado de conta com os campos `email` e
`senha`. Se o gateway exigir Basic, acrescente `basic` no formato
`usuário:senha`. Nunca coloque esse arquivo no Git nem passe segredos na linha de
comando. Restrinja as permissões dos arquivos privados no sistema operacional.
Nenhuma credencial é gerada ou impressa pela ferramenta.

```powershell
node tools/provision-mei-demo.mjs --target C:/privado/alvo.json --account-file C:/privado/conta.json --inventory C:/privado/inventario.json
```

Este é o modo padrão de inspeção. Consulta sessão, perfil, catálogo e prévias de
importação. Os dois POSTs de prévia apenas leem os mapeamentos, conforme o
contrato atual da API; nenhum dado de negócio é gravado. O login normal cria uma
sessão autenticada. O inventário informa alvo, plano, registros e conclusão;
nunca contém senhas, cookies ou respostas com dados privados.

Somente depois da autorização específica de escrita no ambiente real, backup e
revisão do alvo, execute o mesmo comando com `--apply`. Não é necessário publicar
uma imagem ou aplicar migration para usar o provisionador.

A versão inicial inclui quatro clientes sem telefone/CNPJ/Instagram, e-mails
reservados `example.test`, três serviços ou produtos, duas vendas, três lançamentos,
duas oportunidades e dois registros internos manuais de atendimento. Brilho
inclui dois recursos e quatro agendamentos: concluído, cancelado e dois pendentes.
Todos os registros artificiais têm identificação explícita. Os lançamentos
financeiros representam as duas vendas e o custo de material da venda paga.

O perfil e os horários de agendamento existentes são preservados. Em um perfil
vazio, grava o segmento e as capacidades do cenário; em política vazia, grava
horários úteis de 08h a 18h com agendamento pelos canais **desabilitado**. O
provisionador não habilita políticas, não cria eventos recebidos, não insere
conversas sintéticas e não envia mensagens.

Clientes/produtos usam origem de importação estável; recursos, agendamentos,
vendas, finanças, oportunidades e lembretes usam IDs de operação estáveis por
workspace. Cada escrita revalida a identidade e envia o cabeçalho de identidade
do contrato existente. Conflitos e cadastros de mesmo nome sem origem conhecida
interrompem a execução; nenhum registro é adotado por nome nem apagado. A sessão
não é trocada automaticamente.

Uma falha pode deixar operações anteriores concluídas. O inventário é salvo
após cada resposta confirmada e fica `complete: false` até a leitura final de
relatórios. Uma resposta perdida pode ter sido persistida sem aparecer nesse
arquivo; repetir com o mesmo manifesto recupera a operação pelo contrato de
idempotência. Não troque IDs, origem, data ou conteúdo para contornar um 409.
O inventário não é backup nem autoriza limpeza automática.

Para professor, o papel existente `report_viewer` permite relatórios; o papel
`member` atende a equipe operacional. Conceda esses acessos pelo fluxo existente
de membros, sob autorização própria. Vínculos WhatsApp e Meta exigem contas e
consentimentos reais autorizados por workspace: nenhum vínculo é simulado aqui.

Validação isolada:

```powershell
node --test tests/provision-mei-demo.test.cjs
```

Os testes usam um adaptador em memória para provar repetição, recuperação de
resposta perdida, recusa de identidade divergente e ausência de escrita na prévia.
O adaptador HTTP também tem teste com `Response` nativo para cookies, CSRF e
identidade. O ensaio integrado está em `tests/provision-mei-demo-integration.mjs`:
usa as rotas FastAPI reais por `TestClient`, dois cadastros sintéticos e PostgreSQL
descartável. Compara contagens e hashes dos registros após recuperação/repetição,
confere estoque/status e recusa escrita com identidade de outro workspace.

Esse ensaio exige `SOCIALMEI_DEMO_DISPOSABLE_TESTS=1`, `TEST_DATABASE_URL` apontando
exclusivamente para `localhost:55491/socialmei_demo_test` ou
`127.0.0.1:55491/socialmei_demo_test`, schema previamente instalado e dependências
Python do projeto. `MEI_DEMO_TEST_PYTHON` permite selecionar a venv de testes.
Execute `node tests/provision-mei-demo-integration.mjs` somente nessa base. O
ensaio não instala migrations nem limpa tabelas, mas cria dados sintéticos no
banco descartável. Não é homologação do ambiente real. Nunca aponte fixtures de
testes para o banco de produção.
