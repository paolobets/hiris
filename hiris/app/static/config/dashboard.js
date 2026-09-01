/* HIRIS · Configurazione · «Cosa HIRIS sa» (route #/, la home)

   HIRIS 2.0 e' la conoscenza della casa piu' una chat per interrogarla -- e,
   dalla fetta «comandare», per comandarla. Questa pagina e' la faccia della
   sola CONOSCENZA: mostra cio' che HIRIS ha letto della casa e cio' che
   dichiara di ignorare. L'azione non ha (ancora) una faccia qui: passa dalla
   chat e si racconta li'.

   Due sole fetch, su rotte vive e in sola lettura:
     - GET /api/home-space   -> l'anagrafe ricostruita, il comportamento, le plance;
     - GET /api/briefing -> il testo ESATTO che il modello ha davanti in chat
                          (la stessa composizione, non un secondo conto:
                          `handlers_casa.compose_briefing()` e' condivisa con
                          `handlers_chat.compose_chat_context`).

   La regola che governa ogni riga qui sotto: i campi di /api/home-space hanno TRE
   stati, non due. `null` = «non ho potuto controllare», `[]`/`{}`/`0` = «ho
   controllato, non c'e' niente». Renderli allo stesso modo -- un `null`
   mostrato come «0» o come «tutto a posto» -- rimetterebbe dentro dalla porta
   di servizio esattamente il difetto che tutto il backend dell'anagrafe e'
   stato scritto per evitare. Nessun conteggio inventato: se un numero non
   arriva dal backend, la pagina dice che non lo sa invece di stampare zero.

   Sicurezza: testi via textContent / nodi DOM, mai innerHTML su dati server
   (stessa disciplina di memoria-route.js e models-route.js). */
window.HirisDashboard = (function () {
  'use strict';

  /* Toni: il colore non e' decorazione, distingue i tre stati. Sono i token
     *-ink, non `--warn`/`--err`: quelli nascono per pallini e riempimenti e sul
     tema chiaro -- che e' il predefinito -- stanno a 2.04:1 e 4.05:1. Qui
     colorano il TESTO con cui HIRIS dice «questo non l'ho letto», cioe' la
     frase per cui questa pagina esiste: era servita dal colore meno leggibile
     dell'intera tavolozza. */
  var TONO_IGNOTO = 'color:var(--warn-ink)';
  var TONO_PROBLEMA = 'color:var(--err-ink)';
  var TONO_QUIETO = 'color:var(--text-3)';

  var NOMI_REGISTRI = {
    piani: 'Piani',
    aree: 'Aree',
    dispositivi: 'Dispositivi',
    entita: 'Entità',
    etichette: 'Etichette',
    categorie: 'Categorie',
    integrazioni: 'Integrazioni'
  };

  var NOMI_COMPORTAMENTO = {
    automazione: 'Automazioni',
    script: 'Script'
  };

  function el(tag, cls, testo) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (testo != null) e.textContent = testo;
    return e;
  }

  function riga(padre, testo, stile) {
    var p = el('p', 'sc-desc', testo);
    if (stile) p.style.cssText = stile;
    padre.appendChild(p);
    return p;
  }

  function elenco(padre, voci) {
    var ul = el('ul');
    ul.style.cssText = 'margin:4px 0 0;padding-left:20px;color:var(--text-2);font-size:var(--fs-13)';
    voci.forEach(function (v) { ul.appendChild(el('li', null, v)); });
    padre.appendChild(ul);
    return ul;
  }

  function sezione(outlet, titolo, sottotitolo) {
    var card = el('section', 'section-card');
    var testa = el('div', 'sc-header');
    testa.appendChild(el('div', 'sc-title', titolo));
    if (sottotitolo) testa.appendChild(el('div', 'sc-desc', sottotitolo));
    card.appendChild(testa);
    var corpo = el('div', 'sc-body');
    card.appendChild(corpo);
    outlet.appendChild(card);
    return corpo;
  }

  /* I registri caduti, per NOME: `non_disponibili` porta voci come "piani" o
     "categorie:script" (il perche' dopo i due punti, vedi
     `ha_client.read_registries`). Qui serve solo il nome del registro. */
  function registriCaduti(nonDisponibili) {
    if (!nonDisponibili) return null;   // null = non si sa, diverso da nessuno
    return nonDisponibili.map(function (v) { return String(v).split(':')[0]; });
  }

  /* Il comportamento ha DUE tipi fissi, e nessuno dei due puo' sparire.
     `conteggi` (handlers_casa.py) si costruisce contando le voci lette: una
     casa con dodici automazioni e zero script produce `{automazione: 12}` e
     la tessera «Script» non veniva disegnata affatto -- ne' «0» ne' «non
     letto», proprio niente. Qui i due tipi ci sono sempre.

     Il terzo stato lo porta `file_non_letti`, che pero' mappa il NOME DEL
     FILE ("automations.yaml") alla ragione, non il tipo di voce
     ("automazione"): senza questa traduzione il quarto argomento di
     `tessere()` non veniva passato affatto, ed era il Minor e7.

     Attenzione a cosa significa davvero un file non letto: le voci arrivano
     dai file E dallo stato di Home Assistant (`casa/comportamento.rileggi`),
     quindi con `automations.yaml` assente HIRIS puo' comunque conoscere per
     NOME dodici automazioni prese dallo stato -- e `senza_corpo` dice gia'
     di quante non conosce il corpo. Marcare quella tessera «non letto»
     nasconderebbe dodici voci vere. Un tipo si dichiara non letto solo
     quando il suo file non si e' letto E il conto e' a zero: e' l'unico caso
     in cui «non c'e' niente» e «non ho guardato» sono indistinguibili. */
  var FILE_PER_TIPO = { automazione: 'automations.yaml', script: 'scripts.yaml' };

  function conteggiComportamento(conteggi) {
    var letti = conteggi || {};
    var esito = {};
    Object.keys(FILE_PER_TIPO).forEach(function (tipo) {
      esito[tipo] = letti[tipo] != null ? letti[tipo] : 0;
    });
    /* Un tipo nuovo del backend deve comparire, non sparire: stessa regola
       delle chiavi sconosciute al dizionario dei nomi, un livello piu' su. */
    Object.keys(letti).forEach(function (tipo) {
      if (esito[tipo] == null) esito[tipo] = letti[tipo];
    });
    return esito;
  }

  function comportamentoCaduto(fileNonLetti, conteggi) {
    if (!fileNonLetti) return null;   // null = non si sa, diverso da nessuno
    var letti = conteggi || {};
    return Object.keys(FILE_PER_TIPO).filter(function (tipo) {
      return Object.prototype.hasOwnProperty.call(fileNonLetti, FILE_PER_TIPO[tipo])
          && !letti[tipo];
    });
  }

  /* Un conteggio per chiave, in tessere. Chiamata SOLO quando la lettura
     corrispondente e' avvenuta: una griglia di zeri su una lettura mai fatta
     racconterebbe una casa vuota al posto di una casa non letta.

     `caduti` chiude lo stesso buco un livello piu' in basso: `conteggi` non
     ha tre stati -- e' `{chiave: len(elenco)}` sull'archivio, quindi un
     registro che NON ha risposto ci arriva come `0`, indistinguibile da un
     registro letto e vuoto. Il terzo stato ce l'ha `non_disponibili`, che
     nomina il registro: dove i due si incontrano, vince il non-letto e il
     numero non si stampa affatto. */
  function tessere(corpo, conteggi, nomi, caduti, motivoCaduto) {
    var chiavi = Object.keys(conteggi || {});
    /* Una chiave caduta puo' NON essere in `conteggi` affatto: `conteggi` e'
       un conto di cio' che si e' letto, quindi cio' che non si e' letto non
       ci compare. Senza questa riga la tessera SPARIVA invece di dire «non
       letto» -- su una pagina il cui unico scopo e' distinguere «non lo so»
       da «non c'e'», una tessera che sparisce e' il difetto-firma del
       prodotto. */
    (caduti || []).forEach(function (chiave) {
      if (chiavi.indexOf(chiave) === -1) chiavi.push(chiave);
    });
    if (!chiavi.length) {
      riga(corpo, 'La lettura non ha prodotto nessuna voce.', TONO_QUIETO);
      return;
    }
    chiavi.sort();
    var griglia = el('div', 'stat-grid');
    chiavi.forEach(function (chiave) {
      var tessera = el('div', 'stat-tile');
      /* Chiave sconosciuta al dizionario: si mostra grezza, non si nasconde.
         Una voce nuova del backend deve comparire storpiata, non sparire. */
      tessera.appendChild(el('div', 'st-label', nomi[chiave] || chiave));
      if (caduti && caduti.indexOf(chiave) !== -1) {
        var valore = el('div', 'st-value', 'non letto');
        valore.style.cssText = 'font-size:var(--fs-15);font-weight:500;letter-spacing:normal;' + TONO_IGNOTO;
        tessera.appendChild(valore);
        tessera.appendChild(el('div', 'st-delta', motivoCaduto || 'il registro non ha risposto'));
      } else {
        tessera.appendChild(el('div', 'st-value', String(conteggi[chiave])));
      }
      griglia.appendChild(tessera);
    });
    corpo.appendChild(griglia);
  }

  /* Il cuore della pagina: un campo a tre stati reso in tre modi diversi.
     `valore` null -> non si sa; vuoto -> si sa che non c'e' niente; pieno ->
     si nomina cio' che c'e'. */
  function treStati(corpo, valore, frasi, formatta) {
    if (valore == null) {
      riga(corpo, frasi.ignoto, TONO_IGNOTO);
      return;
    }
    var voci = formatta ? formatta(valore) : valore;
    if (!voci.length) {
      riga(corpo, frasi.vuoto, TONO_QUIETO);
      return;
    }
    riga(corpo, frasi.pieno, TONO_PROBLEMA);
    elenco(corpo, voci);
  }

  function dizionarioAVoci(oggetto) {
    return Object.keys(oggetto).sort().map(function (k) {
      return k + ' — ' + oggetto[k];
    });
  }

  /* Il fatto «questa sezione è stata letta» non sta nel campo: sta nella sua
     DATA. I getter dell'archivio NON distinguono i due casi -- su un archivio
     esistente ma mai riempito (nessuna riga in `meta`) `non_disponibili()`
     torna `[]` (archivio.py:173-183), `problemi_comportamento()` `[]`
     (:256-268), `file_non_letti()` `{}` (:270-281),
     `non_disponibili_plance()` `[]` (:332-344), e `senza_corpo` è un `sum()`
     su zero voci, cioè `0` (handlers_casa.py:75). Solo le tre date tornano
     `None`.

     Quindi un elenco vuoto è prova di «controllato, niente da segnalare»
     SOLO se la lettura corrispondente è avvenuta. Senza questa riga la
     pagina, su una casa mai letta, affermava quattro volte «tutto a posto»
     accanto a «non ho ancora guardato» -- ed è lo stato che `server.py:723-733`
     dichiara per iscritto come ATTESO (un Home Assistant non ancora pronto
     all'avvio), non un ramo di difesa.

     È la stessa regola già applicata alle tessere dei conteggi, fatta scendere
     un livello più su: dove il dato non ha tre stati, il terzo stato lo porta
     la data. */
  function soloSeLetta(letta, valore) {
    return letta == null ? null : valore;
  }

  /* I registri caduti, in italiano. `non_disponibili` porta il nome grezzo
     della tabella e, per le categorie, l'ambito che ha fallito
     (`categorie:script` -- vedi `ha_client.read_registries`): l'ambito NON si
     butta, è il dettaglio che dice quale delle quattro chiamate è caduta. */
  function nomiRegistriInItaliano(voci) {
    return voci.map(function (voce) {
      var pezzi = String(voce).split(':');
      var nome = NOMI_REGISTRI[pezzi[0]] || pezzi[0];
      var ambito = pezzi.slice(1).join(':');
      return ambito ? nome + ' (ambito «' + ambito + '»)' : nome;
    });
  }

  /* ---------------------------------------------------------------- casa */

  function rendiCasa(outlet, casa) {
    var corpo = sezione(outlet, 'L’anagrafe della casa',
      'Piani, aree, dispositivi ed entità come HIRIS li ha ricostruiti dai registri di Home Assistant.');

    if (casa.anagrafe_letta_il == null) {
      riga(corpo, 'L’anagrafe non è ancora stata letta: qui non c’è una casa vuota, c’è una casa che HIRIS non ha ancora guardato.', TONO_IGNOTO);
    } else {
      riga(corpo, 'Letta il ' + casa.anagrafe_letta_il + '.', TONO_QUIETO);
      tessere(corpo, casa.conteggi, NOMI_REGISTRI, registriCaduti(casa.non_disponibili));
    }

    treStati(corpo, soloSeLetta(casa.anagrafe_letta_il, casa.non_disponibili), {
      ignoto: 'Non si sa quali registri abbiano risposto: HIRIS non ha potuto controllarlo.',
      vuoto: 'Tutti i registri hanno risposto.',
      pieno: 'Registri che non hanno risposto all’ultima lettura:'
    }, nomiRegistriInItaliano);

    /* Comportamento */
    var comp = casa.comportamento || {};
    var corpoComp = sezione(outlet, 'Ciò che la casa sa fare da sola',
      'Automazioni e script: quanti ne conosce, e di quanti conosce solo il nome.');

    if (comp.letto_il == null) {
      riga(corpoComp, 'Il comportamento non è ancora stato letto.', TONO_IGNOTO);
    } else {
      riga(corpoComp, 'Letto il ' + comp.letto_il + '.', TONO_QUIETO);
      tessere(corpoComp, conteggiComportamento(comp.conteggi), NOMI_COMPORTAMENTO,
              comportamentoCaduto(comp.file_non_letti, comp.conteggi),
              'il file non è stato letto');
    }

    /* `senza_corpo` e' il numero che dice quanto HIRIS sa DAVVERO: le voci di
       cui conosce il nome e non il corpo. A null non diventa «0»: sarebbe
       l'affermazione «conosco tutto» su una lettura mai avvenuta -- e senza
       lettura il backend manda proprio `0`, non `null`. */
    var senzaCorpo = soloSeLetta(comp.letto_il, comp.senza_corpo);
    if (senzaCorpo == null) {
      riga(corpoComp, 'Non si sa di quante voci HIRIS conosca solo il nome: la lettura non è avvenuta.', TONO_IGNOTO);
    } else if (senzaCorpo === 0) {
      riga(corpoComp, 'Di ogni voce HIRIS conosce anche il corpo, non solo il nome.', TONO_QUIETO);
    } else {
      riga(corpoComp, 'Di ' + senzaCorpo + ' voci HIRIS conosce solo il nome, non il corpo.', TONO_PROBLEMA);
    }

    /* «L'ultima lettura non ha lasciato niente in sospeso» compariva una riga
       SOPRA l'elenco dei file non letti (il `treStati` subito qui sotto): due
       frasi adiacenti che si smentivano. Questo blocco parla soltanto delle
       voci che sono state lette -- id duplicati, script vuoti, voci
       malformate -- e ora lo dice invece di promettere che non c'e' rimasto
       niente in sospeso in tutta la lettura. */
    treStati(corpoComp, soloSeLetta(comp.letto_il, comp.problemi), {
      ignoto: 'Non si sa se nelle voci lette ci siano incongruenze: la lettura non è avvenuta.',
      vuoto: 'Nelle voci lette non c’è nessuna incongruenza.',
      pieno: 'Incongruenze nelle voci lette, che HIRIS non ha potuto sciogliere con certezza:'
    });

    treStati(corpoComp, soloSeLetta(comp.letto_il, comp.file_non_letti), {
      ignoto: 'Non si sa quali file di automazioni e script siano stati letti.',
      vuoto: 'Tutti i file di automazioni e script sono stati letti.',
      pieno: 'File non letti, con la ragione:'
    }, dizionarioAVoci);

    /* Plance */
    var plance = casa.plance || {};
    var corpoPlance = sezione(outlet, 'Le plance di Home Assistant',
      'Le dashboard Lovelace che HIRIS ha potuto leggere.');

    if (plance.lette_il == null) {
      riga(corpoPlance, 'Le plance non sono ancora state lette.', TONO_IGNOTO);
    } else {
      riga(corpoPlance, 'Lette il ' + plance.lette_il + '.', TONO_QUIETO);
      var voci = plance.voci || [];
      riga(corpoPlance, voci.length === 1 ? '1 plancia letta.' : voci.length + ' plance lette.', TONO_QUIETO);
      if (voci.length) {
        elenco(corpoPlance, voci.map(function (p) {
          return (p.titolo || p.percorso || 'plancia predefinita');
        }));
      }
    }

    treStati(corpoPlance, soloSeLetta(plance.lette_il, plance.non_disponibili), {
      ignoto: 'Non si sa quali plance abbiano risposto: HIRIS non ha potuto controllarlo.',
      vuoto: 'Tutte le plance hanno risposto.',
      pieno: 'Plance che l’ultima lettura non è riuscita a risolvere:'
    });
  }

  /* -------------------------------------------------------------- nucleo */

  function rendiNucleo(outlet, nucleo) {
    var riepilogo = nucleo.riepilogo || {};
    var corpo = sezione(outlet, 'Il nucleo, come lo vede il modello',
      'Il testo esatto che HIRIS ha davanti a ogni turno di chat — non una sua descrizione, né un secondo conto.');

    var avvisi = riepilogo.avvisi || [];
    var titoloLacune = el('div', null, 'Ciò che HIRIS ignora');
    titoloLacune.style.cssText = 'font-weight:500;margin-bottom:4px';
    corpo.appendChild(titoloLacune);
    if (!avvisi.length) {
      riga(corpo, 'Il nucleo non dichiara nessuna lacuna.', TONO_QUIETO);
    } else {
      elenco(corpo, avvisi);
    }

    var misure = el('div', 'stat-grid');
    misure.style.cssText = 'margin-top:12px';
    function misura(etichetta, valore, sotto) {
      var t = el('div', 'stat-tile');
      t.appendChild(el('div', 'st-label', etichetta));
      t.appendChild(el('div', 'st-value', valore));
      if (sotto) t.appendChild(el('div', 'st-delta', sotto));
      misure.appendChild(t);
    }
    misura('Caratteri', String(riepilogo.caratteri != null ? riepilogo.caratteri : '—'), 'del nucleo');
    misura('Troncato', riepilogo.troncato ? 'Sì' : 'No', 'per il tetto di lunghezza');
    misura('Ricordi esclusi', String(riepilogo.ricordi_esclusi != null ? riepilogo.ricordi_esclusi : '—'), 'fuori dal nucleo');
    corpo.appendChild(misure);

    var pre = el('pre', null, nucleo.testo || '');
    pre.style.cssText = 'margin-top:12px;max-height:420px;overflow:auto;white-space:pre-wrap;' +
      'font-family:var(--font-mono,monospace);font-size:12px;line-height:1.5;' +
      'background:var(--bg-2,var(--hover));padding:12px;border-radius:8px';
    corpo.appendChild(pre);
  }

  /* --------------------------------------------------------------- mount */

  /* Un errore di rete NON degrada in una pagina vuota: la sezione dice che
     non ha potuto leggere, e la console porta il dettaglio tecnico. Una
     pagina che tace su una fetch caduta e' indistinguibile da una casa
     senza niente dentro -- il difetto ricorrente n.1 di questo prodotto. */
  function rendiErrore(outlet, titolo, testo, err) {
    console.error('[cosa-hiris-sa] ' + titolo, err);
    var corpo = sezione(outlet, titolo, null);
    riga(corpo, testo, TONO_PROBLEMA);
  }

  function leggi(percorso) {
    return fetch(percorso).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function mount() {
    var outlet = document.getElementById('route-outlet');
    if (!outlet) return;
    outlet.innerHTML = '';

    var testa = el('div');
    testa.style.cssText = 'display:flex;justify-content:space-between;align-items:baseline;gap:16px;flex-wrap:wrap';
    var intro = el('div');
    intro.appendChild(el('div', 'page-title', 'Cosa HIRIS sa'));
    intro.appendChild(el('p', 'page-subtitle',
      'La conoscenza della tua casa che HIRIS ha davanti quando gli parli: ciò che ha letto, e ciò che dichiara di ignorare.'));
    testa.appendChild(intro);
    var vaiAllaChat = el('a', 'btn', 'Vai alla chat');
    vaiAllaChat.href = './';
    testa.appendChild(vaiAllaChat);
    outlet.appendChild(testa);

    var caricamento = el('p', 'page-subtitle', 'Caricamento…');
    outlet.appendChild(caricamento);

    return Promise.all([
      leggi('api/home-space').then(function (casa) {
        return function () { rendiCasa(outlet, casa); };
      }, function (err) {
        return function () {
          rendiErrore(outlet, 'L’anagrafe della casa',
            'Non è stato possibile leggere ciò che HIRIS sa della casa. Questo non significa che la casa sia vuota: la richiesta non è andata a buon fine.', err);
        };
      }),
      leggi('api/briefing').then(function (nucleo) {
        return function () { rendiNucleo(outlet, nucleo); };
      }, function (err) {
        return function () {
          rendiErrore(outlet, 'Il nucleo, come lo vede il modello',
            'Non è stato possibile leggere il nucleo. Questo non significa che il nucleo sia vuoto: la richiesta non è andata a buon fine.', err);
        };
      })
    ]).then(function (rendite) {
      /* Le due fetch partono insieme ma si rendono nell'ordine dichiarato:
         casa prima, nucleo dopo, sempre -- cosi' la pagina non cambia
         disposizione a seconda di quale risposta arriva per prima. */
      if (caricamento.parentNode) caricamento.parentNode.removeChild(caricamento);
      rendite.forEach(function (rendi) { rendi(); });
    });
  }

  return {
    mount: mount,
    /* Seam di test: le due funzioni di resa sono pure DOM + dati, e i tre
       stati vanno pinnati senza passare da fetch. */
    _rendi: { casa: rendiCasa, nucleo: rendiNucleo }
  };
})();
