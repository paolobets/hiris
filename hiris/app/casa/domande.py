"""Le tre domande: cercare per nome, guardare il dettaglio, chiedere i legami.

Il nucleo (nucleo.py) dice DOVE sono le cose -- conta, non elenca. Le tre
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
- `legami(risposta, tipo, riferimento)` -- CHI tocca questa cosa, secondo
  Home Assistant. Non e' un terzo modo di guardare la stessa cosa: `guarda`
  porta il CORPO (cosa fa quell'automazione), `legami` porta i LEGAMI (quali
  automazioni, script, scene o gruppi nominano questa entita'). Sono due
  fatti diversi sullo stesso oggetto, e tenerli in due risposte e' cio' che
  li tiene distinti -- la confusione fra «dichiarato» e «dedotto» questo
  progetto la paga da sempre.

Due, non trentaquattro: la mappa del prodotto ha condannato un catalogo di
trentaquattro strumenti con tre copie divergenti (vedi
docs/design/2026-08-05-la-conoscenza-di-hiris.md). Un tipo nuovo di "cosa"
si aggiunge come un altro `if` dentro `guarda`, non come un tool in piu'.

Tutte e tre sono PURE: prendono dati gia' letti dal chiamante (l'indice, la
casa, il comportamento, i ricordi, lo stato vivo, la risposta che Home
Assistant ha gia' dato) e non aprono archivi ne' chiamano la rete -- la
stessa scelta che rende `componi()` del nucleo verificabile senza finti
elaborati (nucleo.py). Vale anche per `legami`: la chiamata WebSocket la fa
il chiamante (`casa/strumenti.py`), qui arriva solo cio' che ha risposto.

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

from ..proxy._sanitize import sanitize_text
from .anagrafe import (categorie_con_nome, classe_effettiva, dominio_di,
                       etichette_con_id, gerarchia, nomi_delle_categorie,
                       nomi_delle_etichette, traduci_stato, unita_effettiva)

# I tipi di comportamento che `guarda` sa mostrare col loro corpo. Un
# "automazione" e uno "script" sono voci dello stesso elenco
# (comportamento.py), non due archivi diversi: la distinzione e' nel campo
# `tipo` della voce, non nella provenienza.
_TIPI_COMPORTAMENTO = {"automazione", "script"}

# I quattordici tipi che `search/related` sa collegare -- i VALORI di
# `ItemType` (`homeassistant/components/search/__init__.py`, letti sul
# sorgente, non a memoria) -- nel vocabolario di HIRIS.
#
# A sinistra il nome vero di Home Assistant, che e' quello che va dentro il
# comando; a destra il nome italiano con cui quella cosa vive qui dentro.
# Stessa disciplina di `anagrafe._CAMPI_RIFERIMENTO`: l'anagrafe parla la
# lingua di HIRIS ovunque, e una risposta meta' inglese sarebbe l'unico posto
# in cui non lo fa -- per giunta proprio quella da cui il modello ricava un
# `riferimento` da passare a `guarda`, che i tipi li nomina in italiano.
#
# Si legge nei DUE versi (`TIPO_LEGAME_HA` piu' sotto e' la stessa tabella
# rovesciata, non una seconda): il modello nomina «entita», Home Assistant
# vuole «entity». Due elenchi da tenere allineati a mano sarebbero due
# vocabolari, cioe' la forma di difetto che le fondamenta chiamano doppione.
#
# Cinque di questi nomi -- area, entita, dispositivo, automazione, script --
# sono esattamente i tipi che `guarda` sa aprire; gli altri nove no, e
# `guarda` lo DICHIARA invece di rispondere «non esiste» (vedi il ramo finale
# di `guarda`): un id vero preso da qui non deve poter diventare
# un'affermazione falsa sulla casa.
NOME_LEGAME = {
    "area": "area",
    "automation": "automazione",
    "automation_blueprint": "progetto_di_automazione",
    "config_entry": "voce_di_configurazione",
    "device": "dispositivo",
    "entity": "entita",
    "floor": "piano",
    "group": "gruppo",
    "integration": "integrazione",
    "label": "etichetta",
    "person": "persona",
    "scene": "scena",
    "script": "script",
    "script_blueprint": "progetto_di_script",
}

# La stessa tabella dal verso del modello. Derivata, mai riscritta.
TIPO_LEGAME_HA = {nostro: loro for loro, nostro in NOME_LEGAME.items()}


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
      tale -- stessa forma di `nome_dedotto` in `guarda()`/`_guarda_entita`;
    - `nascosta` (solo per le entita', e solo quando e' vera), fetta
      "nascoste fuori dagli elenchi" (2026-08-25): il proprietario ha
      misurato in produzione che `cerca` non riportava affatto questo campo
      -- «lampadario» trovava tre lampade LIFX nascoste e nulla lo diceva.
      Qui NON si esclude come in `guarda`: un'entita' cercata per nome e'
      una domanda diretta, e togliere dalla lista una cosa che esiste
      sarebbe rispondere «non esiste» di una cosa che c'e' -- la frase che
      questo prodotto non deve mai dire con sicurezza. Si MARCA soltanto, e
      solo quando e' vera: `nascosta: false` su ogni candidato di una casa
      da 1226 entita' sarebbe rumore in ogni risposta -- stessa disciplina
      di `unita`/`categorie` in `guarda()`.

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
                if oggetto.get("nascosta"):
                    candidato["nascosta"] = True
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
                        classi_vive: dict[str, str] | None = None,
                        nomi_categorie: dict[tuple[str, str], str] | None = None,
                        attributi_vivi: dict[str, dict] | None = None) -> dict:
    """LA PORTA UNICA per tutto cio' che si aggiunge a un'entita'.

    Arricchisce `dettaglio_entita` con cio' che lo SPECCHIO VIVO sa e il
    registro no (il nome dedotto e l'unita' di misura) e con cio' che il
    registro sa e la proiezione lascerebbe indietro (la piattaforma, le
    etichette e le categorie).

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
    #
    # Il DOMINIO e l'`hvac_action` (dallo specchio vivo, mai dal registro:
    # `anagrafe.classe_effettiva` vale anche qui) alimentano il solo caso in
    # cui uno stato grezzo mente da solo -- un termostato IMPOSTATO su
    # riscaldamento e FERMO che si legge «heat» com'e' il difetto misurato dal
    # proprietario (2026-08-25, `anagrafe.traduci_stato`). Passati anche
    # quando l'entita' non e' un termostato: `traduci_stato` li ignora per
    # ogni altro dominio, e ricalcolarli qui una volta e' piu' semplice che
    # farlo condizionale.
    valore = dettaglio_entita.get("stato")
    if valore is not None:
        hvac_action = ((attributi_vivi or {}).get(entita_id) or {}).get("hvac_action")
        dettaglio_entita["stato_leggibile"] = traduci_stato(
            valore, dettaglio_entita.get("classe"), dominio_di(entita_id), hvac_action)
    # L'integrazione che la fornisce (hue, zwave_js, template): dice perche'
    # una cosa non risponde e cosa le si puo' chiedere.
    piattaforma = (voce.get("piattaforma") or "").strip()
    if piattaforma:
        dettaglio_entita["piattaforma"] = piattaforma
    # NASCOSTA e CATEGORIA: fuori dalle gestioni, dentro la conoscenza.
    #
    # Il digesto conta le nascoste e scrive «esistono, e `guarda` le riporta se
    # gliele chiedi» -- una promessa che `guarda` non poteva mantenere, perche'
    # il campo non usciva da nessuna porta. Alla domanda «quali sono?» il
    # modello o si contraddiceva o inventava.
    #
    # Solo quando sono vere: `nascosta: false` su ogni entita' di una casa da
    # trecento sarebbe rumore in ogni risposta, e `categoria: null` pure.
    if voce.get("nascosta"):
        dettaglio_entita["nascosta"] = True
    categoria = (voce.get("categoria") or "").strip()
    if categoria:
        dettaglio_entita["categoria"] = categoria
    _con_categorie(dettaglio_entita, voce, nomi_categorie or {})
    return _con_etichette(dettaglio_entita, voce, nomi_etichette or {})


def _con_categorie(dettaglio: dict, voce: dict,
                   nomi_categorie: dict[tuple[str, str], str]) -> dict:
    """L'altra tassonomia scritta a mano dall'utente in Home Assistant.

    Le categorie stanno alle etichette come una cartella sta a un post-it:
    «Luci esterne», «Vacanza», «Da rifare». HIRIS leggeva il loro registro con
    QUATTRO comandi WebSocket a ogni ricostruzione dell'anagrafe -- uno per
    ambito -- e non le faceva uscire da nessuna porta; l'assegnazione
    per-entita', che arriva GRATIS dentro la risposta del registro delle
    entita' (`RegistryEntry.as_partial_dict`, verificato sul sorgente di HA),
    non la salvava nemmeno. Costo pieno, resa zero.

    Escono col NOME, non col `category_id`: l'unione la fa
    `anagrafe.categorie_con_nome`, la stessa che usa l'indice di `cerca`.
    Senza, HIRIS riferirebbe all'utente un identificativo che l'utente non ha
    mai scritto -- ed e' la trappola gia' pagata una volta con le etichette.

    La forma e' `{ambito: nome}` e non una lista di nomi: l'ambito
    (`automation`, `script`, `scene`, `helpers`) fa parte dell'identita' della
    categoria, e due omonime in ambiti diversi sono due cose diverse.

    Da NON confondere con `categoria` (singolare), che e' l'`entity_category`
    di Home Assistant -- `config` o `diagnostic`, decisa dall'integrazione.

    Compare solo quando ce n'e' almeno una: `categorie: {}` su ogni cosa
    sarebbe rumore in ogni risposta e -- peggio -- indistinguibile da un
    registro delle categorie caduto. Stessa disciplina di `etichette`.
    """
    categorie = categorie_con_nome(voce, nomi_categorie)
    if categorie:
        dettaglio["categorie"] = categorie
    return dettaglio


def _con_etichette(dettaglio: dict, voce: dict, nomi_etichette: dict[str, str]) -> dict:
    """Le etichette che l'utente ha scritto a mano in Home Assistant.

    Sono il significato piu' DICHIARATO che esista in quella casa -- «inverno»,
    «da controllare», «piano di sotto» -- e HIRIS le leggeva, le salvava, le
    metteva perfino nell'albero di `gerarchia()`, senza farle uscire da nessuna
    porta. Un'etichetta che non porta a niente costringe l'utente a ripetere a
    parole cio' che aveva gia' dichiarato una volta.

    Escono col NOME protagonista, col `label_id` accanto come dato
    ACCESSORIO -- `Nome (id: X)`, la stessa forma di `anagrafe.nome_con_id`
    (T8, R2: fino a questa fetta il `label_id` non usciva da NESSUNA porta,
    eppure `esegui(bersaglio.etichette=[...])` lo pretende -- il vicolo cieco
    piu' radicale della famiglia, docs/design/2026-08-20-i-riferimenti.md).
    La scelta di leggibilita' di questo modulo NON cambia: la parentesi entra
    solo perche' l'id serve, non al posto del nome. L'unione la fa
    `anagrafe.nomi_delle_etichette`, la stessa che usa l'indice di `cerca` --
    che da T8 conosce anche le etichette stesse come candidati
    (`memoria/riconoscitore.py::costruisci_indice`), per chi sa solo il nome
    e non ha ancora nessuna cosa che la porti.

    Compare solo quando ce n'e' almeno una: `etichette: []` su ogni cosa
    sarebbe rumore in ogni risposta e -- peggio -- indistinguibile da un
    registro delle etichette caduto. Stessa disciplina di `unita`.
    """
    etichette = etichette_con_id(voce, nomi_etichette)
    if etichette:
        dettaglio["etichette"] = etichette
    return dettaglio


def _suggerimento_cerca(riferimento) -> str:
    """Il messaggio che accompagna un `esiste: False` sui tre rami che
    possono confondere un NOME con un id -- area, entita', dispositivo.

    R5 (2026-08-20, misurato dal vivo): il modello chiama `guarda` con un
    nome («Soggiorno») al posto dell'id (`soggiorno`), e riceveva
    `{"esiste": False}` nudo -- indistinguibile da "quest'area non esiste
    davvero", nessun invito a `cerca`. E' il meccanismo diretto
    dell'incidente che ha generato questa fetta: il modello ritenta uguale
    finche' il turno muore.

    Il pattern esiste gia' in `azione/verifica.py::_no` per il bersaglio
    non risolto («Usa "cerca" per trovare il nome giusto e ripeti il
    comando») -- questa funzione lo estende a `guarda`, non lo reinventa:
    UNA sola sorgente per i tre rami (fondamenta 3, "stessa forma"), cosi'
    che togliere il richiamo da un ramo solo non lascia gli altri due
    invariati -- si nota, perche' la frase e' la stessa ovunque.
    """
    return (f"«{riferimento}» non e' stato trovato. Se e' un NOME (non un "
            f"id), chiama «cerca» con questo testo per trovare l'id giusto, "
            f"poi ripeti «guarda» con quello.")


def _dettaglio_non_trovato(tipo: str, riferimento, registro_caduto: bool) -> dict:
    """Il dict `esiste: False` comune ai rami che possono confondere un
    NOME con un id -- area, entita', dispositivo, e da T7 (R2) anche
    automazione/script (`_guarda_comportamento`, sotto).

    "non trovato" ha due cause DIVERSE (CRITICAL ③, gia' pagato piu' volte
    su questo file): il riferimento non c'e' davvero, oppure il registro
    che lo conterrebbe non ha risposto. Sono anche due RIMEDI diversi, non
    solo due dichiarazioni:

    - riferimento assente -> `suggerimento` (invita a `cerca`, potrebbe
      essere un nome scambiato per un id);
    - registro caduto -> SOLO `non_disponibile`, MAI `suggerimento`:
      `cerca` legge la STESSA anagrafe incompleta, quindi "prova a
      cercare" sarebbe una strada altrettanto cieca -- e diluirebbe
      proprio la distinzione che `non_disponibile` esiste per marcare
      (review indipendente Task 3, confermata: suggerire quando la causa
      e' un guasto e' un rischio, non un aiuto).

    Un punto solo per questa scelta: i rami non portano una copia ciascuno
    della stessa condizione, e chi la cambia la cambia qui una volta sola.

    T7 (R2): fino a questa fetta `_guarda_comportamento` costruiva il suo
    `esiste: False` a mano, SENZA `suggerimento` -- una scelta deliberata
    del Task 3 (review indipendente, confermata), perche' allora `cerca`
    non indicizzava automazioni/script: suggerire "chiama cerca" sarebbe
    stato un invito a una strada cieca. Da quando `cerca` li indicizza
    (`memoria/riconoscitore.py::costruisci_indice`), quella ragione non
    vale piu', e il confine si sposta: `_guarda_comportamento` chiama
    questa funzione come gli altri tre rami, invece di duplicarne la
    logica con un `file_non_letti` scambiato per `registro_caduto`.
    """
    dettaglio = {"esiste": False, "tipo": tipo, "riferimento": riferimento}
    if registro_caduto:
        dettaglio["non_disponibile"] = True
    else:
        dettaglio["suggerimento"] = _suggerimento_cerca(riferimento)
    return dettaglio


def _righe_entita(elenco: list[dict], stato: dict, da_quando_vive: dict[str, str] | None,
                  disabilitata: bool, nomi_di_ripiego: dict[str, str] | None,
                  unita_vive: dict[str, str] | None, nomi_etichette: dict[str, str],
                  classi_vive: dict[str, str] | None,
                  nomi_categorie: dict[tuple[str, str], str],
                  attributi_vivi: dict[str, dict] | None) -> list[dict]:
    """Un elenco grezzo di voci dell'anagrafe (`entita`/`entita_disabilitate`/
    `entita_nascoste` di `gerarchia()`) arricchito UNA riga alla volta con
    `_arricchisci_entita` -- il ciclo si scriveva tre volte in `_guarda_area`
    (una per lista) con la stessa forma, e tre copie sono tre posti in cui la
    stessa correzione si dimentica di una.

    `disabilitata` e' un valore FISSO per l'intero elenco, non letto dalla
    voce: chi chiama sa gia' da quale lista viene (le disabilitate hanno gia'
    lasciato `per_area`/`per_area_nascoste` in `gerarchia()`)."""
    return [
        _arricchisci_entita(
            {"id": e["id"], "nome": e.get("nome"), "classe": e.get("classe"),
             "stato": stato.get(e["id"]),
             "da_quando": (da_quando_vive or {}).get(e["id"]),
             "disabilitata": disabilitata},
            e, nomi_di_ripiego, unita_vive, nomi_etichette, classi_vive,
            nomi_categorie, attributi_vivi)
        for e in elenco
    ]


def _guarda_area(casa: dict, ricordi: list[dict], stato: dict, riferimento,
                 non_disponibili: tuple[str, ...] = (),
                 nomi_di_ripiego: dict[str, str] | None = None,
                 unita_vive: dict[str, str] | None = None,
                 classi_vive: dict[str, str] | None = None,
                 da_quando_vive: dict[str, str] | None = None,
                 attributi_vivi: dict[str, dict] | None = None) -> dict:
    # `non_disponibili` va PROPAGATO, non solo ricevuto: senza, `gerarchia()`
    # crede che sia andato tutto bene e un'entita' che eredita l'area dal
    # proprio dispositivo -- col registro dispositivi caduto -- finisce in
    # "Senza area" invece che in "Dispositivi non letti". Risultato: una
    # cucina con cinque luci ne mostra quattro, con `esiste: True` e nessun
    # avviso: la stessa forma di una cucina davvero piu' piccola.
    piani = gerarchia(casa, tuple(non_disponibili))
    nomi_etichette = nomi_delle_etichette(casa)
    nomi_categorie = nomi_delle_categorie(casa)
    area = _trova_area(piani, riferimento)
    if area is None:
        # CRITICAL ③: se il registro delle aree non ha risposto, "non
        # trovata" non e' lo stesso di "non esiste" -- potrebbe stare
        # proprio nella parte che non si e' letta. Senza dichiararlo, il
        # modello legge "quest'area non esiste nella tua casa", un'
        # affermazione che nessuno ha il diritto di fare. La scelta fra
        # `non_disponibile` e `suggerimento` e' in `_dettaglio_non_trovato`.
        return _dettaglio_non_trovato("area", riferimento, "aree" in non_disponibili)
    entita = (
        # Marcate, non nascoste (MINOR): una vista di DETTAGLIO deve poter
        # dire "questa luce c'e' ma e' disabilitata" -- `_guarda_dispositivo`
        # e `_guarda_entita` lo fanno gia', `_guarda_area` no. `gerarchia()`
        # le tiene apposta fuori dai conteggi ma raggiungibili qui (vedi
        # anagrafe.py). Restano dentro `entita`, marcate: sapere che quella
        # luce c'e' ma non funziona e' informazione, non rumore.
        _righe_entita(area["entita"], stato, da_quando_vive, False, nomi_di_ripiego,
                     unita_vive, nomi_etichette, classi_vive, nomi_categorie, attributi_vivi)
        + _righe_entita(area.get("entita_disabilitate", []), stato, da_quando_vive, True,
                       nomi_di_ripiego, unita_vive, nomi_etichette, classi_vive,
                       nomi_categorie, attributi_vivi)
    )
    # Le NASCOSTE, invece, in una chiave A PARTE -- non marcate dentro
    # `entita` come le disabilitate qui sopra (fetta "nascoste fuori dagli
    # elenchi", 2026-08-25). Il proprietario ha misurato in produzione che
    # `guarda("area", "sala_da_pranzo")` elencava sette luci mescolate,
    # quattro nascoste, col campo `nascosta` gia' presente su ognuna: stare
    # nella STESSA lista non ha impedito che venissero nominate lo stesso.
    # La regola voluta -- "HIRIS non considera le nascoste, a meno che non
    # gli vengano chieste esplicitamente" -- si applica per STRUTTURA: il
    # modello che legge `entita` per rispondere "quali luci ci sono in sala
    # da pranzo" non le vede affatto, senza dover ricordare di filtrarle da
    # un campo. Restano pero' COMPLETE e raggiungibili qui, per la stessa
    # domanda esplicita -- "cosa hai nascosto?" -- che il campo `nascosta`
    # serviva gia' quando l'entita' si guarda da sola (`_guarda_entita`).
    entita_nascoste = _righe_entita(area.get("entita_nascoste", []), stato, da_quando_vive,
                                    False, nomi_di_ripiego, unita_vive, nomi_etichette,
                                    classi_vive, nomi_categorie, attributi_vivi)
    # L'elenco puo' essere incompleto senza che si veda: si dichiara.
    incompleto = sorted(set(non_disponibili) & {"aree", "dispositivi", "entita"})
    dettaglio = {
        "esiste": True, "tipo": "area", "id": area["id"], "nome": area["nome"],
        "entita": entita,
        "ricordi": _ricordi_ancorati(ricordi, "area", riferimento),
    }
    # Solo quando ce n'e' almeno una: `entita_nascoste: []` su ogni area
    # (la stragrande maggioranza non ne ha) sarebbe rumore in ogni risposta
    # -- stessa disciplina di `unita`/`etichette`/`categorie` in questo file.
    if entita_nascoste:
        dettaglio["entita_nascoste"] = entita_nascoste
    # Le entita' di riferimento della stanza: solo quando l'utente le ha
    # dichiarate. Una chiave `null` su ogni area sarebbe rumore, e per giunta
    # indistinguibile da un registro delle aree caduto.
    for chiave in ("entita_temperatura", "entita_umidita"):
        valore = (area.get(chiave) or "").strip()
        if valore:
            dettaglio[chiave] = valore
    _con_etichette(dettaglio, area, nomi_etichette)
    if incompleto:
        dettaglio["elenco_incompleto"] = incompleto
    return dettaglio


def _guarda_entita(casa: dict, ricordi: list[dict], stato: dict, riferimento,
                   non_disponibili: tuple[str, ...] = (),
                   nomi_di_ripiego: dict[str, str] | None = None,
                   unita_vive: dict[str, str] | None = None,
                 classi_vive: dict[str, str] | None = None,
                 da_quando_vive: dict[str, str] | None = None,
                 attributi_vivi: dict[str, dict] | None = None) -> dict:
    entita = next((e for e in casa.get("entita") or [] if e.get("id") == riferimento), None)
    if entita is None:
        # CRITICAL ③: col registro "entita" caduto (`sostituisci` parziale
        # lascia la tabella vuota), un'entita' vera non trovata qui non e'
        # un'entita' che non esiste -- e' un registro che non ha risposto.
        # Prima di questo fix la firma non aveva nemmeno un punto d'ingresso
        # per dirlo: `non_disponibili` era ricevuto da `guarda()` ma
        # inoltrato SOLO a `_guarda_area`.
        return _dettaglio_non_trovato("entita", riferimento, "entita" in non_disponibili)
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
        "da_quando": (da_quando_vive or {}).get(entita["id"]),
        "ricordi": _ricordi_ancorati(ricordi, "entita", riferimento),
    }
    # Stesso rimedio di `costruisci_indice` e per lo stesso motivo: su
    # questa casa `name` e `original_name` sono entrambi vuoti per un'intera
    # famiglia di entita', e un `nome: null` qui e' un'entita' che l'utente
    # chiama per nome e HIRIS non sa nominare. Marcato, mai scritto sopra
    # `nome`: dichiarato e dedotto restano due fatti (`_arricchisci_entita`).
    dettaglio = _arricchisci_entita(dettaglio, entita, nomi_di_ripiego, unita_vive,
                                    nomi_delle_etichette(casa), classi_vive,
                                    nomi_delle_categorie(casa), attributi_vivi)
    # GLI ATTRIBUTI CURATI (`_DOMAIN_ATTRS`, `proxy/entity_cache.py`): solo
    # QUI, sul dettaglio di UNA entita' sola -- decisione del proprietario,
    # fetta "attributi al modello" (2026-08-25). `_guarda_area` e
    # `_guarda_dispositivo` elencano entita' a decine (un'area con venti
    # cose, un dispositivo con le sue entita'): mettere gli attributi di
    # ognuna dentro quegli elenchi gonfierebbe la risposta di un dato che
    # nessuno ha chiesto per la singola cosa. Qui invece il modello ha gia'
    # chiesto IL DETTAGLIO di questa entita' precisa, ed e' il momento in cui
    # l'informazione si paga -- non prima. `hvac_action` (climate) alimenta
    # comunque `stato_leggibile` ovunque, dentro `_arricchisci_entita`: la
    # differenza qui e' solo se il resto degli attributi grezzi (luminosita',
    # posizione, titolo del brano...) esce come chiave a se'.
    attributi = (attributi_vivi or {}).get(entita["id"])
    if attributi:
        dettaglio["attributi"] = attributi
    return dettaglio


def _guarda_dispositivo(casa: dict, ricordi: list[dict], stato: dict, riferimento,
                        non_disponibili: tuple[str, ...] = (),
                        nomi_di_ripiego: dict[str, str] | None = None,
                        unita_vive: dict[str, str] | None = None,
                 classi_vive: dict[str, str] | None = None,
                 da_quando_vive: dict[str, str] | None = None,
                 attributi_vivi: dict[str, dict] | None = None) -> dict:
    nomi_etichette = nomi_delle_etichette(casa)
    nomi_categorie = nomi_delle_categorie(casa)
    dispositivo = next(
        (d for d in casa.get("dispositivi") or [] if d.get("id") == riferimento), None)
    if dispositivo is None:
        # CRITICAL ③, stesso difetto applicato al dispositivo: col registro
        # "dispositivi" caduto, "non trovato" non e' "non esiste".
        return _dettaglio_non_trovato("dispositivo", riferimento,
                                      "dispositivi" in non_disponibili)
    # Stessa ragione per cui `_guarda_entita` porta `disabilitata`: qui si
    # legge `casa["entita"]` grezzo, fuori da `gerarchia()`, che le disabilitate
    # le esclude. Senza dirlo, un dispositivo spento e le sue entita' morte
    # avrebbero la stessa forma di uno che funziona.
    #
    # Le NASCOSTE (e non disabilitate: stessa precedenza di `gerarchia()` --
    # una disabilitata e nascosta insieme resta fra le disabilitate, non
    # duplica il fatto in due chiavi) si separano PRIMA di arricchire, con la
    # stessa regola dell'area: fuori da `entita`, dentro `entita_nascoste`
    # (fetta "nascoste fuori dagli elenchi", 2026-08-25) -- STESSA chiave,
    # STESSA forma della porta area, cosi' il modello non impara due
    # vocabolari per lo stesso fatto su due porte diverse.
    entita_grezze_del_dispositivo = [
        e for e in casa.get("entita") or [] if e.get("dispositivo_id") == riferimento]
    nascoste_grezze = [e for e in entita_grezze_del_dispositivo
                       if e.get("nascosta") and not e.get("disabilitata")]
    visibili_grezze = [e for e in entita_grezze_del_dispositivo
                       if not (e.get("nascosta") and not e.get("disabilitata"))]
    entita_del_dispositivo = [
        _arricchisci_entita(
            # `classe` e `stato` come dall'area: la stessa entita' e' la stessa
            # cosa da tutte le porte. Senza lo stato, questa porta usciva con
            # `unita: "C"` e nessun valore -- un'unita' di misura di un numero
            # che non c'e', e il modello o dice "non lo so" o lo inventa.
            {"id": e["id"], "nome": e.get("nome"), "classe": e.get("classe"),
             "stato": stato.get(e["id"]),
             "da_quando": (da_quando_vive or {}).get(e["id"]),
             "disabilitata": bool(e.get("disabilitata"))},
            e, nomi_di_ripiego, unita_vive, nomi_etichette, classi_vive,
            nomi_categorie, attributi_vivi)
        for e in visibili_grezze
    ]
    entita_nascoste_dispositivo = _righe_entita(
        nascoste_grezze, stato, da_quando_vive, False, nomi_di_ripiego, unita_vive,
        nomi_etichette, classi_vive, nomi_categorie, attributi_vivi)
    dettaglio = {
        "esiste": True, "tipo": "dispositivo", "id": dispositivo["id"],
        "nome": dispositivo.get("nome"),
        "disabilitato": bool(dispositivo.get("disabilitato")),
        "entita": entita_del_dispositivo,
        "ricordi": _ricordi_ancorati(ricordi, "dispositivo", riferimento),
    }
    # Solo quando ce n'e' almeno una -- stessa disciplina della porta area.
    if entita_nascoste_dispositivo:
        dettaglio["entita_nascoste"] = entita_nascoste_dispositivo
    # Marca e modello: letti a ogni ricostruzione, e mai usciti da nessuna
    # porta. «Di che marca e' la valvola del bagno? Devo ordinarne un'altra
    # uguale» e' una domanda che si fa davvero, e la risposta era in tabella.
    for chiave in ("produttore", "modello"):
        valore = (dispositivo.get(chiave) or "").strip()
        if valore:
            dettaglio[chiave] = valore
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
        # CRITICAL ③, quinto ramo: se un file di comportamento non si e'
        # letto (`automations.yaml`/`scripts.yaml`, o uno incluso in un
        # pacchetto), "non trovato" non e' "non esiste" -- potrebbe essere
        # scritto proprio li'. Non si prova a indovinare QUALE file avrebbe
        # contenuto QUESTA voce (le automazioni scritte a mano non stanno
        # per forza nel file principale, vedi comportamento.py): se un file
        # qualsiasi non si e' letto, l'incertezza si dichiara comunque,
        # invece di tacerla come prima -- la firma non aveva nemmeno un
        # punto d'ingresso per riceverlo.
        #
        # T7 (R2): `_dettaglio_non_trovato`, non piu' un dict a mano --
        # `file_non_letti` gioca lo stesso ruolo di `registro_caduto` per
        # area/entita'/dispositivo (un guasto di lettura, non l'assenza
        # della cosa), e ora che `cerca` indicizza automazioni e script un
        # NOME al posto dell'id e' un errore possibile anche qui: merita lo
        # stesso `suggerimento` degli altri tre rami, con la stessa frase.
        return _dettaglio_non_trovato(tipo, riferimento, bool(file_non_letti))
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
    # La forma e' PIATTA, la stessa di `richiama` e dei `ricordi` che ogni
    # altro ramo di `guarda` gia' restituisce (`_ricordi_ancorati`).
    #
    # Prima l'interpretazione era annidata sotto una chiave `interpretazione`
    # e `detto_il` non usciva affatto: lo stesso ricordo aveva due forme a
    # seconda della porta. Il modello ne imparava una dentro
    # `guarda("area", ...)`, poi chiedeva il dettaglio con
    # `guarda("ricordo", id)` e leggeva `r["forza"]` -> assente, e riferiva
    # «di questo ricordo non so la forza» su un ricordo che ce l'ha. E alla
    # domanda «quando te l'ho detto?» la risposta dipendeva da quale strumento
    # il modello avesse scelto.
    #
    # Le caselle restano distinte dal TESTO -- che e' la verita' e non si
    # riscrive -- ma la distinzione la fanno i nomi dei campi, non un livello
    # di annidamento in piu' che esiste da una porta sola.
    dettaglio = {
        "esiste": True, "tipo": "ricordo", "id": ricordo["id"], "testo": ricordo["testo"],
        "detto_da": ricordo.get("detto_da"),
        "detto_il": ricordo.get("detto_il"),
        "forza": ricordo.get("forza"), "grandezza": ricordo.get("grandezza"),
        "minimo": ricordo.get("minimo"), "massimo": ricordo.get("massimo"),
        "unita": ricordo.get("unita"),
        "ancore": ricordo.get("ancore") or [],
        "condizioni": ricordo.get("condizioni") or [],
    }
    return dettaglio


def ricordi_sanificati(ricordi: list[dict] | None) -> list[dict]:
    """I ricordi con `testo` passato dal sanitizzatore -- funzione condivisa,
    non una riga ripetuta a ogni porta che restituisce ricordi al modello.

    C-2/I1 (L1-sicurezza.md, review indipendente del 25/08/2026): la prima
    versione di questa correzione sanificava il testo dentro `guarda()` ma
    non dentro `strumenti.py::_richiama` (che legge `ArchivioMemoria.per_ancora`
    direttamente, senza passare da qui) -- lo stesso ricordo usciva filtrato
    da una porta e grezzo dall'altra: la fondamenta 3 (consistenza fra porte)
    rotta dentro la correzione che doveva chiuderla. Un punto SOLO, importato
    da entrambe le porte, e' l'unico modo per cui questo non possa ripetersi
    con una terza porta futura.

    Il testo ARCHIVIATO non cambia (`memoria/archivio.py`, regola 1): questa
    e' una copia, non una riscrittura -- vedi il docstring di `guarda()`."""
    return [dict(r, testo=sanitize_text(r["testo"])) if "testo" in r else r
           for r in (ricordi or [])]


def guarda(casa: dict, comportamento: list[dict], ricordi: list[dict], stato: dict,
           tipo: str, riferimento,
           non_disponibili: tuple[str, ...] = (),
           file_non_letti: dict[str, str] | None = None,
           nomi_di_ripiego: dict[str, str] | None = None,
           unita_vive: dict[str, str] | None = None,
           classi_vive: dict[str, str] | None = None,
           da_quando_vive: dict[str, str] | None = None,
           attributi_vivi: dict[str, dict] | None = None) -> dict:
    """Il dettaglio di UNA cosa sola -- l'area con le sue entita' e i loro
    stati, l'entita' col suo stato e la sua classe, l'automazione o lo
    script col loro corpo, il dispositivo con le sue entita', il ricordo
    con la sua interpretazione.

    Restituisce SEMPRE la chiave `esiste`. Quando e' `False` il resto non
    si inventa: nessun `entita: []`, nessun `corpo: None` che si potrebbe
    scambiare per un fatto sulla casa invece che per "non trovato" -- un
    silenzio non dichiarato e' indistinguibile da un'assenza di problemi.

    Sui due rami che elencano entita' -- area e dispositivo -- `entita` NON
    contiene mai le NASCOSTE (`hidden_by` di Home Assistant, l'utente le ha
    tolte dalle proprie viste): fetta "nascoste fuori dagli elenchi"
    (2026-08-25), decisione del proprietario -- "HIRIS non prende in
    considerazione le entita' nascoste, a meno che non gli vengano chieste
    esplicitamente". Restano complete e raggiungibili nella chiave parallela
    `entita_nascoste` (presente solo quando ce n'e' almeno una), la stessa
    forma di `gerarchia()` per le disabilitate. La differenza col
    trattamento delle disabilitate e' voluta: quelle restano DENTRO `entita`,
    marcate (`disabilitata: true`) -- e' un dato utile su un impianto che
    esiste, "questa luce c'e' ma non funziona"; le nascoste sono una scelta
    di VISTA dell'utente, e la misura in produzione (`guarda("area",
    "sala_da_pranzo")`, sette luci mescolate, quattro nascoste) ha mostrato
    che marcarle SENZA separarle non basta -- il campo c'era gia' e non ha
    impedito che venissero elencate. Una singola entita' guardata da sola
    (`_guarda_entita`) continua a portare il campo `nascosta` invece che una
    chiave a parte: non c'e' un elenco da cui separarla, hai chiesto
    esplicitamente proprio lei.

    R5: sui rami che possono confondere un NOME con un id -- area, entita',
    dispositivo, e da T7 (R2) anche automazione e script -- `esiste: False`
    porta anche `suggerimento` (`_suggerimento_cerca`): invita a chiamare
    `cerca` col riferimento ricevuto. STESSA chiave, STESSA frase su tutti
    questi rami (fondamenta 3) -- non su `_guarda_ricordo`, il solo tipo il
    cui id (numerico, interno a HIRIS, mai uno slug di Home Assistant) non
    si scrive mai al posto di un nome.

    Fino a T7 automazione e script restavano fuori apposta (decisione del
    Task 3, review indipendente): `cerca` non li indicizzava ancora, e
    suggerirlo sarebbe stato un invito a una strada che non portava da
    nessuna parte. Da quando `cerca` li indicizza
    (`memoria/riconoscitore.py::costruisci_indice`), quella ragione e'
    caduta, e il confine si e' spostato con lei: vedi il docstring di
    `_dettaglio_non_trovato`, che ora e' anche la porta di
    `_guarda_comportamento`.

    MA non quando `non_disponibile` e' vero (`_dettaglio_non_trovato`): se
    il registro e' caduto, `cerca` legge la STESSA anagrafe incompleta --
    suggerirlo sarebbe una strada altrettanto cieca, e diluirebbe la
    distinzione fra "non trovato" e "non ho potuto guardare" che questo
    modulo marca come critica. Le due chiavi sono quindi mutuamente
    esclusive su questi tre rami: mai `suggerimento` insieme a
    `non_disponibile`.

    E `esiste: False` ha due cause diverse, che da questa fetta si vedono:
    il riferimento non c'e' (le cinque funzioni qui sopra), oppure il TIPO
    non e' fra quelli che HIRIS sa aprire -- e allora esce anche
    `non_so_guardare: True`, perche' una scena o un gruppo che `legami()`
    ha appena mostrato esistono eccome, e dirne «non esiste» sarebbe una
    risposta sbagliata detta con sicurezza.

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

    `da_quando_vive` (entity_id -> `last_changed` dallo specchio dello stato,
    stessa forma di `unita_vive`/`classi_vive`) accompagna OGNI `"stato"` che
    esce da questa funzione: il campo che Home Assistant manda a ogni cambio
    di stato e che la proiezione della cache scartava (fondamenta 3 -- la
    stessa domanda non puo' avere due risposte diverse a seconda di quale
    ramo di `guarda` la porta).

    `attributi_vivi` (entity_id -> il dizionario `attributes` dello specchio
    dello stato, `_DOMAIN_ATTRS` di `proxy/entity_cache.py`: `hvac_action` e
    la temperatura di un termostato, la luminosita' di una luce, la
    posizione di una tapparella, ...) alimenta DUE cose diverse, e non allo
    stesso modo:

    - `stato_leggibile` lo legge SEMPRE, su ogni ramo che elenca entita'
      (dentro `_arricchisci_entita`), perche' e' un campo che gia' usciva
      ovunque e che per un termostato mentiva da solo -- vedi
      `anagrafe.traduci_stato`. Il difetto misurato dal proprietario
      (2026-08-25): `hvac_mode: heat` con `hvac_action: idle` usciva come
      «heat», indistinguibile da un termostato che sta scaldando davvero.
    - Il dizionario `attributi` INTERO esce solo dal ramo `entita` (decisione
      del proprietario): un'area o un dispositivo elencano entita' a decine,
      e mettere tutti gli attributi di ognuna dentro quegli elenchi
      gonfierebbe la risposta di un dato che nessuno ha chiesto per la
      singola cosa. Il dettaglio di UNA entita' e' il momento in cui il
      modello ha gia' chiesto quella cosa precisa, e l'informazione si paga
      solo li'.

    Pura: legge `casa`/`comportamento`/`ricordi`/`stato` cosi' come arrivano
    dal chiamante (`ArchivioCasa`, `ArchivioMemoria`, lo stato vivo di Home
    Assistant), non apre archivi ne' chiama la rete.

    C-2 (L1-sicurezza.md): il testo di un ricordo passa dal sanitizzatore
    UNA volta, qui, prima di qualunque ramo -- per id diretto
    (`_guarda_ricordo`), ancorato a un'area/entita'/dispositivo
    (`_ricordi_ancorati`, dentro i tre rami sopra) o ancorato a
    un'automazione/script (`_guarda_comportamento`). Un punto solo, non uno
    per ramo: la fondamenta 3 (consistenza fra porte) e' anche questo -- lo
    stesso ricordo non deve poter uscire filtrato da una via e grezzo da
    un'altra. Il testo ARCHIVIATO non cambia (`memoria/archivio.py`, regola
    1): questa e' una copia, non una riscrittura.
    """
    ricordi = ricordi_sanificati(ricordi)
    if tipo == "area":
        return _guarda_area(casa, ricordi, stato, riferimento, non_disponibili,
                            nomi_di_ripiego, unita_vive, classi_vive, da_quando_vive,
                            attributi_vivi)
    if tipo == "entita":
        return _guarda_entita(casa, ricordi, stato, riferimento, non_disponibili,
                              nomi_di_ripiego, unita_vive, classi_vive, da_quando_vive,
                              attributi_vivi)
    if tipo == "dispositivo":
        return _guarda_dispositivo(casa, ricordi, stato, riferimento, non_disponibili,
                                   nomi_di_ripiego, unita_vive, classi_vive, da_quando_vive,
                                   attributi_vivi)
    if tipo in _TIPI_COMPORTAMENTO:
        return _guarda_comportamento(comportamento, ricordi, tipo, riferimento, file_non_letti)
    if tipo == "ricordo":
        return _guarda_ricordo(ricordi, riferimento)
    # Un tipo che non conosciamo non e' un errore da sollevare: e' lo
    # stesso caso di "non l'ho trovato", solo con una causa diversa (il
    # modello ha nominato un tipo che non esiste, non un riferimento che
    # manca) -- e va dichiarato con la stessa onesta', non con un'eccezione
    # che gli spezza il turno.
    #
    # `non_so_guardare`: la causa e' un LIMITE DI HIRIS, non un fatto sulla
    # casa, e da quando esistono i legami quella differenza costa. `legami`
    # restituisce identificatori veri di cose vere -- una scena, un gruppo,
    # una persona -- che `guarda` non sa aprire: senza questa chiave il
    # modello chiedeva `guarda("scena", ...)`, leggeva `esiste: false` e
    # riferiva all'utente «quella scena non esiste», che e' una risposta
    # sbagliata detta con sicurezza su una cosa che Home Assistant gli aveva
    # appena mostrato. Stessa disciplina di `non_disponibile`: «non l'ho
    # trovato» e «non ho potuto guardare» sono due fatti diversi.
    return {"esiste": False, "tipo": tipo, "riferimento": riferimento,
            "non_so_guardare": True}


def legami(risposta: dict, tipo: str, riferimento) -> dict:
    """Chi tocca questa cosa, nella forma che il modello legge.

    Prende la risposta GIA' ottenuta da `HAClient.legami()` -- questa
    funzione e' pura come le altre due, la rete la fa il chiamante
    (`casa/strumenti.py`) -- e fa tre cose sole: distingue il guasto dal
    niente, traduce i tipi nel vocabolario di HIRIS, e ordina.

    **Il guasto non e' un «niente».** `legami: {}` e' un'affermazione:
    «questa cosa non la tocca nessuno e non sta da nessuna parte». Se Home
    Assistant non ha risposto, quell'affermazione nessuno ha il diritto di
    farla, e la risposta esce con `errore` -- una chiave diversa, non un
    elenco piu' corto. E' lo stesso principio con cui `HAClient.legami`
    rifiuta di restituire `{}` su un rifiuto, portato fino al modello: un
    guasto dichiarato al client e appiattito qui sarebbe un guasto taciuto.

    **La traduzione.** Le chiavi arrivano come le manda Home Assistant
    (`entity`, `automation`, ...) ed escono come le nomina HIRIS (`entita`,
    `automazione`): sono gli stessi nomi di `cerca` e di `guarda`, cosi' un
    `riferimento` letto qui si passa di li' senza tradurlo a mano -- e senza
    che il modello debba imparare due vocabolari per la stessa casa
    (fondamenta: consistenza). Una chiave che Home Assistant aggiungesse
    domani e che questa tabella non conosce passa COSI' COM'E': un nome non
    tradotto e' un fastidio, una riga buttata sarebbe una perdita silenziosa.

    **Cosa questa funzione NON fa: raggruppare.** Per un'entita' la risposta
    di Home Assistant mescola chi la USA (automazioni, script, scene, gruppi,
    persone) con dove STA (area, dispositivo, piano, integrazione) --
    verificato sul sorgente, `_async_search_entity` fa entrambe le cose. La
    tentazione e' dividerle in due gruppi, ma il significato delle stesse
    chiavi cambia col tipo chiesto: per un'AREA le entita' elencate sono cio'
    che l'area contiene, non dove l'area sta. Un raggruppamento fisso sarebbe
    giusto per un tipo e falso per gli altri, quindi non si raggruppa: si
    lascia la struttura di Home Assistant e si spiega al modello (nella
    descrizione dello strumento) come leggerla.
    """
    if not isinstance(risposta, dict) or "errore" in risposta:
        motivo = (risposta.get("errore") if isinstance(risposta, dict)
                  else "risposta in forma inattesa")
        return {"errore": (
            f"non ho potuto sapere chi tocca «{riferimento}»: {motivo}. "
            "Non e' un «non la tocca nessuno»: e' una domanda a cui Home "
            "Assistant non ha risposto, e il legame potrebbe esserci.")}
    tradotti = {NOME_LEGAME.get(chiave, chiave): list(valori)
                for chiave, valori in risposta.items()}
    # Ordinate per nome: Home Assistant manda un dizionario costruito da
    # insiemi, e due letture identiche produrrebbero due risposte con le
    # chiavi in ordine diverso. I VALORI li ordina gia' il client, e per la
    # stessa ragione.
    return {"tipo": tipo, "riferimento": riferimento,
            "legami": {nome: tradotti[nome] for nome in sorted(tradotti)}}
