import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { loadScripts, tick } from './helpers/dom.mjs';
import { fintoFetch, risposta } from './helpers/fetch.mjs';

/* Reperto 26 (docs/design/2026-08-17-reperti-della-review.md): `GET
   /api/home-space` manda l'albero completo che `anagrafe.gerarchia()` costruisce
   (`casa.piani`), e prima usciva verso nessuna pagina. Questo file pinna la
   pagina #/tree (config/tree-route.js), che lo mostra.

   Ciò che conta qui non è l'impaginazione — è che le SEI cause distinte di
   silenzio che `hierarchy()` dichiara (Senza area / Area sconosciuta / Aree
   non lette / Dispositivi non letti / Senza piano / Piani non letti) restino
   SEI frasi diverse, non un'unica "non si sa" — e che le entità disabilitate
   compaiano sempre, marcate, mai nascoste. */

const HTML = '<!doctype html><body><div id="route-outlet"></div></body>';

function rendi(casa) {
  // `common.js` PRIMA di `config/tree-route.js`, come fa davvero
  // config.html: dal collaudo 3.22 (A10) tree-route.js chiama `fmtDateTime`,
  // condivisa con la pagina Consumi -- non e' piu' un file isolato.
  const ctx = loadScripts(['common.js', 'config/tree-route.js'], { html: HTML });
  const chiamate = fintoFetch(ctx.window, { 'api/home-space': casa });
  return ctx.window.HirisTreeRoute.mount().then(() => {
    ctx.testo = ctx.document.getElementById('route-outlet').textContent;
    ctx.chiamate = chiamate.map((c) => c.url);
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
      sistema_unita: { temperature: '°C', length: 'km' },
    },
    // I nomi delle misure li manda il server (`briefing._MEASUREMENT_NAMES`,
    // C-09): qui una loro parte, quanto basta alla casa di prova.
    nomi_misure: { temperature: 'temperatura', length: 'lunghezza' },
    // Le parole dei registri, dal server (`nomi_registri`, C-10).
    nomi_registri: { piani: 'Piani', aree: 'Aree', categorie: 'Categorie' },
    // I segni del `fuori`, dal server (`segni_fuori`, C-10).
    segni_fuori: {
      disabilitata: '[disabilitata]', nascosta: '[nascosta in Home Assistant]',
      servizio: '[di servizio]',
    },
    piani: [
      {
        id: 'piano_terra', nome: 'Piano terra', livello: 0,
        aree: [
          {
            id: 'cucina', nome: 'Cucina',
            entita_temperatura: 'sensor.temperatura_cucina',
            entita: [
              // La resa media della chat (Tappa 9, F5): le etichette col nome,
              // l'integrazione come riferimento, `fuori` solo quando c'e'.
              { id: 'light.cucina', genere: 'entita', nome: 'Luce cucina', stato: 'on',
                stato_leggibile: 'Acceso', integrazione: { id: 'hue', nome: 'Philips Hue' },
                etichette: ['Da controllare (id: da_controllare)'] },
            ],
            entita_disabilitate: [
              { id: 'sensor.vecchio', genere: 'entita', nome: 'Vecchio sensore cucina',
                integrazione: { id: 'zwave_js', nome: 'Z-Wave' },
                fuori: { classe: 'disabilitata', causa: 'user' } },
            ],
          },
        ],
      },
      {
        id: '__senza_piano__', nome: 'Senza piano', livello: null,
        aree: [
          { id: 'garage', nome: 'Garage', entita: [], entita_disabilitate: [] },
        ],
      },
      {
        id: '__piani_non_letti__', nome: 'Piani non letti', livello: null,
        aree: [
          { id: 'taverna', nome: 'Taverna', entita: [], entita_disabilitate: [] },
        ],
      },
      {
        id: '__fuori_dalle_aree__', nome: 'Fuori dalle aree', livello: null,
        aree: [
          { id: '__aree_non_lette__', nome: 'Aree non lette',
            entita: [{ id: 'sensor.a', nome: 'Entità A' }] },
          { id: '__area_sconosciuta__', nome: 'Area sconosciuta',
            entita: [{ id: 'sensor.b', nome: 'Entità B' }] },
          { id: '__senza_area__', nome: 'Senza area',
            entita: [{ id: 'sensor.c', nome: 'Entità C' }] },
          { id: '__dispositivi_non_letti__', nome: 'Dispositivi non letti',
            entita: [{ id: 'sensor.d', nome: 'Entità D' }] },
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
  // "nascoste fuori dagli elenchi" -- `hierarchy()` toglie le nascoste da
  // `entita` per STRUTTURA (la stessa ragione per cui la chat non le nomina
  // piu' di sua iniziativa), ma questa pagina audita cosa HIRIS sa e non
  // deve far sparire niente: le mostra in `entita_nascoste`, come già fa per
  // `entita_disabilitate`.
  const casa = casaCompleta();
  casa.piani[0].aree[0].entita = [];
  casa.piani[0].aree[0].entita_nascoste = [
    { id: 'light.lampadario_fake', nome: null,
      integrazione: { id: 'ave_domina', nome: 'ave_domina' },
      fuori: { classe: 'nascosta', causa: 'user' } },
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

test('collaudo 3.22 (A9): il plurale del riepilogo è «disabilitate»/«nascoste», non «disabilitatae»/«nascostae»', async () => {
  // Il difetto era `' disabilitata'.concat(n === 1 ? '' : 'e')`: AGGIUNGE la
  // "e" invece di SOSTITUIRE la "a" finale. Con n=1 il ramo `''` la nasconde
  // per caso (singolare corretto per fortuna, non per costruzione) -- serve
  // un conteggio ≥ 2 per farlo vedere, ed è esattamente il caso reale
  // misurato ("Soggiorno — 57 entità, 32 disabilitatae, 5 nascostae").
  const casa = casaCompleta();
  casa.piani[0].aree[0].entita = [];
  casa.piani[0].aree[0].entita_disabilitate = [
    { id: 'sensor.vecchio1', nome: 'Vecchio sensore 1', integrazione: { id: 'zwave', nome: 'zwave' },
      fuori: { classe: 'disabilitata', causa: 'user' } },
    { id: 'sensor.vecchio2', nome: 'Vecchio sensore 2', integrazione: { id: 'zwave', nome: 'zwave' },
      fuori: { classe: 'disabilitata', causa: 'user' } },
  ];
  casa.piani[0].aree[0].entita_nascoste = [
    { id: 'light.nascosta1', nome: 'Nascosta 1', integrazione: { id: 'hue', nome: 'hue' },
      fuori: { classe: 'nascosta', causa: 'user' } },
    { id: 'light.nascosta2', nome: 'Nascosta 2', integrazione: { id: 'hue', nome: 'hue' },
      fuori: { classe: 'nascosta', causa: 'user' } },
  ];
  const { document } = await rendi(casa);
  const sommarioCucina = [...document.querySelectorAll('summary')]
    .find((s) => s.textContent.indexOf('Cucina') === 0);
  assert.ok(sommarioCucina, 'precondizione: l’area Cucina deve essere disegnata');
  assert.match(sommarioCucina.textContent, /2 disabilitate\b/, 'plurale corretto delle disabilitate');
  assert.match(sommarioCucina.textContent, /2 nascoste\b/, 'plurale corretto delle nascoste');
  assert.doesNotMatch(sommarioCucina.textContent, /disabilitatae/, 'mai la "e" aggiunta invece che sostituita');
  assert.doesNotMatch(sommarioCucina.textContent, /nascostae/, 'mai la "e" aggiunta invece che sostituita');
});

test('U2 bis: una pseudo-area («Senza area») mostra le disabilitate/nascoste come un\'area vera', async () => {
  // Collaudo 3.22, misure-del-controllore.md, «U2 bis»: `topology.hierarchy()`
  // smistava le disabilitate/nascoste senza area (o con un'area sconosciuta,
  // o coi registri non letti) in NESSUNA chiave -- sparivano. Il fix le rende
  // raggiungibili nelle stesse chiavi parallele `entita_disabilitate`/
  // `entita_nascoste` che un'area vera porta gia'. Questa pagina non ha
  // bisogno di saperlo: `renderArea`/`entityCountLabel` leggono quelle chiavi
  // da QUALUNQUE area, vera o pseudo -- questa prova lo dimostra invece di
  // darlo per scontato.
  const casa = casaCompleta();
  const senzaArea = casa.piani.find((p) => p.id === '__fuori_dalle_aree__')
    .aree.find((a) => a.id === '__senza_area__');
  senzaArea.entita_disabilitate = [
    { id: 'sensor.orfano_spento', nome: 'Sensore orfano spento', integrazione: { id: 'zwave', nome: 'zwave' },
      fuori: { classe: 'disabilitata', causa: 'user' } },
  ];
  senzaArea.entita_nascoste = [
    { id: 'light.orfano_nascosto', nome: 'Luce orfana nascosta', integrazione: { id: 'hue', nome: 'hue' },
      fuori: { classe: 'nascosta', causa: 'user' } },
  ];
  const { document } = await rendi(casa);
  const sommarioSenzaArea = [...document.querySelectorAll('summary')]
    .find((s) => s.textContent.indexOf('Senza area') === 0);
  assert.ok(sommarioSenzaArea, 'precondizione: la pseudo-area «Senza area» deve essere disegnata');
  // Stesso riepilogo di un'area vera: «N entità, 1 disabilitata, 1 nascosta»
  // -- non un conteggio a parte, non zero perche' non contate.
  assert.match(sommarioSenzaArea.textContent, /1 disabilitata\b/,
    'il riepilogo conta la disabilitata con la stessa label delle aree vere');
  assert.match(sommarioSenzaArea.textContent, /1 nascosta\b/,
    'il riepilogo conta la nascosta con la stessa label delle aree vere');
  const corpo = sommarioSenzaArea.closest('details').textContent;
  assert.match(corpo, /Sensore orfano spento/, 'la disabilitata compare');
  assert.match(corpo, /\[disabilitata\]/, 'marcata come tale');
  assert.match(corpo, /Luce orfana nascosta/, 'la nascosta compare');
  assert.match(corpo, /\[nascosta in Home Assistant\]/, 'marcata come tale');
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

test('collaudo 3.22 (A10): «Letta il» mostra la data nel formato italiano, non l’ISO grezzo in UTC', async () => {
  const { testo } = await rendi(casaCompleta());
  // La stessa funzione che la pagina Consumi già usa (common.js) --
  // non una seconda copia della formattazione. Il difetto misurato era
  // «Letta il 2026-09-07T05:13:52+00:00.», due righe sopra un orario nel
  // fuso di casa: la stessa distanza di due ore che l'Osservatore dichiara
  // altrove.
  // `fmtDateTime` e' un global BARE (common.js non e' un modulo, vedi il suo
  // commento in cima): il ponte di loadScripts() lo specchia su `window`
  // solo per le assegnazioni `window.X = ...`, non per le dichiarazioni di
  // funzione di primo livello -- quindi si legge da `globalThis`, come fa
  // gia' `globalThis.loadUsage()` in chat-usage-widget.test.mjs.
  const atteso = globalThis.fmtDateTime(casaCompleta().anagrafe_letta_il);
  assert.ok(atteso, 'precondizione: fmtDateTime deve produrre qualcosa di leggibile per questa fixture');
  assert.match(testo, /Letta il/);
  assert.doesNotMatch(testo, /Letta il 2026-08-17T09:00:00/,
    'l’ISO grezzo non deve comparire a schermo');
  assert.ok(testo.indexOf('Letta il ' + atteso) >= 0,
    'deve comparire la data formattata da fmtDateTime, non l’ISO grezzo');
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

test('i nomi delle misure arrivano dal server, nel suo ordine; una chiave che non nomina resta grezza', async () => {
  /* C-09 (Tappa 4, Task 5): la pagina non tiene piu' una copia della tabella
     del nucleo. Un nome che solo il server conosce ('calore') deve comparire,
     l'ordine e' quello della mappa e non quello di `sistema_unita`, e una chiave che
     la mappa non nomina compare col suo nome grezzo invece di sparire. */
  const { testo } = await rendi(casaCompleta({
    sistema_di_riferimento: { nome: 'Casa', sistema_unita: { length: 'km', ignota: 'x', temperature: '°C' } },
    nomi_misure: { temperature: 'calore', length: 'lunghezza' },
  }));
  assert.match(testo, /Unità con cui ragiona la casa: calore °C, lunghezza km, ignota x \(/);
});

test("le etichette di un'entità arrivano col nome dal server, e la pagina non le traduce", async () => {
  /* Fino alla Tappa 9 (F5) la pagina riceveva gli id e una mappa id -> nome
     (`casa.etichette`) e li traduceva da se'. Ora l'entita' e' la resa media
     della chat: le etichette arrivano gia' «Nome (id: X)», e la mappa non
     esce piu'. */
  const { testo } = await rendi(casaCompleta());
  assert.match(testo, /etichette: Da controllare \(id: da_controllare\)/);
  assert.doesNotMatch(testo, /I nomi delle etichette non sono stati letti/,
    'la frase della mappa mancante esce con la mappa');
});

test('lo stato sta accanto al nome: le parole di Home Assistant, o il valore con la sua unità', async () => {
  /* D1 della F5 (disegno dello ux-ui-specialist): «· 21,5 °C» dopo il nome e
     prima dell'id; l'unita' scritta accanto allo stato non si ripete nella
     riga dei dettagli; senza stato non si scrive niente, nemmeno «—». */
  const casa = casaCompleta();
  casa.piani[0].aree[0].entita.push(
    { id: 'sensor.temperatura_cucina', nome: 'Temperatura cucina', stato: '21.5', unita: '°C',
      classe: 'temperature' },
    { id: 'sensor.muto', nome: 'Sensore muto', unita: 'W' });
  const { document, testo } = await rendi(casa);
  const riga = (id) => [...document.querySelectorAll('#route-outlet li')]
    .find((li) => li.textContent.includes('(' + id + ')')).textContent;
  assert.match(riga('light.cucina'), /Luce cucina · Acceso \(light\.cucina\)/,
    'le parole di Home Assistant al posto del grezzo');
  const termometro = riga('sensor.temperatura_cucina');
  assert.match(termometro, /Temperatura cucina · 21\.5 °C \(sensor\.temperatura_cucina\)/);
  assert.doesNotMatch(termometro, /unità °C/, 'l’unità dello stato non si ripete');
  const muto = riga('sensor.muto');
  assert.doesNotMatch(muto, /·\s*\(/, 'senza stato nessun segno davanti all’id');
  assert.match(muto, /unità W/, 'senza stato l’unità resta fra i dettagli');
  assert.match(testo, /Gli stati mostrati sono quelli dell’ultimo aggiornamento, non quelli di adesso/);
});

test('il segno del `fuori` usa le parole di oggi, e «[di servizio]» per le entità di servizio', async () => {
  /* Scelta del proprietario, 12/10/2026 («Parole di oggi»): nessun termine
     nuovo. La categoria di Home Assistant e' la causa del `fuori` di
     servizio, e il riepilogo dell'area conta le entita' di servizio. */
  const casa = casaCompleta();
  casa.piani[0].aree[0].entita.push(
    { id: 'sensor.segnale', nome: 'Segnale', fuori: { classe: 'servizio', causa: 'diagnostic' },
      integrazione: { id: 'shelly', nome: 'Shelly' } },
    { id: 'sensor.strano', nome: 'Strano', fuori: { classe: 'nuova_classe', causa: null } });
  const { document, testo } = await rendi(casa);
  const riga = (id) => [...document.querySelectorAll('#route-outlet li')]
    .find((li) => li.textContent.includes('(' + id + ')')).textContent;
  assert.match(riga('sensor.segnale'), /\[di servizio\]/);
  assert.match(testo, /Le entità «di servizio» sono quelle che Home Assistant tiene/,
    'il segno si spiega una volta');
  const senza = (await rendi(casaCompleta())).testo;
  assert.doesNotMatch(senza, /Le entità «di servizio»/, 'senza entità di servizio la riga non c’è');
  assert.match(riga('sensor.segnale'), /integrazione Shelly · categoria diagnostic/);
  assert.match(riga('sensor.vecchio'), /\[disabilitata\]/);
  assert.match(riga('sensor.strano'), /\[nuova_classe\]/, 'una classe sconosciuta non sparisce');
  assert.doesNotMatch(riga('light.cucina'), /\[/, 'un’entità visibile non porta segni');
  const sommario = [...document.querySelectorAll('summary')]
    .find((x) => x.textContent.indexOf('Cucina') === 0).textContent;
  assert.match(sommario, /3 entità, 1 disabilitata, 1 di servizio/);
});

test('i registri caduti dicono di quando è la copia che HIRIS usa al loro posto', async () => {
  const { testo } = await rendi(casaCompleta({
    non_disponibili: ['piani', 'aree'],
    non_disponibili_letti_il: { piani: '2026-10-03T12:20:00+00:00', aree: null },
  }));
  const quando = globalThis.fmtDateTime('2026-10-03T12:20:00+00:00');
  assert.ok(testo.includes('Piani — HIRIS usa la copia del ' + quando + '.'), testo);
  assert.ok(testo.includes('Aree — nessuna copia disponibile, mai letto.'), testo);
});

test('il confronto con Home Assistant: mai fatto, combacia, diverge, non si è potuto fare', async () => {
  const mai = (await rendi(casaCompleta({ confronto: null }))).testo;
  assert.match(mai, /Mai confrontato: HIRIS non ha ancora verificato il suo albero/);

  const letto = '2026-10-12T10:00:00+00:00';
  const uguale = (await rendi(casaCompleta({ confronto: { aree_totali: 16, letto_il: letto,
    guardate: [{ area: 'cucina', nome: 'Cucina', mancanti: [], in_piu: [], assente_in_ha: false }] } }))).testo;
  assert.ok(uguale.includes('Confronto del ' + globalThis.fmtDateTime(letto) +
    ': controllata 1 area su 16.'), uguale);
  assert.match(uguale, /Tutto combacia: in queste aree/);
  assert.doesNotMatch(uguale, /tutta la casa/);

  const tanti = Array.from({ length: 12 }, (_, i) => 'sensor.x' + i);
  const diverge = (await rendi(casaCompleta({ confronto: { aree_totali: 16, letto_il: letto,
    guardate: [
      { area: 'cucina', nome: 'Cucina', mancanti: ['sensor.nuovo'], in_piu: ['light.cucina'],
        assente_in_ha: false },
      { area: 'cantina', nome: 'Cantina', mancanti: [], in_piu: [], assente_in_ha: true },
      { area: 'sala', nome: 'Sala', mancanti: tanti, in_piu: [], assente_in_ha: false },
      { area: 'bagno', nome: 'Bagno', errore: 'Home Assistant non ha risposto' },
    ] } }))).testo;
  assert.match(diverge, /controllate 4 aree su 16/);
  assert.match(diverge, /In 3 aree l’albero di HIRIS non combacia con Home Assistant:/);
  assert.match(diverge, /Cucina — HIRIS ha in più: Luce cucina; gli manca: sensor\.nuovo\./,
    'le entità per nome quando l’albero le conosce, per id altrimenti');
  assert.match(diverge, /Cantina — non esiste più in Home Assistant\./);
  assert.match(diverge, /Sala — gli manca: sensor\.x0, .*sensor\.x9 e altre 2\./);
  assert.match(diverge, /Aree che non si sono potute controllare:/);
  assert.match(diverge, /Bagno — Home Assistant non ha risposto\./);
  assert.doesNotMatch(diverge, /Tutto combacia/);

  const vuoto = (await rendi(casaCompleta({ confronto: { aree_totali: 0, guardate: [] } }))).testo;
  assert.match(vuoto, /Il confronto non ha avuto aree da controllare/);
  const errore = (await rendi(casaCompleta({ confronto: { errore: 'rete giù' } }))).testo;
  assert.match(errore, /Il confronto non si è potuto fare: rete giù\./);
});

test('una fetch caduta lo dichiara: niente casa vuota travestita da silenzio', async () => {
  const ctx = loadScripts(['common.js', 'config/tree-route.js'], { html: HTML });
  const consoleVera = console.error;
  console.error = () => {};
  fintoFetch(ctx.window, { 'api/home-space': risposta({}, 500) });
  await ctx.window.HirisTreeRoute.mount();
  await tick(0);
  console.error = consoleVera;
  const testo = ctx.document.getElementById('route-outlet').textContent;
  assert.match(testo, /Non è stato possibile leggere l’albero della casa/);
  assert.match(testo, /non significa che la casa sia vuota/);
});

test('wiring: la rotta #/tree e lo script sono registrati nella SPA', () => {
  const configHtml = readFileSync(
    new URL('../../hiris/app/static/config.html', import.meta.url), 'utf8');
  assert.match(configHtml, /static\/config\/tree-route\.js/,
    'config.html deve caricare config/tree-route.js');
  assert.match(configHtml, /href="#\/tree"/, 'deve esistere una voce di navigazione verso #/tree');

  const mainJs = readFileSync(
    new URL('../../hiris/app/static/config/main.js', import.meta.url), 'utf8');
  assert.ok(mainJs.includes('HirisRouter.register(/^#\\/tree\\/?$/'),
    'main.js deve registrare la rotta #/tree presso HirisRouter');
  assert.ok(mainJs.includes('HirisTreeRoute.mount()'),
    'la rotta registrata deve montare HirisTreeRoute');
});

/* `translation_key` (fetta «il comportamento dal vivo», 10/09/2026): e' cio'
   che l'INTEGRAZIONE dichiara di se' su quell'entita' -- `energy_generating_
   today`, `battery_soc`, `carbon_monoxide` -- ed e' il campo su cui si regge
   lo sprint: e' quello che permette di capire che «Potenza autoconsumata» e'
   la produzione fotovoltaica e non il consumo di una presa.

   Fino a questa fetta l'anagrafe lo buttava via. Misurato sulla casa vera:
   presente su 526 delle 804 entita' visibili nell'albero. */

test('il translation_key sta su una riga sua, non impastato coi dettagli tecnici', async () => {
  const { document } = await rendi({
    anagrafe_letta_il: '2026-09-10T17:00:00+00:00', non_disponibili: [],
    piani: [{ id: 'terra', nome: 'Terra', aree: [{ id: 'cucina', nome: 'Cucina', entita: [
      { id: 'sensor.solare', nome: 'Energia prodotta', integrazione: { id: 'zcsazzurro', nome: 'ZCS' },
        classe: 'energy', unita: 'kWh', translation_key: 'energy_generating_today' },
    ] }] }],
  });
  const righe = [...document.querySelectorAll('#route-outlet li')]
    .map((li) => [...li.querySelectorAll('div')].map((d) => d.textContent));
  const [dettagli] = righe.filter((r) => r.some((t) => t.includes('classe energy')));

  /* La riga a «·» raccoglie fatti di classificazione -- vocabolari chiusi,
     valori brevi. `translation_key` e' l'autodichiarazione semantica
     dell'integrazione: un genere diverso, e fino a 37 caratteri misurati.
     Impastarli sarebbe due cose diverse dette con lo stesso trattamento. */
  const riga = dettagli.find((t) => t.includes('classe energy'));
  assert.doesNotMatch(riga, /energy_generating_today/,
    'la chiave non va dentro la riga dei dettagli separati da «·»');
  assert.ok(dettagli.some((t) => t.includes('translation_key energy_generating_today')),
    'la chiave sta su una riga sua, con la sua etichetta non tradotta');
});

test('dove il translation_key non c’è, la riga non compare affatto', async () => {
  const { testo } = await rendi({
    anagrafe_letta_il: '2026-09-10T17:00:00+00:00', non_disponibili: [],
    piani: [{ id: 'terra', nome: 'Terra', aree: [{ id: 'cucina', nome: 'Cucina', entita: [
      { id: 'light.lampadario', nome: 'Lampadario', integrazione: { id: 'ave_domina', nome: 'ave_domina' } },
    ] }] }],
  });
  /* Su 331 entita' di questa casa il campo non c'e'. Un «translation_key: —»
     su ognuna sarebbe rumore che copre le 526 che dicono qualcosa: si tace,
     come gia' fanno alias ed etichette. */
  assert.doesNotMatch(testo, /translation_key/);
});
