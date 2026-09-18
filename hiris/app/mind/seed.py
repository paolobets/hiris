"""Il seme del sapere: cio' che il repo sa gia', con la sua provenienza.

Spec `docs/design/2026-09-10-i-tre-attori.md` §8: *«Il repo diventa il seme.
Le righe del vocabolario dei tipi e quelle delle direzioni si caricano
all'avvio con la loro provenienza: restano scritte, riviste, linterate e in
git -- e la casa scrive sopra.»*

**Perche' un seme e non una tabella nel codice.** Finora queste righe erano
dizionari dentro `proxy/ha_client.py`: per correggerne una serviva un
rilascio, nessuno poteva vederle, e non c'era modo di dire da dove venissero
ne' se qualcuno le avesse mai verificate. Come righe del sapere hanno una
provenienza, si leggono e si correggono senza toccare il codice.

**«A caldo» vale per chi le rilegge a ogni giro, non per tutte** (Fable 5.1,
13/09/2026): le direzioni si rileggono a ogni aggregazione, il significato di
una classe a ogni dettaglio chiesto. Gli **attributi voluti** no --
l'osservatore li tiene in memoria per non interrogare l'archivio due volte per
evento, e una riga corretta si legge al riavvio successivo. Il costo della
memoria e la sua sorte stanno scritti accanto (`mind/watcher.py`).

**Il seme non schiaccia la casa**: `KnowledgeStore.seed` scrive solo cio' che
ancora non c'e'. Se sovrascrivesse, ogni riavvio cancellerebbe cio' che la
casa ha imparato, e il difetto sarebbe invisibile -- il valore tornerebbe
semplicemente a essere quello scritto nel repo, che sembra giusto.
"""
from __future__ import annotations

from .knowledge import (
    ATTRIBUTE_FIELD,
    DIRECTION_FIELD_PREFIX,
    MEANING_FIELD,
    Fact,
    now_ts,
    type_subject,
)
from .recipes import ENTITY_MARK, STEP_MARK

#: Chi ha scritto le righe del seme: il repo stesso, non un modello e non il
#: proprietario. Serve perche' `Fact` pretende un autore, e «il repo» e' la
#: risposta onesta.
#:
#: **`who` non e' decorazione: e' la chiave con cui il seme sa cosa puo'
#: correggere** (`KnowledgeStore.seed`). Due scrittori diversi devono avere due
#: nomi diversi, o l'uno correggerebbe le righe dell'altro credendole sue.
SEED_AUTHOR = "seme del repo"

#: La precedenza del repo fra i semi. **Il repo batte l'installazione**: porta
#: una frase che dice cosa un valore E', mentre l'installazione porta il nome
#: che Home Assistant pubblica. Senza una precedenza esplicita vincerebbe chi
#: arriva prima, e su una casa che ha gia' importato «Indice AQI» la frase piu'
#: ricca aggiunta da un rilascio successivo non atterrerebbe mai (Fable 5.1,
#: 13/09/2026).
#:
#: **Cambiare `SEED_AUTHOR` non e' piu' pericoloso**: la regola del seme si
#: legge dal valore seminato, non dall'autore. `who` resta cio' che dice a chi
#: legge da dove viene la riga.
REPO_PRIORITY = 2

#: Chi scrive le righe che arrivano dall'installazione di questa casa. E' un
#: autore DIVERSO dal repo, e la differenza morde: con lo stesso nome, il nome
#: pubblicato da Home Assistant («Potenza») schiaccerebbe la frase piu' ricca
#: che il repo ha scritto per quella classe -- che e' esattamente cio' che
#: `test_il_NOME_della_casa_non_schiaccia_la_FRASE_del_repo` difende.
HOUSE_AUTHOR = "l'installazione di questa casa"

#: La precedenza dell'installazione: sotto il repo. Vedi `REPO_PRIORITY`.
HOUSE_PRIORITY = 1

#: Le quattordici chiavi di `zcsazzurro`, misurate sulla casa vera il
#: 27/08/2026 e ri-misurate il 12/09/2026 (tutte e quattordici hanno ancora un
#: nome tradotto vivo dentro l'installazione, vedi
#: `docs/design/2026-09-12-il-sapere-e-le-ricette.md`).
#:
#: **Nessun suffisso `_today` sul gemello di potenza** -- trappola misurata,
#: non dedotta dal pattern dell'energia (`power_generating`, non
#: `power_generating_today`).
#:
#: **La provenienza e' `dedotto`, e le prove sono il `translation_key`.**
#: Home Assistant dichiara il NOME («Energia prodotta oggi»), non la
#: direzione: il salto fra le due cose l'ha fatto un modello leggendo le
#: chiavi che l'integrazione scrive -- che e' esattamente cio' che `dedotto`
#: significa nel vocabolario del sapere. Non `importato` (nessuno la' fuori ce
#: l'ha detto) e non `nostro` (quello e' un giudizio che nessuna fonte
#: potrebbe darci, e qui la fonte c'e': la chiave).
_ZCSAZZURRO_DIRECTIONS = {
    "energy_generating_today": "produzione", "power_generating": "produzione",
    "energy_importing_today": "prelievo", "power_importing": "prelievo",
    "energy_exporting_today": "immissione", "power_exporting": "immissione",
    "energy_charging_today": "carica", "power_charging": "carica",
    "energy_discharging_today": "scarica", "power_discharging": "scarica",
    "energy_consuming_today": "consumo", "power_consuming": "consumo",
    "energy_autoconsuming_today": "autoconsumo", "power_autoconsuming": "autoconsumo",
}

_DIRECTION_EVIDENCE = (
    "il translation_key che l'integrazione scrive nel registro delle entita' "
    "(config/entity_registry/list), misurato sulla casa vera il 27/08/2026. Il "
    "12/09/2026 si e' ri-visto che tutte e quattordici le chiavi hanno ancora "
    "un nome pubblicato (frontend/get_translations, categoria «entity») -- il "
    "che prova che la chiave esiste, non che la direzione sia quella"
)


def direction_seed(when_ts: float | None = None) -> list[Fact]:
    """Le direzioni dell'energia come righe del sapere.

    Soggetto **integrazione**, quindi universali: valgono per chiunque abbia
    quell'inverter, e si esportano.
    """
    when = when_ts if when_ts is not None else now_ts()
    return [
        Fact(subject_kind="integrazione", subject="zcsazzurro",
             field=f"{DIRECTION_FIELD_PREFIX}{key}", value=direction,
             provenance="dedotto", evidence=_DIRECTION_EVIDENCE,
             who=SEED_AUTHOR, when_ts=when)
        for key, direction in sorted(_ZCSAZZURRO_DIRECTIONS.items())
    ]


# -- I significati delle classi -------------------------------------------

def meaning_seed(when_ts: float | None = None) -> list[Fact]:
    """I significati che il REPO ha scritto a mano, come righe del sapere.

    Sono le ventisette coppie di `home_space/ha_vocabulary.DEVICE_CLASS_MEANING`,
    copiate dai sorgenti di Home Assistant al tag dichiarato. Il docstring di
    quel modulo lo aveva gia' previsto per nome: *«e' il candidato dichiarato a
    diventare un campo di quelle righe, con la sua provenienza `importato`,
    quando la fetta che collega i vocabolari arrivera'»*. E' questa.

    **La provenienza e' `importato` e la fonte e' la citazione col tag**: non
    sono giudizi nostri, sono frasi lette nel sorgente di Home Assistant, e chi
    legge la riga fra sei mesi deve poter sapere da quale versione.

    Il dizionario **resta nel repo**: e' il seme, ed e' cio' che la spec
    chiede -- *«restano scritte, riviste, linterate e in git, e la casa scrive
    sopra»*. Resta anche il lettore che ne fa un altro uso: il censore
    (`home_space/type_census.py`) lo interroga per sapere cosa il REPO
    rivendica, che e' una domanda diversa da «cosa significa».
    """
    from ..home_space.ha_vocabulary import (
        DEVICE_CLASS_MEANING,
        VOCABULARY_HA_VERSION,
        VOCABULARY_SOURCE,
    )

    when = when_ts if when_ts is not None else now_ts()
    citation = f"{VOCABULARY_SOURCE} (Home Assistant {VOCABULARY_HA_VERSION})"
    return [
        Fact(subject_kind="tipo", subject=type_subject(domain, device_class),
             field=MEANING_FIELD, value=meaning,
             provenance="importato", source=citation,
             who=SEED_AUTHOR, when_ts=when)
        for (domain, device_class), meaning in sorted(DEVICE_CLASS_MEANING.items())
    ]


def meanings_from_translations(resources, *, ha_version: str, language: str,
                               when_ts: float | None = None) -> list[Fact]:
    """I nomi che **questa installazione** pubblica per ogni classe.

    Chiude il buco misurato il 12/09/2026: il repo scriveva a mano il
    significato di 18 classi di `sensor` su 62 e di **zero** su 28 di
    `binary_sensor`, mentre l'installazione li pubblica tutti, nella lingua
    dell'utente (`docs/design/2026-09-12-il-sapere-e-le-ricette.md`, misura 2).
    Le 44 classi che il repo non nominava non erano «non importanti»: erano
    quelle di cui HIRIS non sapeva dire niente.

    **E' un NOME, non una spiegazione**, e la differenza si dichiara invece di
    lasciarla intuire: Home Assistant pubblica «Potenza», non «la potenza
    istantanea in watt, che non e' un'energia». Per questo queste righe **non
    schiacciano** quelle del seme -- si scrivono con `seed`, che tocca solo
    cio' che manca -- e dove il repo ha scritto una frase vera quella resta.

    **`verification` resta vuota anche qui**, e la ragione e' la stessa del
    seme del repo (Fable 5.1, 13/09/2026): il «controllo» sarebbe la stessa
    fonte da cui viene la provenienza, cioe' la provenienza riscritta due
    volte. `confermata` si riserva a un controllo fatto contro una fonte
    DIVERSA -- che e' l'unica cosa per cui avere due assi serva a qualcosa.
    """
    from ..proxy.state_translations import published_device_classes

    when = when_ts if when_ts is not None else now_ts()
    citation = (f"frontend/get_translations «entity_component», lingua "
                 f"«{language}» (Home Assistant {ha_version})")
    facts = []
    for domain, classes in sorted(published_device_classes(resources).items()):
        for device_class in sorted(classes):
            name = resources.get(
                f"component.{domain}.entity_component.{device_class}.name")
            if not name:
                continue
            facts.append(Fact(
                subject_kind="tipo", subject=type_subject(domain, device_class),
                field=MEANING_FIELD, value=name, provenance="importato",
                source=citation, who=HOUSE_AUTHOR, when_ts=when))
    return facts


# -- gli attributi che valgono la pena --------------------------------------

#: Gli attributi che il repo dichiara utili, per tipo. **Sono un giudizio
#: nostro**: nessuna API di Home Assistant dice quali attributi servano a
#: capire una casa, quindi `provenienza` e' `nostro` e `verifica` e' vuota --
#: la regola che `Fact` fa rispettare al costruttore.
#:
#: Le righe di `climate` vengono dall'esempio fondativo del documento del
#: cervello, che la spec §5.4 cita come **oggi non rispondibile**: *«il
#: riscaldamento parte alle 15:30, la casa e' calda alle 16:30»*. Lo stato di
#: un termostato e' `heat` e resta `heat`; `hvac_action` dice se sta davvero
#: scaldando, `current_temperature` dove si e', `temperature` dove si vuole
#: arrivare. Senza quei tre, quella frase non si puo' scrivere.
#:
#: **Sono pochi apposta.** Il silenzio qui significa «non tenere niente», non
#: «tieni tutto»: tenere tutto rimetterebbe nel grezzo le 6.503 righe al
#: giorno di soli attributi che il filtro `da == a` ha appena tolto (misurato
#: il 10/09/2026). Un tipo entra in questa tabella quando qualcuno ha una
#: domanda che senza quell'attributo non si risponde.
#: **`current_temperature` NON c'e', ed e' la correzione piu' importante di
#: questa tabella** (revisione indipendente, 13/09/2026). E' una grandezza
#: continua: si muove di decimo in decimo tutto il giorno, e le 6.503 righe di
#: solo attributo misurate il 10/09 -- 6.446 dei soli otto termostati -- sono
#: in buona parte sue. Tenerla fra i voluti riaprirebbe proprio il flusso che
#: il filtro `da == a` ha chiuso, in misura che nessuno ha contato: un numero
#: non misurato travestito da scelta.
#:
#: E non serve. La domanda fondativa -- *«il riscaldamento parte alle 15:30, la
#: casa e' calda alle 16:30»* -- la risponde `hvac_action`, che passa a `idle`
#: **quando** la casa e' arrivata in temperatura: un cambio per episodio, non
#: uno per decimo di grado. La temperatura istantanea, se serve, e' un
#: `sensor` a se' che Home Assistant riassume gia' (regola 1 della spec §5.3).
_WANTED_ATTRIBUTES = {
    "climate": ("hvac_action", "temperature"),
    "water_heater": ("temperature",),
    "humidifier": ("action", "humidity"),
}


def attribute_seed(when_ts: float | None = None) -> list[Fact]:
    """Gli attributi che valgono la pena, come righe del sapere."""
    when = when_ts if when_ts is not None else now_ts()
    return [
        Fact(subject_kind="tipo", subject=domain, field=ATTRIBUTE_FIELD,
             value=",".join(attributes), provenance="nostro",
             who=SEED_AUTHOR, when_ts=when)
        for domain, attributes in sorted(_WANTED_ATTRIBUTES.items())
    ]


# -- i giudizi sui tipi ------------------------------------------------------

def judgment_seed(when_ts: float | None = None) -> list[Fact]:
    """I giudizi sui tipi come righe del sapere (spec 2026-09-16 §3): `nostro`,
    senza verifica, dal letterale di `home_space/type_vocabulary.py`. La casa
    scrive sopra dalla porta unica (`mind/judgments.write_judgment`).

    **Il seme non CANCELLA: una riga ritirata da un rilascio futuro resta in
    vigore per sempre** (giro di correzioni 1, punto 6, dichiarato e non
    costruito). `knowledge.seed` scrive e corregge, non toglie: il giorno in
    cui una riga sparisse da `judgment_seed_rows()`, sulle installazioni
    esistenti resterebbe sul disco, `judgment_listing` la mostrerebbe come
    `da: altro` (nessuno dei due la rivendica) e l'istantanea continuerebbe a
    leggerla. Oggi non succede: nessuna riga e' mai stata ritirata. Non si
    costruisce niente adesso perche' **cancellare righe del seme e' una
    decisione del proprietario**, non un effetto collaterale di un
    aggiornamento -- e una cancellazione automatica porterebbe via anche la
    riga che il proprietario avesse corretto a mano sulla stessa terna. Voce
    in `docs/BACKLOG.md`.
    """
    from ..home_space.type_vocabulary import judgment_seed_rows

    when = when_ts if when_ts is not None else now_ts()
    return [Fact(subject_kind=kind, subject=subject, field=field, value=value,
                 provenance="nostro", who=SEED_AUTHOR, when_ts=when)
            for kind, subject, field, value in judgment_seed_rows()]


# -- la ricetta del bilancio ------------------------------------------------

def balance_recipe(entity_per_dimension: dict[str, str], *, order,
                   expected_hours: int | None = None) -> dict:
    """La ricetta del bilancio dell'energia, **come dato**.

    **Sta fra i SEMI e non nel motore** (Fable 5.1, 13/09/2026): `recipes.py`
    e' l'esecutore generico e non deve sapere cosa sono i kWh, l'autoconsumo o
    il prelievo. Questa funzione invece e' cio' che il REPO sa di un bilancio,
    destinato a diventare una riga del sapere quando la ricetta ci vivra'
    davvero -- esattamente come le direzioni e i significati qui sopra.

    **E' il pezzo che la spec §7 nomina per primo.** Da qui in avanti il
    bilancio e' una sequenza di passi con nomi: si legge tutta, si valida, si
    rifiuta prima di eseguirla, e le due quote si calcolano in un posto solo
    invece che in due (erano un conto a se' dentro `_balance_moments`).

    **Non e' ancora scritta nel sapere**, quindi correggerla vuole ancora un
    rilascio: la meta' che manca e' a backlog. Vedi il docstring del modulo.

    **Perche' il repo la genera invece di averla scritta a mano.** I passi
    dipendono da quali direzioni questo dispositivo ha davvero: un inverter
    senza accumulo non ha «carica» ne' «scarica», e una ricetta con passi che
    nominano entita' inesistenti verrebbe **rifiutata** dalla validazione --
    giustamente. La ricetta e' un dato generato da un altro dato (la mappa
    direzione -> entita', che il chiamante risolve), non un letterale da
    tenere aggiornato a mano per ogni forma d'impianto.

    **L'ordine arriva da chi possiede l'elenco delle direzioni**, e non e'
    estetica: un passo puo' leggere solo quelli PRIMA di lui, quindi i totali
    devono venire prima delle quote che li compongono, e l'ordine fra i totali
    dev'essere stabile o due giri della stessa casa produrrebbero due ricette
    diverse. La prima stesura ne teneva una copia qui (`_BALANCE_ORDER`),
    identica lettera per lettera a `mind/facts.BALANCE_DIRECTIONS`: una
    direzione aggiunta a una sola delle due sarebbe sparita dal bilancio
    **senza un errore e senza un log** (revisione indipendente, 13/09/2026).

    I passi:

    - un totale per ogni direzione presente (`somma_periodo`);
    - la quota di autoconsumo sulla produzione, quando ci sono entrambe;
    - l'autosufficienza come **la ricetta della spec §7 la scrive**:
      `quota(differenza_fra(consumo, prelievo), consumo)`.
    """
    steps = []
    present = [d for d in order if entity_per_dimension.get(d)]
    for dimension in present:
        given_entity = f"{ENTITY_MARK}{entity_per_dimension[dimension]}"
        steps.append({
            "name": dimension, "operation": "somma_periodo",
            "inputs": [given_entity],
            "params": {"unit": "kWh", "expected_parts": expected_hours},
        })
        steps.append({
            "name": f"forma_{dimension}", "operation": "per_ora",
            "inputs": [given_entity],
            "params": {"unit": "kWh", "expected_parts": expected_hours},
        })
    if "autoconsumo" in present and "produzione" in present:
        steps.append({"name": "quota_autoconsumo", "operation": "quota",
                      "inputs": [f"{STEP_MARK}autoconsumo",
                                 f"{STEP_MARK}produzione"]})
    if "consumo" in present and "prelievo" in present:
        steps.append({"name": "autoprodotto", "operation": "differenza_fra",
                      "inputs": [f"{STEP_MARK}consumo", f"{STEP_MARK}prelievo"]})
        steps.append({"name": "quota_autosufficienza", "operation": "quota",
                      "inputs": [f"{STEP_MARK}autoprodotto",
                                 f"{STEP_MARK}consumo"]})
    return {
        "why": ("il bilancio dell'energia di questo dispositivo: quanto ha "
                "prodotto, consumato, prelevato, e quanta parte del consumo "
                "non e' venuta dalla rete"),
        "steps": steps,
    }
