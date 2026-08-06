import pytest

from hiris.app.casa.archivio import ArchivioCasa
from hiris.app.casa.comportamento import componi, rileggi

_AUTOMAZIONI = [
    {"id": "1700", "alias": "Sveglia", "trigger": [{"platform": "time", "at": "07:00"}]},
    {"id": "1701", "alias": "Mai caricata", "trigger": []},
]
_SCRIPT = {
    "saluta": {"alias": "Saluta", "sequence": [{"service": "tts.speak"}]},
}
_STATI = [
    {"entity_id": "automation.sveglia", "state": "on",
     "attributes": {"id": "1700", "friendly_name": "Sveglia"}},
    {"entity_id": "automation.a_mano", "state": "on",
     "attributes": {"id": "9999", "friendly_name": "Scritta a mano"}},
    {"entity_id": "script.saluta", "state": "off",
     "attributes": {"friendly_name": "Saluta"}},
    {"entity_id": "light.cucina", "state": "on", "attributes": {}},
]


def _per_id(voci):
    return {v["id"]: v for v in voci}


def test_un_automazione_nel_file_e_nello_stato_ha_il_corpo():
    voci, _ = componi(_AUTOMAZIONI, _SCRIPT, _STATI)
    voci = _per_id(voci)
    assert voci["automation.sveglia"]["origine"] == "file"
    assert voci["automation.sveglia"]["corpo"]["trigger"][0]["at"] == "07:00"


def test_un_automazione_scritta_a_mano_si_conosce_di_nome_e_si_dichiara():
    """Non sta in automations.yaml: puo' vivere nei pacchetti o in cartelle
    incluse. HIRIS deve sapere che esiste e sapere di non conoscerne il corpo."""
    voci, _ = componi(_AUTOMAZIONI, _SCRIPT, _STATI)
    voci = _per_id(voci)
    assert voci["automation.a_mano"]["origine"] == "solo_stato"
    assert voci["automation.a_mano"]["corpo"] is None
    assert voci["automation.a_mano"]["nome"] == "Scritta a mano"


def test_una_voce_solo_nel_file_e_scritta_ma_non_caricata():
    voci, _ = componi(_AUTOMAZIONI, _SCRIPT, _STATI)
    sola = [v for v in voci if v["origine"] == "solo_file"]
    assert [v["nome"] for v in sola] == ["Mai caricata"]


def test_lo_script_si_aggancia_per_object_id():
    """Per gli script la chiave del file E' l'object_id dell'entita':
    script.saluta <-> chiave `saluta`, nessuna ricerca."""
    voci, _ = componi(_AUTOMAZIONI, _SCRIPT, _STATI)
    voci = _per_id(voci)
    assert voci["script.saluta"]["corpo"]["sequence"][0]["service"] == "tts.speak"


def test_le_entita_che_non_sono_comportamento_restano_fuori():
    voci, _ = componi(_AUTOMAZIONI, _SCRIPT, _STATI)
    voci = _per_id(voci)
    assert "light.cucina" not in voci


def test_un_file_assente_non_e_un_file_vuoto():
    """`None` significa «non ho letto il file»: tutte le automazioni vive
    diventano solo_stato, non spariscono."""
    voci, _ = componi(None, None, _STATI)
    voci = _per_id(voci)
    assert voci["automation.sveglia"]["origine"] == "solo_stato"
    assert voci["automation.sveglia"]["corpo"] is None
    assert len(voci) == 3


def test_due_automazioni_con_lo_stesso_id_non_diventano_un_corpo_certo():
    """Il caso peggiore trovato dalla review: l'ultima vinceva in silenzio e
    ENTRAMBE le entita' vive ricevevano il corpo sbagliato marcato «file»."""
    automazioni = [
        {"id": "1700", "alias": "Sveglia", "trigger": [{"at": "07:00"}]},
        {"id": "1700", "alias": "Buonanotte", "trigger": [{"at": "22:00"}]},
    ]
    stati = [{"entity_id": "automation.sveglia", "state": "on",
              "attributes": {"id": "1700", "friendly_name": "Sveglia"}}]
    voci, problemi = componi(automazioni, {}, stati)
    voce = [v for v in voci if v["id"] == "automation.sveglia"][0]
    assert voce["origine"] == "ambiguo"
    assert voce["corpo"] is None
    assert any("1700" in p for p in problemi)


def test_uno_script_presente_e_nullo_non_genera_un_doppione():
    """`scripts.yaml` a meta' modifica: la chiave c'e' e vale None. Prima
    l'entita' finiva DUE volte nell'elenco, e l'INSERT falliva su UNIQUE,
    facendo cadere l'intero aggiornamento del comportamento."""
    stati = [{"entity_id": "script.saluta", "state": "off",
              "attributes": {"friendly_name": "Saluta"}}]
    voci, problemi = componi([], {"saluta": None}, stati)
    assert [v["id"] for v in voci] == ["script.saluta"]
    assert voci[0]["corpo"] is None
    assert problemi


def test_un_automazione_senza_id_non_sparisce():
    voci, problemi = componi([{"alias": "Scritta a mano", "trigger": []}], {}, [])
    assert [v["nome"] for v in voci] == ["Scritta a mano"]
    assert voci[0]["origine"] == "solo_file"
    assert problemi


def test_un_id_zero_non_e_un_id_assente():
    """0 e' falsy in Python: l'automazione perdeva il corpo E generava una
    voce fantasma. La stessa automazione, due volte, con etichette opposte."""
    automazioni = [{"id": 0, "alias": "Prima", "trigger": []}]
    stati = [{"entity_id": "automation.prima", "state": "on",
              "attributes": {"id": 0, "friendly_name": "Prima"}}]
    voci, _ = componi(automazioni, {}, stati)
    assert [v["id"] for v in voci] == ["automation.prima"]
    assert voci[0]["origine"] == "file"


def test_uno_scripts_yaml_che_e_una_lista_si_dichiara():
    voci, problemi = componi([], [{"saluta": {}}], [])
    assert voci == []
    assert any("scripts.yaml" in p for p in problemi)


class _ClienteFinto:
    """Home Assistant finto: nessuno stato vivo, non serve altro per questo test.

    La firma di `get_states` combacia con quella vera di `HAClient` — che
    richiede `entity_ids`, dove `[]` significa «tutte». Un finto con una firma
    propria non e' una semplificazione: e' un test che codifica il bug. Questo
    finto lo aveva, e `rileggi()` chiamava `get_states()` senza argomenti:
    `TypeError` alla prima chiamata vera, invisibile alla suite.
    """

    def __init__(self):
        self.chiamato_con = None

    async def get_states(self, entity_ids):
        self.chiamato_con = entity_ids
        return []


def test_il_finto_combacia_con_la_firma_vera():
    """La rete di sicurezza contro la deriva: se HAClient.get_states cambia
    firma, questo test cade invece di lasciare che il finto menta."""
    import inspect

    from hiris.app.proxy.ha_client import HAClient

    vera = inspect.signature(HAClient.get_states)
    finta = inspect.signature(_ClienteFinto.get_states)
    assert list(vera.parameters) == list(finta.parameters)


@pytest.mark.asyncio
async def test_un_file_rotto_si_distingue_da_un_file_assente(tmp_path):
    """Creare il file e ripararlo sono due interventi diversi: chi legge
    l'esito deve poterli distinguere."""
    (tmp_path / "automations.yaml").write_text(
        "- id: '1'\n   alias: male indentato\n  altro: x\n", encoding="utf-8"
    )
    # scripts.yaml resta assente

    archivio = ArchivioCasa(str(tmp_path / "casa.db"))
    try:
        cliente = _ClienteFinto()
        esito = await rileggi(cliente, archivio, tmp_path)
    finally:
        archivio.chiudi()

    assert "illeggibile" in esito["file_non_letti"]["automations.yaml"]
    assert esito["file_non_letti"]["scripts.yaml"] == "assente"
    assert cliente.chiamato_con == []   # «tutte», la convenzione di HAClient
