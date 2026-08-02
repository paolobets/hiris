import test from 'node:test';
import assert from 'node:assert/strict';
import { loadScripts, tick } from './helpers/dom.mjs';

/* Regressione: il chip "eseguiti" della pagina Task del config interrogava
   lo stato 'executed', che task_engine.py non scrive mai (scrive 'done').
   Risultato visibile: click su "eseguiti" -> il backend non trova nulla ->
   chip sempre a zero, anche con task davvero completati. Questo test
   simula la semantica reale del backend (list_tasks filtra per
   uguaglianza esatta sullo status) tramite lo stub di fetch: una query
   `status=executed` torna vuota, `status=done` torna il task completato.
   Prima della correzione il chip puntava a 'executed' e falliva; ora deve
   puntare a 'done'. */

test('chip "eseguiti": interroga status=done ed il conteggio non resta a zero', async () => {
  const { window, document } = loadScripts(
    ['config/labels.js', 'config/tasks-route.js'],
    { html: '<!doctype html><body><div id="route-outlet"></div></body>' },
  );

  const doneTask = {
    id: 't1', label: 'Irrigazione sera', status: 'done', agent_id: 'a1',
    created_at: '2026-08-01T18:00:00Z', trigger: { type: 'delay', minutes: 30 }, actions: [{}],
  };
  const pendingTask = {
    id: 't2', label: 'Promemoria', status: 'pending', agent_id: 'a1',
    created_at: '2026-08-01T19:00:00Z', trigger: { type: 'at_time', time: '20:00' }, actions: [{}],
  };
  const allTasks = [doneTask, pendingTask];

  const calls = [];
  window.fetch = async (url) => {
    const u = String(url);
    calls.push(u);
    if (u.indexOf('api/chatbots') !== -1) {
      return { ok: true, status: 200, json: async () => ([{ id: 'a1', name: 'Iris' }]) };
    }
    if (u.indexOf('status=done') !== -1) {
      return { ok: true, status: 200, json: async () => ([doneTask]) };
    }
    if (u.indexOf('status=') !== -1) {
      // Qualunque altro filtro esplicito (es. 'executed', se il bug
      // tornasse) non trova nulla -- come farebbe davvero list_tasks().
      return { ok: true, status: 200, json: async () => ([]) };
    }
    // 'api/tasks' senza query = fetchTasks('all') -> tutti i task.
    return { ok: true, status: 200, json: async () => (allTasks) };
  };

  window.HirisTasksRoute.mount();
  await tick(30);

  const doneChip = document.querySelector('#route-outlet [data-filter="done"]');
  assert.ok(doneChip, 'deve esistere un chip che filtra su "done" (lo stato scritto davvero da task_engine.py)');

  const executedChip = document.querySelector('#route-outlet [data-filter="executed"]');
  assert.equal(executedChip, null, 'non deve piu\' esistere un chip che filtra su "executed" (mai scritto dal motore)');

  doneChip.dispatchEvent(new window.Event('click', { bubbles: true }));
  await tick(30);

  const filterCall = calls.find((u) => u.indexOf('api/tasks?status=') !== -1);
  assert.ok(filterCall, 'il click sul chip deve fare una fetch filtrata');
  assert.match(filterCall, /status=done$/, 'la fetch deve interrogare status=done, non status=executed');

  const doneCount = document.getElementById('tasks-count-done');
  assert.equal(doneCount.textContent, '1', 'il conteggio del chip "eseguiti" deve contare il task done, non restare a zero');

  const rows = document.querySelectorAll('#tasks-list-body .log-row');
  assert.equal(rows.length, 1, 'la lista filtrata su "eseguiti" deve mostrare il task in stato done');
});

test('ogni stato reale del motore ha un chip proprio: nessuno resta invisibile fuori da "tutti"', async () => {
  const { window, document } = loadScripts(
    ['config/labels.js', 'config/tasks-route.js'],
    { html: '<!doctype html><body><div id="route-outlet"></div></body>' },
  );
  window.fetch = async (url) => {
    const u = String(url);
    if (u.indexOf('api/chatbots') !== -1) return { ok: true, status: 200, json: async () => ([]) };
    return { ok: true, status: 200, json: async () => ([]) };
  };

  window.HirisTasksRoute.mount();
  await tick(30);

  // I sette stati scritti da task_engine.py (Task.status / _TERMINAL).
  ['pending', 'running', 'done', 'skipped', 'expired', 'failed', 'cancelled'].forEach((status) => {
    const chip = document.querySelector('#route-outlet [data-filter="' + status + '"]');
    assert.ok(chip, 'manca un chip per lo stato "' + status + '"');
  });
});
