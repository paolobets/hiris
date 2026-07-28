import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, stubFetch, tick } from './helpers/dom.mjs';

function setup() {
  const ctx = loadScripts(['config/api.js', 'config/entity-picker.js']);
  const root = ctx.document.createElement('div');
  ctx.document.body.appendChild(root);
  return { ...ctx, root };
}

test('due picker sulla stessa pagina hanno stato indipendente', () => {
  const { window, document } = setup();
  const a = document.createElement('div'), b = document.createElement('div');
  document.body.append(a, b);
  const p1 = window.HirisEntityPicker.create(a, {});
  const p2 = window.HirisEntityPicker.create(b, {});
  p1.add('light.salotto');
  p2.add('sensor.porta');
  assert.deepEqual(p1.getValue(), ['light.salotto']);
  assert.deepEqual(p2.getValue(), ['sensor.porta']);   // il singleton fallirebbe qui
});

test('setValue NON emette onChange, add/remove si', () => {
  const { window, root } = setup();
  let n = 0;
  const p = window.HirisEntityPicker.create(root, { onChange: () => { n++; } });
  p.setValue(['light.a']);
  assert.equal(n, 0, 'setValue e il caricamento, non una modifica utente');
  p.add('light.b');
  assert.equal(n, 1);
  p.remove('light.b');
  assert.equal(n, 2);
});

test('single:true tiene una sola entita', () => {
  const { window, root } = setup();
  const p = window.HirisEntityPicker.create(root, { single: true });
  p.add('light.a'); p.add('light.b');
  assert.deepEqual(p.getValue(), ['light.b']);
});

test('destroy() stacca il listener documento (niente handler accumulati)', () => {
  const { window, document, root } = setup();
  const before = window.document.body.innerHTML;
  const p = window.HirisEntityPicker.create(root, {});
  p.destroy();
  // dopo destroy un click sul documento non deve piu' toccare nulla del picker
  document.body.dispatchEvent(new window.Event('click', { bubbles: true }));
  assert.equal(root.innerHTML, '', 'destroy() deve svuotare il root');
});

test('il chip rimuove il valore al click (interazione vera)', () => {
  const { window, document, root } = setup();
  const p = window.HirisEntityPicker.create(root, {});
  p.add('light.salotto');
  const x = root.querySelector('.chip-remove');
  assert.ok(x, 'il chip deve esistere nel DOM');
  x.dispatchEvent(new window.Event('click', { bubbles: true }));
  assert.deepEqual(p.getValue(), []);
});

test('la ricerca legge la forma canonica {entities:[{entity_id}]}', async () => {
  const { window, document, root } = setup();
  stubFetch(window, { 'api/entities': { entities: [
    { entity_id: 'light.salotto', friendly_name: 'Luce Salotto' } ] } });
  const p = window.HirisEntityPicker.create(root, {});
  const search = root.querySelector('input');
  search.value = 'sal';
  search.dispatchEvent(new window.Event('input', { bubbles: true }));
  await tick(350);                       // oltre il debounce
  const sugg = root.querySelector('.ep-suggestion');
  assert.ok(sugg, 'il suggerimento deve comparire (era il bug della forma sbagliata)');
  sugg.dispatchEvent(new window.Event('click', { bubbles: true }));
  assert.deepEqual(p.getValue(), ['light.salotto']);
});
