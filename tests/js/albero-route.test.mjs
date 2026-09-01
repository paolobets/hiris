import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { loadScripts, tick } from './helpers/dom.mjs';

/* Reperto 26 (docs/design/2026-08-17-reperti-della-review.md): `GET
   /api/home-space` manda l'albero completo che `anagrafe.gerarchia()` costruisce
   (`casa.piani`), e prima usciva verso nessuna pagina. Questo file pinna la
   pagina #/albero (config/albero-route.js), che lo mostra.

   Ciò che conta qui non è l'impaginazione — è che le SEI cause distinte di
   silenzio che `gerarchia()` dichiara (Senza area / Area sconosciuta / Aree
   non lette / Dispositivi non letti / Senza piano / Piani non letti) restino
   SEI frasi diverse, non un'unica "non si sa" — e che le entità disabilitate
   compaiano sempre, marcate, mai nascoste. */

const HTML = '<!doctype html><body><div id="route-outlet"></div></body>';

function rendi(casa) {
  const ctx = loadScripts(['config/albero-route.js'], { html: HTML });
  const chiamate = [];
  ctx.window.fetch = (url) => {
    chiamate.push(String(url));
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(casa) });
  };
  return ctx.window.HirisAlberoRoute.mount().then(() => {
    ctx.testo = ctx.document.getElementById('route-outlet').textContent;
    ctx.chiamate = chiamate;
    return ctx;
  });
}

/* Una casa letta, con l'intero repertorio di gerarchia(): un piano vero con
   un'area vera (un'entità attiva + una disabilitata), un piano "Senza
   piano", un piano "Piani non letti", e il piano-contenitore "Fuori dalle
   aree" con le quattro pseudo-aree, ciascuna con una sola entità — cosi'
   ogni asserzione parla di UNA causa sola. */
function casaCompleta(extra = {}) {
  return Object.assign({
    anagrafe_letta_il: '2026-08-17T09:00:00',
    non_disponibili: [],
    conteggi: {},
    sistema_di_riferimento: {
      nome: 'Casa di prova', fuso: 'Europe/Rome', lingua: 'it', valuta: 'EUR',
      versione_ha: '2026.8.1',
      unita: { temperature: '°C', length: 'km' },
    },
    // Una nota risolvibile (nomeEtichetta la traduce) e una PENZOLANTE
    // (nessuna voce in questa mappa): 'Luce cucina' sotto porta entrambi gli
    // id, cosi' la stessa entita' prova sia la traduzione sia il fallback.
    etichette: { da_controllare: 'Da controllare', priorita_alta: 'Priorità alta' },
    piani: [
      {
        id: 'piano_terra', nome: 'Piano terra', livello: 0,
        aree: [
          {
            id: 'cucina', nome: 'Cucina', alias: [], etichette: [],
            entita_temperatura: 'sensor.temperatura_cucina',
            entita: [
              { id: 'light.cucina', nome: 'Luce cucina', piattaforma: 'hue', categoria: null,
                classe: null, unita: null, disabilitata: 0, nascosta: 0, alias: [],
                etichette: ['da_controllare', 'slug_fantasma'] },
            ],
            entita_disabilitate: [
              { id: 'sensor.vecchio', nome: 'Vecchio sensore cucina', piattaforma: 'zwave',
                categoria: null, classe: null, unita: null, disabilitata: 1, nascosta: 0,
                alias: [], etichette: [] },
            ],
          },
        ],
      },
      {
        id: '__senza_piano__', nome: 'Senza piano', livello: null,
        aree: [
          { id: 'garage', nome: 'Garage', alias: [], etichette: [], entita: [], entita_disabilitate: [] },
        ],
      },
      {
        id: '__piani_non_letti__', nome: 'Piani non letti', livello: null,
        aree: [
          { id: 'taverna', nome: 'Taverna', alias: [], etichette: [], entita: [], entita_disabilitate: [] },
        ],
      },
      {
        id: '__fuori_dalle_aree__', nome: 'Fuori dalle aree', livello: null,
        aree: [
          { id: '__aree_non_lette__', nome: 'Aree non lette', alias: [], etichette: [],
            entita: [{ id: 'sensor.a', nome: 'Entità A', alias: [], etichette: [] }] },
          { id: '__area_sconosciuta__', nome: 'Area sconosciuta', alias: [], etichette: [],
            entita: [{ id: 'sensor.b', nome: 'Entità B', alias: [], etichette: [] }] },
          { id: '__senza_area__', nome: 'Senza area', alias: [], etichette: [],
            entita: [{ id: 'sensor.c', nome: 'Entità C', alias: [], etichette: [] }] },
          { id: '__dispositivi_non_letti__', nome: 'Dispositivi non letti', alias: [], etichette: [],
            entita: [{ id: 'sensor.d', nome: 'Entità D', alias: [], etichette: [] }] },
        ],
      },
    ],
  }, extra);
}

test('legge api/home-space e nessun\'altra rotta', async () => {
  const { chiamate } = await rendi(casaCompleta());
  assert.ok(chiamate.some((u) => u.includes('api/home-space')));
  assert.equal(chiamate.length, 1, 'una sola fetch: niente api/briefing, niente rotte uscite');
});

test('le sei pseudo-aree/pseudo-piani restano SEI frasi diverse, non un unico «non si sa»', async () => {
  const { testo } = await rendi(casaCompleta());

  // Le sei frasi che il docstring di gerarchia() distingue: nessuna è
  // sostituibile da un'altra, e nessuna può ridursi a una generica "non so".
  const frasi = [
    /Il registro delle aree ha risposto: queste entità davvero non sono assegnate/,   // Senza area
    /puntano a un’area che non esiste più nel registro/,                              // Area sconosciuta
    /Il registro delle aree non ha risposto: non si può sapere/,                      // Aree non lette
    /erediterebbero l’area dal proprio dispositivo, ma HIRIS non ha potuto leggere/,   // Dispositivi non letti
    /non ha assegnato a nessun piano/,                                                 // Senza piano
    /Il registro dei piani non ha risposto/,                                           // Piani non letti
  ];
  for (const frase of frasi) {
    assert.match(testo, frase, `manca la spiegazione: ${frase}`);
  }

  // E ognuna compare esattamente una volta: appiattirle in una frase unica
  // le farebbe collassare in un numero di occorrenze diverso da 6 distinte.
  const testi = [...new Set(frasi.map((f) => f.source))];
  assert.equal(testi.length, 6, 'precondizione: le sei frasi attese sono davvero sei stringhe diverse');
});

test('i nomi delle sei pseudo-aree/pseudo-piani compaiono tutti, per nome', async () => {
  const { document } = await rendi(casaCompleta());
  const sommari = [...document.querySelectorAll('summary')].map((s) => s.textContent);
  for (const nome of ['Senza piano', 'Piani non letti', 'Fuori dalle aree',
    'Aree non lette', 'Area sconosciuta', 'Senza area', 'Dispositivi non letti']) {
    assert.ok(sommari.some((s) => s.indexOf(nome) === 0 || s.indexOf(nome + ' —') === 0),
      `manca il gruppo «${nome}» fra i sommari: ${JSON.stringify(sommari)}`);
  }
});

test('un\'entità disabilitata compare SEMPRE, marcata, anche quando è l\'unica della sua area', async () => {
  const casa = casaCompleta();
  // Cucina ha 1 attiva + 1 disabilitata nella fixture di base: qui la
  // svuotiamo di attive per provare il caso limite dichiarato dallo spec
  // ("un'area con tre luci disabilitate e zero attive non deve sembrare
  // vuota"). Altre aree della fixture (Garage, Taverna) restano a zero
  // entità DAVVERO vuote apposta, cosi' l'asserzione sotto -- ristretta al
  // solo <details> della Cucina -- non puo' essere soddisfatta per caso da
  // una "Nessuna entità." che appartiene a un'altra area.
  casa.piani[0].aree[0].entita = [];
  const { document } = await rendi(casa);
  const sommarioCucina = [...document.querySelectorAll('summary')]
    .find((s) => s.textContent.indexOf('Cucina') === 0);
  assert.ok(sommarioCucina, 'precondizione: l’area Cucina deve essere disegnata');
  const corpoCucina = sommarioCucina.closest('details').textContent;
  assert.match(corpoCucina, /Vecchio sensore cucina/, 'l’entità disabilitata deve comparire');
  assert.match(corpoCucina, /\[disabilitata\]/, 'e deve essere marcata come tale');
  assert.doesNotMatch(corpoCucina, /Nessuna entità\./,
    'un\'area con solo entità disabilitate non è "nessuna entità": ce ne sono, sono marcate');
});

test('un\'entità nascosta compare SEMPRE, marcata, in una sezione propria (2026-08-25)', async () => {
  // Stessa prova gemella di quella per le disabilitate qui sopra: fetta
  // "nascoste fuori dagli elenchi" -- `gerarchia()` toglie le nascoste da
  // `entita` per STRUTTURA (la stessa ragione per cui la chat non le nomina
  // piu' di sua iniziativa), ma questa pagina audita cosa HIRIS sa e non
  // deve far sparire niente: le mostra in `entita_nascoste`, come già fa per
  // `entita_disabilitate`.
  const casa = casaCompleta();
  casa.piani[0].aree[0].entita = [];
  casa.piani[0].aree[0].entita_nascoste = [
    { id: 'light.lampadario_fake', nome: null, nome_dedotto: 'Lampadario fake',
      piattaforma: 'ave_domina', categoria: null, classe: null, unita: null,
      disabilitata: 0, nascosta: 1, alias: [], etichette: [] },
  ];
  const { document } = await rendi(casa);
  const sommarioCucina = [...document.querySelectorAll('summary')]
    .find((s) => s.textContent.indexOf('Cucina') === 0);
  assert.ok(sommarioCucina, 'precondizione: l’area Cucina deve essere disegnata');
  assert.match(sommarioCucina.textContent, /1 nascosta/, 'il conteggio in sommario le dichiara');
  const corpoCucina = sommarioCucina.closest('details').textContent;
  assert.match(corpoCucina, /Entità nascosta/, 'il titolo di sezione compare');
  assert.match(corpoCucina, /\[nascosta in Home Assistant\]/, 'e l’entità è marcata come tale');
  assert.doesNotMatch(corpoCucina, /Nessuna entità\./,
    'un\'area con solo entità nascoste non è "nessuna entità": ce n\'è una, marcata');
});

test('«non_disponibili» pieno: una casa letta a metà non sembra una casa piccola', async () => {
  const { testo } = await rendi(casaCompleta({ non_disponibili: ['aree', 'categorie:script'] }));
  assert.match(testo, /Registri che non hanno risposto all’ultima lettura/);
  assert.match(testo, /Aree/);
  assert.match(testo, /Categorie \(ambito «script»\)/);
  assert.doesNotMatch(testo, /Tutti i registri hanno risposto/);
});

test('«non_disponibili: null» non si traveste da «tutti hanno risposto»', async () => {
  const { testo } = await rendi(casaCompleta({ non_disponibili: null }));
  assert.match(testo, /Non si sa quali registri abbiano risposto/);
  assert.doesNotMatch(testo, /Tutti i registri hanno risposto/);
});

test('«non_disponibili: []» invece è un controllo avvenuto, e lo dice', async () => {
  const { testo } = await rendi(casaCompleta({ non_disponibili: [] }));
  assert.match(testo, /Tutti i registri hanno risposto/);
});

test('un\'anagrafe mai letta non si traveste da albero vuoto', async () => {
  const { testo, document } = await rendi({
    anagrafe_letta_il: null, non_disponibili: null, conteggi: {}, piani: [],
    sistema_di_riferimento: null,
  });
  assert.match(testo, /non è ancora stata letta/);
  assert.doesNotMatch(testo, /Letta il/);
  assert.equal(document.querySelectorAll('details').length, 0,
    'nessun piano/area disegnato su una lettura mai avvenuta -- niente albero vuoto spacciato per verità');
});

test('sistema di riferimento: presente si legge, assente lo dichiara (mai silenzio)', async () => {
  const { testo } = await rendi(casaCompleta());
  assert.match(testo, /casa «Casa di prova»/);
  assert.match(testo, /fuso Europe\/Rome/);
  assert.match(testo, /temperatura °C/);
  assert.match(testo, /lunghezza km/);

  const { testo: assente } = await rendi(casaCompleta({ sistema_di_riferimento: {} }));
  assert.match(assente, /Non letto: fuso, unità, valuta e lingua della casa non sono disponibili/);
});

test("le etichette di un'entità mostrano il NOME (`casa.etichette`), non lo slug", async () => {
  // Luce cucina porta due id: 'da_controllare' (nella mappa -> 'Da controllare')
  // e 'slug_fantasma' (fuori mappa: un riferimento penzolante).
  const { testo } = await rendi(casaCompleta());
  assert.match(testo, /etichette: Da controllare, slug_fantasma/,
    'l’id risolvibile diventa il nome; quello penzolante resta l’id, non sparisce');
  assert.doesNotMatch(testo, /da_controllare/,
    'lo slug grezzo di un id RISOLVIBILE non deve comparire più da nessuna parte');
});

test('`etichette: null`: lo dichiara, e nel frattempo gli id restano grezzi (mai un nome inventato)', async () => {
  const { testo } = await rendi(casaCompleta({ etichette: null }));
  assert.match(testo, /I nomi delle etichette non sono stati letti/,
    'un `null` sulla mappa si dichiara, stessa disciplina di `non_disponibili`');
  assert.match(testo, /etichette: da_controllare, slug_fantasma/,
    'senza mappa nessun id si traduce: restano tutti grezzi, non un misto inventato');
  assert.doesNotMatch(testo, /etichette: Da controllare/,
    'senza la mappa non può comparire un nome tradotto');
});

test('una fetch caduta lo dichiara: niente casa vuota travestita da silenzio', async () => {
  const ctx = loadScripts(['config/albero-route.js'], { html: HTML });
  const consoleVera = console.error;
  console.error = () => {};
  ctx.window.fetch = () => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
  await ctx.window.HirisAlberoRoute.mount();
  await tick(0);
  console.error = consoleVera;
  const testo = ctx.document.getElementById('route-outlet').textContent;
  assert.match(testo, /Non è stato possibile leggere l’albero della casa/);
  assert.match(testo, /non significa che la casa sia vuota/);
});

test('wiring: la rotta #/albero e lo script sono registrati nella SPA', () => {
  const configHtml = readFileSync(
    new URL('../../hiris/app/static/config.html', import.meta.url), 'utf8');
  assert.match(configHtml, /static\/config\/albero-route\.js/,
    'config.html deve caricare config/albero-route.js');
  assert.match(configHtml, /href="#\/albero"/, 'deve esistere una voce di navigazione verso #/albero');

  const mainJs = readFileSync(
    new URL('../../hiris/app/static/config/main.js', import.meta.url), 'utf8');
  assert.ok(mainJs.includes('HirisRouter.register(/^#\\/albero\\/?$/'),
    'main.js deve registrare la rotta #/albero presso HirisRouter');
  assert.ok(mainJs.includes('HirisAlberoRoute.mount()'),
    'la rotta registrata deve montare HirisAlberoRoute');
});
