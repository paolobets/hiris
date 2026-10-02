"""Il seme del sapere: cio' che il repo sa gia', con la sua provenienza.

Spec `docs/design/2026-09-10-i-tre-attori.md` §8: *«Il repo diventa il seme.
Le righe del vocabolario dei tipi e quelle delle direzioni si caricano
all'avvio con la loro provenienza: restano scritte, riviste, linterate e in
git -- e la casa scrive sopra.»* (Le righe delle direzioni sono uscite il 01/10/2026 con
la pulizia dei bilanci: le scriveva solo questo seme e nessuno le leggeva.)

**Perche' un seme e non una tabella nel codice.** Finora queste righe erano
dizionari dentro `proxy/ha_client.py`: per correggerne una serviva un
rilascio, nessuno poteva vederle, e non c'era modo di dire da dove venissero
ne' se qualcuno le avesse mai verificate. Come righe del sapere hanno una
provenienza, si leggono e si correggono senza toccare il codice.

**«A caldo» vale per chi le rilegge a ogni giro, non per tutte** (Fable 5.1,
13/09/2026): il significato di una classe si rilegge a ogni dettaglio chiesto
(le direzioni dell'energia, che si rileggevano a ogni aggregazione, sono
uscite dal seme il 01/10/2026). Gli **attributi voluti** no --
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
    MEANING_FIELD,
    Fact,
    now_ts,
    type_subject,
)

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

# **Le direzioni dell'energia sono uscite dal seme il 01/10/2026.** Le
# quattordici chiavi di `zcsazzurro` (`direzione:energy_generating_today` ->
# «produzione», ...) si leggevano solo da
# `knowledge.directions_by_translation_key`, che serviva solo ai bilanci, e i
# bilanci non seminavano niente da due settimane: le righe erano scritte e
# mai lette. Sono usciti tutti e tre insieme. Quelle gia' scritte nel
# sapere delle case avviate le toglie `knowledge._migration_9` (02/10/2026),
# perche' il seme non cancella (vedi `docs/BACKLOG.md`, «Una riga del seme
# ritirata da un rilascio futuro resta in vigore per sempre»).


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
    (`scripts/censore_tipi.py`) lo interroga per sapere cosa il REPO
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
#: scaldando, `temperature` dove si vuole
#: arrivare. Senza quei due, quella frase non si puo' scrivere.
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
