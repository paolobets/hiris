"""La porta degli script verso la casa legge e basta, e non scrive nel repo.

`scripts/casa.py` e' l'unico punto da cui gli attrezzi dello sprint (sonda,
fotografia, batterie) toccano la casa vera. La regola del proprietario e'
«solo letture»: qui e' una prova, non una raccomandazione.

Mutazione ESEGUITA: aggiunto `call_service` a `READ_METHODS` -- rossa
(`metodi che scrivono ammessi alla porta di lettura: ['call_service']`).
Mutazione ESEGUITA: tolto il rifiuto in `ha_read` -- rossa (la chiamata
prosegue fino a cercare il file del token, e la prova non riceve il rifiuto).
Mutazione ESEGUITA: in `capture` tolto il controllo sui registri non letti --
rossa (`DID NOT RAISE` nella prova dell'ingresso monco).
Mutazione ESEGUITA: in `hiris_get` aggiunto `data=b"x"` alla `Request` --
rossa (`la porta di lettura costruisce una richiesta con un corpo`).
Mutazione ESEGUITA: in `outside_repo` tolto il rifiuto -- rossa (`DID NOT
RAISE` nella prova del bersaglio dentro il repo).
"""
import ast
import asyncio
import json
import sys
from pathlib import Path

import pytest

from tests._casa_sintetica import synthetic_inputs
from tests.test_mind_actuator_guards import porte_home_assistant

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import casa

DOOR = ROOT / "scripts" / "casa.py"
#: I verbi con cui un metodo del client SCRIVE. Non e' l'elenco dei metodi
#: (quello si chiede al sorgente): e' il vocabolario dei verbi, e una lista
#: dei verbi e' il fatto stesso. **E' una lista di esclusione, e lo si sa**:
#: un verbo nuovo (`fire_`, `reload_`) non la attraverserebbe. Non e' lei a
#: chiudere la porta: la chiude `READ_METHODS`, che e' di ammissione. Questa
#: serve solo a impedire che in quell'ammissione entri, per distrazione, un
#: metodo che gia' oggi si sa che scrive.
WRITING_VERBS = ("add_", "call_", "create_", "delete_", "remove_", "save_",
                 "set_", "update_")


def test_ogni_metodo_ammesso_esiste_nel_client():
    public = porte_home_assistant()
    assert len(public) >= 30, sorted(public)
    missing = sorted(set(casa.READ_METHODS) - public)
    assert not missing, f"metodi ammessi che il client non ha piu': {missing}"


def test_nessun_metodo_ammesso_scrive():
    writing = sorted(name for name in casa.READ_METHODS if name.startswith(WRITING_VERBS))
    assert not writing, f"metodi che scrivono ammessi alla porta di lettura: {writing}"


def test_un_metodo_fuori_elenco_e_rifiutato_prima_della_rete():
    with pytest.raises(PermissionError, match="call_service"):
        asyncio.run(casa.ha_read("call_service", "light", "turn_on",
                                 url="http://127.0.0.1:9", token_file="/non/esiste"))


def test_la_porta_non_costruisce_richieste_che_scrivono():
    """Si guarda l'ALBERO, non le parole: una `Request(url, data=...)` e' una
    POST anche senza la stringa "POST" da nessuna parte."""
    tree = ast.parse(DOOR.read_text(encoding="utf-8"))
    requests = [node for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "Request"]
    assert requests, "nessuna `Request` trovata: la prova non guarda piu' niente"
    for call in requests:
        keywords = {keyword.arg for keyword in call.keywords}
        assert not keywords & {"data", "method"}, (
            "la porta di lettura costruisce una richiesta con un corpo o un verbo "
            f"(riga {call.lineno})")
        assert len(call.args) == 1, f"argomenti posizionali in piu' (riga {call.lineno})"


def test_i_dati_della_casa_non_si_scrivono_dentro_il_repo(tmp_path):
    with pytest.raises(SystemExit, match="pubblico"):
        casa.outside_repo(ROOT / "docs" / "ingressi")
    with pytest.raises(SystemExit, match="pubblico"):
        asyncio.run(casa.capture(ROOT / "ingressi", house=_House(), hiris=_hiris))
    assert not (ROOT / "ingressi").exists()
    assert casa.outside_repo(tmp_path / "fuori") == (tmp_path / "fuori").resolve()


class _House:
    """La casa sintetica dietro i metodi che la cattura chiede."""

    def __init__(self, *, unread=(), states=None, behavior=None) -> None:
        self._inputs = synthetic_inputs()
        self._unread = list(unread)
        self._states = self._inputs["states"] if states is None else states
        self._behavior = self._inputs["behavior"] if behavior is None else behavior

    async def read_registries(self):
        return self._inputs["registries"], self._unread

    async def get_states(self, entity_ids):
        return self._states

    async def statistic_ids(self):
        return set(self._inputs["statistic_ids"])

    async def behavior_configs(self, entity_ids):
        return self._behavior

    async def get_config(self):
        return self._inputs["ha_config"]

    async def get_services(self):
        return self._inputs["services"]

    async def get_translations(self, language, category="entity_component"):
        return self._inputs["translations"]["report"]

    async def problems(self):
        return self._inputs["problems"]

    async def system_log(self):
        return self._inputs["system_log"]

    async def read_dashboards(self):
        dashboards = self._inputs["dashboards"]
        return dashboards["entries"], dashboards["unavailable"]


def _hiris(path):
    return json.dumps({"version": "3.72.2", "piani": []}).encode()


def _capture(tmp_path, **house):
    return asyncio.run(casa.capture(tmp_path / "ingressi", house=_House(**house),
                                    hiris=_hiris))


def test_un_registro_non_letto_ferma_la_cattura(tmp_path):
    with pytest.raises(SystemExit, match="piani"):
        _capture(tmp_path, unread=["piani"])
    assert not (tmp_path / "ingressi").exists(), "un ingresso monco e' stato salvato"


def test_una_casa_senza_stati_ferma_la_cattura(tmp_path):
    with pytest.raises(SystemExit, match="stati"):
        _capture(tmp_path, states=[])
    assert not (tmp_path / "ingressi").exists()


def test_un_corpo_di_automazione_non_letto_ferma_la_cattura(tmp_path):
    partial = {"configurazioni": {}, "non_letti": {"automation.automazione_uno": "rifiutato"}}
    with pytest.raises(SystemExit, match="non letti"):
        _capture(tmp_path, behavior=partial)
    assert not (tmp_path / "ingressi").exists()


def test_la_cattura_scrive_gli_ingressi_e_il_manifesto_e_si_rilegge(tmp_path):
    manifest = _capture(tmp_path)
    target = tmp_path / "ingressi"
    written = {path.stem for path in target.iterdir()}
    assert written == {*casa.INPUTS, casa.MANIFEST, casa.HIRIS_TREE}
    assert manifest["conti"] == {"entita": 12, "dispositivi": 4, "aree": 3, "stati": 11}
    assert manifest["hiris"] == "3.72.2"
    assert manifest["home_assistant"] == "2026.9.4"
    assert casa.manifest_of(target) == manifest
    # Cio' che si rilegge e' cio' che la casa sintetica ha dato: la cattura non
    # perde e non inventa niente lungo la strada.
    assert casa.read_inputs(target) == synthetic_inputs()


def test_una_cartella_di_una_cattura_piu_vecchia_si_rifiuta(tmp_path):
    _capture(tmp_path)
    (tmp_path / "ingressi" / "services.json").unlink()
    with pytest.raises(SystemExit, match="services"):
        casa.read_inputs(tmp_path / "ingressi")
