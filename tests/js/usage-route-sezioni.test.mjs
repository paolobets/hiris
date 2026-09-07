import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* La pagina Consumi, fetta «i consumi, per modello».

   Quello che questi test tengono fermo non e' il markup: e' la disciplina che
   la fetta esiste per imporre. Un costo che non si conosce non si scrive
   «0,00»; un provider mai usato e' un'ASSENZA e non uno zero; un totale a cui
   manca un prezzo e' un pavimento e lo dice; e il pulsante che sposta
   un'ancora non comunica una distruzione, perche' non ne compie una. */

const HTML = '<!doctype html><body><div id="route-outlet"></div></body>';

const RISPOSTA = {
  measured: true,
  total_requests: 1204,
  input_tokens: 8300000,
  output_tokens: 412000,
  cost_usd: 26.28,
  cost_eur: 24.18,
  partial_cost: true,
  rate_limit_errors: 3,
  last_reset: '2026-07-14T09:22:00Z',
  timezone: 'Europe/Rome',
  timezone_known: true,
  sections: [
    {
      provider: 'claude', label: 'API Anthropic',
      note: 'Costo calcolato sul listino Anthropic.',
      requests: 980, token_in: 2600000, token_out: 380000,
      cache_read: 4200000, cache_write: 310000,
      cost_usd: 20.78, cost_eur: 19.1183, partial_cost: false,
      models: [{
        model: 'claude-sonnet-4-6', requests: 980,
        token_in: 2600000, token_out: 380000,
        cache_read: 4200000, cache_write: 310000,
        cost_usd: 20.78, cost_eur: 19.1183, cost_state: 'misurato',
        rate_limit_errors: 3, first_use: '2026-08-02', last_use: '2026-08-21',
      }],
    },
    {
      provider: 'openrouter', label: 'OpenRouter',
      note: 'Costo dichiarato da OpenRouter.',
      requests: 23, token_in: 110000, token_out: 5000,
      cache_read: 0, cache_write: 0,
      cost_usd: 3.41, cost_eur: 3.1402, partial_cost: true,
      models: [
        {
          model: 'anthropic/claude-sonnet-4-6', requests: 18,
          token_in: 88000, token_out: 3900, cache_read: 0, cache_write: 0,
          cost_usd: 3.41, cost_eur: 3.1402, cost_state: 'reale',
          rate_limit_errors: 0, first_use: '2026-08-19', last_use: '2026-08-21',
        },
        {
          model: 'meta-llama/llama-3.3-70b:free', requests: 5,
          token_in: 22000, token_out: 1100, cache_read: 0, cache_write: 0,
          cost_usd: 0.0, cost_eur: 0.0, cost_state: 'gratuito',
          rate_limit_errors: 0, first_use: '2026-08-20', last_use: '2026-08-20',
        },
      ],
    },
    {
      provider: 'ponte', label: 'Abbonamento Claude',
      note: "L'abbonamento non espone il prezzo del singolo turno.",
      requests: 128, token_in: 2100000, token_out: 94000,
      cache_read: 1400000, cache_write: 210000,
      cost_usd: 0.0, cost_eur: null, partial_cost: false,
      models: [{
        model: 'sonnet (alias)', requests: 128,
        token_in: 2100000, token_out: 94000,
        cache_read: 1400000, cache_write: 210000,
        cost_usd: null, cost_eur: null, cost_state: 'compreso',
        rate_limit_errors: 0, first_use: '2026-08-04', last_use: '2026-08-21',
      }],
    },
  ],
};

const STORIA = {
  da: '2026-07-23', a: '2026-08-21',
  days: [
    { day: '2026-08-20', per_provider: { claude: { cost_eur: 1.02, requests: 41 } } },
    { day: '2026-08-21', per_provider: { claude: { cost_eur: 0.44, requests: 17 },
                                            openrouter: { cost_eur: 0.21, requests: 3 } } },
  ],
};

function rispondi(corpo) {
  return { ok: true, status: 200, json: () => Promise.resolve(corpo) };
}

async function monta(usage = RISPOSTA, storia = STORIA) {
  const ctx = loadScripts(['config/api.js', 'config/usage-route.js'], { html: HTML });
  const chiamate = [];
  ctx.window.fetch = (u, opzioni) => {
    chiamate.push({ url: String(u), opzioni: opzioni });
    // Era `.includes('storia')`, che non intercetta MAI la rotta vera
    // (`api/usage/history`, config/usage-route.js): "history" non contiene
    // la sottostringa "storia" ('history' = h-i-s-t-o-r-y, non ...-i-a).
    // Il parametro `storia` di questa `monta()` non arrivava mai al
    // grafico -- charts() riceveva la stessa RISPOSTA del riepilogo, priva
    // di `.days`, e ogni test di questo file che non ispezionava il
    // contenuto del grafico non se n'e' mai accorto. Trovato scrivendo i
    // due test C5 sui grafici qui sotto, che DIPENDONO da una storia vera.
    if (String(u).includes('api/usage/history')) return Promise.resolve(rispondi(storia));
    if (String(u).includes('reset')) return Promise.resolve(rispondi({ last_reset: 'x', deleted: false }));
    return Promise.resolve(rispondi(usage));
  };
  ctx.window.HirisUsageRoute.mount();
  for (let i = 0; i < 8; i++) await tick(0);
  const outlet = ctx.document.getElementById('route-outlet');
  return { ...ctx, outlet, testo: outlet.textContent, chiamate };
}


test('le sezioni compaiono solo per i provider usati', async () => {
  const { testo } = await monta();
  assert.match(testo, /API Anthropic/);
  assert.match(testo, /OpenRouter/);
  assert.match(testo, /Abbonamento Claude/);
  assert.doesNotMatch(testo, /API OpenAI/,
    "mai usato: e' un'ASSENZA, non una sezione a zero");
});

test('un modello senza prezzo NON scrive uno zero, e nemmeno un trattino', async () => {
  const usage = JSON.parse(JSON.stringify(RISPOSTA));
  usage.sections[1].models[0].cost_state = 'non_noto';
  usage.sections[1].models[0].cost_eur = null;

  const { testo } = await monta(usage);

  assert.match(testo, /Prezzo sconosciuto/,
    'lo stato va detto a parole: e\' un\'assenza che chiede attenzione');
  assert.doesNotMatch(testo, /anthropic\/claude-sonnet-4-6[\s\S]{0,80}€ 0,00/,
    'lo zero bugiardo e\' tornato a schermo');
});

test('un modello gratuito dice «Gratuito», non «€ 0,00»', async () => {
  const { testo } = await monta();
  assert.match(testo, /Gratuito/);
});

test("l'abbonamento dice «Compreso», che non e' ne' zero ne' sconosciuto", async () => {
  const { testo } = await monta();
  assert.match(testo, /Compreso nell’abbonamento/);
});

test('il totale a cui manca un prezzo si dichiara un pavimento', async () => {
  const { testo } = await monta();
  assert.match(testo, /≥/, 'senza il segno il minimo si legge come il costo');
  assert.match(testo, /cifra minima/i,
    'il simbolo da solo e\' criptico per chi apre la pagina dal telefono');
});

test('senza righe ignote il totale non si scusa', async () => {
  const usage = JSON.parse(JSON.stringify(RISPOSTA));
  usage.partial_cost = false;
  usage.sections[1].partial_cost = false;

  const { testo } = await monta(usage);

  assert.doesNotMatch(testo, /cifra minima/i);
});

// ---------------------------------------------------------------------------
// Collaudo 3.22, C5 ("€ 0,00 quando la verità è «non misurabile»"): la
// tessera «COSTO» del riepilogo sommava anche la sezione dell'abbonamento
// (`ponte`, `cost_usd: null`) come 0.0 -- quando l'abbonamento è l'UNICO
// uso, il totale che il server manda è 0.0 per costruzione, e la tessera
// scriveva «€ 0,00» invece di dire che qui non c'è niente da misurare.
// ---------------------------------------------------------------------------

const RISPOSTA_SOLO_ABBONAMENTO = {
  measured: true,
  total_requests: 99,
  input_tokens: 7200000,
  output_tokens: 500000,
  cost_usd: 0.0,
  cost_eur: 0,
  partial_cost: false,
  rate_limit_errors: 0,
  last_reset: '2026-07-14T09:22:00Z',
  timezone: 'Europe/Rome',
  timezone_known: true,
  sections: [{
    provider: 'ponte', label: 'Abbonamento Claude',
    note: "L'abbonamento non espone il prezzo del singolo turno.",
    requests: 99, token_in: 7200000, token_out: 500000,
    cache_read: 0, cache_write: 0,
    cost_usd: null, cost_eur: null, partial_cost: false,
    models: [{
      model: 'sonnet (alias)', requests: 99,
      token_in: 7200000, token_out: 500000, cache_read: 0, cache_write: 0,
      cost_usd: null, cost_eur: null, cost_state: 'compreso',
      rate_limit_errors: 0, first_use: '2026-08-04', last_use: '2026-08-21',
    }],
  }],
};

const STORIA_SOLO_ABBONAMENTO = {
  da: '2026-07-23', a: '2026-08-21',
  days: [{ day: '2026-08-21', per_provider: { ponte: { requests: 99 } } }],
};

test('collaudo 3.22 (C5): con il solo abbonamento la tessera «Costo» dice «In abbonamento», mai «€ 0,00»', async () => {
  const { outlet, testo } = await monta(RISPOSTA_SOLO_ABBONAMENTO, STORIA_SOLO_ABBONAMENTO);
  const tessera = [...outlet.querySelectorAll('#usage-summary .stat-tile')]
    .find((t) => t.querySelector('.st-label').textContent === 'Costo');
  assert.ok(tessera, 'precondizione: la tessera Costo deve esistere');
  assert.equal(tessera.querySelector('.st-value').textContent, 'In abbonamento');
  assert.doesNotMatch(testo, /€ 0,00/, 'lo zero che afferma non deve comparire da nessuna parte nella pagina');
});

test('collaudo 3.22 (C5, difetto di resa): il grafico del costo senza provider a consumo spiega DENTRO l\'area, non sotto', async () => {
  const { outlet } = await monta(RISPOSTA_SOLO_ABBONAMENTO, STORIA_SOLO_ABBONAMENTO);
  const grafici = outlet.querySelector('.usage-charts');
  assert.ok(grafici, 'precondizione: il blocco dei grafici deve esistere');

  // Il grafico del COSTO (il primo <svg>/placeholder dentro .usage-charts,
  // prima del titolo "Richieste al giorno") non deve disegnare un SVG vuoto:
  // deve essere rimpiazzato da un box con la spiegazione DENTRO.
  const vuoto = grafici.querySelector('.usage-chart-empty');
  assert.ok(vuoto, 'un grafico senza provider da impilare deve avere il suo box vuoto con la spiegazione dentro');
  assert.match(vuoto.textContent, /abbonamento/i,
    'la spiegazione (perche\' il costo non compare qui) deve stare DENTRO il box, non in un paragrafo separato dopo');

  // Il grafico delle RICHIESTE, invece, ha davvero un provider (ponte) da
  // disegnare: resta un <svg> vero, non il placeholder vuoto.
  const titoli = [...grafici.querySelectorAll('h3')].map((h) => h.textContent);
  assert.ok(titoli.includes('Richieste al giorno'), 'precondizione: il secondo grafico deve esistere');
  assert.equal(grafici.querySelectorAll('.usage-chart-empty').length, 1,
    'SOLO il grafico del costo e\' vuoto -- quello delle richieste ha il ponte da disegnare');
});

test('i rifiuti 429 compaiono solo se ce ne sono', async () => {
  const { testo } = await monta();
  assert.match(testo, /3 rifiuti/, 'la sezione Anthropic ne ha tre');
  assert.doesNotMatch(testo, /0 rifiuti/,
    'lo stato-non-evento si omette, non si scrive a zero');
});

test('il pulsante non minaccia una distruzione che non compie', async () => {
  const { outlet, testo } = await monta();
  const bottone = outlet.querySelector('#usage-reset');
  assert.ok(bottone, 'il pulsante esiste');
  assert.doesNotMatch(bottone.className, /btn-danger/,
    'sposta un\'ancora: il rosso comunicherebbe una distruzione');
  assert.match(testo, /Non cancella niente/,
    'la frase deve essere sempre visibile, non dentro un confirm()');
});

test('premere il pulsante non apre nessun confirm()', async () => {
  const ctx = await monta();
  let chiesto = false;
  ctx.window.confirm = () => { chiesto = true; return true; };

  ctx.outlet.querySelector('#usage-reset').click();
  for (let i = 0; i < 8; i++) await tick(0);

  assert.equal(chiesto, false,
    'un gesto reversibile dall\'interfaccia stessa non merita un blocco modale');
  assert.ok(ctx.chiamate.some((c) => c.url.includes('usage/reset')));
});

test('il fuso si dichiara: un giorno senza fuso non e\' un giorno', async () => {
  const { testo } = await monta();
  assert.match(testo, /Europe\/Rome/);
});

test('la storia si chiede alla SUA rotta, non a quella del riepilogo', async () => {
  const { chiamate } = await monta();
  assert.ok(chiamate.some((c) => c.url.includes('api/usage/history')));
});

test('quando non si misura, la pagina lo dice e toglie il pulsante', async () => {
  const { outlet, testo } = await monta({
    measured: false, reason: 'nessun_provider',
    message: 'Nessun provider AI configurato e nessun consumo mai registrato.',
    sections: [],
  });

  assert.match(testo, /Nessun provider AI configurato/);
  assert.equal(outlet.querySelector('#usage-reset'), null,
    'non c\'e\' nessuna ancora da spostare');
});
