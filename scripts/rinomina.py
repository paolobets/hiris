#!/usr/bin/env python3
"""Il rinominatore: porta all'inglese GLI IDENTIFICATORI, e nient'altro.

**Il confine e' strutturale, non promesso.** Si lavora sui soli token di tipo
NAME: commenti, stringhe e docstring non sono «da evitare», sono fuori
portata per costruzione. E' il mandato del proprietario -- «solo ed
esclusivamente cio' che e' codice» -- reso una proprieta' del meccanismo
invece che una precauzione che qualcuno puo' dimenticare.

**Non indovina.** Sui nomi composti l'inglese inverte l'ordine delle parole
(`unita_vive` non e' `unit_reported`, e' `reported_units`), ci sono
preposizioni che spariscono (`nomi_di_ripiego`) e sigle di confine da non
tradurre (`sanitize_ha_value`: quel `ha` e' Home Assistant, e resta `ha`).
Quindi propone e si ferma: e' la legge del glossario applicata alla
rinomina, «una riga senza prova non e' decisa».

**E la stessa sigla non e' sempre la stessa cosa** (corretto il 31/08:
questo docstring portava `ha_credenziale` come esempio del confine, ed era
falso). In `decisione_modelli.py:653` quel `ha` e' il VERBO -- «il provider
ha una credenziale» -- e il gemello gia' inglese si chiama
`_config_has_credential`, non `ha_credential`. Dieci nomi su dodici sono
Home Assistant e due sono il verbo: nessuna regola meccanica li separa, li
separa la lettura -- che e' la ragione per cui questo strumento propone
invece di applicare.
"""
from __future__ import annotations

import builtins
import keyword
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comune import ROOT, leggi

GLOSSARIO = ROOT / "docs" / "GLOSSARIO.md"

# Le tre tabelle che portano una coppia italiano -> inglese, con la posizione
# della colonna inglese. I «valori di dominio» NON sono qui: il glossario li
# ha rinviati di proposito, con la ragione scritta.
_TABELLE = (
    ("## I concetti", 2),
    ("## Le parole ordinarie", 1),
    ("## I nomi degli strumenti", 2),
)
_SCARTATE = "## Parole scartate durante l'estrazione"

# La sezione «Parole scartate» porta DUE tabelle, e sono l'opposto l'una
# dell'altra: la prima sono parole che restano italiane per sempre, la
# seconda sono forme (singolare/plurale) gia' ricondotte a un lemma che HA
# una riga vera nel glossario. Il confine fra le due si legge
# dall'INTESTAZIONE, non dalla posizione ne' dal conteggio delle tabelle:
# se l'intestazione degli alias cambiasse e il lettore continuasse a cercare
# solo «dov'e' la seconda tabella», le sue righe finirebbero silenziosamente
# fra gli scarti -- il contrario del vero.
_INTESTAZIONE_SCARTI = "| parola uscita dallo script | perche' e' stata scartata |"
_INTESTAZIONE_ALIAS = "| forma uscita dallo script | lemma nel glossario |"


@dataclass
class Glossario:
    mappa: dict[str, str] = field(default_factory=dict)
    omonimi: dict[str, dict[str, str]] = field(default_factory=dict)
    scartate: set[str] = field(default_factory=set)
    alias: dict[str, str] = field(default_factory=dict)

    def per(self, parola: str, ambito: str) -> str | None:
        """L'inglese di una parola nel sottosistema dato.

        Un omonimo fuori dai sottosistemi che il glossario nomina restituisce
        `None`: meglio non rinominare che rinominare col significato
        dell'altra riga.
        """
        if parola in self.scartate:
            return None
        if parola in self.omonimi:
            return self.omonimi[parola].get(ambito)
        return self.mappa.get(parola)


def _sezione(testo: str, titolo: str) -> str:
    i = testo.index(titolo)
    resto = testo[i + len(titolo):]
    j = resto.find("\n## ")
    return resto if j < 0 else resto[:j]


def _scarti_e_alias(sezione: str) -> tuple[set[str], dict[str, str]]:
    """Le due tabelle della sezione «Parole scartate», tenute distinte
    dall'intestazione: se l'intestazione degli alias non si trova piu',
    `str.index` solleva `ValueError` invece di lasciar scivolare le sue
    righe nella tabella degli scarti veri -- fermarsi rumorosamente e'
    la stessa legge di `Glossario.per`, applicata alla lettura.
    """
    i_scarti = sezione.index(_INTESTAZIONE_SCARTI)
    i_alias = sezione.index(_INTESTAZIONE_ALIAS)
    blocco_scarti = sezione[i_scarti:i_alias]
    blocco_alias = sezione[i_alias:]

    scartate = set()
    for riga in blocco_scarti.splitlines():
        m = re.match(r"\| `?([a-z][a-z_']*)`? \|", riga)
        if m:
            scartate.add(m.group(1))

    alias = {}
    for riga in blocco_alias.splitlines():
        m = re.match(r"\| `([a-z][a-z_']*)` \| `([a-z][a-z_']*)` \|", riga)
        if m:
            alias[m.group(1)] = m.group(2)
    return scartate, alias


def leggi_glossario(percorso: Path | None = None) -> Glossario:
    testo = leggi(percorso or GLOSSARIO)
    g = Glossario()

    g.scartate, g.alias = _scarti_e_alias(_sezione(testo, _SCARTATE))

    for titolo, colonna in _TABELLE:
        for riga in _sezione(testo, titolo).splitlines():
            if not riga.startswith("|") or riga.startswith("|---"):
                continue
            celle = [c.strip() for c in riga.strip("|").split("|")]
            if len(celle) <= colonna:
                continue
            it, en = celle[0], celle[colonna]
            if it in ("italiano", "costante") or not re.fullmatch(r"[a-z_]+", en):
                continue
            m = re.fullmatch(r"([a-z][a-z_']*)(?: \((\w+)\))?", it)
            if not m:
                continue
            parola, ambito = m.group(1), m.group(2)
            if parola in g.scartate:
                continue
            if ambito:
                # Un secondo omonimo dichiarato per la STESSA coppia
                # (parola, ambito) con un inglese diverso e' una riga
                # scritta due volte in disaccordo con se stessa: si ferma
                # rumorosamente, non si tiene l'ultima in silenzio.
                esistente = g.omonimi.get(parola, {}).get(ambito)
                if esistente is not None and esistente != en:
                    raise ValueError(
                        f"'{parola} ({ambito})' e' dichiarato due volte nel "
                        f"glossario con inglesi diversi ('{esistente}' e "
                        f"'{en}')")
                # Un omonimo esce dalla mappa piatta anche se ci era gia'
                # entrato da una riga senza parentesi: la mappa piatta
                # risponderebbe con una sola delle due letture.
                g.mappa.pop(parola, None)
                g.omonimi.setdefault(parola, {})[ambito] = en
            elif parola not in g.omonimi:
                # Due righe NUDE (senza ambito) per la stessa parola, in due
                # tabelle diverse, con inglesi diversi: l'ultima tabella
                # letta vincerebbe in silenzio -- misurato dal vivo (Task
                # 6): `guarda` era `look` fra le parole ordinarie e `view`
                # fra i nomi degli strumenti, nessuna riga lo dichiarava.
                # O e' lo stesso concetto ripetuto (stesso inglese in
                # entrambe: nessun problema, si sovrascrive con lo stesso
                # valore), o va scritto come omonimo -- 'parola (ambito)' --
                # non lasciato nudo in due posti.
                esistente = g.mappa.get(parola)
                if esistente is not None and esistente != en:
                    raise ValueError(
                        f"'{parola}' compare senza ambito in piu' tabelle "
                        f"con inglesi diversi ('{esistente}' e '{en}'): "
                        "e' un omonimo non dichiarato -- scrivilo come "
                        f"'{parola} (ambito)' in ciascuna riga.")
                g.mappa[parola] = en
    return g


@dataclass
class Proposta:
    """Un composto: lo strumento sa cosa contiene, non come si dice in inglese."""
    nome: str
    pezzi: list[str]
    suggerito: str


@dataclass
class Collisione:
    """Due nomi ORIGINALI diversi che, nello stesso file, finirebbero sullo
    stesso inglese: `_fuso` e `fuso` diventano entrambi `timezone` senza il
    trattino basso a distinguerli. Fonderli sarebbe peggio di non rinominare
    -- un aiutante privato scambiato per l'interfaccia pubblica di
    qualcun altro, senza che nessuno lo sappia. Come un composto, si segnala
    e non si applica: lo strumento non indovina, chiede.
    """
    nomi: list[str]
    suggerito: str


@dataclass
class FirmaScollegata:
    """Un parametro rinominato in una `def`, e un `vecchio=` rimasto in una
    chiamata dello STESSO file: la firma e i suoi chiamanti hanno smesso di
    parlarsi.

    **Lo strumento aveva gia' i due fatti e non li incrociava.** `riscrivi`
    sa quali token ha rinominato (fra cui i parametri di una `def`) e sa
    quali token stanno in posizione di parola chiave in una chiamata (li
    salta di proposito, e la ragione scritta in
    `_righe_di_percorso_e_parola_chiave` resta buona: non puo' sapere a
    quale firma quella chiamata risolva). Mancava solo l'intersezione fra i
    due insiemi, che e' gratis e chiude l'intera classe dentro il file.

    **Non e' un errore: e' una domanda.** Il `vecchio=` puo' essere giusto
    com'e' -- la parola chiave di una firma ALTRUI non ancora convertita che
    si chiama per caso come il parametro appena rinominato. Misurato dal
    vivo (Task 9, lotto 12): `nota_ripiego(motivo=reason, ...)` convive
    nella stessa riga col `reason=` appena rinominato, e li' l'italiano e'
    corretto. Distinguere i due casi richiede di sapere a quale funzione
    ogni chiamata risolve, cioe' cio' che questo strumento non sa e non deve
    indovinare: quindi elenca e si ferma, come per i composti.

    **Il caso FRA FILE non lo copre**, per costruzione: vedi
    `chiamanti_orfani`, il secondo strato.
    """
    vecchio: str
    nuovo: str
    righe: list[int]


def spezza(nome: str) -> list[str]:
    """I pezzi di un identificatore, senza i trattini bassi di convenzione."""
    return [p for p in re.split(r"_+|(?<=[a-z0-9])(?=[A-Z])", nome) if p]


_BUILTIN_NAMES = frozenset(dir(builtins))


def _pericoloso(parola: str) -> bool:
    """Vero se `parola` e' una keyword Python o il nome di un builtin.

    Applicarla a un identificatore NUDO (senza trattini di protezione)
    produce uno `SyntaxError` (una keyword: `class = ...`) o ombreggia
    silenziosamente il builtin (`type`, `list`, `round`...) -- e il secondo
    caso non lo vede nessun cancello finche' qualcosa non lo chiama
    davvero, perche' `flake8-builtins` non e' nel set di regole attive.
    Misurato dal vivo (Task 6): il glossario decide `classe -> class`,
    applicato a un identificatore nudo in `cervello/pavimento.py` ha
    prodotto `class = _text(...)`, trovato solo da `py_compile`. Non e' un
    giudizio sulla parola decisa -- resta decisa cosi' -- e' una guardia
    sulla FORMA nuda dell'applicazione, la stessa disciplina gia' in vigore
    per il trattino basso finale (`gamba_` -> `aspect_`, non `aspect`)."""
    return keyword.iskeyword(parola) or parola in _BUILTIN_NAMES


def _radici_plurali(parola: str) -> list[str]:
    """Candidati singolari italiani per una parola che potrebbe essere un
    plurale non aliasato.

    Senza questo, un plurale invisibile al glossario (nessun pezzo traduce)
    sparisce dal dry-run SENZA NESSUNA PROPOSTA -- misurato dal vivo (Task
    6): `GENERI`/`DIREZIONI_BILANCIO` non comparivano affatto nell'elenco
    dei composti, non perche' decisi ma perche' `classifica()` ritorna
    `None` quando NESSUN pezzo traduce, e "generi"/"direzioni" non sono le
    chiavi esatte del glossario (`genere`/`direzione`, singolari) ne' hanno
    un alias (a differenza di `gambe -> gamba`, che ce l'ha ed e' infatti
    gia' riconosciuto). Una singolarizzazione trovata per questa via non si
    applica MAI da sola: e' una supposizione morfologica, non una lettura
    diretta del glossario, quindi il chiamante la tratta come un alias (una
    Proposta, mai un'applicazione diretta) anche quando il nome e' un pezzo
    solo.

    Euristica, non un motore morfologico: copre le tre desinenze regolari
    (maschile -o/-i, la coppia -e/-i condivisa da maschile e femminile,
    femminile -a/-e), non le forme irregolari."""
    candidati = []
    if len(parola) > 1 and parola.endswith("i"):
        radice = parola[:-1]
        candidati.append(radice + "o")
        candidati.append(radice + "e")
    if len(parola) > 1 and parola.endswith("e"):
        candidati.append(parola[:-1] + "a")
    return candidati


def classifica(nome: str, g: Glossario, ambito: str):
    """`str` da applicare, `Proposta` da confermare, o `None` da lasciar stare."""
    pezzi = spezza(nome)
    forza_proposta = False
    tradotti = []
    for p in pezzi:
        chiave = p.lower()
        lemma = g.alias.get(chiave)
        if lemma is not None:
            forza_proposta = True
            tradotti.append(g.per(lemma, ambito))
            continue
        trovato = g.per(chiave, ambito)
        if trovato is None:
            for candidato in _radici_plurali(chiave):
                trovato = g.per(candidato, ambito)
                if trovato is not None:
                    forza_proposta = True
                    break
        tradotti.append(trovato)
    if not any(tradotti):
        return None
    if len(pezzi) == 1 and not forza_proposta:
        en = tradotti[0]
        if en is None:
            return None
        # I trattini bassi iniziali E finali sono convenzione Python
        # (privato; oppure evitare di ombreggiare una parola riservata, come
        # `tipo_`/`gamba_`): non parole da tradurre, si tolgono prima di
        # guardare le maiuscole e si rimettono identici alla fine. Senza,
        # `_fuso` (un aiutante privato) diventava `timezone` (interfaccia
        # pubblica) -- misurato su `consumi/store.py` (Task 4). Stessa
        # famiglia sul lato finale: `gamba_` (`cervello/oggetti.py`, evita
        # di ombreggiare la parola `gamba`) sarebbe diventato `aspect`,
        # perdendo il trattino che lo distingue dalla parola che ombreggia
        # -- trovato guardando se restasse una quarta variante di forma non
        # coperta, dopo maiuscole (round 1), costanti TUTTE MAIUSCOLE
        # (round 1) e prefisso privato (round 2).
        nucleo = nome.strip("_")
        prefisso = nome[:len(nome) - len(nome.lstrip("_"))]
        suffisso = nome[len(nome.rstrip("_")):]
        # La forma del nome originale si conserva: `Archivio` -> `Store`,
        # `archivio` -> `store`. Rinominare una classe in minuscolo romperebbe
        # la convenzione di Python piu' silenziosamente di quanto sembri.
        #
        # Ma `nucleo[:1].isupper()` da solo confonde una classe (`Archivio`,
        # PascalCase) con una costante di modulo (`ETICHETTA`, TUTTA
        # maiuscola): entrambe iniziano con una lettera maiuscola. Misurato
        # puntando lo strumento su `consumi/vocabolario.py` (Task 4): senza
        # `nucleo.isupper()`, `ETICHETTA` diventava `Label` invece di
        # `LABEL`, rompendo la convenzione delle costanti in silenzio.
        if nucleo[:1].isupper():
            parola = en.upper() if nucleo.isupper() else en.capitalize()
        else:
            parola = en
        if not prefisso and not suffisso and _pericoloso(parola):
            # Nudo, nessun trattino di protezione: si propone, non si
            # applica. Un prefisso o un suffisso (`_tipo`, `tipo_`) non
            # ombreggiano niente -- sono gia' un nome diverso dal builtin --
            # quindi restano nel ramo di applicazione diretta qui sopra.
            return Proposta(nome=nome, pezzi=[nome.lower()], suggerito=parola)
        return prefisso + parola + suffisso
    # Un composto in cui almeno un pezzo non e' deciso resta una proposta lo
    # stesso: il pezzo ignoto va guardato, non saltato. Una forma raggiunta
    # per alias (`costruzioni` -> lemma `costruzione` -> `construction`) o
    # per singolarizzazione di un plurale non aliasato (`GENERI` -> `genere`
    # -> `genre`) resta una proposta anche da sola: ne' l'inflessione
    # inglese del lemma ne' la singolarizzazione italiana sono garantite
    # corrette -- una lettura diretta del glossario si', un'euristica no.
    suggerito = "_".join(t or p.lower() for t, p in zip(tradotti, pezzi))
    return Proposta(nome=nome, pezzi=[p.lower() for p in pezzi], suggerito=suggerito)


import argparse
import io
import subprocess
import tokenize

from _comune import file_py, rel

# Il confine di HAClient (`proxy/ha_client.py`): un ambito che questa fetta
# non converte affatto, ma che OGNI sottosistema convertito puo' chiamare
# per attributo (`ha.storico(...)`, `ha.statistiche(...)`...). Una parola
# gia' decisa nel glossario (`statistiche -> statistics`) non sa
# distinguere "un metodo mio che si chiama cosi'" da "un metodo DI
# HACLIENT che si chiama cosi' per caso" -- l'attributo dopo il punto e'
# un NAME come un altro per il tokenizzatore. Misurato dal vivo (Task 8,
# review indipendente): il join meccanico ha tradotto
# `ha.statistiche(...)` in `ha.statistics(...)` dentro `casa/tempo.py` --
# un `AttributeError` in produzione alla prima domanda di andamento sopra
# le 24 ore, perche' `HAClient.statistiche` resta cosi' finche' `proxy/`
# non viene convertito, e nessun test lo vedeva perche' il finto che lo
# imitava era stato rinominato insieme al chiamante.
#
# Elenco letto a mano da `proxy/ha_client.py` (non importato: questo
# script non dipende dal resto del pacchetto) -- va aggiornato se quel
# file guadagna o perde un metodo. Include anche i privati (`_ws_batch` e
# simili): non c'e' svantaggio a proteggerli anche se oggi nessuna parola
# del glossario li tocca, e un domani in cui una collidesse non
# richiederebbe di ricordarsi di questa lista.
_METODI_HA_CLIENT = frozenset({
    "start", "stop", "get_states", "get_services", "call_service",
    "_config_route", "_http_reason", "leggi_configurazione",
    "salva_configurazione", "cancella_configurazione", "valida_config",
    "_ws_occurrence", "crea_helper", "cancella_helper", "elenca_etichette",
    "crea_etichetta", "aggiungi_etichetta_a", "estrai_dal_bersaglio",
    "leggi_plance", "_health_value", "get_system_health",
    "storico", "diario", "render_template", "_ws_batch", "_ws_request",
    "_ws_command", "_ws_call", "statistiche", "statistiche_orarie",
    "_request_statistics", "legami", "problemi", "direzioni_energia",
    "_declare", "get_config", "leggi_registri", "_add_extended_fields",
    "add_state_listener", "remove_state_listener", "add_anagrafe_listener",
    "add_servizi_listener", "add_plance_listener", "start_websocket",
    "_ws_loop",
})

# La STESSA guardia, per una specie diversa di confine (Task 9, `api/`):
# `UsageStore` (`consumi/store.py`) e' un ambito GIA' CHIUSO -- a
# differenza di `HAClient`, la cui intera classe resta fuori da questa
# fetta -- ma tre dei suoi metodi PUBBLICI (`sezioni`, `totali`, `storia`)
# non sono mai stati decisi nel glossario, e restano italiani nonostante
# `consumi/` sia "idempotente". Un ambito idempotente non e' la garanzia
# che ci si aspetterebbe (vedi il debito tracciato in
# `tests/test_rinomina_applica.py` per `AgendaStore.list::
# solo_in_sospeso` e `ConstructionStore.scadi`, la stessa famiglia):
# `sezioni -> section`/`totali -> total` sarebbero comunque solo delle
# PROPOSTE (parole singole non aliasate al plurale, mai applicate da
# sole), ma il giorno in cui qualcuno decidesse `sezione -> section` per
# un'altra ragione, `archivio.sezioni(...)` diventerebbe
# `archivio.section(...)` in silenzio -- lo stesso guasto di
# `ha.statistiche()`, misurato PRIMA di commetterlo qui (dry-run su
# `api/handlers_usage.py`, che chiama tutti e tre), non dopo.
#
# Elenco letto a mano da `consumi/store.py` (stessa disciplina di
# `_METODI_HA_CLIENT`: include anche i privati e i metodi gia' inglesi,
# nessuno svantaggio a proteggerli).
_METODI_USAGE_STORE = frozenset({
    "__init__", "close", "_timezone", "empty", "log", "_where", "sezioni",
    "totali", "storia", "anchor", "_anchor_day", "sposta_anchor",
    "_sottrai_saldo", "importa_legacy",
})

# Terza voce (Task 9, `api/handlers_impostazioni.py`, PRIMA di applicare il
# file, non dopo): `ImpostazioniChat` (`impostazioni_chat.py`, un file di
# RADICE -- non un ambito di questa fetta, ne' chiuso ne' aperto) e' un
# dataclass, non una classe di servizio: il rischio non e' un METODO
# rinominato per attributo, e' un CAMPO. `nome` e `giorni_conservazione`
# restano italiani (gli altri cinque campi sono gia' inglesi per conto
# loro: `system_prompt`, `response_mode`, `thinking_budget`,
# `max_chat_turns`, `restrict_to_home`). Misurato PRIMA di romperlo:
# `corrente.nome` (`nome` gia' deciso, parola ordinaria -> `name`)
# diventava `corrente.name` in una prova isolata (`rinomina.riscrivi()` su
# uno snippet sintetico) -- lo stesso guasto di `ha.statistiche()` e di
# `archivio.sezioni()`, qui su un campo di dataclass invece che su un
# metodo. Elenco letto a mano da `impostazioni_chat.py`: i sette campi piu'
# i due metodi pubblici (`carica`, `salva`).
_METODI_IMPOSTAZIONI_CHAT = frozenset({
    "nome", "system_prompt", "response_mode", "thinking_budget",
    "max_chat_turns", "restrict_to_home", "giorni_conservazione",
    "carica", "salva",
})

# Quarta voce (Task 9, `api/handlers_chat.py`, PRIMA di applicare il file):
# `RegistroEsiti` (`esiti_provider.py`, un altro file di RADICE) e' l'unico
# ricevitore di tutto `api/` su cui una parola GIA' DECISA si applicherebbe da
# sola. `esito -> occurrence` e' deciso da sempre («I concetti»), e
# `handlers_chat.py:303` scrive `occurrence_registry.esito(backend_name)` (era
# `registro.esito(nome_backend)` prima del lotto 12): senza questa
# voce il join meccanico produce `registry.occurrence(...)` -- un
# `AttributeError` alla prima chat che ripiega dal piano alla catena, cioe'
# proprio sul percorso che la fetta «la catena diventa l'unica verita'» esiste
# per rendere affidabile. **Non e' un rischio futuro come per `UsageStore`**
# (dove nessuna parola era decisa e la guardia preveniva un domani): qui il
# difetto e' ATTIVO oggi, misurato con `rinomina.riscrivi()` sul file vero
# prima di scriverlo su disco, e provato per mutazione.
#
# Elenco letto a mano da `esiti_provider.py` (stessa disciplina delle altre
# tre: i due campi privati, i quattro metodi pubblici, e le due funzioni di
# modulo -- `famiglia_da_codice`/`famiglia_errore` non sono attributi della
# classe, ma si leggono per attributo sul MODULO
# (`esiti_provider.famiglia_errore(...)`) ed e' lo stesso gesto sintattico).
_METODI_REGISTRO_ESITI = frozenset({
    "__init__", "_orologio", "_per_provider",
    "successo", "fallimento", "esito", "tutti",
    "famiglia_da_codice", "famiglia_errore",
})

# L'insieme delle classi esterne protette per attributo, indipendentemente
# da QUALE oggetto le porta: `_righe_di_percorso_e_parola_chiave` non sa
# (ne' deve sapere) se una variabile si chiama `ha`, `archivio` o
# `store` -- controlla solo se il NOME dopo il punto appartiene a una di
# queste classi. Un domani in cui una terza classe rivelasse lo stesso
# guasto si aggiunge qui, non si duplica il meccanismo.
_METODI_ESTERNI_PROTETTI = (
    _METODI_HA_CLIENT | _METODI_USAGE_STORE | _METODI_IMPOSTAZIONI_CHAT
    | _METODI_REGISTRO_ESITI
)


def _righe_di_percorso_e_parola_chiave(tokens: list) -> tuple[set[int], set[int], set[int]]:
    """Tre insiemi di INDICI nella lista `tokens`: quelli che sono un
    segmento di un percorso di IMPORT, quelli che sono il nome di una
    PAROLA CHIAVE (keyword argument) in una chiamata, e quelli che sono un
    METODO DI HACLIENT letto per attributo (`ha.storico(...)`).

    Un percorso di import (`from ..casa.anagrafe import X`, `import
    hiris.app.memoria.archivio`) e' un indirizzo verso UN ALTRO modulo, mai
    un identificatore del proprio ambito -- vale anche quando punta al
    proprio stesso sottosistema (il file, se deciso, si rinomina con
    `git mv`, non riscrivendo la stringa dell'import). Riconosciuto per
    posizione: il primo `from`/`import` di una riga logica apre il
    percorso, e il primo `import` che lo richiude (nella forma `from ...
    import`), oppure `as`/una virgola (nella forma `import ...` da solo),
    lo richiude. **Non un elenco di percorsi noti**: una lista andrebbe
    aggiornata a ogni nuovo import, e sarebbe silenziosamente incompleta
    per costruzione -- qui e' la SINTASSI dell'istruzione a deciderlo,
    indipendentemente da quali parole contenga.

    Una parola chiave in una chiamata (`f(origine="x")`) e' un nome che lo
    strumento non puo' verificare: potrebbe risolvere verso una funzione di
    un ambito non ancora convertito (`azione/porta.py::esegui(*, origine)`),
    e rinominarla romperebbe la chiamata in un modo che nessun test di
    QUESTO file puo' vedere. Riconosciuta per struttura: un NAME seguito da
    un singolo `=` (mai `==`), dentro una parentesi aperta da un NAME (o da
    `)`/`]`, per le chiamate incatenate) che non sia essa stessa una
    `def` -- una parentesi di raggruppamento o di definizione lascia il
    nome cosi' com'e' (e' la propria firma, o non e' affatto una chiamata).

    Un metodo di `HAClient` (`ha.storico(...)`, `self._ha.statistiche(...)`)
    e' un attributo di un oggetto che arriva da un ambito -- `proxy/` --
    che questa fetta non converte affatto: riconosciuto per struttura (un
    NAME preceduto da un singolo `.`) e per appartenenza a
    `_METODI_ESTERNI_PROTETTI`, indipendentemente da quale variabile lo
    precede. **Non solo `HAClient`**: `_METODI_ESTERNI_PROTETTI` unisce
    anche `_METODI_USAGE_STORE` (`UsageStore`, `consumi/`) -- un ambito
    GIA' CHIUSO puo' avere metodi pubblici mai decisi quanto uno non
    ancora toccato, e il rischio per lo strumento e' identico (Task 9).
    Trattato come una parola chiave: si segnala, non si applica.
    """
    percorso: set[int] = set()
    parola_chiave: set[int] = set()
    confine_ha: set[int] = set()

    modo = None  # None | "percorso_from" | "percorso_import" | "alias_in_arrivo"
    inizio_riga = True
    pila_parentesi: list[str] = []
    precedente = None
    precedente_precedente = None

    for i, t in enumerate(tokens):
        if t.type == tokenize.OP and t.string == "(":
            if precedente is not None and precedente.type == tokenize.NAME:
                e_def = (precedente_precedente is not None
                         and precedente_precedente.type == tokenize.NAME
                         and precedente_precedente.string == "def")
                pila_parentesi.append("def" if e_def else "chiamata")
            elif precedente is not None and precedente.type == tokenize.OP \
                    and precedente.string in (")", "]"):
                pila_parentesi.append("chiamata")
            else:
                pila_parentesi.append("altro")
        elif t.type == tokenize.OP and t.string in ("[", "{"):
            pila_parentesi.append("altro")
        elif t.type == tokenize.OP and t.string in (")", "]", "}") and pila_parentesi:
            pila_parentesi.pop()

        if t.type == tokenize.NAME:
            if modo == "percorso_from":
                percorso.add(i)
                if t.string == "import":
                    modo = None
            elif modo == "percorso_import":
                if t.string == "as":
                    modo = "alias_in_arrivo"
                else:
                    percorso.add(i)
            elif modo == "alias_in_arrivo":
                modo = "percorso_import"  # dopo l'alias potrebbe seguirne un altro (virgola)
            elif inizio_riga and t.string == "from":
                percorso.add(i)
                modo = "percorso_from"
            elif inizio_riga and t.string == "import":
                percorso.add(i)
                modo = "percorso_import"
            elif (pila_parentesi and pila_parentesi[-1] == "chiamata"
                    and i not in percorso
                    and i + 1 < len(tokens)
                    and tokens[i + 1].type == tokenize.OP
                    and tokens[i + 1].string == "="):
                parola_chiave.add(i)
            elif (t.string in _METODI_ESTERNI_PROTETTI
                    and precedente is not None
                    and precedente.type == tokenize.OP
                    and precedente.string == "."):
                confine_ha.add(i)

        if t.type == tokenize.NEWLINE:
            # Fine della riga LOGICA: `percorso_from` si chiude sempre da
            # solo (incontra il proprio `import`), ma un `import a, b` o
            # `import a as x` non ha nessun token che lo richiuda -- senza
            # questo reset, `modo` restava "percorso_import" per il resto
            # del file dopo il primo `import semplice`, e ogni nome
            # successivo veniva scambiato per un segmento di percorso.
            # Misurato: senza questa riga, un solo `import re` in cima a un
            # file azzerava i composti rilevati in tutto il resto del file.
            modo = None
            inizio_riga = True
        elif t.type in (tokenize.INDENT, tokenize.DEDENT):
            inizio_riga = True
        elif t.type not in (tokenize.NL, tokenize.COMMENT, tokenize.ENCODING):
            inizio_riga = False

        if t.type not in (tokenize.NL, tokenize.COMMENT, tokenize.ENCODING,
                          tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE):
            precedente_precedente = precedente
            precedente = t

    return percorso, parola_chiave, confine_ha


def riscrivi(sorgente: str, g: Glossario, ambito: str
             ) -> tuple[str, list[Proposta | Collisione | FirmaScollegata]]:
    """Il sorgente coi soli token NAME rinominati, piu' i composti, le
    collisioni e le firme scollegate da decidere.

    Si sostituisce sul TESTO alle posizioni dei token, da destra a sinistra:
    `tokenize.untokenize` rigenererebbe il file e ne perderebbe la
    formattazione, che qui e' contenuto -- i commenti allineati di questa
    codebase sono la sua parte migliore.
    """
    righe = sorgente.splitlines(keepends=True)
    inizi = [0]
    for r in righe:
        inizi.append(inizi[-1] + len(r))

    def offset(pos):
        riga, col = pos
        return inizi[riga - 1] + col

    tokens = list(tokenize.generate_tokens(io.StringIO(sorgente).readline))
    percorso, parola_chiave, confine_ha = _righe_di_percorso_e_parola_chiave(tokens)

    grezzi, proposte = [], []
    # `indice del token -> inglese applicato`, per il controllo di chiusura
    # in fondo: `grezzi` porta gli OFFSET nel testo, che non bastano a
    # ritrovare il token nella lista.
    applicati: dict[int, str] = {}
    visti = set()
    for i, t in enumerate(tokens):
        if t.type != tokenize.NAME:
            continue
        if i in percorso:
            # Un indirizzo verso un altro modulo, mai un identificatore del
            # proprio ambito -- vedi `_righe_di_percorso_e_parola_chiave`.
            continue
        esito = classifica(t.string, g, ambito)
        if esito is None:
            continue
        if isinstance(esito, Proposta):
            if esito.nome not in visti:
                visti.add(esito.nome)
                proposte.append(esito)
            continue
        if i in parola_chiave or i in confine_ha:
            # Una parola chiave in una chiamata: lo strumento non puo'
            # sapere se punta a una funzione gia' convertita. Si segnala
            # come una proposta -- non indovina, chiede -- invece di
            # applicarla e rischiare di rompere una firma altrui in
            # silenzio (`origine=` verso `azione/porta.py::esegui`, misurato).
            # Stessa cura per un metodo di HAClient o di UsageStore
            # (`confine_ha`, che nonostante il nome copre entrambi ora):
            # rompere `ha.statistiche()` in `ha.statistics()` e' lo stesso
            # guasto di rompere `archivio.sezioni()` in `archivio.section()`,
            # misurato dal vivo su `casa/tempo.py` (Task 8) e prevenuto per
            # `consumi/store.py` prima di commetterlo (Task 9).
            proposta = Proposta(nome=t.string, pezzi=[t.string.lower()], suggerito=esito)
            if proposta.nome not in visti:
                visti.add(proposta.nome)
                proposte.append(proposta)
            continue
        applicati[i] = esito
        grezzi.append((offset(t.start), offset(t.end), t.string, esito))

    # Guardia sulle collisioni: se due nomi ORIGINALI diversi finirebbero
    # sullo stesso inglese in questo file, nessuno dei due si applica.
    # Fondere due identita' diverse senza che nessuno lo sappia e' peggio di
    # non rinominare -- lo stesso principio dei composti, applicato a un
    # difetto che un composto non copre (qui ogni singolo nome e' gia'
    # deciso; e' l'INCONTRO fra due nomi decisi che va guardato).
    nomi_per_nuovo: dict[str, set[str]] = {}
    for _, _, nome_originale, nuovo in grezzi:
        nomi_per_nuovo.setdefault(nuovo, set()).add(nome_originale)
    collisi = {nuovo: nomi for nuovo, nomi in nomi_per_nuovo.items() if len(nomi) > 1}
    for nuovo, nomi in collisi.items():
        chiave = (nuovo, tuple(sorted(nomi)))
        if chiave not in visti:
            visti.add(chiave)
            proposte.append(Collisione(nomi=sorted(nomi), suggerito=nuovo))

    cambi = [(i, j, nuovo) for i, j, _, nuovo in grezzi if nuovo not in collisi]

    # Il controllo di chiusura, primo strato: dentro QUESTO file.
    #
    # I due fatti erano gia' qui e non si incontravano -- `parametri_def`
    # sa quali token sono il nome di un parametro in una firma, e
    # `parola_chiave` sa quali token sono un `foo=` in una chiamata. Se un
    # parametro e' stato rinominato e nello stesso file resta un `vecchio=`,
    # la firma e la chiamata hanno smesso di parlarsi: si dichiara, non si
    # corregge (vedi `FirmaScollegata` per il perche' correggere sarebbe
    # sbagliato).
    parametri_def = _posizioni_parametri_def(tokens)
    nomi_chiave = {tokens[i].string for i in parola_chiave}
    rinominati = {tokens[i].string: nuovo for i, nuovo in applicati.items()
                  if i in parametri_def and nuovo not in collisi}
    for vecchio, nuovo in sorted(rinominati.items()):
        if vecchio in nomi_chiave:
            righe = sorted({tokens[i].start[0] for i in parola_chiave
                            if tokens[i].string == vecchio})
            proposte.append(FirmaScollegata(vecchio=vecchio, nuovo=nuovo, righe=righe))

    fuori = sorgente
    for i, j, nuovo in sorted(cambi, reverse=True):
        fuori = fuori[:i] + nuovo + fuori[j:]
    return fuori, proposte


def _leggi_grezzo(f: Path) -> str:
    """Il sorgente coi SUOI fine-riga, non quelli di `leggi()` (`_comune.py`).

    `leggi()` legge in universal newlines implicito: va bene per chi la
    usa solo in lettura (`censimento.py`, `doppioni.py`), sbagliato qui, dove
    il testo si RISCRIVE sul disco. Non si tocca `_comune.py` per questo:
    e' condiviso con quei due strumenti, e a loro il comportamento attuale
    va bene -- leggere diversamente quando serve una garanzia che lui non
    da' non e' il doppione che il vincolo vieta.

    `newline=""` lascia intatti i fine-riga che ci sono, qualunque essi
    siano; senza, la scrittura successiva li tradurrebbe (su Windows, LF
    diventa CRLF) e cambierebbe OGNI riga del file, non solo quella
    dell'identificatore rinominato -- il contrario della prima guardia (un
    diff che contiene una cosa sola).
    """
    with open(f, encoding="utf-8-sig", errors="replace", newline="") as fh:
        return fh.read()


def _scrivi_grezzo(f: Path, testo: str) -> None:
    """Scrive senza tradurre i fine-riga: il gemello di `_leggi_grezzo`."""
    with open(f, "w", encoding="utf-8", newline="") as fh:
        fh.write(testo)


def _posizioni_parametri_def(tokens: list) -> set[int]:
    """Gli INDICI dei token che sono il NOME di un parametro in una `def`.

    Non e' un doppione di `_righe_di_percorso_e_parola_chiave`: quella
    risponde a «questo token si puo' toccare?», questa a «questo token e' un
    parametro di una firma?». Sono due domande diverse sullo stesso flusso, e
    solo la seconda serve al controllo di chiusura qui sotto.

    Riconosciuto per struttura, mai per elenco: un NAME che sta dentro la
    parentesi di una `def` (la stessa pila di `_righe_di_percorso_e_parola_
    chiave`, con lo stesso criterio per distinguerla da una chiamata) e che
    segue `(`, `,`, `*`, `**` oppure `/`. Cio' che segue `:` o `=` e' invece
    un'annotazione o un valore predefinito, e non e' il nome del parametro --
    la profondita' della pila basta a distinguerli, perche' `dict[str, int]`
    apre una parentesi quadra e la sua virgola non e' mai al livello della
    `def`.
    """
    posizioni: set[int] = set()
    pila: list[str] = []
    precedente = None
    precedente_precedente = None

    for i, t in enumerate(tokens):
        if t.type == tokenize.OP and t.string == "(":
            e_def = (precedente is not None and precedente.type == tokenize.NAME
                     and precedente_precedente is not None
                     and precedente_precedente.type == tokenize.NAME
                     and precedente_precedente.string == "def")
            pila.append("def" if e_def else "altro")
        elif t.type == tokenize.OP and t.string in ("[", "{"):
            pila.append("altro")
        elif t.type == tokenize.OP and t.string in (")", "]", "}") and pila:
            pila.pop()
        elif (t.type == tokenize.NAME and pila and pila[-1] == "def"
                and precedente is not None and precedente.type == tokenize.OP
                and precedente.string in ("(", ",", "*", "**", "/")):
            posizioni.add(i)

        if t.type not in (tokenize.NL, tokenize.COMMENT, tokenize.ENCODING,
                          tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE):
            precedente_precedente = precedente
            precedente = t

    return posizioni


def parametri_def_rinominati(sorgente: str, g: Glossario, ambito: str) -> dict[str, str]:
    """`{nome vecchio: nome nuovo}` per i soli parametri di `def` che
    `riscrivi()` rinomina in questo sorgente.

    E' la META' MANCANTE della guardia sulle parole chiave. Quella guardia
    (`_righe_di_percorso_e_parola_chiave`, e la ragione scritta li') salta di
    proposito i token in posizione `foo=` dentro una chiamata: lo strumento
    non sa da quale oggetto quella chiamata passi, e rinominare la parola
    chiave di una firma altrui la romperebbe in silenzio. La regola resta
    giusta. Ma ha una conseguenza inevitabile che nessuna riga diceva: **ogni
    volta che un parametro viene rinominato in una `def`, tutti i `vecchio=`
    dei suoi chiamanti restano indietro**, e la firma e le chiamate smettono
    di parlarsi.

    Misurato quattro volte in due lotti (Task 9): `stato` in
    `api/handlers_mcp.py` (tre chiamanti nello stesso file), `motivo` e
    `turno` in `api/handlers_chat.py` -- e per `turno` **uno dei chiamanti era
    in un altro file gia' convertito** (`api/handlers_mcp.py:438`), fuori dal
    perimetro che il lotto stava guardando. Prese a mano quattro volte su
    quattro, il che e' la definizione di un difetto in attesa della prima
    volta che nessuno guarda: nessun cancello lo vede (Python non controlla i
    nomi delle parole chiave all'import) e la rete e' la sola copertura del
    percorso chiamante, che e' parziale per costruzione.
    """
    tokens = list(tokenize.generate_tokens(io.StringIO(sorgente).readline))
    percorso, parola_chiave, confine = _righe_di_percorso_e_parola_chiave(tokens)
    rinominati: dict[str, str] = {}
    for i in _posizioni_parametri_def(tokens):
        if i in percorso or i in parola_chiave or i in confine:
            continue
        t = tokens[i]
        esito = classifica(t.string, g, ambito)
        if isinstance(esito, str) and esito != t.string:
            rinominati[t.string] = esito
    return rinominati


def parametri_dichiarati(radice: Path | None = None) -> set[str]:
    """Ogni nome di parametro dichiarato da una `def` del repo, oggi.

    Serve a separare i chiamanti orfani CERTI dagli ambigui: se nessuna firma
    del progetto porta piu' quel nome, un `vecchio=` non puo' risolvere a
    niente -- o e' rotto, o non e' un parametro (una chiave di dizionario in
    un costruttore `**kwargs`, il caso 2 di `chiamanti_orfani`). Se invece il
    nome e' ancora dichiarato da qualche parte, la chiamata puo' benissimo
    essere corretta e puntare a quella firma.
    """
    dichiarati: set[str] = set()
    for f in file_py(radice or ROOT):
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(_leggi_grezzo(f)).readline))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            continue
        for i in _posizioni_parametri_def(tokens):
            dichiarati.add(tokens[i].string)
    return dichiarati


def chiamanti_orfani(nomi: dict[str, str],
                     radice: Path | None = None) -> list[tuple[Path, int, str, str]]:
    """I siti di chiamata, su TUTTO il repo, che passano ancora una parola
    chiave con un nome che una `def` non porta piu'.

    **La radice predefinita e' l'intero progetto, non l'ambito in
    lavorazione, ed e' il punto**: il chiamante orfano che ha motivato questo
    controllo viveva in un file di un lotto PRECEDENTE, gia' chiuso e gia'
    verde. Cercarlo solo dentro il `--percorso` corrente lo lascerebbe
    esattamente dov'era.

    **Dichiara, non corregge**, e la ragione non e' prudenza: **tre forme
    diverse producono lo stesso `vecchio=`, e due sono giuste.** Misurate
    rilanciando questo controllo sull'intera fetta (192 parametri di firma
    rinominati in 50 commit, 555 occorrenze trovate):

    1. **La parola chiave di una firma ALTRUI, non ancora convertita.**
       `nota_ripiego(motivo=...)` verso `decisione_modelli.py` conviveva,
       nella stessa riga, col `reason=` appena rinominato: giusta cosi'.
    2. **Una CHIAVE DI DIZIONARIO passata a un costruttore `**kwargs`.** E'
       la forma piu' frequente nei test (`_intento(gesto="modifica")`,
       `_fai(frase=...)`, `_entita(disabilitata=1)`, `dict(_REGISTRI,
       piani=[])`): quel nome non e' un parametro, e' una chiave di dominio o
       una colonna del database -- entrambe deliberatamente italiane, con la
       ragione scritta nel glossario. Rinominarle romperebbe il dato, non la
       firma. **Sono 24 delle 24 «certe» trovate nella scansione retroattiva,
       e non una era un difetto.**
    3. **Il parametro di una `lambda` dentro una chiamata**
       (`MagicMock(side_effect=lambda k, d=None: ...)`): la guardia sulle
       parole chiave lo scambia per un `d=` di chiamata. La sbaglia nella
       direzione sicura (protegge invece di rinominare), ma qui compare come
       falso positivo e va saputo.

    Distinguere i tre casi richiede di sapere a quale funzione ogni chiamata
    risolva, cioe' esattamente cio' che questo strumento non sa e non deve
    indovinare. Quindi elenca e si ferma, come per i composti: la legge del
    glossario applicata a un'altra domanda.

    **Il filtro che rende l'elenco leggibile** e' `parametri_dichiarati()`:
    un `vecchio=` il cui nome NON e' piu' dichiarato da nessuna `def` del
    repo e' certo, gli altri sono ambigui. Sulla fetta intera ha portato 555
    occorrenze a 24 da guardare -- senza di lui nessuno leggerebbe l'elenco,
    ed e' la differenza fra un controllo che si usa e uno che si salta.
    """
    trovati: list[tuple[Path, int, str, str]] = []
    if not nomi:
        return trovati
    for f in file_py(radice or ROOT):
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(_leggi_grezzo(f)).readline))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            continue
        _, parola_chiave, _ = _righe_di_percorso_e_parola_chiave(tokens)
        for i in sorted(parola_chiave):
            t = tokens[i]
            if t.string in nomi:
                trovati.append((f, t.start[0], t.string, nomi[t.string]))
    return trovati


def _elenco_file(base: Path) -> list[Path]:
    """I file `.py` di un percorso, che sia una cartella o un file solo.

    Misurato: `file_py()` usa `rglob`, che su un percorso-FILE non trova
    nulla. Vive qui e non dentro `applica` perche' `main` ha bisogno dello
    stesso elenco per il controllo di chiusura, e due modi di decidere quali
    file sono «quelli di questo lotto» sarebbero due elenchi liberi di
    divergere.
    """
    return [base] if base.is_file() else file_py(base)


def applica(base: Path, ambito: str, *,
            scrivi: bool = True) -> list[Proposta | Collisione | FirmaScollegata]:
    """Tutto il sottosistema, oppure un file solo. Un file illeggibile si
    riporta e si va avanti.

    Misurato: `file_py()` usa `rglob`, che su un percorso-file non trova
    nulla -- serve decidere l'elenco dei file all'inizio, non delegarlo
    tutto a `file_py`, o un `--percorso` a un file singolo elaborerebbe
    zero file senza errore: il difetto peggiore, perche' ha l'aspetto
    esatto di un successo.
    """
    file = _elenco_file(base)
    tutte: list[Proposta | Collisione | FirmaScollegata] = []
    for f in file:
        sorgente = _leggi_grezzo(f)
        try:
            fuori, proposte = riscrivi(sorgente, g_corrente(), ambito)
        except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
            print(f"  ! {rel(f)}: non leggibile, saltato ({exc})")
            continue
        tutte.extend(proposte)
        if scrivi and fuori != sorgente:
            _scrivi_grezzo(f, fuori)
    return tutte


_G: Glossario | None = None


def g_corrente() -> Glossario:
    global _G
    if _G is None:
        _G = leggi_glossario()
    return _G


def _albero_pulito() -> bool:
    fuori = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                           capture_output=True, text=True, check=False)
    return not fuori.stdout.strip()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Rinomina gli identificatori di un sottosistema.")
    p.add_argument("--percorso", required=True, help="es. hiris/app/consumi")
    p.add_argument("--ambito", required=True, help="il sottosistema, per gli omonimi: es. consumi")
    p.add_argument("--dry-run", action="store_true", help="non scrive, elenca soltanto")
    a = p.parse_args(argv)

    # Guardia 1: un diff da rivedere non deve mai mescolare la rinomina con
    # altro. E' l'unica cosa che rende leggibile un diff da migliaia di righe.
    if not a.dry_run and not _albero_pulito():
        print("albero sporco: la rinomina si applica solo su un albero pulito")
        return 1

    base = ROOT / a.percorso
    if not base.exists():
        print(f"percorso inesistente: {a.percorso}")
        return 1

    # I parametri di firma che stanno per essere rinominati, letti PRIMA che
    # `applica` riscriva i file: dopo, sul disco c'e' gia' il nome nuovo e non
    # c'e' piu' niente da confrontare. Serve al secondo strato del controllo
    # di chiusura (`chiamanti_orfani`, su tutto il repo); il primo strato --
    # dentro il file stesso -- lo fa gia' `riscrivi`.
    parametri: dict[str, str] = {}
    for f in _elenco_file(base):
        try:
            parametri.update(parametri_def_rinominati(
                _leggi_grezzo(f), g_corrente(), a.ambito))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            continue

    proposte = applica(base, a.ambito, scrivi=not a.dry_run)
    composti = [p for p in proposte if isinstance(p, Proposta)]
    collisioni = [p for p in proposte if isinstance(p, Collisione)]
    scollegate = [p for p in proposte if isinstance(p, FirmaScollegata)]
    msg = f"{a.percorso} (ambito «{a.ambito}»): {len(composti)} composti da decidere"
    if collisioni:
        msg += f", {len(collisioni)} collisioni"
    if scollegate:
        msg += f", {len(scollegate)} firme scollegate"
    print(msg)
    for pr in sorted(composti, key=lambda x: x.nome):
        print(f"  {pr.nome:38} pezzi={'+'.join(pr.pezzi):30} suggerito={pr.suggerito}")
    for c in sorted(collisioni, key=lambda x: x.suggerito):
        print(f"  COLLISIONE {'/'.join(c.nomi):30} -> suggerito={c.suggerito} "
              f"(nessuno dei due si applica)")
    for s in sorted(scollegate, key=lambda x: x.vecchio):
        righe = ", ".join(str(r) for r in s.righe)
        print(f"  FIRMA SCOLLEGATA {s.vecchio} -> {s.nuovo}: la «def» e' "
              f"rinominata, ma nello stesso file resta «{s.vecchio}=» "
              f"alle righe {righe} (guardale: potrebbe essere la parola "
              f"chiave di una firma altrui, e allora e' giusta cosi')")

    # Secondo strato: i chiamanti orfani in TUTTO il repo, non solo
    # nell'ambito in lavorazione -- il caso che ha motivato questo controllo
    # (Task 9, lotto 12) aveva il chiamante in un file di un lotto
    # precedente, gia' chiuso e gia' verde.
    orfani = [(f, riga, vecchio, nuovo)
              for f, riga, vecchio, nuovo in chiamanti_orfani(parametri)
              if rel(f) not in {rel(x) for x in _elenco_file(base)}]
    if orfani:
        dichiarati = parametri_dichiarati()
        certi = [o for o in orfani if o[2] not in dichiarati]
        ambigui = len(orfani) - len(certi)
        print(f"  -- {len(orfani)} chiamanti con la parola chiave vecchia FUORI "
              f"da {a.percorso} ({len(certi)} certi, {ambigui} ambigui):")
        for f, riga, vecchio, nuovo in certi:
            print(f"     CERTO   {rel(f)}:{riga}  {vecchio}=  (la firma ora dice "
                  f"{nuovo}, e nessuna «def» del repo dichiara piu' «{vecchio}»)")
        if ambigui:
            print(f"     (gli altri {ambigui} portano un nome che QUALCHE «def» "
                  "dichiara ancora: possono essere firme altrui, chiavi di "
                  "dizionario o parametri di lambda -- vedi «chiamanti_orfani»)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


