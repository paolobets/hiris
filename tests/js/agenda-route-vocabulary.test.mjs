import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

/* Review finale della fetta «lo schedulatore», rilievo ②: il vocabolario
   degli stati «in sospeso» (`in_attesa`, `in_corso`) vive in Python
   (`hiris/app/keeper/promise.py::STATES_SOSPESO`, usata da
   `store.py` per le sue due query) E in JavaScript
   (`static/config/agenda-route.js::STATI_SOSPESO`, che filtra
   `GET /api/agenda?all=1` lato client) -- senza niente che li legasse.
   Il vocabolario degli stati «conclusi» (`STATES_CONCLUSI`) ha la stessa
   forma: Python lo usa per `concludi()`/potatura, il JavaScript lo rispecchia
   in `STATE_LABEL`/`STATE_BADGE`.

   Nota sulla rinomina in inglese: `promise.py` e' gia' stato convertito
   (`STATI_SOSPESO` -> `STATES_SOSPESO`, `STATI_CONCLUSI` -> `STATES_CONCLUSI`);
   `agenda-route.js` no. I due lati parlano quindi due lingue diverse per i
   NOMI delle costanti -- per questo il confronto qui sotto e' e resta sui
   VALORI (gli insiemi di stringhe), mai sui nomi degli identificatori.

   `scripts/doppioni.py` cerca apposta queste coppie (vocabolario Python i
   cui membri compaiono tutti in un file JS), e per costruzione smette di
   segnalarle SOLO quando una prova le confronta: qui e' quella prova, dal
   lato JavaScript -- lo stesso pattern di lettura di un sorgente con
   `readFileSync(new URL(...))` gia' usato da `tree-route.test.mjs`
   ("wiring: la rotta #/albero...") e da `dashboard-knowledge.test.mjs`
   ("le sole rotte raggiungibili..."), adottato qui per leggere un file
   Python invece di un altro file JS o config.html.

   Mutazione che deve far diventare rosso questo file: aggiungere un quinto
   stato "sospeso" (o un quinto stato "concluso") da UN lato solo -- Python o
   JavaScript -- lasciando l'altro fermo. E' esattamente il rischio che la
   spec §12 nomina per la fetta successiva: uno stato non conclusivo
   aggiunto in Python per un lavoro di sistema ricorrente, dimenticato nel
   JavaScript, sparirebbe in silenzio dalla sezione «In sospeso» della
   pagina. */

const PROMESSA_PY = readFileSync(
  new URL('../../hiris/app/keeper/promise.py', import.meta.url), 'utf8');
const ROUTE_JS = readFileSync(
  new URL('../../hiris/app/static/config/agenda-route.js', import.meta.url), 'utf8');

/* Una tupla Python di stringhe: `NOME = ("a", "b", ...)`. Regex, non un
   parser -- e' lo stesso grado di sofisticazione delle letture gia' in uso
   nei due file citati sopra (`.includes(...)`, `.match(...)`). */
function tuplaPython(nomeCostante) {
  const m = PROMESSA_PY.match(new RegExp(nomeCostante + '\\s*=\\s*\\(([^)]*)\\)'));
  assert.ok(m, 'costante Python non trovata: ' + nomeCostante +
    ' (promise.py e\' cambiato sotto questo test?)');
  return m[1].split(',').map((s) => s.trim()).filter(Boolean)
    .map((s) => s.replace(/^["']|["']$/g, ''));
}

test('gli stati in sospeso: lo stesso insieme in promise.py (STATES_SOSPESO) e in agenda-route.js (PENDING_STATES)', () => {
  const python = tuplaPython('STATES_SOSPESO');
  // Se questa riga fallisse, il problema e' la lettura del sorgente Python
  // (un rinominamento, un formato diverso), non ancora un confronto col JS:
  // separarla aiuta a leggere subito quale delle due cose si e' rotta.
  assert.deepEqual(new Set(python), new Set(['in_attesa', 'in_corso']));

  // Il nome JS e' passato all'inglese il 02/09 (fetta del frontend);
  // `STATES_SOSPESO` di `promise.py` e' ancora mezzo italiano, ed e' un
  // residuo del lotto Python -- questo test lega i due INSIEMI, non i due
  // nomi, ed e' per questo che sopravvive a una rinomina di un lato solo.
  const m = ROUTE_JS.match(/var PENDING_STATES = \[([^\]]*)\];/);
  assert.ok(m, 'PENDING_STATES non trovata in agenda-route.js');
  const js = m[1].split(',').map((s) => s.trim()).filter(Boolean)
    .map((s) => s.replace(/^['"]|['"]$/g, ''));

  assert.deepEqual(new Set(js), new Set(python),
    'gli stati "in sospeso" devono essere lo stesso insieme in Python e in JavaScript');
});

test('STATI_CONCLUSI: ogni stato concluso di promise.py (STATES_CONCLUSI) ha una voce in STATE_LABEL e in STATE_BADGE', () => {
  const python = tuplaPython('STATES_CONCLUSI');
  assert.deepEqual(new Set(python), new Set(['mantenuta', 'saltata', 'disdetta', 'fallita']));

  // Il JavaScript non ripete `STATI_CONCLUSI` come proprio insieme a se':
  // "concluso" e' li' "tutto cio' che non e' in STATI_SOSPESO" (vedi
  // `carica()` in agenda-route.js -- e' l'insieme SOSPESO che va confrontato
  // per identita', non due volte lo stesso complemento). Cio' che PUO'
  // divergere in silenzio, e che questo test copre, sono le due tendine di
  // resa: uno stato concluso che ne fosse privo diventerebbe "undefined" a
  // schermo, o un badge neutro invece di uno che porta il significato.
  const chiaviDiOggetto = (nomeCostante) => {
    const m = ROUTE_JS.match(new RegExp('var ' + nomeCostante + ' = \\{([\\s\\S]*?)\\};'));
    assert.ok(m, nomeCostante + ' non trovata in agenda-route.js');
    return new Set(Array.from(m[1].matchAll(/(\w+):/g)).map((mm) => mm[1]));
  };
  const label = chiaviDiOggetto('STATE_LABEL');
  const badge = chiaviDiOggetto('STATE_BADGE');

  for (const stato of python) {
    assert.ok(label.has(stato), 'STATE_LABEL non conosce lo stato concluso "' + stato + '"');
    assert.ok(badge.has(stato), 'STATE_BADGE non conosce lo stato concluso "' + stato + '"');
  }
});
