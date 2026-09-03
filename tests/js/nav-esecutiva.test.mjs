import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { loadScripts, STATIC_VIVO } from './helpers/dom.mjs';

/* Le due voci esecutive -- Impegni e Proposte -- e il gruppo in cui stanno.
 *
 * Il difetto che questo file chiude: nel secondo guscio una sola etichetta di
 * sezione, «Configurazione», stava sopra NOVE voci, di cui configurazione vera
 * ne erano due (Impostazioni chat, Modelli). «Cosa HIRIS sa», «Albero della
 * casa», «Memoria», «L'osservatore», «Consumi» e le due esecutive non
 * configurano niente: si guardano, e su due di esse si decide.
 *
 * Le due esecutive sono il caso che pesa. Su «Proposte» il proprietario
 * aspetta -- senza il suo si' non succede niente -- e la chat lo manda li'
 * («e' in attesa di conferma»). Una voce a cui la chat rimanda, sepolta sotto
 * un'etichetta che dice «Configurazione», e' una strada che si perde.
 *
 * Si legge il guscio VERO (`STATIC_VIVO`), non un finto: il fatto sorvegliato
 * e' com'e' scritto quel file, e un finto direbbe solo che il test sa
 * copiarsi.
 *
 * Mutazione che questi test devono uccidere: rimettere le due voci sotto
 * «Configurazione» -- cioe' esattamente lo stato da cui si parte, che e' il
 * modo piu' onesto di provare che sanno fallire. */

const ESECUTIVE = [
  { etichetta: 'Impegni', badge: 'agenda', hash: '#/agenda' },
  { etichetta: 'Proposte', badge: 'constructions', hash: '#/constructions' },
];

const GRUPPO_ESECUTIVO = 'Da fare';

function domDi(file) {
  const html = readFileSync(join(STATIC_VIVO, file), 'utf8');
  return loadScripts([], { html });
}

/* Le voci del template, ognuna col titolo di sezione che la precede. Si
   scorre il template in ordine di documento: e' cosi' che lo legge un utente,
   ed e' l'unico modo per sapere sotto quale etichetta cade una voce -- il
   raggruppamento qui non e' un contenitore, e' una sequenza. */
function vociConGruppo() {
  const ctx = domDi('config.html');
  const tpl = ctx.document.getElementById('tpl-side-nav');
  assert.ok(tpl, 'config.html deve avere il template della side-nav');

  const fuori = [];
  let gruppo = null;
  const nodi = tpl.content.querySelectorAll('.nav-section-label, .nav-item');
  for (const n of nodi) {
    if (n.classList.contains('nav-section-label')) gruppo = n.textContent.trim();
    else fuori.push({ nodo: n, gruppo, nome: n.textContent.trim() });
  }
  return fuori;
}

test('le due voci esecutive NON stanno sotto «Configurazione»', () => {
  const voci = vociConGruppo();

  for (const attesa of ESECUTIVE) {
    const voce = voci.find((v) => v.nome === attesa.etichetta);
    assert.ok(voce, `la voce «${attesa.etichetta}» deve esistere nella side-nav`);
    assert.equal(voce.gruppo, GRUPPO_ESECUTIVO,
      `«${attesa.etichetta}» deve stare sotto «${GRUPPO_ESECUTIVO}», non sotto «${voce.gruppo}»`);
  }
});

test('«Da fare» e\' il primo gruppo: e\' l\'unico che chiede qualcosa', () => {
  const ctx = domDi('config.html');
  const tpl = ctx.document.getElementById('tpl-side-nav');
  const etichette = [...tpl.content.querySelectorAll('.nav-section-label')]
    .map((n) => n.textContent.trim());

  assert.deepEqual(etichette, [GRUPPO_ESECUTIVO, 'La casa', 'Configurazione']);
});

test('ogni voce esecutiva porta il suo data-badge', () => {
  const voci = vociConGruppo();

  for (const attesa of ESECUTIVE) {
    const voce = voci.find((v) => v.nome === attesa.etichetta);
    assert.equal(voce.nodo.getAttribute('data-badge'), attesa.badge,
      `senza data-badge il pallino non ha dove attaccarsi su «${attesa.etichetta}»`);
  }
});

test('gli indirizzi NON cambiano: i segnalibri restano validi', () => {
  /* La rinomina (02/09) ha gia' portato questi hash all'inglese e la tabella
     `HASH_DI_PRIMA` copre quelli italiani. Rinominarli di nuovo per seguire
     un'etichetta aggiungerebbe due righe a quella tabella in cambio di
     niente: l'utente non legge l'hash, legge l'etichetta. */
  const voci = vociConGruppo();

  for (const attesa of ESECUTIVE) {
    const voce = voci.find((v) => v.nome === attesa.etichetta);
    assert.equal(voce.nodo.getAttribute('href'), attesa.hash);
  }
});

test('il nome sta anche in title e aria-label, o sotto i 1024px sparisce', () => {
  /* La side-nav si stringe a 64px e resta la sola icona (hiris-config.css):
     il nome deve vivere accanto al testo che lo ripete, o i due divergono. */
  const voci = vociConGruppo();

  for (const attesa of ESECUTIVE) {
    const voce = voci.find((v) => v.nome === attesa.etichetta);
    assert.equal(voce.nodo.getAttribute('title'), attesa.etichetta);
    assert.equal(voce.nodo.getAttribute('aria-label'), attesa.etichetta);
  }
});

test('la barra della chat porta le stesse due voci, con gli stessi pallini', () => {
  /* E' il punto della fetta: da dove l'utente sta davvero, la pagina e' a un
     click -- non dentro «Configurazione», a due. */
  const ctx = domDi('index.html');

  for (const attesa of ESECUTIVE) {
    const voce = ctx.document.querySelector(`[data-badge="${attesa.badge}"]`);
    assert.ok(voce, `index.html deve avere la voce «${attesa.etichetta}»`);
    assert.match(voce.textContent, new RegExp(attesa.etichetta));
    assert.equal(voce.getAttribute('title'), attesa.etichetta);
    /* `config#/agenda`, non `#/agenda`: dalla chat serve cambiare guscio. */
    assert.equal(voce.getAttribute('href'), `config${attesa.hash}`);
  }
});

test('le parole vecchie non sopravvivono da nessuna parte nei due gusci', () => {
  /* «Promesse» e «Costruzioni» come NOMI DI PAGINA. La parola «promessa» al
     singolare resta viva altrove -- e' come la chat chiama la cosa, ed e' per
     questo che l'etichetta scelta e' «Impegni»: prendere un impegno e fare
     una promessa sono la stessa mossa in due registri. Qui si vieta solo il
     titolo. */
  for (const file of ['config.html', 'index.html']) {
    const html = readFileSync(join(STATIC_VIVO, file), 'utf8');
    assert.doesNotMatch(html, />\s*Promesse\s*</,
      `${file} nomina ancora la pagina «Promesse»`);
    assert.doesNotMatch(html, />\s*Costruzioni\s*</,
      `${file} nomina ancora la pagina «Costruzioni»`);
  }
});
