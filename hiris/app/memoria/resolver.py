"""Riconoscere di quale parte della casa parla una frase.

Oggi non esiste in HIRIS nessun codice che risolva un nome in un'entita':
nessuna normalizzazione, nessun indice sugli alias. Senza questo, "la sala
da pranzo" resta una parola e un'ancora di memoria non si puo' scrivere.

La semantica NON la fa questo modulo. Il modello, che ha la casa in
contesto, e' quello che capisce che "in salotto fa freddo" parla dell'area
"soggiorno" anche se l'utente non ha mai scritto quell'alias: e' esattamente
il principio della specifica -- il modello propone l'ancora nominando il suo
identificatore, e questo modulo restringe:

- `Lookup.find(frase)` e' la RETE: confronto letterale su nomi e alias
  DICHIARATI dall'utente in Home Assistant (sinonimi dati, non indovinati).
  Prende cio' che il modello si dimentica, e funziona anche senza modello.
  Due voci diverse possono normalizzarsi allo stesso testo (due aree
  chiamate "Bagno", un alias che e' il nome vero di un'altra area): quando
  succede, il termine e' AMBIGUO, e `trova()` lo dichiara -- ogni risultato
  porta la lista completa dei `candidati` che quel testo puo' significare,
  non uno scelto a caso. Scegliere spetta al modello, che ha la casa in
  contesto, o all'utente, che puo' correggere dalla pagina: questo modulo
  non sceglie per loro, si limita a non mentire.
- `Lookup.verify(tipo, riferimento)` e' il CANCELLO: controlla che
  l'identificatore che il modello ha nominato esista davvero, con quel
  tipo, nell'anagrafe. Se non esiste, l'ancora non si scrive.

Niente fuzzy, niente embedding: un sinonimo che l'utente non ha dichiarato
non e' un sinonimo, e di fabbrica l'embedder di HIRIS e' spento -- una
ricerca approssimata che ne dipendesse degraderebbe in silenzio.
"""
from __future__ import annotations

import re
import unicodedata

from ..casa.anagrafe import (
    categories_with_name,
    category_names,
    label_names,
    labels_with_name,
)

# Tipi che l'indice riconosce, nello spazio di nomi di verifica(): stessa
# forma dei termini che il modello vede quando la casa gli e' data in
# contesto, cosi' l'ancora che nomina "area" o "entita" e' gia' la chiave
# con cui si cerca qui.
#
# "piani" (T7, R2 -- docs/design/2026-08-20-i-riferimenti.md): stesso
# trattamento di aree/entita/dispositivi, perche' e' la stessa cosa che
# loro sono -- un REGISTRO dell'anagrafe (`_TABELLE`, casa/archivio.py),
# gia' dentro la `casa` che ogni chiamante legge, che puo' mancare
# all'appello di una ricostruzione esattamente come gli altri tre
# (`ArchivioCasa.non_disponibili()`). Prima di questo task nessuna
# sequenza di chiamate produceva mai un id di piano: `esegui(piani=...)`
# lo pretende (`claude_runner.py`), e non esisteva modo di procurarselo.
#
# Automazioni e script NON entrano qui, apposta: vengono da
# `ArchivioCasa.comportamento()`, una fonte diversa (file YAML riletti a
# una cadenza propria, non un registro di Home Assistant) con un proprio
# segnale di incompletezza (`file_non_letti()`, non `non_disponibili()`)
# e un proprio campo `tipo` PER VOCE -- una lista sola contiene sia le
# automazioni sia gli script, a differenza di `_ARCHIVI` dove ogni chiave
# e' UN tipo solo. Mescolarli qui avrebbe fatto sembrare "automazione" un
# registro dell'anagrafe che puo' comparire in `non_disponibili()`, cosa
# che non fa mai -- e avrebbe allargato `STORE_KEY_PER_TYPE` (e con
# lei `_TIPI_ANCORA` in casa/strumenti.py) a tipi che la memoria non puo'
# mai scrivere come ancora (`memoria/interpretazione.VOCABULARY`),
# creando esattamente il secondo vocabolario che R9 denuncia altrove.
# `costruisci_indice()` le indicizza per conto suo, sotto: stessa forma
# dei candidati, fonte e ciclo di vita diversi.
_ARCHIVI = (("aree", "area"), ("entita", "entita"), ("dispositivi", "dispositivo"),
           ("piani", "piano"))

# Stessa mappa di _ARCHIVI, capovolta: dato il tipo di un'ancora, la chiave
# del registro che l'anagrafe usa per quel tipo. Pubblica perche' serve a chi
# deve sapere se QUEL registro specifico ha risposto all'ultima lettura
# (`ArchivioCasa.non_disponibili()`), non solo se l'anagrafe intera e' stata
# letta -- vedi handlers_memoria.py.
STORE_KEY_PER_TYPE: dict[str, str] = {type: key for key, type in _ARCHIVI}


def _normalize(text: str) -> str:
    """Minuscole, accenti tolti, spazi multipli compressi.

    E' l'unica forma di "somiglianza" che questo modulo si concede: non e'
    ricerca approssimata, e' la stessa parola scritta in modo diverso.
    """
    text = text.lower()
    decomposto = unicodedata.normalize("NFKD", text)
    senza_accenti = "".join(c for c in decomposto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", senza_accenti).strip()


def _normalize_con_mappa(text: str) -> tuple[str, list[int]]:
    """Come `_normalizza`, ma restituisce anche la mappa posizione
    normalizzata -> posizione originale.

    `trova()` cerca sul testo normalizzato, ma `nome_visto` deve restare
    cio' che l'utente ha scritto davvero (maiuscole, accenti, spaziatura),
    non il testo normalizzato: oggi non morde perche' nessuno lo archivia,
    ma nella fetta E sarebbe gia' una riscrittura silenziosa di cio' che
    l'utente ha detto -- e il testo e' la verita' (memoria/archivio.py,
    regola 1).

    Minuscolo e NFKD-senza-combinanti sono, carattere per carattere, quasi
    sempre 1:1; la compressione degli spazi multipli invece sposta le
    posizioni, quindi va tracciata esplicitamente invece di essere assunta.
    """
    minuscolo = text.lower()
    reading: list[str] = []
    mappa_grezza: list[int] = []
    for original_index, carattere in enumerate(minuscolo):
        decomposto = unicodedata.normalize("NFKD", carattere)
        for c in decomposto:
            if unicodedata.combining(c):
                continue
            reading.append(c)
            mappa_grezza.append(original_index)

    normalizzato: list[str] = []
    mappa: list[int] = []
    previous_space = True  # tronca anche gli spazi iniziali, come .strip()
    for c, original_index in zip(reading, mappa_grezza):
        if re.match(r"\s", c):
            if previous_space:
                continue
            previous_space = True
            normalizzato.append(" ")
            mappa.append(original_index)
        else:
            previous_space = False
            normalizzato.append(c)
            mappa.append(original_index)
    while normalizzato and normalizzato[-1] == " ":
        normalizzato.pop()
        mappa.pop()
    return "".join(normalizzato), mappa


def _e_carattere_di_parola(carattere: str) -> bool:
    return re.match(r"\w", carattere) is not None


def _compila(term: str) -> re.Pattern[str]:
    """Compila il pattern di un termine una volta sola: farlo a ogni
    chiamata di trova() si appoggia alla cache implicita di `re`, che ha un
    tetto fisso di 512 pattern condiviso con tutto il processo -- oltre
    quella soglia ricompila in continuazione, ed e' li' che il costo esplode
    (misurato: 7 ms a 200 entita', 76 ms a 300).

    `\\b` e' un punto di transizione tra un carattere di parola e uno che non
    lo e': se il bordo del termine e' gia' non-parola (una parentesi, un
    apostrofo), pretendere `\\b` li' non trova mai nulla, perche' nel
    linguaggio naturale dopo/prima di quel bordo viene uno spazio, un altro
    segno di punteggiatura o la fine della frase. Il confine si mette solo
    dove il bordo e' un carattere di parola."""
    prefix = r"(?<!\w)" if _e_carattere_di_parola(term[0]) else ""
    suffix = r"(?!\w)" if _e_carattere_di_parola(term[-1]) else ""
    return re.compile(prefix + re.escape(term) + suffix)


class Lookup:
    """L'indice dei nomi e alias di una casa, pronto per riconoscere e
    verificare. Si costruisce con `costruisci_indice()`, non direttamente."""

    def __init__(self, termini: dict[str, list[tuple[str, str]]],
                 per_type: dict[str, dict[str, dict]]) -> None:
        # I termini piu' lunghi vincono e consumano il testo, cosi' "sala da
        # pranzo" non collassa su "sala": l'ordine e' deciso una volta sola,
        # non a ogni chiamata di trova(). Un testo normalizzato che piu'
        # voci condividono (due aree omonime, un alias che collide col nome
        # di un'altra) non viene deciso qui: resta un unico termine con piu'
        # candidati, ed e' trova() a dichiararlo, non a sceglierne uno.
        #
        # Le espressioni pero' NON si compilano qui: costruisci_indice()
        # gira a ogni GET/PATCH di /api/memoria (handlers_memoria.py), ma
        # quelle rotte usano solo verifica() -- un accesso a dizionario.
        # Compilare un pattern per termine per una richiesta che non chiama
        # mai trova() e' lavoro morto (misurato: 16,8 ms a 380 voci). Si
        # compila pigri, alla prima trova(), e resta cache per la vita di
        # questo Lookup.
        self._termini_grezzi = sorted(termini.items(), key=lambda kv: len(kv[0]), reverse=True)
        self._termini_compilati: list[tuple[list[tuple[str, str]], re.Pattern[str]]] | None = None
        self._per_type = per_type

    def _termini(self) -> list[tuple[list[tuple[str, str]], re.Pattern[str]]]:
        if self._termini_compilati is None:
            self._termini_compilati = [
                (candidati, _compila(term)) for term, candidati in self._termini_grezzi
            ]
        return self._termini_compilati

    def find(self, phrase: str) -> list[dict]:
        """I riferimenti riconosciuti in `frase`, sui confini di parola.

        Nessun risultato non e' un errore: e' la regola (3) della struttura
        (docs/design/2026-08-05-la-conoscenza-di-hiris.md) -- "non riconosce
        niente? resta testo e funziona come oggi". "cucinare" non nomina la
        cucina perche' il confine di parola dopo "cucina" non c'e'.

        Ogni risultato porta `candidati`, la lista di TUTTE le voci (tipo +
        riferimento) che quel testo puo' significare, e `ambiguo`, vero
        quando sono piu' di una. Non c'e' un "il" riferimento: un testo che
        piu' voci condividono e' ambiguo per costruzione, e questo modulo
        non sceglie al posto del modello o dell'utente.

        `nome_visto` e' il testo ORIGINALE (maiuscole, accenti, spaziatura
        di chi ha scritto la frase), non il testo normalizzato su cui si
        cerca: il testo e' la verita' (memoria/archivio.py, regola 1), e
        vale anche per il frammento riconosciuto, non solo per la frase
        intera.
        """
        normalizzata, mappa = _normalize_con_mappa(phrase)
        if not normalizzata:
            return []

        intervalli_occupati: list[tuple[int, int]] = []
        trovate: list[tuple[int, dict]] = []
        for candidati, pattern in self._termini():
            for m in pattern.finditer(normalizzata):
                inizio, fine = m.span()
                if any(inizio < f and i < fine for i, f in intervalli_occupati):
                    continue
                intervalli_occupati.append((inizio, fine))
                inizio_originale = mappa[inizio]
                fine_originale = mappa[fine - 1] + 1
                trovate.append((inizio, {
                    "nome_visto": phrase[inizio_originale:fine_originale],
                    "candidati": [{"tipo": type, "riferimento": reference}
                                  for type, reference in candidati],
                    "ambiguo": len(candidati) > 1,
                }))

        trovate.sort(key=lambda t: t[0])
        return [entry for _, entry in trovate]

    def verify(self, type: str, reference: str) -> dict | None:
        """L'oggetto dell'anagrafe se `riferimento` esiste con quel `tipo`,
        altrimenti None.

        E' il punto in cui "il modello propone, il codice restringe"
        diventa codice: un'ancora che il modello si e' inventata non entra.
        Nessuna somiglianza qui -- tipi diversi sono spazi di nomi diversi,
        e un id di entita' passato come area non deve passare.
        """
        return self._per_type.get(type, {}).get(reference)

    def tutti(self, type: str) -> list[dict]:
        """Tutte le voci dell'anagrafe di un tipo — aree, entita' o dispositivi.

        Serve a chi deve DEDURRE qualcosa dalla casa invece che verificarla:
        per esempio l'unita' di misura di un'area, che si ricava dall'entita'
        di quell'area la cui classe combacia con la grandezza. E' pubblico
        perche' altrimenti chi ne ha bisogno finisce a leggere `_per_type`, e
        un accoppiamento a un dettaglio interno si propaga in silenzio.
        """
        return list(self._per_type.get(type, {}).values())


def _log(termini: dict[str, list[tuple[str, str]]], term_originale,
              candidate: tuple[str, str]) -> None:
    """Aggiunge `candidato` (tipo, riferimento) al termine che
    `term_originale` normalizza a -- il cuore di `costruisci_indice()`,
    estratto perche' anagrafe e comportamento (sotto) lo condividono: due
    copie della stessa regola di dedup/ambiguita' sarebbero due posti in
    cui la stessa correzione si dimentica di un posto.

    Un termine che non e' una stringa non e' un termine (vedi il commento
    dentro il ciclo principale, sugli alias `[null]` di un'anagrafe gia'
    avvelenata) -- difesa in profondita', non ridondanza."""
    if not isinstance(term_originale, str):
        return
    term_normalizzato = _normalize(term_originale)
    if not term_normalizzato:
        return
    candidati = termini.setdefault(term_normalizzato, [])
    if candidate not in candidati:
        candidati.append(candidate)


def costruisci_indice(home_space: dict,
                      nomi_di_ripiego: dict[str, str] | None = None,
                      behavior: list[dict] | None = None) -> Lookup:
    """Costruisce l'indice di una casa: nome e alias di aree, entita',
    dispositivi e piani, PIU' automazioni e script (`comportamento`, T7),
    normalizzati e pronti per trova()/verifica().

    Due voci diverse possono normalizzarsi allo stesso termine (due aree
    omonime, un alias che e' il nome vero di un'altra voce): il termine
    resta uno solo, ma raccoglie TUTTI i candidati che lo condividono,
    cosi' trova() puo' dichiarare l'ambiguita' invece di sceglierne uno in
    silenzio in base all'ordine di raccolta.

    `nomi_di_ripiego` (entity_id -> `friendly_name`) NON e' un rimedio per i
    casi rari in cui il nome manca: sull'impianto del proprietario, misurato
    il 14 agosto, e' la STRADA NORMALE. `casa/archivio.py:133` prende il nome
    dell'entita' da `name or original_name` del REGISTRO, e li' il nome e'
    nullo QUASI OVUNQUE (le quattro valvole dell'irrigazione, le abat-jour);
    nello specchio dello stato vivo il `friendly_name` c'e' invece su TUTTE
    e 849 le entita' vive -- zero vuote -- e sono i nomi buoni:
    `valve.giardino_ingresso` -> «Giardino ingresso»,
    `light.abat_jour_sinistra_abat_jour_sinistra` -> «Abat-jour sinistra».

    HIRIS leggeva i nomi dal posto sbagliato, e senza ripiego l'indice di
    ricerca e' quasi vuoto di nomi. Un'entita' senza nome non e' "non
    trovata": e' INESISTENTE nello spazio in cui si cerca -- nessun nome,
    nessun termine, invisibile. E' lo stesso criterio del nucleo: il modello
    perde la possibilita' di sapere che quella cosa esiste, e sono i quattro
    giri di `cerca` bruciati sulle abat-jour.

    Il ripiego e' il `friendly_name`, non l'`entity_id`: e' cio' che Home
    Assistant mostra all'utente ed e' la parola che una persona userebbe
    parlando. Lo specchio dello stato lo conserva gia'
    (`proxy/entity_cache._to_minimal`, chiave "name"). Un id tecnico non
    entra qui, ne' tale e quale ne' ingentilito: sarebbe un nome che nessuno
    ha mai pronunciato. E i nomi veri portano in dote un raggruppamento che
    nessun meccanismo deve costruire: quattro «Giardino ...» dicono da soli
    che sono un impianto solo.

    Un nome dedotto **non si spaccia per dichiarato**: la voce guadagna
    `nome_dedotto` e `nome` resta com'era nel registro (vuoto o None: non si
    riscrive). Chi legge puo' dirlo, e chi confronta i nomi DICHIARATI
    dall'utente non inciampa in uno che l'utente non ha mai scritto. Vale il
    doppio proprio perche' qui il dedotto e' la norma, non l'eccezione.

    **Cio' che il ripiego non copre, e che non si nasconde:** lo specchio
    dello stato conosce solo le entita' con uno stato vivo -- 849 contro le
    1.225 del registro. Per le altre 376 non esiste un `friendly_name` da
    nessuna parte: restano senza nome e quindi fuori da `trova()`,
    esattamente come oggi. Non spariscono (`verifica()` e `tutti()`
    continuano a vederle) e non si inventa loro un nome dall'id.

    Il ripiego vale solo per le entita': lo specchio dello stato non ha
    `friendly_name` per aree e dispositivi, e un ripiego li' sarebbe di
    nuovo un id travestito da nome.

    `comportamento` (T7, R2): le voci di `ArchivioCasa.comportamento()` --
    automazioni e script, col loro `tipo` ("automazione" o "script") gia'
    dentro ogni voce, non nella chiave del dizionario `casa` come per
    `_ARCHIVI` sopra. Indicizzate con la STESSA disciplina (nome, alias,
    etichette, categorie; ambiguita' dichiarata, mai scelta), ma FUORI dal
    ciclo su `_ARCHIVI`: sono lette da una fonte diversa, con un ciclo di
    vita diverso (file YAML riletti a una cadenza propria, non un registro
    di Home Assistant) -- vedi il commento su `_ARCHIVI` per la ragione per
    cui non condividono la stessa tupla. Nessun ripiego sul nome qui: le
    voci di comportamento arrivano gia' con un nome (`friendly_name` dello
    stato o l'`alias` dello YAML -- vedi `casa/comportamento.py`), mai nullo
    per costruzione.
    """
    termini: dict[str, list[tuple[str, str]]] = {}
    per_type: dict[str, dict[str, dict]] = {}
    downgrade = nomi_di_ripiego or {}
    nomi_etichette = label_names(home_space)
    nomi_categorie = category_names(home_space)

    for store_key, type in _ARCHIVI:
        registry = per_type.setdefault(type, {})
        for entry in home_space.get(store_key) or []:
            reference = entry.get("id")
            if reference is None:
                continue

            name = entry.get("nome") or ""
            deduced = ""
            if not name.strip() and type == "entita":
                deduced = (downgrade.get(reference) or "").strip()
            if deduced:
                # Copia, non mutazione in place: `voce` e' il dizionario che
                # `ArchivioCasa.leggi()` ha appena costruito per il
                # chiamante, e marcarlo li' accoppierebbe l'indice al ciclo
                # di vita di una struttura che non gli appartiene.
                entry = dict(entry)
                entry["nome_dedotto"] = deduced
            registry[reference] = entry

            # Nome, alias E ETICHETTE. Le etichette sono parole che l'utente
            # ha scritto lui in Home Assistant («inverno», «da controllare»):
            # se non portano a niente, HIRIS gli chiede di ripetere a parole
            # cio' che aveva gia' dichiarato una volta. Non diventano il NOME
            # di niente -- entrano solo qui, fra i termini che `trova()`
            # riconosce, e il nome resta quello che era.
            #
            # Col NOME, non col `label_id`: nei registri Home Assistant mette
            # gli slug (`da_controllare`), e indicizzare quelli avrebbe fatto
            # funzionare la ricerca SOLO per le etichette di una parola sola
            # senza maiuscole. Nessuno cerca «da_controllare»: si cerca «da
            # controllare». L'unione la fa `casa.anagrafe.etichette_con_nome`,
            # la stessa che usa `guarda` -- scritta due volte sarebbe una
            # ricerca che trova per un nome e una risposta che ne mostra un
            # altro.
            # E le CATEGORIE, per la stessa ragione e con la stessa
            # trappola: sono l'altra tassonomia che l'utente scrive a mano in
            # Home Assistant («Luci esterne», «Vacanza»), e nei registri HA
            # manda i soli `category_id`. Entrano col NOME -- l'unione la fa
            # `casa.anagrafe.categorie_con_nome`, la stessa che usa `guarda`.
            # Solo i nomi, non gli ambiti: `automation` e' un termine tecnico
            # di Home Assistant, non una parola che qualcuno cerchera'.
            # Un termine che non e' una stringa non e' un termine.
            #
            # Difesa in profondita', non ridondanza: la causa vera si
            # chiude a monte (`ha_client._aggiungi_campi_estesi` filtra le
            # sentinelle `None` degli alias), ma questo indice legge
            # l'ARCHIVIO -- che su un'installazione gia' avvelenata
            # contiene ancora `[null]` finche' l'anagrafe non si ricostruisce.
            # Un rilevatore che muore sul dato vecchio lascia `cerca` e
            # `ricorda` rotti fino al riavvio successivo. Vedi `_log`.
            for term_originale in [deduced or name, *(entry.get("alias") or []),
                                      *labels_with_name(entry, nomi_etichette),
                                      *categories_with_name(entry, nomi_categorie).values()]:
                _log(termini, term_originale, (type, reference))

    # Automazioni e script (T7, R2): stessa disciplina, fonte diversa --
    # vedi il commento su `_ARCHIVI` e il docstring qui sopra. `tipo` viene
    # dalla VOCE stessa, non da `_ARCHIVI`: una lista sola porta entrambi i
    # tipi, distinti campo per campo (`casa/comportamento.py`). Una voce col
    # `tipo` che non e' ne' "automazione" ne' "script", o senza `id`, non e'
    # una voce di comportamento valida: si scarta invece di indicizzarla
    # sotto un tipo che ne' `guarda` ne' `verifica()` altrove riconoscono.
    for entry in behavior or []:
        entry_type = entry.get("tipo")
        reference = entry.get("id")
        if entry_type not in ("automazione", "script") or reference is None:
            continue
        registry = per_type.setdefault(entry_type, {})
        registry[reference] = entry
        for term_originale in [entry.get("nome") or "", *(entry.get("alias") or []),
                                  *labels_with_name(entry, nomi_etichette),
                                  *categories_with_name(entry, nomi_categorie).values()]:
            _log(termini, term_originale, (entry_type, reference))

    # Le etichette STESSE (T8, R2 -- docs/design/2026-08-20-i-riferimenti.md
    # §2): fin qui sopra un'etichetta entrava nell'indice SOLO come termine
    # che porta a un'entita'/area/dispositivo/automazione che la porta (vedi
    # "Nome, alias E ETICHETTE" piu' sopra) -- mai come candidato essa
    # stessa. Un'etichetta ancora inutilizzata, o assegnata solo a cose
    # disabilitate o fuori registro, restava IRRAGGIUNGIBILE: nessuna
    # sequenza di chiamate produceva mai il suo `label_id`, che
    # `esegui(bersaglio.etichette=...)` pretende -- il vicolo cieco piu'
    # radicale della famiglia (R2). Qui il suo NOME diventa un termine che
    # porta a SE STESSA -- tipo "etichetta", riferimento il suo `label_id`
    # -- cosi' un modello che sa solo il nome arriva all'id con UNA sola
    # chiamata a `cerca`, invece di doverne prima trovare una cosa che la
    # porta (che potrebbe non esistere).
    #
    # Fonte diversa da `_ARCHIVI` per lo stesso motivo di `comportamento`
    # (vedi il commento su `_ARCHIVI` in cima al modulo): la tabella
    # `etichette` non e' una voce con `nome`/`alias`/`etichette` proprie, e'
    # gia' l'unione id->nome (`nomi_delle_etichette`, sopra). Un nome vuoto o
    # un id assente non e' un'etichetta indicizzabile: si scarta invece di
    # registrare un termine muto o un candidato senza riferimento.
    label_registry = per_type.setdefault("etichetta", {})
    for e in home_space.get("etichette") or []:
        label_id = e.get("id")
        if label_id is None:
            continue
        label_name = (e.get("nome") or "").strip() or str(label_id)
        label_registry[label_id] = {"id": label_id, "nome": label_name}
        _log(termini, label_name, ("etichetta", label_id))

    return Lookup(termini, per_type)
