import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, stubFetch, tick } from './helpers/dom.mjs';

/* SP-4 Fase B Task 3: kit editor condiviso. Questi tre test provano
   esattamente i due bug live che il kit deve chiudere (dirty tracking come
   MutationObserver, non uno snapshot one-shot; guard di navigazione su
   hashchange/beforeunload) più la fetch condivisa di modelSelect (oggi
   agentbot-route.js ne fa una PER RIGA). */

function setup() {
  return loadScripts(['config/editor-kit.js']);
}

test('dirty.track: un controllo creato DOPO track() marca dirty e abilita Salva (bug live #1)', async () => {
  const { window, document } = setup();
  const root = document.createElement('div');
  document.body.appendChild(root);
  const btnSave = document.createElement('button');
  btnSave.disabled = true;
  document.body.appendChild(btnSave);

  window.HirisEditorKit.dirty.track(root, () => { btnSave.disabled = false; });

  // Controllo aggiunto DOPO track() -- lo scenario esatto del bug live #1
  // (setupStickyActions faceva un querySelectorAll UNA VOLTA al mount: i
  // checkbox di buildToolChecks/le chip dell'entity-picker, creati dopo,
  // non erano mai agganciati a markDirty).
  const later = document.createElement('input');
  later.type = 'checkbox';
  root.appendChild(later);
  await tick(0);

  assert.equal(btnSave.disabled, true, 'nessuna modifica utente ancora: Salva resta disabled');
  later.checked = true;
  later.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(btnSave.disabled, false,
    'il controllo creato DOPO track() deve abilitare Salva al change (MutationObserver, non uno snapshot)');
});

test('dirty.guard: con dirty=true, hashchange chiede conferma e se annullato NON naviga (bug live #2)', () => {
  const { window } = setup();
  const dirty = { value: true };
  let confirmCalls = 0;
  window.confirm = () => { confirmCalls += 1; return false; }; // utente annulla

  window.location.hash = '#/chatbots/abc';
  window.HirisEditorKit.dirty.guard(() => dirty.value);

  const before = window.location.hash;
  window.location.hash = '#/tasks';
  window.dispatchEvent(new window.Event('hashchange'));

  assert.equal(confirmCalls, 1, 'deve chiedere conferma quando ci sono modifiche non salvate');
  assert.equal(window.location.hash, before,
    'annullando la conferma la navigazione non deve avvenire (hash ripristinato all\'originale)');
});

test('dirty.guard: con dirty=true e conferma accettata, la navigazione procede', () => {
  const { window } = setup();
  const dirty = { value: true };
  window.confirm = () => true; // utente conferma di voler uscire

  window.location.hash = '#/chatbots/abc';
  window.HirisEditorKit.dirty.guard(() => dirty.value);

  window.location.hash = '#/tasks';
  window.dispatchEvent(new window.Event('hashchange'));

  assert.equal(window.location.hash, '#/tasks', 'confermando, la navigazione deve procedere');
});

test('modelSelect: due chiamate condividono UNA sola fetch di api/models (oggi una per riga)', async () => {
  const { window, document } = setup();
  const calls = stubFetch(window, {
    'api/models': { providers: [{ label: 'Anthropic', models: ['auto', 'claude-x'] }] },
  });

  const p1 = document.createElement('div');
  const p2 = document.createElement('div');
  document.body.append(p1, p2);
  window.HirisEditorKit.modelSelect(p1, { label: 'Modello riga 1' });
  window.HirisEditorKit.modelSelect(p2, { label: 'Modello riga 2' });

  await tick(20);

  const modelCalls = calls.filter((c) => c.url.includes('api/models'));
  assert.equal(modelCalls.length, 1, 'due modelSelect() devono condividere una sola fetch api/models (cache)');

  // Entrambe le select devono comunque essere state popolate dalla stessa
  // promise condivisa (nessuna delle due resta vuota/inerte).
  const sel1 = p1.querySelector('select');
  const sel2 = p2.querySelector('select');
  assert.ok(sel1 && sel1.querySelector('option[value="claude-x"]'), 'la prima select deve ricevere i modelli');
  assert.ok(sel2 && sel2.querySelector('option[value="claude-x"]'), 'la seconda select deve ricevere i modelli');
});
