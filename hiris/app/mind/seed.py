"""Il seme del sapere: cio' che il repo sa gia', con la sua provenienza.

Spec `docs/design/2026-09-10-i-tre-attori.md` §8: *«Il repo diventa il seme.
Le righe del vocabolario dei tipi e quelle delle direzioni si caricano
all'avvio con la loro provenienza: restano scritte, riviste, linterate e in
git -- e la casa scrive sopra.»*

**Perche' un seme e non una tabella nel codice.** Finora queste righe erano
dizionari dentro `proxy/ha_client.py`: per correggerne una serviva un
rilascio, nessuno poteva vederle, e non c'era modo di dire da dove venissero
ne' se qualcuno le avesse mai verificate. Come righe del sapere hanno una
provenienza, si leggono, si correggono a caldo e -- quelle universali -- si
esportano a chiunque abbia la stessa integrazione.

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

#: Chi ha scritto le righe del seme: il repo stesso, non un modello e non il
#: proprietario. Serve perche' `Fact` pretende un autore, e «il repo» e' la
#: risposta onesta.
#:
#: **`who` non e' decorazione: e' la chiave con cui il seme sa cosa puo'
#: correggere** (`KnowledgeStore.seed`). Due scrittori diversi devono avere due
#: nomi diversi, o l'uno correggerebbe le righe dell'altro credendole sue.
SEED_AUTHOR = "seme del repo"

#: Chi scrive le righe che arrivano dall'installazione di questa casa. E' un
#: autore DIVERSO dal repo, e la differenza morde: con lo stesso nome, il nome
#: pubblicato da Home Assistant («Potenza») schiaccerebbe la frase piu' ricca
#: che il repo ha scritto per quella classe -- che e' esattamente cio' che
#: `test_il_NOME_della_casa_non_schiaccia_la_FRASE_del_repo` difende.
HOUSE_AUTHOR = "l'installazione di questa casa"

#: Le quattordici chiavi di `zcsazzurro`, misurate sulla casa vera il
#: 27/08/2026 e ri-misurate il 12/09/2026 (tutte e quattordici hanno ancora un
#: name tradotto vivo dentro l'installazione, vedi
#: `docs/design/2026-09-12-il-sapere-e-le-ricette.md`).
#:
#: **Nessun suffisso `_today` sul gemello di potenza** -- trappola misurata,
#: non dedotta dal pattern dell'energia (`power_generating`, non
#: `power_generating_today`).
#:
#: **La provenienza e' `dedotto`, e le prove sono il `translation_key`.**
#: Home Assistant dichiara il NOME («Energia prodotta oggi»), non la
#: direzione: il salto fra le due cose e' un giudizio nostro sulla chiave che
#: l'integrazione scrive, e chiamarlo `importato` sarebbe dire che qualcuno
#: la' fuori ce l'ha detto.
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
    "il translation_key che l'integrazione scrive nel registro delle entita', "
    "misurato sulla casa vera il 27/08/2026 e ri-visto il 12/09/2026 "
    "(frontend/get_translations, categoria «entity»)"
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
    quel modulo lo aveva gia' previsto per name: *«e' il candidato dichiarato a
    diventare un campo di quelle righe, con la sua provenienza `importato`,
    quando la fetta che collega i vocabolari arrivera'»*. E' questa.

    **La provenienza e' `importato` e la fonte e' la citation col tag**: non
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
             provenance="importato", evidence=citation,
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

    `verification` e' `confermata` e la fonte e' il comando con la versione
    di Home Assistant: e' l'installazione stessa a dirlo, non una nostra
    deduzione.
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
                verification="confermata", source=citation,
                who=HOUSE_AUTHOR, when_ts=when))
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
