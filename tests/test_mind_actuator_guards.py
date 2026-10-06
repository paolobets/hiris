"""I cancelli dell'attuatore (spec 2026-09-21 §7) — rifatti il 21/09 per I-0.

Le cose che si rompono **in silenzio**: un confine dichiarato in un documento e
non custodito da niente, e un turno pagato due volte. Nessuna delle due si
vedrebbe guardando la pagina.

**Perche' questo file e' stato rifatto.** Il cancello precedente elencava A MANO
tre porte di scrittura. `ha_client` ne espone **quarantatre** pubbliche su **due
canali** -- HTTP e websocket -- e le quattro che scrivono via websocket
(`create_helper`, `delete_helper`, `create_label`, `add_label_to`) non erano
nell'elenco. Un cancello che RICOPIA una lista invecchia in silenzio: l'originale
cresce, la copia no, e il cancello resta verde mentre il buco si apre.

**Adesso l'elenco si CHIEDE, non si scrive.** Alle porte lo chiede il sorgente di
`ha_client`; ai moduli dell'attuatore lo chiede il grafo delle chiamate di
tutto `hiris/app`; alle due porte-modulo lo chiede `CLAUDE.md`, che le dichiara. Una
porta nuova e una funzione nuova entrano nel cancello **il giorno in cui
nascono**, non il giorno in cui qualcuno se ne ricorda.

**La sola lista scritta a mano che resta e' quella delle ECCEZIONI** (`AMMESSI`),
ed e' di un'altra specie: non ricopia un fatto che vive altrove, **enuncia il
cancello**. Chiude per difetto -- un metodo nuovo dell'officina e' vietato finche'
qualcuno non lo ammette per iscritto, con la ragione accanto.
"""
import ast
import asyncio
import json
import pathlib
import re

import pytest

from hiris.app.home_space import historian
from hiris.app.mind.proposer_round import proposer_round
from hiris.app.mind.store import ObservationsStore

OGGI = historian.today(historian.house_timezone(None)).isoformat()

RADICE = pathlib.Path(__file__).resolve().parents[1]
_CLIENT = RADICE / "hiris" / "app" / "proxy" / "ha_client.py"
_APP = RADICE / "hiris" / "app"
_GIRO = _APP / "mind" / "proposer_round.py"

#: La radice del grafo: il giro del proponente (attori, Task 4.2). Fino al
#: 06/10/2026 era `actuator_round`, in `server.py`.
RADICE_GIRO = "proposer_round"

#: Il gesto dell'attuatore che PUO' toccare una porta, e perche'.
#:
#: `propose` compone e valida contro questa casa e **non scrive niente**: la
#: scrittura e' un turno diverso, col si' del proprietario (spec §3). E' il gesto
#: «propone», ed e' l'unica ragione per cui l'attuatore nomina l'officina.
#:
#: `notify_admins` (`keeper/delivery.py`) e' una FUNZIONE, non un metodo di una
#: porta: l'avviso agli amministratori per una proposta `alto` (D14 del piano
#: degli attori, strati 3-4, approvata dal proprietario il 06/10/2026: «una
#: notifica agli amministratori, con lo stesso recapito delle promesse,
#: attraverso `action/actuator.py`»). Il proponente la chiama, e il grafo **si
#: ferma li'**: il suo corpo legge gli utenti e i telefoni da Home Assistant e
#: spinge dalla porta dei servizi, ma solo una push di forma fissa
#: (`promise.delivery_call`) verso i servizi che dice il recapito -- mai un
#: servizio scelto dal modello. Ammettere `execute` al posto suo avrebbe dato
#: al proponente l'intera porta dei servizi.
#:
#: Questa lista non ricopia niente: **dice cosa il cancello ammette**. Un metodo
#: nuovo dell'officina non entra qui da solo -- va ammesso a mano, con la ragione,
#: che e' esattamente il momento in cui qualcuno deve pensarci.
AMMESSI = frozenset({"propose", "notify_admins"})


def _albero(percorso: pathlib.Path):
    return ast.parse(percorso.read_text(encoding="utf-8"))


def _metodi_pubblici(percorso: pathlib.Path) -> frozenset[str]:
    """I metodi pubblici di ogni classe di un modulo, letti dal sorgente."""
    return frozenset(
        figlio.name
        for nodo in _albero(percorso).body if isinstance(nodo, ast.ClassDef)
        for figlio in nodo.body
        if isinstance(figlio, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not figlio.name.startswith("_"))


def porte_home_assistant() -> frozenset[str]:
    """Ogni metodo pubblico di `HAClient`, DERIVATO dal suo sorgente.

    Non si distingue lettura da scrittura, di proposito: distinguerle vorrebbe
    dire un vocabolario (i verbi HTTP, i suffissi dei comandi websocket), cioe'
    **un altro elenco a mano** un piano piu' sotto. L'attuatore oggi non nomina
    nessuno di questi nomi, quindi il cancello puo' permettersi la domanda piu'
    larga -- e la domanda piu' larga e' l'unica che chiude per difetto.

    Il giorno in cui l'attuatore dovesse leggere davvero da Home Assistant (il
    gesto «indaga» della spec §2), questo cancello diventera' rosso e la
    decisione dovra' essere presa e scritta. **E' il comportamento voluto**: un
    potere nuovo non si prende per distrazione.
    """
    classi = {nodo.name for nodo in _albero(_CLIENT).body
              if isinstance(nodo, ast.ClassDef)}
    assert "HAClient" in classi, (
        "`HAClient` non e' piu' una classe di `ha_client.py`: il cancello sta "
        "derivando da un modulo che non conosce piu'")
    return _metodi_pubblici(_CLIENT)


def porte_dichiarate() -> tuple[pathlib.Path, ...]:
    """I due moduli-porta, DERIVATI da `CLAUDE.md` che li dichiara.

    *«Per ogni canale di scrittura verso Home Assistant esiste un unico modulo
    che lo attraversa. Oggi sono due.»* Il cancello legge quella frase invece di
    ricopiarne i percorsi: il giorno in cui una porta si sposta o ne nasce una
    terza, il documento e il cancello restano d'accordo.
    """
    testo = (RADICE / "CLAUDE.md").read_text(encoding="utf-8")
    inizio = testo.index("**Un canale, una porta.**")
    blocco = testo[inizio:inizio + 900]
    percorsi = [RADICE / "hiris" / "app" / grezzo
                for grezzo in re.findall(r"`([A-Za-z0-9_/]+\.py)`", blocco)]
    vivi = [p for p in percorsi if p.exists()]
    assert len(vivi) == len(percorsi) == 2, (
        f"`CLAUDE.md` dichiara le porte di scrittura, e da quel paragrafo ho "
        f"letto {len(percorsi)} percorsi di cui {len(vivi)} esistono davvero. "
        "Servono due porte, entrambe vive: o il documento ne nomina una che non "
        "esiste piu', o le porte sono cambiate e nessuno l'ha scritto")
    return tuple(vivi)


def _funzioni(moduli) -> dict[str, list[tuple[str, ast.AST, str]]]:
    """`{nome: [(modulo, definizione, sorgente del modulo)]}` per ogni funzione
    di primo livello dei `moduli`. Una lista per nome: due moduli possono
    definire lo stesso nome, e il grafo li segue tutti e due -- meglio
    sorvegliare una funzione di troppo che perderne una."""
    funzioni: dict[str, list[tuple[str, ast.AST, str]]] = {}
    for percorso in moduli:
        sorgente = percorso.read_text(encoding="utf-8")
        modulo = percorso.relative_to(_APP).as_posix()
        for nodo in ast.parse(sorgente).body:
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funzioni.setdefault(nodo.name, []).append((modulo, nodo, sorgente))
    return funzioni


def _chiamate_dirette(funzioni: dict, radice: str,
                      fermate=frozenset()) -> set[str]:
    """I nomi raggiungibili da `radice` seguendo le sole chiamate dirette.
    Nelle `fermate` non si scende: sono le funzioni ammesse per nome."""
    visti: set[str] = set()

    def scendi(nome: str) -> None:
        if nome in visti or nome in fermate or nome not in funzioni:
            return
        visti.add(nome)
        for _, definizione, _ in funzioni[nome]:
            for nodo in ast.walk(definizione):
                if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name):
                    scendi(nodo.func.id)

    scendi(radice)
    return visti


def superficie_attuatore(moduli=None) -> dict[str, str]:
    """Il sorgente che appartiene all'attuatore, DERIVATO — `{nome: sorgente}`.

    Due pezzi, e il secondo e' quello che il cancello vecchio non vedeva:

    1. i moduli `mind/actuator*.py` e `mind/proposer*.py` (l'attore si chiama
       proponente dal 06/10/2026, D11), presi **dalla cartella** e non
       elencati;
    2. il **giro** (`proposer_round`, che la spec §6 dichiara parte
       dell'attore; fino al 06/10/2026 `actuator_round`, in `server.py`) e
       cio' che chiama, dovunque viva. Si ricava dal grafo delle chiamate, **meno** cio' che
       raggiungono anche gli altri giri (le funzioni pubbliche `*_round`): una
       funzione condivisa non e' dell'attuatore, e sorvegliarla qui farebbe
       diventare rosso questo cancello per colpa di qualcun altro.

    Il grafo si costruisce su **tutto `hiris/app`**, non sul solo `server.py`
    (Tappa 1 dello sprint «Una fonte sola di verita'», 03/10/2026): un gesto
    dell'attuatore spostato in un altro modulo usciva dal grafo -- `scendi` si
    fermava al primo nome che `server.py` non definiva -- e il cancello restava
    verde guardando meno. `moduli` restringe il grafo: serve solo alla prova
    che la derivazione larga contenga quella stretta.
    """
    superficie = {p.name: p.read_text(encoding="utf-8")
                  for pattern in ("actuator*.py", "proposer*.py")
                  for p in sorted((_APP / "mind").glob(pattern))}
    assert superficie, "non trovo nessun modulo `mind/actuator*.py` o `mind/proposer*.py`"

    funzioni = _funzioni(moduli if moduli is not None else sorted(_APP.rglob("*.py")))
    altri_giri = {n for n in funzioni
                  if n.endswith("_round") and not n.startswith("_")
                  and n != RADICE_GIRO}
    condivise: set[str] = set()
    for giro in altri_giri:
        condivise |= _chiamate_dirette(funzioni, giro)

    sole_sue = _chiamate_dirette(funzioni, RADICE_GIRO, AMMESSI) - condivise
    assert RADICE_GIRO in sole_sue
    for nome in sorted(sole_sue):
        for modulo, definizione, sorgente in funzioni[nome]:
            superficie[f"{modulo}::{nome}"] = ast.get_source_segment(sorgente, definizione) or ""
    return superficie


def _attributi(sorgente: str) -> set[str]:
    """I nomi usati come ATTRIBUTO (`qualcosa.nome`).

    Attributi e non nomi nudi: un metodo di `HAClient` si chiama sempre su un
    oggetto, mentre una variabile locale chiamata `start` o `stop` non e' una
    porta. Cercare le parole nude farebbe gridare il cancello al primo `start_ts`
    -- e un cancello che grida a vuoto viene disattivato, che e' peggio di non
    averlo.
    """
    return {n.attr for n in ast.walk(ast.parse(sorgente)) if isinstance(n, ast.Attribute)}


# --- I-0: il cancello chiede il suo elenco invece di ricopiarlo --------------

def test_una_porta_NUOVA_entra_nel_cancello_da_sola():
    """**I-0.** L'elenco delle porte si CHIEDE a `ha_client`, non si ricopia.

    Il cancello precedente ne elencava tre a mano mentre `HAClient` ne espone
    quarantatre su due canali: quaranta non erano sorvegliate, e una porta nuova
    non ci sarebbe mai entrata.

    Mutazione ESEGUITA: aggiungere un metodo pubblico a `HAClient` -- compare
    nell'insieme senza che nessuno tocchi questo file.
    """
    porte = porte_home_assistant()

    assert len(porte) > 30, (
        f"ne ho derivate solo {len(porte)}: la derivazione si e' rotta, e un "
        "cancello che deriva male e' peggio di uno che ricopia, perche' sembra vivo")
    for websocket in ("create_helper", "delete_helper", "create_label", "add_label_to"):
        assert websocket in porte, (
            f"`{websocket}` scrive in Home Assistant via websocket e non e' "
            "nell'insieme derivato: il cancello sorveglia un canale su due")


def test_la_superficie_comprende_il_GIRO_non_solo_i_moduli():
    """**I-0.** Il cancello vecchio leggeva due file in `mind/` mentre il giro
    viveva in `server.py`: una scrittura aggiunta li' era **invisibile**. Dal
    06/10/2026 il giro vive in `mind/proposer_round.py`, e il grafo parte da
    lui: i gesti del giro sono sorvegliati per nome, non per cartella.

    Mutazione ESEGUITA (06/10/2026): `RADICE_GIRO` su un nome che non esiste
    -- rossa.
    """
    superficie = superficie_attuatore()

    assert "proposer_turn.py" in superficie and "proposer_round.py" in superficie
    for gesto in ("_settle", "_chain", "_collect", "_alert_high"):
        assert f"mind/proposer_round.py::{gesto}" in superficie, (
            f"`{gesto}` e' un gesto del proponente e non e' sorvegliato")


def test_il_grafo_su_tutto_il_prodotto_contiene_quello_del_solo_giro():
    """**La derivazione larga non si e' svuotata.** Il grafo delle chiamate
    costruito su tutto `hiris/app` deve vedere almeno cio' che vedeva quello
    costruito sul solo `server.py`: se la derivazione larga si rompesse (un
    altro `actuator_round`, una funzione condivisa di troppo), il cancello
    guarderebbe meno e resterebbe verde.

    Mutazione ESEGUITA (03/10/2026): un gesto dell'attuatore scritto in
    `action/rhythm.py` -- `_prova_scrive(app)`, che chiama
    `app["ha_client"].call_service(...)` -- e chiamato da `actuator_round`: il
    cancello di `test_l_attuatore_non_tocca_MAI_home_assistant` col grafo del
    solo `server.py` restava VERDE, col grafo di tutto il prodotto e' rosso.
    """
    stretta = superficie_attuatore([_GIRO])
    larga = superficie_attuatore()

    assert set(stretta) <= set(larga), sorted(set(stretta) - set(larga))
    assert any(nome.startswith("mind/proposer_round.py::") for nome in larga)


def test_le_due_porte_si_leggono_da_CLAUDE_md():
    """**I-0.** Anche i due moduli-porta si derivano: li dichiara `CLAUDE.md`.

    Se un percorso dichiarato non esiste piu', questa prova lo dice -- ed e' il
    caso in cui la ragione scritta accanto al codice ha smesso di essere vera,
    che e' la classe di difetto piu' frequente di questo audit.
    """
    nomi = {p.name for p in porte_dichiarate()}

    assert nomi == {"actuator.py", "workshop.py"}, (
        f"le porte dichiarate in `CLAUDE.md` sono {sorted(nomi)}: o sono "
        "cambiate, o il documento non le nomina piu' per percorso")


def test_l_attuatore_non_tocca_MAI_home_assistant():
    """**Il confine del 25/08/2026**: «l'attuatore non guadagna un canale di
    scrittura suo». Finche' nessuno lo custodisce e' una promessa, e le promesse
    in un documento non fermano una riga di codice.

    Si legge il sorgente e basta: e' un cancello di FORMA, e la forma e' cio'
    che si rompe quando qualcuno aggiunge una chiamata «solo per provare».

    Tre insiemi, **tutti derivati**: le porte di `ha_client`, i metodi delle due
    porte-modulo dichiarate in `CLAUDE.md`, e la superficie dell'attuatore. Meno
    `AMMESSI`, che e' l'unica lista scritta a mano e che **enuncia** il cancello
    invece di ricopiare un fatto.

    Mutazione ESEGUITA: `await ha_client.call_service(...)` in `actuator.py` --
    rossa. E `self._workshop.apply(...)` in `_file_proposals` -- rossa. Dal
    06/10/2026 (Task 4.2, Passo 5): `app["action_actuator"].execute(...)` in
    `proposer_round._settle` -- rossa. Dal Task 4.3 (06/10/2026): `AMMESSI`
    senza `notify_admins` -- rossa su `soffitto._refresh_users` (`users`);
    `app["action_actuator"].execute(...)` in `_alert_high`, accanto
    all'avviso ammesso -- rossa.
    """
    vietati = (porte_home_assistant()
               | {m for porta in porte_dichiarate() for m in _metodi_pubblici(porta)}
               ) - AMMESSI

    for nome, sorgente in superficie_attuatore().items():
        if not sorgente.strip():
            continue
        toccate = _attributi(sorgente) & vietati
        assert not toccate, (
            f"{nome} nomina {sorted(toccate)}: l'attuatore toccherebbe Home "
            "Assistant senza passare dal cancello di consenso. Se e' voluto, la "
            "decisione va scritta in `AMMESSI` con la sua ragione")


class _FintoModello:
    def __init__(self):
        self.chiamate = 0

    async def chat(self, **kwargs):
        self.chiamate += 1
        await asyncio.sleep(0)
        return json.dumps({"esiti": [{"osservazione": 0, "esito": "niente",
                                      "perche": "guardato"}]})


@pytest.mark.asyncio
async def test_due_giri_insieme_non_fanno_DUE_turni(tmp_path):
    """Lo schedulatore ha un `misfire_grace_time` di mezz'ora: due giri
    possono partire insieme dopo una sosta dell'add-on. Senza guardia si
    pagherebbero due turni per la stessa analisi -- e il secondo scriverebbe
    sopra il primo, con gli stessi dati.

    Mutazione: togliere la guardia -- rossa (due chiamate al modello).
    """
    store = ObservationsStore(str(tmp_path / "oss.db"))
    modello = _FintoModello()
    app = {"observations": store, "llm_router": modello, "bridge_active": False}
    try:
        store.replace_analysis(OGGI, {
            "osservazioni": [{"soggetto": "dev1", "misura": "prelievo",
                              "chiave": None, "innesco": 1, "base": 19,
                              "cosa": "x", "cosa_cambierebbe": "y"}],
            "fondamento": {"giorni": 3, "impronta": "aaa"}})

        await asyncio.gather(proposer_round(app), proposer_round(app))

        assert modello.chiamate == 1
    finally:
        store.close()


class _OfficinaCheConta:
    def __init__(self):
        self.chiamate = 0

    async def propose(self, intent, *, actor, exchange, now):
        self.chiamate += 1
        return {"proposta_id": "c1"}


@pytest.mark.asyncio
async def test_le_due_forme_non_si_MESCOLANO_negli_archivi(tmp_path):
    """**Il terzo cancello** (spec §7): si leggono insieme, si archiviano
    separate. Una frase in prosa dentro la tabella dei diff sarebbe cinque
    colonne di finti valori; un'automazione dentro l'archivio delle proposte a
    mano sarebbe un «crea» senza niente da creare.

    Qui si prova la meta' che le altre prove non toccano: **una proposta da
    fare a mano non chiama l'officina** -- dal 06/10/2026 l'officina la chiama
    solo lo strumento `propose`, dentro il turno.

    Mutazione ESEGUITA sul giro dell'attuatore: mandare all'officina anche le
    non costruibili -- rossa."""
    store = ObservationsStore(str(tmp_path / "oss.db"))
    officina = _OfficinaCheConta()

    class _Modello:
        chiamate = 0

        async def chat(self, **kwargs):
            return json.dumps({"esiti": [
                {"osservazione": 0, "esito": "a_mano",
                 "testo": "Sposta la lavatrice nel pomeriggio",
                 "perche": "costa meno"}]})

    app = {"observations": store, "llm_router": _Modello(), "bridge_active": False,
           "workshop": officina}
    try:
        store.replace_analysis(OGGI, {
            "osservazioni": [{"soggetto": "dev1", "misura": "prelievo",
                              "chiave": None, "innesco": 1, "base": 19,
                              "cosa": "x", "cosa_cambierebbe": "y"}],
            "fondamento": {"giorni": 3, "impronta": "aaa"}})

        await proposer_round(app)

        assert officina.chiamate == 0, (
            "una proposta da fare a mano e' finita all'officina")
        assert len(store.proposals()) == 1
    finally:
        store.close()
