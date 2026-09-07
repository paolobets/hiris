import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { loadScripts, STATIC_VIVO } from './helpers/dom.mjs';

/* Collaudo usabilita' 3.22.3, rilievo A: il titolo di ogni pagina della SPA
 * di configurazione ESISTEVA -- ventidue occorrenze in undici file -- ma era
 * un `<div class="page-title">`: zero `<h1>` in tutto il frontend
 * (.superpowers/sdd/collaudo-3.22/misure-del-controllore.md, U5). Uno
 * screen reader che salta da titolo a titolo non trovava niente.
 *
 * La cura e' il div che diventa `<h1>` (stessa classe, stesso stile) in ogni
 * rotta -- registrata oggi in `config/main.js`, o registrata domani.
 *
 * Questo file NON enumera le rotte per nome: legge `HirisRouter.
 * _internal_routes` (gia' esposto per test, vedi router-alias.test.mjs) e ne
 * chiama ogni handler(). E' cosi' che la prova "regge nel tempo" -- una
 * rotta nuova che `main.js` registra domani, se il suo segnaposto dimentica
 * l'h1 o ne mette due, fa arrossire QUESTO test senza bisogno di
 * aggiornarne la lista.
 *
 * Mutazione che questa prova deve uccidere: rimettere anche un solo
 * `el('div', 'page-title', ...)` (o `<div class="page-title">` in una
 * stringa) al posto di un h1 -- cioe' esattamente lo stato da cui si parte,
 * il modo piu' onesto di provare che sanno fallire. */

const HTML_BASE = '<!doctype html><body>'
  + '<div id="chrome-here"></div><div id="route-outlet"></div></body>';

function bootSoloGuscio() {
  return loadScripts(['config/state.js', 'config/router.js', 'config/main.js'], { html: HTML_BASE });
}

test('ogni rotta registrata da main.js mostra ESATTAMENTE un h1 nel proprio segnaposto, con la classe page-title', () => {
  const { document, window } = bootSoloGuscio();
  const routes = window.HirisRouter._internal_routes;

  // Le nove rotte note oggi (root, tree, memory, agenda, constructions,
  // watcher, usage, models, settings): se questo numero scende qualcuno ha
  // tolto una rotta senza accorgersene: se sale, e' la prova stessa che
  // "regge nel tempo" -- la rotta nuova viene comunque verificata dal ciclo
  // sotto, nessuna lista da toccare.
  assert.ok(routes.length >= 9,
    `main.js deve registrare almeno le nove rotte note (trovate ${routes.length})`);

  for (const r of routes) {
    const outlet = document.getElementById('route-outlet');
    outlet.innerHTML = '';
    r.handler();

    const h1s = outlet.querySelectorAll('h1');
    assert.equal(h1s.length, 1,
      `la rotta ${r.pattern} deve mostrare esattamente un <h1> nel proprio segnaposto (trovati ${h1s.length})`);
    assert.equal(h1s[0].className, 'page-title',
      `l'h1 della rotta ${r.pattern} deve portare la classe page-title, che gli da' tutto lo stile`);
    assert.equal(outlet.querySelectorAll('div.page-title').length, 0,
      `la rotta ${r.pattern} non deve lasciare nessun div.page-title residuo accanto all'h1`);
    assert.ok(h1s[0].textContent.trim().length > 0,
      `l'h1 della rotta ${r.pattern} non puo' essere vuoto`);
  }
});

test('la pagina non trovata (nessuna rotta combacia) mostra ESATTAMENTE un h1', () => {
  const { document, window } = bootSoloGuscio();
  window.location.hash = '#/questa-rotta-non-esiste-mai';
  window.HirisRouter.start();
  window.dispatchEvent(new window.Event('hashchange'));

  const outlet = document.getElementById('route-outlet');
  const h1s = outlet.querySelectorAll('h1');
  assert.equal(h1s.length, 1, `«Pagina non trovata» deve avere un solo h1 (trovati ${h1s.length})`);
  assert.match(h1s[0].textContent, /Pagina non trovata/);
});

/* Le due pagine che il collaudo nomina per nome perche' ripetono il titolo
 * in piu' rami: usage-route.js (quattro), settings-route.js (tre). Il rischio
 * vero non e' "esiste un h1 nel file" (gia' coperto sopra sul segnaposto
 * di main.js) ma "resta UNO SOLO quando lo stato della pagina cambia" --
 * caricamento -> contenuto, o caricamento -> errore -- perche' ogni ramo
 * scrive la propria copia del titolo. */

test('Consumi: caricamento, misurato:false, contenuto normale ed errore hanno TUTTI un solo h1', async () => {
  const HTML = '<!doctype html><body><div id="route-outlet"></div></body>';

  function monta(rispondi) {
    const ctx = loadScripts(['config/api.js', 'config/usage-route.js'], { html: HTML });
    ctx.window.fetch = rispondi;
    return ctx;
  }

  function h1s(ctx) {
    return ctx.document.getElementById('route-outlet').querySelectorAll('h1');
  }

  // 1) caricamento: il controllo sincrono, PRIMA che la fetch si risolva --
  //    mount() scrive «Carico…» in modo sincrono, quindi si guarda subito
  //    dopo averlo chiamato, senza await.
  {
    const ctx = monta(() => new Promise(() => {})); // non si risolve mai
    ctx.window.HirisUsageRoute.mount();
    assert.equal(h1s(ctx).length, 1, 'stato di caricamento: un solo h1');
  }

  // 2) misurato:false (200, ma niente da mostrare)
  {
    const ctx = monta(() => Promise.resolve({
      ok: true, status: 200,
      json: () => Promise.resolve({ measured: false, message: 'niente da misurare' }),
    }));
    ctx.window.HirisUsageRoute.mount();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    assert.equal(h1s(ctx).length, 1, 'stato misurato:false: un solo h1');
  }

  // 3) contenuto normale
  {
    const ctx = monta((url) => {
      if (String(url).indexOf('api/usage/history') === 0) {
        return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ days: [] }) });
      }
      return Promise.resolve({
        ok: true, status: 200,
        json: () => Promise.resolve({
          measured: true, timezone_known: true, timezone: 'Europe/Rome',
          cost_eur: 0, cost_state: 'gratuito', requests: 0, sections: [],
        }),
      });
    });
    ctx.window.HirisUsageRoute.mount();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    assert.equal(h1s(ctx).length, 1, 'stato con contenuto: un solo h1');
  }

  // 4) errore di rete
  {
    const ctx = monta(() => Promise.reject(new Error('rete giu\'')));
    ctx.window.HirisUsageRoute.mount();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    assert.equal(h1s(ctx).length, 1, 'stato di errore: un solo h1');
  }
});

test('Impostazioni chat: caricamento, contenuto ed errore hanno TUTTI un solo h1', async () => {
  const HTML = '<!doctype html><body><div id="route-outlet"></div></body>';

  function h1s(ctx) {
    return ctx.document.getElementById('route-outlet').querySelectorAll('h1');
  }

  // 1) caricamento
  {
    const ctx = loadScripts(['config/settings-route.js'], { html: HTML });
    ctx.window.fetch = () => new Promise(() => {});
    ctx.window.HirisSettingsRoute.mount();
    assert.equal(h1s(ctx).length, 1, 'stato di caricamento: un solo h1');
  }

  // 2) contenuto
  {
    const ctx = loadScripts(['config/settings-route.js'], { html: HTML });
    ctx.window.fetch = () => Promise.resolve({
      ok: true, status: 200,
      json: () => Promise.resolve({
        name: 'HIRIS', system_prompt: '', response_mode: 'compact',
        thinking_budget: 2048, max_chat_turns: 4, restrict_to_home: true,
        retention_days: 30, response_modes: ['auto', 'compact', 'minimal'],
        default_system_prompt: '',
      }),
    });
    ctx.window.HirisSettingsRoute.mount();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    assert.equal(h1s(ctx).length, 1, 'stato con contenuto: un solo h1');
  }

  // 3) errore
  {
    const ctx = loadScripts(['config/settings-route.js'], { html: HTML });
    ctx.window.fetch = () => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
    ctx.window.HirisSettingsRoute.mount();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    assert.equal(h1s(ctx).length, 1, 'stato di errore: un solo h1');
  }
});

/* La gerarchia sotto l'h1: `.sc-title` e `.usec-name` sono titoli di sezione
 * esistenti, nominati dal capitolato. Dove restavano `<div>` (dashboard.js,
 * tree-route.js) o saltavano un livello (usec-name era h3 senza nessun h2
 * sulla pagina Consumi) diventano `<h2>`. Non si tocca `<summary>`: e' un
 * widget di disclosure, non un titolo (marcarlo come tale sarebbe esattamente
 * il "non trasformare in titolo cio' che titolo non e'" che il capitolato
 * vieta). */

test('.sc-title e\' <h2> ovunque: nessun div.sc-title residuo', () => {
  for (const file of ['dashboard.js', 'tree-route.js', 'agenda-route.js',
    'constructions-route.js', 'watcher-route.js', 'models-route.js']) {
    const src = readFileSync(join(STATIC_VIVO, 'config', file), 'utf8');
    assert.doesNotMatch(src, /el\(\s*'div'\s*,\s*'sc-title'/,
      `${file} non deve avere piu' un div.sc-title: sotto l'h1 e' un titolo di sezione vero`);
  }
});

test('.usec-name e\' <h2>, non <h3>: sulla pagina Consumi non c\'era nessun h2 fra l\'h1 e lui', () => {
  const src = readFileSync(join(STATIC_VIVO, 'config', 'usage-route.js'), 'utf8');
  assert.match(src, /<h2 class="usec-name">/);
  assert.doesNotMatch(src, /<h3 class="usec-name">/);
});

test('.page-title porta margin-top:0 e display:block: un h1 vero non sposta la pagina in giu\', ne\' eredita display:flex da un vecchio h1 di hiris-config-override.css', () => {
  // I commenti dentro la regola contengono a loro volta delle graffe (citano
  // `h1 { display: flex; ... }`), quindi si toglie ogni commento CSS PRIMA di
  // isolare il corpo della regola: altrimenti la prima graffa di commento
  // chiuderebbe il match e le dichiarazioni vere, scritte dopo, resterebbero fuori.
  const css = readFileSync(join(STATIC_VIVO, 'hiris-config.css'), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '');
  const blocco = css.match(/\.page-title\s*\{([^}]*)\}/);
  assert.ok(blocco, '.page-title deve esistere in hiris-config.css');
  assert.match(blocco[1], /margin-top:\s*0\b/, 'manca margin-top:0 -- un h1 porta un margine dal foglio del browser che un div non ha');
  assert.match(blocco[1], /display:\s*block\b/, 'manca display:block -- neutralizza il residuo `h1{display:flex}` di hiris-config-override.css');
});
