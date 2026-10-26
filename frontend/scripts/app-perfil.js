/* SocialMEI.IA · liga a porta de entrada (entrada.html) ao app v14.
   - Lê o perfil demonstrativo salvo no navegador (smei-perfil) e aplica nome, e-mail,
     negócio e área no app. Se não houver perfil, o app continua com os dados de exemplo.
   - As telas antigas #/entrar e #/cadastro agora levam para a porta de entrada.
   Carregado depois do script principal de socialmei-app.html. */
(function () {
  'use strict';
  if (typeof S === 'undefined' || typeof render !== 'function') return;
  try {
    var p = JSON.parse(localStorage.getItem('smei-perfil') || 'null');
    if (p && typeof p === 'object') {
      if (p.nome) S.user.nome = String(p.nome).trim().split(/\s+/)[0];
      if (p.email) S.user.email = String(p.email);
      if (p.negocio) S.biz.nome = String(p.negocio);
      if (p.area) S.biz.seg = String(p.area);
      if (p.email) S.biz.email = String(p.email);
      if (p.tel) S.biz.tel = String(p.tel);
    }
  } catch (e) {}
  var _render = render;
  render = function () {
    var r = (H.slice(1).split('/')[0] || '');
    if (r === 'entrar' || r === 'cadastro') {
      if (r === 'entrar') { try { localStorage.removeItem('smei-sessao'); } catch (e) {} }
      location.replace('entrada.html#/' + r);
      return;
    }
    _render();
  };
  render();
})();
