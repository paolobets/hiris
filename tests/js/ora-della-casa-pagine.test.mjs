/* Le pagine mostrano l'ora della casa (C-17): ogni pagina che mostra un
   orario legge le cifre che il server manda con l'offset della casa, «oggi»
   dall'`orologio` della stessa risposta, e quando il browser sta in un altro
   fuso lo dice in una riga sotto il titolo.

   Il browser di queste prove sta a New York, la casa a Roma, alle 01:00 del
   14/10/2026 di Roma: a New York sono le 19:00 del 13. Una pagina che passa
   ancora dal fuso del browser scrive «13/10, 18:30» o «ieri» dove la casa
   dice «oggi alle 00:30». */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';
import { fintoFetch } from './helpers/fetch.mjs';

process.env.TZ = 'America/New_York';

const OROLOGIO = { fuso: 'Europe/Rome', adesso: '2026-10-14T01:00:00+02:00' };
const OGGI = '2026-10-14T00:30:00+02:00';
const RIGA_FUSO = 'Gli orari sono quelli della casa (Europe/Rome), non del tuo dispositivo.';
const HTML = '<!doctype html><body><div id="route-outlet"></div></body>';

function rigaFuso(document) {
  const righe = document.querySelectorAll('#clock-hint');
  assert.equal(righe.length, 1, 'una riga sola per pagina');
  assert.equal(righe[0].textContent, RIGA_FUSO);
  return righe[0];
}

test('Cosa HIRIS sa: «Letta oggi alle 00:30», e la riga del fuso', async () => {
  const ctx = loadScripts(['common.js', 'config/dashboard.js'], { html: HTML });
  fintoFetch(ctx.window, {
    'api/home-space': {
      orologio: OROLOGIO, anagrafe_letta_il: OGGI, non_disponibili: [], conteggi: {},
      piani: [], comportamento: { letto_il: null, conteggi: {} }, plance: { lette_il: null },
    },
    'api/briefing': { text: '', summary: { chars: 0, truncated: false, excluded_memories: 0, notices: [] } },
  });
  await ctx.window.HirisDashboard.mount();
  const testo = ctx.document.getElementById('route-outlet').textContent;
  assert.ok(testo.includes('Letta oggi alle 00:30.'), testo);
  rigaFuso(ctx.document);
});

test('Servizi: «arrivato oggi alle 00:30»', async () => {
  const ctx = loadScripts(['common.js', 'config/services-route.js'], { html: HTML });
  fintoFetch(ctx.window, {
    'api/services': {
      orologio: OROLOGIO,
      servizi: { da_decidere: [{ chiave: 'k', nome: 'pannello', indirizzo: '10.0.0.2',
        stato: 'in_attesa', visto_ts: OGGI, deciso_ts: null, codice: '123', impronta: 'x' }],
      accoppiati: [], revocati: [] },
      finestra: { aperta: true, resta_s: 300 }, ruoli: [], specie: [],
    },
  });
  ctx.window.HirisServicesRoute.mount();
  await tick(20);
  const testo = ctx.document.getElementById('route-outlet').textContent;
  assert.ok(testo.includes('arrivato oggi alle 00:30'), testo);
  rigaFuso(ctx.document);
});

test('Impegni: «oggi alle 00:30» viene dall’orologio della casa, non dal browser', async () => {
  const ctx = loadScripts(['common.js', 'config/agenda-route.js'], { html: HTML });
  fintoFetch(ctx.window, {
    'GET api/agenda': {
      orologio: OROLOGIO, stati: {}, total: 1, shown: 1,
      agenda: [{ id: 'p1', specie: 'fai', frase: 'accendi lo studio', quando: OGGI,
        stato: 'in_attesa', stato_leggibile: 'In attesa', sospesa: false, esito: true,
        disdicibile: false, esito_letto_il: '2026-10-14T00:40:00+02:00' }],
    },
  });
  ctx.window.HirisAgendaRoute.mount();
  await tick(20);
  const testo = ctx.document.getElementById('route-outlet').textContent;
  assert.ok(testo.includes('oggi alle 00:30'), testo);
  assert.doesNotMatch(testo, /18:30/, 'l’ora del browser non compare');
  rigaFuso(ctx.document);
});

test('Memoria: «detto oggi alle 00:30», e la riga del fuso', async () => {
  const ctx = loadScripts(['common.js', 'config/memory-route.js'], { html: HTML });
  fintoFetch(ctx.window, {
    'api/memories': { available: true, total: 1, shown: 1, orologio: OROLOGIO, memories: [{
      id: 1, testo: 'un ricordo', detto_da: 'paolo', detto_il: OGGI, forza: 'fatto',
      grandezza: null, minimo: null, massimo: null, unita: null,
      corretto_da_utente: false, ancore: [], condizioni: [] }] },
  });
  ctx.window.HirisMemoryRoute.mount();
  await tick(20);
  const testo = ctx.document.getElementById('route-outlet').textContent;
  assert.ok(testo.includes('oggi alle 00:30'), testo);
  assert.doesNotMatch(testo, /18:30/, 'l’ora del browser non compare');
  rigaFuso(ctx.document);
});

/* Passo 5: a New York sono le 19:00 del 13, a Roma l'01:00 del 14. «Ieri»
   per la casa e' il 13, per il browser il 12: la pagina non lo calcola, lo
   chiede per nome, e scrive nel selettore il giorno che il server risponde.
   Fino al 14/10/2026 chiedeva `day=2026-10-12`, il giorno sbagliato. */
const OSSERVATORE = ['common.js', 'config/watcher-shared.js', 'config/watcher-giorno.js',
  'config/watcher-cosa-fare.js', 'config/watcher-sapere.js',
  'config/watcher-lavoro.js', 'config/state.js', 'config/router.js',
  'config/watcher-route.js'];

test('Il giorno: chiede «ieri» per nome e scrive nel selettore il giorno della casa', async () => {
  const ctx = loadScripts(OSSERVATORE, { html: HTML });
  const chiamate = fintoFetch(ctx.window, {
    'api/mind/report': { giorno: '2026-10-13', orologio: OROLOGIO, resoconto: {
      giorno: '2026-10-13', misure: [], forme: [], cronaca: [],
      primo_piano: [{ sorta: 'da_sapere_subito', nome: 'Allarme piano terra',
        chi: 'alarm_control_panel.piano_terra', cosa: 'triggered', volte: 1,
        quando_ts: '2026-10-13T23:30:00+02:00', ultimo_ts: '2026-10-13T23:30:00+02:00',
        fine_ts: '2026-10-13T23:40:00+02:00' }] } },
  });
  ctx.window.HirisWatcherRoute.mount('giorno');
  await tick(20);
  const report = chiamate.map((c) => c.url).filter((u) => u.indexOf('api/mind/report') === 0);
  assert.deepEqual(report, ['api/mind/report?day=ieri']);
  assert.equal(ctx.document.getElementById('watcher-day').value, '2026-10-13');
  const testo = ctx.document.getElementById('route-outlet').textContent;
  assert.ok(testo.includes('ieri alle 23:30 → 23:40'), testo);
  assert.ok(testo.includes('Letto alle 01:00'), 'la cornice dice l’ora della casa');
  rigaFuso(ctx.document);
});

