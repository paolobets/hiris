import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts } from './helpers/dom.mjs';

/* labels.js e' il dizionario unico condiviso da chat + config (Task 3
   A4+B1). Copre: sette stati task reali, stati suggerimenti (compreso
   'recorded'), tre severita' segnalazioni, cinque tipi di trigger reali.
   Ogni get* deve degradare al valore grezzo per una chiave sconosciuta,
   mai far sparire la riga. */

test('HirisLabels copre tutti e sette gli stati task reali (task_engine.py)', () => {
  const { window } = loadScripts(['config/labels.js']);
  const statuses = ['pending', 'running', 'done', 'skipped', 'expired', 'failed', 'cancelled'];
  statuses.forEach((s) => {
    assert.notEqual(window.HirisLabels.taskStatusLabel(s), s, 'stato "' + s + '" deve avere una etichetta tradotta');
  });
  // 'executed' non e' uno stato reale: deve degradare al valore grezzo, non sparire.
  assert.equal(window.HirisLabels.taskStatusLabel('executed'), 'executed');
});

test('HirisLabels copre gli stati dei suggerimenti, compreso "recorded"', () => {
  const { window } = loadScripts(['config/labels.js']);
  assert.equal(window.HirisLabels.suggestionStatusLabel('recorded'), 'Registrato');
  assert.equal(window.HirisLabels.suggestionStatusLabel('applied'), 'Applicato');
  // Valore sconosciuto -> degrada al grezzo.
  assert.equal(window.HirisLabels.suggestionStatusLabel('mai-visto'), 'mai-visto');
});

test('HirisLabels copre le tre severita reali delle segnalazioni', () => {
  const { window } = loadScripts(['config/labels.js']);
  assert.equal(window.HirisLabels.advisorySeverityLabel('info'), 'INFO');
  assert.equal(window.HirisLabels.advisorySeverityLabel('warn'), 'AVVISO');
  assert.equal(window.HirisLabels.advisorySeverityLabel('high'), 'CRITICO');
  // Sconosciuta -> degrada a maiuscolo del valore grezzo, non sparisce.
  assert.equal(window.HirisLabels.advisorySeverityLabel('boh'), 'BOH');
});

test('HirisLabels.triggerDescription copre i cinque tipi reali di trigger, non quelli inesistenti', () => {
  const { window } = loadScripts(['config/labels.js']);
  const L = window.HirisLabels;
  assert.equal(L.triggerDescription({ type: 'delay', minutes: 30 }), 'tra 30 min');
  assert.equal(L.triggerDescription({ type: 'at_time', time: '18:00' }), 'alle 18:00');
  assert.equal(L.triggerDescription({ type: 'at_datetime', datetime: '2026-04-23T18:00:00' }), '2026-04-23T18:00:00');
  assert.equal(L.triggerDescription({ type: 'time_window', from: '18:00', to: '20:00' }), 'finestra 18:00–20:00');
  assert.equal(L.triggerDescription({ type: 'immediate' }), 'immediato');
  // Tipi mai generati da task_tools.py/task_engine.py: nessun ramo dedicato,
  // degradano all'etichetta/valore grezzo invece di un branch fantasma.
  assert.equal(L.triggerDescription({ type: 'cron', cron: '* * * * *' }), 'cron');
  assert.equal(L.triggerDescription(null), '');
});
