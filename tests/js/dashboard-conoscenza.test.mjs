import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { loadScripts, tick } from './helpers/dom.mjs';

/* La home della configurazione (`#/`) e' «Cosa HIRIS sa»: la faccia di
   GET /api/casa e GET /api/nucleo.

   Cio' che questo file pinna non e' l'impaginazione -- e' l'unica cosa che
   distingue questa pagina da un cruscotto qualunque: i campi di /api/casa
   hanno TRE stati e la pagina li deve rendere in tre modi diversi.
   `null` = «non ho potuto controllare»; `[]`/`{}`/`0` = «ho controllato, non
   c'e' niente». Renderli allo stesso modo -- un `null` che diventa «tutto a
   posto» o «0» -- e' esattamente il difetto che tutto il backend
   dell'anagrafe e' stato scritto per evitare, rimesso dentro dalla porta di
   servizio della UI. */

const HTML = '<!doctype html><body><div id="route-outlet"></div></body>';

/* Una risposta di /api/casa con tutto letto e tutto a posto: la base da cui
   ogni test cambia UN campo, cosi' l'asserzione parla di quel campo solo. */
function casaLetta(modifiche = {}) {
  return Object.assign({
    anagrafe_letta_il: '2026-08-10T09:00:00',
    non_disponibili: [],
    conteggi: { piani: 2, aree: 7, dispositivi: 31, entita: 190 },
    piani: [],
    comportamento: {
      letto_il: '2026-08-10T09:01:00',
      conteggi: { automazione: 12, script: 3 },
      senza_corpo: 0,
      problemi: [],
      file_non_letti: {},
      voci: [],
    },
    plance: { lette_il: '2026-08-10T09:02:00', non_disponibili: [], voci: [] },
  }, modifiche);
}

/* Le DUE forme di «casa non letta», che non sono la stessa cosa. Tenerle
   separate e' il punto: la seconda e' quella che il tester incontra davvero.

   (a) Archivio ASSENTE: tutti i campi a tre stati sono `null`. E' la forma
       letterale del ramo di difesa di `handlers_casa.handle_get_home_space`, che
       dichiara di se stesso (`:25-31`): «difesa, non stato atteso: in
       produzione questo ramo non dovrebbe mai scattare». */
const CASA_ARCHIVIO_ASSENTE = {
  anagrafe_letta_il: null, non_disponibili: null, conteggi: {}, piani: [],
  comportamento: {
    letto_il: null, conteggi: {}, senza_corpo: null,
    problemi: null, file_non_letti: null, voci: [],
  },
  plance: { lette_il: null, non_disponibili: null, voci: [] },
};

/* (b) Archivio ESISTENTE ma mai riempito -- nessuna riga in `meta`. Solo le
       tre DATE tornano `null`; ogni elenco torna vuoto e `senza_corpo` e' un
       `sum()` su zero voci, cioe' `0`:
         non_disponibili()        -> []   (archivio.py:173-183)
         problemi_comportamento() -> []   (:256-268)
         file_non_letti()         -> {}   (:270-281)
         non_disponibili_plance() -> []   (:332-344)
         senza_corpo              -> 0    (handlers_casa.py:75)
       E' lo stato che `server.py:723-733` dichiara per iscritto come ATTESO:
       «un Home Assistant non ancora pronto lascia l'anagrafe vuota con un
       avviso nel log, non fa fallire l'add-on». Cioe': la prima apertura
       della home, su un HA lento o con un token sbagliato. */
const CASA_ARCHIVIO_VUOTO = {
  anagrafe_letta_il: null, non_disponibili: [], conteggi: {}, piani: [],
  comportamento: {
    letto_il: null, conteggi: {}, senza_corpo: 0,
    problemi: [], file_non_letti: {}, voci: [],
  },
  plance: { lette_il: null, non_disponibili: [], voci: [] },
};

/* Le CINQUE frasi che affermano «ho controllato, va tutto bene». Nessuna di
   loro puo' comparire su una lettura mai avvenuta, in NESSUNA delle due
   forme sopra. (La review ne contava quattro nell'intestazione e cinque
   nella resa che ha incollato: sono cinque -- le plance sono la quinta.) */
const FRASI_TUTTO_A_POSTO = [
  /Tutti i registri hanno risposto/,
  /Di ogni voce HIRIS conosce anche il corpo/,
  /Nelle voci lette non c’è nessuna incongruenza/,
  /Tutti i file di automazioni e script sono stati letti/,
  /Tutte le plance hanno risposto/,
];

const NUCLEO_VUOTO = { testo: '', riepilogo: { caratteri: 0, troncato: false, ricordi_esclusi: 0, avvisi: [] } };

/* Monta la pagina con le due risposte date e restituisce il testo reso. */
async function rendi(casa, nucleo = NUCLEO_VUOTO) {
  const ctx = loadScripts(['config/dashboard.js'], { html: HTML });
  const chiamate = [];
  ctx.window.fetch = (url) => {
    const u = String(url);
    chiamate.push(u);
    const corpo = u.indexOf('api/nucleo') !== -1 ? nucleo : casa;
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(corpo) });
  };
  await ctx.window.HirisDashboard.mount();
  await tick(0);
  return { ...ctx, chiamate, testo: ctx.document.getElementById('route-outlet').textContent };
}

test('la pagina legge le due rotte vive, e nessuna delle rotte uscite', async () => {
  const { chiamate } = await rendi(casaLetta());
  assert.ok(chiamate.some((u) => u.includes('api/casa')), 'deve leggere api/casa');
  assert.ok(chiamate.some((u) => u.includes('api/nucleo')), 'deve leggere api/nucleo');
  for (const morta of ['api/chatbots', 'api/brain/', 'api/proposals', 'api/tasks']) {
    assert.equal(chiamate.filter((u) => u.includes(morta)).length, 0,
      `nessuna chiamata a ${morta}: e' una rotta uscita, chiamarla degraderebbe in silenzio`);
  }
});

test("`non_disponibili: null` NON viene reso come «tutto a posto»", async () => {
  const ignoto = await rendi(casaLetta({ non_disponibili: null }));
  const controllato = await rendi(casaLetta({ non_disponibili: [] }));

  assert.doesNotMatch(ignoto.testo, /Tutti i registri hanno risposto/,
    'null non e\' «tutti hanno risposto»: nessuno ha controllato');
  assert.match(ignoto.testo, /Non si sa quali registri/,
    'null deve dire esplicitamente che non si sa');
  assert.match(controllato.testo, /Tutti i registri hanno risposto/,
    '[] invece e\' un controllo avvenuto, e va detto');
});

test('i registri caduti si NOMINANO, non si contano soltanto', async () => {
  const { testo } = await rendi(casaLetta({ non_disponibili: ['piani', 'dispositivi'] }));
  /* Fix round 1: i nomi si leggono in italiano, non col nome grezzo della
     tabella -- il resto della pagina lo e', e questo elenco era l'unico punto
     che mostrava un identificatore tecnico. */
  assert.match(testo, /Registri che non hanno risposto all’ultima lettura:PianiDispositivi/);
  assert.doesNotMatch(testo, /Tutti i registri hanno risposto/);
});

test('il conteggio di un registro caduto NON si stampa: 0 letto e 0 non-letto non si confondono', async () => {
  /* `conteggi` arriva dal backend come `{chiave: len(elenco)}` e NON ha tre
     stati: un registro che non ha risposto ci arriva come 0, uguale a un
     registro letto e vuoto. Il terzo stato ce l'ha `non_disponibili`, che lo
     nomina -- dove i due si incontrano deve vincere il non-letto. */
  const caduto = await rendi(casaLetta({
    non_disponibili: ['piani:timeout'],
    conteggi: { piani: 0, aree: 7 },
  }));
  const tessere = [...caduto.document.querySelectorAll('.stat-tile')]
    .map((t) => t.textContent);
  const piani = tessere.find((t) => t.startsWith('Piani'));
  assert.ok(piani, 'la tessera Piani deve esserci');
  assert.match(piani, /non letto/, 'un registro caduto non vale «0»');
  assert.doesNotMatch(piani, /\b0\b/, 'e il numero non si stampa affatto');
  assert.ok(tessere.some((t) => /^Aree7$/.test(t.replace(/\s/g, ''))),
    'i registri che HANNO risposto restano numeri veri');

  /* Lo stesso 0, ma da un registro che ha risposto: resta 0. */
  const letto = await rendi(casaLetta({ non_disponibili: [], conteggi: { piani: 0 } }));
  const pianiLetto = [...letto.document.querySelectorAll('.stat-tile')]
    .map((t) => t.textContent).find((t) => t.startsWith('Piani'));
  assert.doesNotMatch(pianiLetto, /non letto/);
  assert.match(pianiLetto, /0/);
});

test("un'anagrafe mai letta non si traveste da casa vuota (nessun conteggio a zero)", async () => {
  const { testo, document } = await rendi(CASA_ARCHIVIO_ASSENTE);
  assert.match(testo, /non è ancora stata letta/,
    'deve dire che non ha guardato, non mostrare una casa senza dispositivi');
  assert.doesNotMatch(testo, /Letta il/,
    'nessuna data inventata quando la lettura non c\'e\' stata');

  /* Il conto delle tessere e' la prova che non si inventa nessun numero:
     restano SOLO le tre del nucleo (caratteri/troncato/ricordi esclusi, che
     una fonte ce l'hanno), zero per l'anagrafe e zero per il comportamento. */
  const etichette = [...document.querySelectorAll('.stat-tile .st-label')].map((e) => e.textContent);
  assert.deepEqual(etichette, ['Caratteri', 'Troncato', 'Ricordi esclusi'],
    'nessuna tessera di conteggio su una lettura mai avvenuta');

  const lette = await rendi(casaLetta());
  const etichetteLette = [...lette.document.querySelectorAll('.stat-tile .st-label')].map((e) => e.textContent);
  assert.ok(etichetteLette.includes('Entità') && etichetteLette.includes('Automazioni'),
    'a lettura avvenuta, invece, i conteggi ci sono e vengono dal backend');
});

/* ------------------------------------------------------------------------
   Fix round 1 (review indipendente, Important). Il caso qui sotto e' quello
   che il tester incontra DAVVERO -- archivio esistente e mai riempito -- e
   nel primo giro non era coperto: il file pinnava solo l'archivio ASSENTE,
   che il backend stesso dichiara «non stato atteso». Con gli elenchi vuoti
   che l'archivio restituisce in quel caso, la pagina affermava cinque volte
   «ho controllato, va tutto bene» sulla stessa schermata in cui diceva «non
   ho ancora guardato».
   ------------------------------------------------------------------------ */

test('archivio esistente ma mai riempito: NESSUNA frase «tutto a posto» su una lettura mai avvenuta', async () => {
  const { testo } = await rendi(CASA_ARCHIVIO_VUOTO);

  /* Precondizione: la pagina deve comunque dire che non ha guardato. */
  assert.match(testo, /L’anagrafe non è ancora stata letta/);
  assert.match(testo, /Il comportamento non è ancora stato letto/);
  assert.match(testo, /Le plance non sono ancora state lette/);

  for (const frase of FRASI_TUTTO_A_POSTO) {
    assert.doesNotMatch(testo, frase,
      `«${frase.source}» afferma un controllo che non e' avvenuto: gli ` +
      "elenchi sono vuoti perche' l'archivio non e' mai stato riempito, non " +
      "perche' qualcuno abbia guardato senza trovare niente");
  }

  /* E al loro posto ci deve essere la frase vera, una per campo. */
  assert.match(testo, /Non si sa quali registri abbiano risposto/);
  assert.match(testo, /Non si sa di quante voci HIRIS conosca solo il nome/);
  assert.match(testo, /Non si sa se nelle voci lette ci siano incongruenze/);
  assert.match(testo, /Non si sa quali file di automazioni e script/);
  assert.match(testo, /Non si sa quali plance abbiano risposto/);
});

test('a lettura avvenuta gli stessi elenchi vuoti tornano a significare «tutto a posto»', async () => {
  /* La contro-prova del test qui sopra: senza questa, «non dire mai tutto a
     posto» si potrebbe soddisfare non dicendolo MAI, e il terzo stato
     sparirebbe dal lato opposto. */
  const { testo } = await rendi(casaLetta());
  for (const frase of FRASI_TUTTO_A_POSTO) {
    assert.match(testo, frase,
      `«${frase.source}» deve comparire quando la lettura c'e' stata davvero`);
  }
});

test('il nome di un registro caduto si legge in italiano, e l’ambito non si butta', async () => {
  const { testo } = await rendi(casaLetta({ non_disponibili: ['categorie:script', 'piani'] }));
  assert.match(testo, /Categorie \(ambito «script»\)/,
    'la stringa tecnica «categorie:script» non va mostrata grezza in una pagina in italiano');
  assert.doesNotMatch(testo, /categorie:script/);
  assert.match(testo, /Piani/, 'un registro senza ambito resta il suo nome italiano');
});

test("`senza_corpo: null` non diventa «0», e `0` non diventa «non si sa»", async () => {
  const ignoto = await rendi(casaLetta({
    comportamento: Object.assign(casaLetta().comportamento, { senza_corpo: null }),
  }));
  assert.match(ignoto.testo, /Non si sa di quante voci/);
  assert.doesNotMatch(ignoto.testo, /Di 0 voci/);

  const zero = await rendi(casaLetta());
  assert.match(zero.testo, /Di ogni voce HIRIS conosce anche il corpo/);
  assert.doesNotMatch(zero.testo, /Non si sa di quante voci/);
});

test("`problemi` e `file_non_letti` a null non affermano «nessun problema»", async () => {
  const { testo } = await rendi(casaLetta({
    comportamento: Object.assign(casaLetta().comportamento, { problemi: null, file_non_letti: null }),
  }));
  assert.doesNotMatch(testo, /Nelle voci lette non c’è nessuna incongruenza/);
  assert.doesNotMatch(testo, /Tutti i file di automazioni e script sono stati letti/);
  assert.match(testo, /Non si sa se nelle voci lette ci siano incongruenze/);
  assert.match(testo, /Non si sa quali file/);
});

test('i file non letti si mostrano con la loro RAGIONE, non solo col nome', async () => {
  const { testo } = await rendi(casaLetta({
    comportamento: Object.assign(casaLetta().comportamento, {
      file_non_letti: { 'automations.yaml': 'assente' },
    }),
  }));
  assert.match(testo, /automations\.yaml/);
  assert.match(testo, /assente/);
});

/* ---------------------------------------------------------------------------
   Minor e7 (fetta «fix pre-UAT»): `tessere(corpoComp, ...)` non passava il
   quarto argomento `caduti`, e `conteggi` non porta affatto i tipi che non ha
   contato. Conseguenza vista dal vivo: le tessere «Automazioni» e «Script»
   sparivano invece di dire qualcosa. Su questa pagina, il cui unico scopo e'
   distinguere «non lo so» da «non c'e'», una tessera che sparisce e' il
   difetto-firma del prodotto.
   --------------------------------------------------------------------------- */

/* Le tessere rese, come coppie etichetta/valore leggibili. */
function tessereDi(document) {
  return [...document.querySelectorAll('.stat-tile')].map((t) => ({
    etichetta: t.querySelector('.st-label').textContent,
    valore: t.querySelector('.st-value').textContent,
    delta: t.querySelector('.st-delta') ? t.querySelector('.st-delta').textContent : '',
  }));
}

test('e7: «Script» non sparisce quando la casa non ne ha nessuno — dice 0', async () => {
  const comp = Object.assign(casaLetta().comportamento, { conteggi: { automazione: 12 } });
  const { document } = await rendi(casaLetta({ comportamento: comp }));
  const script = tessereDi(document).find((t) => t.etichetta === 'Script');
  assert.ok(script, 'la tessera Script deve esserci: prima non veniva disegnata affatto');
  assert.equal(script.valore, '0', 'i file sono stati letti: «zero script» è un fatto, e si dice');
});

test('e7: un tipo il cui file non si è letto E il cui conto è a zero dice «non letto», non «0»', async () => {
  const comp = Object.assign(casaLetta().comportamento, {
    conteggi: { automazione: 12 },
    file_non_letti: { 'scripts.yaml': 'assente' },
  });
  const { document, testo } = await rendi(casaLetta({ comportamento: comp }));
  const tessere = tessereDi(document);
  const script = tessere.find((t) => t.etichetta === 'Script');
  assert.equal(script.valore, 'non letto',
    'file non letto e conto a zero: «non c’è niente» e «non ho guardato» sono indistinguibili');
  assert.match(script.delta, /il file non è stato letto/);
  /* e la ragione resta comunque nell'elenco sotto, con il nome del file */
  assert.match(testo, /scripts\.yaml/);
});

test('e7: un file non letto NON cancella le voci che HIRIS conosce comunque dallo stato', async () => {
  /* Le voci arrivano dai file E dallo stato di Home Assistant: con
     automations.yaml assente HIRIS conosce lo stesso dodici automazioni per
     nome (e `senza_corpo` dice di quante ignora il corpo). Marcare quella
     tessera «non letto» nasconderebbe dodici voci vere -- il difetto opposto,
     ugualmente falso. */
  const comp = Object.assign(casaLetta().comportamento, {
    conteggi: { automazione: 12, script: 3 },
    file_non_letti: { 'automations.yaml': 'assente' },
    senza_corpo: 12,
  });
  const { document } = await rendi(casaLetta({ comportamento: comp }));
  const automazioni = tessereDi(document).find((t) => t.etichetta === 'Automazioni');
  assert.equal(automazioni.valore, '12',
    'dodici automazioni note per nome restano dodici: non si nascondono dietro un «non letto»');
});

test('e7: «niente in sospeso» non compare più una riga sopra l’elenco dei file NON letti', async () => {
  const comp = Object.assign(casaLetta().comportamento, {
    problemi: [],
    file_non_letti: { 'automations.yaml': 'assente' },
  });
  const { testo } = await rendi(casaLetta({ comportamento: comp }));
  assert.doesNotMatch(testo, /non ha lasciato niente in sospeso/,
    'si smentiva con la riga successiva, che elenca i file non letti');
  assert.match(testo, /Nelle voci lette non c’è nessuna incongruenza/);
  assert.match(testo, /File non letti, con la ragione:/);
});

test('il nucleo mostra «ciò che HIRIS ignora» con gli avvisi reali del riepilogo', async () => {
  const { testo } = await rendi(casaLetta(), {
    testo: '## La casa\n- una riga',
    riepilogo: { caratteri: 24, troncato: true, ricordi_esclusi: 5, avvisi: ['Il registro dei piani non ha risposto.'] },
  });
  assert.match(testo, /Ciò che HIRIS ignora/);
  assert.match(testo, /Il registro dei piani non ha risposto\./);
  assert.match(testo, /Sì/, 'troncato: true va detto');
  assert.match(testo, /5/, 'i ricordi esclusi sono un numero con una fonte');
});

test('una fetch caduta lo DICHIARA: la sezione non resta muta né finge una casa vuota', async () => {
  const ctx = loadScripts(['config/dashboard.js'], { html: HTML });
  const errori = [];
  const consoleVera = console.error;
  console.error = (...a) => errori.push(a.join(' '));
  ctx.window.fetch = (url) => (String(url).indexOf('api/casa') !== -1
    ? Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) })
    : Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(NUCLEO_VUOTO) }));

  await ctx.window.HirisDashboard.mount();
  await tick(0);
  console.error = consoleVera;

  const testo = ctx.document.getElementById('route-outlet').textContent;
  assert.match(testo, /Non è stato possibile leggere/,
    'la pagina deve dire che non ha potuto leggere');
  assert.match(testo, /non significa che la casa sia vuota/,
    'e deve distinguere il fallimento dall\'assenza di dati');
  assert.equal(errori.length > 0, true, 'il dettaglio tecnico va in console, non a schermo');
});

test('nessun link morto: la home non porta piu\' a #/nuovo ne\' a #/gateway', async () => {
  const { document } = await rendi(casaLetta());
  const href = [...document.querySelectorAll('a')].map((a) => a.getAttribute('href'));
  assert.deepEqual(href.filter((h) => h && h.startsWith('#/')), [],
    'le sole rotte raggiungibili dalla home sono quelle della nav, non link interni a pagine uscite');
  // Il sorgente, non solo il DOM reso: un ramo non percorso da questo test
  // (stato vuoto, errore) potrebbe contenerli lo stesso.
  const sorgente = readFileSync(
    new URL('../../hiris/app/static/config/dashboard.js', import.meta.url), 'utf8');
  for (const morto of ['#/nuovo', '#/gateway', '#/chatbots', '#/agentbots', '#/task', '#/proposte']) {
    assert.equal(sorgente.includes(morto), false, `il sorgente non deve nominare ${morto}`);
  }
});
