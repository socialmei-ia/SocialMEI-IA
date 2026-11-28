'use strict';
/*
  SocialMEI-IA · teste de regressão mínimo (v7.9.11).
  Abre as rotas do aplicativo em tema claro e escuro, em 1440 px e 390 px, e FALHA (código de saída 1) se houver:
    - erro de console ou erro de página (pageerror);
    - rolagem horizontal da página (overflow);
    - contagem de "conversas aguardando resposta" divergente entre a barra lateral, o Início e a Caixa.
  Não altera arquivos nem dados; usa um servidor estático próprio, em porta livre, sobre a pasta do projeto.

  Como rodar (Windows, PowerShell ou Prompt, na pasta do projeto):
    1) npm install --no-save playwright
    2) npx playwright install chromium
    3) node tools\teste-regressao.cjs
  Opções:  --rotas=inicio,caixa   (só algumas rotas)      --url=http://127.0.0.1:4173   (usar um servidor já aberto)
*/
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

let playwright;
try { playwright = require('playwright'); } catch (e) {
  console.error('Playwright não encontrado. Rode:\n  npm install --no-save playwright\n  npx playwright install chromium');
  process.exit(2);
}

const arg = (nome) => (process.argv.find((a) => a.startsWith('--' + nome + '=')) || '').split('=').slice(1).join('=');
const ROTAS = (arg('rotas') || 'inicio,caixa,agenda,oport,divul,negocio,negocio/clientes,negocio/vendas,negocio/produtos,negocio/financeiro,catalogo,automacoes,relatorios,config').split(',');
const TAMANHOS = [1440, 390];
const TEMAS = ['light', 'dark'];
const raiz = path.resolve(__dirname, '..');
const tipos = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.woff2': 'font/woff2', '.ico': 'image/x-icon' };

function servidorEstatico() {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      let p; try { p = decodeURIComponent(new URL(req.url, 'http://x').pathname); } catch (e) { res.writeHead(400); return res.end(); }
      const arq = path.resolve(raiz, '.' + p);
      if (arq !== raiz && !arq.startsWith(raiz + path.sep)) { res.writeHead(403); return res.end(); }
      fs.readFile(arq, (err, buf) => {
        if (err) { res.writeHead(404); return res.end('404'); }
        res.writeHead(200, { 'Content-Type': tipos[path.extname(arq).toLowerCase()] || 'application/octet-stream' });
        res.end(buf);
      });
    });
    srv.listen(0, '127.0.0.1', () => resolve({ srv, base: 'http://127.0.0.1:' + srv.address().port }));
  });
}

(async () => {
  let base = arg('url'); let srv = null;
  if (!base) { const s = await servidorEstatico(); base = s.base; srv = s.srv; }
  const browser = await playwright.chromium.launch();
  const falhas = []; let verificacoes = 0;
  const registra = (msg) => { falhas.push(msg); console.log('  FALHA: ' + msg); };

  for (const w of TAMANHOS) {
    for (const tema of TEMAS) {
      const ctx = await browser.newContext({ viewport: { width: w, height: 900 } });
      const pg = await ctx.newPage();
      const erros = [];
      pg.on('pageerror', (e) => erros.push('pageerror: ' + e.message));
      pg.on('console', (m) => { if (m.type() === 'error') erros.push('console: ' + m.text()); });
      await pg.goto(base + '/frontend/socialmei-app.html#/inicio', { waitUntil: 'domcontentloaded' });
      await pg.waitForTimeout(1500);
      await pg.evaluate((t) => document.documentElement.setAttribute('data-theme', t), tema);
      const contagens = {};
      for (const r of ROTAS) {
        await pg.evaluate((x) => { location.hash = '#/' + x; }, r);
        await pg.waitForTimeout(800);
        verificacoes++;
        const rotulo = w + 'px · ' + tema + ' · #/' + r;
        const over = await pg.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        if (over > 1) registra(rotulo + ': rolagem horizontal de ' + over + ' px');
        if (r === 'inicio' || r === 'caixa') {
          /* Início diz "N conversas esperando resposta"; a Caixa diz "N conversas aguardam sua resposta";
             a barra lateral mostra o número no selo da Caixa. Sem selo/texto = 0. */
          contagens[r] = await pg.evaluate(() => {
            const t = document.getElementById('v').innerText;
            const m = /(\d+)\s+conversas?\s+(esperando|aguard)/i.exec(t) || /Aguardando resposta\s+(\d+)/i.exec(t);  /* celular: sem a frase, vale o título do grupo da lista */
            const nb = document.querySelector('#app a.nv[href="#/caixa"] .nb span');
            return { tela: m ? parseInt(m[1], 10) : 0, lateral: nb ? parseInt(nb.textContent, 10) || 0 : 0 };
          });
        }
      }
      verificacoes++;
      const ini = contagens.inicio, cx = contagens.caixa;
      if (ini && cx) {
        const vals = [ini.lateral, ini.tela, cx.tela, cx.lateral];
        if (new Set(vals).size !== 1) registra(w + 'px · ' + tema + ': contagens divergentes ' + JSON.stringify(contagens));
      }
      if (erros.length) registra(w + 'px · ' + tema + ': ' + erros.length + ' erro(s): ' + erros.slice(0, 3).join(' | '));
      await ctx.close();
      console.log('ok  ' + w + 'px · ' + tema + ' (' + ROTAS.length + ' rotas)');
    }
  }
  await browser.close();
  if (srv) srv.close();
  console.log('\n' + verificacoes + ' verificações, ' + falhas.length + ' falha(s).');
  process.exit(falhas.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
