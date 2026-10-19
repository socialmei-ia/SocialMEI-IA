# Divulgação — estúdio nativo de preparação

Acesso: aplicação oficial → **Ferramentas → Divulgação · preparar conteúdo**.
A navegação principal, contas, onboarding e Relatórios permanecem no mesmo app.

## Funciona nesta entrega

- Story (9:16), Feed (4:5) e Reel (9:16), com seletor acessível por teclado.
- Título, legenda, chamada e hashtags opcionais; prévia dinâmica com nome do
  negócio quando disponível no perfil existente. Nenhum preço ou oferta é gerado.
- Arquivo local: JPG/PNG/WebP até 10 MB; MP4/WebM até 50 MB. Feed aceita imagem;
  Reel aceita vídeo; Story aceita ambos. MIME, limite e cabeçalho são verificados;
  falha de decodificação/codec informa indisponibilidade de prévia.
- Rascunhos: salvar, editar, duplicar e excluir com confirmação; cancelamento de
  mudanças não salvas, cópia de legenda e download real de texto UTF-8.
- Prévia de vídeo com controles, sem autoplay; URLs blob revogadas na troca de
  mídia, saída da tela, descarte e troca de identidade. Sem upload para servidor.
- Duas colunas no desktop e sequência editor/prévia no celular; claro/escuro,
  movimento reduzido, foco e Escape nos modais nativos.

## Persistência e identidade

Texto e **metadados** de arquivo usam `socialmei-content-drafts-v1:<escopo>` no
localStorage. O escopo reutiliza a identidade do perfil comercial: modo local
por identidade de demonstração; conta conectada por usuário/workspace e sessão
vinculada. Falta de escopo bloqueia gravação. Máximo de 40 rascunhos.

O envelope valida versão, escopo e conteúdo antes da leitura/gravação. Dados
inválidos ou quota/armazenamento bloqueado não geram sucesso nem sobrescrevem
rascunhos. Troca de identidade limpa editor, mídia e confirmações pendentes.

**Não há sincronização remota.** Arquivos não são salvos: reanexar mídia ao
reabrir. Referência de nome/tipo/tamanho não comprova que o arquivo ainda esteja
no dispositivo. Downloads contêm apenas texto; a mídia original é separada.
Limpar o navegador pode apagar rascunhos. A prévia não renderiza títulos/legendas
sobre a imagem ou vídeo: esses campos não são incorporados à mídia.

## Publicação e integração

Publicação está desabilitada com explicação. Não há envio, conexão Meta, n8n,
IA externa, calendário ou publicação agendada. A investigação estática e o
contrato futuro constam em [INSTAGRAM-PUBLISH-READINESS.md](INSTAGRAM-PUBLISH-READINESS.md).
O workflow histórico não tem export de publicação disponível; exports de Direct
não substituem esse contrato. Nenhum runtime foi acessado.

## Validação

Testes do repositório: modelo de rascunhos, CRUD, atualização/duplicação,
limites/validação de mídia, corrupção/quota, isolamento e ausência de URLs/blobs
persistidos. Navegador: três formatos em 320/390/768/1024/1280/1440 px, nos dois
temas; imagem PNG e vídeo WebM gerados para teste; CRUD, copiar/falha, exportação,
confirmar/Escape, teclado, movimento reduzido, XSS, quota e troca de workspace
com API simulada. Regressão global mantida, incluindo Relatórios V2/V2.1.

Capturas e resultados: [mega-update-evidence](mega-update-evidence/).
Ver checks da PR para o resultado do HEAD final. Não houve merge/deploy.
