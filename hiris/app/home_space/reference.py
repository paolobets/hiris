"""Il riferimento: quando due modi di scrivere un nome sono lo stesso nome.

Un'area, un piano, un'integrazione scritti da una persona o dal modello si
confrontano con i nomi della casa dopo `normalize` -- maiuscole, accenti e
spazi non contano, gli articoli si' (D5). Lo usano la porta della casa
(`house_query`: nome, area, piano, integrazione), la sua storia
(`house_history`, il filtro degli errori) e il dettaglio di
un'integrazione (`queries.view`).

Nasce con la Tappa 3, Task 9 (B-18, B-20, B-51): il normalizzatore era
`memory/resolver._normalize`, privato e in `memory/`, e i confronti di
area, piano e integrazione se ne scrivevano uno proprio -- esatto o con
`.lower()`. Sulla cattura del 01/10/2026 sera erano 118 casi di
`search` che davano zero righe per una maiuscola.

Una funzione di modulo, non un metodo: `House` (Task 4 della stessa tappa)
non c'e' ancora, e quando arrivera' la richiamera' da qui.
"""
from __future__ import annotations

import re
import unicodedata

# Le parole funzionali dell'italiano. **Vivono nel prodotto, non nel
# cancello** (24/09/2026): erano nate in `tests/test_preposizioni_italiane.py`,
# che le usa per vietare una giuntura italiana dentro un identificatore, e
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
# la lista CONTIENE e' italiano, ed e' un'altra cosa. Stava in
# `memory/resolver.py` fino alla Tappa 3 (Task 9), con `name_matches`.
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




def fold_accents(text: str) -> str:
    """Gli accenti tolti, e nient'altro: «Città» -> «Citta».

    La piegatura di tutto il prodotto (B-20): il riferimento qui sotto, e i
    due slug (`action/construction/composer.available_slug`,
    `keeper/recipient._slugify`), che dopo ci applicano ciascuno il proprio
    filtro ASCII -- quello e' la forma della chiave che Home Assistant
    accetta, non una regola del confronto."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


#: Lo slug di un testo che si riduce al niente (`homeassistant/util/
#: __init__.py::slugify`): non e' uno stato di Home Assistant. Chi lo
#: confronta (`privacy.named_after_person`) lo chiede qui.
NO_SLUG = "unknown"


def slugify(text: str | None) -> str:
    """Replica di `homeassistant.util.slugify(text, separator="_")`
    (che a sua volta chiama il pacchetto PyPI `python-slugify`), per i nomi
    Latini con accenti che un dispositivo smart-home porta nella pratica --
    niente dipendenza nuova per una funzione di poche righe.

    Viveva in `keeper/recipient.py` fino al 06/10/2026: la usano il
    destinatario delle promesse e il segnaposto dei nomi
    (`home_space/privacy.PresenceMask`, G26-1), e una seconda copia sarebbe
    un doppione (B-21 resta aperta per `composer.available_slug`).

    La piegatura degli accenti e' `fold_accents`, qui sopra (Tappa 3, Task 9,
    B-20); il filtro
    ASCII che segue resta di qui, perche' e' la forma dello slug: `"é"` -> `"e"`,
    `"à"` -> `"a"`. Copre il range Latino che un nome di dispositivo usa in
    pratica; **non** e' una traslitterazione fonetica come quella che
    `python-slugify` usa per altri alfabeti (cirillico, greco, CJK
    diventerebbero stringhe vuote qui, non una resa approssimata) -- se la
    casa vera lo richiedesse un giorno, la verifica contro il registro dei
    servizi piu' sotto scarta comunque un candidato sbagliato invece di spingere al
    posto sbagliato.

    Stessa forma dei due casi limite di HA (`homeassistant/util/
    __init__.py::slugify`): testo vuoto o `None` -> stringa vuota; testo che
    si riduce al niente dopo la traslitterazione -> `"unknown"`.

    **Pinnata** in `tests/test_keeper_recipient.py` con i quattro nomi
    misurati sulla casa vera piu' un caso con spazi e accenti (fix round 1,
    26/09/2026).
    """
    if text is None or text == "":
        return ""
    ascii_only = fold_accents(text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_only.lower()).strip("_")
    return slug or NO_SLUG


def normalize(text: str) -> str:
    """Minuscole, accenti tolti, spazi multipli compressi.

    E' l'unica forma di "somiglianza" che il riferimento si concede: non e'
    ricerca approssimata, e' la stessa parola scritta in modo diverso. Gli
    ARTICOLI restano (decisione D5 della Tappa 3, «senza articoli»): «la
    cucina» non e' «cucina», e toglierli sarebbe una regola nuova che
    nessuna copia aveva.
    """
    return re.sub(r"\s+", " ", fold_accents(text.lower())).strip()


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
    words = [w for w in normalize(query).split()
             if w and w not in ITALIAN_FUNCTION_WORDS]
    if not words:
        return False
    target = normalize(name)
    return all(re.search(_word_pattern(word), target) for word in words)
