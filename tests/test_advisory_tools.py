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


# fetta E2 Task 7 ("esce il dispatcher"): `test_dispatcher_instrada_il_tool_
# allo_store_iniettato` viveva qui, provando due cose insieme: (1) che
# `ToolDispatcher` girasse `get_advisories` allo store iniettato
# correttamente, e (2) che il dispatcher normalizzasse `severity=""` a
# `None` PRIMA di chiamare `get_advisories` (`inputs.get("severity") or
# None`, dentro il ramo -- `get_advisories` stessa tratta `""` come un
# valore fuori enum e risponde errore, vedi sotto in questo file). Entrambe
# vivevano SOLO nel dispatcher, ora uscito, e non hanno successore: nessun
# altro chiamante instrada piu' `get_advisories` a runtime, ne' normalizza
# piu' una severity vuota. Il comportamento della funzione stessa (incluso
# `severity=None` = nessun filtro) resta provato direttamente qui sotto e
# nel resto del file, senza passare da nessun dispatcher.


def test_il_totale_dichiarato_rispetta_il_filtro_severita():
    righe = [_riga(id=i, severity="info", title=f"info {i}")
             for i in range(MAX_ADVISORIES + 5)]
    righe += [_riga(id=900 + i, severity="high", title=f"grave {i}")
              for i in range(3)]
    res = get_advisories(_FakeStore(righe), severity="high")
    assert res["count"] == 3
    assert "truncated" not in res


# --- perimetro delle entita' ------------------------------------------------
# Gemello del filtro di get_logbook (tools/diagnostics_tools.py): l'evidenza di
# una segnalazione porta identificativi e nomi amichevoli di tutta la casa --
# la batteria della serratura, l'automazione dell'allarme -- e senza perimetro
# un bot ristretto alle luci (o un agente reattivo, che ha get_advisories fra i
# suoi tool) se li legge tutti.

def test_senza_perimetro_vede_tutte_le_segnalazioni():
    righe = [
        _riga(id=1, evidence={"entity_id": "light.salotto"}),
        _riga(id=2, evidence={"entity_id": "lock.portone"}),
    ]
    res = get_advisories(_FakeStore(righe), severity=None, allowed_entities=None)
    assert res["count"] == 2
    assert "filtered" not in res


def test_scarta_le_segnalazioni_di_entita_fuori_perimetro():
    righe = [
        _riga(id=1, evidence={"entity_id": "light.salotto"}),
        _riga(id=2, evidence={"entity_id": "lock.portone", "name": "Portone"}),
    ]
    res = get_advisories(_FakeStore(righe), severity=None,
                         allowed_entities=["light.*"])
    assert res["count"] == 1
    assert res["advisories"][0]["evidence"]["entity_id"] == "light.salotto"
    # Nessuna traccia dell'entita' fuori perimetro, nemmeno il nome amichevole.
    assert "portone" not in repr(res).lower()


def test_dichiara_il_filtro_di_perimetro():
    # Come fa get_logbook con `filtered`: il modello deve poter dire che sta
    # vedendo una parte, invece di concludere "non c'e' altro".
    righe = [
        _riga(id=1, evidence={"entity_id": "light.salotto"}),
        _riga(id=2, evidence={"entity_id": "lock.portone"}),
    ]
    res = get_advisories(_FakeStore(righe), severity=None,
                         allowed_entities=["light.*"])
    assert res["filtered"] == {"shown": 1, "total": 2}


def test_perimetro_conserva_le_segnalazioni_di_sistema():
    # Spazio disco, add-on e aggiornamenti non riguardano un'entita': sono
    # informazioni di sistema, non di una stanza. Scartarle renderebbe cieco
    # sulla salute della casa proprio il bot che deve sorvegliarla.
    righe = [
        _riga(id=1, check_id="disk_space", evidence={"free_pct": 7, "free_gb": 3.1}),
        _riga(id=2, check_id="addon_unhealthy", evidence={"slug": "core_samba",
                                                          "state": "stopped"}),
        _riga(id=3, check_id="updates_available", evidence={"count": 4,
                                                            "items": ["Core 2026.7"]}),
    ]
    res = get_advisories(_FakeStore(righe), severity=None,
                         allowed_entities=["light.*"])
    assert res["count"] == 3
    assert "filtered" not in res


def test_perimetro_vuoto_non_lascia_passare_alcuna_entita():
    # `[]` e' una decisione, non un'omissione (stessa semantica del dispatcher).
    righe = [_riga(id=1, evidence={"entity_id": "light.salotto"})]
    res = get_advisories(_FakeStore(righe), severity=None, allowed_entities=[])
    assert res["count"] == 0
    assert res["filtered"] == {"shown": 0, "total": 1}


def test_perimetro_restringe_il_campione_di_entita_nell_evidenza():
    # `entity_no_area` non ha un `entity_id`: e' una voce di sistema e resta.
    # Ma la sua evidenza porta un CAMPIONE di identificativi di tutta la casa,
    # che e' la stessa fuga per un'altra strada. `count` resta il totale reale
    # (lo era gia': i controlli troncano il campione a 50).
    righe = [_riga(id=1, check_id="entity_no_area", evidence={
        "count": 3, "entities": ["light.salotto", "lock.portone", "alarm.casa"]})]
    res = get_advisories(_FakeStore(righe), severity=None,
                         allowed_entities=["light.*"])
    voce = res["advisories"][0]
    assert voce["evidence"]["entities"] == ["light.salotto"]
    assert voce["evidence"]["count"] == 3


def test_troncamento_conta_solo_cio_che_e_dentro_al_perimetro():
    # `truncated.total` deve descrivere l'elenco che il chiamante puo' vedere:
    # contarci dentro le voci gia' scartate dal perimetro farebbe riferire
    # all'utente problemi che non sono nemmeno suoi.
    righe = [_riga(id=i, evidence={"entity_id": f"lock.p{i}"})
             for i in range(MAX_ADVISORIES + 5)]
    righe.append(_riga(id=999, evidence={"entity_id": "light.salotto"}))
    res = get_advisories(_FakeStore(righe), severity=None,
                         allowed_entities=["light.*"])
    assert res["count"] == 1
    assert "truncated" not in res


def test_tool_def_dichiara_il_filtro_di_perimetro():
    assert "filtered" in GET_ADVISORIES_TOOL_DEF["description"]


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


def test_evidence_la_chiave_sintetica_sopravvive_a_quella_enorme_che_la_precede():
    # Gemello del test qui sopra con l'ORDINE INVERTITO. Li' la chiave piccola
    # viene prima e il caso resta verde anche fermandosi alla prima chiave
    # smisurata: non pinna nulla. Qui la smisurata viene PRIMA, quindi solo il
    # "salta e prosegui" (`continue`, non `break`) fa arrivare `count` al
    # modello -- ed e' proprio `count` che gli permette di riferire il numero
    # reale invece di dedurlo dai pochi elementi mostrati.
    grande = {"addons": ["addon-molto-lungo-" + "x" * 80] * 40, "count": 3}
    res = get_advisories(_FakeStore([_riga(evidence=grande)]), severity=None)
    voce = res["advisories"][0]
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
