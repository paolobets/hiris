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
  misurata: true,
  total_requests: 1204,
  input_tokens: 8300000,
  output_tokens: 412000,
  cost_usd: 26.28,
  cost_eur: 24.18,
  costo_parziale: true,
  rate_limit_errors: 3,
  last_reset: '2026-07-14T09:22:00Z',
  fuso: 'Europe/Rome',
  fuso_noto: true,
  sezioni: [
    {
      provider: 'claude', etichetta: 'API Anthropic',
      nota: 'Costo calcolato sul listino Anthropic.',
      richieste: 980, token_in: 2600000, token_out: 380000,
      cache_lettura: 4200000, cache_scrittura: 310000,
      costo_usd: 20.78, cost_eur: 19.1183, costo_parziale: false,
      modelli: [{
        modello: 'claude-sonnet-4-6', richieste: 980,
        token_in: 2600000, token_out: 380000,
        cache_lettura: 4200000, cache_scrittura: 310000,
        costo_usd: 20.78, cost_eur: 19.1183, costo_stato: 'misurato',
        errori_rate_limit: 3, primo_uso: '2026-08-02', ultimo_uso: '2026-08-21',
      }],
    },
    {
      provider: 'openrouter', etichetta: 'OpenRouter',
      nota: 'Costo dichiarato da OpenRouter.',
      richieste: 23, token_in: 110000, token_out: 5000,
      cache_lettura: 0, cache_scrittura: 0,
      costo_usd: 3.41, cost_eur: 3.1402, costo_parziale: true,
      modelli: [
        {
          modello: 'anthropic/claude-sonnet-4-6', richieste: 18,
          token_in: 88000, token_out: 3900, cache_lettura: 0, cache_scrittura: 0,
          costo_usd: 3.41, cost_eur: 3.1402, costo_stato: 'reale',
          errori_rate_limit: 0, primo_uso: '2026-08-19', ultimo_uso: '2026-08-21',
        },
        {
          modello: 'meta-llama/llama-3.3-70b:free', richieste: 5,
          token_in: 22000, token_out: 1100, cache_lettura: 0, cache_scrittura: 0,
          costo_usd: 0.0, cost_eur: 0.0, costo_stato: 'gratuito',
          errori_rate_limit: 0, primo_uso: '2026-08-20', ultimo_uso: '2026-08-20',
        },
      ],
    },
    {
      provider: 'ponte', etichetta: 'Abbonamento Claude',
      nota: "L'abbonamento non espone il prezzo del singolo turno.",
      richieste: 128, token_in: 2100000, token_out: 94000,
      cache_lettura: 1400000, cache_scrittura: 210000,
      costo_usd: 0.0, cost_eur: null, costo_parziale: false,
      modelli: [{
        modello: 'sonnet (alias)', richieste: 128,
        token_in: 2100000, token_out: 94000,
        cache_lettura: 1400000, cache_scrittura: 210000,
        costo_usd: null, cost_eur: null, costo_stato: 'compreso',
        errori_rate_limit: 0, primo_uso: '2026-08-04', ultimo_uso: '2026-08-21',
      }],
    },
  ],
};

const STORIA = {
  da: '2026-07-23', a: '2026-08-21',
  giorni: [
    { giorno: '2026-08-20', per_provider: { claude: { cost_eur: 1.02, richieste: 41 } } },
    { giorno: '2026-08-21', per_provider: { claude: { cost_eur: 0.44, richieste: 17 },
                                            openrouter: { cost_eur: 0.21, richieste: 3 } } },
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
    if (String(u).includes('storia')) return Promise.resolve(rispondi(storia));
    if (String(u).includes('reset')) return Promise.resolve(rispondi({ last_reset: 'x', cancellato: false }));
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
  usage.sezioni[1].modelli[0].costo_stato = 'non_noto';
  usage.sezioni[1].modelli[0].cost_eur = null;

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
  assert.match(testo, /Compreso nell'abbonamento/);
});

test('il totale a cui manca un prezzo si dichiara un pavimento', async () => {
  const { testo } = await monta();
  assert.match(testo, /≥/, 'senza il segno il minimo si legge come il costo');
  assert.match(testo, /cifra minima/i,
    'il simbolo da solo e\' criptico per chi apre la pagina dal telefono');
});

test('senza righe ignote il totale non si scusa', async () => {
  const usage = JSON.parse(JSON.stringify(RISPOSTA));
  usage.costo_parziale = false;
  usage.sezioni[1].costo_parziale = false;

  const { testo } = await monta(usage);

  assert.doesNotMatch(testo, /cifra minima/i);
});

test('i rifiuti 429 compaiono solo se ce ne sono', async () => {
  const { testo } = await monta();
  assert.match(testo, /3 rifiuti/, 'la sezione Anthropic ne ha tre');
  assert.doesNotMatch(testo, /0 rifiuti/,
    'lo stato-non-evento si omette, non si scrive a zero');
});

test('il pulsante non minaccia una distruzione che non compie', async () => {
  const { outlet, testo } = await monta();
  const bottone = outlet.querySelector('#usage-riparti');
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

  ctx.outlet.querySelector('#usage-riparti').click();
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
    misurata: false, motivo: 'nessun_provider',
    messaggio: 'Nessun provider AI configurato e nessun consumo mai registrato.',
    sezioni: [],
  });

  assert.match(testo, /Nessun provider AI configurato/);
  assert.equal(outlet.querySelector('#usage-riparti'), null,
    'non c\'e\' nessuna ancora da spostare');
});
