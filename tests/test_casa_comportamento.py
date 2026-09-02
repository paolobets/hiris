import pytest

from hiris.app.casa.archivio import HomeSpaceStore
from hiris.app.casa.comportamento import compose, reread

_AUTOMATIONS = [
    {"id": "1700", "alias": "Sveglia", "trigger": [{"platform": "time", "at": "07:00"}]},
    {"id": "1701", "alias": "Mai caricata", "trigger": []},
]
_SCRIPT = {
    "saluta": {"alias": "Saluta", "sequence": [{"service": "tts.speak"}]},
}
_STATES = [
    {"entity_id": "automation.sveglia", "state": "on",
     "attributes": {"id": "1700", "friendly_name": "Sveglia"}},
    {"entity_id": "automation.a_mano", "state": "on",
     "attributes": {"id": "9999", "friendly_name": "Scritta a mano"}},
    {"entity_id": "script.saluta", "state": "off",
     "attributes": {"friendly_name": "Saluta"}},
    {"entity_id": "light.cucina", "state": "on", "attributes": {}},
]


def _by_id(entries):
    return {v["id"]: v for v in entries}


def test_an_automation_in_the_file_and_in_state_has_a_body():
    entries, _ = compose(_AUTOMATIONS, _SCRIPT, _STATES)
    entries = _by_id(entries)
    assert entries["automation.sveglia"]["origine"] == "file"
    assert entries["automation.sveglia"]["corpo"]["trigger"][0]["at"] == "07:00"


def test_a_handwritten_automation_is_known_by_name_and_declared():
    """Non sta in automations.yaml: puo' vivere nei pacchetti o in cartelle
    incluse. HIRIS deve sapere che esiste e sapere di non conoscerne il corpo."""
    entries, _ = compose(_AUTOMATIONS, _SCRIPT, _STATES)
    entries = _by_id(entries)
    assert entries["automation.a_mano"]["origine"] == "solo_stato"
    assert entries["automation.a_mano"]["corpo"] is None
    assert entries["automation.a_mano"]["nome"] == "Scritta a mano"


def test_an_entry_only_in_the_file_is_written_but_not_loaded():
    entries, _ = compose(_AUTOMATIONS, _SCRIPT, _STATES)
    file_only = [v for v in entries if v["origine"] == "solo_file"]
    assert [v["nome"] for v in file_only] == ["Mai caricata"]


def test_the_script_hooks_by_object_id():
    """Per gli script la chiave del file E' l'object_id dell'entita':
    script.saluta <-> chiave `saluta`, nessuna ricerca."""
    entries, _ = compose(_AUTOMATIONS, _SCRIPT, _STATES)
    entries = _by_id(entries)
    assert entries["script.saluta"]["corpo"]["sequence"][0]["service"] == "tts.speak"


def test_entities_that_are_not_behavior_stay_out():
    entries, _ = compose(_AUTOMATIONS, _SCRIPT, _STATES)
    entries = _by_id(entries)
    assert "light.cucina" not in entries


def test_a_missing_file_is_not_an_empty_file():
    """`None` significa «non ho letto il file»: tutte le automazioni vive
    diventano solo_stato, non spariscono."""
    entries, _ = compose(None, None, _STATES)
    entries = _by_id(entries)
    assert entries["automation.sveglia"]["origine"] == "solo_stato"
    assert entries["automation.sveglia"]["corpo"] is None
    assert len(entries) == 3


def test_two_automations_with_the_same_id_do_not_become_a_certain_body():
    """Il caso peggiore trovato dalla review: l'ultima vinceva in silenzio e
    ENTRAMBE le entita' vive ricevevano il corpo sbagliato marcato «file»."""
    automations = [
        {"id": "1700", "alias": "Sveglia", "trigger": [{"at": "07:00"}]},
        {"id": "1700", "alias": "Buonanotte", "trigger": [{"at": "22:00"}]},
    ]
    states = [{"entity_id": "automation.sveglia", "state": "on",
              "attributes": {"id": "1700", "friendly_name": "Sveglia"}}]
    entries, problems = compose(automations, {}, states)
    entry = next(v for v in entries if v["id"] == "automation.sveglia")
    assert entry["origine"] == "ambiguo"
    assert entry["corpo"] is None
    assert any("1700" in p for p in problems)


def test_a_present_and_null_script_does_not_generate_a_duplicate():
    """`scripts.yaml` a meta' modifica: la chiave c'e' e vale None. Prima
    l'entita' finiva DUE volte nell'elenco, e l'INSERT falliva su UNIQUE,
    facendo cadere l'intero aggiornamento del comportamento."""
    states = [{"entity_id": "script.saluta", "state": "off",
              "attributes": {"friendly_name": "Saluta"}}]
    entries, problems = compose([], {"saluta": None}, states)
    assert [v["id"] for v in entries] == ["script.saluta"]
    assert entries[0]["corpo"] is None
    assert problems


def test_an_automation_without_id_does_not_disappear():
    entries, problems = compose([{"alias": "Scritta a mano", "trigger": []}], {}, [])
    assert [v["nome"] for v in entries] == ["Scritta a mano"]
    assert entries[0]["origine"] == "solo_file"
    assert problems


def test_an_id_of_zero_is_not_a_missing_id():
    """0 e' falsy in Python: l'automazione perdeva il corpo E generava una
    voce fantasma. La stessa automazione, due volte, con etichette opposte."""
    automations = [{"id": 0, "alias": "Prima", "trigger": []}]
    states = [{"entity_id": "automation.prima", "state": "on",
              "attributes": {"id": 0, "friendly_name": "Prima"}}]
    entries, _ = compose(automations, {}, states)
    assert [v["id"] for v in entries] == ["automation.prima"]
    assert entries[0]["origine"] == "file"


def test_a_scripts_yaml_that_is_a_list_is_declared():
    entries, problems = compose([], [{"saluta": {}}], [])
    assert entries == []
    assert any("scripts.yaml" in p for p in problems)


class _ClienteFinto:
    """Home Assistant finto: nessuno stato vivo, non serve altro per questo test.

    La firma di `get_states` combacia con quella vera di `HAClient` — che
    richiede `entity_ids`, dove `[]` significa «tutte». Un finto con una firma
    propria non e' una semplificazione: e' un test che codifica il bug. Questo
    finto lo aveva, e `reread()` chiamava `get_states()` senza argomenti:
    `TypeError` alla prima chiamata vera, invisibile alla suite.
    """

    def __init__(self):
        self.chiamato_con = None

    async def get_states(self, entity_ids):
        self.chiamato_con = entity_ids
        return []


def test_the_fake_matches_the_real_signature():
    """La rete di sicurezza contro la deriva: se HAClient.get_states cambia
    firma, questo test cade invece di lasciare che il finto menta."""
    import inspect

    from hiris.app.proxy.ha_client import HAClient

    vera = inspect.signature(HAClient.get_states)
    finta = inspect.signature(_ClienteFinto.get_states)
    assert list(vera.parameters) == list(finta.parameters)


@pytest.mark.asyncio
async def test_a_broken_file_is_distinguished_from_a_missing_file(tmp_path):
    """Creare il file e ripararlo sono due interventi diversi: chi legge
    l'esito deve poterli distinguere."""
    (tmp_path / "automations.yaml").write_text(
        "- id: '1'\n   alias: male indentato\n  altro: x\n", encoding="utf-8"
    )
    # scripts.yaml resta assente

    archivio = HomeSpaceStore(str(tmp_path / "casa.db"))
    try:
        cliente = _ClienteFinto()
        esito = await reread(cliente, archivio, tmp_path)
    finally:
        archivio.close()

    assert "illeggibile" in esito["file_non_letti"]["automations.yaml"]
    assert esito["file_non_letti"]["scripts.yaml"] == "assente"
    assert cliente.chiamato_con == []   # «tutte», la convenzione di HAClient


def test_a_real_automation_declares_itself_real():
    """Complemento di `test_an_automation_in_the_file_and_in_state_has_a_body`:
    l'id combacia con un entity_id vero, ricevuto dallo stato."""
    entries, _ = compose(_AUTOMATIONS, _SCRIPT, _STATES)
    entries = _by_id(entries)
    assert entries["automation.sveglia"]["id_reale"] is True


def test_a_synthetic_id_declares_itself_not_real():
    """Critical minore (7): `automation.__non_caricata_1701` combacia con la
    forma di un entity_id vero (dominio.oggetto) — senza questo campo un
    consumatore non ha modo di saperlo se non deducendolo da una convenzione
    di prefisso."""
    entries, _ = compose(_AUTOMATIONS, _SCRIPT, _STATES)
    entries = _by_id(entries)
    assert entries["automation.__non_caricata_1701"]["id_reale"] is False


def test_a_non_dict_automation_is_discarded_without_exploding():
    """Critical (2): un trattino residuo in coda a automations.yaml
    (`- id: '1'\\n  alias: X\\n-\\n`) e' YAML VALIDO e produce `[{...}, None]`.
    Prima `compose` esplodeva con `AttributeError: 'NoneType' object has no
    attribute 'get'` sul secondo elemento; ora si scarta e si dichiara."""
    automations = [
        {"id": "1", "alias": "Sveglia", "trigger": []},
        None,
    ]
    entries, problems = compose(automations, {}, [])
    assert [v["nome"] for v in entries] == ["Sveglia"]
    assert any("voce #2" in p and "automations.yaml" in p for p in problems)


def test_a_scalar_automation_is_discarded_without_exploding():
    """Stessa classe di guasto, forma diversa: uno scalare al posto di una
    mappa (es. una riga YAML mal indentata che finisce come stringa)."""
    entries, problems = compose(["non e' una mappa"], {}, [])
    assert entries == []
    assert any("voce #1" in p for p in problems)


def test_a_scalar_value_script_is_discarded_without_exploding():
    """Speculare a `test_a_present_and_null_script_does_not_generate_a_duplicate`,
    ma per il valore-scalare invece del valore-nullo: `saluta: 'ciao'`.
    Prima crashava con `AttributeError` in `(corpo or {}).get("alias")`
    quando lo script restava senza entita' viva corrispondente (solo_file)."""
    entries, problems = compose([], {"saluta": "ciao"}, [])
    assert entries == []
    assert any("saluta" in p and "dizionario" in p for p in problems)


@pytest.mark.asyncio
async def test_a_leftover_dash_does_not_crash_the_reread(tmp_path):
    """Stesso guasto di `test_a_non_dict_automation_is_discarded_without_exploding`,
    ma attraverso `reread()` per intero — file veri su disco, corpo YAML
    reale, non solo `compose()` isolato."""
    (tmp_path / "automations.yaml").write_text(
        "- id: '1'\n  alias: Sveglia\n  trigger: []\n-\n", encoding="utf-8"
    )
    # scripts.yaml resta assente: non serve a questo test.

    class _ClienteConSveglia:
        async def get_states(self, entity_ids):
            return [{"entity_id": "automation.sveglia", "state": "on",
                      "attributes": {"id": "1", "friendly_name": "Sveglia"}}]

    archivio = HomeSpaceStore(str(tmp_path / "casa.db"))
    try:
        esito = await reread(_ClienteConSveglia(), archivio, tmp_path)
        assert any("voce #2" in p for p in esito["problemi"])
        entries = archivio.behavior()
        assert [v["nome"] for v in entries] == ["Sveglia"]
    finally:
        archivio.close()


@pytest.mark.asyncio
async def test_a_state_with_no_automations_or_scripts_does_not_replace(tmp_path):
    """Critical (1): Home Assistant ripartito in safe mode (configuration.yaml
    rotto) risponde 200 su /api/states MA senza alcuna automation.*/script.*:
    e' un successo HTTP, non un errore. Sostituire comunque trasformerebbe
    ogni automazione viva in "solo_file" (falso: sembra scritta-ma-non-
    caricata) e farebbe sparire quelle scritte a mano (solo_stato)."""
    (tmp_path / "automations.yaml").write_text(
        "- id: '1700'\n  alias: Sveglia\n  trigger: []\n", encoding="utf-8"
    )
    # scripts.yaml resta assente: non serve a questo test, e una seconda voce
    # "solo_file" per lo script renderebbe l'asserzione sul conteggio meno
    # diretta senza aggiungere niente alla dimostrazione.

    class _ClientWithStates:
        def __init__(self, states):
            self._stati = states

        async def get_states(self, entity_ids):
            return self._stati

    archivio = HomeSpaceStore(str(tmp_path / "casa.db"))
    try:
        # Prima lettura: HA e' su, l'automazione e' viva -> replica buona.
        cliente_su = _ClientWithStates([
            {"entity_id": "automation.sveglia", "state": "on",
             "attributes": {"id": "1700", "friendly_name": "Sveglia"}},
        ])
        await reread(cliente_su, archivio, tmp_path)
        assert len(archivio.behavior()) == 1
        assert archivio.behavior()[0]["origine"] == "file"

        # HA riparte in safe mode: /api/states risponde 200 ma vuoto.
        cliente_safe_mode = _ClientWithStates([])
        esito = await reread(cliente_safe_mode, archivio, tmp_path)

        # La replica precedente resta INTATTA: non diventa "solo_file", e
        # l'automazione a mano scritta a mano (se ci fosse stata) non sparisce.
        entries = archivio.behavior()
        assert len(entries) == 1
        assert entries[0]["nome"] == "Sveglia"
        assert entries[0]["origine"] == "file"
        assert esito["problemi"]  # il fatto e' dichiarato, non solo loggato
    finally:
        archivio.close()
