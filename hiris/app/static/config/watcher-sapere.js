/* HIRIS · Configurazione · «L'osservatore» / scheda «Cosa ho capito» (spec
   2026-09-18 §4C).

   *Cosa pensa della casa, e dove sbaglia?* E' la sezione 04 di ieri. «Se un
   dato c'e' e nessuno puo' chiederlo, non esiste»: fino al 15/09/2026 il
   sapere si leggeva da tre punti del codice e da nessuna pagina.

   E' la scheda dove vivono le DOMANDE APERTE e le CORREZIONI, cioe' le uniche
   cose che la pagina chiede al proprietario: la ragione per cui la spec le
   porta a un clic invece che in fondo a una colonna da oltre cinquecento
   righe (spec §0).

   -- i giudizi sui tipi (spec «i tre attori» §4, §7) --
   Gerarchia approvata dal proprietario il 17/09/2026 (task 9,
   .superpowers/sdd/2026-09-16-il-giudizio-dei-tipi/task-9-ux-approvata.md):
   «Cosa non ha capito» -> «Le tue correzioni» (righe `proprietario`+`altro`, e
   il modulo di aggiunta in testa) -> «I giudizi del seme» (sette gruppi
   chiusi, uno per campo -- sei approvati il 17/09/2026 piu'
   `da_sapere_subito`, spec 2026-09-18-da-sapere-subito.md §5) -> «Le domande
   aperte» (chiuse) -> «Cosa ha capito».

   **Una riga vive in un posto solo** (fondamenta HIRIS): chi ha corretto un
   giudizio del seme sparisce dal SUO gruppo e vive solo in «Le tue
   correzioni» -- il gruppo del seme ne conta il numero rimasto, non la
   nasconde e basta.

   -- il giro di correzioni 1 (revisione Fable, 17/09/2026) --
   Cinque difetti misurati e chiusi, che i commenti puntuali qui sotto
   richiamano per sigla senza ripetere la cronistoria: IMPORTANT 1 (la frase
   sulla cronaca mancava del tutto), IMPORTANT 2 (`da_sapere_subito` non
   compariva, e le etichette non erano ASSOCIATE ai campi), IMPORTANT 3 e
   MINOR 6 (il focus cadeva su `<body>` ad ogni passo), MINOR 4 (due frasi
   attaccate senza punto), MINOR 5 (il conteggio del gruppo ignorava le righe
   `altro`), MINOR 8 (il modulo di aggiunta non era un `<form>`).

   Sicurezza: mai innerHTML sul testo del server -- le domande aperte portano
   backtick e `**`, e si costruiscono nodo per nodo (`appendMarkedText`,
   watcher-shared.js). */
window.HirisWatcherSapere = (function () {
  'use strict';

  var S = HirisWatcherShared;
  var el = S.el;
  var clearEl = S.clearEl;
  var line = S.line;
  var subheading = S.subheading;
  var read = S.read;
  var write = S.write;
  var retryButton = S.retryButton;
  var createDisclosure = S.createDisclosure;
  var describeWatchedSubject = S.describeWatchedSubject;
  var judgmentField = S.judgmentField;
  var appendMarkedText = S.appendMarkedText;
  var firstSentenceTruncated = S.firstSentenceTruncated;
  var fmtWhenFull = S.fmtWhenFull;
  var fmtCount = S.fmtCount;
  var fmtDays = S.fmtDays;
  var fmtDateOnly = S.fmtDateOnly;
  var fmtDayMonth = S.fmtDayMonth;
  var TONE_PROBLEM = S.TONE_PROBLEM;
  var TONE_CALM = S.TONE_CALM;
  var TONE_UNKNOWN = S.TONE_UNKNOWN;

  /* I campi del sapere, detti come li direbbe una persona.

     La traduzione avviene al confine, e il confine è questa pagina: nel
     sapere il campo si chiama `ricetta_non_serve` perché è una colonna, qui
     si legge «niente da misurare» perché è una frase. Senza, la piastrella
     più grossa della scheda -- 18 dispositivi su 52, sulla casa vera --
     sembrerebbe un guasto, mentre è il contrario: il modello ha guardato e ha
     detto che non c'è niente che valga la pena. Un campo che non è in questa
     mappa esce col suo nome: meglio una parola tecnica che una inventata. */
  var KNOWLEDGE_FIELDS = {
    ricetta: 'ricette',
    ricetta_non_serve: 'niente da misurare',
    ricetta_non_capita: 'ricette non capite',
    significato: 'significati',
    attributi: 'attributi che contano',
    direzione: 'direzioni dell’energia'
  };

  function knowledgeFieldLabel(campo) {
    return KNOWLEDGE_FIELDS[campo] || campo;
  }

  /* I sette campi, nell'ordine approvato -- letterale, identico a
     GENRE_FIELD/RESTING_FIELD/NOTABLE_FIELD/OPERABLE_FIELD/
     PARAMETER_LIMITS_FIELD/WORKING_FIELD/DA_SAPERE_SUBITO_FIELD di
     home_space/type_judgments.py (contati nel sorgente Python, non
     ricopiati da una variabile). Fix round 1, IMPORTANT 2: `da_sapere_subito`
     (Task 1, spec 2026-09-18-da-sapere-subito.md §2) era un settimo campo nel
     sapere senza il suo settimo qui -- non compariva mai nella pagina. Resta
     fuori da `EDITABLE_JUDGMENT_FIELDS` (sotto): la spec §5 dichiara fuori da
     quella fetta la SCRITTURA di un valore nuovo dalla pagina -- il ritorno al
     seme, invece, la pagina lo fa gia' per qualunque riga corretta di
     qualunque campo (`revertToSeedControl`). */
  var JUDGMENT_FIELD_GROUPS = [
    { campo: 'genere', etichetta: 'Genere' },
    { campo: 'riposo', etichetta: 'Riposo' },
    { campo: 'notevole', etichetta: 'Notevole' },
    { campo: 'accendibile', etichetta: 'Accendibile' },
    { campo: 'limiti_parametri', etichetta: 'Limiti dei parametri' },
    { campo: 'lavoro', etichetta: 'Lavoro' },
    { campo: 'da_sapere_subito', etichetta: 'Da sapere subito' },
    { campo: 'impalcatura', etichetta: 'Impalcatura' }
  ];

  /* I campi che si correggono sul posto, e **le forme che quel campo ammette**.
     In v1 era solo `genere` (forma approvata, punto 3); `impalcatura` e'
     entrata il 20/09/2026 con la decisione del proprietario «hacs non e'
     qualcosa da monitorare»: se il criterio del primo piano vive nel sapere
     ma non si puo' correggere da qui, vive nel seme -- cioe' nel codice, che
     e' esattamente cio' che la fetta dichiarava di evitare.

     Una mappa e non due funzioni: l'editor e' lo stesso, cambiano le opzioni
     del menu. Gli altri cinque campi restano in sola lettura. */
  var EDITABLE_JUDGMENT_FIELDS = {
    genere: null,  // le sue opzioni sono `JUDGMENT_GENRE_OPTIONS`, qui sotto
    impalcatura: [
      { valore: 'si', etichetta: 'Sì: è Home Assistant che parla di sé' },
      { valore: 'no', etichetta: 'No: riguarda la casa' }
    ]
  };

  /* I campi che entrano nell'IMPRONTA della cronaca -- letterale, identico a
     `CHRONICLE_FIELDS = (GENRE_FIELD, RESTING_FIELD)` di
     home_space/type_judgments.py, e legato a quello da una prova che legge
     entrambi i sorgenti (`tests/js/watcher-sapere.test.mjs`).

     **Solo per questi la pagina può promettere che «la cronaca dei giorni
     passati si rifà da sola»** (revisione finale, I-4): l'impronta non
     comprende `notevole`, `accendibile`, `lavoro`, `limiti_parametri` né
     `da_sapere_subito`, e correggere uno di quelli non fa rifare nessun
     giorno. Prometterlo lo stesso era la pagina che diceva il falso proprio a
     chi corregge il campo di quella fetta. */
  var CHRONICLE_JUDGMENT_FIELDS = { genere: true, riposo: true };

  function rifaLaCronaca(campo) {
    return CHRONICLE_JUDGMENT_FIELDS[campo] === true;
  }

  /* L'etichetta italiana di un campo, dall'elenco qui sopra: serve alla riga di
     «Le tue correzioni», dove righe di campi diversi stanno mescolate e
     «lock · no · Corretto da te» non distingue `notevole` da
     `da_sapere_subito` (revisione finale, I-4). Un campo sconosciuto torna
     com'è scritto: meglio il nome tecnico che il silenzio. */
  function judgmentFieldLabel(campo) {
    for (var i = 0; i < JUDGMENT_FIELD_GROUPS.length; i += 1) {
      if (JUDGMENT_FIELD_GROUPS[i].campo === campo) return JUDGMENT_FIELD_GROUPS[i].etichetta;
    }
    return String(campo || '');
  }

  /* Valori JSON (liste/mappe), non tradotti -- `.text-mono` (forma
     approvata, punto 2). Gli altri campi portano un valore già leggibile. */
  var JSON_JUDGMENT_FIELDS = { riposo: true, lavoro: true, limiti_parametri: true };

  /* I generi che il proprietario può scegliere: CHRONICLE_GENRES meno
     `guasto` (le condizioni di sistema -- mai lo stato di un tipo o di
     un'entità, `judgments._SYSTEM_ONLY_GENRE`) più `nessuno` (`NO_GENRE`,
     "niente episodi") -- letterale da home_space/type_vocabulary.py, forma
     approvata punto 3. */
  var JUDGMENT_GENRE_OPTIONS = [
    { valore: 'funzionamento', etichetta: 'Funzionamento' },
    { valore: 'presenza', etichetta: 'Presenza' },
    { valore: 'sicurezza', etichetta: 'Sicurezza' },
    { valore: 'nessuno', etichetta: 'Nessuno (niente episodi)' }
  ];

  /* 22 giorni: la ritenzione del grezzo, `mind/store.READING_RETENTION_S`
     (server). NON arriva nel payload di `/api/mind/knowledge` -- se un
     campo un giorno la porta, questa costante si toglie e si legge da lì
     (regola del brief, task 9, sezione 04). */
  var CHRONICLE_RETENTION_DAYS = 22;

  function chronicleCostPhrase() {
    return 'rifà la cronaca degli ultimi ' + fmtDays(CHRONICLE_RETENTION_DAYS * 86400) +
      ', un giorno ogni 5 minuti: fino a circa due ore';
  }

  /* Il livello che il soggetto occupa nelle chiavi di `TypeJudgments`
     (dominio -> coppia -> entità, mirror di `judgments._level`, letto nel
     sorgente Python il 17/09/2026): serve solo a ORDINARE le righe del
     gruppo (forma approvata, punto 2), non a validarle -- quello lo fa il
     server, sul 400. */
  function judgmentSubjectLevel(kind, subject) {
    if (kind === 'entita') return 2;
    return (String(subject || '').indexOf('.') === -1) ? 0 : 1;
  }

  function sortJudgmentRows(righe) {
    return righe.slice().sort(function (a, b) {
      var la = judgmentSubjectLevel(a.soggetto_genere, a.soggetto);
      var lb = judgmentSubjectLevel(b.soggetto_genere, b.soggetto);
      if (la !== lb) return la - lb;
      return String(a.soggetto).localeCompare(String(b.soggetto));
    });
  }

  /* Nessun `aria-label` qui: il select passa SEMPRE da `judgmentField`
     (watcher-shared.js), che gli lega un'etichetta VERA (`for`/`id`) -- un
     `aria-label` in più vincerebbe quel legame per il nome accessibile
     (la regola di calcolo lo preferisce) e lo renderebbe invisibile a chi
     naviga per etichette, mentre il testo visibile resterebbe un altro
     («Genere» in entrambi i casi qui, ma sarebbe un doppione fragile). */
  function fieldOptions(campo) {
    return EDITABLE_JUDGMENT_FIELDS[campo] || JUDGMENT_GENRE_OPTIONS;
  }

  function genreSelect(campo) {
    var sel = el('select');
    fieldOptions(campo).forEach(function (o) {
      var opt = el('option', null, o.etichetta);
      opt.value = o.valore;
      sel.appendChild(opt);
    });
    return sel;
  }

  /* Il testo da mostrare quando la SCRITTURA (non la lettura della scheda)
     fallisce per un motivo che non è 400/409 -- stesso tono di
     `renderKnowledgeError`, adattato a un verbo di scrittura invece che di
     lettura (regola del brief: "le frasi di renderKnowledgeError").

     `corpo` è quello della risposta, quando c'è: dal 17/09/2026 il 503 ha DUE
     ragioni -- il sapere non collegato, e l'archivio che c'è ma non si lascia
     scrivere (disco pieno, base occupata; vedi `handlers_mind.py`) -- e il
     server manda la sua in `errore`. Scriverne qui una sola sarebbe una
     ragione falsa accanto al codice per l'altra metà dei casi. Il testo di
     riserva resta per quando il corpo non c'è (un 503 del proxy) o per un
     guasto di rete, dove non c'è nessuna risposta da leggere. */
  function judgmentWriteErrorText(status, corpo) {
    if (corpo && corpo.errore) return corpo.errore;
    if (status === 503) {
      return 'Il sapere non è collegato in questo momento. Non è vuoto — è che non si può leggere.';
    }
    return 'Non è stato possibile scrivere. Riprova più tardi.';
  }

  /* La scrittura, condivisa dall'editor del genere, da «Torna al seme» e dal
     modulo di aggiunta -- un solo posto per i quattro esiti della spec
     (200/400/409/rete), così i tre chiamanti non li interpretano ciascuno a
     modo suo (fondamenta: nessun doppione). */
  function submitJudgment(payload, ui) {
    ui.button.disabled = true;
    ui.esito.textContent = 'Scrivo…';
    return write('api/mind/judgment', payload).then(function (occurrence) {
      if (occurrence.ok) {
        /* 200: la scheda si ricarica intera -- la riga riappare in «Le tue
           correzioni» con la sua provenienza nuova (forma approvata, punto 3).
           `true`: sposta il focus sul titolo di «Le tue correzioni» dopo il
           ricaricamento (fix round 1, MINOR 6) -- senza, il bottone appena
           premuto sparisce col resto del corpo e il focus cade su `<body>`. */
        carica(ui.outerBody, undefined, true);
        return;
      }
      ui.button.disabled = false;
      if (occurrence.status === 400) {
        ui.esito.textContent = (occurrence.corpo && occurrence.corpo.errore) ||
          'Questa correzione non si può scrivere.';
        return;
      }
      if (occurrence.status === 409) {
        var motivo = (occurrence.corpo && occurrence.corpo.errore) || '';
        // Fix round 1, MINOR 4: senza un punto dopo `motivo` la frase
        // successiva si leggeva attaccata («…seme non ce l'ha Il sapere
        // legge…»). Non se ne aggiunge uno se `motivo` lo porta già
        // (niente «..»).
        var motivoPuntato = motivo && !/[.!?]$/.test(motivo) ? motivo + '.' : motivo;
        carica(ui.outerBody, 'La correzione è scritta ma non è in vigore: ' + motivoPuntato +
          ' Il sapere legge solo il seme.', true);
        return;
      }
      ui.esito.textContent = judgmentWriteErrorText(occurrence.status, occurrence.corpo);
    }, function () {
      ui.button.disabled = false;
      ui.esito.textContent = judgmentWriteErrorText(null);
    });
  }

  /* «Correggi» sul posto il campo di questa riga (uno di
     `EDITABLE_JUDGMENT_FIELDS`): apre/chiude un editor dentro la riga, senza
     modale. */
  function judgmentCorrectControl(g, outerBody) {
    var wrap = el('div');
    var toggle = el('button', 'btn btn-ghost', 'Correggi');
    toggle.type = 'button';
    toggle.setAttribute('aria-expanded', 'false');
    var panel = el('div');
    panel.hidden = true;
    panel.style.cssText = 'margin-top:8px;display:flex;flex-direction:column;gap:6px;max-width:340px';

    toggle.addEventListener('click', function () {
      var aperto = toggle.getAttribute('aria-expanded') === 'true';
      if (aperto) { clearEl(panel); panel.hidden = true; toggle.setAttribute('aria-expanded', 'false'); return; }
      clearEl(panel);
      var sel = genreSelect(g.campo);
      if (fieldOptions(g.campo).some(function (o) { return o.valore === g.valore; })) sel.value = g.valore;
      panel.appendChild(judgmentField(judgmentFieldLabel(g.campo), sel));
      /* **Il costo si dice solo per i campi che lo hanno.** `impalcatura` non
         entra nell'impronta: si legge quando la pagina legge, e cambiarla non
         fa rifare nessun giorno. Un avviso falso insegna a ignorare quelli
         veri. */
      if (rifaLaCronaca(g.campo)) {
        panel.appendChild(el('p', 'field-hint',
          'Cambiare ' + judgmentFieldLabel(g.campo).toLowerCase() + ' ' + chronicleCostPhrase() + '.'));
      }
      var esito = el('p', 'sc-desc', '');
      var scrivi = el('button', 'btn btn-ghost', 'Scrivi');
      scrivi.type = 'button';
      scrivi.addEventListener('click', function () {
        submitJudgment({
          soggetto_genere: g.soggetto_genere, soggetto: g.soggetto, campo: g.campo,
          valore: sel.value
        }, { button: scrivi, esito: esito, outerBody: outerBody });
      });
      panel.appendChild(scrivi);
      panel.appendChild(esito);
      panel.hidden = false;
      toggle.setAttribute('aria-expanded', 'true');
    });

    wrap.appendChild(toggle);
    wrap.appendChild(panel);
    return wrap;
  }

  /* «Torna al seme» (forma approvata, punto 5): niente `confirm()`, due
     passi in linea. Vale per righe `proprietario` E `altro`, di qualunque
     campo -- manda `valore: null`. */
  function revertToSeedControl(g, outerBody) {
    var wrap = el('div');
    var start = el('button', 'btn btn-ghost', 'Torna al seme');
    start.type = 'button';
    var confirmBox = el('div');
    confirmBox.hidden = true;
    confirmBox.style.cssText = 'margin-top:6px;display:flex;flex-direction:column;gap:6px;max-width:340px';
    /* La seconda frase vale solo per i campi dell'impronta (revisione finale,
       I-4): tornare al seme su `da_sapere_subito` non fa rifare nessun giorno,
       e annunciare due ore di ricostruzione a chi non le pagherà è un avviso
       falso -- che per di più scoraggia una correzione che non costa niente. */
    var testoWarn = 'Cancella la tua correzione: il sapere riprende il valore del seme, o ' +
      'nessuna riga se il seme non ne ha.';
    if (rifaLaCronaca(g.campo)) testoWarn += ' Anche questo ' + chronicleCostPhrase() + '.';
    var warn = el('p', 'field-hint', testoWarn);
    var actions = el('div');
    actions.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap';
    var yes = el('button', 'btn btn-ghost btn-ghost-danger', 'Sì, torna al seme');
    yes.type = 'button';
    var cancel = el('button', 'btn btn-ghost', 'Annulla');
    cancel.type = 'button';
    var esito = el('p', 'sc-desc', '');

    /* Fix round 1, IMPORTANT 3: nascondere il bottone che ha il focus lo fa
       cadere su `<body>` (il browser non lo sposta da solo) -- chi naviga da
       tastiera perdeva il posto ad ogni passo. Si sposta ESPLICITAMENTE, dopo
       aver reso visibile il bersaglio. */
    start.addEventListener('click', function () {
      start.hidden = true; confirmBox.hidden = false; yes.focus();
    });
    cancel.addEventListener('click', function () {
      confirmBox.hidden = true; start.hidden = false; start.focus();
    });
    yes.addEventListener('click', function () {
      submitJudgment({
        soggetto_genere: g.soggetto_genere, soggetto: g.soggetto, campo: g.campo, valore: null
      }, { button: yes, esito: esito, outerBody: outerBody });
    });

    actions.appendChild(yes);
    actions.appendChild(cancel);
    confirmBox.appendChild(warn);
    confirmBox.appendChild(actions);
    confirmBox.appendChild(esito);
    wrap.appendChild(start);
    wrap.appendChild(confirmBox);
    return wrap;
  }

  /* La provenienza di una riga (forma approvata, punto 4): `seme` è un
     testo quieto, `proprietario`/`altro` sono badge -- lo stesso linguaggio
     di `.agent-badge` già in uso nel resto della pagina, non un componente
     nuovo.

     **Fix round 1, IMPORTANT 1**: la forma approvata dice che una riga
     corretta dal proprietario porta ANCHE «La cronaca dei giorni passati si
     rifà da sola» -- mancava del tutto. Sta qui, accanto al badge, perché è
     una proprietà della riga finché resta `proprietario` (non una notifica
     che sparisce al primo ricaricamento): chi rivede la pagina domani deve
     rileggerla, non solo chi l'ha appena scritta.

     **Revisione finale, I-4**: la frase era incondizionata ed è vera solo per
     i campi dell'impronta (`CHRONICLE_JUDGMENT_FIELDS`). Su `da_sapere_subito`
     -- il campo che quella fetta aggiunge, e che con la cronaca non c'entra
     per costruzione (spec §6) -- la pagina prometteva a chi corregge una
     ricostruzione che non avviene. */
  function provenanceNode(g) {
    if (g.da === 'proprietario') {
      var wrap = el('span', 'jr-provenance');
      wrap.appendChild(el('span', 'agent-badge badge-on', 'Corretto da te il ' + (fmtDateOnly(g.quando_ts) || '—')));
      if (rifaLaCronaca(g.campo)) {
        wrap.appendChild(el('span', 'field-hint', 'La cronaca dei giorni passati si rifà da sola.'));
      }
      return wrap;
    }
    if (g.da === 'altro') {
      return el('span', 'agent-badge badge-warn',
        'Modificata a mano il ' + (fmtDayMonth(g.quando_ts) || '—') + ' da ' + (g.chi || 'qualcun altro'));
    }
    return el('span', 'field-hint', 'dal seme');
  }

  /* `da_sapere_subito` porta TRE forme (decisione del proprietario,
     18/09/2026): `si`, `no`, oppure l'elenco JSON degli stati che contano --
     `lock` porta `["jammed"]`, perché per lei `lavoro` vuol dire «sta
     operando» e l'inceppamento non è né lavoro né riposo.

     In pagina l'elenco si legge «solo: jammed»: il «solo» è la regola detta in
     italiano (entra quello stato e nient'altro), **gli stati si CITANO e non
     si traducono**. Scelta dichiarata: «inceppata» sarebbe una traduzione
     decisa qui, in un file di resa, cioè esattamente dove il vocabolario della
     casa non si decide — e finché non esiste la fetta che rende gli stati
     nella lingua della casa, mostrare il nome vero è ciò che permette a chi
     legge di ritrovarlo in Home Assistant. Gli stati stanno in un nodo loro
     (`.jr-value-states`, monospazio) come gli altri valori tecnici.

     Un valore che NON si interpreta si mostra com'è: mai un errore muto. */
  function judgmentStateList(valore) {
    if (typeof valore !== 'string' || valore.charAt(0) !== '[') return null;
    var stati;
    // Un valore che non si interpreta non e' un errore da gridare: si ricade
    // sulla resa grezza, che almeno mostra cosa c'e' scritto nell'archivio.
    try { stati = JSON.parse(valore); } catch { return null; }
    if (!Array.isArray(stati) || !stati.length) return null;
    for (var i = 0; i < stati.length; i += 1) {
      if (typeof stati[i] !== 'string') return null;
    }
    return stati;
  }

  function judgmentValueNode(g) {
    if (g.campo === 'da_sapere_subito') {
      var stati = judgmentStateList(g.valore);
      if (stati) {
        var wrap = el('span', 'jr-value');
        wrap.appendChild(document.createTextNode('solo: '));
        wrap.appendChild(el('span', 'jr-value-states text-mono', stati.join(', ')));
        return wrap;
      }
    }
    /* `.jr-value` su OGNI forma del valore, non solo qui: senza, una prova che
       volesse guardare il valore di una riga non ha altro appiglio che il testo
       dell'intera scheda -- e `/si/` combacia con «siren», cioe' con il nome
       del soggetto della riga accanto. E' una prova che non puo' fallire, il
       difetto n. 1 di questo progetto, reso possibile da una classe mancante. */
    var cls = JSON_JUDGMENT_FIELDS[g.campo] ? 'jr-value text-mono' : 'jr-value';
    return el('span', cls, g.valore == null ? '—' : g.valore);
  }

  /* Una riga: `soggetto | valore | provenienza | azioni` (forma approvata,
     punto 6), a griglia larga e impilata sotto i 768px -- mai una
     `<table>` (CSS: `.jr-row` in hiris-config.css).

     `mostraCampo` (revisione finale, I-4): in «Le tue correzioni» righe di
     campi diversi stanno mescolate, e senza il nome del campo «lock · no ·
     Corretto da te» vale identica per `notevole` e per `da_sapere_subito` --
     chi legge non sa cosa ha corretto. Dentro «I giudizi del seme» il campo è
     già il titolo del gruppo e ripeterlo su ogni riga sarebbe rumore. */
  function judgmentRow(g, outerBody, mostraCampo) {
    var riga = el('div', 'sc-row jr-row');
    riga.appendChild(el('div', 'jr-subject text-mono', g.soggetto));
    var meta = el('div', 'jr-meta');
    if (mostraCampo === true) meta.appendChild(el('span', 'jr-field', judgmentFieldLabel(g.campo)));
    meta.appendChild(judgmentValueNode(g));
    meta.appendChild(provenanceNode(g));
    riga.appendChild(meta);
    var actions = el('div', 'jr-actions');
    if (Object.prototype.hasOwnProperty.call(EDITABLE_JUDGMENT_FIELDS, g.campo)) {
      actions.appendChild(judgmentCorrectControl(g, outerBody));
    }
    if (g.da === 'proprietario' || g.da === 'altro') actions.appendChild(revertToSeedControl(g, outerBody));
    riga.appendChild(actions);
    return riga;
  }

  /* Il modulo di aggiunta (forma approvata, punto 7): soggetto libero,
     tipo/entità OBBLIGATORIO (guida `soggetto_genere`), genere. Nessuna
     validazione client della FORMA del soggetto -- il 400 del server la
     spiega; il tipo/entità invece si controlla qui, perché senza non c'è
     `soggetto_genere` da mandare affatto.

     Fix round 1, MINOR 8: era un `<div>` con un bottone `type="button"` --
     Invio nel campo Soggetto non mandava niente, e `required` sui radio non
     aveva alcun form da validare. Un `<form>` vero con un bottone
     `type="submit"` restituisce entrambi; il controllo JS sul radio mancante
     resta (vedi sotto) perché un evento 'submit' sintetico (dispatchEvent,
     come nei test) NON passa dalla validazione nativa del browser -- solo un
     invio vero da tastiera/mouse la passa. */
  function addJudgmentForm(outerBody) {
    var wrap = el('form', 'field-group jr-add-form');
    wrap.style.cssText = 'border:1px solid var(--border-2);border-radius:8px;padding:10px 12px;' +
      'margin-bottom:10px;display:flex;flex-direction:column;gap:8px;max-width:420px';

    var subjectInput = el('input');
    subjectInput.type = 'text';
    subjectInput.placeholder = 'binary_sensor.occupancy';
    wrap.appendChild(judgmentField('Soggetto', subjectInput));

    var radioName = 'judgment-add-kind-' + Math.random().toString(36).slice(2);
    var radioWrap = el('div');
    radioWrap.style.cssText = 'display:flex;gap:14px;flex-wrap:wrap';
    function radioOption(value, testo) {
      var label = el('label');
      label.style.cssText = 'display:flex;align-items:center;gap:6px;min-height:28px';
      var input = el('input');
      input.type = 'radio'; input.name = radioName; input.value = value; input.required = true;
      label.appendChild(input);
      label.appendChild(document.createTextNode(testo));
      radioWrap.appendChild(label);
      return input;
    }
    var radioTipo = radioOption('tipo', 'Un tipo');
    var radioEntita = radioOption('entita', 'Un’entità');
    wrap.appendChild(radioWrap);
    wrap.appendChild(el('p', 'field-hint',
      'Un tipo vale per tutti i dispositivi di quella classe; un’entità per uno solo.'));

    var sel = genreSelect();
    wrap.appendChild(judgmentField('Genere', sel));

    var esito = el('p', 'sc-desc', '');
    var scrivi = el('button', 'btn btn-ghost', 'Scrivi');
    scrivi.type = 'submit';
    wrap.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var scelto = radioTipo.checked ? 'tipo' : (radioEntita.checked ? 'entita' : null);
      if (!scelto) {
        esito.textContent = 'Scegli se è un tipo o un’entità.';
        return;
      }
      submitJudgment({
        soggetto_genere: scelto, soggetto: subjectInput.value.trim(), campo: 'genere',
        valore: sel.value
      }, { button: scrivi, esito: esito, outerBody: outerBody });
    });
    wrap.appendChild(scrivi);
    wrap.appendChild(esito);
    return wrap;
  }

  /* «Le tue correzioni» (forma approvata, gerarchia): il modulo di aggiunta
     in testa, sempre visibile, poi le righe `proprietario` e `altro` --
     ovunque vivessero nel seme, qui vivono UNA volta sola.

     Torna il titolo (`<h3>`): fix round 1, MINOR 6 lo rende focalizzabile
     (`tabindex=-1`) e ci sposta il focus dopo un ricaricamento innescato da
     una scrittura -- senza, il bottone appena premuto sparisce col resto
     del corpo e il focus cade su `<body>`, e chi naviga da tastiera perde
     il posto. */
  function renderCorrections(body, giudizi, outerBody) {
    var heading = subheading(body, 'Le tue correzioni');
    heading.tabIndex = -1;
    body.appendChild(addJudgmentForm(outerBody));

    var corrette = sortJudgmentRows(giudizi.filter(function (g) {
      return g.da === 'proprietario' || g.da === 'altro';
    }));
    if (!corrette.length) {
      line(body, 'Nessuna correzione ancora: le righe che scrivi da qui vivono da sole.', TONE_CALM);
      return heading;
    }
    corrette.forEach(function (g) { body.appendChild(judgmentRow(g, outerBody, true)); });
    return heading;
  }

  /* «I giudizi del seme» (forma approvata, punto 2): sette gruppi chiusi, uno
     per campo, ordinati per soggetto dentro. Il conteggio si calcola dai
     dati -- mai scritto a mano -- e porta anche le correzioni tolte da qui
     («25 dal seme · 1 corretta da te»): la riga vive solo in «Le tue
     correzioni», ma il numero del gruppo racconta lo storico intero.

     **Fix round 1, MINOR 5**: il conteggio contava solo `da === 'proprietario'`
     -- una riga `altro` (modificata a mano, fuori da questa porta) spariva dal
     gruppo E dal conteggio, e il commento sopra («racconta lo storico intero»)
     era falso proprio per quel caso. Ora conta entrambe, separate: «N dal seme
     · M corretta/e da te · K modificata/e a mano» (una parte si omette se il
     suo numero è zero). */
  function renderSeedGroups(body, giudizi, outerBody) {
    subheading(body, 'I giudizi del seme');
    JUDGMENT_FIELD_GROUPS.forEach(function (gruppo) {
      var semeRighe = sortJudgmentRows(giudizi.filter(function (g) {
        return g.campo === gruppo.campo && g.da === 'seme';
      }));
      var correzioni = giudizi.filter(function (g) {
        return g.campo === gruppo.campo && g.da === 'proprietario';
      }).length;
      var modificheAMano = giudizi.filter(function (g) {
        return g.campo === gruppo.campo && g.da === 'altro';
      }).length;
      var parti = [];
      if (correzioni || modificheAMano) {
        parti.push(fmtCount(semeRighe.length) + ' dal seme');
        if (correzioni) parti.push(fmtCount(correzioni) + (correzioni === 1 ? ' corretta da te' : ' corrette da te'));
        if (modificheAMano) {
          parti.push(fmtCount(modificheAMano) + (modificheAMano === 1 ? ' modificata a mano' : ' modificate a mano'));
        }
      } else {
        parti.push(fmtCount(semeRighe.length));
      }
      var etichetta = gruppo.etichetta + ' · ' + parti.join(' · ');
      body.appendChild(createDisclosure(etichetta, etichetta, function (panel) {
        if (!semeRighe.length) {
          panel.appendChild(el('p', 'field-hint', 'Nessuna riga di questo campo.'));
          return;
        }
        semeRighe.forEach(function (g) { panel.appendChild(judgmentRow(g, outerBody)); });
      }, false));
    });
  }

  /* «Le domande aperte» (forma approvata): 4 delle 6 non si rispondono da
     questa porta (il contratto non porta un campo di destinazione) -- in v1
     si mostrano da leggere, chiuse, senza modulo di risposta. */
  function renderOpenQuestions(body, domande) {
    subheading(body, 'Le domande aperte');
    if (!domande.length) {
      line(body, 'Il censore non ha domande aperte in questo momento.', TONE_CALM);
      return;
    }
    domande.forEach(function (q) {
      var chiavi = q.chiavi || [];
      var chiuso = firstSentenceTruncated(q.domanda, 80) + ' (' + fmtCount(chiavi.length) +
        (chiavi.length === 1 ? ' chiave)' : ' chiavi)');
      body.appendChild(createDisclosure(chiuso, chiuso, function (panel) {
        var testo = el('p', 'sc-desc');
        appendMarkedText(testo, q.domanda);
        panel.appendChild(testo);
        if (chiavi.length) panel.appendChild(el('p', 'text-mono', chiavi.join(', ')));
      }, false));
    });
  }

  function renderKnowledge(body, sapere) {
    var nonCapito = (sapere && sapere.non_capito) || [];
    var giudizi = (sapere && sapere.giudizi) || [];
    var domande = (sapere && sapere.domande_aperte) || [];

    /* **Ciò che non ha capito viene PRIMA.** È l'unica parte su cui il
       proprietario può fare qualcosa -- «quello è il contatore dell'acqua» --
       e in fondo a un elenco di conteggi non salterebbe all'occhio. Stessa
       regola di «cosa non si sa» nel resoconto. */
    subheading(body, 'Cosa non ha capito');
    if (!nonCapito.length) {
      line(body, 'Non c’è niente che non abbia capito. Quando il modello non riesce ' +
        'a leggere un dispositivo lo scrive qui, e basta una parola tua per risolverlo.',
        TONE_CALM);
    } else {
      nonCapito.forEach(function (r) {
        var riga = el('div', 'sc-row');
        riga.appendChild(el('div', 'sc-row-title',
          describeWatchedSubject(r.soggetto || '', null).primary));
        riga.appendChild(el('div', 'sc-row-why', r.valore || ''));
        var coda = [];
        if (r.chi) coda.push('L’ha scritto ' + r.chi + '.');
        if (r.quando_ts) coda.push('Il ' + fmtWhenFull(r.quando_ts) + '.');
        if (coda.length) riga.appendChild(el('div', 'field-hint', coda.join(' ')));
        body.appendChild(riga);
      });
    }

    /* «Le tue correzioni» -> «I giudizi del seme» -> «Le domande aperte»
       (forma approvata, gerarchia). `outerBody` è la scheda intera: ogni
       scrittura la ricarica per intero (spec: la correzione vale subito).
       Il titolo di «Le tue correzioni» torna indietro (fix round 1, MINOR 6):
       `carica` lo usa per rimettere il focus dopo una scrittura. */
    var correctionsHeading = renderCorrections(body, giudizi, body);
    renderSeedGroups(body, giudizi, body);
    renderOpenQuestions(body, domande);

    subheading(body, 'Cosa ha capito');
    var righe = (sapere && sapere.conteggi && sapere.conteggi.righe) || [];
    if (!righe.length) {
      line(body, 'Il sapere è vuoto: nessuna riga, di nessuna specie.', TONE_UNKNOWN);
      return correctionsHeading;
    }
    /* **Per specie e provenienza, non un totale solo**: «177 significati
       importati da Home Assistant» e «tre ricette dedotte dal modello» sono
       due fatti diversi, e il secondo è quello che il modello ha aggiunto. */
    var grid = el('div', 'stat-grid');
    righe.forEach(function (r) {
      var tile = el('div', 'stat-tile');
      tile.appendChild(el('div', 'st-label',
        knowledgeFieldLabel(r.campo) + ' · ' + r.specie));
      tile.appendChild(el('div', 'st-value', fmtCount(r.quante)));
      tile.appendChild(el('div', 'st-delta', r.provenienza));
      grid.appendChild(tile);
    });
    body.appendChild(grid);
    return correctionsHeading;
  }

  function renderKnowledgeError(body, status, reload) {
    if (status === 503) {
      line(body, 'Il sapere non è collegato in questo momento. Non è vuoto — ' +
        'è che non si può leggere.', TONE_PROBLEM);
    } else {
      line(body, 'Non è stato possibile leggere il sapere. Riprova più tardi.', TONE_PROBLEM);
    }
    retryButton(body, reload);
  }

  /* `notice` (facoltativo): il messaggio del 409 («scritta ma non in
     vigore», `submitJudgment`) sopravvive al ricaricamento -- senza,
     ricaricare subito la scheda lo cancellerebbe prima che chi ha
     scritto la correzione faccia in tempo a leggerlo.

     `focusCorrections` (fix round 1, MINOR 6): dopo una scrittura riuscita
     (200) o non in vigore (409) il corpo si ricostruisce da zero -- il
     bottone appena premuto sparisce, e senza spostarlo esplicitamente il
     focus cade su `<body>`. Il bersaglio è il titolo di «Le tue
     correzioni» (`renderKnowledge` lo torna indietro), reso focalizzabile
     con `tabindex=-1` -- non un ricaricamento generico (prima apertura,
     «Riprova», «Aggiorna»), dove spostare il focus da solo sarebbe
     invadente. */
  function carica(corpo, notice, focusCorrections) {
    clearEl(corpo);
    line(corpo, 'Caricamento…', TONE_CALM);
    function reload() { return carica(corpo); }
    return read('api/mind/knowledge').then(function (occurrence) {
      clearEl(corpo);
      if (!occurrence.ok) { renderKnowledgeError(corpo, occurrence.status, reload); return; }
      if (notice) line(corpo, notice, TONE_PROBLEM);
      var heading = renderKnowledge(corpo, occurrence.corpo);
      if (focusCorrections && heading && typeof heading.focus === 'function') heading.focus();
    }, function () {
      clearEl(corpo);
      renderKnowledgeError(corpo, null, reload);
    });
  }

  return {
    carica: carica,
    /* Seam di test: la resa e' pura DOM + dati, va pinnata senza passare da fetch. */
    _rendiSapere: renderKnowledge
  };
})();
