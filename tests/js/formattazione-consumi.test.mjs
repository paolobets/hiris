import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts } from './helpers/dom.mjs';

/* `fmtEuro` faceva `'EUR ' + Number(n).toFixed(2)`: due difetti in una riga,
   e il primo e' esattamente la bugia che la fetta «i consumi, per modello»
   esiste per togliere, rientrata dalla porta della formattazione.

   1. `toFixed(2)` scrive «0.00» per un modello costato tre decimillesimi di
      euro. Dopo aver tolto lo zero che afferma dai DATI, riaverlo a schermo
      sarebbe la stessa bugia con un'altra provenienza.
   2. `toFixed` non conosce la lingua e produce il separatore col PUNTO, in
      una pagina dove la data accanto e' formattata `it-IT`. Difetto
      preesistente, trovato dall'audit di disegno, non introdotto qui.

   La funzione e' CONDIVISA col riquadro della chat: sistemarla la sistema in
   tutti e due i posti, che e' il punto di averla in `config/api.js`. */

const HTML = '<!doctype html><body></body>';

function carica() {
  // `loadScripts` valuta col global dell'host: le funzioni di `api.js` -- che
  // nel browser sono globali di pagina -- finiscono su `globalThis`, non su
  // `window`. E' lo stesso modo in cui `usage-route.js` le chiama: nude.
  loadScripts(['config/api.js'], { html: HTML });
  return globalThis;
}

test('un costo di riga da pochi decimillesimi non diventa zero', () => {
  const scritto = carica().fmtEuro(0.0003, 4);
  assert.doesNotMatch(scritto, /0[.,]00\b/, "lo zero bugiardo e' tornato dalla formattazione");
  assert.match(scritto, /0,0003/);
});

test("il separatore decimale e' la virgola, non il punto", () => {
  assert.equal(carica().fmtEuro(24.18), '€ 24,18');
});

test('il totale resta a due decimali quando non si chiede altro', () => {
  assert.equal(carica().fmtEuro(21.045), '€ 21,05');
});

test('un costo assente resta un trattino, e non uno zero', () => {
  assert.equal(carica().fmtEuro(null), '—');
});

test('anche a quattro decimali un costo tondo non si sporca di zeri', () => {
  assert.equal(carica().fmtEuro(3.14, 4), '€ 3,14');
});
