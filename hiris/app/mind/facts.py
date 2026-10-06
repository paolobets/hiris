"""L'aggregazione: dai cambi grezzi agli episodi della cronaca.

**Un episodio e' una cosa compiuta della casa**: qualcosa che e' cominciato,
e' durato, e' finito.

    Riscaldamento camera: acceso 15:30 -> 17:05.

**E' l'unico posto di questa fetta dove si giudica**, ed e' voluto: un giudizio
qui si rifa' finche' il grezzo esiste (22 giorni: 21 di promessa, uno di
guardia -- vedi `mind/store.READING_RETENTION_S`), uno preso in scrittura non
si corregge piu'.

**L'obiettivo sceglie QUALI entita', la natura decide CHE TIPO di episodio ne
esce.** La prima non e' una lista scritta a mano: e' lo scope
(`mind/watcher.py`, `store.is_watched`), una decisione presa soggetto per
soggetto dall'osservatore (`mind/observer.py`, spec §5.1) -- non piu' derivata
da `device_class`/`source_type` come faceva la gamba, uscita insieme al
vocabolario dei tipi il 17/09/2026 (spec 2026-09-16 §11). **La seconda,
invece, e' un giudizio nostro**: che genere di episodio nasce da un soggetto,
e quali suoi stati valgono «a riposo», nessuna API di Home Assistant lo dice.

**Dal 07/09/2026 quel giudizio non vive piu' qui.** `_OPERABLE`, `_RESTING` e
`_UNKNOWN` erano tre elenchi scritti a mano in questo modulo; sono diventati
righe del **vocabolario dei tipi** (`home_space/type_vocabulary.py`). Spec:
`docs/design/2026-09-07-l-anagrafe-dei-tipi.md`.

**Dal 17/09/2026 il genere e il riposo si chiedono all'istantanea dei
giudizi** (`home_space/type_judgments.TypeJudgments`, spec
`docs/design/2026-09-16-il-giudizio-dei-tipi.md` §5), di cui il vocabolario e'
il seme. Questo modulo resta il LETTORE: `genre_for` chiede il genere del
soggetto, `_is_on` chiede se uno stato e' un riposo PER QUEL soggetto, e gli
stati «non lo so» e le forme dell'assenza di stato
(`type_vocabulary.unknown_states()`, `type_vocabulary.ABSENT_STATE_FORMS`)
non sono il riposo di nessuno: dal 06/10/2026 sono le VOCI d'assenza della
fonte (`_absences`, D5 «raccolte»). L'istantanea arriva come parametro
`judgments=`: in produzione e' `app["type_judgments"]`, il predefinito
`REPO_JUDGMENTS` e' il solo seme.

**Una frase che questo docstring ha portato fino a oggi era falsa**, e vale la
pena lasciarne traccia: diceva che Home Assistant «non dichiara da nessuna
parte quale dominio funziona come un interruttore». Lo dichiara -- il registro
dei servizi isola i domini con `turn_on` **e** `turn_off`, o `toggle` (spec
§4, misurato sulla casa vera il 07/09/2026: 16 domini). La derivazione non
coincide con il giudizio nostro e sbaglia in entrambi i versi, quindi non lo
sostituisce: lo **sorveglia**, ed e' lavoro delle fette 3 e 4.
"""
from __future__ import annotations

import json

from ..home_space.ha_vocabulary import domain_of
from ..home_space.historian import day_boundaries
from ..home_space.house import ENDED_SOURCE_STATES, House
from ..home_space.type_judgments import TypeJudgments
from ..home_space.type_vocabulary import (
    ABSENT_STATE_FORMS,
    CHRONICLE_GENRES,
    REPO_JUDGMENTS,
    SYSTEM_GENRE,
    unknown_states,
)
from .report import build_report
from .store import READING_RETENTION_S

# `aggregate_day` e `build_episodes` sono SINCRONE: non fanno nessuna lettura
# di rete. Cio' che viene da Home Assistant -- le serie delle ricette, i nomi
# dei dispositivi -- arriva gia' letto dal chiamante
# (`server.py::_report_ingredients`), una lettura per giro e non una per
# episodio. Renderle `async` "per il futuro" sarebbe generalita' speculativa.

#: I quattro generi che hanno una forma (spec 2026-09-16 §5, D2), spostati in
#: `type_vocabulary.CHRONICLE_GENRES`: una casa sola, `mind/facts` la importa.
#: `energia` e `bilancio` sono usciti il 16/09/2026: nessun ramo di
#: `build_episodes` apre o chiude niente per un contatore (vedi i commenti
#: dentro la funzione, «I bilanci non entrano piu' qui» subito dopo
#: `store.readings` e «Un contatore non apre niente» piu' sotto), e nessun
#: codice produce il genere `"bilancio"`.
GENRES = CHRONICLE_GENRES

#: I cinque prefissi con cui un `protagonista` NON e' un'entita' di Home
#: Assistant, ma una condizione di sistema: una voce del registro di errori
#: (`problema:`, `integrazione:`, `log:` -- Task 2 «le tracce e il log»),
#: un'esecuzione di automazione in errore (`automazione:`, Task 4 dello
#: stesso verticale) o la finestra in cui l'add-on e' rimasto scollegato da
#: Home Assistant (`connessione:`, il riallineamento alla riconnessione,
#: decisione del proprietario del 06/10/2026). **Il lettore della tupla e'
#: `genre_for`**, qui sotto, che ne fa un `guasto`. I singoli prefissi sono
#: riletti a mano anche in `api/handlers_mind.py::_with_integration` e in
#: `mind/watcher.py::rebuild_conditions`.
#:
NOT_ENTITY_PREFIXES = ("problema:", "integrazione:", "log:", "automazione:",
                       "connessione:")

#: Il prefisso di un'istanza d'integrazione, chiesto alla tupla qui sopra e
#: non riscritto: da qui lo scrive anche la cronaca. La voce di un'istanza le
#: cui entita' sono assenti nello stesso istante (Task 1.4 degli attori,
#: Passo 3) ha per soggetto la stessa istanza con lo stesso prefisso con cui l'osservatore
#: scrive un'istanza in errore -- la stessa cosa vista da due porte ha la
#: stessa forma (fondamenta 3). La tupla resta letterale, e dal 06/10/2026
#: il suo gemello in JavaScript (`parseSubjectPrefix` in `watcher-shared.js`,
#: C-10 del registro) le e' legato da una prova
#: (`tests/test_pagine_legate.py::test_subject_prefixes_are_read_by_the_page`);
#: la prova dell'istanza
#: (`test_un_integrazione_che_sparisce_tutta_insieme_e_UNA_voce`) arrossisce
#: se l'ordine cambia.
INSTANCE_SUBJECT_PREFIX = NOT_ENTITY_PREFIXES[1]

#: Il soggetto della finestra di scollegamento: l'osservatore lo scrive alla
#: riconnessione (`Watcher.realign`, «scollegato» all'inizio e «chiuso» alla
#: fine), la cronaca ne fa una voce di sistema e le raccoglie dentro le
#: assenze cominciate in quella finestra (`_gathered_by_disconnection`), il
#: primo piano la lascia fuori (`report._front_page_mark`). Uno solo: c'e' un
#: solo Home Assistant da cui l'add-on puo' restare scollegato.
DISCONNECTION_SUBJECT = NOT_ENTITY_PREFIXES[4] + "home_assistant"

#: **La regola con cui questo modulo costruisce la cronaca**, accanto
#: all'impronta dei giudizi in `giudizio` (`chronicle_mark`). L'impronta dice
#: con quali giudizi e' nata una cronaca; questa, con quale codice. Si alza
#: quando cambia cio' che `build_episodes` scrive a parita' di grezzo e di
#: giudizi, e il recupero (`server.py::backfill_one_report`) rifa' allora le
#: cronache scritte prima, finche' il loro grezzo c'e' -- lo stesso meccanismo
#: dell'impronta, nessuno nuovo.
#:
#: - assente: fino al 05/10/2026;
#: - 2: una fonte che Home Assistant non nomina piu' chiude il suo episodio
#:   (Task 1.4 degli attori, Passo 1);
#: - 3: l'episodio ereditato comincia dove comincia la sequenza, dentro la
#:   finestra del grezzo e solo per chi e' nello scope (Passo 2) -- uscita
#:   con la 3.76.0;
#: - 4: le assenze sono voci, raccolte per istanza quando entita' della
#:   stessa istanza mancano nello stesso istante, e interrompono l'episodio in corso (Passo 3, D5
#:   «raccolte», 06/10/2026). Non e' la 3 ritoccata: la 3 e' gia' nelle
#:   cronache scritte dalla 3.76.0, e il recupero deve poterle riconoscere.
#:   Ritoccata invece lo stesso giorno (giro 17: lo stato e `chiusa_dalla_fonte`
#:   dentro `assenti`, lo stato dell'istanza solo se e' di tutte) SENZA
#:   alzarla: la 4 non era ancora uscita in nessun rilascio (`git tag
#:   --contains` del suo commit vuoto), quindi nessuna cronaca scritta da un
#:   add-on pubblicato la porta con la forma di prima.
#:
#:   Non si alza nemmeno per la finestra di scollegamento (riallineamento alla
#:   riconnessione, 06/10/2026): la sua voce e le assenze che raccoglie
#:   nascono solo dalle righe `connessione:`, che nessun grezzo scritto prima
#:   porta -- a parita' di grezzo la cronaca e' la stessa
#:   (`test_senza_finestre_la_cronaca_non_cambia`).
CHRONICLE_RULE = 4

# **Il riposo e' del SOGGETTO, non l'unione di tutti i tipi** (17/09/2026, spec
# 2026-09-16 §5). Fino ad allora `_is_on` riceveva lo stato nudo e lo
# confrontava con `type_vocabulary.resting_states()`, l'unione dei riposi di
# ogni tipo; ora riceve anche il soggetto e la sua classe, e chiede
# all'istantanea il riposo di QUEL soggetto (entita', poi coppia, poi dominio).
# **Misurato prima di cambiarlo** (spec §1, misura 7): ripassate 52.123 righe
# di storia di Home Assistant su 304 entita' dei tipi con genere, dal 09/09 al
# 16/09/2026, nessuna riga cambia esito. L'unico cambio che la casa vede e' il
# salto di `none` e del vuoto, dichiarato in `build_episodes`.


def genre_for(subject: str, device_class: str | None, *,
              judgments: TypeJudgments = REPO_JUDGMENTS) -> str | None:
    """Che genere di episodio puo' nascere da questo soggetto, o `None` se non
    ne nasce nessuno.

    **Le condizioni di sistema sono `guasto` qui, nel codice**: `problema:`,
    `integrazione:`, `log:` (una voce del registro di errori) e `automazione:`
    (un'esecuzione in errore) non sono entita' di Home Assistant, e la loro
    forma e' codice. Per ogni entita' il genere e' un **giudizio
    dell'istantanea** (spec 2026-09-16 §5): prima l'entita', poi la coppia
    dominio/`device_class` della riga di grezzo, poi il dominio. Un `nessuno`
    scritto su un livello nega quelli sopra.

    **I sensori da soli non generano episodi**: «la temperatura e' salita» non
    e' una cosa compiuta, e' il CONTESTO di qualcosa che e' successo. Nel seme
    il dominio `sensor` non ha nessuna riga `genere`, e nemmeno le sue coppie.

    **`sicurezza` non e' `guasto`.** Serrature, pannello dell'allarme, sirene e
    i `binary_sensor` di fumo, gas, monossido, allagamento, sicurezza,
    manomissione, problema, calore e gelo hanno la stessa FORMA di una
    condizione di sistema -- nascono, durano, finiscono o restano aperti -- ma
    una porta aperta con la chiave e un'integrazione Sonos rotta non sono lo
    stesso genere di fatto. Nel seme sono righe `genere` `sicurezza`, e una
    sirena (accendibile anche lei) e' `sicurezza`, non `funzionamento`.

    **Il monossido misurato resta fuori, e restare fuori e' la decisione**: un
    `sensor` di classe `carbon_monoxide` MISURA una concentrazione, non SCATTA.
    Una lettura come "0.4" non e' mai un riposo e aprirebbe un episodio che non
    chiude mai; servirebbe una soglia, e non ne abbiamo una onesta. Il seme non
    gli scrive nessun genere; il `binary_sensor` di monossido, che scatta
    davvero, e' `sicurezza`.
    """
    if subject.startswith(NOT_ENTITY_PREFIXES):
        return "guasto"
    return judgments.genre_of(subject, device_class)


def _is_on(value, subject: str, device_class: str | None,
           judgments: TypeJudgments) -> bool:
    """Se questo stato NON e' un riposo **per questo soggetto** -- cioe' se
    l'episodio e' ancora in corso. Il riposo e' quello che l'istantanea
    dichiara per l'entita', la coppia o il dominio (vedi il commento sopra
    `genre_for`: misurato, nessuna riga della casa cambia esito)."""
    domain = domain_of(subject)
    state = str(value or "").strip().lower()
    return state not in judgments.resting_of(domain, device_class, subject)


#: I generi che aprono e chiudono sullo STATO: i generi della cronaca meno
#: quello di sistema, che ha la sua forma (apre su qualunque condizione, chiude
#: su `chiuso`). Chiesti al vocabolario, non riscritti: fino al 05/10/2026 la
#: tupla stava scritta due volte in questo modulo.
_STATE_GENRES = tuple(g for g in CHRONICLE_GENRES if g != SYSTEM_GENRE)


def _replay_open(transitions, *, judgments: TypeJudgments,
                 absent: frozenset[str] | set[str],
                 ) -> tuple[dict[str, tuple[str, dict]], dict[str, dict]]:
    """Cio' che e' in corso alla fine di queste transizioni: gli episodi
    `{soggetto: (genere, riga che l'ha aperto)}` e le assenze `{soggetto:
    riga che l'ha aperta}`.

    **La regola e' quella del ciclo del giorno** (`_episodes`): uno stato non
    a riposo apre se niente e' aperto, un riposo chiude; uno stato assente
    (`absent`) INTERROMPE l'episodio in corso e apre l'assenza, il primo stato
    vero dopo la chiude (D5 «raccolte», Passo 3). Cosi' cio' che si eredita a
    mezzanotte e' esattamente cio' che il ciclo di ieri ha lasciato aperto:
    stesso inizio, stesso stato -- e un episodio interrotto ieri e' finito
    ieri, non continua oggi.
    """
    opened: dict[str, tuple[str, dict]] = {}
    missing: dict[str, dict] = {}
    for r in transitions:
        subject = r["soggetto"]
        state = str(r["a"] or "").strip().lower()
        if state in absent:
            opened.pop(subject, None)
            missing.setdefault(subject, r)
            continue
        missing.pop(subject, None)
        genre = genre_for(subject, r.get("device_class"), judgments=judgments)
        if genre not in _STATE_GENRES:
            continue
        if _is_on(state, subject, r.get("device_class"), judgments):
            opened.setdefault(subject, (genre, r))
        else:
            opened.pop(subject, None)
    return opened, missing


def _opening_attributes(row: dict):
    """La foto degli attributi voluti al momento in cui l'episodio si apre.

    E' la riga del cambio di STATO, che l'osservatore scrive gia' con gli
    attributi che il sapere vuole (`mind/watcher.py`, spec §5.4). Senza di
    lei il corpo dell'episodio comincerebbe dal primo cambio SUCCESSIVO, e
    meta' della colonna `attributes` del grezzo resterebbe scritta e non letta
    da nessuno (Fable 5.1, 13/09/2026).

    Lista vuota quando non c'e' niente: mai una voce con un dizionario vuoto,
    che direbbe «li abbiamo guardati e non c'erano».
    """
    raw_attributes = row.get("attributes")
    if not raw_attributes:
        return []
    try:
        values = json.loads(raw_attributes)
    except (TypeError, ValueError):
        return []
    return [(row["quando_ts"], values)] if isinstance(values, dict) and values else []


def build_episodes(*, store, day: str, timezone: str | None,
                   judgments: TypeJudgments = REPO_JUDGMENTS,
                   house: House | None = None) -> list[dict]:
    """Gli episodi di un giorno, nella forma che `report.build_report` riceve.

    Ogni episodio e' `{"genere", "protagonista", "inizio", "fine",
    "corpo_base"}`: `fine` a `None` quando a fine giornata e' ancora in corso.
    **Legge soltanto l'archivio** -- `store.readings` (i cambi del giorno) e
    `store.last_before` e `store.transitions` (cio' che era gia' in corso a
    mezzanotte, rigiocato dentro la finestra del grezzo) -- e non
    scrive niente: estratta da `aggregate_day` il 17/09/2026 perche' la cronaca
    si possa costruire senza le misure (spec 2026-09-16 §1, misura 10).

    **Il genere e il riposo vengono da `judgments`** (spec §5): in produzione
    l'istantanea viva, `app["type_judgments"]`; il predefinito `REPO_JUDGMENTS`
    e' il solo seme del repo. Un episodio di `funzionamento`, `sicurezza` o
    `presenza` e' aperto quando lo stato non e' a riposo per il suo soggetto
    (`_is_on`); un `guasto` apre su qualunque condizione e chiude su `chiuso`.

    **Un'entita' che non risponde e' una voce anche lei** (Task 1.4 degli
    attori, Passo 3; D5 «raccolte», 06/10/2026): `unavailable`, `unknown`,
    `none` o il vuoto aprono un'assenza col genere delle condizioni di
    sistema, raccolta per istanza quando entita' della stessa istanza
    mancano nello stesso istante (`_absences`); l'episodio in corso si chiude con `interrotto`, e al
    ritorno ne comincia uno nuovo.

    **Il corpo porta `nome`, quando il grezzo del giorno lo portava**
    (fetta «il nome», 07/09/2026): il nome amichevole SALVATO al momento
    del cambio (`store.py::_migration_5`), non risolto ora dall'anagrafe --
    un resoconto sopravvive ai 22 giorni del grezzo e all'entita' stessa, e
    un nome risolto dopo tornerebbe a essere l'`entity_id` grezzo proprio
    sulle voci piu' vecchie. Il campo **tace** quando non c'e' (le righe
    scritte prima della colonna, le condizioni di sistema, le entita' su cui
    HA non scrive l'attributo): mai un `nome: null`, e chi legge mostra
    allora l'identificatore DICENDO che e' un identificatore.

    **Il corpo porta `classe`, quando il grezzo del giorno la portava**
    (fetta «lo stato», 07/09/2026): la `device_class` che Home Assistant
    dichiarava sull'entita' al momento del cambio. Non e' un dato in piu'
    «per ogni evenienza»: e' il secondo dei quattro gradini con cui HA
    traduce uno stato, e senza di lei un rilevatore di fumo scattato si
    leggerebbe «Acceso» invece di «Rilevato» (misurato dal vivo il
    07/09/2026). Tace come `nome` quando non c'e'. Vedi `close()` qui
    sotto e `proxy/state_translations.py`.
    """
    return _episodes(store=store, day=day, timezone=timezone, judgments=judgments,
                     house=house)[0]


def _episodes(*, store, day: str, timezone: str | None, judgments: TypeJudgments,
              house: House | None) -> tuple[list[dict], set[str]]:
    """`build_episodes`, piu' i soggetti che il grezzo ha ancora prima del
    giorno, dentro la finestra: la stessa lettura, per chi rifa' una cronaca
    (`rebuild_chronicle`, A-39 del registro: prima la chiedeva due volte)."""
    from_ts, to_ts = day_boundaries(day, timezone)
    rows = store.readings(from_ts=from_ts, to_ts=to_ts)

    # **I bilanci non entrano piu' qui** (15/09/2026). Servivano a due cose:
    # diventare un oggetto, e sopprimere gli episodi individuali dei loro
    # membri. La prima e' uscita con gli oggetti; la seconda non ha piu'
    # oggetto, perche' gli episodi di energia sono usciti anche loro -- un
    # contatore e' un numero, e i numeri stanno fra le misure, dove il
    # bilancio arriva per la sua ricetta.

    # **Le assenze si SEPARANO, non si buttano** (Task 1.4 degli attori,
    # Passo 3; D5 «raccolte», decisione del proprietario del 06/10/2026).
    # `unavailable`/`unknown` (`type_vocabulary.unknown_states()`) e, dal
    # 17/09/2026, `none` e il vuoto (`ABSENT_STATE_FORMS`) sono lo stesso
    # fatto: la fonte non risponde. Non sono il riposo di nessuno -- in
    # NESSUN ramo uno di loro apre o chiude un episodio come se fosse uno
    # stato della casa -- ma non sono nemmeno niente: dal 06/10/2026 sono una
    # VOCE della cronaca, col genere delle condizioni di sistema
    # (`SYSTEM_GENRE`), e interrompono l'episodio in corso.
    #
    # **Fino alla regola 3 si saltavano qui, prima di ogni ramo**, e il
    # salto aveva una ragione vera: un riavvio li fa attraversare a ogni
    # entita', e filtrarli a valle li faceva significare due cose diverse
    # (riposo in un ramo, salto nell'altro). Ma il salto rendeva invisibile
    # il buco: misurato il 05/10/2026 sulla casa, una luce rimasta
    # `unavailable` per tre giorni risultava «accesa» per tre giorni. La
    # ragione resta -- un'assenza non e' mai un riposo -- e la forma cambia:
    # l'assenza e' un fatto della FONTE, non della casa, e ha la sua voce.
    #
    # **Le righe ci sono gia'**: `watcher.watch_reading` scrive ogni cambio
    # di stato di un soggetto guardato, `unavailable` compreso (tranne i
    # `sensor` con statistiche, che non scrive mai). Mancano quelle che
    # l'add-on non ha visto -- un riavvio di Home Assistant lo scollega -- e
    # quelle non si inventano qui (vedi la fine di `_episodes`).
    absent = unknown_states() | ABSENT_STATE_FORMS.value

    def is_absence(row: dict) -> bool:
        return (str(row["a"] or "").strip().lower() in absent
                and not row["soggetto"].startswith(NOT_ENTITY_PREFIXES))

    # Il nome amichevole del soggetto, preso dal GREZZO di questo giorno --
    # mai dall'anagrafe di oggi (`store.py::_migration_5`: risolverlo dopo
    # attribuirebbe a ieri il nome di oggi, e per un oggetto piu' vecchio
    # dei 22 giorni di grezzo non ci sarebbe piu' niente da risolvere).
    #
    # **Il primo non vuoto vince**, e la regola vale per tutti e due i modi
    # in cui un episodio nasce qui sotto (lo stato ereditato da prima di
    # mezzanotte e il ciclo apri/chiudi del giorno): uno solo, non due che
    # possono divergere. Un
    # `None` non e' un nome, e' l'assenza di uno -- saltarlo per prendere il
    # nome che una riga successiva dello STESSO soggetto, nello STESSO
    # giorno, dichiara davvero non inventa niente. E' anche il caso vero del
    # giorno dell'aggiornamento: i cambi scritti prima della colonna non lo
    # portano, quelli scritti dopo si', e il proprietario legge la pagina
    # proprio quel giorno.
    # **`entity_names`, non `names`: sono due cose diverse.** Qui vivono i
    # nomi amichevoli delle ENTITA', letti dal grezzo e per chiave
    # l'`entity_id`; il parametro `names` di `aggregate_day` porta i nomi dei
    # DISPOSITIVI, per chiave l'id del dispositivo, e serve alle misure.
    #
    # Fino al 15/09/2026 si chiamavano tutt'e due `names`, e questa riga
    # cancellava il parametro. Il risultato si e' letto nella prima analisi
    # vera: l'analista parlava al proprietario in esadecimale -- «513a6661 ·
    # prelievo» -- e sul resoconto del giorno **zero misure su 73** portavano
    # un nome.
    #
    # **Prima le righe vere, poi quelle d'assenza** (Passo 3): un'assenza
    # porta il nome che Home Assistant le ha scritto, ma non deve scavalcare
    # quello di un episodio dello stesso giorno, che e' il nome di sempre.
    entity_names: dict[str, str] = {}
    for r in sorted(rows, key=is_absence):
        name = r.get("friendly_name")
        if name and r["soggetto"] not in entity_names:
            entity_names[r["soggetto"]] = name

    open_episodes: dict[str, dict] = {}
    # **Cio' che era gia' in corso quando il giorno e' cominciato.** Un fatto
    # che DURA non ha cambi dentro il giorno: comincia prima. Leggere solo la
    # finestra del giorno lo rende invisibile, e non e' un caso di scuola --
    # misurato sulla casa vera il 10/09/2026, gli otto termostati hanno
    # prodotto otto oggetti il 06/09 (il loro ultimo cambio vero) e **zero**
    # il 07, l'08 e il 09, mentre erano accesi tutto il tempo.
    #
    # L'episodio nasce con la sua data d'inizio **vera**, non con la
    # mezzanotte: dire che il riscaldamento e' partito alle 00:00 sarebbe una
    # bugia sul quando, ed e' proprio il quando che l'analista guarda.
    #
    # Solo i generi che aprono e chiudono sullo stato (`_STATE_GENRES`). Il
    # `guasto` ha gia' il suo meccanismo attraverso i riavvii
    # (`watcher.rebuild_conditions`), e riseminarlo anche qui sarebbero due
    # risposte alla stessa domanda.
    #
    # **L'inizio e' quello della sequenza, non l'ultima riga** (Task 1.4 degli
    # attori, Passo 2, 05/10/2026; voce C7 dell'audit). Fino a quel giorno si
    # prendeva l'ultima riga del soggetto prima di mezzanotte: dopo un buco --
    # `on`, `unavailable`, `on` -- era la riga di RITORNO, e l'episodio
    # nasceva all'ora del ritorno; e se l'ultima riga era l'`unavailable`, il
    # soggetto si saltava, cioe' l'`unavailable` CHIUDEVA, contro la regola
    # scritta sopra. Misurato sulla casa vera: 21 delle 85 voci sbagliate fra
    # il 30/09 e il 04/10 avevano l'inizio alla riga di ritorno. Ora le
    # transizioni del soggetto si RIGIOCANO con la regola del ciclo del giorno
    # (`_replay_open`), e l'episodio in corso a mezzanotte e' quello che il
    # ciclo avrebbe aperto: stesso inizio, stesso stato d'apertura, nella
    # cronaca di ieri e in quella di oggi.
    #
    # **Dentro una finestra dichiarata**: `READING_RETENTION_S` contata
    # dall'inizio del giorno, la vita che il grezzo promette. Una riga piu'
    # vecchia esiste solo se la potatura non e' ancora girata, e la cronaca
    # di un giorno non deve dipendere da quello.
    #
    # **Solo per chi e' dentro lo scope di adesso** (`store.is_watched`): chi
    # ne e' uscito non ha piu' righe scritte, e la sua riga ereditata
    # resterebbe aperta per sempre -- misurato: 4 voci fra il 30/09 e il
    # 04/10 da un dispositivo fuori dallo scope, con una riga dell'11/09. Le
    # sue righe DENTRO il giorno restano storia del giorno.
    #
    # **Anche un'assenza si eredita** (Passo 3): chi a mezzanotte non
    # risponde e' assente anche oggi, dall'inizio vero. Si rigioca chi ha un
    # genere di stato e chi ha per ultima riga un'assenza -- gli altri non
    # hanno niente in corso.
    window_start = from_ts - READING_RETENTION_S
    before = store.last_before(from_ts, since_ts=window_start)
    subjects_before = {r["soggetto"] for r in before}
    candidates = [r["soggetto"] for r in before
                  if (genre_for(r["soggetto"], r.get("device_class"),
                                judgments=judgments) in _STATE_GENRES or is_absence(r))
                  and store.is_watched(r["soggetto"])]
    replayed, missing_before = _replay_open(
        store.transitions(candidates, from_ts=window_start, to_ts=from_ts),
        judgments=judgments, absent=absent)
    for subject, (genre, r) in replayed.items():
        open_episodes[subject] = {
            "genere": genre, "inizio": r["quando_ts"], "stato": r["a"],
            "classe": r.get("device_class")}
        if r.get("friendly_name") and subject not in entity_names:
            entity_names[subject] = r["friendly_name"]
    # Le assenze in corso: `{soggetto: {inizio, stato, classe}}`. Quelle
    # finite: `stretches`, i tratti che diventano voci in fondo (`_absences`).
    missing: dict[str, dict] = {}
    stretches: list[dict] = []
    for subject, r in missing_before.items():
        missing[subject] = {"inizio": r["quando_ts"], "stato": r["a"],
                            "classe": r.get("device_class")}
        if r.get("friendly_name") and subject not in entity_names:
            entity_names[subject] = r["friendly_name"]
    # Gli episodi chiusi (o ancora aperti a fine giornata), nell'ordine in cui
    # `close()` li consegna.
    episodes: list[dict] = []
    # I cambi di ATTRIBUTO del giorno, per soggetto: `[(istante, {nome:
    # valore}), ...]` in ordine cronologico. Sono le righe che l'osservatore
    # scrive quando cambia un attributo che il sapere ha dichiarato utile
    # (`mind/watcher.py`, spec §5.4) -- e senza di loro l'esempio fondativo
    # del cervello non e' rispondibile: lo stato di un termostato e' `heat` e
    # resta `heat`, mentre `hvac_action` dice quando la casa e' arrivata in
    # temperatura.
    attribute_changes: dict[str, list[tuple[float, dict]]] = {}

    def close(subject: str, when: float | None) -> None:
        o = open_episodes.pop(subject, None)
        if o is None:
            return
        base_body = {"stato": o["stato"]}
        # Il nome amichevole, quando il grezzo del giorno lo portava. Tace
        # come ogni altra chiave che non ha niente da dire: un `nome: null`
        # sarebbe un buco travestito da dato, e la pagina ha gia' la sua
        # regola per quando il nome manca (mostra l'identificatore DICENDO
        # che e' un identificatore, mai un nome dedotto dall'`entity_id`).
        subject_name = entity_names.get(subject)
        if subject_name:
            base_body["nome"] = subject_name
        # La classe che Home Assistant dichiarava sull'entita' al momento del
        # cambio (`device_class` nel grezzo, `classe` qui -- il nome italiano
        # che l'anagrafe usa gia' ovunque per la stessa cosa). Non e' un
        # doppione del grezzo: il `resoconto` vive piu' a lungo dei `cambi`
        # (22 giorni), esattamente come per `nome`.
        #
        # **Perche' serve, e non e' un "per ogni evenienza"**: e' il SECONDO
        # gradino con cui Home Assistant traduce uno stato
        # (`helpers/translation.py:480-486`, trascritto in
        # `proxy/state_translations.py`), e senza di lei quel gradino non
        # potrebbe mai rispondere. Misurato dal vivo il 07/09/2026 sulla casa:
        # `component.binary_sensor.entity_component.smoke.state.on` e'
        # «Rilevato», mentre `..._.state.on` -- l'unico gradino raggiungibile
        # senza classe -- e' «Acceso». Un rilevatore di fumo scattato
        # leggerebbe «Acceso».
        #
        # Tace quando non c'e', come ogni altra chiave del corpo. Le voci
        # aggregate PRIMA di questa riga non la portano e non si riempiono a
        # posteriori: cadono sul terzo gradino, che e' la verita' («di quella
        # riga non sappiamo la classe»), non un'invenzione.
        if o.get("classe"):
            base_body["classe"] = o["classe"]
        # `dominio`/`titolo` esistono solo per un guasto (sopra), e solo
        # quando la riga che ha aperto l'episodio li portava: tacciono come
        # ogni altra chiave del corpo che non ha niente da dire, non
        # diventano mai `null`.
        if o.get("dominio"):
            base_body["dominio"] = o["dominio"]
        if o.get("titolo"):
            base_body["titolo"] = o["titolo"]
        # **Cosa hanno fatto gli attributi MENTRE l'episodio durava.** E'
        # il lettore della colonna `attributes` del grezzo, e la ragione per
        # cui quella colonna esiste: un episodio di riscaldamento che porta
        # `hvac_action: heating -> idle alle 16:30` risponde alla domanda
        # fondativa del cervello, che prima di oggi non era rispondibile.
        #
        # Dentro la finestra dell'episodio, estremi compresi a sinistra e
        # esclusi a destra -- la stessa convenzione di
        # `mind/operations.Period.contains`, una sola in tutto il prodotto.
        # Un episodio ancora aperto (`when is None`) prende tutto cio' che
        # viene dopo il suo inizio.
        # **La foto d'apertura c'e', e senza di lei meta' della colonna
        # `attributes` restava scritta e non letta** (Fable 5.1, 13/09/2026):
        # la riga del cambio di STATO porta gia' gli attributi voluti -- il
        # `hvac_action: heating` delle 15:30 -- e quel primo istante spariva
        # dal corpo, che cominciava dal primo cambio successivo.
        #
        # **La forma e' una FOTO, non un delta**, e va detto: ogni voce porta
        # tutti gli attributi voluti di quel momento, non il solo che si e'
        # mosso. Chi legge due voci vicine vede cosa e' cambiato confrontandole;
        # chi ne legge una sola sa lo stato di tutti. Il delta sarebbe piu'
        # compatto e meno leggibile da solo, e questa e' la cronaca di un
        # giorno, non un flusso da ricostruire.
        during = list(o.get("attributi_apertura") or [])
        during += [(instant, values)
                   for instant, values in attribute_changes.get(subject, [])
                   if instant > o["inizio"] and (when is None or instant < when)]
        if during:
            base_body["attributi"] = [
                {"quando_ts": instant, "valori": values} for instant, values in during]
        # `comparso_ts`: SOLO una voce di log lo porta (`_reading_row`
        # rilegge `None` per un `problema:`/`integrazione:`/`automazione:`,
        # che non lo dichiarano mai). Non e' `inizio`: `inizio` e' quando NOI l'abbiamo
        # scritto (l'orologio del giro, vedi `watcher.py::watch_system` e
        # `store.py::_migration_4`), `comparso_ts` e' quando HA dice che e'
        # cominciato -- «rilevato stamattina, va avanti dal 2» invece di una
        # data sola. `is not None`, non un controllo di verita': uno zero
        # epoch sarebbe un istante vero (per quanto assurdo su una casa
        # vera), non un campo vuoto.
        if o.get("comparso_ts") is not None:
            base_body["comparso_ts"] = o["comparso_ts"]
        # Perche' finisce, quando non l'ha chiuso uno stato visto: la fonte
        # di adesso, con la sua causa (vedi la chiusura sotto il ciclo). Tace
        # per ogni episodio finito normalmente.
        if o.get("chiusa_dalla_fonte"):
            base_body["chiusa_dalla_fonte"] = o["chiusa_dalla_fonte"]
        # Finito perche' la fonte ha smesso di rispondere, non per uno stato
        # visto (Passo 3): l'assenza che l'ha interrotto e' la voce dopo.
        if o.get("interrotto"):
            base_body["interrotto"] = True
        episodes.append({"genere": o["genere"], "protagonista": subject,
                        "inizio": o["inizio"], "fine": when,
                        "corpo_base": base_body})

    for r in rows:
        subject = r["soggetto"]
        # **La riga di solo attributo si raccoglie PRIMA di ogni giudizio di
        # genere**, e poi non prosegue: non apre e non chiude niente -- lo
        # stato di partenza e quello d'arrivo sono lo stesso -- ma dice cosa
        # ha fatto la grandezza mentre l'episodio durava (spec §5.4). Senza
        # questa raccolta la colonna `attributes` del grezzo sarebbe scritta
        # e non letta da nessuno.
        if r["da"] == r["a"] and r.get("attributes"):
            try:
                values = json.loads(r["attributes"])
            except (TypeError, ValueError):
                # Una riga vecchia o storta non ferma la giornata: si salta.
                values = None
            if isinstance(values, dict) and values:
                attribute_changes.setdefault(subject, []).append(
                    (r["quando_ts"], values))
            continue
        # **L'assenza, prima di ogni giudizio di genere** (Passo 3): vale per
        # ogni entita' -- anche un sensore, che episodi non ne apre -- e
        # interrompe cio' che e' in corso. Il primo stato vero dopo la chiude,
        # e poi prosegue come ogni riga: se e' lo stesso stato di prima, apre
        # un episodio NUOVO, perche' quello di prima e' finito col buco.
        if is_absence(r):
            if subject in open_episodes:
                open_episodes[subject]["interrotto"] = True
                close(subject, r["quando_ts"])
            missing.setdefault(subject, {"inizio": r["quando_ts"], "stato": r["a"],
                                         "classe": r.get("device_class")})
            continue
        if subject in missing:
            stretches.append({**missing.pop(subject), "soggetto": subject,
                              "fine": r["quando_ts"]})
        genre = genre_for(subject, r.get("device_class"), judgments=judgments)
        if genre is None:
            continue
        if genre == SYSTEM_GENRE:
            # Solo condizioni di sistema arrivano qui (vedi `genre_for`). La
            # convenzione si rovescia con la fetta «il guasto e il
            # riavvio»: prima "aperto" apriva e tutto il resto chiudeva.
            # Ora `a` porta la CONDIZIONE VERA (`setup_retry`,
            # `setup_error`, ...), quindi chiude solo "chiuso" ed e' tutto
            # il resto ad aprire. Le righe scritte prima della migrazione 3
            # portano ancora "aperto" e continuano ad aprire: non serve
            # nessun caso a parte.
            if r["a"] == "chiuso":
                close(subject, r["quando_ts"])
            else:
                # Sovrascrive senza `if subject not in open_episodes` (a
                # differenza del ramo dei tre generi di stato, sotto): due
                # aperture di fila per lo stesso soggetto perderebbero la
                # prima data d'inizio. Non per una guardia qui, ma per la
                # disciplina dello SCRITTORE, in un altro file:
                # `watcher.py::watch_system` scrive una nascita solo per
                # `set(open_now) - self._conditions`, quindi un soggetto gia'
                # malato (in `self._conditions`) che passa da `setup_retry` a
                # `setup_error` non produce una seconda riga d'apertura --
                # SALVO l'eccezione che `watcher.py::rebuild_conditions`
                # dichiara nel suo docstring: se l'archivio non risponde
                # all'avvio, `self._conditions` riparte da vuoto, e
                # `watch_system` tratta di proposito ogni guasto gia' aperto
                # come nuovo (e' il prerequisito della garanzia attraverso i
                # riavvii: senza la riseminatura, sarebbe la regola, non
                # l'eccezione). E' un'eccezione dichiarata e voluta, non un
                # buco silenzioso -- e non e' una ragione per una guardia qui.
                open_episodes[subject] = {
                    "genere": genre, "inizio": r["quando_ts"],
                    "stato": r["a"],
                    "dominio": r.get("domain"), "titolo": r.get("title"),
                    "comparso_ts": r.get("first_occurred"),
                }
            continue
        if genre in _STATE_GENRES:
            # **Una forma sola per i tre generi** (spec 2026-09-16 §5): aperto
            # quando lo stato non e' a riposo per il soggetto, chiuso quando lo
            # e'. Il genere e' diverso, la forma no.
            #
            # **La presenza non ha piu' un ramo suo.** Fino al 17/09/2026 qui
            # c'era un confronto scritto a mano con `"home"`; ora `home` e' la
            # riga `riposo` di `person` e `device_tracker` nel seme, e l'episodio
            # di una persona resta l'ASSENZA, «fuori casa dalle 8:10 alle
            # 17:34», non il ritorno. Trattare anche il ritorno come un secondo
            # episodio duplicherebbe lo stesso fatto (l'orario del rientro e'
            # gia' `fine_ts` dell'assenza). Un sensore di presenza a cui la
            # casa scrive il genere `presenza` apre a `on` e chiude a `off`,
            # il riposo del suo dominio: lo dicono `cosa` e `classe`.
            #
            # `if subject not in open_episodes`: un cambio fra due stati non a
            # riposo -- una persona che da `not_home` entra nella zona
            # `ufficio`, una TV da `playing` a `paused` -- non riapre
            # l'episodio e non ne azzera inizio e stato.
            if _is_on(r["a"], subject, r.get("device_class"), judgments):
                if subject not in open_episodes:
                    open_episodes[subject] = {"genere": genre, "inizio": r["quando_ts"],
                                              "stato": r["a"], "classe": r.get("device_class"),
                                              "attributi_apertura": _opening_attributes(r)}
            else:
                close(subject, r["quando_ts"])
            continue
        # **Un contatore non apre niente.** Fino al 15/09/2026 qui si
        # annotava che il soggetto era un contatore, per costruirgli dopo
        # un episodio di energia; quell'episodio e' uscito, perche' un
        # contatore non ha uno stato, ha un numero -- e i numeri stanno
        # fra le misure, dove la ricetta li porta con la copertura che
        # l'episodio non aveva. Dal 16/09/2026 nemmeno il genere `energia`
        # esiste piu' (spec 2026-09-16 §5, D2): l'istantanea ammette solo i
        # quattro generi trattati qui sopra, e nessuna riga arriva fin qui.

    # **Una fonte che Home Assistant non nomina piu' chiude il suo episodio**
    # (Task 1.4 degli attori, Passo 1, 05/10/2026). Misurato quel giorno sulla
    # casa vera: 60 delle 85 voci sbagliate fra il 30/09 e il 04/10 erano
    # episodi di 12 entita' spente dal proprietario con la loro istanza,
    # rimasti «in corso» per giorni. Un'entita' spenta o rimossa non manda un
    # ultimo cambio (`watcher.watch_reading` scarta `new_state` a `None`), e
    # nessuno chiedeva alla fonte se fosse ancora viva.
    #
    # **Si chiede a `House.source`, con la fonte di ADESSO**, non a una soglia
    # nostra e non al grezzo: e' la casa di chi costruisce la cronaca. Solo gli
    # stati in cui Home Assistant non ne parla piu' (`ENDED_SOURCE_STATES`:
    # spenta o sparita); `non_disponibile` e `integrazione_ferma` possono
    # tornare da sole, e restano al terzo passo, quello delle assenze.
    #
    # **Il quando e' la sua ultima riga nel grezzo** (`store.last_seen`, di
    # qualunque stato e giorno): l'ultima volta che Home Assistant ne ha
    # parlato -- spesso l'`unavailable` di un riavvio, che il salto qui sopra
    # ignora. Se e' DOPO la fine del giorno, a fine giornata la fonte parlava
    # ancora e l'episodio resta aperto come sempre; se e' PRIMA dell'inizio
    # (un ereditato), l'episodio e' finito prima di questo giorno e non ci
    # entra. Se l'ultima riga e' quella che l'ha aperto, la voce dura zero:
    # di dopo non si sa niente, e `chiusa_dalla_fonte` lo dice.
    #
    # Senza la casa (`house=None`: le prove, o un archivio dell'anagrafe non
    # collegato) niente si chiude: non si dice finita una fonte che non si e'
    # potuta guardare.
    #
    # **Vale anche per un'assenza in corso** (Passo 3): un'entita' andata
    # `unavailable` e poi spenta dal proprietario non resta «assente, in
    # corso» per i ventidue giorni del grezzo. Stessa regola, stesso quando.
    if house is not None:
        ended = {}
        for subject in (*open_episodes, *missing):
            source = house.source(subject)
            if source is not None and source["stato"] in ENDED_SOURCE_STATES:
                ended[subject] = source
        last_seen = store.last_seen(ended) if ended else {}
        for subject, source in ended.items():
            when = last_seen.get(subject)
            if when is None or when >= to_ts:
                continue
            mark = {"stato": source["stato"], "causa": source["causa"],
                    "spenta_da": source["spenta_da"]}
            if subject in missing:
                stretch = missing.pop(subject)
                if when >= from_ts:
                    stretches.append({**stretch, "soggetto": subject, "fine": when,
                                      "chiusa_dalla_fonte": mark})
                continue
            if when < from_ts:
                open_episodes.pop(subject)
                continue
            open_episodes[subject]["chiusa_dalla_fonte"] = mark
            close(subject, when)

    # Cio' che a fine giornata e' ancora in corso resta APERTO: `fine_ts` a
    # `None` e' un fatto, zero direbbe «finita subito».
    for subject in list(open_episodes):
        close(subject, None)
    for subject, stretch in missing.items():
        stretches.append({**stretch, "soggetto": subject, "fine": None})

    # **Le assenze diventano voci, raccolte come le dichiara Home Assistant**
    # (`_absences`), e prendono il loro posto nell'ordine della cronaca: le
    # chiuse per fine, poi le aperte per inizio (`_chronicle_position`).
    stretches = _gathered_by_disconnection(stretches, episodes)
    if stretches:
        for entry in _absences(stretches, house=house, names=entity_names):
            key = _episode_position(entry)
            index = next((i for i, e in enumerate(episodes)
                          if _episode_position(e) > key), len(episodes))
            episodes.insert(index, entry)
    # **Il riavvio di Home Assistant ha la sua voce dal 06/10/2026**, e la
    # prende da una fonte che lo dichiara, non da una soglia nostra: la
    # finestra in cui l'add-on e' rimasto scollegato, misurata dal client
    # dalla caduta della connessione a quando Home Assistant si dichiara
    # avviato (`HAClient.add_disconnection_listener`) e scritta
    # dall'osservatore (`Watcher.record_disconnection`); alla riconnessione
    # `Watcher.realign` riallinea anche le entita' guardate allo stato che
    # Home Assistant dichiara. Fino ad allora il
    # grezzo non ne portava traccia: durante il riavvio l'add-on e'
    # scollegato, e le righe di andata a `unavailable` non arrivano mai
    # (misurato sul 29/09/2026). La voce non dice «riavvio»: un guasto di rete
    # ha la stessa forma, e da qui non si distinguono.
    # **L'energia non e' un EPISODIO** (15/09/2026, con gli oggetti).
    # Qui si costruiva un episodio per ogni contatore -- valore iniziale,
    # finale, differenza -- e il suo unico lettore era l'oggetto. Nella
    # cronaca quella voce direbbe «quando, chi, genere: energia, cosa:
    # niente»: un contatore non ha uno stato, ha un numero, e un numero
    # sta fra le MISURE.
    #
    # **Verificato dal vivo prima di toglierlo**: i tre contatori della
    # casa che avevano un episodio di energia sono tutti coperti da una
    # ricetta -- `energia_totale_periodo` (somma_periodo) per la presa,
    # `potenza_media_min_max` per la potenza, il bilancio per l'inverter.
    # I numeri non si perdono: cambiano posto, e prendono la copertura che
    # l'episodio non aveva.

    # **Gli OGGETTI sono usciti** (spec §13, 15/09/2026): qui si costruiva
    # un secondo strato -- episodio piu' comprimari piu' misure -- che viveva
    # accanto al resoconto e diceva le stesse cose in un'altra forma.
    #
    # **Misurato sulla casa vera prima di cancellarlo**: 200 oggetti, e i
    # comprimari erano **zero su 200** -- il campo `misure` vuoto in tutti.
    # La perdita che si temeva non esisteva: non c'era niente da perdere.
    # E ogni giorno che aveva oggetti (26/08 -> 14/09) aveva gia' il suo
    # resoconto, quindi nemmeno la storia si e' persa.
    return episodes, subjects_before


def _episode_position(episode: dict) -> tuple:
    """`_chronicle_position` di un episodio non ancora diventato voce: la
    stessa regola d'ordine, una sola."""
    return _chronicle_position({"fine_ts": episode["fine"], "quando_ts": episode["inizio"]})


def _gathered_by_disconnection(stretches: list[dict], episodes: list[dict]) -> list[dict]:
    """I tratti d'assenza che cominciano DENTRO una finestra di scollegamento
    entrano nella voce di quella finestra, in `assenti`; torna gli altri.

    E' la ragione della decisione del proprietario del 06/10/2026
    («Riallinea»): le assenze dovute al riavvio non devono sembrare guasti.
    Un'entita' che Home Assistant dichiara `unavailable` alla riconnessione,
    con un istante dentro la finestra, e' sparita mentre l'add-on non
    guardava: la voce che lo racconta e' quella della finestra, non quella
    della sua istanza (che salirebbe in primo piano).

    **Dentro, estremi compresi, e solo l'inizio.** La finestra e' un fatto,
    non un margine nostro: comincia alla caduta della connessione e finisce
    quando Home Assistant si DICHIARA avviato (`RUNNING`, o l'evento
    `homeassistant_started`: `HAClient.add_disconnection_listener`), non al
    ritorno del socket -- il websocket risponde mentre il nucleo e' ancora in
    avvio, e le entita' che le integrazioni lente lasciano `unavailable` in
    quel tratto sono del riavvio (revisione, giro 41). Un tratto cominciato
    prima era gia' un'assenza quando la connessione e' caduta, e resta la
    voce sua; uno cominciato dopo l'avvio dichiarato e' un fatto della casa
    avviata. **Cosa non e' stato misurato**: quanti `unavailable` Home
    Assistant scriva dopo `homeassistant_started` (un'integrazione che ritenta
    oltre l'avvio). Quelli restano voci dell'istanza.
    """
    windows = [e for e in episodes if e["protagonista"] == DISCONNECTION_SUBJECT]
    if not windows:
        return stretches
    remaining = []
    for stretch in stretches:
        window = next((w for w in windows
                       if w["inizio"] <= stretch["inizio"]
                       and (w["fine"] is None or stretch["inizio"] <= w["fine"])), None)
        if window is None:
            remaining.append(stretch)
            continue
        window["corpo_base"].setdefault("assenti", []).append(_absent(stretch))
    for window in windows:
        if "assenti" in window["corpo_base"]:
            window["corpo_base"]["assenti"].sort(key=lambda a: (a["quando_ts"], a["chi"]))
    return remaining


def _absences(stretches: list[dict], *, house: House | None,
              names: dict[str, str]) -> list[dict]:
    """I tratti d'assenza di un giorno, come voci della cronaca (Task 1.4 degli
    attori, Passo 3; D5 «raccolte»), nella forma di `build_episodes`.

    **Raccolti come li dichiara Home Assistant**: l'istanza dell'integrazione
    di ogni entita' (`config_entry_id` nel registro, chiesta a `House.source`,
    la fonte della Tappa 3). Entita' della stessa istanza assenti nello STESSO
    istante -- tratti che si sovrappongono, anche a catena -- sono una voce
    sola, per l'istanza: soggetto `integrazione:` piu' l'id, come per
    un'istanza in errore, `dominio` per il nome, e `assenti`, ogni entita' col
    suo intervallo (`chi`, `quando_ts`, `fine_ts`), il suo `stato` e, se c'e',
    `chiusa_dalla_fonte` -- la forma della voce di un'entita' sola
    (`_absent`) -- perche' la voce si legga da sola anche quando le entita'
    non sono tornate insieme.

    **Lo `stato` dell'istanza e' quello di tutte, o nessuno** (G17-3,
    06/10/2026): se le entita' sono sparite con lo stesso stato la voce lo
    porta; se gli stati differiscono (`unavailable` e `unknown`) la voce non
    ne porta nessuno, e i due stanno in `assenti`. Fino ad allora prendeva lo
    stato del primo tratto, e diceva `unavailable` di chi era `unknown`.

    Un tratto che non
    ne tocca nessun altro della sua istanza e' la voce della sua entita':
    `stato` e' cio' che Home Assistant ha scritto (`unavailable`, `unknown`,
    `none`, il vuoto), con nome e classe come per un episodio.

    **«Insieme», non «tutte»: misurato prima di scegliere.** La decisione del
    proprietario dice «un'integrazione che sparisce tutta insieme». Sulla casa
    (rigioco del 30/09-04/10, 06/10/2026) i buchi brevi dell'irrigazione sono
    16 entita' su 20 guardate della stessa istanza: in ognuno dei quattro
    dispositivi un sensore di durata resta vivo. Con «tutte» nessun buco
    diventava la voce dell'istanza, e un giorno passava da 10 a 91 voci.
    Nessun numero nostro decide quando un gruppo e' un'integrazione: basta che
    due sue entita' manchino nello stesso istante.

    Il genere e' quello delle condizioni di sistema (`SYSTEM_GENRE`): la voce
    parla della FONTE, non della casa, e ha la loro forma -- nasce, dura,
    finisce o resta aperta. Senza la casa (`house=None`) non si raccoglie
    niente: ogni tratto e' la voce della sua entita'.

    **Il limite, dichiarato**: si raccoglie fra i tratti di QUESTO giorno. Un
    tratto finito prima di mezzanotte non si eredita, quindi due entita'
    sparite insieme ieri sera, una tornata prima di mezzanotte e l'altra dopo,
    sono la voce dell'istanza ieri e la voce dell'entita' rimasta oggi.
    """
    instance_of: dict[str, dict | None] = {}
    if house is not None:
        for subject in {s["soggetto"] for s in stretches}:
            source = house.source(subject)
            instance_of[subject] = (source or {}).get("istanza")

    by_instance: dict[str, list[dict]] = {}
    alone: list[dict] = []
    for stretch in stretches:
        instance = instance_of.get(stretch["soggetto"])
        if instance:
            by_instance.setdefault(instance["id"], []).append(stretch)
        else:
            alone.append(stretch)

    entries: list[dict] = []
    for instance_id, mine in by_instance.items():
        # Le componenti di tratti che si sovrappongono: in ordine d'inizio, un
        # tratto entra nella componente se comincia prima che lei finisca.
        mine.sort(key=lambda s: (s["inizio"], s["soggetto"]))
        components: list[list[dict]] = []
        reach = None
        for stretch in mine:
            if components and (reach is None or stretch["inizio"] < reach):
                components[-1].append(stretch)
            else:
                components.append([stretch])
                reach = stretch["fine"]
                continue
            reach = (None if reach is None or stretch["fine"] is None
                     else max(reach, stretch["fine"]))
        for component in components:
            if len(component) == 1:
                alone.append(component[0])
                continue
            ends = [s["fine"] for s in component]
            body = {"assenti": [_absent(s) for s in component]}
            states = {s["stato"] for s in component}
            if len(states) == 1:
                body["stato"] = states.pop()
            domain = instance_of[component[0]["soggetto"]].get("dominio")
            if domain:
                body["dominio"] = domain
            entries.append({"genere": SYSTEM_GENRE,
                            "protagonista": INSTANCE_SUBJECT_PREFIX + instance_id,
                            "inizio": component[0]["inizio"],
                            "fine": None if None in ends else max(ends),
                            "corpo_base": body})
    for stretch in alone:
        subject = stretch["soggetto"]
        body = {"stato": stretch["stato"]}
        if names.get(subject):
            body["nome"] = names[subject]
        if stretch.get("classe"):
            body["classe"] = stretch["classe"]
        if stretch.get("chiusa_dalla_fonte"):
            body["chiusa_dalla_fonte"] = stretch["chiusa_dalla_fonte"]
        entries.append({"genere": SYSTEM_GENRE, "protagonista": subject,
                        "inizio": stretch["inizio"], "fine": stretch["fine"],
                        "corpo_base": body})
    return sorted(entries, key=lambda e: (_episode_position(e), e["protagonista"]))


def _absent(stretch: dict) -> dict:
    """Un'entita' dentro `assenti`: lo stesso fatto della voce di un'entita'
    sola, con la stessa forma -- lo `stato` che Home Assistant ha scritto
    quando e' sparita e, se l'assenza e' finita perche' la fonte e' finita,
    `chiusa_dalla_fonte` (G17-2 e G17-3, 06/10/2026). Senza, `fine_ts`
    direbbe un ritorno che non c'e' stato."""
    absent = {"chi": stretch["soggetto"], "quando_ts": stretch["inizio"],
              "fine_ts": stretch["fine"], "stato": stretch["stato"]}
    if stretch.get("chiusa_dalla_fonte"):
        absent["chiusa_dalla_fonte"] = stretch["chiusa_dalla_fonte"]
    return absent


def aggregate_day(*, store, day: str, timezone: str | None,
                  recipes=None, series=None, names=None,
                  silent=None, muted=None,
                  judgments: TypeJudgments = REPO_JUDGMENTS,
                  house: House | None = None) -> int:
    """Scrive il resoconto di un giorno. Torna quante voci di cronaca porta.

    **Il resoconto e' la cronaca piu' le misure** (spec §9): la cronaca sono gli
    episodi di `build_episodes`, che legge il grezzo dell'archivio con
    l'istantanea `judgments`; le misure arrivano gia' lette dal chiamante --
    `recipes` (le ricette dal sapere), `series` (le serie delle entita' che le
    ricette nominano), `names` (i nomi dei DISPOSITIVI, per chiave l'id) e
    `silent` (le entita' che non daranno una serie, col perche') e `muted`
    (le ricette che non possono produrre, una riga per dispositivo:
    `recipes.muted_recipes`) -- e si incontrano in `report.build_report`,
    che e' pura. L'obiettivo e' quello che valeva alla fine di QUEL giorno
    (`store.objective_at`), non quello di oggi.

    **Sincrona, nessuna lettura di rete**: tutto cio' che viene da Home
    Assistant l'ha gia' letto il chiamante (`server.py::_report_ingredients`).

    **Idempotente**: rifare un giorno lo SOSTITUISCE, non lo accoda. Il
    resoconto si costruisce tutto in memoria e si consegna in una scrittura
    sola ad `store.replace_report`, che sostituisce la riga del giorno: niente
    giorno mezzo scritto indistinguibile da uno completo se qualcosa muore a
    meta'. E' esattamente il difetto gemello che il vecchio «costruire» ha gia'
    pagato (accodava invece di sostituire, e le ancore YAML lo nascondevano).

    **In produzione `judgments` e' `app["type_judgments"]`**, l'istantanea viva
    (`server.py::write_day_report`, l'unica strada del resoconto, D-36); il
    predefinito `REPO_JUDGMENTS` e' il solo seme, per le prove.

    **Il bilancio non entra piu' qui, e non produce un genere `"bilancio"`**
    (15/09/2026, con gli oggetti). Fino ad allora questa funzione riceveva un
    parametro `balances` che faceva nascere un oggetto di genere `"bilancio"`;
    quel parametro non esiste piu', e il bilancio vive fra le MISURE, con la
    ricetta del dispositivo scritta nel sapere (il generatore del repo,
    `mind/seed.balance_recipe`, e' uscito il 01/10/2026: le ricette che aveva
    seminato restano).
    """
    episodes = build_episodes(store=store, day=day, timezone=timezone, judgments=judgments,
                              house=house)
    _, to_ts = day_boundaries(day, timezone)
    # **Si scrive SEMPRE, anche senza ricette.** Fino al 15/09/2026 un
    # chiamante che non portava le ricette non faceva scrivere niente, e la
    # ragione era buona: un resoconto con meta' delle misure vuota per un
    # motivo che non riguarda la casa resterebbe li' a dire il falso. Ma quella
    # ragione reggeva finche' c'erano gli OGGETTI a tenere il giorno; tolti
    # quelli, non scrivere vuol dire **perdere il giorno**, e «non e' successo
    # niente» tornerebbe a confondersi con «non l'abbiamo guardato» -- la
    # distinzione per cui il resoconto esiste.
    # **L'impronta dei giudizi viaggia con la cronaca** (spec 2026-09-16 §6):
    # e' cio' che permette al recupero di sapere quali giorni sono nati con un
    # altro giudizio, e al documento di dirlo.
    store.replace_report(day, build_report(
        day=day, episodes=episodes, series=series or {},
        recipes=recipes or {}, names=names or {},
        silent=silent, muted=muted,
        objective=store.objective_at(to_ts),
        judgment=chronicle_mark(judgments)))
    # **Torna quante voci di cronaca ha scritto.** Prima tornava quanti
    # oggetti aveva salvato: e' lo stesso numero detto nella lingua che resta.
    return len(episodes)


def chronicle_is_stale(report: dict, judgments: TypeJudgments) -> bool:
    """Una cronaca e' vecchia se non dice con quale giudizio e' nata, o se e'
    nata con un altro (spec 2026-09-16 §6).

    **L'assenza conta come «un altro»**: i resoconti scritti prima del
    17/09/2026 non portano impronta, e sono proprio quelli che il primo avvio
    deve rifare dentro il grezzo.

    **Anche la regola del codice** (`CHRONICLE_RULE`, dal 05/10/2026): una
    cronaca con l'impronta giusta ma scritta con la regola di prima -- o senza
    regola, cioe' prima di quel giorno -- e' vecchia anche lei.
    """
    written = (report or {}).get("giudizio") or {}
    current = chronicle_mark(judgments)
    return any(written.get(key) != value for key, value in current.items())


def chronicle_mark(judgments: TypeJudgments) -> dict:
    """Con che cosa e' nata una cronaca: l'impronta dei giudizi e la regola
    del codice (`CHRONICLE_RULE`). Una forma sola per chi la scrive
    (`aggregate_day`, `rebuild_chronicle`) e chi la confronta
    (`chronicle_is_stale`)."""
    return {"impronta": judgments.chronicle_fingerprint(), "regola": CHRONICLE_RULE}


def rebuild_chronicle(*, store, day: str, timezone: str | None,
                      judgments: TypeJudgments = REPO_JUDGMENTS,
                      house: House | None = None) -> bool:
    """Rifa' **solo** la cronaca di un giorno col giudizio di adesso. Torna
    `True` se ha riscritto, `False` se quel giorno non ha un resoconto.

    Misure, forme e obiettivo restano quelli scritti: **nessuna lettura di Home
    Assistant, nessuna ricetta riletta** -- le statistiche di un giorno vecchio
    possono non esserci piu', e rifare le misure le perderebbe (spec 2026-09-16
    §6). Gli episodi escono da `build_episodes`, la stessa costruzione di
    `aggregate_day`; la voce di cronaca e l'impronta da `build_report`, che
    resta pura: le misure che calcola su serie e ricette vuote si buttano.

    **Gli episodi EREDITATI da prima del giorno si tengono, a una condizione.**
    Misurato dalla revisione del 17/09/2026: un termostato acceso da venticinque
    giorni entra nella cronaca di oggi per la sua riga d'origine
    (`store.transitions`), e quella riga esce dal grezzo prima del giorno che
    la eredita. Rifare quel giorno perdeva la voce. Una voce scritta che
    **comincia prima dell'inizio del giorno** e che la cronaca rifatta non ha
    (stessa identita': `chi` e `quando_ts`) si tiene se:

    - il grezzo **non ha piu' nessuna riga** di quel soggetto prima del giorno,
      dentro la finestra con cui l'ereditato si costruisce (`_episodes`, la
      stessa lettura: A-39)
      -- se ce l'ha, l'assenza e' un giudizio nuovo (un riposo cambiato), non
      un grezzo perso, e la voce esce;
    - il soggetto ha **ancora un genere** per i giudizi di adesso
      (`genre_for`, con la `classe` della voce): un `nessuno` la toglie.

    Si inserisce dove la cronaca di oggi la metterebbe: le chiuse per `fine_ts`,
    poi le ancora aperte per `quando_ts`, senza spostare le voci rifatte (vedi
    `_chronicle_position`).

    **Il limite, dichiarato**: una voce tenuta cosi' conserva la forma con cui
    era stata scritta -- non si puo' rifare senza la sua riga d'origine -- e
    resta cosi' anche sotto l'impronta nuova. Le voci che cominciano DENTRO il
    giorno non si tengono mai: per questo il recupero non rifa' un giorno che
    puo' aver perso righe per la potatura -- cioe' che comincia prima del taglio
    (`server.py::backfill_one_report`), non un giorno che comincia prima della
    riga piu' vecchia.

    **Il residuo che le due condizioni non coprono: riposo cambiato E riga
    d'origine potata.** Le due condizioni verificano che il grezzo sia sparito
    e che il soggetto abbia ANCORA un genere -- non che il giudizio di OGGI
    avrebbe aperto quella stessa voce. Una voce ereditata puo' quindi restare
    anche quando il giudizio nuovo non l'avrebbe mai aperta cosi' (un riposo
    diventato piu' largo, per esempio): non c'e' modo di accorgersene senza la
    riga d'origine, ed e' gia' potata. Resta com'e', sotto qualunque impronta,
    finche' il giorno non torna raggiungibile dal grezzo -- cioe', superati i
    22 giorni di ritenzione (`mind/store.READING_RETENTION_S`), mai.

    **Un giorno senza resoconto non si tocca**: farlo intero, con le misure,
    e' lavoro del recupero (`server.py::backfill_one_report`), non di questa
    funzione.
    """
    report = store.report(day)
    if report is None:
        return False
    episodes, raw_subjects = _episodes(store=store, day=day, timezone=timezone,
                                       judgments=judgments, house=house)
    rebuilt = build_report(day=day, episodes=episodes, series={}, recipes={}, names={},
                           judgment=chronicle_mark(judgments))
    chronicle = list(rebuilt["cronaca"])
    from_ts, _ = day_boundaries(day, timezone)
    rebuilt_ids = {(v.get("chi"), v.get("quando_ts")) for v in chronicle}
    for entry in report.get("cronaca") or []:
        started = entry.get("quando_ts")
        subject = entry.get("chi")
        if (started is None or started >= from_ts or subject is None
                or (subject, started) in rebuilt_ids or subject in raw_subjects
                or genre_for(subject, entry.get("classe"), judgments=judgments) is None):
            continue
        key = _chronicle_position(entry)
        index = next((i for i, v in enumerate(chronicle)
                      if _chronicle_position(v) > key), len(chronicle))
        chronicle.insert(index, entry)
    store.replace_report(day, {**report, "cronaca": chronicle,
                               "giudizio": rebuilt["giudizio"]})
    return True


def _chronicle_position(entry: dict) -> tuple:
    """Dove una voce sta nella cronaca di un giorno, nell'ordine in cui
    `build_episodes` la consegna: prima le chiuse, nell'ordine in cui si sono
    chiuse (`fine_ts`), poi quelle ancora aperte a fine giornata, nell'ordine in
    cui si sono aperte -- le ereditate prima delle nate nel giorno.

    Serve solo a `rebuild_chronicle` per INSERIRE una voce tenuta: le voci
    rifatte non si riordinano, restano nell'ordine di `build_episodes`.
    """
    end = entry.get("fine_ts")
    if end is not None:
        return (0, float(end))
    return (1, float(entry.get("quando_ts") or 0.0))
