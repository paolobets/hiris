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


def test_un_automazione_reale_si_dichiara_reale():
    """Complemento di `test_un_automazione_nel_file_e_nello_stato_ha_il_corpo`:
    l'id combacia con un entity_id vero, ricevuto dallo stato."""
    voci, _ = componi(_AUTOMAZIONI, _SCRIPT, _STATI)
    voci = _per_id(voci)
    assert voci["automation.sveglia"]["id_reale"] is True


def test_un_id_sintetico_si_dichiara_non_reale():
    """Critical minore (7): `automation.__non_caricata_1701` combacia con la
    forma di un entity_id vero (dominio.oggetto) — senza questo campo un
    consumatore non ha modo di saperlo se non deducendolo da una convenzione
    di prefisso."""
    voci, _ = componi(_AUTOMAZIONI, _SCRIPT, _STATI)
    voci = _per_id(voci)
    assert voci["automation.__non_caricata_1701"]["id_reale"] is False


def test_un_automazione_non_a_dizionario_si_scarta_senza_esplodere():
    """Critical (2): un trattino residuo in coda a automations.yaml
    (`- id: '1'\\n  alias: X\\n-\\n`) e' YAML VALIDO e produce `[{...}, None]`.
    Prima `componi` esplodeva con `AttributeError: 'NoneType' object has no
    attribute 'get'` sul secondo elemento; ora si scarta e si dichiara."""
    automazioni = [
        {"id": "1", "alias": "Sveglia", "trigger": []},
        None,
    ]
    voci, problemi = componi(automazioni, {}, [])
    assert [v["nome"] for v in voci] == ["Sveglia"]
    assert any("voce #2" in p and "automations.yaml" in p for p in problemi)


def test_un_automazione_scalare_si_scarta_senza_esplodere():
    """Stessa classe di guasto, forma diversa: uno scalare al posto di una
    mappa (es. una riga YAML mal indentata che finisce come stringa)."""
    voci, problemi = componi(["non e' una mappa"], {}, [])
    assert voci == []
    assert any("voce #1" in p for p in problemi)


def test_uno_script_a_valore_scalare_si_scarta_senza_esplodere():
    """Speculare a `test_uno_script_presente_e_nullo_non_genera_un_doppione`,
    ma per il valore-scalare invece del valore-nullo: `saluta: 'ciao'`.
    Prima crashava con `AttributeError` in `(corpo or {}).get("alias")`
    quando lo script restava senza entita' viva corrispondente (solo_file)."""
    voci, problemi = componi([], {"saluta": "ciao"}, [])
    assert voci == []
    assert any("saluta" in p and "dizionario" in p for p in problemi)


@pytest.mark.asyncio
async def test_un_trattino_residuo_non_pianta_la_rilettura(tmp_path):
    """Stesso guasto di `test_un_automazione_non_a_dizionario_si_scarta_senza_esplodere`,
    ma attraverso `rileggi()` per intero — file veri su disco, corpo YAML
    reale, non solo `componi()` isolato."""
    (tmp_path / "automations.yaml").write_text(
        "- id: '1'\n  alias: Sveglia\n  trigger: []\n-\n", encoding="utf-8"
    )
    # scripts.yaml resta assente: non serve a questo test.

    class _ClienteConSveglia:
        async def get_states(self, entity_ids):
            return [{"entity_id": "automation.sveglia", "state": "on",
                      "attributes": {"id": "1", "friendly_name": "Sveglia"}}]

    archivio = ArchivioCasa(str(tmp_path / "casa.db"))
    try:
        esito = await rileggi(_ClienteConSveglia(), archivio, tmp_path)
        assert any("voce #2" in p for p in esito["problemi"])
        voci = archivio.comportamento()
        assert [v["nome"] for v in voci] == ["Sveglia"]
    finally:
        archivio.chiudi()


@pytest.mark.asyncio
async def test_uno_stato_senza_automazioni_ne_script_non_sostituisce(tmp_path):
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

    class _ClienteConStati:
        def __init__(self, stati):
            self._stati = stati

        async def get_states(self, entity_ids):
            return self._stati

    archivio = ArchivioCasa(str(tmp_path / "casa.db"))
    try:
        # Prima lettura: HA e' su, l'automazione e' viva -> replica buona.
        cliente_su = _ClienteConStati([
            {"entity_id": "automation.sveglia", "state": "on",
             "attributes": {"id": "1700", "friendly_name": "Sveglia"}},
        ])
        await rileggi(cliente_su, archivio, tmp_path)
        assert len(archivio.comportamento()) == 1
        assert archivio.comportamento()[0]["origine"] == "file"

        # HA riparte in safe mode: /api/states risponde 200 ma vuoto.
        cliente_safe_mode = _ClienteConStati([])
        esito = await rileggi(cliente_safe_mode, archivio, tmp_path)

        # La replica precedente resta INTATTA: non diventa "solo_file", e
        # l'automazione a mano scritta a mano (se ci fosse stata) non sparisce.
        voci = archivio.comportamento()
        assert len(voci) == 1
        assert voci[0]["nome"] == "Sveglia"
        assert voci[0]["origine"] == "file"
        assert esito["problemi"]  # il fatto e' dichiarato, non solo loggato
    finally:
        archivio.chiudi()
