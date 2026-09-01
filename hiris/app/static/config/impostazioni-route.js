/* HIRIS · Config · Impostazioni chat (route #/impostazioni)
   fetta E5 Task 2. I sette campi di `ChatSettings`
   (hiris/app/impostazioni_chat.py) governano l'unica conversazione che HIRIS
   sa avere. Fino a quel task si cambiavano SOLO scrivendo a mano
   /data/impostazioni_chat.json: questa pagina e le due rotte
   GET/PUT api/chat-settings sono la loro prima interfaccia.

   fetta "Modelli" (2.0), Task 12: settimo campo, `retention_days` --
   arrivato da `history_retention_days` (l'opzione dell'add-on). Non e'
   aspetto, non e' una chiave, non e' rete: e' una decisione sulla
   conversazione, come le altre.

   Nessuna dipendenza da editor-kit.js / entity-picker.js / templates.js: tutti
   e tre escono al Task 6 di questa fetta, e una pagina nuova che ci si
   appoggiasse nascerebbe gia' condannata. Le sole cose che questo file usa
   sono `document` e `fetch`.

   Sicurezza: testi via textContent / nodi DOM, mai innerHTML su dati del
   server (stesso vincolo di models-route.js; history-route.js, citato qui
   fino alla fetta "esce il documentale", e' uscito con la pagina
   Storicizzazione; agentbot-route.js, citato fino al Task 11, era uscito con
   la fetta E5 Task 6 insieme al workbench).

   fetta "la catena diventa l'unica verita'" (Task 4): il selettore del
   modello NON e' piu' qui, e con lui sono usciti il secondo `fetch`
   (GET api/models) e il ripiego a campo di testo che quella lettura
   alimentava. Il modello si sceglie per provider, nella pagina Modelli: era
   uno SCAVALCO -- se valorizzato, `LLMRouter.chat` sceglieva il provider da
   se' con `_route()`, saltava la catena e annullava il ripiego, e la pagina
   Modelli non lo nominava mai. Il sottotitolo lo DICE, una volta: un campo
   che sparisce senza dire dove e' andato e' una crudelta'. */
window.HirisImpostazioniRoute = (function () {
  'use strict';

  var URL_IMPOSTAZIONI = 'api/chat-settings';

  /* Etichette italiane dei modi di risposta. Le CHIAVI ammesse arrivano dal
     server (payload `response_modes`), non sono scritte qui: se il backend ne
     aggiunge una e questa mappa non la conosce, si mostra la chiave grezza
     invece di far sparire l'opzione. */
  var ETICHETTE_MODO = {
    auto: 'Auto — nessun vincolo di lunghezza',
    compact: 'Compatta — risposte brevi',
    minimal: 'Minima — solo l\'essenziale'
  };

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  /* Stesso wrapper di models-route.js (`api()`, :68-73): l'header
     X-Requested-With NON e' facoltativo -- `csrf_middleware`
     (api/middleware_csrf.py) risponde 403 a ogni PUT/POST/DELETE su /api/ che
     non lo porta. Sta qui, in un punto solo, perche' dimenticarlo su una sola
     chiamata e' il modo esatto in cui questa pagina smetterebbe di salvare. */
  function api(url, opts) {
    opts = opts || {};
    opts.headers = Object.assign(
      { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      opts.headers || {});
    return fetch(url, opts);
  }

  function campo(body, titolo, descrizione, controllo) {
    var wrap = el('div');
    wrap.style.cssText = 'padding:12px 0 4px';
    var t = el('div', null, titolo);
    t.style.cssText = 'font-weight:500;margin-bottom:4px';
    wrap.appendChild(t);
    wrap.appendChild(controllo);
    if (descrizione) wrap.appendChild(el('p', 'sc-desc', descrizione));
    body.appendChild(wrap);
    return controllo;
  }

  function input(tipo, valore) {
    var i = el('input');
    i.type = tipo;
    i.value = valore == null ? '' : String(valore);
    i.style.cssText = 'padding:8px 10px;border-radius:8px;min-height:44px;box-sizing:border-box;' +
      (tipo === 'number' ? 'width:140px' : 'width:100%');
    return i;
  }

  function render(outlet, dati) {
    outlet.innerHTML = '';
    outlet.appendChild(el('div', 'page-title', 'Impostazioni chat'));
    /* La dichiarazione che manca quasi ovunque in questo prodotto: cosa
       succede DOPO il salvataggio. Qui l'effetto e' immediato perche' il PUT
       riassegna app["impostazioni_chat"] (api/handlers_impostazioni.py), che
       e' lo stesso oggetto che handlers_chat.py rilegge a ogni turno. */
    outlet.appendChild(el('p', 'page-subtitle',
      'La configurazione dell\'unica conversazione di HIRIS. Le modifiche valgono ' +
      'dal messaggio successivo: non serve riavviare l\'add-on. ' +
      'Il modello non si sceglie più qui: si sceglie per provider, nella pagina Modelli.'));

    var card = el('section', 'section-card');
    var body = el('div', 'sc-body');

    var nome = campo(body, 'Nome',
      'Come si chiama l\'assistente nell\'interfaccia.', input('text', dati.name));

    var prompt = el('textarea');
    prompt.value = dati.system_prompt || '';
    prompt.rows = 10;
    prompt.style.cssText = 'width:100%;box-sizing:border-box;padding:8px 10px;border-radius:8px;' +
      'font-family:var(--font-mono,monospace);font-size:13px';
    campo(body, 'Prompt di sistema',
      'Arriva parola per parola in testa a ogni turno di chat: è la cosa più ' +
      'delicata di HIRIS. Se lo svuoti e salvi, torna il testo predefinito ' +
      'scritto nel codice — non resta mai vuoto.', prompt);

    /* Il ritorno indietro, esplicito: il default arriva dal server
       (`default_system_prompt`), non da una copia tenuta qui che
       invecchierebbe alla prima modifica del prompt nel codice. */
    var ripristina = el('button', 'btn', 'Ripristina il prompt predefinito');
    ripristina.type = 'button';
    ripristina.style.cssText = 'margin-top:6px';
    ripristina.addEventListener('click', function () {
      prompt.value = dati.default_system_prompt || '';
    });
    body.appendChild(ripristina);

    var modi = (dati.response_modes && dati.response_modes.length)
      ? dati.response_modes : ['auto'];
    var selModo = el('select');
    selModo.style.cssText = 'padding:8px 10px;border-radius:8px;min-height:44px;box-sizing:border-box;width:100%';
    modi.forEach(function (m) {
      var o = el('option', null, ETICHETTE_MODO[m] || m);
      o.value = m;
      if (m === dati.response_mode) o.selected = true;
      selModo.appendChild(o);
    });
    campo(body, 'Forma della risposta',
      'Quanto deve essere asciutta la risposta.', selModo);

    /* Fix round 1 (I-2). La versione precedente prometteva «viene disattivato
       comunque e il log lo dice», ed era vero su UN percorso su tre: sugli
       altri due (OpenAI/OpenRouter/Ollama via openai_compat_runner, e il ponte
       per abbonamento) il valore veniva scartato senza una riga. Le due righe
       di log ora ci sono, ma la descrizione non le promette come se
       l'impostazione avesse effetto ovunque: dice PRIMA dove vale, che e' cio'
       che serve a chi sta decidendo quanto scrivere. */
    var thinking = campo(body, 'Budget di ragionamento (token)',
      '0 disattiva il ragionamento esteso. Vale solo con i modelli Claude sul ' +
      'percorso diretto: sugli altri backend (OpenAI, OpenRouter, Ollama) e in ' +
      'modalità abbonamento resta salvato ma non ha effetto, e il log lo dice a ' +
      'ogni turno. Anche sul percorso diretto, sotto i 1024 token o su un modello ' +
      'che non lo supporta viene disattivato.',
      input('number', dati.thinking_budget));
    thinking.min = '0';

    var turni = campo(body, 'Tetto di turni per sessione',
      '0 significa nessun tetto. Oltre il tetto la chat risponde che il limite ' +
      'è stato raggiunto, invece di continuare a consumare.',
      input('number', dati.max_chat_turns));
    turni.min = '0';

    /* fetta "Modelli" (2.0), Task 12: arrivato da `history_retention_days`
       (l'opzione dell'add-on) -- non e' aspetto, non e' una chiave, non e' rete:
       e' una decisione sulla conversazione, come gli altri campi di questa
       pagina. Il numero fa DUE lavori e la descrizione li dice entrambi: nessuno
       dei due era mai stato scritto da nessuna parte prima di questo task. */
    var conservazione = campo(body, 'Giorni di conservazione',
      'Ogni notte cancella i messaggi più vecchi di questo numero di giorni. ' +
      'Lo stesso numero limita quanto HIRIS rilegge della conversazione in ' +
      'corso: abbassarlo gli fa dimenticare prima. 0 = non cancella mai niente.',
      input('number', dati.retention_days));
    conservazione.min = '0';

    var riga = el('label');
    riga.style.cssText = 'display:flex;align-items:center;gap:10px;padding:12px 0 4px;cursor:pointer';
    var casa = el('input');
    casa.type = 'checkbox';
    casa.checked = !!dati.restrict_to_home;
    casa.style.cssText = 'width:20px;height:20px;flex:0 0 auto';
    riga.appendChild(casa);
    riga.appendChild(el('span', null, 'Rispondi solo su argomenti di casa'));
    body.appendChild(riga);
    body.appendChild(el('p', 'sc-desc',
      'Aggiunge al prompt l\'istruzione di declinare le domande che non ' +
      'riguardano la casa.'));

    var barra = el('div');
    barra.style.cssText = 'margin-top:16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap';
    var salva = el('button', 'btn btn-primary', 'Salva');
    salva.type = 'button';
    var stato = el('span', 'sc-desc', '');
    stato.setAttribute('aria-live', 'polite');
    barra.appendChild(salva);
    barra.appendChild(stato);
    body.appendChild(barra);

    function mostraEsito(testo) {
      /* aria-live annuncia le MUTAZIONI del contenuto: si svuota e si
         riscrive, cosi' due errori identici di fila vengono comunque letti
         (stessa ragione documentata in models-route.js, showErrBadge). */
      stato.textContent = '';
      stato.textContent = testo;
    }

    salva.addEventListener('click', function () {
      var corpo = {
        name: nome.value,
        system_prompt: prompt.value,
        response_mode: selModo.value,
        /* I tre interi passano da parseInt: un campo number svuotato produce
           '' e Number('') sarebbe 0 -- per retention_days "non cancella
           mai niente", non solo per i due tetti -- senza che l'utente lo
           abbia chiesto. Con NaN si manda il valore corrente, che il PUT
           conserva. */
        thinking_budget: numero(thinking.value, dati.thinking_budget),
        max_chat_turns: numero(turni.value, dati.max_chat_turns),
        restrict_to_home: !!casa.checked,
        retention_days: numero(conservazione.value, dati.retention_days)
      };
      salva.disabled = true;
      mostraEsito('Salvataggio…');
      api(URL_IMPOSTAZIONI, { method: 'PUT', body: JSON.stringify(corpo) })
        .then(function (r) {
          return r.json().catch(function () { return {}; })
            .then(function (j) { return { ok: r.ok, corpo: j }; });
        })
        .then(function (esito) {
          salva.disabled = false;
          if (esito.ok) {
            /* I valori tornati dal server sono quelli davvero in vigore (il
               prompt puo' essere tornato al default): si aggiorna la vista
               con QUELLI, non con cio' che si era digitato. */
            dati = esito.corpo;
            nome.value = dati.name || '';
            prompt.value = dati.system_prompt || '';
            selModo.value = dati.response_mode || 'auto';
            thinking.value = String(dati.thinking_budget);
            turni.value = String(dati.max_chat_turns);
            casa.checked = !!dati.restrict_to_home;
            conservazione.value = String(dati.retention_days);
            mostraEsito('Salvato. Vale dal prossimo messaggio.');
            return;
          }
          /* Mai un catch vuoto: l'errore del server dice quale campo non va,
             e quel testo e' scritto per essere letto da chi sta compilando. */
          mostraEsito(esito.corpo && esito.corpo.error
            ? esito.corpo.error
            : 'Salvataggio non riuscito. Controlla il log dell\'add-on.');
        })
        .catch(function () {
          salva.disabled = false;
          mostraEsito('Salvataggio non riuscito: il server non ha risposto.');
        });
    });

    card.appendChild(body);
    outlet.appendChild(card);
  }

  function numero(grezzo, ripiego) {
    var n = parseInt(grezzo, 10);
    return isNaN(n) ? ripiego : n;
  }

  function errore(outlet, testo) {
    outlet.innerHTML = '';
    outlet.appendChild(el('div', 'page-title', 'Impostazioni chat'));
    outlet.appendChild(el('p', 'page-subtitle', testo));
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    outlet.innerHTML = '';
    outlet.appendChild(el('div', 'page-title', 'Impostazioni chat'));
    outlet.appendChild(el('p', 'page-subtitle', 'Caricamento…'));

    /* Una lettura sola: le impostazioni. Il secondo `fetch` (GET api/models,
       che alimentava il selettore del modello) e' uscito con lui alla fetta
       "la catena diventa l'unica verita'" -- questa pagina non ha piu'
       nessuna ragione di conoscere i provider. */
    api(URL_IMPOSTAZIONI, { method: 'GET' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
      .then(function (dati) { render(outlet, dati); })
      .catch(function () {
        errore(outlet, 'Non è stato possibile leggere le impostazioni della chat. ' +
          'Controlla il log dell\'add-on e ricarica la pagina.');
      });
  }

  return { mount: mount };
})();
