import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* La pagina «Servizi» (config/services-route.js), fetta «l'accoppiamento»
   (spec 2026-09-21 §7, rifatta il 22/09/2026).

   Qui si verifica cio' che il proprietario fa davvero: apre la finestra, vede
   comparire chi si presenta, CONFRONTA il codice a quattro cifre, approva col
   ruolo, e revoca. E le due proprieta' che nessuno guarderebbe a mano:
   - **presentarsi non e' essere autorizzati** (la riga in attesa non si mescola
     con gli accoppiati);
   - **il giro di riletture si ferma**, o la pagina interrogherebbe il server
     per sempre da una route che non si vede piu'. */

const HTML = '<!doctype html><body><div id="route-outlet"></div></body>';
const SCRIPTS = ['config/api.js', 'config/services-route.js'];

function risposta(body, status) {
  return { ok: (status || 200) < 400, status: status || 200, json: async () => body };
}

const RUOLI = ['amministratore', 'utente', 'lettore'];
const SPECIE = ['integrazione', 'luogo'];

function servizio(extra) {
  return Object.assign({
    chiave: 'k-uno', nome: 'Retro Panel cucina', indirizzo: '192.168.1.77',
    stato: 'in_attesa', ruolo: null, specie: null,
    visto_ts: 1758500000, deciso_ts: null, codice: '0421',
  }, extra || {});
}

function stato(servizi, finestra) {
  return {
    servizi: servizi || [],
    finestra: finestra || { aperta: false, resta_s: 0 },
    ruoli: RUOLI, specie: SPECIE,
  };
}

/* Il finto server. Ogni prova rompe o cambia solo il pezzo che la riguarda; le
   POST tornano l'elenco aggiornato, come fanno quelle vere. */
function monta(opts = {}) {
  const ctx = loadScripts(SCRIPTS, { html: HTML });
  ctx.window.location.hash = '#/services';
  /* Il battito si CATTURA invece di aspettarlo: una prova che dorme cinque
     secondi per vedere un giro e' una prova che nessuno rieseguira'
     volentieri, e che fallisce a caso su una macchina lenta. Qui si prende la
     funzione che il giro registra e la si chiama a mano -- cio' che si vuole
     provare non e' che `setInterval` funzioni, e' cosa fa quel battito. */
  const battito = { fn: null, spenti: [] };
  ctx.window.setInterval = (fn) => { battito.fn = fn; return 7; };
  ctx.window.clearInterval = (id) => { battito.spenti.push(id); battito.fn = null; };
  const chiamate = [];
  let corpo = opts.stato || stato();
  ctx.window.fetch = async (url, options) => {
    const u = String(url);
    chiamate.push({ url: u, opts: options || {}, corpo: (options || {}).body });
    if (opts.rotto) return risposta({ errore: 'no' }, 403);
    if (u.endsWith('/window/open')) {
      corpo.finestra = { aperta: true, resta_s: 600 };
      return risposta({ aperta: true, resta_s: 600 });
    }
    if (u.endsWith('/window/close')) {
      corpo.finestra = { aperta: false, resta_s: 0 };
      return risposta({ aperta: false, resta_s: 0 });
    }
    if (u.endsWith('/approve')) {
      if (opts.approveStatus) return risposta({ errore: 'il ruolo non esiste' }, opts.approveStatus);
      const d = JSON.parse((options || {}).body || '{}');
      corpo.servizi = corpo.servizi.map((r) => (r.chiave === d.chiave
        ? Object.assign({}, r, { stato: 'autorizzato', ruolo: d.ruolo, specie: d.specie,
                                 deciso_ts: 1758500500 })
        : r));
      return risposta({ servizi: corpo.servizi });
    }
    if (u.endsWith('/revoke')) {
      const d = JSON.parse((options || {}).body || '{}');
      corpo.servizi = corpo.servizi.map((r) => (r.chiave === d.chiave
        ? Object.assign({}, r, { stato: 'revocato', deciso_ts: 1758500600 })
        : r));
      return risposta({ servizi: corpo.servizi });
    }
    return risposta(corpo);
  };
  return Object.assign(ctx, { chiamate, battito, statoServer: () => corpo });
}

function testo(document) {
  return document.getElementById('route-outlet').textContent;
}

function bottone(document, etichetta) {
  return Array.from(document.querySelectorAll('button'))
    .find((b) => b.textContent === etichetta);
}

function sezione(document, titolo) {
  return Array.from(document.querySelectorAll('.section-card'))
    .find((c) => c.textContent.indexOf(titolo) >= 0);
}

// ---------------------------------------------------------------------------

test('a finestra chiusa la pagina lo DICE e offre di aprirla', async () => {
  const { document, window } = monta();
  window.HirisServicesRoute.mount();
  await tick();

  assert.match(testo(document), /Finestra chiusa/);
  assert.ok(bottone(document, 'Apri la finestra per 10 minuti'),
    'senza questo bottone la finestra si aprirebbe solo da un’altra parte');
  assert.equal(bottone(document, 'Chiudi adesso'), undefined);
});

test('aprire la finestra dice per quanto resta aperta, in MINUTI', async () => {
  const { document, window } = monta();
  window.HirisServicesRoute.mount();
  await tick();

  bottone(document, 'Apri la finestra per 10 minuti').click();
  await tick();

  /* Mutazione: mostrare i secondi -- rossa. Dieci minuti al secondo sono una
     gara; qui sono il tempo per fare una cosa sull'altra macchina. */
  assert.match(testo(document), /ancora per circa 10 minuti/);
  assert.doesNotMatch(testo(document), /600/);
  window.HirisServicesRoute.unmount();
});

test('chi si presenta NON è accoppiato: sta fra le decisioni da prendere', async () => {
  const { document, window } = monta({ stato: stato([servizio()]) });
  window.HirisServicesRoute.mount();
  await tick();

  /* **La proprieta' che regge tutto il disegno.** Mutazione: mettere le righe
     in attesa nella sezione degli accoppiati -- rossa. */
  assert.match(sezione(document, 'Accoppiamento').textContent, /Retro Panel cucina/);
  assert.match(sezione(document, 'Servizi accoppiati').textContent,
    /Nessun servizio accoppiato/);
});

test('la riga in attesa NON afferma il nome: dice che è quello che si presenta', async () => {
  const { document, window } = monta({ stato: stato([servizio()]) });
  window.HirisServicesRoute.mount();
  await tick();

  /* Il nome se lo sceglie chi si presenta: chi si mette in mezzo puo'
     chiamarsi «Retro Panel cucina». Dirlo come un fatto sarebbe la pagina che
     mente al posto suo.

     Mutazione ESEGUITA: scrivere il nome asciutto -- rossa. */
  assert.match(testo(document), /Si presenta come «Retro Panel cucina»/);
});

test('il codice a quattro cifre c’è, con lo ZERO davanti, e dice cosa farne', async () => {
  const { document, window } = monta({ stato: stato([servizio({ codice: '0421' })]) });
  window.HirisServicesRoute.mount();
  await tick();

  const codice = document.querySelector('.service-code');
  /* Lo zero iniziale non e' un dettaglio: se uno dei due lati trattasse il
     codice come numero, il confronto fallirebbe in un caso su dieci -- e
     fallirebbe dicendo «non è lo stesso servizio», che è la bugia peggiore
     che questa pagina possa raccontare.

     Mutazione ESEGUITA: `Number(r.codice)` -- rossa. */
  assert.equal(codice.textContent, '0421');
  assert.match(testo(document), /Lo stesso numero deve comparire sullo schermo del servizio/);
});

test('approvare chiede PRIMA il ruolo, e propone «utente»', async () => {
  const { document, window } = monta({ stato: stato([servizio()]) });
  window.HirisServicesRoute.mount();
  await tick();

  bottone(document, 'Approva…').click();
  await tick();

  /* Mutazione ESEGUITA: approvare direttamente al click, senza chiedere il
     ruolo -- rossa. Un servizio accoppiato senza scegliere il ruolo
     erediterebbe qualcosa deciso dal codice invece che dal proprietario. */
  const scelti = Array.from(document.querySelectorAll('input[type=radio]'))
    .filter((r) => r.checked).map((r) => r.value);
  assert.deepEqual(scelti, ['utente', 'integrazione']);
  assert.ok(bottone(document, 'Accoppia come utente'));
  assert.match(testo(document), /Approva solo se sullo schermo di «Retro Panel cucina» c’è 0421/);
});

test('scegliere «amministratore» cambia la frase che dice cosa succede dopo', async () => {
  const { document, window } = monta({ stato: stato([servizio()]) });
  window.HirisServicesRoute.mount();
  await tick();
  bottone(document, 'Approva…').click();
  await tick();

  const admin = Array.from(document.querySelectorAll('input[type=radio]'))
    .find((r) => r.value === 'amministratore');
  admin.checked = true;
  admin.dispatchEvent(new window.Event('change'));

  /* La frase E' la conferma: un `window.confirm` sopra sarebbe un secondo
     cancello sulla stessa porta, e un secondo cancello si impara a
     scavalcare, non a leggere.

     Mutazione: lasciare la frase ferma sul ruolo predefinito -- rossa. */
  assert.match(testo(document), /potrà comandare la casa e costruire automazioni/);
  assert.ok(bottone(document, 'Accoppia come amministratore'));
});

test('il giro intero: approva, e il servizio passa fra gli accoppiati', async () => {
  const { document, window, chiamate } = monta({ stato: stato([servizio()]) });
  window.HirisServicesRoute.mount();
  await tick();
  bottone(document, 'Approva…').click();
  await tick();

  bottone(document, 'Accoppia come utente').click();
  await tick();
  await tick();

  const inviata = chiamate.find((c) => c.url.endsWith('/approve'));
  assert.deepEqual(JSON.parse(inviata.corpo),
    { chiave: 'k-uno', ruolo: 'utente', specie: 'integrazione' });
  assert.match(sezione(document, 'Servizi accoppiati').textContent, /Retro Panel cucina/);
  assert.match(testo(document), /è accoppiato come utente/);
});

test('«Rifiuta» esiste, e impedisce di tornare in coda ribussando', async () => {
  const { document, window, chiamate } = monta({ stato: stato([servizio()]) });
  window.HirisServicesRoute.mount();
  await tick();

  bottone(document, 'Rifiuta').click();
  await tick();
  await tick();

  /* Senza questo bottone l'unica risposta a un codice che NON coincide
     sarebbe aspettare ventiquattro ore con uno sconosciuto sotto gli occhi.
     E' la revoca, e non e' un riuso pigro: «un revocato che si ripresenta
     resta revocato» e' esattamente la protezione che serve qui.

     Mutazione ESEGUITA: tolto il bottone -- rossa. */
  assert.ok(chiamate.find((c) => c.url.endsWith('/revoke')),
    'rifiutare non chiede niente al server');
  assert.match(testo(document), /è stato rifiutato/);
});

test('revocare un accoppiato vale SUBITO e la riga resta leggibile', async () => {
  const { document, window } = monta({ stato: stato([
    servizio({ stato: 'autorizzato', ruolo: 'utente', specie: 'luogo', deciso_ts: 1758500500 })]) });
  window.HirisServicesRoute.mount();
  await tick();

  bottone(document, 'Revoca').click();
  await tick();
  await tick();

  /* Nessuna conferma: la riga non sparisce, passa fra i revocati. Si conferma
     cio' che distrugge senza coda -- qui l'errore e' reversibile.

     Mutazione: far sparire la riga -- rossa. */
  assert.match(sezione(document, 'Servizi accoppiati').textContent,
    /Nessun servizio accoppiato/);
  const storia = sezione(document, 'Revocati');
  assert.ok(storia, 'la riga revocata è sparita del tutto');
  assert.match(storia.textContent, /Revocati \(1\)/);
});

test('i revocati nascono CHIUSI e si riaprono', async () => {
  const { document, window } = monta({ stato: stato([
    servizio({ stato: 'revocato', ruolo: 'utente', deciso_ts: 1758500600 })]) });
  window.HirisServicesRoute.mount();
  await tick();

  const storia = sezione(document, 'Revocati');
  assert.equal(storia.querySelector('.sc-body').hidden, true,
    'una memoria aperta di default seppellirebbe le decisioni da prendere');
  storia.querySelector('.sc-toggle').click();
  await tick();
  assert.equal(sezione(document, 'Revocati').querySelector('.sc-body').hidden, false);
});

test('un revocato si può RIAMMETTERE, o un click sbagliato sarebbe definitivo', async () => {
  const { document, window } = monta({ stato: stato([
    servizio({ stato: 'revocato', ruolo: 'utente', deciso_ts: 1758500600 })]) });
  window.HirisServicesRoute.mount();
  await tick();
  sezione(document, 'Revocati').querySelector('.sc-toggle').click();
  await tick();

  bottone(document, 'Riammetti…').click();
  await tick();

  /* Ripresentarsi non rimette in coda un revocato -- per disegno. Senza questo
     bottone il proprietario dovrebbe far rifare le chiavi al servizio per un
     click sbagliato.

     Mutazione ESEGUITA: tolto il bottone -- rossa. */
  assert.ok(bottone(document, 'Accoppia come utente'),
    'riammettere deve far riscegliere il ruolo, non riportarlo in silenzio');
});

test('un rifiuto del server si LEGGE, non finisce in un catch muto', async () => {
  const { document, window } = monta({ stato: stato([servizio()]), approveStatus: 400 });
  window.HirisServicesRoute.mount();
  await tick();
  bottone(document, 'Approva…').click();
  await tick();

  bottone(document, 'Accoppia come utente').click();
  await tick();
  await tick();

  /* Mutazione ESEGUITA: `.catch(function(){})` -- rossa. */
  assert.match(testo(document), /il ruolo non esiste/);
});

test('se la pagina non si legge lo dice, e dice anche a CHI è riservata', async () => {
  const { document, window } = monta({ rotto: true });
  window.HirisServicesRoute.mount();
  await tick();
  await tick();

  assert.match(testo(document), /Non è stato possibile leggere i servizi/);
  /* Un 403 qui vuol dire quasi sempre «non sei amministratore»: lasciare che
     sembri un guasto manderebbe a cercare un log che non ha niente da dire. */
  assert.match(testo(document), /amministratore/);
});

test('una rilettura NON azzera la scelta del pannello aperto', async () => {
  const { document, window, battito } = monta({
    stato: stato([servizio()], { aperta: true, resta_s: 573 }) });
  window.HirisServicesRoute.mount();
  await tick();
  bottone(document, 'Approva…').click();
  await tick();

  const lettore = Array.from(document.querySelectorAll('input[type=radio]'))
    .find((r) => r.value === 'lettore');
  lettore.checked = true;
  lettore.dispatchEvent(new window.Event('change'));

  battito.fn();
  await tick();

  /* **Difetto TROVATO DAL VIVO il 22/09/2026, alla prima prova vera.** Il
     proprietario sceglieva «lettore», cinque secondi dopo arrivava un battito,
     `disegna()` ricostruiva l'outlet -- pannello compreso, con una `scelte`
     nuova -- e la scelta tornava «utente» sotto i suoi occhi. Su una pagina
     dove si decide quanto potere dare a una macchina sulla casa, cio' che si
     conferma deve essere cio' che si e' scelto.

     Mutazione ESEGUITA: `disegna()` al posto di `ridisegna()` nel battito --
     rossa (era lo stato da cui si parte). */
  const scelti = Array.from(document.querySelectorAll('input[type=radio]'))
    .filter((r) => r.checked).map((r) => r.value);
  assert.deepEqual(scelti, ['lettore', 'integrazione'],
    'la rilettura ha azzerato la scelta del proprietario');
  assert.ok(bottone(document, 'Accoppia come lettore'));
});

test('e quello che si conferma è quello che si era scelto', async () => {
  const { document, window, battito, chiamate } = monta({
    stato: stato([servizio()], { aperta: true, resta_s: 573 }) });
  window.HirisServicesRoute.mount();
  await tick();
  bottone(document, 'Approva…').click();
  await tick();

  const lettore = Array.from(document.querySelectorAll('input[type=radio]'))
    .find((r) => r.value === 'lettore');
  lettore.checked = true;
  lettore.dispatchEvent(new window.Event('change'));
  battito.fn();
  await tick();

  bottone(document, 'Accoppia come lettore').click();
  await tick();
  await tick();

  /* La meta' che conta davvero: non basta che il pallino resti dov'era, deve
     restarci anche il valore che parte. */
  const inviata = chiamate.find((c) => c.url.endsWith('/approve'));
  assert.equal(JSON.parse(inviata.corpo).ruolo, 'lettore');
});

// --- il giro di riletture ---------------------------------------------------

test('la pagina si rilegge da sola SOLO mentre la finestra è aperta', async () => {
  const { document, window, battito } = monta();
  window.HirisServicesRoute.mount();
  await tick();

  /* A finestra chiusa non c'e' niente da aspettare: interrogare comunque
     sarebbe rumore su un percorso che gira per sempre.
     Mutazione ESEGUITA: far partire il giro sempre -- rossa. */
  assert.equal(battito.fn, null, 'a finestra chiusa il giro non deve esistere');

  bottone(document, 'Apri la finestra per 10 minuti').click();
  await tick();
  assert.ok(battito.fn, 'con la finestra aperta le righe in attesa non arriverebbero mai');
});

test('ogni battito RILEGGE, o le righe in attesa non comparirebbero mai', async () => {
  const { document, window, battito, chiamate } = monta();
  window.HirisServicesRoute.mount();
  await tick();
  bottone(document, 'Apri la finestra per 10 minuti').click();
  await tick();

  const prima = chiamate.length;
  battito.fn();
  await tick();

  /* Mutazione: un giro che non chiede niente -- rossa. */
  assert.ok(chiamate.length > prima);
});

test('chiudere la finestra SPEGNE il giro', async () => {
  const { document, window, battito } = monta();
  window.HirisServicesRoute.mount();
  await tick();
  bottone(document, 'Apri la finestra per 10 minuti').click();
  await tick();

  bottone(document, 'Chiudi adesso').click();
  await tick();
  await tick();

  /* Mutazione ESEGUITA: non spegnere alla chiusura -- rossa. */
  assert.equal(battito.fn, null);
  assert.deepEqual(battito.spenti, [7]);
});

test('il giro si FERMA quando si lascia la pagina', async () => {
  const { document, window, battito, chiamate } = monta();
  window.HirisServicesRoute.mount();
  await tick();
  bottone(document, 'Apri la finestra per 10 minuti').click();
  await tick();

  window.location.hash = '#/models';
  const fermo = chiamate.length;
  battito.fn();
  await tick();

  /* Il router di questa SPA non avvisa nessuno quando una route esce di scena:
     un giro che sopravvivesse interrogherebbe il server per sempre da una
     pagina che non si vede piu'.

     Mutazione ESEGUITA: tolto il controllo sull'indirizzo dal battito --
     rossa. */
  assert.equal(chiamate.length, fermo, 'ha chiesto da una pagina che non si vede piu\'');
  assert.deepEqual(battito.spenti, [7]);
});
