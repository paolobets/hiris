"""Le due domande: cercare per nome, guardare il dettaglio.

Il nucleo (nucleo.py) dice DOVE sono le cose -- conta, non elenca. Le due
funzioni qui sotto danno il DETTAGLIO, quando il modello (o l'utente dalla
pagina) lo chiede esplicitamente:

- `cerca(indice, testo)` -- trovare qualcosa per nome o alias. E' un guscio
  sottile attorno a `Indice.trova()` (memoria/riconoscitore.py): il
  contratto -- `candidati` sempre una lista, `ambiguo` dichiarato -- e' gia'
  li', e riscriverlo qui vorrebbe dire poterlo rompere in due punti invece
  che in uno. Due voci che si normalizzano uguali (due «Bagno» su piani
  diversi, un alias che collide col nome vero di un'altra area) restano
  AMBIGUE: scegliere spetta al modello, che ha la casa in contesto, o
  all'utente, che corregge dalla pagina -- non a questo modulo.
- `guarda(casa, comportamento, ricordi, stato, tipo, riferimento)` -- il
  dettaglio di UNA cosa sola: un'area con le sue entita' e i loro stati,
  un'entita' col suo stato e la sua classe, un'automazione o uno script col
  loro corpo, un dispositivo con le sue entita', un ricordo con la sua
  interpretazione.

Due, non trentaquattro: la mappa del prodotto ha condannato un catalogo di
trentaquattro strumenti con tre copie divergenti (vedi
docs/design/2026-08-05-la-conoscenza-di-hiris.md). Un tipo nuovo di "cosa"
si aggiunge come un altro `if` dentro `guarda`, non come un tool in piu'.

Entrambe sono PURE: prendono dati gia' letti dal chiamante (l'indice, la
casa, il comportamento, i ricordi, lo stato vivo) e non aprono archivi ne'
chiamano la rete -- la stessa scelta che rende `componi()` del nucleo
verificabile senza finti elaborati (nucleo.py).

**Un silenzio non dichiarato e' indistinguibile da un'assenza di
problemi** (pagato sedici volte su questo ramo, sempre trovato da una
review, mai dalla suite). Per questo `guarda` restituisce SEMPRE la chiave
`esiste`, e quando e' `False` non inventa il resto: nessun `entita: []`,
nessun `corpo: None` che si potrebbe scambiare per un fatto sulla casa
invece che per "non trovato". E «non ho il corpo» (un limite di HIRIS --
`corpo: None` con un `origine` che lo dichiara) resta distinto da «il
corpo e' vuoto» (un fatto sulla casa: `corpo: {}` o simile).
"""
from __future__ import annotations

from .anagrafe import (classe_effettiva, dominio_di, etichette_con_nome,
                       gerarchia, nomi_delle_etichette, traduci_stato,
                       unita_effettiva)

# I tipi di comportamento che `guarda` sa mostrare col loro corpo. Un
# "automazione" e uno "script" sono voci dello stesso elenco
# (comportamento.py), non due archivi diversi: la distinzione e' nel campo
# `tipo` della voce, non nella provenienza.
_TIPI_COMPORTAMENTO = {"automazione", "script"}


def cerca(indice, testo: str) -> list[dict]:
    """Trova `testo` per nome o alias, con l'ambiguita' dichiarata.

    E' `Indice.trova()` PIU' cio' che serve a non sbagliare cosa si e'
    trovato. Scegliere UN candidato qui -- il primo, il piu' probabile --
    rifarebbe il difetto che e' gia' costato un fix: due «Bagno» su piani
    diversi vincevano in silenzio in base all'ordine di raccolta. Questa
    funzione non sceglie: **rende scegliere possibile**.

    Ogni candidato porta:

    - `nome`, con cui la casa lo conosce. Senza, il modello ha una lista di
      identificatori e nessun modo di riconoscerli;
    - `dominio` (solo per le entita'): `sensor`, `light`, ... E' il rimedio
      alla cecita' al dominio -- `cerca("luci")` restituisce `sensor.lights`,
      un CONTATORE di luci, e nel risultato non c'era niente che lo dicesse.
      Non si filtra (il modello e' quello che sa se un contatore gli serve),
      si dichiara;
    - `nome_dedotto`, presente (col nome dedotto, come STRINGA -- mai un
      booleano: I2, review finale) quando il nome non e' dichiarato nel
      registro ma ricavato dal `friendly_name` dello specchio dello stato
      (vedi `memoria/riconoscitore.costruisci_indice`). Un nome dedotto e'
      un fatto diverso da un nome scelto dall'utente e non va spacciato per
      tale -- stessa forma di `nome_dedotto` in `guarda()`/`_guarda_entita`.

    `verifica()` e' un accesso a dizionario, non una ricerca: farlo per
    candidato costa quanto leggere la lista."""
    risultati = indice.trova(testo)
    for voce in risultati:
        for candidato in voce["candidati"]:
            oggetto = indice.verifica(candidato["tipo"], candidato["riferimento"]) or {}
            dedotto = (oggetto.get("nome_dedotto") or "").strip()
            candidato["nome"] = (oggetto.get("nome") or "").strip() or dedotto
            if dedotto:
                # I2 (review finale): `nome_dedotto` e' UNA forma sola in
                # tutto il modulo -- la stringa col nome dedotto, la stessa
                # che porta `guarda()`/`_guarda_entita`. Prima di questo fix
                # qui usciva un booleano (`True`) mentre `guarda()` usciva la
                # stringa: due tipi diversi per lo stesso fatto, con un
                # modello che poteva imparare la forma sbagliata dall'uno e
                # leggere male l'altro.
                candidato["nome_dedotto"] = dedotto
            if candidato["tipo"] == "entita":
                candidato["dominio"] = dominio_di(candidato["riferimento"])
    return risultati


def _ricordi_ancorati(ricordi: list[dict], tipo: str, riferimento) -> list[dict]:
    """I ricordi di `ricordi` che portano un'ancora (tipo, riferimento)
    uguale a quella cercata -- stessa chiave di `ArchivioMemoria.per_ancora`
    (memoria/archivio.py), ma su una lista gia' in memoria: `guarda` e'
    pura, non interroga l'archivio da sola.

    E' il senso delle ancore: «quali preferenze riguardano questa stanza».
    Un tipo come "automazione", "script" o "ricordo" -- fuori dal
    vocabolario delle ancore (memoria/interpretazione.py: area, entita,
    dispositivo) -- semplicemente non trova mai nulla qui: non e' un
    errore, e' un tipo di "cosa" per cui nessun ricordo si ancora.
    """
    trovati = []
    for r in ricordi:
        for ancora in r.get("ancore") or []:
            if ancora.get("tipo") == tipo and ancora.get("riferimento") == riferimento:
                trovati.append(r)
                break
    return trovati


def _trova_area(piani: list[dict], riferimento) -> dict | None:
    """L'area `riferimento` nell'albero gia' costruito da `gerarchia()`,
    con le entita' che le spettano (ereditarieta' dal dispositivo, esclusi
    i disabilitati) gia' risolte.

    Riusa l'albero invece di rifiltrare `casa["entita"]` a mano: una
    piccola reimplementazione delle stesse regole e' gia' costata un
    Critical al Task 1 -- qui non si ripete.
    """
    for piano in piani:
        for area in piano["aree"]:
            if area["id"] == riferimento:
                return area
    return None


def _arricchisci_entita(dettaglio_entita: dict, voce: dict,
                        nomi_di_ripiego: dict[str, str] | None,
                        unita_vive: dict[str, str] | None = None,
                        nomi_etichette: dict[str, str] | None = None,
                        classi_vive: dict[str, str] | None = None) -> dict:
    """LA PORTA UNICA per tutto cio' che si aggiunge a un'entita'.

    Arricchisce `dettaglio_entita` con cio' che lo SPECCHIO VIVO sa e il
    registro no (il nome dedotto e l'unita' di misura) e con cio' che il
    registro sa e la proiezione lascerebbe indietro (la piattaforma e le
    etichette).

    Prende la VOCE del registro, non il solo `entita_id`: e' il cambiamento
    che rende questa porta capace di portare anche i campi dichiarati. Con il
    solo id, chi aggiungeva un campo nuovo era costretto a scriverlo nel
    proprio ramo -- ed e' esattamente quello che era appena successo con
    `piattaforma` ed `etichette`, uscite da una porta su tre: lo stesso
    difetto (I1) per cui questa funzione era nata.

    `nome_dedotto` con la disciplina di B5: solo quando `nome` e' vuoto nel
    registro, e mai scritto sopra `nome` -- dichiarato e dedotto restano due
    fatti diversi.

    `unita` con la stessa disciplina, e per la stessa ragione: `_to_minimal`
    la conserva (`proxy/entity_cache.py`) e nessuno la rileggeva, cosi' il
    modello riceveva `72` senza sapere se fossero gradi Celsius o Fahrenheit.
    L'unita' VIVA vince su quella del registro: Home Assistant converte le
    unita' **solo alla prima aggiunta del sensore**, quindi il registro puo'
    portare quella vecchia mentre lo specchio porta quella che HA sta usando
    adesso. La chiave compare solo quando c'e' un'unita': una lampada non ne
    ha, e `unita: null` su ogni luce sarebbe rumore in ogni risposta.

    Condivisa fra i TRE rami di `guarda` che elencano entita' (I1, review
    finale): prima di quel fix solo `_guarda_entita` applicava il nome dedotto,
    e le altre due porte mostravano `nome: null` secco. L'unita' entra dalla
    stessa porta unica, per non ripetere quella storia."""
    entita_id = voce.get("id")
    if not (dettaglio_entita.get("nome") or "").strip():
        dedotto = ((nomi_di_ripiego or {}).get(entita_id) or "").strip()
        if dedotto:
            dettaglio_entita["nome_dedotto"] = dedotto
    unita = unita_effettiva(voce.get("unita"), (unita_vive or {}).get(entita_id))
    if unita:
        dettaglio_entita["unita"] = unita
    # La CLASSE: dallo specchio vivo, perche' il registro delle entita' non la
    # manda affatto (`anagrafe.classe_effettiva`). Prima questa riga usciva
    # `null` su ogni entita' della casa, e con lei taceva tutto il vocabolario
    # dei significati.
    classe = classe_effettiva(voce.get("classe"), (classi_vive or {}).get(entita_id))
    if classe:
        dettaglio_entita["classe"] = classe
    # Lo stato IN PAROLE, accanto al valore grezzo -- mai al posto suo:
    # `stato` e' il fatto, `stato_leggibile` e' l'interpretazione, e non si
    # sovrascrivono (stessa disciplina di `nome`/`nome_dedotto`).
    #
    # Senza, `guarda` rispondeva `on` e basta: un allagamento aveva la forma di
    # una lampadina accesa. Il digesto lo traduceva gia', ma `guarda` e' la
    # porta che il modello usa quando la domanda e' PRECISA, o quando il
    # digesto ha tagliato, o quando l'entita' e' `config`/`diagnostic` e nel
    # digesto non entra affatto. La tabella e' la stessa
    # (`anagrafe._SIGNIFICATO_CLASSE`): due tabelle sarebbero due significati.
    valore = dettaglio_entita.get("stato")
    if valore is not None:
        dettaglio_entita["stato_leggibile"] = traduci_stato(
            valore, dettaglio_entita.get("classe"))
    # L'integrazione che la fornisce (hue, zwave_js, template): dice perche'
    # una cosa non risponde e cosa le si puo' chiedere.
    piattaforma = (voce.get("piattaforma") or "").strip()
    if piattaforma:
        dettaglio_entita["piattaforma"] = piattaforma
    return _con_etichette(dettaglio_entita, voce, nomi_etichette or {})


def _con_etichette(dettaglio: dict, voce: dict, nomi_etichette: dict[str, str]) -> dict:
    """Le etichette che l'utente ha scritto a mano in Home Assistant.

    Sono il significato piu' DICHIARATO che esista in quella casa -- «inverno»,
    «da controllare», «piano di sotto» -- e HIRIS le leggeva, le salvava, le
    metteva perfino nell'albero di `gerarchia()`, senza farle uscire da nessuna
    porta. Un'etichetta che non porta a niente costringe l'utente a ripetere a
    parole cio' che aveva gia' dichiarato una volta.

    Escono col NOME, non col `label_id`: l'unione la fa
    `anagrafe.nomi_delle_etichette`, la stessa che usa l'indice di `cerca`.

    Compare solo quando ce n'e' almeno una: `etichette: []` su ogni cosa
    sarebbe rumore in ogni risposta e -- peggio -- indistinguibile da un
    registro delle etichette caduto. Stessa disciplina di `unita`.
    """
    etichette = etichette_con_nome(voce, nomi_etichette)
    if etichette:
        dettaglio["etichette"] = etichette
    return dettaglio


def _guarda_area(casa: dict, ricordi: list[dict], stato: dict, riferimento,
                 non_disponibili: tuple[str, ...] = (),
                 nomi_di_ripiego: dict[str, str] | None = None,
                 unita_vive: dict[str, str] | None = None,
                 classi_vive: dict[str, str] | None = None) -> dict:
    # `non_disponibili` va PROPAGATO, non solo ricevuto: senza, `gerarchia()`
    # crede che sia andato tutto bene e un'entita' che eredita l'area dal
    # proprio dispositivo -- col registro dispositivi caduto -- finisce in
    # "Senza area" invece che in "Dispositivi non letti". Risultato: una
    # cucina con cinque luci ne mostra quattro, con `esiste: True` e nessun
    # avviso: la stessa forma di una cucina davvero piu' piccola.
    piani = gerarchia(casa, tuple(non_disponibili))
    nomi_etichette = nomi_delle_etichette(casa)
    area = _trova_area(piani, riferimento)
    if area is None:
        dettaglio = {"esiste": False, "tipo": "area", "riferimento": riferimento}
        # CRITICAL ③: se il registro delle aree non ha risposto, "non
        # trovata" non e' lo stesso di "non esiste" -- potrebbe stare
        # proprio nella parte che non si e' letta. Senza dichiararlo, il
        # modello legge "quest'area non esiste nella tua casa", un'
        # affermazione che nessuno ha il diritto di fare.
        if "aree" in non_disponibili:
            dettaglio["non_disponibile"] = True
        return dettaglio
    entita = [
        _arricchisci_entita(
            {"id": e["id"], "nome": e.get("nome"), "classe": e.get("classe"),
             "stato": stato.get(e["id"]), "disabilitata": False},
            e, nomi_di_ripiego, unita_vive, nomi_etichette, classi_vive)
        for e in area["entita"]
    ] + [
        # Marcate, non nascoste (MINOR): una vista di DETTAGLIO deve poter
        # dire "questa luce c'e' ma e' disabilitata" -- `_guarda_dispositivo`
        # e `_guarda_entita` lo fanno gia', `_guarda_area` no. `gerarchia()`
        # le tiene apposta fuori dai conteggi ma raggiungibili qui (vedi
        # anagrafe.py).
        _arricchisci_entita(
            {"id": e["id"], "nome": e.get("nome"), "classe": e.get("classe"),
             "stato": stato.get(e["id"]), "disabilitata": True},
            e, nomi_di_ripiego, unita_vive, nomi_etichette, classi_vive)
        for e in area.get("entita_disabilitate", [])
    ]
    # L'elenco puo' essere incompleto senza che si veda: si dichiara.
    incompleto = sorted(set(non_disponibili) & {"aree", "dispositivi", "entita"})
    dettaglio = {
        "esiste": True, "tipo": "area", "id": area["id"], "nome": area["nome"],
        "entita": entita,
        "ricordi": _ricordi_ancorati(ricordi, "area", riferimento),
    }
    _con_etichette(dettaglio, area, nomi_etichette)
    if incompleto:
        dettaglio["elenco_incompleto"] = incompleto
    return dettaglio


def _guarda_entita(casa: dict, ricordi: list[dict], stato: dict, riferimento,
                   non_disponibili: tuple[str, ...] = (),
                   nomi_di_ripiego: dict[str, str] | None = None,
                   unita_vive: dict[str, str] | None = None,
                 classi_vive: dict[str, str] | None = None) -> dict:
    entita = next((e for e in casa.get("entita") or [] if e.get("id") == riferimento), None)
    if entita is None:
        dettaglio = {"esiste": False, "tipo": "entita", "riferimento": riferimento}
        # CRITICAL ③: col registro "entita" caduto (`sostituisci` parziale
        # lascia la tabella vuota), un'entita' vera non trovata qui non e'
        # un'entita' che non esiste -- e' un registro che non ha risposto.
        # Prima di questo fix la firma non aveva nemmeno un punto d'ingresso
        # per dirlo: `non_disponibili` era ricevuto da `guarda()` ma
        # inoltrato SOLO a `_guarda_area`.
        if "entita" in non_disponibili:
            dettaglio["non_disponibile"] = True
        return dettaglio
    dettaglio = {
        "esiste": True, "tipo": "entita", "id": entita["id"], "nome": entita.get("nome"),
        # `unita` NON viene da qui: `config/entity_registry/list` risponde con
        # `as_partial_dict`, che non contiene ne' l'unita' ne' la classe ne'
        # gli alias (verificato sul sorgente di HA). La aggiunge
        # `_arricchisci_entita` dallo specchio vivo, che ce l'ha davvero -- e solo
        # quando c'e'. Prima questa riga prometteva un campo che era sempre
        # `null`: una promessa che non ha mai mantenuto niente.
        "classe": entita.get("classe"),
        # Un'entita' disabilitata resta in anagrafe (e' in Home Assistant e
        # non funziona) ma sparisce dall'albero di `gerarchia()` -- questo
        # campo dice perche' `guarda` la trova comunque, senza far credere
        # che sia una stanza arredata (stesso principio di anagrafe.py).
        "disabilitata": bool(entita.get("disabilitata")),
        "stato": stato.get(entita["id"]),
        "ricordi": _ricordi_ancorati(ricordi, "entita", riferimento),
    }
    # Stesso rimedio di `costruisci_indice` e per lo stesso motivo: su
    # questa casa `name` e `original_name` sono entrambi vuoti per un'intera
    # famiglia di entita', e un `nome: null` qui e' un'entita' che l'utente
    # chiama per nome e HIRIS non sa nominare. Marcato, mai scritto sopra
    # `nome`: dichiarato e dedotto restano due fatti (`_arricchisci_entita`).
    return _arricchisci_entita(dettaglio, entita, nomi_di_ripiego, unita_vive,
                               nomi_delle_etichette(casa), classi_vive)


def _guarda_dispositivo(casa: dict, ricordi: list[dict], stato: dict, riferimento,
                        non_disponibili: tuple[str, ...] = (),
                        nomi_di_ripiego: dict[str, str] | None = None,
                        unita_vive: dict[str, str] | None = None,
                 classi_vive: dict[str, str] | None = None) -> dict:
    nomi_etichette = nomi_delle_etichette(casa)
    dispositivo = next(
        (d for d in casa.get("dispositivi") or [] if d.get("id") == riferimento), None)
    if dispositivo is None:
        dettaglio = {"esiste": False, "tipo": "dispositivo", "riferimento": riferimento}
        # CRITICAL ③, stesso difetto applicato al dispositivo: col registro
        # "dispositivi" caduto, "non trovato" non e' "non esiste".
        if "dispositivi" in non_disponibili:
            dettaglio["non_disponibile"] = True
        return dettaglio
    # Stessa ragione per cui `_guarda_entita` porta `disabilitata`: qui si
    # legge `casa["entita"]` grezzo, fuori da `gerarchia()`, che le disabilitate
    # le esclude. Senza dirlo, un dispositivo spento e le sue entita' morte
    # avrebbero la stessa forma di uno che funziona.
    entita_del_dispositivo = [
        _arricchisci_entita(
            # `classe` e `stato` come dall'area: la stessa entita' e' la stessa
            # cosa da tutte le porte. Senza lo stato, questa porta usciva con
            # `unita: "C"` e nessun valore -- un'unita' di misura di un numero
            # che non c'e', e il modello o dice "non lo so" o lo inventa.
            {"id": e["id"], "nome": e.get("nome"), "classe": e.get("classe"),
             "stato": stato.get(e["id"]),
             "disabilitata": bool(e.get("disabilitata"))},
            e, nomi_di_ripiego, unita_vive, nomi_etichette, classi_vive)
        for e in casa.get("entita") or [] if e.get("dispositivo_id") == riferimento
    ]
    dettaglio = {
        "esiste": True, "tipo": "dispositivo", "id": dispositivo["id"],
        "nome": dispositivo.get("nome"),
        "disabilitato": bool(dispositivo.get("disabilitato")),
        "entita": entita_del_dispositivo,
        "ricordi": _ricordi_ancorati(ricordi, "dispositivo", riferimento),
    }
    _con_etichette(dettaglio, dispositivo, nomi_etichette)
    # L'elenco sopra viene da "entita" grezzo: se quel registro non ha
    # risposto, l'elenco puo' essere incompleto (o vuoto) senza che si veda
    # -- stesso principio di `_guarda_area`.
    if "entita" in non_disponibili:
        dettaglio["elenco_incompleto"] = ["entita"]
    return dettaglio


def _guarda_comportamento(comportamento: list[dict], ricordi: list[dict],
                           tipo: str, riferimento,
                           file_non_letti: dict[str, str] | None = None) -> dict:
    voce = next(
        (v for v in comportamento if v.get("id") == riferimento and v.get("tipo") == tipo), None)
    if voce is None:
        dettaglio = {"esiste": False, "tipo": tipo, "riferimento": riferimento}
        # CRITICAL ③, quinto ramo: se un file di comportamento non si e'
        # letto (`automations.yaml`/`scripts.yaml`, o uno incluso in un
        # pacchetto), "non trovato" non e' "non esiste" -- potrebbe essere
        # scritto proprio li'. Non si prova a indovinare QUALE file avrebbe
        # contenuto QUESTA voce (le automazioni scritte a mano non stanno
        # per forza nel file principale, vedi comportamento.py): se un file
        # qualsiasi non si e' letto, l'incertezza si dichiara comunque,
        # invece di tacerla come prima -- la firma non aveva nemmeno un
        # punto d'ingresso per riceverlo.
        if file_non_letti:
            dettaglio["non_disponibile"] = True
        return dettaglio
    return {
        "esiste": True, "tipo": tipo, "id": voce["id"], "nome": voce.get("nome"),
        # `corpo` passa cosi' com'e': `None` (HIRIS non l'ha, `origine` lo
        # dichiara) e un corpo vuoto ma presente sono due valori diversi, e
        # questa funzione non li confonde riscrivendoli.
        "corpo": voce.get("corpo"), "origine": voce.get("origine"),
        "ricordi": _ricordi_ancorati(ricordi, tipo, riferimento),
    }


def _guarda_ricordo(ricordi: list[dict], riferimento) -> dict:
    ricordo = next((r for r in ricordi if r.get("id") == riferimento), None)
    if ricordo is None:
        return {"esiste": False, "tipo": "ricordo", "riferimento": riferimento}
    return {
        "esiste": True, "tipo": "ricordo", "id": ricordo["id"], "testo": ricordo["testo"],
        "detto_da": ricordo.get("detto_da"),
        # Le quattro caselle dell'interpretazione (memoria/interpretazione.py),
        # tenute distinte dal testo -- che resta la verita', non riscritta.
        "interpretazione": {
            "forza": ricordo.get("forza"), "grandezza": ricordo.get("grandezza"),
            "minimo": ricordo.get("minimo"), "massimo": ricordo.get("massimo"),
            "unita": ricordo.get("unita"),
            "ancore": ricordo.get("ancore") or [],
            "condizioni": ricordo.get("condizioni") or [],
        },
    }


def guarda(casa: dict, comportamento: list[dict], ricordi: list[dict], stato: dict,
           tipo: str, riferimento,
           non_disponibili: tuple[str, ...] = (),
           file_non_letti: dict[str, str] | None = None,
           nomi_di_ripiego: dict[str, str] | None = None,
           unita_vive: dict[str, str] | None = None,
           classi_vive: dict[str, str] | None = None) -> dict:
    """Il dettaglio di UNA cosa sola -- l'area con le sue entita' e i loro
    stati, l'entita' col suo stato e la sua classe, l'automazione o lo
    script col loro corpo, il dispositivo con le sue entita', il ricordo
    con la sua interpretazione.

    Restituisce SEMPRE la chiave `esiste`. Quando e' `False` il resto non
    si inventa: nessun `entita: []`, nessun `corpo: None` che si potrebbe
    scambiare per un fatto sulla casa invece che per "non trovato" -- un
    silenzio non dichiarato e' indistinguibile da un'assenza di problemi.

    `non_disponibili` (registri dell'anagrafe caduti: "aree", "dispositivi",
    "entita") e `file_non_letti` (i file di comportamento non letti, stessa
    forma di `ArchivioCasa.file_non_letti()`) vanno propagati a OGNI ramo,
    non solo a quello dell'area: un "non trovato" e un "non ho potuto
    guardare" sono due fatti diversi, e prima di questo fix solo l'area
    poteva dirlo (CRITICAL ③ -- sbagliato quattro volte su questo ramo). Chi
    non li passa non e' punito con un errore: resta silenziosamente onesto,
    non silenziosamente sbagliato -- vedi `dettaglio["non_disponibile"]`,
    presente solo quando `esiste` e' `False` E il registro/file pertinente
    non ha risposto.

    `nomi_di_ripiego` (entity_id -> friendly_name dallo specchio dello
    stato, stessa forma usata da `costruisci_indice` e da `cerca()`) conta
    per OGNI ramo che elenca entita' -- `entita` da sola, ma anche le
    entita' di un'`area` e di un `dispositivo` (I1, review finale: la stessa
    entita' e' la stessa cosa da tutte le porte) -- e solo quando il
    registro non ha un nome: se c'e' esce come `nome_dedotto`, mai scritto
    sopra `nome` -- dichiarato e dedotto restano due fatti diversi.

    Pura: legge `casa`/`comportamento`/`ricordi`/`stato` cosi' come arrivano
    dal chiamante (`ArchivioCasa`, `ArchivioMemoria`, lo stato vivo di Home
    Assistant), non apre archivi ne' chiama la rete.
    """
    if tipo == "area":
        return _guarda_area(casa, ricordi, stato, riferimento, non_disponibili,
                            nomi_di_ripiego, unita_vive, classi_vive)
    if tipo == "entita":
        return _guarda_entita(casa, ricordi, stato, riferimento, non_disponibili,
                              nomi_di_ripiego, unita_vive, classi_vive)
    if tipo == "dispositivo":
        return _guarda_dispositivo(casa, ricordi, stato, riferimento, non_disponibili,
                                   nomi_di_ripiego, unita_vive, classi_vive)
    if tipo in _TIPI_COMPORTAMENTO:
        return _guarda_comportamento(comportamento, ricordi, tipo, riferimento, file_non_letti)
    if tipo == "ricordo":
        return _guarda_ricordo(ricordi, riferimento)
    # Un tipo che non conosciamo non e' un errore da sollevare: e' lo
    # stesso caso di "non l'ho trovato", solo con una causa diversa (il
    # modello ha nominato un tipo che non esiste, non un riferimento che
    # manca) -- e va dichiarato con la stessa onesta', non con un'eccezione
    # che gli spezza il turno.
    return {"esiste": False, "tipo": tipo, "riferimento": riferimento}
