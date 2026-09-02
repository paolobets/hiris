"""Il cancello sui NOMI DEGLI STRUMENTI citati dentro le loro definizioni.

**Perche' esiste, con la misura che l'ha motivato.** I nomi degli strumenti
non sono codice che i test coprono: sono DATI che un modello linguistico
legge per decidere cosa chiamare. Cambiandoli a meta' -- il catalogo dice
gia' `view` e la sua description continua a ordinare al modello di chiamare
`guarda` -- la suite non se ne accorge: misurato prima di scrivere questo
file, **3012 test su 3013 restano verdi**. L'unico rosso e'
`test_strumenti_conoscenza.py::
test_la_descrizione_del_bersaglio_etichette_dice_da_dove_si_prende_l_id`,
che nomina due strumenti dentro una description per una ragione che con la
coerenza del catalogo non c'entra: copre 1 sito su 39, e per caso.

Un catalogo che ordina al modello di chiamare un nome che non esiste piu'
e' il guasto peggiore di questa fetta, perche' non produce un'eccezione:
produce un turno in cui HIRIS dice "ho guardato" senza aver guardato.

**Cosa fa.** Per ognuna delle QUATTORDICI definizioni (i tredici di
`casa/strumenti.py`, il catalogo della chat, piu' `CONCLUDI_TOOL_DEF` di
`schedulatore/turno.py`, che vive solo nel turno di una promessa) prende
la `description` e ogni `description` annidata dentro `input_schema` --
proprieta', proprieta' di proprieta', `items` -- ed estrae **ogni parola
dentro ogni coppia di delimitatori**: backtick oppure virgolette caporali.
Una parola che sia MAI STATA un nome di strumento, in italiano o in
inglese, e che NON sia nel catalogo di oggi, fa fallire.

**Il limite, ed e' importante scriverlo qui e non altrove: questo cancello
vede solo le citazioni DELIMITATE.** Dentro le quattordici description ci
sono anche **otto occorrenze NUDE** di quelle stesse parole, e non sono
citazioni: sono italiano ordinario, il verbo o il nome comune. Elencate,
perche' chi legge questo file non deve "correggerle":

    strumenti.py:183  (cerca)     "**guarda il dominio prima di ..."   verbo
    strumenti.py:269  (guarda)    "... non i suoi legami: ..."         nome comune
    strumenti.py:317  (legami)    "... qui i legami sono completi ..." nome comune
    strumenti.py:324  (legami)    "... guarda i primi -- un'area ..."  verbo
    strumenti.py:340  (legami)    "... di cui vuoi i legami ..."       nome comune
    strumenti.py:475  (richiama)  "cerca fra tutti e tre i tipi ..."   verbo
    strumenti.py:608  (prometti)  "... nella pagina delle promesse"    nome comune
    strumenti.py:847  (accaduto)  "... senza, guarda tutta la casa"    verbo

Un cancello che le vedesse pretenderebbe di tradurle, e tradurrebbe
l'italiano: le description restano in italiano, il prodotto parla
italiano. Le otto si distinguono da una citazione soltanto leggendo -- ed
e' per questo che il commit che traduce le citazioni si legge riga per riga
e le elenca nel proprio messaggio.

**Cosa questo cancello NON copre**: la prosa a runtime che vive FUORI dalle
quattordici definizioni. Quella ha il suo cancello gemello in fondo a
questo file, sui testi che si possono importare come costanti; le sei
citazioni sparse dentro funzioni (`casa/domande.py`, `casa/nucleo.py`,
`memoria/interpretazione.py`, `azione/verifica.py`) non hanno rete e si
sono lette a mano.
"""
import re

import pytest

from hiris.app.casa.strumenti import KNOWLEDGE_TOOLS
from hiris.app.schedulatore.turno import CONCLUDI_TOOL_DEF

# I nomi che sono STATI un nome di strumento, in una qualunque delle due
# lingue. E' un elenco STORICO e si scrive a mano: non esiste un posto da
# cui derivarlo, perche' i nomi vecchi per definizione non vivono piu' nel
# codice. Chi aggiunge o rinomina uno strumento aggiunge una riga qui --
# e se se ne dimentica, `test_ogni_nome_del_catalogo_e_nell_elenco_storico`
# (sotto) glielo dice, invece di lasciare il cancello cieco in silenzio.
_NOMI_MAI_STATI_STRUMENTO = frozenset({
    # italiano, fino alla fetta del 02/09
    "cerca", "guarda", "legami", "ricorda", "richiama", "esegui",
    "prometti", "promesse", "disdici", "costruisci", "conferma",
    "andamento", "accaduto", "concludi",
    # inglese, dal 02/09 (docs/GLOSSARIO.md, "I nomi degli strumenti")
    "search", "view", "related", "remember", "fetch", "execute",
    "promise", "agenda", "cancel", "propose", "confirm",
    "trend", "logbook", "conclude",
})

_DEFINIZIONI = list(KNOWLEDGE_TOOLS) + [CONCLUDI_TOOL_DEF]

# Un frammento delimitato: fra backtick, oppure fra caporali. Le due forme
# convivono nelle description di oggi e nessuna delle due e' piu' vera
# dell'altra: si prendono tutte e due.
_DELIMITATO = re.compile("`([^`]*)`|«([^»]*)»")
_PAROLA = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Al ponte gli strumenti arrivano col prefisso del server MCP
# (`mcp__hiris__cerca`): il nome vero e' cio' che viene dopo.
_PREFISSO_MCP = "mcp__hiris__"


def _catalogo() -> frozenset:
    return frozenset(d["name"] for d in _DEFINIZIONI)


def _scendi(dove: str, nodo):
    """Ogni `description` annidata sotto `nodo`, a qualunque profondita'."""
    if not isinstance(nodo, dict):
        return
    if isinstance(nodo.get("description"), str):
        yield dove, nodo["description"]
    for chiave, figlio in (nodo.get("properties") or {}).items():
        yield from _scendi(f"{dove}.{chiave}", figlio)
    if isinstance(nodo.get("items"), dict):
        yield from _scendi(f"{dove}.items", nodo["items"])


def _testi_definizione(definizione: dict):
    """Ogni testo che il modello legge di questa definizione: la sua
    `description` e ogni `description` dello schema degli argomenti."""
    yield "description", definizione["description"]
    schema = (definizione.get("input_schema") or {}).get("properties") or {}
    for chiave, prop in schema.items():
        yield from _scendi(chiave, prop)


def _citazioni(testo: str):
    """Ogni parola dentro ogni coppia di delimitatori, col frammento intero
    accanto: senza il contesto un fallimento direbbe il nome e non dove."""
    for pezzo in _DELIMITATO.finditer(testo):
        frammento = pezzo.group(1) if pezzo.group(1) is not None else pezzo.group(2)
        for parola in _PAROLA.findall(frammento):
            yield parola.removeprefix(_PREFISSO_MCP), frammento


def _citazioni_false(testi) -> list:
    catalogo = _catalogo()
    falsi = []
    for dove, testo in testi:
        for parola, frammento in _citazioni(testo):
            if parola in _NOMI_MAI_STATI_STRUMENTO and parola not in catalogo:
                falsi.append((dove, parola, frammento))
    return falsi


@pytest.mark.parametrize("definizione", _DEFINIZIONI,
                         ids=[d["name"] for d in _DEFINIZIONI])
def test_nessuna_citazione_nomina_uno_strumento_che_non_esiste(definizione):
    """Il cancello vero. Una description che nomina `guarda` mentre il
    catalogo espone `view` ordina al modello di chiamare uno strumento che
    non esiste: il dispatcher risponde "non e' fra quelli disponibili" e il
    turno si brucia, oppure -- peggio -- il modello se ne dimentica e
    racconta di aver guardato."""
    falsi = _citazioni_false(_testi_definizione(definizione))
    assert not falsi, (
        f"la definizione di «{definizione['name']}» cita nomi di strumento "
        f"che il catalogo non espone: {falsi}. Il catalogo di oggi e' "
        f"{sorted(_catalogo())}. O la citazione e' rimasta indietro rispetto "
        "al catalogo, o il catalogo e' rimasto indietro rispetto alla "
        "citazione: le due meta' si cambiano nello stesso commit, mai in due")


def test_ogni_nome_del_catalogo_e_nell_elenco_storico():
    """La guardia sull'elenco scritto a mano. Un quindicesimo strumento --
    o un nome nuovo per uno dei quattordici -- che non venisse aggiunto a
    `_NOMI_MAI_STATI_STRUMENTO` renderebbe il cancello sopra cieco su
    quella riga, e in silenzio: nessuna citazione del nome VECCHIO verrebbe
    piu' riconosciuta come nome di strumento."""
    fuori = _catalogo() - _NOMI_MAI_STATI_STRUMENTO
    assert not fuori, (
        f"{sorted(fuori)} sono nel catalogo ma non nell'elenco storico: "
        "aggiungili a `_NOMI_MAI_STATI_STRUMENTO`, o il cancello non "
        "riconoscera' piu' la citazione del loro nome precedente")


def test_il_catalogo_ha_quattordici_nomi_distinti():
    """Tredici e' il numero del perimetro della CHAT, quattordici quello
    delle definizioni: e' la sesta volta, in questa fetta, che un numero
    giusto su un perimetro sembra sbagliato su un altro (vedi la nota in
    cima a "I nomi degli strumenti" nel glossario). Pinnato qui perche' un
    doppione fra i due cataloghi -- `concludi` che finisse anche nella chat
    -- non lo vedrebbe nessun altro test."""
    nomi = [d["name"] for d in _DEFINIZIONI]
    assert len(nomi) == 14, nomi
    assert len(set(nomi)) == 14, "due definizioni portano lo stesso nome"


def _prose_runtime():
    """I testi che il modello legge e che NON sono una definizione: le due
    guide del ponte, le regole degli strumenti della chat locale, il prompt
    di sistema del turno di promessa, e il testo di DEFAULT delle
    impostazioni della chat.

    Importati come costanti invece che letti dal file: un `grep` sul
    sorgente prenderebbe anche i commenti storici di `agent/prompts.py`,
    che nominano i nomi vecchi APPOSTA (sono il verbale di come quel testo
    e' cambiato) e non devono seguire il codice."""
    from hiris.app.agent.prompts import (
        _GUIDE_WITH_TOOLS,
        _GUIDE_WITHOUT_TOOLS,
    )
    from hiris.app.claude_runner import BASE_TOOL_RULES
    from hiris.app.impostazioni_chat import DEFAULT_SYSTEM_PROMPT
    from hiris.app.schedulatore.turno import _system_prompt
    return [
        ("agent/prompts._GUIDE_WITHOUT_TOOLS", _GUIDE_WITHOUT_TOOLS),
        ("agent/prompts._GUIDE_WITH_TOOLS", _GUIDE_WITH_TOOLS),
        ("claude_runner.BASE_TOOL_RULES", BASE_TOOL_RULES),
        ("schedulatore/turno._system_prompt()", _system_prompt()),
        ("impostazioni_chat.DEFAULT_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
    ]


def test_nessun_prompt_a_runtime_nomina_uno_strumento_che_non_esiste():
    """Il cancello gemello, sulla prosa che sta FUORI dalle definizioni.

    Stessa regola e stesso limite (solo le citazioni delimitate), su cinque
    testi che il modello legge davvero: le due guide del ponte, le regole
    della chat locale, il prompt del turno di promessa e il testo di
    default delle impostazioni. Serve per la stessa ragione del primo: qui
    un nome sbagliato non solleva niente e nessun altro test guarda queste
    stringhe una parola alla volta.

    `impostazioni_chat.DEFAULT_SYSTEM_PROMPT` e' un DEFAULT: chi ha gia'
    salvato il proprio testo in `impostazioni_chat.json` continua a servire
    al modello quello, e questo cancello non lo vede -- ne' potrebbe, quel
    file e' dell'utente."""
    falsi = _citazioni_false(_prose_runtime())
    assert not falsi, (
        f"la prosa a runtime cita nomi di strumento che il catalogo non "
        f"espone: {falsi}. Il catalogo di oggi e' {sorted(_catalogo())}")
