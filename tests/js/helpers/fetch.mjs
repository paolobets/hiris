import { afterEach, after } from 'node:test';

/* Il finto `fetch` delle prove: UNO solo (T-03, 14/10/2026).

   Fino a oggi ogni file se ne scriveva uno: 84 assegnazioni a `fetch` in 29
   file, e l'aiuto condiviso (`stubFetch`) rispondeva `200` con `{}` a
   QUALUNQUE indirizzo non mappato. Una pagina che chiedeva una rotta
   sbagliata riceveva un oggetto vuoto e la prova restava verde: l'errore di
   indirizzo, il piu' banale, era quello che nessuna prova poteva vedere.

   Le regole di questa finta:
   - le rotte sono PERCORSI, non pezzi di stringa: `'api/chat'` risponde ad
     `api/chat`, ad `api/chat?x=1` e ad `api/chat/reply/7`, ma non ad
     `api/chat-settings`. Fra due rotte che combaciano vince la piu' lunga, e
     una rotta col metodo (`'POST api/chat'`) vince su quella senza;
   - **un indirizzo che nessuna rotta conosce fa fallire la prova** in cui e'
     stato chiesto (il controllo sta in un `afterEach` di questo modulo, che
     ogni file che lo importa riceve), e la richiesta stessa si rifiuta;
   - il valore di una rotta e' il corpo JSON di un 200, oppure una
     `risposta(corpo, status)`, oppure una funzione `(url, opts, chiamata)`
     che restituisce uno dei due, una promessa (anche una che non si risolve
     mai), o solleva (la rete giu').

   Una prova che vuole davvero la rete giu' su tutto lo dice con una
   funzione che solleva, scritta per la rotta che la pagina chiede. */

const MARCA = Symbol('risposta finta');
const sconosciuti = [];

/** Una risposta nella forma che le pagine leggono: `ok`, `status`, `json()`.
 *  `ok` segue lo stato come nel `fetch` vero (200-299). */
export function risposta(corpo, status = 200) {
  return {
    [MARCA]: true,
    ok: status >= 200 && status < 300,
    status,
    json: async () => corpo,
  };
}

function percorso(url) {
  return String(url).split(/[?#]/)[0];
}

function combacia(rotta, url) {
  const p = percorso(url);
  return p === rotta || p.startsWith(rotta + '/');
}

function scegli(rotte, url, metodo) {
  let migliore = null;
  for (const [chiave, valore] of Object.entries(rotte)) {
    const spazio = chiave.indexOf(' ');
    const conMetodo = spazio > 0 && /^[A-Z]+$/.test(chiave.slice(0, spazio));
    const rotta = conMetodo ? chiave.slice(spazio + 1) : chiave;
    if (conMetodo && chiave.slice(0, spazio) !== metodo) continue;
    if (!combacia(rotta, url)) continue;
    const peso = rotta.length * 2 + (conMetodo ? 1 : 0);
    if (migliore === null || peso > migliore.peso) migliore = { peso, valore };
  }
  return migliore;
}

function comeRisposta(valore) {
  if (valore && valore[MARCA]) return valore;
  return risposta(valore);
}

/** Installa il finto su `window.fetch` e restituisce l'elenco delle
 *  chiamate: `{ url, metodo, opts, corpo }`, nell'ordine in cui arrivano. */
export function fintoFetch(window, rotte) {
  const chiamate = [];
  window.fetch = (url, opts) => {
    const metodo = ((opts && opts.method) || 'GET').toUpperCase();
    const chiamata = { url: String(url), metodo, opts: opts || {}, corpo: (opts || {}).body };
    chiamate.push(chiamata);
    const trovata = scegli(rotte, url, metodo);
    if (trovata === null) {
      sconosciuti.push(metodo + ' ' + String(url));
      return Promise.reject(new Error('finto fetch: indirizzo sconosciuto ' + metodo + ' ' + url));
    }
    if (typeof trovata.valore !== 'function') return Promise.resolve(comeRisposta(trovata.valore));
    try {
      return Promise.resolve(trovata.valore(String(url), opts || {}, chiamata)).then(comeRisposta);
    } catch (errore) {
      return Promise.reject(errore);
    }
  };
  return chiamate;
}

/** Una richiesta che non torna mai: la pagina resta nel suo stato di attesa. */
export const maiRisposta = () => new Promise(() => {});

function controlla() {
  if (sconosciuti.length === 0) return;
  const elenco = sconosciuti.splice(0);
  throw new Error('la pagina ha chiesto indirizzi che il finto fetch non conosce: '
    + elenco.join(', ') + ' -- aggiungi la rotta alla prova, o la pagina chiede '
    + "l'indirizzo sbagliato");
}

afterEach(controlla);
after(controlla);
