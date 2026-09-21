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
`server.py`; alle due porte-modulo lo chiede `CLAUDE.md`, che le dichiara. Una
porta nuova e una funzione nuova entrano nel cancello **il giorno in cui
nascono**, non il giorno in cui qualcuno se ne ricorda.

**La sola lista scritta a mano che resta e' quella delle ECCEZIONI** (`AMMESSI`),
ed e' di un'altra specie: non ricopia un fatto che vive altrove, **enuncia il
cancello**. Chiude per difetto -- un metodo nuovo dell'officina e' vietato finche'
qualcuno non lo ammette per iscritto, con la ragione accanto.
"""
import ast
import asyncio
import datetime
import json
import pathlib
import re

import pytest

from hiris.app import server
from hiris.app.home_space.historian import home_space_zone
from hiris.app.mind.store import ObservationsStore

OGGI = datetime.datetime.now(
    home_space_zone(server._timezone_from_home_space_store(None))).date().isoformat()

RADICE = pathlib.Path(__file__).resolve().parents[1]
_CLIENT = RADICE / "hiris" / "app" / "proxy" / "ha_client.py"
_SERVER = RADICE / "hiris" / "app" / "server.py"

#: Il gesto dell'attuatore che PUO' toccare una porta, e perche'.
#:
#: `propose` compone e valida contro questa casa e **non scrive niente**: la
#: scrittura e' un turno diverso, col si' del proprietario (spec §3). E' il gesto
#: «propone», ed e' l'unica ragione per cui l'attuatore nomina l'officina.
#:
#: Questa lista non ricopia niente: **dice cosa il cancello ammette**. Un metodo
#: nuovo dell'officina non entra qui da solo -- va ammesso a mano, con la ragione,
#: che e' esattamente il momento in cui qualcuno deve pensarci.
AMMESSI = frozenset({"propose"})


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


def _chiamate_dirette(funzioni: dict, radice: str) -> set[str]:
    """I nomi raggiungibili da `radice` seguendo le sole chiamate dirette."""
    visti: set[str] = set()

    def scendi(nome: str) -> None:
        if nome in visti or nome not in funzioni:
            return
        visti.add(nome)
        for nodo in ast.walk(funzioni[nome]):
            if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Name):
                scendi(nodo.func.id)

    scendi(radice)
    return visti


def superficie_attuatore() -> dict[str, str]:
    """Il sorgente che appartiene all'attuatore, DERIVATO — `{nome: sorgente}`.

    Due pezzi, e il secondo e' quello che il cancello vecchio non vedeva:

    1. i moduli `mind/actuator*.py`, presi **dalla cartella** e non elencati;
    2. il **giro** in `server.py`, che la spec §6 dichiara parte dell'attuatore
       (`actuator_round`) e dove `ha_client` e' a portata di mano dovunque. Si
       ricava dal grafo delle chiamate, **meno** cio' che raggiungono anche gli
       altri giri: una funzione condivisa non e' dell'attuatore, e sorvegliarla
       qui farebbe diventare rosso questo cancello per colpa di qualcun altro.
    """
    superficie = {p.name: p.read_text(encoding="utf-8")
                  for p in sorted((RADICE / "hiris" / "app" / "mind").glob("actuator*.py"))}
    assert superficie, "non trovo nessun modulo `mind/actuator*.py`"

    albero = _albero(_SERVER)
    funzioni = {n.name: n for n in albero.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    altri_giri = {n for n in funzioni if n.endswith("_round") and n != "actuator_round"}
    condivise: set[str] = set()
    for giro in altri_giri:
        condivise |= _chiamate_dirette(funzioni, giro)

    sole_sue = _chiamate_dirette(funzioni, "actuator_round") - condivise
    assert "actuator_round" in sole_sue
    sorgente = _SERVER.read_text(encoding="utf-8")
    for nome in sorted(sole_sue):
        superficie[f"server.py::{nome}"] = ast.get_source_segment(sorgente, funzioni[nome]) or ""
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


def test_la_superficie_comprende_il_GIRO_nel_server_non_solo_i_due_moduli():
    """**I-0.** Il cancello vecchio leggeva due file in `mind/`. Il giro vero
    dell'attuatore vive in `server.py` (spec §6), dove `ha_client` e' a portata
    di mano: una scrittura aggiunta li' era **invisibile**.

    Mutazione ESEGUITA: restringere la superficie ai soli `mind/actuator*.py` --
    rossa.
    """
    superficie = superficie_attuatore()

    assert "actuator.py" in superficie and "actuator_turn.py" in superficie
    for gesto in ("_repair_recipes", "_file_proposals", "_write_actuation"):
        assert f"server.py::{gesto}" in superficie, (
            f"`{gesto}` e' un gesto dell'attuatore e non e' sorvegliato")


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
    rossa. E `self._workshop.apply(...)` in `_file_proposals` -- rossa.
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
        return json.dumps({"esiti": [{"osservazione": 0, "gesto": "indagine",
                                      "trovato": "guardato"}]})


@pytest.mark.asyncio
async def test_due_giri_insieme_non_fanno_DUE_attuazioni(tmp_path):
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

        await asyncio.gather(server.actuator_round(app), server.actuator_round(app))

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
    fare a mano non chiama l'officina**.

    Mutazione ESEGUITA: mandare all'officina anche le non costruibili --
    rossa."""
    store = ObservationsStore(str(tmp_path / "oss.db"))
    officina = _OfficinaCheConta()

    class _Modello:
        chiamate = 0

        async def chat(self, **kwargs):
            return json.dumps({"esiti": [
                {"osservazione": 0, "gesto": "proposta", "costruibile": False,
                 "trovato": "Sposta la lavatrice nel pomeriggio"}]})

    app = {"observations": store, "llm_router": _Modello(), "bridge_active": False,
           "workshop": officina}
    try:
        store.replace_analysis(OGGI, {
            "osservazioni": [{"soggetto": "dev1", "misura": "prelievo",
                              "chiave": None, "innesco": 1, "base": 19,
                              "cosa": "x", "cosa_cambierebbe": "y"}],
            "fondamento": {"giorni": 3, "impronta": "aaa"}})

        await server.actuator_round(app)

        assert officina.chiamate == 0, (
            "una proposta da fare a mano e' finita all'officina")
        assert len(store.proposals()) == 1
    finally:
        store.close()
