/* HIRIS · Config · la pagina #/models — «chi risponde alle tue domande, e in
   che ordine».

   Quattro blocchi, in quest'ordine (progetto §3):
     «Adesso»   la risposta: chi risponde al prossimo messaggio. Non numerato,
                perché non fa decidere niente -- dice cosa succede.
     01 LA CATENA           le righe in uso, in ordine. È l'unica verità: un
                            provider è usato se e solo se sta qui.
     02 FUORI DALLA CATENA  chi potrebbe entrare, e chi non può finché manca
                            la credenziale.
     la riga degli embedding, senza numero: non è una decisione (progetto §8).

   Il blocco «03 QUANDO NON DECIDE LA CATENA» del progetto §3 è CANCELLATO e
   non si disegna: esisteva solo per dichiarare che un modello fissato in
   «Impostazioni chat» scavalcava la catena, e quel campo è uscito col Task 4
   (`handlers_chat` chiede sempre "auto", la PUT rifiuta la chiave). Disegnarlo
   sarebbe un avviso per uno stato irraggiungibile.

   Fino alla 2.4.1 questo file aveva tre sezioni -- «Provider e credenziali»,
   «Catena automatica», «Embeddings» -- e le prime due erano DUE
   RAPPRESENTAZIONI DELLA STESSA COSA: un elenco di provider con un badge di
   stato, e una catena ricostruita a parte da `buildDisplayChain`, che
   riproduceva in JavaScript la stessa regola che il backend applicava in
   Python. Due rappresentazioni della stessa cosa possono divergere, ed è
   esattamente il modo in cui questa pagina ha potuto essere vera riga per riga
   e falsa nel complesso: mostrava «Attivo» un provider a credito esaurito e
   mostrava spento un provider che stava lavorando. Fuse in una, la divergenza
   è impossibile per costruzione.

   LA REGOLA DI QUESTO FILE: la pagina disegna ciò che le viene detto e non
   calcola niente. `catena[]` e `fuori_catena[]` arrivano già ordinate da
   `model_resolution.compose_topology`, la frase in cima da
   `compose_now`, e ogni parola che afferma qualcosa sul prodotto (i nomi,
   le nature, «manca il token», il perché una riga non si sposta) viene dal
   payload. Se qui dentro comparisse un `.sort()`, un confronto fra
   `chain_order` e le credenziali, o un `if (id === 'subscription')`, il
   difetto sarebbe tornato per un'altra porta -- e il test «la pagina NON
   ricostruisce la catena» (Task 2) è lì per accorgersene.
   L'unica eccezione, delimitata e dichiarata, è `recomposeLayout`: vedi il
   commento sopra la funzione.

   Vale anche per il PANNELLO DEL MODELLO (Task 9), che è la parte più recente
   e quella in cui sarebbe stato più facile ricominciare: la provenienza
   dell'elenco, la spiegazione, da quando la scelta ha effetto e persino DOVE
   va scritta (`dove`, un percorso dentro `state.cfg`) arrivano dal payload.
   È il percorso, in particolare, a permettere a questo file di non sapere che
   il modello di Ollama non vive in `provider_models` e che il piano non ha
   niente da salvare.

   La parola «Attivo» non compare in questo file e non deve comparirci.
   Significava «interruttore acceso E credenziale presente» e si leggeva
   «funziona»: una chiave a credito esaurito era «Attivo».

   Sicurezza: testi via textContent/createElement, mai innerHTML su dati server
   (stesso vincolo di dashboard.js e settings-route.js). */
(function() {
  'use strict';

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function clearEl(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
    return node;
  }

  function byId(id) {
    return document.getElementById(id);
  }

  function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign(
      { 'Content-Type': 'application/json', 'X-Requested-With': 'fetch' },
      opts.headers || {});
    return fetch(path, opts);
  }

  /* L'ordine di «Fuori dalla catena», dove un ordine non significa niente e
     quindi non può contraddire niente. DUPLICA `model_resolution.FIXED_ORDER`
     (il frontend non importa Python): le due liste sono tenute legate da un
     test che si rompe -- test_models_frontend_wiring.py. */
  var FIXED_ORDER = ['claude', 'subscription', 'openrouter', 'openai', 'ollama'];

  /* I tre ordini per esteso, da `llm_router._STRATEGY_ORDER`. Vivono qui
     perché un preset è un GESTO che riscrive la catena, non uno stato
     persistente da cui la catena si deriva: `llm_strategy` come impostazione
     esce con questa fetta. Nessun «preset corrente» da mostrare, nessuna
     regola di precedenza da spiegare, nessun arbitro da mantenere.
     Anche questi sono pinnati lato Python: gli ordini esistono due volte. */
  var PRESET = {
    balanced: { nome: 'Bilanciato', ordine: ['claude', 'openrouter', 'openai', 'ollama'] },
    cost_first: { nome: 'Risparmio', ordine: ['ollama', 'openrouter', 'openai', 'claude'] },
    quality_first: { nome: 'Qualità massima', ordine: ['claude', 'openai', 'openrouter', 'ollama'] }
  };

  var ERR_SAVE = '⚠ Salvataggio non riuscito';

  /* ── Stato locale ──────────────────────────────────────────────────────
     Tutto viene dal payload di GET api/models/config e niente si deriva:
     `catena` e `fuoriCatena` sono le due liste già ordinate. */
  var state = {
    /* Falso finché il PRIMO `GET api/models/config` non è tornato, e l'unica
       cosa che lo mette a vero è il suo `.then()`. Nessuna scrittura parte
       prima: `state.cfg`, qui sotto, è una FORMA -- una catena vuota, nessun
       modello, il ponte ai predefiniti -- non uno stato letto dal prodotto, e
       mandarla al server con una PUT vorrebbe dire scrivere quei predefiniti
       sopra la configurazione vera. I tre preset «Rifai la catena» stanno
       nell'intestazione della sezione, cioè restano a schermo anche quando
       `renderError` sostituisce il corpo: dopo un GET fallito erano, insieme
       a «Riprova», l'unica cosa cliccabile della pagina, e un click mandava
       una PUT che azzerava l'archivio. Nascono `disabled` (mount) e si
       abilitano di là. */
    loaded: false,
    catena: [],            // GET api/models/config -> catena[]
    fuoriCatena: [],       // GET api/models/config -> fuori_catena[]
    adesso: null,          // GET api/models/config -> adesso (la decisione già presa)
    /* GET api/models/config -> ponte.attivo. Fino alla 2.5.0 arrivava in un
       campo suo, `ponte_attivo`, che era `BRIDGE_ENABLED or _sub_first_class`
       e poteva dire `true` mentre `ponte.attivo` diceva `false`: due risposte
       alla stessa domanda nello stesso payload. Il campo è uscito con la
       versione B, e questo valore viene da dove vive. */
    bridgeActive: false,
    fineCatena: '',        // GET api/models/config -> fine_catena
    /* Il pannello aperto, o `null`. `{ id, dati, errore, filtro }`, dove
       `dati` è la voce di GET api/models?provider=<id> -- letta QUANDO IL
       PANNELLO SI APRE, non al caricamento della pagina: quella rotta
       interroga davvero OpenAI/OpenRouter/Ollama con cinque secondi di
       pazienza ciascuno, e fino al Task 8 la pagina la leggeva a ogni
       caricamento per un risultato che nessuno guardava. */
    pannello: null,
    cfg: {
      chain_order: [],
      provider_models: { claude: '', openai: '', openrouter: '' },
      ponte: { attivo: false, scadenza_min: 5, tetto_giornaliero: 50, modello: 'sonnet' },
      ollama: { modello: '', timeout_s: 120 },
      nascondi_gratuiti: false,
      strategia_ultima: ''
      /* `seminato` NON sta qui ed è deliberato: è il segno che la migrazione
         (versione A) è avvenuta, non una decisione dell'utente. Un client HTTP
         non deve poterlo riscrivere -- rimandarlo a `false` farebbe RIGIRARE la
         semina al riavvio successivo, e dopo la versione B, con l'ambiente
         muto, ricopierebbe i predefiniti: la perdita silenziosa che le due
         versioni della migrazione esistono per evitare. Il backend lo tiene
         fuori da `_OUR_KEYS` (`api/handlers_models.py`), quindi anche una
         PUT che lo portasse non lo toccherebbe; qui non viaggia proprio. */
    }
  };

  /* I tre bottoni «Rifai la catena», per poterli abilitare quando il primo GET
     torna. Vivono fuori da `state` perché sono nodi del DOM, non dati. */
  var presetButtons = [];

  /* ── PUT api/models/config — SEMPRE l'oggetto intero (§7.2), serializzato ──
     Due controlli che scrivono quasi in contemporanea potrebbero far arrivare
     le risposte fuori ordine se le richieste partissero in parallelo, e un PUT
     con uno snapshot "vecchio" di state.cfg sovrascriverebbe sul server una
     modifica più recente. Mutex a catena di promise: al più una richiesta in
     volo per volta, e ogni richiesta legge state.cfg SOLO quando è il suo turno
     di partire (non quando viene accodata). */
  var putChain = Promise.resolve();
  function putModelsConfig() {
    var result = putChain.then(function() {
      return api('api/models/config', { method: 'PUT', body: JSON.stringify(state.cfg) })
        .then(function(r) { return r.ok; })
        .catch(function() { return false; });
    });
    /* La catena deve proseguire anche se questa chiamata fallisce, altrimenti
       un fallimento bloccherebbe per sempre le PUT successive in coda. */
    putChain = result.catch(function() { return null; });
    return result;
  }

  /* ── «Adesso»: la risposta, prima delle ragioni ────────────────────────
     Non è una sezione e non è numerata: la numerazione, in questa pagina,
     significa «qui si decide qualcosa». Questo riquadro non fa decidere
     niente -- dice cosa succede.

     Non compone NESSUNA frase: `adesso.frase` e ogni `diagnosi[].testo`
     arrivano già scritti da `model_resolution.compose_now`. È l'invariante
     2 della spec applicato al testo e non solo all'ordine: se le parole si
     componessero qui, esisterebbero due posti che affermano cose sul
     prodotto, e uno dei due prima o poi affermerebbe più di quanto il sistema
     sa.

     `aria-live` (debito lasciato aperto dal Task 2, e chiuso qui). Il guscio
     del riquadro nasce VUOTO in `mount()`, prima della fetch, ed è riempito
     quando la risposta arriva: una regione viva annuncia le mutazioni di
     contenuto, non la propria comparsa, quindi un riquadro creato già pieno e
     poi inserito non verrebbe letto da nessuno. È la cosa più importante della
     pagina e cambia UNA volta per caricamento: `polite` la fa leggere senza
     interrompere, e non c'è nessun altro momento in cui questo testo cambi --
     i gesti sulla catena non ridisegnano il riquadro (la decisione nuova la
     dice il backend, alla prossima lettura). */
  function renderNow() {
    var card = byId('now-card');
    if (!state.adesso || !state.adesso.frase) {
      if (card && card.parentNode) card.parentNode.removeChild(card);
      return;
    }
    if (!card) card = createNowShell();
    clearEl(card);
    card.appendChild(el('p', 'now-phrase', state.adesso.frase));

    var diagnosis = state.adesso.diagnosi;
    if (Array.isArray(diagnosis) && diagnosis.length) {
      var ul = el('ul', 'now-diagnosis');
      diagnosis.forEach(function(d) {
        if (!d || !d.testo) return;
        var li = el('li', 'diagnosis-' + (d.gravita || 'guasto'), d.testo);
        /* Il gesto accanto alla riga che lo motiva. La pagina non sa che cosa
           sta accendendo: riceve un'etichetta, un PERCORSO nell'archivio e un
           valore, e li applica -- la stessa disciplina del pannello del
           modello (`dati.dove`, Task 9). Senza `dove` non si disegna niente:
           un bottone senza bersaglio sarebbe un bottone che non fa niente. */
        if (d.azione && Array.isArray(d.azione.dove) && d.azione.dove.length) {
          li.appendChild(actionButton(d.azione));
        }
        ul.appendChild(li);
      });
      if (ul.firstChild) card.appendChild(ul);
    }
  }

  function actionButton(action) {
    var b = el('button', 'btn btn-sm diagnosis-action', action.etichetta || '');
    b.type = 'button';
    b.addEventListener('click', function() { applyAction(action); });
    return b;
  }

  /* Applica il gesto, e poi RILEGGE. Come `chooseModel` e per la stessa
     ragione: ciò che cambia non è una posizione già determinata dal gesto (le
     frecce si ridisegnano da sé), è CHI RISPONDE -- la frase in cima, la
     presenza del piano in testa, il connettore. Ricomporlo qui vorrebbe dire
     calcolarlo, cioè rimettere la topologia nella pagina. In caso di
     fallimento si rimette il valore di prima: la pagina non deve restare a
     mostrare una scelta che il disco non ha accettato. */
  function applyAction(action) {
    if (!state.loaded) return;
    var where = action.dove;
    var precedente = readPath(where);
    writePath(where, action.valore);
    clearChainError();
    putModelsConfig().then(function(ok) {
      if (!ok) {
        writePath(where, precedente);
        showChainError(ERR_SAVE);
        return;
      }
      loadModelsAndConfig();
    });
  }

  function createNowShell() {
    var card = el('div', 'now-card');
    card.id = 'now-card';
    card.setAttribute('aria-live', 'polite');
    var outlet = byId('route-outlet');
    /* Sopra la prima section-card: la risposta viene prima delle ragioni. */
    if (outlet) outlet.insertBefore(card, outlet.querySelector('.section-card'));
    return card;
  }

  /* ── La row-provider ──────────────────────────────────────────────────
     Una riga è una frase su quattro colonne, e ogni colonna risponde a una
     domanda diversa: dove sei (la posizione), chi sei (il nome), con che cosa
     (il modello), quanto costi (la natura). Il pallino non è mai l'unico
     segnale (WCAG 1.4.1): accanto c'è sempre il testo.

     Non calcola NIENTE: posizione, nome, modello, natura, che cosa manca e
     perché una riga non si muove arrivano dal payload. */
  function providerRow(data, dentro) {
    /* `rifiuta` è un FATTO che arriva dal payload (`esito.tipo`), non una
       deduzione dal testo di stato: leggere una regola dentro una frase è come
       ricostruirla, e questa pagina ha smesso di ricostruire. Serve a due cose
       sole, entrambe di aspetto -- il pallino e il peso del nome. */
    var reject = !!(data.esito && data.esito.tipo === 'rifiutato');
    var row = el('div', 'row-provider' + (dentro ? '' : ' row-outside')
      + (reject ? ' row-muted' : ''));
    row.setAttribute('data-provider', data.id);
    row.setAttribute('role', 'listitem');
    row.appendChild(el('span', 'row-pos',
      data.posizione == null ? '' : String(data.posizione)));
    /* Il pallino di chi ha rifiutato diventa grigio-ambra, non rosso: una riga
       che non risponde deve SMETTERE DI SEMBRARE ATTIVA, che è la traduzione
       grafica del ritiro della parola «Attivo» -- non diventare un allarme.
       E non è mai l'unico segnale: la riga di stato qui sotto dice a parole
       che cosa è successo (WCAG 1.4.1). */
    row.appendChild(el('span', 'dot ' + (reject ? 'muted'
      : (data.ha_credenziale ? 'on' : 'off'))));
    row.appendChild(el('span', 'row-name', data.nome));
    /* Il modello sta NELLA RIGA, sempre visibile, e si clicca per cambiarlo.
       Un bottone e non uno `<span>` con un listener: apre e chiude una cosa, e
       chi naviga da tastiera deve poterci arrivare come ci arriva alle frecce.
       `modello_alias` decide il carattere -- un identificatore ha l'aspetto di
       un identificatore, un alias ha l'aspetto di una parola (progetto §6.2) --
       e arriva dal payload, perché è un fatto sul prodotto e non una regola
       che questa pagina possa conoscere. */
    var model = el('button',
      'row-model' + (data.modello_alias ? ' model-alias' : ''),
      data.modello || '—');
    model.type = 'button';
    model.setAttribute('aria-expanded', 'false');
    model.setAttribute('aria-label',
      'Modello di «' + data.nome + '»: ' + (data.modello || 'nessuno') + '. Cambia');
    model.addEventListener('click', function() { openModelPanel(data.id); });
    row.appendChild(model);
    row.appendChild(el('span', 'row-nature',
      data.ha_credenziale ? data.natura : (data.manca || '')));

    var actions = el('span', 'row-actions');
    /* I gesti che scrivono `chain_order` -- entrare, uscire, salire, scendere
       -- si disegnano SOLO dove il backend dice `riordinabile`. Non c'è nessun
       `if (dati.id === 'subscription')` qui, ed è deliberato: la pagina non sa
       niente del piano, obbedisce a un campo. Il giorno in cui il piano si
       governasse da `chain_order`, il backend risponderebbe `true` e i bottoni
       comparirebbero senza che nessuno tocchi questo file -- e, cosa che conta
       di più, non esiste nessun momento in cui la pagina possa offrire un gesto
       che il backend rifiuterebbe. (Oggi lo rifiuterebbe davvero:
       `save_models_config` scarta `subscription` da `chain_order`, quindi un
       «Usa» sul piano scriverebbe una PUT accettata con 200 e buttata via.) */
    if (dentro && data.riordinabile) {
      var su = iconButton('↑', 'row-up', 'Sposta «' + data.nome + '» su',
        function() { moveInChain(data.id, -1); });
      su.disabled = !neighbourInChain(data.id, -1);
      var down = iconButton('↓', 'row-down', 'Sposta «' + data.nome + '» giù',
        function() { moveInChain(data.id, 1); });
      down.disabled = !neighbourInChain(data.id, 1);
      actions.appendChild(su);
      actions.appendChild(down);
      /* Uscire dalla catena si può sempre, dove entrarci si può: è il gesto
         simmetrico di «Usa», e toglierlo lascerebbe una riga che non si può
         disfare. */
      actions.appendChild(iconButton('✕', 'row-leave',
        'Togli «' + data.nome + '» dalla catena',
        function() { removeFromChain(data.id); }));
    } else if (!dentro && data.ha_credenziale && data.riordinabile) {
      var use = el('button', 'btn btn-ghost btn-sm row-use', 'Usa');
      use.type = 'button';
      use.addEventListener('click', function() { putInChain(data.id); });
      actions.appendChild(use);
    }
    /* Senza credenziale non si offre «Usa»: sarebbe un bottone che non può
       funzionare. E non si offre nemmeno un collegamento a «Configurazione
       add-on»: da dentro l'iframe di ingress non esiste, oggi, nessuna
       navigazione verso quella pagina che questo prodotto sappia fare -- un
       link che non naviga è la stessa promessa non mantenuta di un bottone che
       non fa niente. Dove si mette la credenziale lo dice una riga sola, in
       fondo alla sezione (renderFuori), invece di cinque bottoni finti. */
    row.appendChild(actions);

    /* Una riga che non offre i gesti delle altre deve dire perché, altrimenti
       l'assenza si legge come un guasto. La parola arriva dal payload
       (`compose_topology`), perché è una regola del prodotto e cambia con
       lei. */
    /* La riga di stato: l'ultimo esito OSSERVATO, e quanto è vecchio. È ciò
       che chiude il caso del proprietario -- fino a questa fetta la pagina
       sapeva dire «Claude è primo in catena» e non «e sta rifiutando da
       quaranta richieste», mentre una chiave a credito zero veniva mostrata
       come funzionante.

       La frase arriva dal payload (`model_resolution.occurrence_phrase`) e non si
       compone qui: dice quanto tempo fa, con quale codice e da quante
       richieste, cioè tre affermazioni sul prodotto. È anche il motivo per cui
       questa riga non ha bisogno di essere toccata dal Task 14: quando il
       ponte imparerà a ripiegare, la frase nuova arriverà già scritta.

       Vuota quando non c'è niente da dire (nessuna credenziale e nessuna
       osservazione: la riga dice già «manca la chiave»), e la pagina disegna
       solo ciò che non è vuoto -- nessuna condizione sul provider vive qui. */
    if (data.stato_testo) {
      row.appendChild(el('div', 'row-status' + (reject ? ' status-rejected' : ''),
        data.stato_testo));
    }
    if (data.nota) row.appendChild(el('div', 'row-note', data.nota));
    return row;
  }

  function iconButton(text, cls, label, action) {
    var b = el('button', 'btn-icon-only ' + cls, text);
    b.type = 'button';
    b.setAttribute('aria-label', label);
    b.addEventListener('click', action);
    return b;
  }

  /* ── Il pannello del modello ───────────────────────────────────────────
     Non è un catalogo: OpenRouter ne espone più di duecento, e una tenda con
     duecento voci dentro una riga distruggerebbe la leggibilità che tutto il
     resto costruisce. È un FILTRO, con la curatela che il prodotto ha già
     (`_OPENROUTER_PRESETS`, undici voci scelte a mano) come stato d'apertura.

     Il campo in cima è un filtro E un campo di testo: digitando si filtra la
     lista vera, e ciò che si digita compare in fondo come voce sua, salvabile
     -- il backend accetta qualunque stringa. Nessuna capacità persa, nessun
     catalogo aperto per difetto.

     Il pannello dell'abbonamento offre tre voci e non di più, e non è una
     semplificazione: `agent/runner.cli_model` riduce tutto a
     opus/haiku/sonnet per sottostringa. Offrire `claude-opus-4-7` sul piano
     sarebbe una precisione finta -- sul ponte due opus diversi producono lo
     stesso identico comportamento.

     E come ogni altra cosa in questo file, il pannello NON compone nessuna
     frase: la provenienza dell'elenco, la spiegazione, da quando la scelta ha
     effetto e persino DOVE va scritta arrivano dal payload. Il percorso
     (`dove`) è ciò che permette a questo codice di non sapere che il modello
     di Ollama non vive in `provider_models`: senza, servirebbe un
     `if (id === '...')`, cioè una regola del prodotto scritta una seconda
     volta in un altro linguaggio. */
  function openModelPanel(idProvider) {
    if (state.pannello && state.pannello.id === idProvider) {
      closePanel();
      return;
    }
    closePanel();
    state.pannello = { id: idProvider, dati: null, errore: false, filtro: '' };
    drawPanel();
    loadPanel(idProvider);
  }

  function closePanel() {
    var open = document.querySelector('.panel-model');
    if (open && open.parentNode) open.parentNode.removeChild(open);
    var button = document.querySelectorAll('.row-model[aria-expanded="true"]');
    for (var i = 0; i < button.length; i++) {
      button[i].setAttribute('aria-expanded', 'false');
    }
    state.pannello = null;
  }

  /* La lettura è PIGRA, un provider alla volta, e parte quando il pannello si
     apre. Prima l'elenco intero veniva letto al caricamento della pagina --
     cioè si interrogavano davvero OpenAI, OpenRouter e Ollama, cinque secondi
     di pazienza ciascuno -- per un risultato che dal Task 8 nessuno guardava.
     E rende vera la parola: «letti adesso» detto su una lettura fatta quando
     hai aperto la pagina sarebbe più largo del fatto. */
  function loadPanel(idProvider) {
    fetch('api/models?provider=' + encodeURIComponent(idProvider))
      .then(function(r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function(body) {
        if (!state.pannello || state.pannello.id !== idProvider) return;
        var voci = (body || {}).providers || [];
        var data = null;
        voci.forEach(function(v) { if (v && v.id === idProvider) data = v; });
        state.pannello.dati = data;
        state.pannello.errore = !data;
        drawPanel();
      })
      .catch(function(err) {
        console.error('api/models fetch failed', err);
        if (!state.pannello || state.pannello.id !== idProvider) return;
        state.pannello.errore = true;
        drawPanel();
      });
  }

  /* Il pannello vive DENTRO la riga a cui appartiene: espanso, non
     sovrapposto. Non è una scelta grafica -- una riga ha `role="listitem"`, e
     un blocco appeso al corpo della sezione sarebbe un figlio di `role="list"`
     che non è una voce di elenco. Dentro la riga, invece, è quello che è: un
     dettaglio di quella riga. */
  function drawPanel() {
    var precedente = document.querySelector('.panel-model');
    if (precedente && precedente.parentNode) {
      precedente.parentNode.removeChild(precedente);
    }
    var p = state.pannello;
    if (!p) return;
    var line = document.querySelector('.row-provider[data-provider="' + p.id + '"]');
    if (!line) return;
    var button = line.querySelector('.row-model');
    if (button) button.setAttribute('aria-expanded', 'true');

    var box = el('div', 'panel-model');
    box.setAttribute('role', 'group');
    /* Chiudere con Esc: un pannello che si apre da un click e si chiude solo
       da un altro click è una trappola per chi naviga da tastiera. */
    box.addEventListener('keydown', function(ev) {
      if (ev.key === 'Escape' || ev.keyCode === 27) {
        closePanel();
        if (button && button.focus) button.focus();
      }
    });

    var head = el('div', 'panel-head');
    var title = el('h3', 'panel-title',
      'Modello di ' + ((p.dati && p.dati.nome) || line.querySelector('.row-name').textContent));
    head.appendChild(title);
    head.appendChild(iconButton('✕', 'panel-close', 'Chiudi',
      function() { closePanel(); }));
    box.appendChild(head);
    box.setAttribute('aria-label', title.textContent);

    if (p.errore) {
      box.appendChild(el('p', 'proposals-error',
        'Non riesco a leggere l’elenco dei modelli.'));
      var ancora = el('button', 'btn btn-ghost btn-sm', 'Riprova');
      ancora.type = 'button';
      ancora.addEventListener('click', function() {
        p.errore = false;
        drawPanel();
        loadPanel(p.id);
      });
      box.appendChild(ancora);
    } else if (!p.dati) {
      box.appendChild(el('p', 'field-hint', 'Caricamento…'));
    } else {
      panelBody(box, p);
    }
    line.appendChild(box);
    return box;
  }

  function panelBody(box, p) {
    var data = p.dati;
    var writable = !!(data.dove && data.dove.length);

    /* Da dove viene l'elenco. La classe porta il FATTO (viva/riserva/fissa),
       la frase le parole: la stessa divisione di `diagnosi[].gravita` e
       `diagnosi[].testo` nel riquadro «Adesso». */
    box.appendChild(el('p', 'panel-provenance source-' + (data.fonte || ''),
      data.provenienza || ''));

    /* Il campo si disegna solo dove c'è qualcosa da cercare FUORI dall'elenco.
       `elenco_completo` viene dal backend e questa pagina non sa per chi è
       vero: un `if (id === 'subscription')` qui sarebbe una regola del prodotto
       scritta una seconda volta in un altro linguaggio, cioè il difetto che
       questa pagina esiste per non avere.

       Senza questa guardia, il giorno in cui il piano ha guadagnato un campo
       suo il suo pannello avrebbe offerto di incollare `gpt-4o`, e il
       salvataggio lo avrebbe ridotto a `sonnet` senza dirlo: un controllo
       abilitato che non fa quello che dice — la stessa cosa che i tre radio
       spenti dichiaravano di voler evitare, rientrata dalla porta opposta. */
    if (writable && !data.elenco_completo) {
      var filter = el('input', 'panel-filter');
      filter.type = 'text';
      filter.value = p.filtro;
      filter.setAttribute('placeholder', 'filtra, o incolla un identificatore…');
      filter.setAttribute('aria-label', 'Filtra l’elenco, o incolla un identificatore');
      /* Si ridisegna SOLO l'elenco, non il pannello: rifare il campo a ogni
         tasto gli toglierebbe il fuoco e il cursore da sotto le dita. */
      filter.addEventListener('input', function() {
        p.filtro = filter.value;
        var old = box.querySelector('.panel-list');
        if (!old) return;
        old.parentNode.replaceChild(panelList(data, p, writable), old);
      });
      box.appendChild(filter);
    }

    box.appendChild(panelList(data, p, writable));

    /* La casella vive SOTTO l'elenco che filtra, e la pagina non sa per chi:
       le arrivano un'etichetta e un percorso dentro l'oggetto che già salva. */
    if (data.casella && data.casella.dove) {
      box.appendChild(panelBox(data.casella));
    }
    if (data.spiegazione) {
      box.appendChild(el('p', 'panel-explanation', data.spiegazione));
    }
    /* Da quando ha effetto la scelta, se mai avesse un tempo suo. Oggi il
       backend tace su tutti e cinque i provider (`model_resolution`: ogni
       valore di questa pagina vale dal prossimo messaggio) e questa riga non
       si disegna. Il canale resta perché la pagina non deve imparare una
       forma nuova il giorno in cui un campo tornasse ad avere un tempo
       proprio -- e perché una frase così è un'affermazione sul prodotto, che
       si scrive dove il prodotto la sa. */
    if (data.quando) {
      box.appendChild(el('p', 'panel-when', data.quando));
    }
    var statusEl = el('p', 'panel-status');
    statusEl.setAttribute('aria-live', 'polite');
    box.appendChild(statusEl);
  }

  function panelList(data, p, writable) {
    var list = el('div', 'panel-list');
    list.setAttribute('role', 'radiogroup');
    vociVisibili(data, p.filtro).forEach(function(v) {
      list.appendChild(modelEntry(data, v, writable));
    });
    if (!list.firstChild) list.appendChild(el('p', 'field-hint', 'Nessuno.'));
    return list;
  }

  /* Il filtro agisce sull'elenco vero, e ciò che si digita resta salvabile
     quando l'elenco non lo contiene: è la voce che compare al posto del
     vuoto. Le due cose sono lo stesso campo perché sono la stessa intenzione
     -- «voglio quello lì» -- e separarle costringerebbe a capire, prima di
     scrivere, se quello che si cerca esiste.

     La voce «scritto da te» compare SOLO quando non resta niente altro. Con
     dei risultati a schermo offrirebbe di salvare il pezzo di parola che si
     sta digitando (`gpt`), cioè un valore che il provider rifiuterebbe: un
     controllo che non può funzionare, che è il difetto di questa fetta in
     miniatura. Chi vuole un identificatore che l'elenco non ha lo incolla
     intero, e allora l'elenco si svuota e la voce c'è. */
  function vociVisibili(data, filter) {
    var text = (filter || '').trim();
    var bottom = text.toLowerCase();
    if (!text) return (data.modelli || []).slice();
    var voci = (data.modelli || []).filter(function(v) {
      return (v.valore || '').toLowerCase().indexOf(bottom) !== -1;
    });
    return voci.length ? voci : [{ valore: text, nota: 'scritto da te' }];
  }

  function modelEntry(data, v, writable) {
    var lab = el('label', 'panel-entry' + (data.alias ? ' entry-alias' : ''));
    var radio = el('input');
    radio.type = 'radio';
    radio.name = 'modello-' + data.id;
    radio.value = v.valore;
    radio.checked = (v.valore === data.scelto);
    /* Il pannello del piano MOSTRA e non scrive: il suo modello è un effetto
       di quello di Claude API, e non esiste nessun posto in cui scriverlo. Un
       controllo abilitato che non salva è la versione piccola del difetto che
       questa fetta chiude -- spento, invece, è una lettura onesta, come la
       freccia che non ha niente da scambiare. */
    radio.disabled = !writable;
    if (writable) {
      radio.addEventListener('change', function() {
        if (radio.checked) chooseModel(v.valore);
      });
    }
    lab.appendChild(radio);
    /* Il valore per primo, sempre: è ciò che si cerca leggendo. Quando è la
       voce «auto» (valore vuoto) a parlare è la sua nota, che dice anche a
       quale modello si risolve oggi. */
    if (v.valore) lab.appendChild(el('span', 'entry-value', v.valore));
    if (v.valore && v.nota) lab.appendChild(document.createTextNode(' '));
    if (v.nota) lab.appendChild(el('span', 'entry-note', v.nota));
    return lab;
  }

  function panelBox(checkbox) {
    var lab = el('label', 'panel-box');
    var box = el('input');
    box.type = 'checkbox';
    box.checked = !!readPath(checkbox.dove);
    box.addEventListener('change', function() {
      changeBox(checkbox.dove, box.checked);
    });
    lab.appendChild(box);
    lab.appendChild(el('span', null, checkbox.etichetta || ''));
    return lab;
  }

  /* ── I due percorsi: leggere e scrivere dentro `state.cfg` ──────────────
     `dove` è una lista di chiavi (`['provider_models','openrouter']`,
     `['ollama','modello']`, `['nascondi_gratuiti']`). Applicarla alla cieca è
     ciò che tiene questo file ignorante dei casi particolari. */
  function readPath(where) {
    var node = state.cfg;
    for (var i = 0; i < where.length; i++) {
      if (node == null) return undefined;
      node = node[where[i]];
    }
    return node;
  }

  function writePath(where, value) {
    var node = state.cfg;
    for (var i = 0; i < where.length - 1; i++) {
      if (node[where[i]] == null || typeof node[where[i]] !== 'object') node[where[i]] = {};
      node = node[where[i]];
    }
    node[where[where.length - 1]] = value;
  }

  /* Scegliere un modello e poi RILEGGERE. Le altre scritture di questa pagina
     si ridisegnano da sole perché ciò che cambiano -- le posizioni -- è già
     determinato dal gesto; qui no: il modello che una riga mostra è quello che
     il runtime userebbe, e «auto» si risolve in un nome che solo il backend
     conosce. Disegnarlo da qui vorrebbe dire calcolarlo. E la prima frase
     della pagina NOMINA il modello: lasciarla ferma la farebbe mentire di
     nuovo, in corpo 20. */
  function chooseModel(value) {
    if (!state.loaded) return;
    var p = state.pannello;
    if (!p || !p.dati) return;
    var where = p.dati.dove || [];
    if (!where.length) return;
    var precedente = readPath(where);
    writePath(where, value);
    putModelsConfig().then(function(ok) {
      if (ok) {
        closePanel();
        loadModelsAndConfig();
        return;
      }
      writePath(where, precedente);
      showPanelError(ERR_SAVE);
    });
  }

  /* La casella invece NON ricarica la pagina: cambia l'elenco che si sta
     guardando, e il posto dove guardarlo è quello aperto adesso. */
  function changeBox(where, value) {
    if (!state.loaded) return;
    var p = state.pannello;
    var precedente = readPath(where);
    writePath(where, value);
    putModelsConfig().then(function(ok) {
      if (!state.pannello || state.pannello !== p) return;
      if (ok) {
        state.pannello.dati = null;
        drawPanel();
        loadPanel(state.pannello.id);
        return;
      }
      writePath(where, precedente);
      drawPanel();
      showPanelError(ERR_SAVE);
    });
  }

  function showPanelError(text) {
    var p = document.querySelector('.panel-status');
    if (!p) return;
    p.textContent = '';
    p.textContent = text;
  }

  /* ── Il connettore ─────────────────────────────────────────────────────
     Un elenco numerato dice l'ordine. Non dice la cosa che serve per
     SCEGLIERE l'ordine: quanto costa passare oltre. E i costi qui non sono
     paragonabili -- differiscono di due ordini di grandezza.

     La frase arriva dal payload (`riga.connettore`), e non si compone qui: è
     la SOLA affermazione di questa pagina che, scritta bene per domani,
     sarebbe falsa oggi. Oggi il ponte non ripiega -- alla scadenza il messaggio
     va perso -- e un «se non risponde, si passa al successivo» disegnato fra il
     piano e la riga sotto prometterebbe un ripiego che il prodotto non fa: il
     difetto 3, ricomparso come didascalia. Il giorno del ripiego (Task 14)
     cambia una stringa in `compose_topology` e questa pagina dice la cosa
     nuova senza essere toccata.
     `note_connector` è il tetto utile che nessuno schema dichiara (la chat
     smette di aspettare a 5 minuti): sta FUORI dal connettore perché il
     connettore è la frase, e la frase è il numero.

     Qui la pagina decide solo DOVE, mai COSA: il connettore di una riga si
     disegna fra quella riga e la successiva, e dopo l'ultima si disegna
     `fine_catena`, che è una frase sulla catena e non su una riga -- quale sia
     l'ultima cambia con un gesto, e la pagina riordina da sé fra il gesto e la
     risposta del server. */
  function connettore(cls, text) {
    var c = el('div', cls, text);
    c.setAttribute('role', 'listitem');
    return c;
  }

  /* ── 01 LA CATENA ──────────────────────────────────────────────────────── */
  function renderChain() {
    var body = clearEl(byId('chain-body'));
    if (!body) return;
    var card = byId('chain-card');
    /* Col ponte acceso la catena resta VISIBILE e riordinabile: nascondere ciò
       che conta è proibito, e serve poterla preparare per quando il ponte si
       spegne. È disegnata come ciò che è -- inerte, adesso -- e a DIRE che è
       scavalcata è la nota della riga del piano, che arriva dal backend: una
       frase scritta qui resterebbe quella di oggi anche il giorno in cui il
       ponte imparerà a ripiegare (Task 14), cioè tornerebbe a mentire da sola.
       Il colore non è mai l'unico segnale (WCAG 1.4.1). */
    if (card) {
      if (state.bridgeActive) card.classList.add('chain-inert');
      else card.classList.remove('chain-inert');
    }

    if (!state.catena.length) {
      body.appendChild(el('p', 'field-hint', 'Vuota.'));
      return;
    }

    state.catena.forEach(function(data, i) {
      body.appendChild(providerRow(data, true));
      if (data.connettore && i < state.catena.length - 1) {
        body.appendChild(connettore('connector', data.connettore));
      }
      if (data.connettore_nota) {
        body.appendChild(connettore('connector-note', data.connettore_nota));
      }
    });
    if (state.fineCatena) {
      body.appendChild(connettore('connector', state.fineCatena));
    }
  }

  /* ── 02 FUORI DALLA CATENA ─────────────────────────────────────────────── */
  function renderOutside() {
    var body = clearEl(byId('outside-body'));
    if (!body) return;
    var note = byId('outside-note');
    if (note) note.textContent = '';
    if (!state.fuoriCatena.length) {
      body.appendChild(el('p', 'field-hint', 'Nessuno: sono tutti in catena.'));
      return;
    }
    var missing = false;
    state.fuoriCatena.forEach(function(data) {
      if (!data.ha_credenziale) missing = true;
      body.appendChild(providerRow(data, false));
    });
    /* Il confine fra le due pagine, detto UNA volta e dove serve: le
       credenziali si custodiscono nella configurazione dell'add-on, le
       decisioni si prendono qui. Ripeterlo su ogni riga sarebbe cinque volte
       la stessa frase; non dirlo lascerebbe «manca la chiave» senza il posto
       dove metterla. */
    if (missing && note) {
      note.textContent = 'Le chiavi si mettono in Configurazione add-on: è '
        + 'l\'unico posto che sa custodirle. Qui si decide chi risponde.';
    }
  }

  /* ── Le scritture ──────────────────────────────────────────────────────
     Schema unico: si muove `state.cfg.chain_order`, si ridisegna SUBITO (la
     pagina non aspetta il server: è la disciplina di scrittura ottimistica che
     questa pagina ha già), si salva, e se il salvataggio fallisce si torna
     ESATTAMENTE allo stato precedente -- posizioni comprese, perché
     `recomposeLayout` le ricalcola dall'ordine. */
  function writeChain(newOrder, errText) {
    /* Niente si scrive prima di aver letto: vedi `state.loaded`. */
    if (!state.loaded) return;
    var precedente = state.cfg.chain_order.slice();
    var strategiaPrecedente = state.cfg.strategia_ultima;
    state.cfg.chain_order = newOrder;
    recomposeLayout();
    clearChainError();
    renderChain();
    renderOutside();
    /* Il pannello segue la sua riga invece di sparire con lei: un riordino
       ridisegna le due sezioni, e un dettaglio che si chiude perche' hai
       spostato la riga che stavi guardando e' una perdita senza ragione. */
    drawPanel();
    putModelsConfig().then(function(ok) {
      if (ok) return;
      state.cfg.chain_order = precedente;
      state.cfg.strategia_ultima = strategiaPrecedente;
      recomposeLayout();
      renderChain();
      renderOutside();
      drawPanel();
      showChainError(errText || ERR_SAVE);
    });
  }

  /* L'UNICA cosa che questa pagina ricompone da sé, e solo fra un gesto e la
     risposta del server: le posizioni e l'appartenenza, che sono già
     determinate dall'ordine che l'utente ha appena scelto. Non è la topologia
     -- chi ha una credenziale, chi è il primo col ponte acceso, cosa costa,
     che parole porta: quelli restano quelli che il backend ha detto, e tornano
     aggiornati alla prossima lettura. Senza questo, un riordino resterebbe
     fermo finché il server non risponde, e la freccia sembrerebbe rotta.
     È la sola deroga all'invariante 2 in tutta la pagina, ed è delimitata: il
     test «la pagina NON ricostruisce la catena» (Task 2) monta la pagina con un
     payload in cui `chain_order` e `adesso` sono in disaccordo, e passa solo se
     al PRIMO disegno vince il payload. */
  function recomposeLayout() {
    var perId = {};
    state.catena.concat(state.fuoriCatena).forEach(function(r) { perId[r.id] = r; });
    /* Le righe che NON si governano da `chain_order` restano dove il backend
       le ha messe -- oggi è il piano col ponte acceso, e questa funzione non ha
       bisogno di saperlo: le riconosce dal campo, come tutto il resto della
       pagina. Senza, un gesto qualunque le farebbe sparire dalla catena fino
       alla ricarica. */
    var dentro = state.catena.filter(function(r) { return !r.riordinabile; });
    state.cfg.chain_order.forEach(function(id) {
      var r = perId[id];
      if (r && r.riordinabile && r.ha_credenziale && dentro.indexOf(r) === -1) dentro.push(r);
    });
    state.catena = dentro.map(function(r, i) {
      return Object.assign({}, r, { posizione: i + 1 });
    });
    var idDentro = state.catena.map(function(r) { return r.id; });
    state.fuoriCatena = FIXED_ORDER.filter(function(id) {
      return perId[id] && idDentro.indexOf(id) === -1;
    }).map(function(id) { return Object.assign({}, perId[id], { posizione: null }); });
  }

  function rowById(id) {
    var line = state.catena.concat(state.fuoriCatena);
    for (var i = 0; i < line.length; i++) {
      if (line[i].id === id) return line[i];
    }
    return null;
  }

  function reorderableById(id) {
    var r = rowById(id);
    return !!(r && r.riordinabile);
  }

  /* Chi c'è sopra (direzione -1) o sotto (+1) in catena, fra le righe che si
     possono spostare -- ed è `null` quando non c'è nessuno, cioè quando quella
     freccia non avrebbe niente da scambiare. Serve a due cose che devono dire
     la stessa: disabilitare la freccia e rifiutare la scrittura. Si guarda alle
     righe VISIBILI e non a `chain_order` perché l'ordine salvato può contenere
     un provider senza credenziale, che non si disegna: scambiare con lui
     sembrerebbe una freccia rotta. */
  function neighbourInChain(id, direction) {
    var moving = state.catena.filter(function(r) { return r.riordinabile; })
      .map(function(r) { return r.id; });
    var k = moving.indexOf(id);
    if (k === -1) return null;
    var near = moving[k + direction];
    return near == null ? null : near;
  }

  function putInChain(id) {
    if (!reorderableById(id)) return;
    var order = state.cfg.chain_order.slice();
    if (order.indexOf(id) === -1) order.push(id);
    writeChain(order);
  }

  function removeFromChain(id) {
    if (!reorderableById(id)) return;
    writeChain(state.cfg.chain_order.filter(function(k) { return k !== id; }));
  }

  function moveInChain(id, direction) {
    /* Seconda guardia, sulla scrittura e non solo sul disegno: `chain_order`
       non contiene il piano (la sua posizione discende da `ponte.attivo`), e un
       id non riordinabile qui non troverebbe niente da spostare scrivendo
       comunque una PUT inutile. */
    if (!reorderableById(id)) return;
    var near = neighbourInChain(id, direction);
    if (!near) return;
    var order = state.cfg.chain_order.slice();
    var i = order.indexOf(id);
    var j = order.indexOf(near);
    if (i === -1 || j === -1) return;
    order[i] = near;
    order[j] = id;
    writeChain(order, 'Errore salvataggio ordine. Riprova.');
  }

  function redoChain(key) {
    var p = PRESET[key];
    if (!p) return;
    /* Solo chi ha una credenziale: mettere in catena un provider senza
       credenziale creerebbe una riga che non può funzionare, cioè la seconda
       rappresentazione dello stato che questa pagina ha appena tolto. */
    var credentialed = {};
    state.catena.concat(state.fuoriCatena).forEach(function(r) {
      credentialed[r.id] = r.ha_credenziale;
    });
    state.cfg.strategia_ultima = key;
    writeChain(p.ordine.filter(function(id) { return credentialed[id]; }));
  }

  /* La riga di esito delle scritture. Vive nel guscio della sezione e non nel
     corpo che viene ridisegnato, così è una regione viva che esiste PRIMA del
     fallimento; e si riscrive svuotandola, perché `aria-live` annuncia le
     mutazioni di contenuto e due fallimenti identici di seguito non
     produrrebbero nessuna mutazione da annunciare. */
  function showChainError(text) {
    var p = byId('chain-status');
    if (!p) return;
    p.textContent = '';
    p.textContent = text;
  }

  function clearChainError() {
    var p = byId('chain-status');
    if (p) p.textContent = '';
  }

  function renderError() {
    renderNow();
    var body = clearEl(byId('chain-body'));
    if (body) {
      body.appendChild(el('p', 'proposals-error', 'Errore caricamento provider.'));
      var btn = el('button', 'btn btn-ghost btn-sm', 'Riprova');
      btn.type = 'button';
      btn.addEventListener('click', function() { loadModelsAndConfig(); });
      body.appendChild(btn);
    }
    var outside = clearEl(byId('outside-body'));
    if (outside) {
      outside.appendChild(el('p', 'field-hint',
        'Impossibile leggere chi è fuori dalla catena — vedi qui sopra.'));
    }
  }

  /* ── Caricamento dati ─────────────────────────────────────────────────
     UNA lettura sola. Fino al Task 8 ce n'erano due, in parallelo: questa e
     `api/models`, che alimentava il picker «Modello di default» della vecchia
     sezione 01. Il picker è uscito con quella sezione e la lettura era rimasta
     -- una fetch il cui risultato nessuno legge, e non una qualunque: quella
     rotta interroga davvero OpenAI, OpenRouter e Ollama, con cinque secondi di
     pazienza ciascuno. Adesso si legge quando serve, un provider alla volta,
     all'apertura del pannello (`loadPanel`). */
  function loadModelsAndConfig() {
    var body = byId('chain-body');
    if (body) { clearEl(body); body.appendChild(el('p', 'field-hint', 'Caricamento…')); }
    fetch('api/models/config').then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function(answer) {
      var cfgRaw = answer || {};
      state.catena = Array.isArray(cfgRaw.catena) ? cfgRaw.catena : [];
      state.fuoriCatena = Array.isArray(cfgRaw.fuori_catena) ? cfgRaw.fuori_catena : [];
      state.adesso = (cfgRaw.adesso && typeof cfgRaw.adesso === 'object') ? cfgRaw.adesso : null;
      state.bridgeActive = !!(cfgRaw.ponte && cfgRaw.ponte.attivo);
      state.fineCatena = typeof cfgRaw.fine_catena === 'string' ? cfgRaw.fine_catena : '';
      state.cfg = {
        chain_order: Array.isArray(cfgRaw.chain_order) ? cfgRaw.chain_order.slice() : [],
        provider_models: Object.assign({ claude: '', openai: '', openrouter: '' },
                                       cfgRaw.provider_models || {}),
        ponte: Object.assign({ attivo: false, scadenza_min: 5, tetto_giornaliero: 50,
                               modello: 'sonnet' },
                             cfgRaw.ponte || {}),
        ollama: Object.assign({ modello: '', timeout_s: 120 }, cfgRaw.ollama || {}),
        nascondi_gratuiti: !!cfgRaw.nascondi_gratuiti,
        strategia_ultima: cfgRaw.strategia_ultima || ''
      };
      /* L'UNICO posto che apre le scritture, ed è il ramo del GET riuscito:
         da qui in poi `state.cfg` è ciò che il prodotto ha davvero. */
      state.loaded = true;
      presetButtons.forEach(function(b) { b.disabled = false; });
      clearChainError();
      renderNow();
      renderChain();
      renderOutside();
      drawPanel();
    }).catch(function(err) {
      console.error('models/config fetch failed', err);
      renderError();
    });
  }

  /* ── Shell statico ────────────────────────────────────────────────────── */
  function buildSectionShell(num, idPrefix, title, desc, bodyRole) {
    var section = el('section', 'section-card');
    section.id = idPrefix + '-card';
    var head = el('div', 'sc-header');
    head.appendChild(el('span', 'sc-num', num));
    head.appendChild(el('h2', 'sc-title', title));
    section.appendChild(head);
    section.appendChild(el('p', 'sc-desc', desc));
    var body = el('div', 'sc-body');
    body.id = idPrefix + '-body';
    /* Le righe e i connettori hanno role="listitem": la relazione list/listitem
       è ciò che fa leggere la catena come una sequenza, ed è la sequenza il
       contenuto di questa pagina. */
    if (bodyRole) body.setAttribute('role', bodyRole);
    body.appendChild(el('p', 'field-hint', 'Caricamento…'));
    section.appendChild(body);
    return section;
  }

  function mount() {
    /* Il modulo è un singleton e la route si rimonta: senza questo azzeramento
       un secondo montaggio partirebbe «già caricato» con lo `state.cfg` della
       visita precedente. */
    state.loaded = false;
    var outlet = document.getElementById('route-outlet');
    clearEl(outlet);
    outlet.appendChild(el('div', 'page-title', 'Modelli'));
    outlet.appendChild(el('p', 'page-subtitle', 'Chi risponde alle tue domande, e in che ordine.'));

    var chainCard = buildSectionShell('01', 'chain', 'La catena',
      'Le righe in uso, in ordine. È l\'unica verità: un provider è usato se e solo se sta qui.',
      'list');
    /* I tre preset: un gesto che RIFÀ la catena, non uno stato da cui la catena
       si deriva (progetto §5.3). Effetto immediato e visibile, e da quel momento
       la verità è di nuovo una sola. */
    var actions = el('div', 'sc-actions');
    actions.appendChild(el('span', 'sc-actions-label', 'Rifai la catena:'));
    presetButtons = [];
    Object.keys(PRESET).forEach(function(key) {
      var b = el('button', 'btn btn-ghost btn-sm', PRESET[key].nome);
      b.type = 'button';
      /* Spenti finché il primo GET non è tornato: un preset è un gesto che
         RIFÀ la catena, e rifarla su uno stato mai letto vuol dire cancellarla.
         `state.loaded` rifiuta comunque la scrittura -- questo lo dice a
         schermo, che è la metà che l'utente vede. */
      b.disabled = true;
      b.addEventListener('click', function() { redoChain(key); });
      presetButtons.push(b);
      actions.appendChild(b);
    });
    chainCard.querySelector('.sc-header').appendChild(actions);
    /* Qui viveva la confessione: «L'ordine si applica al riavvio
       dell'add-on». Era vera -- `handle_save_models_config` aggiornava
       l'archivio, ma la catena del router si costruiva all'avvio -- ed è
       uscita col difetto che la rendeva necessaria: la PUT rimette in vigore,
       e il riordino vale dal prossimo messaggio. Non è stata SOSTITUITA da un
       «vale subito»: l'assenza di didascalia È l'affermazione, ed è la cosa
       più onesta che questa pagina possa dire di sé. */
    var statusEl = el('p', 'chain-status');
    statusEl.id = 'chain-status';
    statusEl.setAttribute('aria-live', 'polite');
    chainCard.appendChild(statusEl);
    outlet.appendChild(chainCard);

    var outsideCard = buildSectionShell('02', 'outside', 'Fuori dalla catena',
      'Chi potrebbe entrare, e chi non può finché manca la credenziale.', 'list');
    var outsideNote = el('p', 'outside-note');
    outsideNote.id = 'outside-note';
    outsideCard.appendChild(outsideNote);
    outlet.appendChild(outsideCard);

    /* Il guscio del riquadro «Adesso», vuoto: esiste prima della fetch perché
       una regione viva annuncia ciò che le arriva dentro, non la propria
       comparsa. Sta sopra la prima sezione -- la risposta prima delle ragioni --
       e sparisce se il payload non porta la decisione (renderAdesso). */
    createNowShell();

    /* Gli embedding non sono una sezione e non sono numerati: la numerazione,
       qui, significa «si decide qualcosa», e questi non fanno niente. Restano
       in Configurazione add-on perché toglierli da lì costerebbe la perdita
       silenziosa di un valore in cambio di nulla (progetto §8). */
    outlet.appendChild(el('p', 'embedding-note',
      'Embedding: nessun testo viene vettorizzato, e i due campi in Configurazione add-on non ' +
      'hanno effetto. La ricerca per somiglianza è rimandata, non annullata.'));

    loadModelsAndConfig();
  }

  window.HirisModelsRoute = { mount: mount };
})();
