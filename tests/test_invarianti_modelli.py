"""Cose che questo disegno rende vere e che possono tornare false senza che
nessuno tocchi la pagina Modelli.

Questo file non prova un comportamento nuovo: prova che il terreno sotto la
fetta «la catena e' l'unica verita'» resti quello. Ogni test qui dentro
corrisponde a un invariante della specifica (§7) o a un debito dichiarato nel
registro dei quattordici task precedenti, e ha una sola ragione di esistere: il
difetto che chiude non lascia traccia in nessun altro test.

Due di questi test leggono un `.css`. Fino a oggi **nessun test di questo repo
toccava un foglio di stile** (debito Task 2 -> 15, ridichiarato dai Task 8, 9 e
11): il CSS della pagina Modelli non l'ha mai visto un browser e jsdom non
calcola il layout. Questi due non sostituiscono la prova sulla casa vera --
`docs/prova-modelli-e-catena.md` la chiede esplicitamente -- ma chiudono la
meta' che si puo' chiudere da qui: che il nome della classe scritta nel JS
esista nel CSS, e che i blocchi a tutta larghezza continuino a dichiararsi tali.
"""
import re
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1] / "hiris"
STATIC = BASE / "app" / "static"
MODELS_JS = STATIC / "config" / "models-route.js"
CONFIG_HTML = STATIC / "config.html"


def _righe_vive_js(p: Path) -> str:
    """Il sorgente senza commenti. Serve perche' i commenti di questo ramo
    CITANO le parole ritirate per spiegare perche' sono uscite: cercarle nel
    file intero renderebbe il test impossibile da soddisfare senza cancellare
    la memoria del difetto."""
    testo = p.read_text(encoding="utf-8")
    testo = re.sub(r"/\*.*?\*/", "", testo, flags=re.DOTALL)
    return "\n".join(r for r in testo.splitlines() if not r.lstrip().startswith("//"))


# ── Invariante 3: nessuna parola che affermi piu' di cio' che il sistema sa ──

@pytest.mark.parametrize("parola", ["Attivo", "Disattivato", "Disponibile", "Funzionante"])
def test_nessuna_parola_afferma_piu_di_cio_che_il_sistema_sa(parola):
    """Invariante 3 della spec. «Attivo» significa «interruttore acceso e
    credenziale presente» e si legge «funziona»: una chiave a credito esaurito
    era «Attivo». Cio' che si afferma dev'essere cio' che si e' misurato.

    Il confine di parola non e' un dettaglio: `state.ponteAttivo` contiene la
    sequenza «Attivo» e non e' una parola a schermo, e' il nome di un campo del
    payload. Cercare la sottostringa renderebbe questo test rosso oggi, cioe'
    inutile domani -- e la lezione di questa fetta e' che un test che non puo'
    passare e uno che non puo' fallire sono lo stesso errore.
    """
    vive = _righe_vive_js(MODELS_JS)
    trovate = re.findall(r"\b" + parola + r"\b", vive)
    assert not trovate, (
        f"«{parola}» e' una parola ritirata dal prodotto: e' comparsa "
        f"{len(trovate)} volte in righe vive di models-route.js"
    )


# ── L'invariante che regge tutto il disegno: la chat non fa streaming ───────

def test_la_chat_non_fa_streaming_e_quindi_la_catena_e_onesta():
    """Invariante che regge TUTTO il disegno (progetto §0.1 e §14.1):
    `llm_router.chat` cicla la catena, `chat_stream` NO -- prende il primo e
    basta. La chat di HIRIS non fa streaming (`static/chat/send.js` fa un POST
    JSON e legge `r.json()`), quindi il ramo SSE e' raggiungibile solo da un
    client API esterno. Il giorno in cui la chat chiedesse SSE, il ripiego
    sparirebbe e questa pagina inizierebbe a mentire SENZA CHE NESSUNO LA
    TOCCHI.

    E non solo la pagina: dal Task 11 `chat_stream` non scrive nel registro
    degli esiti, e dal Task 14 il ramo streaming non porta la nota del ripiego
    (nessun payload JSON in cui metterla). Passare la chat allo streaming
    costerebbe insieme il ripiego, il registro e l'annuncio -- tre promesse
    fatte all'utente in questa versione."""
    send = (STATIC / "chat" / "send.js").read_text(encoding="utf-8")
    assert "text/event-stream" not in send
    assert "stream: true" not in send and "stream:true" not in send


# ── Invariante 4: una sola regola di instradamento ─────────────────────────

def test_non_esiste_una_seconda_regola_di_instradamento():
    """Invariante 4 del progetto. `llm_router.simple_chat` sceglieva con
    `self._claude or self._openai or self._ollama` -- OpenRouter escluso,
    nessun ripiego, catena ignorata. E' uscita col Task 7; questo test e' la
    ragione per cui non puo' rientrare in silenzio (ci ha gia' provato tre
    volte da altre porte: il ripiego di `_norm_policy`, il `or r._chat_policy`
    del brief del Task 10, e il ripiego di strategia a catena vuota)."""
    router = (BASE / "app" / "llm_router.py").read_text(encoding="utf-8")
    assert "def simple_chat" not in router


# ── Invariante 2: la pagina non calcola la topologia ───────────────────────

# MISURATO, non indovinato (Task 15, Step 2). Dopo i Task 8-9-14 le letture
# vive della credenziale in `models-route.js` sono SEI, e sono queste:
#   rigaProvider        3  -- il pallino, la colonna «natura»/«manca», e il
#                             gesto «Usa» che non si offre senza credenziale
#   renderFuori         1  -- la nota «le chiavi si mettono in Configurazione
#                             add-on», scritta una volta se manca a qualcuno
#   ricomponiTopologia  1  -- LA DEROGA: riordina righe GIA' COMPOSTE dal
#                             backend fra il gesto e la risposta del server
#   rifaiCatena         1  -- i preset compongono un `chain_order` da MANDARE,
#                             e non mandano chi non puo' rispondere
# Il numero e' un limite superiore: serve a far scattare un test quando qualcuno
# ne aggiunge una settima, che e' il modo in cui il difetto 3 tornerebbe.
_LETTURE_VIVE_DELLA_CREDENZIALE = 6

# Le quattro funzioni che possono leggerla. Questo e' il pin che conta davvero:
# il conteggio dice QUANTE, questo dice DOVE -- e una settima lettura dentro una
# `render*` qualunque sarebbe topologia ricalcolata nel frontend anche se il
# totale restasse sei perche' qualcuno ne ha tolta un'altra.
_FUNZIONI_CHE_LEGGONO_LA_CREDENZIALE = {
    # I nomi sono passati all'inglese il 02/09 (fetta del frontend): sono le
    # STESSE quattro funzioni, non quattro funzioni nuove -- `rigaProvider`,
    # `renderFuori`, `ricomponiTopologia`, `rifaiCatena`. Il pin e' sopravvissuto
    # alla rinomina facendo il suo mestiere: ha nominato le quattro nuove e
    # chiesto conto della differenza, invece di passare perche' il CONTEGGIO
    # era rimasto quattro.
    "providerRow", "renderOutside", "recomposeLayout", "redoChain",
}


def _letture_per_funzione(sorgente: str) -> dict[str, int]:
    """Le funzioni di primo livello dell'IIFE e quante volte ognuna nomina la
    credenziale. Il file e' scritto tutto con `function nome(` (stile ES5 del
    ramo, vincoli globali): la divisione sul sorgente vivo e' esatta quanto
    serve a questo test."""
    parti = re.split(r"\n\s*function\s+(\w+)\s*\(", sorgente)
    assert parti[0].count("ha_credenziale") == 0, (
        "una lettura della credenziale fuori da ogni funzione: e' codice di "
        "modulo, gira al caricamento e nessuno puo' prevederne il momento"
    )
    return {
        parti[i]: parti[i + 1].count("ha_credenziale")
        for i in range(1, len(parti), 2)
        if parti[i + 1].count("ha_credenziale")
    }


def test_la_pagina_non_contiene_la_regola_della_catena():
    """Invariante 2 della spec: se un test trova logica di ordinamento nel
    frontend, il difetto 3 e' tornato per un'altra porta.

    L'UNICA deroga e' `ricomponiTopologia`, che riordina righe GIA' COMPOSTE dal
    backend usando l'ordine che l'utente ha appena espresso, fra un gesto e la
    risposta del server."""
    js = _righe_vive_js(MODELS_JS)
    assert "buildDisplayChain" not in js
    assert "has_credential" not in js, (
        "il nome inglese del campo non esiste piu' nel payload dal Task 7: "
        "trovarlo qui vuol dire che qualcuno legge una seconda superficie"
    )
    quante = js.count("ha_credenziale")
    assert quante <= _LETTURE_VIVE_DELLA_CREDENZIALE, (
        f"l'appartenenza si decide nel backend: {quante} letture della "
        f"credenziale nel frontend, il massimo misurato e' "
        f"{_LETTURE_VIVE_DELLA_CREDENZIALE}"
    )


def test_solo_quattro_funzioni_della_pagina_leggono_la_credenziale():
    """Il gemello del precedente, e il piu' severo dei due: il conteggio dice
    quante letture, questo dice IN QUALI FUNZIONI. Una lettura dentro una
    `render*` nuova sarebbe topologia ricalcolata nella pagina anche a totale
    invariato."""
    dove = _letture_per_funzione(_righe_vive_js(MODELS_JS))
    assert set(dove) == _FUNZIONI_CHE_LEGGONO_LA_CREDENZIALE, (
        f"le funzioni che leggono la credenziale sono cambiate: {sorted(dove)}"
    )


# ── I token semantici del testo, e il resto del CSS che nessuno guardava ────

def _fogli_della_pagina_config() -> list[Path]:
    """I fogli che `config.html` carica davvero, letti da li' e non elencati a
    mano: un foglio aggiunto alla pagina e non a questa lista renderebbe i due
    test qui sotto ciechi proprio sul codice nuovo."""
    html = CONFIG_HTML.read_text(encoding="utf-8")
    nomi = re.findall(r'href="static/([\w.-]+\.css)"', html)
    fogli = [STATIC / n for n in nomi]
    assert fogli, "config.html non carica nessun foglio di stile: forma cambiata"
    for f in fogli:
        assert f.exists(), f"config.html carica un foglio che non esiste: {f.name}"
    return fogli


def test_il_testo_semantico_usa_i_token_ink():
    """`hiris-theme.css` righe 76-82: `--x-ink` per il testo, `--x` per
    pallini, bordi e riempimenti. Secondo l'audit pre-UAT `models-route.js` era
    l'unica superficie rimasta indietro; dopo i Task 8-11-14 le sue regole sono
    trenta e nessun test le guardava."""
    css = (STATIC / "hiris-config.css").read_text(encoding="utf-8")
    regole = re.findall(r"\.(?:adesso|riga|connettore)[^{]*\{[^}]*\}", css)
    assert len(regole) >= 20, (
        f"attese almeno venti regole della pagina Modelli, trovate "
        f"{len(regole)}: la forma del file e' cambiata e questo test sta "
        f"guardando altro"
    )
    for regola in regole:
        for token in ("--ok", "--warn", "--err"):
            assert f"color: var({token})" not in regola, (
                f"testo su var({token}): la regola d'uso vuole var({token}-ink). "
                f"{regola[:80]}")


# I nomi che la pagina scrive e che NON hanno (ne' devono avere) una regola
# propria. Sono di due specie sole, e la lista e' corta apposta: una lista di
# eccezioni che cresce e' il segno che questo test ha smesso di misurare
# qualcosa.
#
#   * gli ID dei quattro contenitori (`byId`), che sono agganci di struttura --
#     il loro aspetto viene dalla classe che portano (`sc-body`,
#     `section-card`), non dal loro nome;
#   * i quattro agganci sui bottoni gia' vestiti da `btn btn-ghost btn-sm`, che
#     esistono per i test e per `querySelector`, non per il foglio.
_CLASSI_SENZA_REGOLA_PER_SCELTA = {
    "catena-body", "catena-card", "fuori-body", "route-outlet",
    "riga-usa", "riga-su", "riga-giu", "riga-esci",
}


def _classi_disegnate_dalla_pagina() -> set[str]:
    """Ogni nome che somiglia a una classe, dalle righe vive -- non solo il
    secondo argomento LETTERALE di `el(`.

    **G3 della revisione finale.** La versione precedente leggeva solo
    `el(...tag..., ...classi...)`, e in questa pagina le classi che contano non si
    scrivono cosi': sono composte con un ternario
    (`'riga-provider' + (dentro ? '' : ' riga-fuori')`) o passate come
    variabile a un wrapper (`connettore('connettore-nota', …)`). Erano
    invisibili al test che prometteva di coprirle: cancellando cinque regole
    dal foglio -- `.riga-muta`, `.stato-rifiutato`, `.modello-alias`,
    `.voce-alias`, `.riga-fuori`, cioe' la traduzione grafica del ritiro della
    parola «Attivo» e la tipografia alias-contro-identificatore -- restavano
    trentaquattro test verdi. Non era un test che non poteva fallire in
    assoluto: era un test che non poteva fallire proprio dove il suo nome
    prometteva che sarebbe fallito, che per la dottrina di questa fetta e' lo
    stesso errore.

    Il criterio adesso e' la FORMA del nome invece della posizione: si prende
    ogni letterale a singolo apice fatto di soli nomi in kebab-case, e da
    quello si tengono i pezzi che contengono un trattino. Il trattino e' cio'
    che distingue un nome di classe di questa pagina da un tag (`div`), da un
    ruolo (`list`, `listitem`), da un id di provider (`claude`) e da un valore
    (`polite`, `balanced`). Restano fuori, per costruzione dichiarata, i nomi
    di classe SENZA trattino passati come variabile -- oggi uno solo,
    `connettore`, la cui gemella `connettore-nota` e' invece coperta."""
    js = _righe_vive_js(MODELS_JS)
    classi: set[str] = set()
    for letterale in re.findall(r"'([^']*)'", js):
        pezzi = letterale.split()
        if pezzi and all(re.fullmatch(r"[a-z][a-z0-9-]*", p) for p in pezzi):
            classi.update(p for p in pezzi if "-" in p)
    classi.update(re.findall(r"classList\.add\('([^']+)'\)", js))
    # I prefissi composti a runtime (`'diagnosi-' + gravita`) non sono classi:
    # il loro suffisso arriva dal backend e questo test non puo' conoscerlo.
    # E i nomi di attributo (`aria-live`, `data-provider`) hanno la forma di una
    # classe e non lo sono: e' l'unica famiglia che il criterio non separa da
    # sola, e si toglie con una regola, non con un elenco.
    return {c for c in classi
            if not c.endswith("-") and not c.startswith(("aria-", "data-"))}


def test_ogni_classe_che_la_pagina_disegna_ha_una_regola_nel_css():
    """Il difetto che questo test coglie e' l'unico difetto di CSS che si possa
    cogliere senza un browser: il nome scritto in due posti e cambiato in uno
    solo. Non prova che il layout regga -- quello lo prova solo la casa vera
    (`docs/prova-modelli-e-catena.md`, prova 1) -- ma prova che il foglio e la
    pagina parlino della stessa cosa.

    E' il primo test di questo repo che apre un `.css`. Fino al Task 14 il
    registro lo ha dichiarato quattro volte come debito aperto."""
    # I COMMENTI si tolgono. I fogli di questo ramo CITANO i nomi delle classi
    # per spiegare le regole (`.modello-alias` compare in un commento di
    # `hiris-config.css`), e una citazione non veste niente: cercare nel testo
    # grezzo faceva passare per «vestita» una classe la cui unica traccia era
    # la spiegazione di una regola cancellata. E' la gemella esatta di
    # `_righe_vive_js`, per il foglio invece che per il sorgente.
    css = re.sub(
        r"/\*.*?\*/", "",
        "\n".join(f.read_text(encoding="utf-8") for f in _fogli_della_pagina_config()),
        flags=re.DOTALL,
    )
    orfane = sorted(
        c for c in _classi_disegnate_dalla_pagina()
        if c not in _CLASSI_SENZA_REGOLA_PER_SCELTA
        and not re.search(r"\." + re.escape(c) + r"(?![\w-])", css)
    )
    assert not orfane, (
        f"la pagina disegna classi che nessun foglio veste: {orfane}. "
        f"O manca la regola, o il nome e' cambiato in un posto solo"
    )


# I tre blocchi che occupano l'intera riga dentro la griglia della
# `.riga-provider`. La griglia ha SEI colonne in largo e QUATTRO sotto i 640px:
# `1 / -1` e' scritto cosi' apposta, perche' regga in tutte e due. Un blocco che
# perdesse questa riga si schiaccerebbe dentro una colonna -- e jsdom non se ne
# accorgerebbe mai.
_BLOCCHI_A_TUTTA_LARGHEZZA = ("riga-nota", "riga-stato", "pannello-modello")


@pytest.mark.parametrize("classe", _BLOCCHI_A_TUTTA_LARGHEZZA)
def test_i_blocchi_a_tutta_larghezza_restano_a_tutta_larghezza(classe):
    """Task 8 -> 15, Task 9 -> 15, Task 11 -> 15: «terzo blocco a tutta
    larghezza dentro una griglia a sei colonne», mai visto da un browser."""
    css = (STATIC / "hiris-config.css").read_text(encoding="utf-8")
    blocco = re.search(r"\." + classe + r"\s*\{([^}]*)\}", css)
    assert blocco, f".{classe} non ha una regola in hiris-config.css"
    assert re.search(r"grid-column:\s*1\s*/\s*-1", blocco.group(1)), (
        f".{classe} sta dentro la griglia della riga-provider e deve "
        f"dichiarare `grid-column: 1 / -1`: senza, si schiaccia in una colonna"
    )


# ── I tre alias del piano e la CLI che li produce ──────────────────────────

def test_ogni_alias_offerto_dal_pannello_sopravvive_alla_cli():
    """`decisione_modelli.SUBSCRIPTION_ALIAS` (quello che il pannello offre) e
    `agent/runner.modello_cli` (quello che la CLI accetta) erano due liste
    digitate a mano in due file, in ordine diverso: un quarto alias aggiunto
    la' sarebbe stato offerto, scelto, e poi ARCHIVIATO COME `sonnet` con un
    warning che nessuno legge -- il radio tornava indietro da solo, senza
    spiegazione.

    Adesso `modello_cli` ITERA `SUBSCRIPTION_ALIAS`, quindi non esiste piu' una
    seconda lista. Questa prova non cerca piu' i letterali nel sorgente: quel
    difetto non puo' piu' esistere, e una prova che lo cercasse non potrebbe
    piu' fallire. Verifica il COMPORTAMENTO -- che ogni alias offerto
    sopravviva davvero al passaggio, e che un nome estraneo ricada
    dichiaratamente su `sonnet` invece di far fallire il turno."""
    from hiris.app.agent.runner import cli_model
    from hiris.app.decisione_modelli import SUBSCRIPTION_ALIAS

    for alias, _descrizione in SUBSCRIPTION_ALIAS:
        assert cli_model(alias) == alias
        # Anche nella forma completa con cui arriva da `resolve_model`.
        assert cli_model(f"claude-{alias}-4-5-20250101") == alias

    assert cli_model("gpt-4o") == "sonnet", (
        "un modello non-Anthropic non deve far fallire il turno: si ricade "
        "sull'alias con meno modi di essere rifiutato, dichiarandolo")


def test_l_insieme_che_il_validatore_accetta_e_quello_che_la_pagina_offre():
    """Dalla fetta «il modello del piano» c'e' una terza superficie: il campo
    `ponte.modello`, che `_clean_bridge` valida.

    Le tre devono essere lo stesso insieme. Se il pannello offrisse una voce
    che il salvataggio riduce a un'altra, avremmo un controllo che non fa
    quello che dice -- la stessa cosa che il test qui sopra difende, un piano
    piu' sotto: li' era il pannello contro la CLI, qui il pannello contro il
    posto in cui la scelta si ferma."""
    from hiris.app.api import handlers_models
    from hiris.app.decisione_modelli import SUBSCRIPTION_ALIAS

    offerti = [v for v, _ in SUBSCRIPTION_ALIAS]
    for alias in offerti:
        assert handlers_models._clean_bridge({"modello": alias})["modello"] == alias, (
            f"il pannello offre {alias!r} e il salvataggio non lo tiene"
        )
    assert sorted(offerti) == ["haiku", "opus", "sonnet"]


def test_il_messaggio_di_primo_avvio_nomina_campi_che_esistono_davvero():
    """Il 503 «Nessun provider AI configurato» e' la PRIMA cosa che legge chi
    installa HIRIS e apre la chat, e cita fra virgolette basse i campi della
    pagina di configurazione. Fino alla 2.4.1 li citava con i nomi di una
    versione precedente -- «Attiva provider: Abbonamento (Claude Max)» e altri
    tre -- cioe' mandava a cercare campi che nella pagina non esistevano piu':
    debito dichiarato dal Task 5 di questa fetta e chiuso dal Task 15.

    Il difetto qui e' della stessa famiglia di quello che l'intera fetta chiude:
    una frase vera quando fu scritta, rimasta a schermo dopo che il fatto era
    cambiato. E si ripeterebbe da solo, perche' rinominare un'etichetta in
    `translations/` non tocca quel file e nessun test le legava.

    **Versione B (3.0.0): il pin ha fatto il suo mestiere.** Due dei quattro
    campi citati -- i due interruttori -- sono usciti dallo schema, e questo
    test e' caduto. Restano le DUE credenziali, che e' cio' che si custodisce
    li'. Il numero non e' piu' fissato a quattro ma pinnato all'insieme esatto:
    contare non diceva quali, e quattro era esattamente il numero che il difetto
    del 2.4.1 aveva."""
    import yaml

    testo = (BASE / "app" / "api" / "handlers_chat.py").read_text(encoding="utf-8")
    blocco = re.search(
        r'"Nessun provider AI configurato.*?sta in catena\."', testo, flags=re.DOTALL)
    assert blocco, "il messaggio di primo avvio non si trova piu': testo cambiato"
    # Le stringhe adiacenti del sorgente Python si concatenano: qui si toglie
    # solo cio' che le separa, per leggere la frase come la legge l'utente.
    frase = re.sub(r'"\s*\n\s*"', "", blocco.group(0))
    citate = re.findall(r"«([^»]+)»", frase)

    voci = yaml.safe_load(
        (BASE / "translations" / "it.yaml").read_text(encoding="utf-8"))
    nomi = set()

    def raccogli(albero):
        for voce in albero.values():
            if isinstance(voce, dict):
                if isinstance(voce.get("name"), str):
                    nomi.add(voce["name"])
                raccogli(voce)

    raccogli(voci["configuration"])
    # I due CAMPI dell'add-on citati, per nome esatto. Le altre due citazioni
    # («Mettilo primo», «Usa») sono i due GESTI della pagina Modelli, che non
    # sono campi di configurazione e non stanno in `translations/`: si
    # verificano dove vivono, nel test qui sotto.
    campi = [c for c in citate if c.startswith("Provider · ")]
    assert set(campi) == {"Provider · Piano Claude Max — token",
                          "Provider · Claude API — chiave"}, campi
    fantasma = [c for c in campi if c not in nomi]
    assert not fantasma, (
        f"il messaggio di primo avvio manda a cercare campi che non esistono: "
        f"{fantasma}. I nomi veri stanno in translations/it.yaml"
    )


def test_il_messaggio_di_primo_avvio_dice_ANCHE_il_secondo_gesto():
    """Incollare la chiave non basta piu', e il messaggio deve dirlo.

    Dalla fetta «la catena diventa l'unica verita'» un provider risponde se e
    solo se sta in catena, e nella catena non ci entra da solo: `reconcile_chain`
    lo accodava, e non lo fa piu'. Un messaggio che si fermasse alla credenziale
    lascerebbe chi ha appena installato HIRIS davanti a una chat ancora muta
    dopo aver fatto esattamente quello che gli era stato detto -- un difetto
    peggiore del precedente, perche' ogni parola sarebbe vera.

    I due gesti citati sono quelli che la pagina disegna DAVVERO: «Mettilo
    primo» arriva da `ACTION_PUT_SUBSCRIPTION_FIRST`, «Usa» e' l'etichetta del
    bottone che mette una riga in catena."""
    from hiris.app.decisione_modelli import ACTION_PUT_SUBSCRIPTION_FIRST

    testo = (BASE / "app" / "api" / "handlers_chat.py").read_text(encoding="utf-8")
    blocco = re.search(
        r'"Nessun provider AI configurato.*?sta in catena\."', testo, flags=re.DOTALL)
    frase = re.sub(r'"\s*\n\s*"', "", blocco.group(0))
    citate = re.findall(r"«([^»]+)»", frase)
    assert ACTION_PUT_SUBSCRIPTION_FIRST["etichetta"] in citate, (
        "il messaggio nomina un gesto che la pagina non offre con quel nome"
    )
    js = (BASE / "app" / "static" / "config" / "models-route.js").read_text(
        encoding="utf-8")
    for gesto in citate:
        if gesto.startswith("Provider · ") or gesto == ACTION_PUT_SUBSCRIPTION_FIRST["etichetta"]:
            continue
        assert "'" + gesto + "'" in js, (
            f"il messaggio manda a cercare il gesto «{gesto}», che la pagina "
            "Modelli non disegna"
        )


@pytest.mark.parametrize("alias", ["haiku", "sonnet", "opus"])
def test_ogni_alias_offerto_sopravvive_alla_traduzione_per_la_cli(alias):
    """Il gemello di comportamento del precedente: leggere il sorgente prova che
    i due elenchi coincidono, questo prova che scegliere una voce del pannello
    e' davvero la voce che arriva alla CLI. Senza, `SUBSCRIPTION_ALIAS` potrebbe
    contenere `Sonnet` maiuscolo e i due test sarebbero d'accordo su niente."""
    from hiris.app.agent.runner import cli_model
    from hiris.app.decisione_modelli import SUBSCRIPTION_ALIAS

    assert alias in {v for v, _ in SUBSCRIPTION_ALIAS}
    assert cli_model(alias) == alias


def test_ogni_codice_di_credenziale_ha_la_sua_causa():
    """`esiti_provider._CREDENZIALE` decide la FAMIGLIA di un esito,
    `decisione_modelli._CREDENTIAL_CAUSE` decide la FRASE: due elenchi dello
    stesso insieme chiuso, in due moduli.

    Se il primo guadagna un codice e il secondo no, la pagina afferma una causa
    che nessuno ha misurato -- e nel caso concreto (un 429 di quota aggiunto
    per farlo comparire come problema di credito) manderebbe l'utente a
    rigenerare una chiave che funziona."""
    from hiris.app.decisione_modelli import _CREDENTIAL_CAUSE
    from hiris.app.esiti_provider import _CREDENTIAL

    senza_causa = sorted(c for c in _CREDENTIAL if c not in _CREDENTIAL_CAUSE)
    assert senza_causa == [], f"codici senza una causa dichiarata: {senza_causa}"


def test_un_codice_senza_causa_non_ne_inventa_una():
    """La rete di sicurezza sotto la prova qui sopra: anche se i due elenchi
    divergessero, HIRIS dice il numero e si ferma invece di affermare un
    perche' che non ha misurato. E' la stessa disciplina del ramo `altro`."""
    from hiris.app.decisione_modelli import occurrence_phrase

    frase = occurrence_phrase(
        {"tipo": "rifiutato", "famiglia": "credenziale", "codice": 429,
         "da_quante": 3, "quando": 0.0},
        position=1, now=0.0)
    assert "429" in frase
    assert "credenziale non è accettata" not in frase
    assert "chiave" not in frase
