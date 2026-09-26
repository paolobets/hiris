"""La porta dei giudizi: costruzione dall'archivio (spec 2026-09-16 §3, §8)."""
import inspect
import json
from types import SimpleNamespace

import pytest

from hiris.app import server
from hiris.app.home_space import type_vocabulary as tv
from hiris.app.home_space.type_judgments import JUDGMENT_FIELD_NAMES
from hiris.app.mind.facts import genre_for
from hiris.app.mind.judgments import (
    JudgmentNotInEffect,
    JudgmentRefused,
    build_judgments,
    judgment_listing,
    write_judgment,
)
from hiris.app.mind.knowledge import Fact, KnowledgeStore
from hiris.app.mind.seed import REPO_PRIORITY, SEED_AUTHOR, judgment_seed

#: Chi scrive i giudizi di queste prove, come il confine lo attacca alla
#: richiesta. Dal 26/09/2026 `write_judgment` registra l'autore vero (spec
#: 2026-09-26 §3, decisione 6): prima firmava tutto «proprietario».
AUTORE = {"specie": "persona", "id": "u-admin", "nome": "Paolo"}
#: L'autore delle righe scritte dalla porta PRIMA del 26/09/2026: per loro e'
#: vero, e restano correzioni (`judgments._LEGACY_AUTHOR`).
AUTORE_STORICO = "proprietario"


def _scrivi(app, **argomenti):
    """`write_judgment` con l'autore di queste prove: la porta vera, a cui
    si aggiunge solo chi scrive."""
    return write_judgment(app, author=AUTORE, **argomenti)


def _sapere(tmp_path):
    return KnowledgeStore(str(tmp_path / "sapere.db"))


def test_sapere_seminato_rende_istantanea_repo(tmp_path):
    """Mutazione: `_status("sapere", ...)` scritto come `_status("solo seme", ...)`
    nel ramo riuscito -- rossa."""
    s = _sapere(tmp_path)
    try:
        s.seed(judgment_seed(when_ts=1.0), priority=2)
        j, stato = build_judgments(s)
        assert stato["provenienza_istantanea"] == "sapere" and stato["perche"] is None
        assert j.rows() == tv.REPO_JUDGMENTS.rows()
        assert stato["impronta"] == j.chronicle_fingerprint()
    finally:
        s.close()


def test_riga_proprietario_VINCE_seme(tmp_path):
    """Una riga che il seme possiede, riscritta dalla casa, resta dopo un
    riavvio (seme riapplicato) e vince nell'istantanea.
    Mutazioni: costruire da `REPO_JUDGMENTS` ignorando l'archivio -- rossa;
    far sovrascrivere al seme anche le righe toccate -- rossa."""
    s = _sapere(tmp_path)
    try:
        s.seed(judgment_seed(when_ts=1.0), priority=2)
        assert tv.REPO_JUDGMENTS.genre_of("person.x", None) == "presenza"
        s.write(Fact(subject_kind="tipo", subject="person",
                     field="genere", value="nessuno", provenance="nostro",
                     who="proprietario", when_ts=2.0))
        s.seed(judgment_seed(when_ts=3.0), priority=2)
        j, _ = build_judgments(s)
        assert j.genre_of("person.x", None) is None
    finally:
        s.close()


def test_riga_storta_tiene_avvio_DICHIARANDO_perche(tmp_path):
    """Spec §8: l'istantanea torna al solo seme e la salute elenca il perche'.
    Mutazione: lasciar propagare `JudgmentError` -- rossa."""
    s = _sapere(tmp_path)
    try:
        s.seed(judgment_seed(when_ts=1.0), priority=2)
        s.write(Fact(subject_kind="tipo", subject="light", field="genere",
                     value="acceso", provenance="nostro", who="proprietario", when_ts=2.0))
        j, stato = build_judgments(s)
        assert stato["provenienza_istantanea"] == "solo seme"
        assert "light" in stato["perche"]
        assert j.rows() == tv.REPO_JUDGMENTS.rows()
    finally:
        s.close()


def test_riga_che_l_archivio_SALTA_e_NOMINATA_dalla_salute(tmp_path):
    """Giro di correzioni 1, punto 6 (differito dal Task 3 al Task 7 e mai
    fatto): una riga di giudizio che non si regge come `Fact` viene **saltata**
    da `knowledge._facts` e finisce solo nel log dell'add-on, che da fuori non
    si legge. Non compariva ne' in `/api/health` ne' nella pagina: la casa
    diceva che il suo giudizio veniva dal sapere, e una riga di quel sapere non
    c'era.

    E' precisamente il caso che la porta del sapere esiste per mostrare, ed e'
    la stessa lezione del difetto del 14/09/2026 (`_record_repair`): un esito
    scritto solo nel log e' un esito perso.

    **L'istantanea resta buona** -- la riga saltata non la sporca, quindi
    `provenienza_istantanea` resta `sapere` -- ma `perche` la nomina. E la riga
    **non** compare nel listato della pagina (`judgment_listing` legge lo stesso
    `_facts`): le due porte dicono la stessa cosa, ciascuna a modo suo.

    La riga storta si scrive con un `UPDATE` a mano, che e' come nascono
    davvero (`knowledge.py`, schema): `nostro` + una verifica e' una delle
    forme che `Fact` rifiuta.

    Rossa prima della correzione: `assert None` su `stato["perche"]`.
    """
    s = _sapere(tmp_path)
    try:
        s.seed(judgment_seed(when_ts=1.0), priority=REPO_PRIORITY)
        s._conn.execute(
            "UPDATE knowledge SET verification = 'confermata', source = 'x' "
            "WHERE subject = 'light' AND field = 'genere'")
        s._conn.commit()

        j, stato = build_judgments(s)
        assert stato["provenienza_istantanea"] == "sapere"
        assert stato["perche"] and "light" in stato["perche"] and "genere" in stato["perche"]
        assert not any(g["soggetto"] == "light" and g["campo"] == "genere"
                       for g in judgment_listing(s))
        assert j.genre_of("light.cucina", None) is None, (
            "la riga saltata non vale: senza di lei il dominio `light` non ha genere")
    finally:
        s.close()


def test_sapere_assente_torna_seme_DICHIARANDO_perche():
    """Mutazione: `perche` a `None` nel ramo senza archivio -- rossa."""
    j, stato = build_judgments(None)
    assert stato["provenienza_istantanea"] == "solo seme" and stato["perche"]
    assert j is tv.REPO_JUDGMENTS


def test_sapere_nasce_PRIMA_cache_entita():
    """Strutturale, dichiarata: non esiste un modo economico di avviare
    `_on_startup` in prova, quindi si guarda l'ordine nel sorgente.
    L'ordine e' prescritto dalla spec §8 («Il sapere, il suo seme e
    l'istantanea nascono prima della EntityCache»); oggi nessun lettore vivo
    della cache lo pretende (spec §2, §3).
    Mutazione: rimettere il blocco del sapere dopo `EntityCache()` -- rossa.

    Dal Task 7b il blocco vive in `_open_knowledge`, e l'ordine si cerca dentro
    `_on_startup`: cercato nel modulo intero, la definizione della funzione (che
    sta sopra) lo renderebbe vero per sempre."""
    src = inspect.getsource(server._on_startup)
    assert (src.index("_open_knowledge(app, data_dir)")
            < src.index("entity_cache = EntityCache("))


# -- l'avvio col sapere che non si apre (spec §8, Task 7b) ---------------------

class _BrokenStore:
    """Un archivio che si apre e poi non si lascia seminare."""

    def __init__(self, path):
        self.closed = False

    def seed(self, facts, *, priority):
        raise RuntimeError("disco pieno")

    def close(self):
        self.closed = True


def test_sapere_che_NON_si_apre_NON_ferma_avvio_e_la_salute_dice_l_errore(tmp_path, monkeypatch,
                                                                         caplog):
    """Decisione del proprietario 17/09/2026, spec §8. Mutazioni ESEGUITE:
    togliere la cattura in `_open_knowledge` -- rossa; perdere l'errore vero dal
    `perche` -- rossa."""
    import logging
    import sqlite3

    def _refuse(path):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(server, "KnowledgeStore", _refuse)
    app = {}
    with caplog.at_level(logging.ERROR, logger=server.logger.name):
        server._open_knowledge(app, str(tmp_path))
    assert app["knowledge"] is None
    assert app["type_judgments"] is tv.REPO_JUDGMENTS
    status = app["type_judgments_status"]
    assert status["provenienza_istantanea"] == "solo seme"
    assert "OperationalError: unable to open database file" in status["perche"], status
    assert status["impronta"] == tv.REPO_JUDGMENTS.chronicle_fingerprint()
    # Con la traccia (fix round 1): mutazione ESEGUITA `logger.error` senza
    # `exc_info` -- rossa.
    assert any("unable to open database file" in r.getMessage() and r.exc_info
               for r in caplog.records)


def test_seme_che_solleva_CHIUDE_archivio_e_torna_al_seme(tmp_path, monkeypatch):
    """Il seme solleva dopo che l'archivio si e' aperto: si chiude, e non resta
    appeso in `app`. Mutazione ESEGUITA: togliere la `close()` -- rossa."""
    opened = []

    def _open(path):
        opened.append(_BrokenStore(path))
        return opened[-1]

    monkeypatch.setattr(server, "KnowledgeStore", _open)
    app = {}
    server._open_knowledge(app, str(tmp_path))
    assert app["knowledge"] is None
    assert [store.closed for store in opened] == [True]
    assert "RuntimeError: disco pieno" in app["type_judgments_status"]["perche"]


def test_sapere_che_si_apre_arriva_in_app_seminato(tmp_path):
    app = {}
    server._open_knowledge(app, str(tmp_path))
    try:
        assert isinstance(app["knowledge"], KnowledgeStore)
        assert app["type_judgments_status"]["provenienza_istantanea"] == "sapere"
        assert app["type_judgments"].rows() == tv.REPO_JUDGMENTS.rows()
    finally:
        app["knowledge"].close()


def test_chiusura_regge_il_sapere_assente():
    """`_on_cleanup` con `app["knowledge"] = None` (l'avvio qui sopra). Mutazione
    ESEGUITA: tornare a `if "knowledge" in app` -- rossa (`None.close()`)."""
    import asyncio

    class _Client:
        async def stop(self):
            return None

    asyncio.run(server._on_cleanup({"knowledge": None, "ha_client": _Client()}))


# -- la porta di scrittura (spec §4) -------------------------------------------

def _app_seminata(tmp_path):
    s = _sapere(tmp_path)
    s.seed(judgment_seed(when_ts=1.0), priority=REPO_PRIORITY)
    j, stato = build_judgments(s)
    return s, {"knowledge": s, "type_judgments": j, "type_judgments_status": stato}


def test_scrivere_rileggere_DAL_LETTORE(tmp_path):
    """Spec §9.3: si rilegge dal lettore della cronaca, non dall'archivio.
    Mutazioni: togliere la sostituzione di `app["type_judgments"]` -- rossa;
    togliere quella di `app["type_judgments_status"]` (le due si sostituiscono
    INSIEME) -- rossa."""
    s, app = _app_seminata(tmp_path)
    try:
        prima = app["type_judgments_status"]
        esito = _scrivi(app, subject_kind="tipo", subject="binary_sensor.occupancy",
                               field="genere", value="presenza", now=lambda: 2.0)
        assert genre_for("binary_sensor.fp300", "occupancy",
                         judgments=app["type_judgments"]) == "presenza"
        assert esito["impronta"] == app["type_judgments"].chronicle_fingerprint()
        assert esito["impronta"] != prima["impronta"]
        assert app["type_judgments_status"] is not prima
        assert app["type_judgments_status"] == {"provenienza_istantanea": "sapere",
                                                "perche": None,
                                                "impronta": esito["impronta"]}
        assert esito["provenienza_istantanea"] == "sapere"
        assert esito["riga"] == {"soggetto_genere": "tipo",
                                 "soggetto": "binary_sensor.occupancy",
                                 "campo": "genere", "valore": "presenza",
                                 "chi": "Paolo", "quando_ts": 2.0}
        riga = s.get("tipo", "binary_sensor.occupancy", "genere")
        assert (riga.value, riga.who, riga.provenance) == ("presenza", "Paolo", "nostro")
        assert riga.said_by == "persona:u-admin"
    finally:
        s.close()


def test_tornare_seme(tmp_path):
    """Mutazione: `value=None` scrive la stringa vuota invece del seme -- rossa
    (la stringa vuota non si interpreta: l'istantanea torna al solo seme e
    la scrittura lo dichiara)."""
    s, app = _app_seminata(tmp_path)
    try:
        _scrivi(app, subject_kind="tipo", subject="light", field="genere",
                       value="sicurezza", now=lambda: 2.0)
        assert app["type_judgments"].rows() != tv.REPO_JUDGMENTS.rows()
        esito = _scrivi(app, subject_kind="tipo", subject="light", field="genere",
                               value=None, now=lambda: 3.0)
        assert app["type_judgments"].rows() == tv.REPO_JUDGMENTS.rows()
        assert esito["riga"]["chi"] == SEED_AUTHOR
        _scrivi(app, subject_kind="entita", subject="switch.x", field="genere",
                       value="nessuno", now=lambda: 4.0)
        assert s.get("entita", "switch.x", "genere") is not None
        esito = _scrivi(app, subject_kind="entita", subject="switch.x", field="genere",
                               value=None, now=lambda: 5.0)
        assert s.get("entita", "switch.x", "genere") is None
        assert esito["riga"] is None
        assert app["type_judgments"].rows() == tv.REPO_JUDGMENTS.rows()
    finally:
        s.close()


def test_tornare_seme_RIAGGANCIA_riga_seme(tmp_path):
    """Una riga scritta prima che il seme la possedesse ha `seeded_value`
    nullo: il seme non la tocca piu'. Tornare al seme deve restituirla al seme
    DAVVERO -- un rilascio che corregge quel valore nel repo deve arrivarle.
    Mutazione: tornare al seme con `knowledge.write` del valore seminato
    (lascia `seeded_value` nullo) -- rossa."""
    s = _sapere(tmp_path)
    try:
        s.write(Fact(subject_kind="tipo", subject="light", field="genere", value="nessuno",
                     provenance="nostro", who=AUTORE_STORICO, when_ts=1.0))
        s.seed(judgment_seed(when_ts=1.0), priority=REPO_PRIORITY)
        assert s.get("tipo", "light", "genere").value == "nessuno"
        j, stato = build_judgments(s)
        app = {"knowledge": s, "type_judgments": j, "type_judgments_status": stato}
        _scrivi(app, subject_kind="tipo", subject="light", field="genere",
                       value=None, now=lambda: 2.0)
        rilascio = Fact(subject_kind="tipo", subject="light", field="genere",
                        value="sicurezza", provenance="nostro", who=SEED_AUTHOR, when_ts=3.0)
        s.seed([rilascio], priority=REPO_PRIORITY)
        assert s.get("tipo", "light", "genere").value == "sicurezza"
    finally:
        s.close()


def test_porta_RIFIUTA_fatto_ha_genere_inventato_ARCHIVIO_intatto(tmp_path):
    """Spec §4.1, D1, D2. Mutazione: togliere la validazione del valore prima
    della scrittura -- rossa (l'archivio cambia)."""
    s, app = _app_seminata(tmp_path)
    try:
        righe = [(f.subject_kind, f.subject, f.field, f.value, f.who) for f in s.judgment_rows()]
        stato = app["type_judgments_status"]
        rifiutate = [
            ("tipo", "climate", "capability_names", "{}"),       # fatto di HA
            ("tipo", "select", "attributi_assumibili", "{}"),    # D1: resta codice
            ("tipo", "light", "genere", "acceso"),               # genere inventato
            ("tipo", "sensor.power", "genere", "energia"),       # D2
            ("tipo", "sensor.power", "genere", "bilancio"),      # D2
            ("tipo", "light", "riposo", '["off", "none"]'),      # l'assenza non e' riposo
            ("tipo", "light", "riposo", "off"),                  # JSON rotto
            ("tipo", "", "genere", "presenza"),                  # soggetto vuoto
            ("dispositivo", "abc", "genere", "presenza"),        # genere di soggetto
        ]
        for kind, subject, field, value in rifiutate:
            with pytest.raises(JudgmentRefused):
                _scrivi(app, subject_kind=kind, subject=subject, field=field, value=value)
        with pytest.raises(JudgmentRefused):
            _scrivi(app, subject_kind="tipo", subject="light", field="riposo",
                           value=["off"])
        assert [(f.subject_kind, f.subject, f.field, f.value, f.who)
                for f in s.judgment_rows()] == righe
        assert app["type_judgments_status"] is stato
    finally:
        s.close()


def test_porta_RIFIUTA_da_sapere_subito_SENZA_riposo_ne_lavoro(tmp_path):
    """Ruling del controller (giro di correzioni 1, IMPORTANT 2): un tipo con
    `da_sapere_subito: si` e SENZA `riposo` ne' `lavoro` e' indecidibile -- per
    sapere quando una cosa esce dal suo riposo bisogna sapere qual e' il
    riposo. La porta lo rifiuta **spiegando perche'**, invece di accettare in
    silenzio una riga che chi la scrive crede di aver capito.

    **Questa prova sorveglia la CORTESIA, non la garanzia** (revisione finale,
    I-1): la garanzia e' nella regola, che senza lavoro ne' riposo risponde
    `no` -- e si prova in
    `test_type_judgments.py::test_un_SI_ORFANO_senza_riposo_ne_lavoro_NON_rende_notizia_ogni_stato`.
    Il rifiuto da solo non basterebbe: il `si` orfano si ottiene scrivendo
    prima il riposo, poi il `si`, poi togliendo il riposo -- una sequenza di
    tre scritture che questa porta accetta tutte, una per una.

    Vista rossa PRIMA di scrivere il rifiuto in `_check`: la scrittura veniva
    accettata in silenzio (nessun `pytest.raises` scattava, `s.get(...)`
    tornava la riga scritta).

    Mutazione da ESEGUIRE: togliere il nuovo controllo da `_check` -- rossa,
    la scrittura torna ad essere accettata.
    """
    s, app = _app_seminata(tmp_path)
    try:
        righe = [(f.subject_kind, f.subject, f.field, f.value, f.who) for f in s.judgment_rows()]
        with pytest.raises(JudgmentRefused, match="riposo"):
            _scrivi(app, subject_kind="tipo", subject="update", field="da_sapere_subito",
                           value="si")
        assert s.get("tipo", "update", "da_sapere_subito") is None
        assert [(f.subject_kind, f.subject, f.field, f.value, f.who)
                for f in s.judgment_rows()] == righe
        # Con un riposo dichiarato PRIMA, la stessa riga passa: il rifiuto
        # segue lo stato del sapere, non un elenco scritto a mano.
        _scrivi(app, subject_kind="tipo", subject="update", field="riposo",
                       value='["off"]')
        _scrivi(app, subject_kind="tipo", subject="update", field="da_sapere_subito",
                       value="si")
        assert app["type_judgments"].da_sapere_subito("update") is True
    finally:
        s.close()


def test_porta_RIFIUTA_guasto(tmp_path):
    """`guasto` e' un genere con una forma, ma quella forma e' delle condizioni
    di sistema (`problema:`, `integrazione:`...: spec §5) e legge `a` come
    `chiuso`/condizione: su uno stato di un'entita' `off` APRIREBBE un guasto e
    nessuno stato lo chiuderebbe. Mutazione: togliere il rifiuto -- rossa."""
    s, app = _app_seminata(tmp_path)
    try:
        for kind, subject in (("tipo", "light"), ("entita", "light.x")):
            with pytest.raises(JudgmentRefused, match="guasto"):
                _scrivi(app, subject_kind=kind, subject=subject, field="genere",
                               value="guasto")
        assert s.get("entita", "light.x", "genere") is None
    finally:
        s.close()


# Il livello del soggetto: una riga che nessuna domanda consulta non si scrive
# (revisione del Task 1). Le domande di `TypeJudgments`: `genre_of` e
# `resting_of` salgono entita' -> coppia -> dominio; `working_of` e `is_notable`
# coppia -> dominio; `operable_domains` e `parameter_limits` solo
# dominio.
_LIVELLI_LETTI = [
    ("entita", "switch.x", "genere", "sicurezza",
     lambda j: j.genre_of("switch.x", None) == "sicurezza"),
    ("tipo", "sensor.power", "genere", "funzionamento",
     lambda j: j.genre_of("sensor.p", "power") == "funzionamento"),
    ("entita", "switch.x", "riposo", '["on"]',
     lambda j: j.resting_of("switch", None, "switch.x") == frozenset({"on"})),
    ("tipo", "sensor.power", "riposo", '["on"]',
     lambda j: j.resting_of("sensor", "power") == frozenset({"on"})),
    ("tipo", "binary_sensor.occupancy", "lavoro", '{"on": "occupato"}',
     lambda j: dict(j.working_of("binary_sensor", "occupancy")) == {"on": "occupato"}),
    ("tipo", "sensor.power", "notevole", "si",
     lambda j: j.is_notable("sensor", "power")),
    ("tipo", "sensor", "accendibile", "si",
     lambda j: "sensor" in j.operable_domains()),
    ("tipo", "sensor", "limiti_parametri", '{"x": {"options": "y"}}',
     lambda j: dict(j.parameter_limits("sensor", "x")) == {"options": "y"}),
]

_LIVELLI_MUTI = [
    ("entita", "light.x", "notevole", "si"),
    ("entita", "light.x", "lavoro", '{"on": "acceso"}'),
    ("entita", "light.x", "accendibile", "si"),
    ("entita", "climate.x", "limiti_parametri", '{"x": {"options": "y"}}'),
    ("tipo", "sensor.power", "accendibile", "si"),
    ("tipo", "climate.hvac", "limiti_parametri", '{"x": {"options": "y"}}'),
    # D1 della fetta 2026-09-18: `_LEVELS` dichiara i livelli a cui
    # `da_sapere_subito` e' davvero CONSULTATO -- coppia e dominio, come
    # `notevole`. Una riga su un'entita' sarebbe accettata e non letta da
    # nessuno: il proprietario la vedrebbe scritta e la casa non cambierebbe.
    ("entita", "alarm_control_panel.ingresso", "da_sapere_subito", "si"),
    # forme di soggetto che nessuna chiave di ricerca costruisce
    ("entita", "light", "genere", "sicurezza"),
    ("entita", "light.", "genere", "sicurezza"),
    ("entita", "light.x.y", "genere", "sicurezza"),
    ("tipo", "sensor.power.x", "genere", "sicurezza"),
    ("tipo", ".power", "genere", "sicurezza"),
    # forme che nessun dominio, classe o entity_id di Home Assistant ha
    # (minuscole, cifre, `_`): accettate, non cambierebbero mai la casa
    ("tipo", "Light", "genere", "sicurezza"),
    ("tipo", "light x", "genere", "sicurezza"),
    ("tipo", "sensor. power", "genere", "sicurezza"),
    ("tipo", "1light", "genere", "sicurezza"),
    ("entita", "Light.x", "genere", "sicurezza"),
    ("entita", "light.x y", "genere", "sicurezza"),
]


@pytest.mark.parametrize(("kind", "subject", "field", "value", "letta"), _LIVELLI_LETTI)
def test_livello_ammesso_LETTO_lettore(tmp_path, kind, subject, field, value, letta):
    """Ogni livello che la porta accetta e' uno che una domanda consulta.
    Mutazione: rifiutare le entita' per `genere` -- rossa."""
    s, app = _app_seminata(tmp_path)
    try:
        _scrivi(app, subject_kind=kind, subject=subject, field=field, value=value)
        assert letta(app["type_judgments"])
    finally:
        s.close()


@pytest.mark.parametrize(("kind", "subject", "field", "value"), _LIVELLI_MUTI)
def test_livello_MUTO_rifiutato(tmp_path, kind, subject, field, value):
    """Una riga che nessuna domanda legge si rifiuta, motivata.
    Mutazioni ESEGUITE: togliere il controllo del livello -- rossa; togliere il
    controllo della forma del soggetto (tornare a spezzare sul punto) -- rossa
    sulle forme con maiuscole, spazi, cifra iniziale."""
    s, app = _app_seminata(tmp_path)
    try:
        righe = [(f.subject_kind, f.subject, f.field, f.value, f.who) for f in s.judgment_rows()]
        with pytest.raises(JudgmentRefused, match="nessuna domanda|soggetto"):
            _scrivi(app, subject_kind=kind, subject=subject, field=field, value=value)
        assert [(f.subject_kind, f.subject, f.field, f.value, f.who)
                for f in s.judgment_rows()] == righe
    finally:
        s.close()


def test_ogni_soggetto_seme_HA_forma_ammessa(tmp_path):
    """Il proprietario deve poter correggere ogni riga del seme: la forma che
    la porta pretende non puo' escluderne nessuna. Mutazione ESEGUITA: la
    forma del tipo senza `_` nel dominio -- rossa (`alarm_control_panel`)."""
    s, app = _app_seminata(tmp_path)
    try:
        for kind, subject, field, value in tv.judgment_seed_rows():
            _scrivi(app, subject_kind=kind, subject=subject, field=field, value=value)
    finally:
        s.close()


def test_scrittura_NON_IN_VIGORE_si_dichiara(tmp_path):
    """Una riga storta nell'archivio (corretto a mano: `knowledge.py`) fa
    tornare l'istantanea al solo seme anche dopo una scrittura buona. La porta
    non dice «fatto»: solleva, e l'app riflette lo stato vero.
    Mutazione: togliere il controllo su `da == "solo seme"` dopo la
    ricostruzione -- rossa."""
    s, app = _app_seminata(tmp_path)
    try:
        s.write(Fact(subject_kind="tipo", subject="light", field="genere",
                     value="acceso", provenance="nostro", who="a mano", when_ts=2.0))
        with pytest.raises(JudgmentNotInEffect) as preso:
            _scrivi(app, subject_kind="tipo", subject="binary_sensor.occupancy",
                           field="genere", value="presenza", now=lambda: 3.0)
        assert "solo seme" in str(preso.value) and "light" in str(preso.value)
        assert preso.value.status["provenienza_istantanea"] == "solo seme"
        assert preso.value.row["valore"] == "presenza"
        assert app["type_judgments_status"]["provenienza_istantanea"] == "solo seme"
        assert app["type_judgments"] is tv.REPO_JUDGMENTS
        assert s.get("tipo", "binary_sensor.occupancy", "genere").value == "presenza"
    finally:
        s.close()


def test_senza_sapere_porta_RIFIUTA():
    """Mutazione: togliere la guardia -- `AttributeError`, non un rifiuto."""
    app = {"type_judgments": tv.REPO_JUDGMENTS}
    with pytest.raises(JudgmentRefused):
        _scrivi(app, subject_kind="tipo", subject="light", field="genere",
                       value="sicurezza")


@pytest.mark.asyncio
async def test_salute_espone_stato_ISTANTANEA():
    """Spec §8: da fuori si deve poter chiedere da dove vengono i giudizi.
    Mutazione: togliere la chiave `istantanea` da `_handle_health` -- rossa."""
    _, stato = build_judgments(None)
    request = SimpleNamespace(app={"type_judgments_status": stato})
    response = await server._handle_health(request)
    assert json.loads(response.body)["istantanea"] == stato


@pytest.mark.asyncio
async def test_le_due_parole_doppie_sono_SEPARATE_alla_fonte(tmp_path):
    """Fondamenta 3 e regola del proprietario (giro di correzioni 1, punto 3):
    **due cose diverse dette con UNA parola si separano alla fonte**, mai a
    valle. Ce n'erano due, ed erano entrambe letterali di questa fetta:

    - **`giudizi`** era lo *stato dell'istantanea* in `/api/health` e l'*elenco
      delle righe* in `/api/mind/knowledge`. Lo stato diventa `istantanea`;
      l'elenco, che di giudizi e' fatto davvero, tiene `giudizi`.
    - **`da`** era l'*origine della riga* (`seme`/`proprietario`/`altro`) nel
      listato e la *provenienza dell'istantanea* (`sapere`/`solo seme`) nella
      risposta della scrittura, nel 409 e nello stato. La seconda diventa
      `provenienza_istantanea` **dove nasce** (`judgments._status`), cosi' che
      nessuna porta a valle debba ribattezzarla; la prima tiene `da`.

    Rosse prima della correzione: `KeyError: 'istantanea'` sulla salute e
    `KeyError: 'provenienza_istantanea'` sull'esito della scrittura.
    """
    s, app = _app_seminata(tmp_path)
    try:
        esito = _scrivi(app, subject_kind="tipo", subject="binary_sensor.occupancy",
                               field="genere", value="presenza", now=lambda: 2.0)
        assert esito["provenienza_istantanea"] == "sapere"
        assert "da" not in esito, "`da` nel listato e' l'origine della RIGA: non si riusa qui"
        stato = app["type_judgments_status"]
        assert set(stato) == {"provenienza_istantanea", "perche", "impronta"}

        response = await server._handle_health(SimpleNamespace(app=app))
        salute = json.loads(response.body)
        assert salute["istantanea"] == stato
        assert "giudizi" not in salute, "`giudizi` e' l'elenco delle righe, non uno stato"

        [riga] = [g for g in judgment_listing(s)
                  if (g["soggetto"], g["campo"]) == ("binary_sensor.occupancy", "genere")]
        assert riga["da"] == "correzione"
    finally:
        s.close()


# ---------------------------------------------------------------------------
# L'archivio che solleva DURANTE la scrittura (giro di correzioni 1, punto 8).
# ---------------------------------------------------------------------------

def test_l_archivio_che_SOLLEVA_scrivendo_diventa_un_rifiuto_dichiarato(tmp_path):
    """Giro di correzioni 1, punto 8 (MEDIO): `knowledge.write` che solleva a
    sapere APERTO non aveva nessuna prova.

    La guardia che c'era copre il sapere **assente** (`knowledge is None` ->
    503); un archivio che c'e' ma non scrive -- disco pieno, `database is
    locked` oltre i 5 secondi di `busy_timeout`, file corrotto -- e' un caso
    diverso e usciva grezzo dalla porta, fino alla rotta, che lo rendeva un
    500 con un corpo HTML che nessun chiamante di questa API sa leggere.

    Ora la porta lo traduce in `JudgmentStoreFailed`, e l'istantanea **non si
    tocca**: una scrittura che non e' avvenuta non puo' cambiare cio' che la
    casa legge.

    Rossa prima della correzione: `sqlite3.OperationalError: disco pieno`
    invece di `JudgmentStoreFailed`.
    """
    import sqlite3

    from hiris.app.mind.judgments import JudgmentStoreFailed

    s, app = _app_seminata(tmp_path)
    giudizi_iniziali = app["type_judgments"]
    stato_iniziale = app["type_judgments_status"]
    try:
        def _rotto(_fact):
            raise sqlite3.OperationalError("disco pieno")

        s.write = _rotto
        with pytest.raises(JudgmentStoreFailed) as preso:
            _scrivi(app, subject_kind="tipo", subject="binary_sensor.occupancy",
                           field="genere", value="presenza", now=lambda: 2.0)
        assert "disco pieno" in str(preso.value)
        assert app["type_judgments"] is giudizi_iniziali
        assert app["type_judgments_status"] is stato_iniziale
    finally:
        s.close()


def test_tornare_al_seme_e_UNA_transazione_sola(tmp_path):
    """Giro di correzioni 1, punto 8 (MEDIO), **prima fondamenta**: «torna al
    seme» era `forget()` e poi `seed()`, due transazioni. Un guasto in mezzo
    lasciava il sapere **senza nessuna delle due righe**: la correzione del
    proprietario cancellata e il seme non rimesso, cioe' il valore che la casa
    legge sparito in silenzio proprio mentre chiedeva di tornare al valore
    normale.

    `KnowledgeStore.forget_and_seed` le fa in una transazione sola: se la
    seconda meta' solleva, si torna indietro e la riga di prima e' ancora li'.

    Rossa prima della correzione: la riga di `light/genere` era sparita
    (`AttributeError: 'NoneType' object has no attribute 'value'`).
    """
    import sqlite3

    s = _sapere(tmp_path)
    try:
        s.write(Fact(subject_kind="tipo", subject="light", field="genere",
                     value="sicurezza", provenance="nostro", who=AUTORE_STORICO,
                     when_ts=2.0))
        seme = Fact(subject_kind="tipo", subject="light", field="genere",
                    value="funzionamento", provenance="nostro", who=SEED_AUTHOR,
                    when_ts=3.0)

        vero = s._seed_one

        def _rotto(fact, priority):
            raise sqlite3.OperationalError("disco pieno")

        s._seed_one = _rotto
        with pytest.raises(sqlite3.OperationalError):
            s.forget_and_seed("tipo", "light", "genere", [seme], priority=REPO_PRIORITY)
        s._seed_one = vero

        rimasta = s.get("tipo", "light", "genere")
        assert rimasta is not None, "la cancellazione deve essere tornata indietro"
        assert rimasta.value == "sicurezza" and rimasta.who == AUTORE_STORICO

        # E quando non solleva, le due meta' si vedono entrambe.
        assert s.forget_and_seed("tipo", "light", "genere", [seme],
                                 priority=REPO_PRIORITY) is True
        tornata = s.get("tipo", "light", "genere")
        assert tornata.value == "funzionamento" and tornata.who == SEED_AUTHOR
    finally:
        s.close()


def test_tornare_al_seme_su_un_campo_che_non_esiste_e_RIFIUTATO(tmp_path):
    """Giro di correzioni 1, punto 8 (BASSO): `value=None` non e' una scorciatoia
    che salta la validazione.

    Il ramo del ritorno al seme esce presto da `_check` -- di proposito, vedi il
    commento li' -- e nessuna prova diceva **fin dove** esce. Sono due cose
    diverse, e vanno fissate insieme:

    - **campo**: rifiutato come per una scrittura qualunque. Un `campo` inventato
      cancellerebbe in silenzio niente e la casa risponderebbe «fatto»;
    - **livello**: ammesso apposta. Una riga scritta a mano dove nessuna domanda
      la legge (`lavoro` su un'entita') la pagina la MOSTRA, e se la porta si
      rifiutasse di toglierla resterebbe li' per sempre -- visibile e
      incancellabile dalla sola via che il proprietario ha.

    Mutazione ESEGUITA: spostare il `return` di `value is None` PRIMA del
    controllo sul campo -- rossa (nessun `JudgmentRefused`); ripristinata con
    l'editor, sha256 identico.
    """
    s, app = _app_seminata(tmp_path)
    try:
        with pytest.raises(JudgmentRefused) as preso:
            _scrivi(app, subject_kind="tipo", subject="light",
                           field="colore_preferito", value=None)
        assert "colore_preferito" in str(preso.value)

        # E il livello non ammesso invece passa: `lavoro` si consulta su coppia
        # e dominio, mai su un'entita' -- ma una riga cosi' si deve poter
        # togliere.
        s.write(Fact(subject_kind="entita", subject="light.salotto", field="lavoro",
                     value='{"on": "accesa"}', provenance="nostro",
                     who=AUTORE_STORICO, when_ts=2.0))
        assert s.get("entita", "light.salotto", "lavoro") is not None
        _scrivi(app, subject_kind="entita", subject="light.salotto",
                       field="lavoro", value=None, now=lambda: 3.0)
        assert s.get("entita", "light.salotto", "lavoro") is None
    finally:
        s.close()


# -- «da sapere subito»: la porta di scrittura (Task 3, spec 2026-09-18-da-sapere-subito.md §5) --
#
# Il rifiuto su un'entita' non ha una prova sua qui: e' gia' la riga
# `("entita", "alarm_control_panel.ingresso", "da_sapere_subito", "si")` in
# `_LIVELLI_MUTI` (sopra, col commento D1), parametrizzata su
# `test_livello_MUTO_rifiutato` -- che verifica in piu' che l'archivio resti
# intatto. Una seconda prova identica, allo stesso livello e con lo stesso
# `match`, sarebbe un doppione.

def test_la_porta_scrive_da_sapere_subito_su_un_dominio_e_su_una_coppia(tmp_path):
    """Spec §5: la porta lo accetta come gli altri campi, senza nessuna riga
    nuova nella porta oltre al livello dichiarato in `_LEVELS`
    (`DA_SAPERE_SUBITO_FIELD: frozenset({"coppia", "dominio"})`) -- che quella
    riga sia OBBLIGATORIA, e non un elenco a parte, lo dimostra
    `test_ogni_giudizio_ha_i_suoi_livelli_dichiarati` qui sotto (`_LEVELS` e
    `JUDGMENT_FIELD_NAMES` devono avere le stesse chiavi)."""
    s, app = _app_seminata(tmp_path)
    try:
        esito = _scrivi(app, subject_kind="tipo", subject="binary_sensor.motion",
                               field="da_sapere_subito", value="si", now=lambda: 5.0)
        assert esito["riga"]["campo"] == "da_sapere_subito"
        assert esito["riga"]["chi"] == "Paolo"
        assert app["type_judgments"].da_sapere_subito("binary_sensor", "motion") is True
        _scrivi(app, subject_kind="tipo", subject="light",
                       field="da_sapere_subito", value="si", now=lambda: 6.0)
        assert app["type_judgments"].da_sapere_subito("light") is True
    finally:
        s.close()


def test_il_SI_basta_il_LAVORO_da_solo_senza_riposo(tmp_path):
    """**Il rifiuto era provato per meta'** (ri-revisione finale, punto 3). La
    condizione e' «senza riposo NE' lavoro»: chi ha solo il lavoro passa, perche'
    il lavoro basta a dire quali stati sono il fatto -- la regola non tocca
    nemmeno il riposo, in quel caso.

    Nessuna prova lo diceva, e il seme non poteva dirlo: tutti e nove i tipi che
    dichiarano un `lavoro` dichiarano **anche** un riposo. La mutazione «il `si`
    esige il riposo e ignora il lavoro» restava quindi VERDE su 117 prove --
    cioe' meta' della condizione non era sorvegliata da niente.

    Mutazione ESEGUITA: `if not current.resting_of(...)` al posto di
    `if not current.resting_of(...) and not current.working_of(...)` -- rossa
    qui (`JudgmentRefused` sulla scrittura del `si`), verde su tutto il resto
    della suite, com'era prima di questa prova. Ripristinata con l'editor.

    `update` e' il tipo che nel seme non ha ne' riposo ne' lavoro: gli si
    scrive PRIMA un lavoro, poi il `si`.
    """
    s, app = _app_seminata(tmp_path)
    try:
        assert not app["type_judgments"].resting_of("update")
        assert not app["type_judgments"].working_of("update")
        _scrivi(app, subject_kind="tipo", subject="update", field="lavoro",
                       value='{"installing": "sta installando un aggiornamento"}',
                       now=lambda: 5.0)
        assert not app["type_judgments"].resting_of("update")  # il riposo resta assente
        _scrivi(app, subject_kind="tipo", subject="update",
                       field="da_sapere_subito", value="si", now=lambda: 6.0)
        assert app["type_judgments"].da_sapere_subito("update") is True
        # E la regola usa il lavoro, senza nessun riposo da consultare.
        assert app["type_judgments"].stato_da_sapere_subito(
            "update", None, "installing") is True
        assert app["type_judgments"].stato_da_sapere_subito("update", None, "off") is False
    finally:
        s.close()


def test_la_porta_scrive_un_ELENCO_di_stati_e_NON_chiede_riposo_ne_lavoro(tmp_path):
    """Terza forma del valore (decisione del proprietario, 18/09/2026): la
    porta la accetta come le altre due, e **il rifiuto «senza riposo ne'
    lavoro» non le si applica**. Per un elenco quella domanda non ha senso:
    l'elenco dice gia' quali stati contano, e non c'e' niente da decidere --
    il rifiuto esiste per il solo `si`, che senza riposo ne' lavoro non sa a
    cosa appoggiarsi.

    `update` e' il tipo usato dalla prova del rifiuto qui sopra proprio perche'
    il seme non gli da' ne' riposo ne' lavoro: con `si` la porta lo respinge,
    con l'elenco lo scrive.

    Mutazione ESEGUITA: allargato il rifiuto di `_check` da `value == "si"` a
    qualunque valore del campo (`value is not None`) -- rossa qui
    (`JudgmentRefused` sulla scrittura dell'elenco), verde sul resto del file.
    Ripristinata con l'editor.
    """
    s, app = _app_seminata(tmp_path)
    try:
        assert not app["type_judgments"].resting_of("update")
        assert not app["type_judgments"].working_of("update")
        esito = _scrivi(app, subject_kind="tipo", subject="update",
                               field="da_sapere_subito", value='["failed"]', now=lambda: 5.0)
        assert esito["riga"]["valore"] == '["failed"]'
        assert app["type_judgments"].da_sapere_subito("update") == frozenset({"failed"})
        assert app["type_judgments"].stato_da_sapere_subito("update", None, "failed") is True
        assert app["type_judgments"].stato_da_sapere_subito("update", None, "idle") is False
    finally:
        s.close()


def test_la_porta_RIFIUTA_un_elenco_di_stati_STORTO(tmp_path):
    """L'elenco vuoto, l'elenco di numeri, l'elenco con una forma dell'assenza:
    la porta li respinge **prima di toccare l'archivio**, con la ragione che
    `_parse_da_sapere_subito` scrive -- nessun ramo nuovo qui, e' la stessa
    `TypeJudgments.from_rows` su una riga sola che valida gli altri campi.

    Mutazione ESEGUITA: tolto il controllo sul vuoto da
    `_parse_da_sapere_subito` -- rossa sulla prima asserzione (nessun
    `JudgmentRefused`: `[]` veniva scritto), e rossa anche su
    `test_type_judgments.py::test_un_elenco_VUOTO_di_stati_da_sapere_subito_si_RIFIUTA`.
    Ripristinata con l'editor.
    """
    s, app = _app_seminata(tmp_path)
    try:
        righe = [(f.subject_kind, f.subject, f.field, f.value) for f in s.judgment_rows()]
        with pytest.raises(JudgmentRefused, match="vuoto"):
            _scrivi(app, subject_kind="tipo", subject="lock",
                           field="da_sapere_subito", value="[]")
        with pytest.raises(JudgmentRefused, match="si/no"):
            _scrivi(app, subject_kind="tipo", subject="lock",
                           field="da_sapere_subito", value="[3]")
        with pytest.raises(JudgmentRefused, match="assenza"):
            _scrivi(app, subject_kind="tipo", subject="lock",
                           field="da_sapere_subito", value='["jammed", "none"]')
        assert [(f.subject_kind, f.subject, f.field, f.value)
                for f in s.judgment_rows()] == righe
    finally:
        s.close()


def test_da_sapere_subito_torna_al_seme_come_gli_altri(tmp_path):
    """`valore: null` rimette la riga del seme se il seme ce l'ha (i sedici
    tipi), la cancella se non ce l'ha. Nessun ramo nuovo: e'
    `knowledge.forget_and_seed`, la stessa transazione sola degli altri campi.
    """
    s, app = _app_seminata(tmp_path)
    try:
        # Un tipo DEL SEME, corretto e poi rimesso: torna «si», non sparisce.
        _scrivi(app, subject_kind="tipo", subject="alarm_control_panel",
                       field="da_sapere_subito", value="no", now=lambda: 5.0)
        assert app["type_judgments"].da_sapere_subito("alarm_control_panel") is False
        _scrivi(app, subject_kind="tipo", subject="alarm_control_panel",
                       field="da_sapere_subito", value=None, now=lambda: 6.0)
        assert app["type_judgments"].da_sapere_subito("alarm_control_panel") is True
        # Un tipo che il seme NON ha: il ritorno al seme la cancella.
        _scrivi(app, subject_kind="tipo", subject="light",
                       field="da_sapere_subito", value="si", now=lambda: 7.0)
        esito = _scrivi(app, subject_kind="tipo", subject="light",
                               field="da_sapere_subito", value=None, now=lambda: 8.0)
        assert esito["riga"] is None
        assert app["type_judgments"].da_sapere_subito("light") is False
    finally:
        s.close()


def test_una_correzione_di_da_sapere_subito_NON_cambia_l_impronta(tmp_path):
    """Spec §6: il campo non entra nella cronaca, quindi correggerlo non fa
    rifare nessun giorno -- a differenza di `genere` e `riposo`, che costano
    fino a due ore di ricostruzione. E' la differenza che la pagina dichiara a
    chi corregge.

    Mutazione da ESEGUIRE: aggiungere il campo a `CHRONICLE_FIELDS` -- rossa
    (ed e' la stessa mutazione del Task 1, vista da un'altra porta: qui
    arrossisce sull'`impronta` che la porta RESTITUISCE).
    """
    s, app = _app_seminata(tmp_path)
    try:
        prima = app["type_judgments_status"]["impronta"]
        esito = _scrivi(app, subject_kind="tipo", subject="light",
                               field="da_sapere_subito", value="si", now=lambda: 5.0)
        assert esito["impronta"] == prima
        # E il contro-caso, che rende la prova discriminante: `genere` la muove.
        dopo = _scrivi(app, subject_kind="tipo", subject="light",
                              field="genere", value="nessuno", now=lambda: 6.0)
        assert dopo["impronta"] != prima
    finally:
        s.close()


def test_ogni_giudizio_ha_i_suoi_livelli_dichiarati():
    """Un campo nuovo in `JUDGMENT_FIELD_NAMES` senza la sua riga in `_LEVELS`
    non e' un rifiuto motivato: e' un KeyError, cioe' un 500 col corpo HTML che
    la pagina non sa leggere. Mutazione ESEGUITA: togliere una riga da
    `_LEVELS` -- rossa."""
    from hiris.app.mind.judgments import _LEVELS
    assert set(_LEVELS) == JUDGMENT_FIELD_NAMES


# ---------------------------------------------------------------------------
# L'IMPALCATURA (decisione del proprietario, 20/09/2026: «hacs non e' qualcosa
# da monitorare»).
#
# Misurato su sette giorni di primo piano (13-19/09): **42 righe, e 12 sono
# Home Assistant che parla di se'** -- HACS (2 errori 404 di GitHub e un
# «riavvio richiesto»), il Supervisor coi timeout sul restart degli add-on, il
# frontend, il websocket, il bluetooth. Le cose di casa -- l'irrigazione ferma,
# l'allarme scattato -- erano la minoranza.
#
# **Il criterio non sta nel codice.** Per un'entita' lo diceva gia' un giudizio
# (`da_sapere_subito`); per una condizione di sistema non lo diceva nessuno, ed
# entravano tutte. Ora lo dice un giudizio sull'INTEGRAZIONE, che la casa
# scrive e corregge da «Cosa ho capito»: `impalcatura`.
# ---------------------------------------------------------------------------

def test_il_seme_dichiara_l_impalcatura_di_home_assistant():
    """Le sei misurate il 20/09/2026. **Il seme non e' un elenco di gusti**:
    ognuna e' comparsa in primo piano in quella settimana.

    Mutazione: togliere una riga dal seme -- rossa."""
    righe = {(soggetto, valore) for genere, soggetto, campo, valore in tv.judgment_seed_rows()
             if genere == "integrazione" and campo == "impalcatura"}

    assert righe == {("frontend", "si"), ("habluetooth", "si"), ("hacs", "si"),
                     ("hassio", "si"), ("homeassistant", "si"), ("websocket_api", "si")}


def test_un_integrazione_che_governa_oggetti_di_casa_NON_e_impalcatura():
    """La contropartita, e senza di lei il seme potrebbe dire «si» a tutti:
    Hydrawise e' l'irrigazione, Alarmo e' l'allarme. Se sparissero dal primo
    piano, la pagina tacerebbe proprio su cio' per cui esiste.

    Mutazione: `impalcatura` che torna vero per assenza -- rossa."""
    giudizi = tv.REPO_JUDGMENTS

    assert giudizi.is_scaffolding("hacs") is True
    assert giudizi.is_scaffolding("hydrawise") is False
    assert giudizi.is_scaffolding("alarmo") is False


def test_impalcatura_su_un_TIPO_e_rifiutata(tmp_path):
    """`impalcatura` vive su un'integrazione e su nient'altro: su `light` non
    la consulterebbe nessuna domanda, e una riga che nessuno legge e' una
    correzione che la casa crede di aver fatto.

    Mutazione: `_LEVELS` che ammette anche il dominio -- rossa."""
    s, app = _app_seminata(tmp_path)
    try:
        with pytest.raises(JudgmentRefused):
            _scrivi(app, subject_kind="tipo", subject="light",
                           field="impalcatura", value="si", now=lambda: 1.0)
    finally:
        s.close()


def test_un_soggetto_integrazione_con_una_forma_che_nessuna_chiave_incontra_e_rifiutato(tmp_path):
    """Il soggetto e' lo SLUG dell'integrazione -- `hacs`, `websocket_api` --
    non il percorso del logger: `custom_components.hacs` sarebbe una riga
    accettata che nessuna chiave incontrera' mai.

    Mutazione: nessun controllo di forma -- rossa."""
    s, app = _app_seminata(tmp_path)
    try:
        with pytest.raises(JudgmentRefused):
            _scrivi(app, subject_kind="integrazione",
                           subject="custom_components.hacs", field="impalcatura",
                           value="si", now=lambda: 1.0)
        # E la forma giusta si scrive: senza questa meta', un controllo che
        # rifiuta TUTTO passerebbe la prova qui sopra.
        _scrivi(app, subject_kind="integrazione", subject="hydrawise",
                       field="impalcatura", value="si", now=lambda: 2.0)
        assert app["type_judgments"].is_scaffolding("hydrawise") is True
    finally:
        s.close()


def test_impalcatura_NON_rifa_la_cronaca():
    """`CHRONICLE_FIELDS` dice quali giudizi obbligano a rifare i giorni
    passati: `impalcatura` si legge quando la pagina legge, quindi cambiarla
    costa una riga e zero ricostruzioni -- la stessa ragione per cui il primo
    piano non si salva.

    Mutazione: aggiungerla a `CHRONICLE_FIELDS` -- rossa (22 giorni da rifare
    per una decisione che con la cronaca non c'entra)."""
    from hiris.app.home_space.type_judgments import CHRONICLE_FIELDS

    assert "impalcatura" not in CHRONICLE_FIELDS
