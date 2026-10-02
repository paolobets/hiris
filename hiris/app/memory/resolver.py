"""Riconoscere di quale parte della casa parla una frase.

La semantica NON la fa questo modulo. Il modello, che ha la casa in
contesto, e' quello che capisce che "in salotto fa freddo" parla dell'area
"soggiorno" anche se l'utente non ha mai scritto quell'alias: e' esattamente
il principio della specifica -- il modello propone l'ancora nominando il suo
identificatore, e questo modulo restringe:

- `Lookup.verify(tipo, riferimento)` e' il CANCELLO: controlla che
  l'identificatore che il modello ha nominato esista davvero, con quel
  tipo, nell'anagrafe. Se non esiste, l'ancora non si scrive.
- `name_matches(frase, nome)` e' il confronto dei nomi che usa la porta della
  casa (`home_space/house_query.py`).

Fino alla 3.72.2 c'era anche `Lookup.find(frase)`, la «rete» che riconosceva
nomi e alias dentro una frase. Nessun chiamante di produzione la usava piu'
(voce M-08 del registro), ed e' uscita con la Tappa 0 dello sprint «Una fonte
sola di verita'» insieme all'indice dei termini e ai nomi di ripiego, che
servivano solo a lei.

Niente fuzzy, niente embedding: un sinonimo che l'utente non ha dichiarato
non e' un sinonimo, e HIRIS non ha un embedder.
"""
from __future__ import annotations

import re
import unicodedata

# Tipi che l'indice riconosce, nello spazio di nomi di `Lookup.verify()`: stessa
# forma dei termini che il modello vede quando la casa gli e' data in
# contesto, cosi' l'ancora che nomina "area" o "entita" e' gia' la chiave
# con cui si cerca qui.
#
# I PIANI (e le ETICHETTE come candidati di se stesse) ci sono stati dal T7
# (R2, docs/design/2026-08-20-i-riferimenti.md) al 30/09/2026: servivano alla
# vecchia ricerca per nome, che doveva produrre l'id di un piano per
# `execute(piani=...)`. Da «una porta sola per la casa» il piano e' un FILTRO
# della porta (`house_query`), e l'unico lettore rimasto di questo indice e'
# `remember`, che ancora solo aree, entita' e dispositivi
# (`memory/interpretation.VOCABULARY`): un candidato che nessuno puo' usare e'
# codice morto, ed e' uscito (review finale, M3).
#
# Automazioni e script NON entrano qui, apposta: vengono dal comportamento
# (`HomeSpace.behavior()`, in `home_space/reader.py`), una fonte diversa (non
# un registro di Home Assistant) con un proprio
# segnale di incompletezza (`unread_bodies()`, non `unavailable()`)
# e un proprio campo `tipo` PER VOCE -- una lista sola contiene sia le
# automazioni sia gli script, a differenza di `_ARCHIVI` dove ogni chiave
# e' UN tipo solo. Mescolarli qui avrebbe fatto sembrare "automazione" un
# registro dell'anagrafe che puo' comparire in `unavailable()`, cosa
# che non fa mai -- e avrebbe allargato `STORE_KEY_PER_TYPE` (e con
# lei `_TETHER_TYPES` in home_space/tools.py) a tipi che la memoria non puo'
# mai scrivere come ancora (`memory/interpretation.VOCABULARY`),
# creando esattamente il secondo vocabolario che R9 denuncia altrove.
# Fino al 29/09/2026 `costruisci_indice()` le indicizzava per conto suo, per
# la vecchia ricerca per nome (`queries.search`); uscita quella, nessun
# chiamante le chiedeva piu' -- la porta della casa (`home_space/
# house_query.py`) confronta i nomi da se' -- e il parametro e' uscito con
# lei.
_ARCHIVI = (("aree", "area"), ("entita", "entita"), ("dispositivi", "dispositivo"))

# Stessa mappa di _ARCHIVI, capovolta: dato il tipo di un'ancora, la chiave
# del registro che l'anagrafe usa per quel tipo. Pubblica perche' serve a chi
# deve sapere se QUEL registro specifico ha risposto all'ultima lettura
# (`HomeSpace.unavailable()`), non solo se l'anagrafe intera e' stata
# letta -- vedi handlers_memory.py.
STORE_KEY_PER_TYPE: dict[str, str] = {type: key for key, type in _ARCHIVI}


# Le parole funzionali dell'italiano. **Vivono qui, non nel cancello**
# (24/09/2026): erano nate in `tests/test_preposizioni_italiane.py`, che le
# usa per vietare una giuntura italiana dentro un identificatore, e da oggi
# servono anche al prodotto -- `name_matches` (qui sotto, la porta della
# casa dal 29/09/2026) deve sapere che «della» non e' il nome di niente
# prima di andarlo a cercare fra i nomi della casa (sulla casa vera «della»
# compare in undici nomi: cercarla porterebbe undici candidati che non
# c'entrano a ogni domanda che contiene una preposizione, cioe' quasi tutte).
#
# La lista NON si ricopia di la': un cancello chiede il suo elenco
# (CLAUDE.md, I-0), e due copie della stessa lista sono due posti in cui la
# stessa aggiunta si dimentica di un posto. Il cancello importa da qui.
#
# Il nome e' inglese perche' questo modulo e' un ambito convertito; cio' che
# la lista CONTIENE e' italiano, ed e' un'altra cosa.
ITALIAN_FUNCTION_WORDS = frozenset([
    # preposizioni proprie
    "di", "da", "con", "su", "tra", "fra",
    # preposizioni articolate
    "del", "dello", "della", "dei", "degli", "delle",
    "al", "allo", "alla", "ai", "agli", "alle",
    "dal", "dallo", "dalla", "dai", "dagli", "dalle",
    "nel", "nello", "nella", "nei", "negli", "nelle",
    "col", "collo", "colla", "coi", "cogli", "colle",
    "sul", "sullo", "sulla", "sui", "sugli", "sulle",
    "pel", "pei",
    # preposizioni improprie e locuzioni
    "sopra", "sotto", "dopo", "prima", "senza", "oltre", "durante", "dentro",
    "fuori", "verso", "contro", "tranne", "salvo", "presso", "mediante",
    "tramite", "entro", "dietro", "davanti", "attraverso", "nonostante", "malgrado",
    # articoli
    "il", "lo", "la", "gli", "le", "un", "uno", "una",
    # congiunzioni e negazione
    "e", "ed", "che", "come", "non",
    # Terza chiusura della lista (01/09). Le due volte precedenti mancavano
    # forme CON occorrenze (`a` nuda e le elisioni la prima, `non`/`senza`/
    # `che`/`come`/`oltre`/`durante` la seconda); questa volta le forme
    # aggiunte hanno **zero occorrenze oggi**, ed e' il punto: il docstring
    # gia' diceva che le forme senza occorrenze «costano nulla e chiudono la
    # lista invece di aspettare la terza volta», e la terza volta e' arrivata
    # lo stesso. Si chiude la CLASSE GRAMMATICALE, non i casi incontrati.
    "ma", "se", "oppure", "pero", "quindi", "dunque", "anche", "pure",
    "poiche", "benche", "sebbene", "finche", "mentre", "cioe", "invece",
    "ne", "neanche", "nemmeno", "neppure", "anzi", "ossia", "nonche",
    "insieme", "accanto", "vicino", "intorno", "rispetto", "riguardo",
    "eccetto", "escluso", "incluso", "compreso",
])


def _normalize(text: str) -> str:
    """Minuscole, accenti tolti, spazi multipli compressi.

    E' l'unica forma di "somiglianza" che questo modulo si concede: non e'
    ricerca approssimata, e' la stessa parola scritta in modo diverso.
    """
    text = text.lower()
    decomposto = unicodedata.normalize("NFKD", text)
    senza_accenti = "".join(c for c in decomposto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", senza_accenti).strip()


#: Sotto questa lunghezza una parola non ha radice: «luc» a inizio di parola
#: troverebbe «lucernario», e «tv» senza vocale niente di sensato. A quattro
#: lettere cambia solo il numero (`_NUMBER_PAIRS`, sotto).
STEM_MIN_LENGTH = 5


def _stem(word: str) -> str:
    """La radice di una parola italiana, nel senso piu' povero e dichiarato:
    la vocale finale tolta. Basta a far incontrare singolare e plurale
    («rifiuto»/«rifiuti», «indifferenziato»/«indifferenziata»), ed e' tutto
    cio' che la batteria del 29/09/2026 ha chiesto."""
    if len(word) >= STEM_MIN_LENGTH and word[-1] in "aeiou":
        return word[:-1]
    return word


#: Le vocali finali che fanno coppia singolare/plurale in italiano: -o/-i
#: («faro»/«fari»), -a/-e («casa»/«case»), -e/-i («luce»/«luci»). Servono
#: alle parole di QUATTRO lettere (review finale della fetta «una porta
#: sola», M4, 30/09/2026): «luci» non trovava «Luce». Una parola di quattro
#: lettere si confronta ancora INTERA -- nessun prefisso: «luce» non trova
#: «lucernario» -- e la sua vocale finale puo' cambiare solo nella propria
#: coppia: «casa» trova «case» ma non «caso», «pala» non trova «palo». Il
#: residuo dichiarato: la regola sa di grammatica, non di significato, e
#: «casi» trova anche «case» (tutte e due plurali di parole diverse).
_NUMBER_PAIRS = {"a": "ae", "e": "eai", "i": "ieo", "o": "oi"}
#: La lunghezza a cui vale la coppia: sotto e' sempre intera, sopra c'e' la
#: radice (`STEM_MIN_LENGTH`).
_PAIR_LENGTH = 4


def _word_pattern(word: str) -> str:
    stem = _stem(word)
    if stem != word:
        return rf"(?<!\w){re.escape(stem)}\w*"
    if len(word) == _PAIR_LENGTH and word[-1] in _NUMBER_PAIRS:
        return rf"(?<!\w){re.escape(word[:-1])}[{_NUMBER_PAIRS[word[-1]]}](?!\w)"
    return rf"(?<!\w){re.escape(word)}(?!\w)"


def name_matches(query: str, name: str) -> bool:
    """Vero se ogni parola significativa di `query` sta in `name`, intera o
    (dalle cinque lettere in su) come radice a inizio di parola; a quattro
    lettere, intera o col numero cambiato (`_NUMBER_PAIRS`)."""
    words = [w for w in _normalize(query).split()
             if w and w not in ITALIAN_FUNCTION_WORDS]
    if not words:
        return False
    target = _normalize(name)
    return all(re.search(_word_pattern(word), target) for word in words)


class Lookup:
    """L'anagrafe di una casa, pronta per verificare un'ancora e per elencare
    le voci di un tipo. Si costruisce con `costruisci_indice()`."""

    def __init__(self, per_type: dict[str, dict[str, dict]]) -> None:
        self._per_type = per_type

    def verify(self, type: str, reference: str) -> dict | None:
        """L'oggetto dell'anagrafe se `reference` esiste con quel `type`,
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
        di quell'area la cui classe combacia con la grandezza.
        """
        return list(self._per_type.get(type, {}).values())


def costruisci_indice(home_space: dict) -> Lookup:
    """L'indice di una casa: le voci di aree, entita' e dispositivi, per tipo
    e per identificatore."""
    per_type: dict[str, dict[str, dict]] = {}
    for store_key, type in _ARCHIVI:
        registry = per_type.setdefault(type, {})
        for entry in home_space.get(store_key) or []:
            reference = entry.get("id")
            if reference is not None:
                registry[reference] = entry
    return Lookup(per_type)
