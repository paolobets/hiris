"""Test del tool che espone all'LLM le segnalazioni del Brain."""
import pytest

from hiris.app.tools.advisory_tools import (
    GET_ADVISORIES_TOOL_DEF,
    MAX_ADVISORIES,
    MAX_EVIDENCE_CHARS,
    MAX_EVIDENCE_KEYS,
    STATI_ATTIVI,
    get_advisories,
)


def _riga(**kw) -> dict:
    """Riga completa come la restituisce AdvisoryStore.list()."""
    base = {
        "id": 1,
        "check_id": "low_battery",
        "ts_created": "2026-07-30T08:00:00Z",
        "ts_updated": "2026-07-31T08:00:00Z",
        "severity": "warn",
        "title": "Batteria scarica: Sensore porta",
        "evidence": {"entity_id": "sensor.porta_battery", "pct": 8},
        "suggested_fix": "Sostituisci la batteria del sensore.",
        "fix_kind": "manual",
        "status": "open",
        "source_ref": "low_battery:sensor.porta_battery",
        "resolved_auto": 0,
    }
    base.update(kw)
    return base


class _FakeStore:
    """Store finto: registra le chiamate e restituisce righe preconfezionate."""

    def __init__(self, righe):
        self.righe = righe
        self.chiamate = []

    def list(self, *, status=None):
        self.chiamate.append(status)
        if status is None:
            return list(self.righe)
        return [r for r in self.righe if r["status"] == status]


class _StoreRotto:
    def list(self, *, status=None):
        raise RuntimeError("db corrotto: /data/advisory.db")


@pytest.fixture
def store():
    return _FakeStore([
        _riga(id=1, severity="high", title="Automazione rotta",
              check_id="automation_broken", status="open"),
        _riga(id=2, severity="warn", title="Batteria scarica", status="open"),
        _riga(id=3, severity="info", title="Entita' senza area",
              check_id="entity_no_area", status="acknowledged"),
    ])


# --- tool def ---------------------------------------------------------------

def test_tool_def_ha_i_campi_richiesti():
    assert GET_ADVISORIES_TOOL_DEF["name"] == "get_advisories"
    assert "description" in GET_ADVISORIES_TOOL_DEF
    props = GET_ADVISORIES_TOOL_DEF["input_schema"]["properties"]
    assert "severity" in props
    assert set(props["severity"]["enum"]) == {"high", "warn", "info"}
    assert GET_ADVISORIES_TOOL_DEF["input_schema"]["required"] == []


def test_tool_def_dichiara_il_troncamento_al_modello():
    # Senza questa istruzione il modello riferisce la lista tagliata come se
    # fosse completa, e l'utente conclude che i problemi siano meno di quanti sono.
    assert "truncated" in GET_ADVISORIES_TOOL_DEF["description"]


# --- comportamento base -----------------------------------------------------

def test_restituisce_le_segnalazioni_attive(store):
    res = get_advisories(store, severity=None)
    assert res["count"] == 3
    assert len(res["advisories"]) == 3
    assert "truncated" not in res


def test_default_severity_none_non_filtra(store):
    res = get_advisories(store, severity=None)
    assert {a["severity"] for a in res["advisories"]} == {"high", "warn", "info"}


def test_store_assente_ritorna_errore():
    res = get_advisories(None, severity=None)
    assert "error" in res
    assert "advisories" not in res


def test_store_che_solleva_non_propaga_e_non_fa_echo(store):
    res = get_advisories(_StoreRotto(), severity=None)
    assert "error" in res
    # L'errore interno non deve arrivare al prompt dell'LLM.
    assert "db corrotto" not in res["error"]
    assert "/data/advisory.db" not in res["error"]


# --- filtro per severita' ---------------------------------------------------

def test_filtro_per_severita(store):
    res = get_advisories(store, severity="high")
    assert res["count"] == 1
    assert res["advisories"][0]["severity"] == "high"


def test_filtro_per_severita_sconosciuta_ritorna_errore(store):
    res = get_advisories(store, severity="catastrofica")
    assert "error" in res
    assert "advisories" not in res


# --- stati ------------------------------------------------------------------

def test_esclude_dismissed_e_resolved():
    # 'dismissed' = messa a tacere dall'utente per sempre: non deve riemergere
    # in chat. 'resolved' = problema rientrato.
    s = _FakeStore([
        _riga(id=1, status="open", title="Aperta"),
        _riga(id=2, status="acknowledged", title="Presa in carico"),
        _riga(id=3, status="resolved", title="Rientrata"),
        _riga(id=4, status="dismissed", title="Messa a tacere"),
    ])
    res = get_advisories(s, severity=None)
    titoli = {a["title"] for a in res["advisories"]}
    assert titoli == {"Aperta", "Presa in carico"}


def test_integrazione_con_lo_store_reale(tmp_path):
    from hiris.app.brain.advisory_store import AdvisoryStore

    store = AdvisoryStore(str(tmp_path / "advisory.db"))
    try:
        store.reconcile([
            {"check_id": "low_battery", "severity": "warn", "title": "Batteria A",
             "evidence": {"pct": 5}, "suggested_fix": "Sostituisci",
             "fix_kind": "manual", "source_ref": "low_battery:a"},
            {"check_id": "low_battery", "severity": "warn", "title": "Batteria B",
             "evidence": {"pct": 7}, "suggested_fix": "Sostituisci",
             "fix_kind": "manual", "source_ref": "low_battery:b"},
        ], {"low_battery"})
        aperte = store.list(status="open")
        store.set_status(aperte[0]["id"], "dismissed")

        res = get_advisories(store, severity=None)
        assert res["count"] == 1
        assert res["advisories"][0]["evidence"]  # evidence deserializzata
    finally:
        store.close()


# --- campi esposti ----------------------------------------------------------

def test_espone_solo_i_campi_utili_al_modello(store):
    voce = get_advisories(store, severity=None)["advisories"][0]
    assert set(voce) == {"severity", "title", "evidence", "suggested_fix", "status"}


def test_non_espone_i_dettagli_interni_dello_store(store):
    voce = get_advisories(store, severity=None)["advisories"][0]
    for interno in ("id", "source_ref", "fix_kind", "resolved_auto",
                    "ts_created", "ts_updated", "check_id"):
        assert interno not in voce


# --- cap --------------------------------------------------------------------

def test_cap_limita_le_voci_e_dichiara_il_totale():
    n = MAX_ADVISORIES + 7
    s = _FakeStore([
        _riga(id=i, source_ref=f"low_battery:{i}", title=f"Segnalazione {i}")
        for i in range(n)
    ])
    res = get_advisories(s, severity=None)
    assert len(res["advisories"]) == MAX_ADVISORIES
    assert res["count"] == MAX_ADVISORIES
    assert res["truncated"] == {
        "shown": MAX_ADVISORIES, "total": n, "order": "severity_first",
    }


def test_il_cap_mostra_prima_le_severita_alte():
    # Tagliare in ordine di arrivo nasconderebbe proprio i problemi gravi.
    righe = [_riga(id=i, severity="info", title=f"info {i}")
             for i in range(MAX_ADVISORIES + 5)]
    righe.append(_riga(id=999, severity="high", title="Grave"))
    res = get_advisories(_FakeStore(righe), severity=None)
    assert res["advisories"][0]["title"] == "Grave"
    assert res["truncated"]["total"] == len(righe)


def test_dispatcher_instrada_il_tool_allo_store_iniettato(store):
    # Il valore del task e' il cablaggio: il tool esiste solo se il dispatcher
    # lo raggiunge con lo store giusto.
    import asyncio

    from hiris.app.tools.dispatcher import ToolDispatcher

    d = ToolDispatcher(ha_client=None, notify_config={}, advisory_store=store)
    res = asyncio.run(d.dispatch("get_advisories", {"severity": "high"}))
    assert res["count"] == 1
    # severity vuota = nessun filtro, non un valore fuori enum.
    res = asyncio.run(d.dispatch("get_advisories", {"severity": ""}))
    assert res["count"] == 3


def test_il_totale_dichiarato_rispetta_il_filtro_severita():
    righe = [_riga(id=i, severity="info", title=f"info {i}")
             for i in range(MAX_ADVISORIES + 5)]
    righe += [_riga(id=900 + i, severity="high", title=f"grave {i}")
              for i in range(3)]
    res = get_advisories(_FakeStore(righe), severity="high")
    assert res["count"] == 3
    assert "truncated" not in res


# --- cap sull'evidenza ------------------------------------------------------

def test_evidence_intatta_non_dichiara_alcun_taglio(store):
    voce = get_advisories(store, severity=None)["advisories"][0]
    assert "evidence_truncated" not in voce


def test_evidence_limitata_nel_numero_di_chiavi():
    # `evidence` e' un dict di forma libera prodotto dai controlli: senza cap
    # un controllo che ne emette venti se le porterebbe tutte nel prompt.
    grande = {f"k{i}": i for i in range(MAX_EVIDENCE_KEYS + 6)}
    res = get_advisories(_FakeStore([_riga(evidence=grande)]), severity=None)
    voce = res["advisories"][0]
    assert len(voce["evidence"]) == MAX_EVIDENCE_KEYS
    assert voce["evidence_truncated"] == {
        "shown": MAX_EVIDENCE_KEYS, "total": len(grande),
    }


def test_evidence_limitata_nella_dimensione_serializzata():
    # Poche chiavi ma enormi: il cap sul numero non basta, serve quello sui
    # caratteri (il caso del Task 6, evidenza = lista di addon).
    grande = {"count": 3, "addons": ["addon-molto-lungo-" + "x" * 80] * 40}
    res = get_advisories(_FakeStore([_riga(evidence=grande)]), severity=None)
    voce = res["advisories"][0]
    import json as _json
    assert len(_json.dumps(voce["evidence"], ensure_ascii=False)) <= MAX_EVIDENCE_CHARS
    # La chiave sintetica sopravvive, quella smisurata no, e il taglio e'
    # dichiarato: il modello puo' dire all'utente che sta vedendo una parte.
    assert voce["evidence"] == {"count": 3}
    assert voce["evidence_truncated"] == {"shown": 1, "total": 2}


def test_evidence_non_dict_diventa_oggetto_vuoto():
    # `_row` dello store deserializza sempre l'evidenza, ma una riga malformata
    # la lascerebbe a None: il modello si aspetta comunque un oggetto.
    res = get_advisories(_FakeStore([_riga(evidence=None)]), severity=None)
    assert res["advisories"][0]["evidence"] == {}
    assert "evidence_truncated" not in res["advisories"][0]


def test_evidence_non_serializzabile_non_fa_fallire_la_lettura():
    res = get_advisories(
        _FakeStore([_riga(evidence={"ok": 1, "bah": object()})]), severity=None
    )
    voce = res["advisories"][0]
    assert voce["evidence"] == {"ok": 1}
    assert voce["evidence_truncated"] == {"shown": 1, "total": 2}


def test_tool_def_dichiara_il_troncamento_dell_evidenza():
    assert "evidence_truncated" in GET_ADVISORIES_TOOL_DEF["description"]


# --- letture allo store -----------------------------------------------------

def test_legge_solo_gli_stati_attivi(store):
    # Una `list()` senza stato leggerebbe l'intera tabella -- comprese le righe
    # risolte e messe a tacere, che nessuno pota mai -- e deserializzerebbe
    # l'evidenza di ognuna, tutto in modo sincrono sull'event loop.
    get_advisories(store, severity=None)
    assert store.chiamate == list(STATI_ATTIVI)
    assert None not in store.chiamate
