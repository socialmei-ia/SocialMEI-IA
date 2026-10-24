# Instagram — proteção criptográfica dos tokens

Unidade posterior ao adaptador da PR104. Implementada e testada com material
sintético, **ainda sem armazenamento no banco, contas reais ou rotas públicas**.
Não configura OAuth nem permite ativar a Meta por variável de ambiente.

## Contrato

`TokenVault(keys=..., active_key_id=...)` exige keyring explícito de até16 chaves
AES de32 bytes e um identificador ativo. Sem chave padrão, chave derivada de
senha, chave do n8n reaproveitada, leitura de `.env` ou geração automática.

- `seal(token, TokenBinding(...))` retorna envelope versionado AES-256-GCM com
  nonce aleatório de12 bytes e tag de autenticação. Tokens limitados a16 KiB,
  ASCII sem espaços/controles, conforme o contrato de entrada do adaptador.
- `open(envelope, binding)` autentica antes de devolver o token. Formato/base64
  canônicos, versão, limites, nonce, chave e tag são verificados; falhas têm uma
  mensagem local única, sem token, ciphertext ou exceção criptográfica original.
- AAD vincula versão, identificador da chave, provedor Instagram, ID BIGINT positivo do negócio,
  UUID interno da conexão e ID externo da conta. Mover o ciphertext entre contas,
  conexões ou negócios falha, inclusive quando usam a mesma chave física.
- `repr` omite chaves e identidade. O token aberto continua um segredo em memória:
  não serializar/logar o retorno, keyring, stack locals ou binding como DTO público.

O binding precisa vir da sessão e de uma conexão autorizada carregada pelo
servidor; criptografia **não substitui autorização SQL**, constraints de workspace,
permissões, transação ou controle de concorrência. Um chamador que já controla a
chave e fornece deliberadamente o binding original pode abrir o ciphertext.

## Chaves, rotação e recuperação

Usar material aleatório de um gerenciador de segredos aprovado; o operador cadastra
privadamente, nunca pelo chat, Git, navegador ou n8n. O módulo aceita bytes já
obtidos por uma camada de configuração futura; não existem nomes de variáveis ou
procedimentos de produção ativos nesta entrega.

Nova gravação usa somente a chave ativa. Chaves antigas mantidas no keyring podem
ler envelopes anteriores. Retirar uma chave torna esses envelopes ilegíveis;
esta unidade não apaga/regrava tokens nem realiza rotação de dados automaticamente.
Antes de aposentar uma chave, testar migração/recuperação em banco isolado e manter
as cópias privadas aprovadas. Perder a chave exige reconectar as contas afetadas.

Backups futuros precisam preservar DB e referências/chaves sob controles separados.
Não afirmar recuperação apenas porque existe um dump criptografado. AES-GCM não
oferece expiração, revogação nem proteção contra replay do envelope: esses estados
precisam ser conferidos na conexão persistida, ainda não implementada.

## Verificação

```sh
python -m unittest discover -s python-service -p test_instagram_token_vault.py -v
```

12 testes focados, com keyrings descartáveis e nenhum serviço externo: roundtrip,
nonce aleatório, alteração de token/nonce, chave incorreta, dois negócios,
conexões/contas diferentes, metadado de chave autenticado, rotação/aposentadoria,
keyring copiado, limites e envelope malformado. Fixtures não são chaves utilizáveis
em produção. A primeira execução recusou a fixture por tamanho incorreto; foi
corrigida para32 bytes, sem relaxar o requisito do módulo.

Dependência declarada: `cryptography==50.0.2`, mesma versão instalada/testada no
ambiente de desenvolvimento. Referência primária:
[PyCA AESGCM](https://github.com/pyca/cryptography/blob/main/docs/hazmat/primitives/aead.rst).

## Ainda falta

Persistência exclusiva por conta/negócio, state Meta real durável e de uso único,
key provider privado, revogação/expiração transacional, gestão segura de refresh,
webhooks/ledger e outbox. Aplicação/migrations em ambiente real dependem de
aprovação própria. Nenhuma chave ou credencial real foi lida/criada/alterada.

Compatibilidade conferida: `socialmei.workspaces.id` usa BIGINT. Binding aceita inteiro positivo até2^63−1, recusa bool/string/UUID e preserva UUID somente para a conexão. Teste reproduzido antes da correção.
