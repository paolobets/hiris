"""Un file JSON in `/data` si scrive in un modo solo (Tappa 7, Task 10; F-11).

Erano tre scritture atomiche -- le impostazioni della chat, l'archivio dei
modelli, la cornice dell'anagrafe -- e solo la prima faceva `fsync`: le altre
due potevano pubblicare, su una perdita di alimentazione, un nome che punta a
un file vuoto. Adesso c'e' `storage.write_json_atomic`, e le prove la
chiedono al sorgente invece di elencare i tre scrittori.
"""
import ast
import os
from pathlib import Path

import pytest

from hiris.app import storage
from hiris.app.chat_settings import ChatSettings
from hiris.app.home_space.reader import HomeSpace
from hiris.app.models_store import save_models_config

_APP = Path(__file__).resolve().parent.parent / "hiris" / "app"


def _json_dump_calls() -> dict[str, int]:
    """File -> quante chiamate a `json.dump` (su un file, non `dumps`)."""
    found: dict[str, int] = {}
    for path in sorted(_APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "dump"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "json"):
                name = str(path.relative_to(_APP))
                found[name] = found.get(name, 0) + 1
    return found


def test_un_file_json_si_scrive_solo_da_storage():
    """Ogni `json.dump` del prodotto sta in `storage.py`: uno scrittore nuovo
    che apre il suo file e ci scrive dentro e' una quarta scrittura, senza
    `fsync`.

    Mutazione ESEGUITA (07/10/2026): `HomeSpace._write_reference_frame`
    rimesso a `open(...)` + `json.dump` + `os.replace` -- rossa
    (`{'home_space/reader.py': 1, 'storage.py': 1}`). Ripristinata, `git diff`
    di `reader.py` senza la mutazione."""
    calls = _json_dump_calls()
    assert calls == {"storage.py": 1}, calls


def test_la_derivazione_vede_ancora_le_chiamate():
    """Un insieme vuoto sarebbe un cancello che non guarda piu' niente: la
    derivazione deve trovare almeno la chiamata di `storage`."""
    assert _json_dump_calls().get("storage.py") == 1


@pytest.mark.parametrize("scrivi", [
    lambda d: ChatSettings(name="Prova").save(str(d)),
    lambda d: save_models_config(str(d), {"chain_order": ["claude"]}),
    lambda d: HomeSpace(str(d)).hold({}, [], reference_frame={"fuso": "Europe/Rome"}),
], ids=["impostazioni_chat", "archivio_modelli", "cornice_anagrafe"])
def test_i_tre_scrittori_arrivano_al_disco_con_fsync(tmp_path, monkeypatch, scrivi):
    """Il contenuto si forza sul disco PRIMA del rename, per tutti e tre.

    Mutazione ESEGUITA (07/10/2026): tolto `os.fsync(f.fileno())` da
    `write_json_atomic` -- rosse tutte e tre (`assert 0 == 1`, nessun `fsync`).
    Ripristinata, `git diff` di `storage.py` senza la mutazione."""
    forced = []
    real_fsync = os.fsync
    monkeypatch.setattr(storage.os, "fsync",
                        lambda fd: (forced.append(fd), real_fsync(fd))[1])
    scrivi(tmp_path)
    assert len(forced) == 1, forced
    assert not list(tmp_path.glob("*.tmp"))


def test_un_errore_a_meta_non_lascia_il_temporaneo_ne_il_file(tmp_path, monkeypatch):
    import json as _json

    def esplodi(*args, **kwargs):
        raise OSError("disco pieno")

    monkeypatch.setattr(_json, "dump", esplodi)
    destinazione = tmp_path / "x.json"
    with pytest.raises(OSError):
        storage.write_json_atomic(str(destinazione), {"a": 1})
    assert not destinazione.exists()
    assert not (tmp_path / "x.json.tmp").exists()
