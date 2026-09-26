import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import fs from 'node:fs';
import { installaFogli, displayRisolto } from './helpers/dom.mjs';

const SORGENTE = fs.readFileSync(
  new URL('../../hiris/app/static/config/constructions-route.js', import.meta.url), 'utf8');

function montaCon(risposta) {
  const dom = new JSDOM('<div id="route-outlet"></div>', { url: 'http://localhost/' });
  global.window = dom.window;
  global.document = dom.window.document;
  const chiamate = [];
  dom.window.fetch = async (url, opzioni) => {
    chiamate.push([url, opzioni]);
    return { ok: true, status: 200, json: async () => risposta };
  };
  global.fetch = dom.window.fetch;
  new dom.window.Function(SORGENTE)();
  return { dom, chiamate };
}

test('le proposte in attesa hanno il bottone di conferma, le applicate no', async () => {
  const { dom } = montaCon({ constructions: [
    { id: 'p1', stato: 'in_attesa', gesto: 'crea', dominio: 'automation',
      chiave: '1771', anteprima: 'Creo un automazione', prima: null,
      dopo: { alias: 'Tapparelle' }, creata_ts: 1756000000 },
    { id: 'c1', stato: 'applicata', gesto: 'modifica', dominio: 'automation',
      chiave: '1772', anteprima: '', prima: { alias: 'vecchio' },
      dopo: { alias: 'nuovo' }, creata_ts: 1756000000 },
  ] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  const testo = dom.window.document.body.textContent;
  assert.match(testo, /Tapparelle/);
  const conferme = dom.window.document.querySelectorAll('[data-azione="confirm"]');
  assert.equal(conferme.length, 1);
});

test('una modifica a un oggetto non creato da HIRIS lo dichiara', async () => {
  // La regola l'ha posta il proprietario con parole sue -- "se tocca
  // qualcosa lo deve dire" -- ed e' il testo esatto sotto, non il badge
  // "Modificata" (`/modificat/i`): quel badge compare per OGNI gesto di
  // modifica, riuscita o no, e cancellando `eraGiaLi()` insieme alla riga
  // "Questo oggetto esiste già in casa tua" la vecchia asserzione restava
  // verde (ondata finale, punto 4 -- il difetto n.1: un test che non puo'
  // fallire). Una `create`, per contrasto, non deve MAI portare questa
  // dichiarazione: non ha toccato niente che esistesse gia'.
  const { dom } = montaCon({ constructions: [
    { id: 'c1', stato: 'applicata', gesto: 'modifica', dominio: 'automation',
      chiave: '1772', anteprima: '', prima: { alias: 'la tua automazione' },
      dopo: { alias: 'modificata' }, creata_ts: 1756000000 },
    { id: 'p1', stato: 'in_attesa', gesto: 'crea', dominio: 'automation',
      chiave: '1773', anteprima: '', prima: null,
      dopo: { alias: 'nuova' }, creata_ts: 1756000000 },
  ] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  const document = dom.window.document;
  const storico = document.getElementById('constructions-history-body');
  const aperte = document.getElementById('constructions-open-body');
  assert.match(storico.textContent, /Questo oggetto esiste già in casa tua\./);
  assert.doesNotMatch(aperte.textContent, /esiste già/);
});

test('il sorgente non usa innerHTML, in nessuna forma', () => {
  // RULING 3 della scansione pre-volo: la versione precedente di questo test
  // cercava una regex cosi' specifica da non poter fallire su nessuna
  // scrittura realistica -- il difetto n.1 di questo progetto.
  // Un divieto netto e' piu' forte di un'ipotesi: alias e anteprime nascono da
  // una chat, e una chat puo' contenere markup. Se un giorno servira'
  // `innerHTML` su una costante nostra, questo test si cambia CON un motivo
  // scritto accanto -- che e' esattamente la conversazione che deve avvenire.
  assert.doesNotMatch(SORGENTE, /innerHTML/);
});

test('una proposta in attesa offre sia Approva sia Rifiuta', async () => {
  const { dom } = montaCon({ constructions: [
    { id: 'p1', stato: 'in_attesa', gesto: 'crea', dominio: 'automation',
      chiave: '1', anteprima: 'x', prima: null, dopo: {}, creata_ts: 1 },
  ] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  assert.equal(dom.window.document.querySelectorAll('[data-azione="confirm"]').length, 1);
  assert.equal(dom.window.document.querySelectorAll('[data-azione="reject"]').length, 1);
});

test('il no di chi costruisce non si mostra come un fallimento', async () => {
  // `disdetta` e `rifiutata` sono due cose diverse e non devono leggersi
  // uguali: la prima e' la persona che ha deciso, la seconda e' HIRIS che non
  // ce l'ha fatta. Se il vocabolario le confondesse, la pagina punirebbe
  // l'unica cosa che deve essere facile fare.
  const { dom } = montaCon({ constructions: [
    { id: 'd1', stato: 'disdetta', gesto: 'crea', dominio: 'automation',
      chiave: '1', anteprima: '', prima: null, dopo: {}, creata_ts: 1,
      motivo: 'rifiutata dalla pagina' },
    { id: 'r1', stato: 'rifiutata', gesto: 'crea', dominio: 'automation',
      chiave: '2', anteprima: '', prima: null, dopo: {}, creata_ts: 1,
      motivo: 'Home Assistant ha rifiutato' },
  ] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  const testo = dom.window.document.body.textContent;
  assert.doesNotMatch(testo, /disdetta|rifiutata\b/i,
    'gli stati interni non devono uscire come token grezzi');
  const righe = dom.window.document.querySelectorAll('.construction');
  assert.notEqual(righe[0].className, righe[1].className,
    'il no della persona e il fallimento di HIRIS non possono avere la stessa faccia');
});

test('una riga «disdetta» col vecchio motivo (righe scritte prima del 26/09/2026) resta un no, non un fallimento', async () => {
  // Sicurezza 5.5, fix round 1: `revisions.py::_migration_3` riscrive UNA
  // volta le righe vecchie (dal letterale "rifiutata dal proprietario" alla
  // costante `REASON_DISDETTA`, "rifiutata dalla pagina") aprendo
  // l'archivio -- ma un archivio non ancora aggiornato, o una riga letta
  // prima che la migrazione giri, porta ancora il vecchio testo. Questa
  // pagina non lo riscrive e non lo distingue dal nuovo: nasconde `motivo`
  // guardando lo STATO (`disdetta`), mai il testo -- quindi il valore
  // vecchio deve rendere ESATTAMENTE come il nuovo, con entrambi i
  // letterali provati qui uno accanto all'altro.
  const { dom } = montaCon({ constructions: [
    { id: 'd1', stato: 'disdetta', gesto: 'crea', dominio: 'automation',
      chiave: '1', anteprima: '', prima: null, dopo: {}, creata_ts: 2,
      motivo: 'rifiutata dal proprietario' },
    { id: 'd2', stato: 'disdetta', gesto: 'crea', dominio: 'automation',
      chiave: '2', anteprima: '', prima: null, dopo: {}, creata_ts: 1,
      motivo: 'rifiutata dalla pagina' },
  ] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  const testo = dom.window.document.body.textContent;
  assert.doesNotMatch(testo, /disdetta|rifiutata\b|proprietario/i,
    'ne\' lo stato interno ne\' il vecchio motivo devono uscire come testo grezzo');
  const righe = dom.window.document.querySelectorAll('.construction');
  assert.equal(righe.length, 2);
  assert.equal(righe[0].className, righe[1].className,
    'vecchio e nuovo motivo devono avere la stessa faccia: sono entrambi un no, non un fallimento');
});

test('solo le costruzioni applicate offrono il ripristino', async () => {
  const { dom } = montaCon({ constructions: [
    { id: 'p1', stato: 'in_attesa', gesto: 'crea', dominio: 'automation',
      chiave: '1', anteprima: 'x', prima: null, dopo: {}, creata_ts: 1 },
  ] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  assert.equal(dom.window.document.querySelectorAll('[data-azione="restore"]').length, 0);
});

test('una scena mostra il conteggio e gli entity_id anche se `entities` è un dizionario', async () => {
  // Rilievo della review: `forme.py::compose_scene` (e Home Assistant per
  // `prima`) rappresentano `entities` di una scena come un DIZIONARIO
  // entity_id -> attributi, non un array come per automazioni/script.
  // `{}.length` in JS è `undefined`, non `0`: senza gestire questa forma il
  // pannello mostrava "entità: undefined" e gli entity_id non comparivano
  // mai -- proprio per il dominio in cui quella lista è tutto il contenuto
  // dell'oggetto (guida §3).
  const { dom } = montaCon({ constructions: [
    { id: 's1', stato: 'applicata', gesto: 'modifica', dominio: 'scene',
      chiave: 'scena_sera', anteprima: '',
      prima: { alias: 'Scena sera', entities: { 'light.cucina': { state: 'on' } } },
      dopo: { alias: 'Scena sera', entities: {
        'light.cucina': { state: 'on' }, 'light.salotto': { state: 'off' } } },
      creata_ts: 1 },
  ] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  const document = dom.window.document;
  const dettagli = Array.from(document.querySelectorAll('button'))
    .find((b) => b.textContent === 'Dettagli tecnici');
  assert.ok(dettagli, 'la card deve avere il rivelatore dei dettagli tecnici');
  dettagli.dispatchEvent(new dom.window.Event('click', { bubbles: true }));

  const testo = document.body.textContent;
  assert.doesNotMatch(testo, /undefined/,
    '{}.length e\' undefined in JS, non 0: un dizionario non trattato come tale lo fa trapelare');
  assert.match(testo, /entità: 1 → 2/,
    'il conteggio deve leggere le CHIAVI del dizionario, non .length su un dizionario');
  assert.match(testo, /light\.cucina/);
  assert.match(testo, /light\.salotto/);
});

/* ── Lo storico chiuso (fetta «i menu esecutivi») ──────────────────────────
 *
 * Gemelle delle due prove in `agenda-route.test.mjs`, e per la stessa
 * ragione: lo storico e' un registro di consultazione, e lasciarlo aperto
 * sotto la sezione che aspetta una decisione fa scorrere via proprio quella.
 * Il conteggio si sa solo dopo la fetch, quindi si asserisce dopo `mount()`.
 */

test('lo storico nasce chiuso, col conteggio nel titolo', async () => {
  const { dom } = montaCon({ constructions: [
    { id: 'a1', stato: 'applicata', gesto: 'crea', dominio: 'automation',
      chiave: '1', anteprima: '', prima: null, dopo: {}, creata_ts: 1 },
    { id: 's1', stato: 'scaduta', gesto: 'crea', dominio: 'script',
      chiave: '2', anteprima: '', prima: null, dopo: {}, creata_ts: 2 },
    // Una in attesa: non conta nello storico, e la sua presenza e' cio' che
    // rende il conteggio (2) diverso dal totale (3) -- senza di lei un
    // `all.length` sbagliato passerebbe lo stesso.
    { id: 'p1', stato: 'in_attesa', gesto: 'crea', dominio: 'automation',
      chiave: '3', anteprima: 'x', prima: null, dopo: {}, creata_ts: 3 },
  ] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  const document = dom.window.document;
  /* I fogli VERI della pagina, e non `.hidden`. La versione precedente di
     questa prova asseriva la proprieta' IDL, che dice solo «l'attributo c'e'»:
     era verde mentre lo storico nasceva in piena vista, perche'
     `.section-card .sc-body { display: flex }` (hiris-config.css) e' una
     dichiarazione d'autore e batteva la regola `[hidden]` dello user agent.
     `displayRisolto()` non e' `getComputedStyle`: la cascata di jsdom ignora
     `!important` e la specificita' -- helpers/dom.mjs lo misura e lo spiega. */
  installaFogli(document);

  const storico = document.querySelector('[data-sezione="history"]');
  assert.equal(displayRisolto(storico), 'none', 'lo storico nasce chiuso, e non si vede');
  assert.equal(storico.hidden, true, 'ed e\' `hidden` che lo chiude, non una classe a parte');
  const bottone = document.querySelector('#constructions-history-toggle');
  assert.ok(bottone, 'l\'intestazione dello storico deve essere un bottone');
  assert.equal(bottone.getAttribute('aria-expanded'), 'false');
  assert.match(bottone.textContent, /Storico \(2\)/);
  const aperte = document.querySelector('[data-sezione="open"]');
  assert.notEqual(displayRisolto(aperte), 'none',
    '«In attesa» non si chiude: e\' la domanda con cui si apre la pagina');
});

test('lo storico si apre con un click, e il bottone lo dice', async () => {
  const { dom } = montaCon({ constructions: [
    { id: 'a1', stato: 'applicata', gesto: 'crea', dominio: 'automation',
      chiave: '1', anteprima: '', prima: null, dopo: {}, creata_ts: 1 },
  ] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  const document = dom.window.document;
  installaFogli(document);

  const bottone = document.querySelector('#constructions-history-toggle');
  bottone.dispatchEvent(new dom.window.Event('click', { bubbles: true }));

  assert.equal(displayRisolto(document.querySelector('[data-sezione="history"]')), 'flex',
    'aperto, si vede davvero');
  assert.equal(bottone.getAttribute('aria-expanded'), 'true');
});

test('durante una richiesta in volo Approva e Rifiuta si disabilitano insieme', async () => {
  // Rilievo della review: il backend regge un doppio clic (la UPDATE e'
  // atomica), ma restava un'incoerenza visibile -- premuto Approva, Rifiuta
  // rimaneva cliccabile mentre la richiesta girava ancora. La `fetch` per la
  // conferma qui NON si risolve mai (`new Promise(() => {})`): e' l'unico
  // modo di osservare lo stato "in volo", non quello dopo -- lo stub di
  // `montaCon`, che risponde subito, non lo permetterebbe.
  const dom = new JSDOM('<div id="route-outlet"></div>', { url: 'http://localhost/' });
  global.window = dom.window;
  global.document = dom.window.document;
  dom.window.fetch = async (url, _opzioni) => {
    if (String(url).indexOf('/confirm') !== -1) return new Promise(() => {});
    return { ok: true, status: 200, json: async () => ({ constructions: [
      { id: 'p1', stato: 'in_attesa', gesto: 'crea', dominio: 'automation',
        chiave: '1', anteprima: 'x', prima: null, dopo: {}, creata_ts: 1 },
    ] }) };
  };
  global.fetch = dom.window.fetch;
  new dom.window.Function(SORGENTE)();

  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  const conferma = dom.window.document.querySelector('[data-azione="confirm"]');
  const rifiuta = dom.window.document.querySelector('[data-azione="reject"]');
  conferma.dispatchEvent(new dom.window.Event('click', { bubbles: true }));

  // Nessun await qui: la disabilitazione avviene sincrona dentro il
  // gestore del click (`executeAction` disabilita PRIMA di chiamare fetch),
  // quindi si asserisce subito, prima di qualunque flush di microtask.
  assert.equal(conferma.disabled, true, 'il bottone premuto si disabilita');
  assert.equal(rifiuta.disabled, true,
    'il gemello deve disabilitarsi insieme, non restare cliccabile mentre la richiesta è in volo');
});


/* -------------------------------------------------------------------------
   Le proposte DA FARE A MANO (spec 2026-09-21 §3).

   «Un posto solo dove si decide» e' una promessa sulla PAGINA: i due archivi
   restano due, l'elenco e' uno, e un campo dice chi la applica.
   ------------------------------------------------------------------------- */

function propostaAMano(extra) {
  return Object.assign({
    id: 'm1', stato: 'attesa', a_mano: true, chi_applica: 'tu',
    testo: 'Sposta la lavatrice nel primo pomeriggio',
    perche: 'il prelievo dalla rete si concentra la mattina',
    giri: [], creata_ts: 1756000100,
  }, extra || {});
}

test('una proposta da fare a mano si legge, e dice che la fai tu', async () => {
  /* Mutazione che la uccide: disegnare solo le costruibili -- la riga sparisce
     dalla pagina pur essendo nella risposta. */
  const { dom } = montaCon({ constructions: [propostaAMano()] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));

  const testo = dom.window.document.body.textContent;
  assert.match(testo, /Sposta la lavatrice nel primo pomeriggio/);
  assert.match(testo, /il prelievo dalla rete/, 'il perche\' sta accanto alla proposta');
  assert.match(testo, /la fai tu/i, 'chi la applica non si legge');
});

test('una proposta a mano ha TRE comandi, e nessun «Approva»', async () => {
  /* «Crea» non si applica: non c'e' niente da scrivere in Home Assistant.
     Mutazione che la uccide: riusare i bottoni dell'officina. */
  const { dom } = montaCon({ constructions: [propostaAMano()] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));

  const testi = [...dom.window.document.querySelectorAll('button')].map((b) => b.textContent);
  assert.ok(testi.some((t) => /Rifiuta/.test(t)));
  assert.ok(testi.some((t) => /fatta|fatto/i.test(t)), 'manca «l\'ho fatta io»');
  assert.ok(testi.some((t) => /Rifalla/.test(t)));
  assert.ok(!testi.some((t) => /Approva/.test(t)), '«Approva» su una cosa che HIRIS non scrive');
});

test('«l’ho fatta io» chiama la rotta delle proposte, non quella dell’officina', async () => {
  /* Due archivi, due porte: chiamare `/api/constructions/...` con l'id di una
     proposta a mano darebbe un 404, e la pagina direbbe «non esiste» su una
     riga che sta guardando.
     Mutazione che la uccide: riusare `actionButton`. */
  const { dom, chiamate } = montaCon({ constructions: [propostaAMano()] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  const fatta = [...dom.window.document.querySelectorAll('button')]
    .filter((b) => /fatta|fatto/i.test(b.textContent))[0];
  fatta.click();
  await new Promise((r) => setTimeout(r, 0));

  const indirizzi = chiamate.map((c) => String(c[0]));
  assert.ok(indirizzi.some((u) => /api\/proposals\/m1\/done/.test(u)),
    'chiamate: ' + JSON.stringify(indirizzi));
});

test('«Rifalla» apre un campo di testo, e manda quello che scrivi', async () => {
  /* La decisione del proprietario: «Rifalla apre un testo con le richieste di
     modifica e si ripete il turno, senza limiti».
     Mutazione che la uccide: mandare la richiesta vuota. */
  const { dom, chiamate } = montaCon({ constructions: [propostaAMano()] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  const rifalla = [...dom.window.document.querySelectorAll('button')]
    .filter((b) => /Rifalla/.test(b.textContent))[0];
  rifalla.click();

  const campo = dom.window.document.querySelector('textarea');
  assert.ok(campo, 'nessun campo di testo: «Rifalla» chiederebbe di rifare la stessa cosa');
  campo.value = 'troppo presto, dopo le 14';
  const manda = [...dom.window.document.querySelectorAll('button')]
    .filter((b) => /Rifalla adesso|Manda/i.test(b.textContent))[0];
  assert.ok(manda, 'manca il bottone che manda la richiesta');
  manda.click();
  await new Promise((r) => setTimeout(r, 0));

  const chiamata = chiamate.filter((c) => /redo/.test(String(c[0])))[0];
  assert.ok(chiamata, 'la richiesta non e\' partita');
  assert.match(String(chiamata[1].body), /troppo presto/);
});

test('il filo dei giri si legge sotto la proposta', async () => {
  /* Chi guarda deve poter vedere cosa ha gia' scartato: senza, al terzo giro
     non si ricorda piu' cosa aveva chiesto.
     Mutazione che la uccide: non disegnare i giri. */
  const { dom } = montaCon({ constructions: [propostaAMano({ giri: [
    { richiesta: 'troppo presto, dopo le 14', scartata: 'Sposta la lavatrice la mattina',
      quando_ts: 1756000200 }] })] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));

  const testo = dom.window.document.body.textContent;
  assert.match(testo, /troppo presto, dopo le 14/);
  assert.match(testo, /Sposta la lavatrice la mattina/);
});

/* --- B-4: il pannello dice COSA chiamera', non quante cose -------------- */

async function pannelloDi(extra) {
  const { dom } = montaCon({ constructions: [Object.assign({
    id: 'b4', stato: 'in_attesa', gesto: 'modifica', dominio: 'automation',
    chiave: 'buonanotte', anteprima: '',
    prima: { alias: 'Buonanotte' }, dopo: { alias: 'Buonanotte' },
    creata_ts: 1,
  }, extra)] });
  await dom.window.HirisConstructions.mount(
    dom.window.document.getElementById('route-outlet'));
  const document = dom.window.document;
  const rivelatore = Array.from(document.querySelectorAll('button'))
    .find((b) => b.textContent === 'Dettagli tecnici');
  assert.ok(rivelatore, 'la card deve avere il rivelatore dei dettagli tecnici');
  rivelatore.dispatchEvent(new dom.window.Event('click', { bubbles: true }));
  return document.body.textContent;
}

test('dettagli tecnici: le chiamate NUOVE si dicono, e per prime', async () => {
  /* **Il reperto B-4.** Il pannello mostrava «azioni: 2 -> 3»: conteggi. Uno
     `shell_command` dentro il corpo passa la validazione di Home Assistant --
     e' valido -- e crea un oggetto permanente che chiama un servizio che la
     porta diretta non avrebbe potuto chiamare. Il si' c'era; era
     disinformato.

     Mutazione ESEGUITA: tolta `servicesLines` dal pannello -- rossa. */
  const testo = await pannelloDi({
    chiama_prima: ['light.turn_on'],
    chiama_dopo: ['light.turn_on', 'shell_command.riavvia'],
  });

  assert.match(testo, /Chiamate NUOVE: shell_command\.riavvia/);
});

test('e se non cambia niente, non si grida al nuovo', async () => {
  /* Un avviso che compare sempre smette di essere un avviso.
     Mutazione: mostrare sempre la riga -- rossa. */
  const testo = await pannelloDi({
    chiama_prima: ['light.turn_on'], chiama_dopo: ['light.turn_on'],
  });

  assert.doesNotMatch(testo, /Chiamate NUOVE/);
  assert.match(testo, /Chiama: light\.turn_on/);
});

test('una proposta che non chiama niente non inventa una riga', async () => {
  /* Una scena non chiama servizi: scrivere l'etichetta seguita da niente
     sarebbe rumore che insegna a saltare la riga.
     Mutazione: scrivere sempre l'etichetta -- rossa. */
  const testo = await pannelloDi({ chiama_prima: [], chiama_dopo: [] });

  assert.doesNotMatch(testo, /Chiama/);
});

/* ── Da quale porta è passato il giro (reperto C-5, 23/09/2026) ────────────
   «Rifalla» risponde subito e il Piano Max risponde in differita: col piano
   acceso quel giro si paga a consumo. Il backend lo dichiara; prima questa
   pagina buttava via la risposta (`.then(function () { reload(); })`) e la
   frase non arrivava a nessuno. */

test('«Rifalla» mostra la nota del backend su dove è passato il giro', async () => {
  const dom = new JSDOM('<div id="route-outlet"></div>', { url: 'http://localhost/' });
  global.window = dom.window;
  global.document = dom.window.document;
  /* Due risposte DIVERSE, una per rotta: la nota esiste solo sulla risposta
     del redo, ed è l'unico modo di distinguere «la pagina legge il corpo del
     redo» da «la pagina pesca un campo che c'era già nell'elenco». */
  dom.window.fetch = async (url) => ({
    ok: true, status: 200,
    json: async () => (/redo/.test(String(url))
      ? { proposta: {}, nota: 'Il Piano Claude Max e\' acceso, ma questo giro risponde subito.' }
      : { constructions: [propostaAMano()] }),
  });
  global.fetch = dom.window.fetch;
  new dom.window.Function(SORGENTE)();

  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  [...dom.window.document.querySelectorAll('button')]
    .filter((b) => /Rifalla/.test(b.textContent))[0].click();
  dom.window.document.querySelector('textarea').value = 'dopo le 14';
  [...dom.window.document.querySelectorAll('button')]
    .filter((b) => /Rifalla adesso/.test(b.textContent))[0].click();
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));

  const stato = dom.window.document.getElementById('constructions-status');
  assert.match(stato.textContent, /Piano Claude Max/,
    'il giro è passato a consumo e la pagina non lo dice');
});

/* ── Chi costruisce, chi ha chiesto (spec 2026-09-26 §3) ─────────────── */

test('ogni proposta dice CHI l’ha chiesta, e il nome resta testo', async () => {
  /* Il nome viene da Home Assistant: e' testo di fuori, e una pagina che lo
     scrivesse come markup eseguirebbe cio' che un utente di HA si e' messo
     come nome. Mutazione ESEGUITA: `requesterLine` che torna sempre null --
     rossa. */
  const { dom } = montaCon({ constructions: [
    { id: 'p1', stato: 'in_attesa', gesto: 'crea', dominio: 'automation',
      chiave: '1', anteprima: 'x', prima: null, dopo: {}, creata_ts: 2,
      chiesta_da: '<img src=x onerror=1>' },
    { id: 'p2', stato: 'in_attesa', gesto: 'crea', dominio: 'automation',
      chiave: '2', anteprima: 'y', prima: null, dopo: {}, creata_ts: 1,
      chiesta_da: 'Marta' },
    { id: 'a1', stato: 'attesa', a_mano: true, testo: 'Sposta la lavatrice',
      chi_applica: 'tu', creata_ts: 3, chiesta_da: null },
  ] });
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  const document = dom.window.document;

  assert.match(document.body.textContent, /Chiesta da Marta/);
  assert.match(document.body.textContent, /Chiesta da <img src=x onerror=1>/);
  assert.equal(document.querySelectorAll('img').length, 0, 'il nome e\' diventato markup');
  assert.equal((document.body.textContent.match(/Chiesta da/g) || []).length, 2,
    'una proposta senza chi l\'ha chiesta non inventa una riga');
});

test('chi arriva per indirizzo senza poter costruire legge il motivo del server', async () => {
  /* La voce di menu non c'e' per chi non costruisce, ma l'indirizzo si puo'
     scrivere. Nascondere la voce non e' la difesa: il server risponde 403, e
     la pagina mostra il SUO motivo -- come testo -- senza un «Riprova» che
     non cambierebbe niente. Mutazione ESEGUITA: togliere il ramo 403 da
     `draw` -- rossa (resta il messaggio generico col «Riprova»). */
  const dom = new JSDOM('<div id="route-outlet"></div>', { url: 'http://localhost/' });
  global.window = dom.window;
  global.document = dom.window.document;
  const motivo = 'scrivere automazioni è riservato agli amministratori <img src=x onerror=1>';
  dom.window.fetch = async () => ({ ok: false, status: 403, json: async () => ({ errore: motivo }) });
  global.fetch = dom.window.fetch;
  new dom.window.Function(SORGENTE)();

  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));
  const aperte = dom.window.document.getElementById('constructions-open-body');

  assert.equal(aperte.textContent, motivo);
  assert.equal(dom.window.document.querySelectorAll('img').length, 0);
  assert.equal(dom.window.document.querySelectorAll('#route-outlet button:not(.sc-toggle)').length, 0,
    'nessun «Riprova»: riprovare non cambierebbe chi sei');
});

test('un’azione negata dal cancello mostra il motivo del server, non «Errore HTTP 403»', async () => {
  const dom = new JSDOM('<div id="route-outlet"></div>', { url: 'http://localhost/' });
  global.window = dom.window;
  global.document = dom.window.document;
  dom.window.fetch = async (url, opzioni) => {
    if (opzioni && opzioni.method === 'POST') {
      return { ok: false, status: 403, json: async () => ({ errore: 'non sei amministratore' }) };
    }
    return { ok: true, status: 200, json: async () => ({ constructions: [
      { id: 'p1', stato: 'in_attesa', gesto: 'crea', dominio: 'automation',
        chiave: '1', anteprima: 'x', prima: null, dopo: {}, creata_ts: 1 }] }) };
  };
  global.fetch = dom.window.fetch;
  new dom.window.Function(SORGENTE)();
  await dom.window.HirisConstructions.mount(dom.window.document.getElementById('route-outlet'));

  dom.window.document.querySelector('[data-azione="reject"]').click();
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));

  assert.equal(dom.window.document.getElementById('constructions-status').textContent,
    'non sei amministratore');
});
