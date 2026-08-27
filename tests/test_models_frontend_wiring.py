import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"

def test_models_route_js_exists_and_exposes_mount():
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    assert "HirisModelsRoute" in js and "mount" in js
    assert "api/models/config" in js

def test_config_html_includes_script_and_nav():
    html = (BASE / "config.html").read_text(encoding="utf-8")
    assert "config/models-route.js" in html
    assert 'data-route="models"' in html

def test_main_js_registers_route():
    js = (BASE / "config" / "main.js").read_text(encoding="utf-8")
    assert "#/models" in js
    assert "'models'" in js  # updateNavActive branch

def test_models_route_ha_due_sezioni_e_una_riga_in_fondo():
    # fetta «la catena e' l'unica verita'» (Task 8): le sezioni erano tre --
    # «Provider e credenziali», «Catena automatica», «Embeddings» -- e le prime
    # due erano DUE RAPPRESENTAZIONI DELLA STESSA COSA (un elenco di provider
    # con un badge di stato, e una catena ricostruita a parte). Fuse in una, la
    # divergenza fra le due e' impossibile per costruzione.
    #
    # Cerchiamo i titoli come LETTERALI passati a buildSectionShell (virgolette
    # dritte), non come prosa nei commenti che spiegano la rimozione (quelli
    # usano virgolette tipografiche): il file continua a *parlare* delle
    # sezioni uscite, ma non le *rende* piu'.
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    assert "'La catena'" in js
    assert "'Fuori dalla catena'" in js
    assert "'Provider e credenziali'" not in js
    assert "'Provider attivi'" not in js
    assert "'Catena automatica'" not in js
    assert "'Assegnazione entita''" not in js
    # Gli embedding restano dichiarati, ma NON come sezione numerata: la
    # numerazione, in questa pagina, significa «qui si decide qualcosa», e gli
    # embedding non decidono niente (progetto §8). Erano la sezione «03».
    assert "'Embeddings (oggi inattivi)'" not in js
    assert "'nota-embedding'" in js
    assert "nessun testo viene vettorizzato" in js
    # E il blocco «03 QUANDO NON DECIDE LA CATENA» del progetto §3 non si
    # disegna: il campo che scavalcava la catena e' uscito col Task 4, e un
    # avviso per uno stato irraggiungibile e' l'esatto contrario del principio
    # di questa pagina.
    assert "QUANDO NON DECIDE" not in _codice_senza_commenti(js).upper()


def test_models_route_puts_full_config_object():
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    # Every write to /api/models/config must send the full {chain_order,
    # provider_models} object (never a partial patch) -- the backend
    # replaces the whole file on PUT. La sezione "Assegnazione per entità",
    # che scriveva anche su api/chatbots/{id}, è uscita alla fetta E5 Task 7:
    # l'unico endpoint di scrittura rimasto in questo file è
    # api/models/config. Cerchiamo la CHIAMATA letterale (non "api/chatbots"
    # come sottostringa, che comparirebbe anche nei commenti che spiegano la
    # rimozione).
    assert "JSON.stringify(state.cfg)" in js
    assert "api('api/chatbots/'" not in js
    assert "fetch('api/chatbots')" not in js

def test_la_pagina_riceve_la_frase_e_non_la_compone():
    """L'invariante 2 della spec, guardato dal lato del file: la pagina legge
    `adesso.frase`, e non c'è nessuna composizione di frase in JS.

    La prima forma di questo test era `assert "state.adesso.frase" in js`, e
    una prova per mutazione l'ha vista SOPRAVVIVERE: sostituendo la riga che
    disegna la frase con una stringa scritta a mano, la sottostringa restava
    comunque nel file (la usa anche la guardia `if (!state.adesso ||
    !state.adesso.frase)`). Quindi qui si pinna l'ESPRESSIONE CHE DISEGNA, non
    una sottostringa che può vivere altrove.
    """
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    assert "el('p', 'adesso-frase', state.adesso.frase)" in js, (
        "la frase a schermo dev'essere quella del backend, non una composta qui"
    )
    assert "adesso-card" in js
    # Le parole del prodotto stanno in `decisione_modelli.componi_adesso` e in
    # nessun altro posto: se l'incipit della frase ricompare nel frontend,
    # esistono due file che affermano cose sul prodotto (invariante 3).
    assert "Il prossimo messaggio va a" not in js


def test_la_pagina_legge_le_due_liste_e_non_piu_gli_ingredienti():
    """Il payload non porta piu' `providers[]` (l'appartenenza detta una
    seconda volta accanto a `catena`/`fuori_catena`) ne' `llm_strategy` (il
    preset letto dall'ambiente accanto a `strategia_ultima` letto
    dall'archivio). Se il file continuasse a leggerli, leggerebbe `undefined` e
    disegnerebbe una pagina vuota mentre la catena lavora -- cioe' esattamente
    il difetto che questa fetta esiste per chiudere, con i campi al contrario.

    Il test guarda il FILE e non il DOM perche' cio' che pinna e' il contratto
    fra due processi (payload <-> pagina), che nessun test JS puo' rompere: la
    finta del test JS porta i campi che le si danno."""
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    assert "cfgRaw.catena" in js
    assert "cfgRaw.fuori_catena" in js
    assert "cfgRaw.providers" not in js
    assert "cfgRaw.llm_strategy" not in js
    assert "cp.in_catena" not in js
    assert "p.in_catena" not in js
    assert "cp.active" not in js
    assert "cp.toggle" not in js


def _codice_senza_commenti(js: str) -> str:
    """Il file MENO i commenti. I commenti di questo file citano apposta le
    scritture vietate («non c'e' nessun `if (dati.id === "subscription")` qui,
    ed e' deliberato»): un test che le cercasse nel testo intero non potrebbe
    mai passare, e uno che le cercasse riga per riga cadrebbe sulle righe
    interne di un commento di blocco."""
    senza = re.sub(r"/\*.*?\*/", "", js, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", senza, flags=re.MULTILINE)


def test_la_pagina_non_conosce_il_caso_del_piano_ma_obbedisce_a_un_campo():
    """L'invariante 2 nel punto in cui e' piu' facile romperlo. I gesti che
    scrivono `chain_order` -- entrare, uscire, salire, scendere -- si disegnano
    dove il backend dice `riordinabile`, e in nessun altro modo. Un
    `if (id === 'subscription')` qui dentro sarebbe una regola del prodotto
    scritta una seconda volta, in un altro linguaggio, libera di divergere da
    `componi_topologia` -- che e' la forma esatta del difetto di questa fetta.

    I due test JS gemelli (OpenRouter non riordinabile) provano il
    COMPORTAMENTO; questo impedisce la scrittura che li farebbe passare per la
    ragione sbagliata su un altro provider."""
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    corpo = _codice_senza_commenti(js)
    assert "dati.riordinabile" in corpo
    for sospetta in ("=== 'subscription'", '=== "subscription"',
                     "!== 'subscription'", ".subscription"):
        assert sospetta not in corpo, (
            "la pagina non deve riconoscere il piano per id: obbedisce a un campo"
        )
    # L'unico posto in cui la parola compare e' l'ordine di «Fuori dalla
    # catena», che e' un ordine di visualizzazione e non una regola: e' pinnato
    # contro il backend dal test qui sotto.
    assert corpo.count("subscription") == 1


def test_le_parole_del_prodotto_non_vivono_nella_pagina():
    """Nomi, nature, che cosa manca, cosa succede se un anello non risponde:
    sono affermazioni sul prodotto e stanno in `decisione_modelli`, dove si
    pinnano. Scritte anche qui sarebbero due file che affermano la stessa cosa,
    e il giorno in cui la regola cambia (il ponte che impara a ripiegare, Task
    14) uno dei due resterebbe a dire quella di ieri -- senza che nessun test
    se ne accorga, perche' a schermo la frase ci sarebbe lo stesso."""
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    corpo = _codice_senza_commenti(js)
    for parola in ("Piano Claude Max", "Claude API", "manca la chiave",
                   "manca il token", "a consumo", "nel piano",
                   "se rifiuta, subito", "ultimo della catena",
                   # Task 11: le parole dell'ESITO OSSERVATO. Il Task 14
                   # riscrive proprio queste (il ripiego dal ponte alla
                   # catena) e la sua promessa e' che il frontend non venga
                   # toccato: se una di queste vivesse anche qui, quel giorno
                   # la pagina direbbe la frase di ieri e nessun test JS
                   # cambierebbe -- il silenzio che questa fetta esiste per
                   # togliere.
                   "ha rifiutato", "ha risposto", "credito esaurito",
                   "non l'hai ancora usato", "ripiegare qui",
                   "non risponde all'indirizzo", " min fa", " h fa"):
        assert parola not in corpo, (
            f"«{parola}» e' una parola del prodotto: viene dal payload"
        )
    assert "dati.connettore" in corpo
    assert "dati.manca" in corpo
    assert "dati.nota" in corpo
    assert "dati.stato_testo" in corpo


def test_la_parola_attivo_non_torna_da_nessuna_porta():
    """Invariante 3. «Attivo» significa «interruttore acceso e credenziale
    presente» e si legge «funziona»: una chiave a credito esaurito era
    «Attivo». La parola non deve poter tornare da nessuna porta -- e questo
    file era l'ultima che restava aperta. I badge che la portavano sono usciti
    con la sezione che li disegnava: quello che resta a schermo e' la catena,
    dove stare dentro o fuori e' una posizione, non un aggettivo."""
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    assert "'Attivo'" not in js
    assert "'Disattivato'" not in js
    assert "agent-badge" not in js
    assert "'Fuori dalla catena'" in js


def test_l_ordine_fisso_del_frontend_e_quello_del_backend():
    """Due liste con lo stesso nome in due linguaggi sono la miniatura del
    difetto che questa fetta chiude. Non si possono fondere (il frontend non
    importa Python), ma si possono tenere legate da un test che si rompe."""
    from hiris.app.decisione_modelli import ORDINE_FISSO
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    atteso = "var ORDINE_FISSO = [" + ", ".join(f"'{p}'" for p in ORDINE_FISSO) + "];"
    assert atteso in js, f"atteso in models-route.js: {atteso}"


def test_i_tre_preset_del_frontend_sono_quelli_del_router():
    """Stessa ragione: i tre ordini esistono due volte. Un preset che
    riscrivesse la catena in un ordine diverso da quello del router
    prometterebbe un comportamento che il prodotto non ha."""
    from hiris.app.llm_router import _STRATEGY_ORDER
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    for chiave, ordine in _STRATEGY_ORDER.items():
        atteso = "ordine: [" + ", ".join(f"'{p}'" for p in ordine) + "]"
        assert atteso in js, f"{chiave}: atteso {atteso} in models-route.js"


def test_il_pannello_non_conosce_i_casi_particolari_ma_obbedisce_a_un_percorso():
    """Il gemello di `test_la_pagina_non_conosce_il_caso_del_piano`, sul pezzo
    piu' nuovo. Il modello di Ollama NON vive in `provider_models`
    (`_PROVIDER_MODEL_KEYS` non lo contiene: quella chiave e' un fantasma,
    scartata in lettura E in scrittura) e il piano non ha nessun posto in cui
    salvarlo. Scritte qui, quelle due regole vivrebbero una seconda volta in un
    altro linguaggio, libere di divergere: il pannello riceve un PERCORSO e lo
    applica alla cieca.

    I QUATTRO id compaiono nel codice esattamente quattro volte ciascuno, e
    sono le due liste che il prodotto tiene legate al backend da un test
    (`ORDINE_FISSO`, una volta; i tre preset, tre volte). Un quinto sarebbe un
    caso particolare riconosciuto per nome -- ed e' cosi' che il difetto di
    questa fetta rientrerebbe."""
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    corpo = _codice_senza_commenti(js)
    assert "dati.dove" in corpo
    assert "scriviPercorso" in corpo and "leggiPercorso" in corpo
    for pid in ("'claude'", "'openrouter'", "'openai'", "'ollama'"):
        assert corpo.count(pid) == 4, (
            f"{pid} compare {corpo.count(pid)} volte: le sole citazioni ammesse "
            "sono ORDINE_FISSO (1) e i tre preset (3), entrambi pinnati contro "
            "il backend"
        )


def test_le_parole_del_pannello_non_vivono_nella_pagina():
    """Provenienza, spiegazione e «da quando ha effetto» sono affermazioni sul
    prodotto e cambiano con lui: la provenienza dipende da un fatto misurato
    adesso, e la didascalia di `quando` sparira' con la scrittura a caldo
    (Task 10) senza che nessuno tocchi questo file. Scritte qui resterebbero a
    dire quella di ieri, e a schermo la frase ci sarebbe lo stesso."""
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    corpo = _codice_senza_commenti(js)
    for parola in ("Letti da", "Elenco di riserva", "riavvio dell'add-on",
                   "Anthropic", "openrouter.ai", "api.openai.com",
                   "nascondi i gratuiti", "il piu' rapido"):
        assert parola not in corpo, (
            f"«{parola}» e' una parola del prodotto: viene dal payload"
        )
    assert "dati.provenienza" in corpo
    assert "dati.spiegazione" in corpo
    assert "dati.quando" in corpo
    assert "casella.etichetta" in corpo


def test_la_pagina_legge_l_elenco_dei_modelli_solo_all_apertura_del_pannello():
    """Quella rotta interroga davvero OpenAI, OpenRouter e Ollama con cinque
    secondi di pazienza ciascuno. Fino al Task 8 la pagina la leggeva a ogni
    caricamento per un risultato che nessuno guardava; adesso si legge un
    provider alla volta, quando il pannello si apre -- ed e' anche cio' che
    rende vera la parola «letti adesso»."""
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    corpo = _codice_senza_commenti(js)
    assert "fetch('api/models')" not in corpo, (
        "la lettura completa al caricamento e' uscita col pannello"
    )
    assert "'api/models?provider=' + encodeURIComponent(idProvider)" in corpo


def test_il_modello_e_un_bottone_e_non_uno_span_con_un_listener():
    """Si clicca: deve essere raggiungibile da tastiera come le frecce, e
    annunciare che apre e chiude qualcosa. Uno `<span>` con un listener e' un
    controllo invisibile a chi non usa il mouse."""
    js = (BASE / "config" / "models-route.js").read_text(encoding="utf-8")
    corpo = _codice_senza_commenti(js)
    assert "var modello = el('button'," in corpo, (
        "uno <span> con un listener supera ogni test JS -- jsdom esegue il "
        "click lo stesso -- e non e' raggiungibile da tastiera: la differenza "
        "si vede solo guardando il file"
    )
    assert "aria-expanded" in corpo
