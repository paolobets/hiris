/* HIRIS · dizionario condiviso di etichette (A4 + B1).

   Perche' esiste: stati e tipi venivano ricopiati a mano in ogni superficie
   (chat + config), in inglese grezzo, e senza un confronto con cio' che il
   backend scrive davvero. Due difetti concreti nati cosi':
   - tasks-route.js conosceva uno stato 'executed' che task_engine.py non
     scrive mai (scrive 'done') -> il chip "eseguiti" filtrava sempre a zero;
   - lo stesso file elencava tipi di trigger ('cron', 'state_changed',
     'absolute_time') che task_tools.py/task_engine.py non generano, mentre
     ne mancavano di reali ('at_time', 'at_datetime', 'time_window',
     'immediate').
   Un dizionario unico, caricato da entrambe le pagine come modulo senza DOM
   esposto su window (stesso schema di config/proposals-core.js), elimina la
   copia a mano: chi vuole un'etichetta la chiede qui, non la riscrive altrove.

   Fonte di verita' per i valori (non riderivare, verificare qui se cambia):
   - stati task: hiris/app/task_engine.py (Task.status, _TERMINAL) — sette:
     pending, running, done, skipped, expired, failed, cancelled.
   - stati suggerimenti Brain: hiris/app/brain/suggestions.py (record/
     set_status) — proposed, applied, dismissed, recorded, superseded.
   - severita' segnalazioni Brain: hiris/app/brain/health_checks.py — info,
     warn, high.
   - tipi di trigger task: hiris/app/tools/task_tools.py +
     hiris/app/task_engine.py (add_task) — delay, at_time, at_datetime,
     time_window, immediate.

   Ogni get* qui sotto degrada al valore grezzo se la chiave e' sconosciuta:
   una voce non mappata deve restare visibile (anche se non tradotta), mai
   sparire.

   Caricato come <script src> statico sia in config.html sia in
   static/index.html (la chat), PRIMA di ogni modulo che lo usa. */
(function() {
  var TASK_STATUS_LABELS = {
    pending: 'In attesa',
    running: 'In corso',
    done: 'Eseguito',
    skipped: 'Saltato',
    expired: 'Scaduto',
    failed: 'Fallito',
    cancelled: 'Cancellato',
  };

  /* Classe CSS per il pallino/testo di stato (.ok/.err esistono in
     hiris-config.css; le altre chiavi restano senza colorazione dedicata,
     come pending oggi -- non e' una regressione, e' lo stato attuale). */
  var TASK_STATUS_CLS = {
    pending: 'warn',
    running: 'warn',
    done: 'ok',
    skipped: '',
    expired: '',
    failed: 'err',
    cancelled: '',
  };

  var SUGGESTION_STATUS_LABELS = {
    proposed: 'Proposto',
    applied: 'Applicato',
    dismissed: 'Ignorato',
    recorded: 'Registrato',
    superseded: 'Sostituito',
  };

  var ADVISORY_SEVERITY_LABELS = {
    info: 'INFO',
    warn: 'AVVISO',
    high: 'CRITICO',
  };

  var TRIGGER_TYPE_LABELS = {
    delay: 'Ritardo',
    at_time: 'Orario',
    at_datetime: 'Data e ora',
    time_window: 'Finestra oraria',
    immediate: 'Immediato',
  };

  function taskStatusLabel(status) { return TASK_STATUS_LABELS[status] || status || '—'; }
  function taskStatusCls(status) { return TASK_STATUS_CLS[status] || ''; }
  function suggestionStatusLabel(status) { return SUGGESTION_STATUS_LABELS[status] || status || '—'; }
  function advisorySeverityLabel(sev) {
    return ADVISORY_SEVERITY_LABELS[sev] || (sev ? String(sev).toUpperCase() : '—');
  }
  function triggerTypeLabel(type) { return TRIGGER_TYPE_LABELS[type] || type || '—'; }

  /* Descrizione leggibile di un trigger completo (tipo + dettagli), usata
     sia dal pannello task della chat sia dalla pagina Task del config.
     Ritorna stringa vuota se non c'e' trigger -- il chiamante decide se
     mostrare un placeholder ('—') o nascondere del tutto la riga. */
  function triggerDescription(t) {
    if (!t || typeof t !== 'object') return '';
    switch (t.type) {
      case 'delay': return 'tra ' + (t.minutes || 0) + ' min';
      case 'at_time': return 'alle ' + (t.time || '');
      case 'at_datetime': return t.datetime || '';
      case 'time_window': return 'finestra ' + (t.from || '') + '–' + (t.to || '');
      case 'immediate': return 'immediato';
      default: return triggerTypeLabel(t.type);
    }
  }

  window.HirisLabels = {
    TASK_STATUS_LABELS: TASK_STATUS_LABELS,
    TASK_STATUS_CLS: TASK_STATUS_CLS,
    SUGGESTION_STATUS_LABELS: SUGGESTION_STATUS_LABELS,
    ADVISORY_SEVERITY_LABELS: ADVISORY_SEVERITY_LABELS,
    TRIGGER_TYPE_LABELS: TRIGGER_TYPE_LABELS,
    taskStatusLabel: taskStatusLabel,
    taskStatusCls: taskStatusCls,
    suggestionStatusLabel: suggestionStatusLabel,
    advisorySeverityLabel: advisorySeverityLabel,
    triggerTypeLabel: triggerTypeLabel,
    triggerDescription: triggerDescription,
  };
})();
