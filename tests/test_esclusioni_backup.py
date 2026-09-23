"""La sessione della CLI non entra nei backup (reperto C-4, 23/09/2026).

**Perché.** `config.yaml` non dichiarava nessuna esclusione, quindi `/data`
entrava intero nell'archivio di Home Assistant — archivio che **non è cifrato**
se il proprietario non gli mette una password, e che la doc di HA consiglia di
copiare su un disco remoto. Dentro `/data/claude` vive la **sessione della CLI**
del Piano Max: non una traccia, una credenziale che **ripristinata altrove
funziona**.

**Cosa NON si esclude, e perché.** Gli archivi della casa — conversazioni,
ricordi, promesse, osservazioni. Un backup che non li riporta non è un backup
più sicuro: è un backup che non fa il suo lavoro, e il proprietario lo scopre
il giorno in cui gli serve. Quelli si proteggono mettendo una password
all'archivio, che è una scelta di Home Assistant e sta scritta nel README.

**Il prezzo, dichiarato**: dopo un ripristino la sessione della CLI va rifatta.

**La semantica del filtro è verificata sul sorgente vero**, non supposta
(`supervisor/apps/validate.py` per la chiave, `supervisor/apps/app.py` per
`_is_excluded_by_filter`, `securetar/__init__.py` per la visita):
l'esclusione si prova con `PurePath.match` sul percorso **intero**, e una
cartella esclusa porta via **tutto il suo sottoalbero** perche' la visita non ci
scende dentro.
"""
import pathlib
from pathlib import PurePath

import yaml

RADICE = pathlib.Path(__file__).resolve().parents[1]
CONFIG = RADICE / "hiris" / "config.yaml"

#: La radice di `/data` come la vede il Supervisor sull'host: non `/data`, che
#: e' il percorso DENTRO il contenitore. Il filtro lavora sul percorso intero,
#: quindi una prova che partisse da `/data` proverebbe un'altra cosa.
ORIGINE = PurePath("/mnt/data/supervisor/addons/data/local_hiris")


def _esclusioni() -> list[str]:
    testo = CONFIG.read_text(encoding="utf-8")
    return yaml.safe_load(testo).get("backup_exclude") or []


def _archiviati(albero: dict, esclusioni: list[str]) -> set[str]:
    """Cosa finisce nell'archivio, visitando come fa il Supervisor.

    Replica `_atomic_contents_add` di `securetar`: si scende in una cartella
    **solo** se la cartella stessa non e' esclusa. E' la meta' che conta e che
    un confronto di stringhe non vedrebbe — escludere `claude` porta via anche
    `claude/.credentials.json`, che nessuna delle esclusioni nomina.
    """
    dentro: set[str] = set()

    def escluso(relativo: str) -> bool:
        intero = ORIGINE / relativo
        return any(intero.match(e) for e in esclusioni)

    def visita(nodo: dict, prefisso: str) -> None:
        for nome, figli in nodo.items():
            relativo = f"{prefisso}/{nome}" if prefisso else nome
            if escluso(relativo):
                continue
            dentro.add(relativo)
            if isinstance(figli, dict):
                visita(figli, relativo)

    visita(albero, "")
    return dentro


ALBERO = {
    "claude": {".credentials.json": None,
               "projects": {"-data": {"sessione.jsonl": None}},
               "settings.json": None},
    "chat_history.db": None,
    "memoria.db": None,
    "sapere.db": None,
    "promesse.db": None,
    "osservazioni.db": None,
    "models_config.json": None,
    "options.json": None,
}


def test_la_sessione_della_CLI_non_entra_nell_archivio():
    """**Il reperto C-4.** Una credenziale che ripristinata altrove funziona.

    Mutazione ESEGUITA: togliere l'esclusione -- rossa."""
    dentro = _archiviati(ALBERO, _esclusioni())

    assert "claude" not in dentro
    assert not [p for p in dentro if p.startswith("claude/")], (
        "la cartella della CLI e' esclusa ma qualcosa di suo e' entrato lo "
        "stesso")


def test_anche_il_file_delle_credenziali_che_nessuna_riga_NOMINA():
    """La meta' che un confronto di stringhe non vedrebbe: `.credentials.json`
    non compare in nessuna esclusione, ed e' fuori perche' la visita non scende
    in una cartella esclusa.

    Mutazione ESEGUITA: visitare i figli anche di una cartella esclusa --
    rossa."""
    dentro = _archiviati(ALBERO, _esclusioni())

    assert "claude/.credentials.json" not in dentro
    assert "claude/projects/-data/sessione.jsonl" not in dentro


def test_gli_ARCHIVI_della_casa_restano_nel_backup():
    """La contropartita, e vale quanto il reperto: un backup che non riporta i
    ricordi non e' piu' sicuro, e' rotto. Se un domani qualcuno aggiungesse
    `*.db` all'elenco, questa prova lo ferma.

    Mutazione ESEGUITA: aggiungere `*.db` alle esclusioni -- rossa."""
    dentro = _archiviati(ALBERO, _esclusioni())

    for atteso in ("chat_history.db", "memoria.db", "sapere.db",
                   "promesse.db", "osservazioni.db", "models_config.json"):
        assert atteso in dentro, (
            f"«{atteso}» non entra piu' nel backup: il ripristino non "
            "riporterebbe la casa")


def test_la_chiave_e_quella_che_il_Supervisor_LEGGE():
    """`backup_exclude`, non un nome inventato. Verificata sullo schema vero
    (`supervisor/apps/validate.py`: `vol.Optional(ATTR_BACKUP_EXCLUDE): [str]`,
    `ATTR_BACKUP_EXCLUDE = "backup_exclude"` in `const.py`).

    Una chiave sbagliata qui non fallisce: **viene ignorata**, e l'esclusione
    non esiste senza che nessuno se ne accorga.

    Mutazione ESEGUITA: rinominare la chiave -- rossa."""
    dati = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))

    assert isinstance(dati.get("backup_exclude"), list)
    assert all(isinstance(v, str) for v in dati["backup_exclude"])


def test_il_prezzo_del_ripristino_e_DICHIARATO_nel_README():
    """Il costo esiste ed e' reale: dopo un ripristino il Piano Max va
    ricollegato. Una perdita che il proprietario scopre da solo e' un difetto;
    una scritta prima e' una scelta.

    Mutazione ESEGUITA: togliere il paragrafo dal README -- rossa."""
    testo = (RADICE / "README.md").read_text(encoding="utf-8").lower()

    assert "backup_exclude" in testo
    inizio = testo.index("backup_exclude")
    paragrafo = testo[max(0, inizio - 1200):inizio + 1200]
    assert "restore" in paragrafo
    assert "sign in again" in paragrafo or "log in again" in paragrafo
