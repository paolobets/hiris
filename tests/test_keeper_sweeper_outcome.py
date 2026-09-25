"""L'esito torna a chi ha chiesto (fetta «il seguito delle chat divise», Task 3).

Spec `docs/design/2026-09-26-il-seguito-delle-chat-divise.md` §2.4 e i
vincoli 3.1-3.9 di `security-constraints.md`: quando una promessa si conclude,
l'esito diventa un messaggio di HIRIS nel filo di chi l'ha chiesta -- e in
nessun altro -- e, per un `chiedi` che ha qualcosa da dire, una push a ogni
servizio del suo recapito, risolto AL RISVEGLIO dal filo (mai dal nome, mai
dal modello).

Le prove guardano il FATTO: cio' che sta nella cronologia vera
(`chat_store`, su un disco temporaneo), le chiamate arrivate alla porta, il
motivo scritto nell'archivio delle promesse.
"""
from __future__ import annotations

import logging
import os

import pytest

from hiris.app.chat_store import (
    _get_store,
    append_assistant_line,
    close_all_stores,
    load_history,
)
from hiris.app.chat_thread import ChatThread
from hiris.app.keeper.promise import (
    DELIVERY_TITLE,
    MAX_SERVICES_PER_PROMISE,
    PUSH_MESSAGE_CAP,
    REASON_CAP,
)
from hiris.app.keeper.recipient import _REASON_LINK_PERSON, Recipients
from hiris.app.keeper.store import AgendaStore
from hiris.app.keeper.sweeper import Sweeper

ADESSO = 1_755_600_000.0
PAOLO = ChatThread("persona:paolo", "pannello")
MARTA = ChatThread("persona:marta", "pannello")
FRASE_CHIEDI = "fra un'ora verifica la temperatura"
FRASE_FAI = "alle 17 accendi lo studio"
TRONCATO = "[troncato]"

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def reset_stores():
    close_all_stores()
    yield
    close_all_stores()


@pytest.fixture()
def archivio(tmp_path):
    a = AgendaStore(os.path.join(str(tmp_path), "promesse.db"))
    yield a
    a.close()


@pytest.fixture()
def cartella(tmp_path):
    d = tmp_path / "chat"
    d.mkdir()
    return str(d)


class PortaFinta:
    """La porta unica: registra ogni chiamata e sa fallire su un servizio."""

    def __init__(self, *, fallisce=(), solleva=()):
        self.chiamate = []
        self.soggetti = []
        self._fallisce = set(fallisce)
        self._solleva = set(solleva)

    async def __call__(self, chiamata, *, actor, subject=None):
        self.chiamate.append((chiamata, actor))
        self.soggetti.append(subject)
        servizio = chiamata.get("servizio")
        if servizio in self._solleva:
            raise RuntimeError("la rete e' caduta")
        if servizio in self._fallisce:
            return {"eseguito": False, "errore": "il servizio non ha risposto"}
        return {"eseguito": True, "esecuzione_id": "e1"}


class TurnoFinto:
    def __init__(self, answer):
        self._answer = answer

    async def __call__(self, promessa):
        return self._answer


class RecapitoFinto:
    """`recipients_for` ridotto a cio' che l'orologio ne vede: un soggetto
    in ingresso, un `Recipients` in uscita. Registra CHI gli e' stato
    chiesto -- la prova che il recapito si risolve dal filo, al risveglio."""

    def __init__(self, services=(), reason=None):
        self.soggetti = []
        self._esito = Recipients(tuple(services), reason)

    async def __call__(self, subject):
        self.soggetti.append(subject)
        return self._esito


class SoffittoFinto:
    def __init__(self, comandare=True, perche=None):
        self.soggetti = []
        self._esito = {"leggere": True, "comandare": comandare,
                       "costruire": False, "ruolo": "utente", "perche": perche}

    async def __call__(self, subject):
        self.soggetti.append(subject)
        return self._esito


def _orologio(archivio, cartella, *, porta=None, turno=None, recapito=None,
              soffitto=None):
    return Sweeper(
        archivio,
        execute=porta or PortaFinta(),
        interpreta=turno or TurnoFinto({"avvisare": False, "testo": "tutto fermo"}),
        recipients=recapito or RecapitoFinto(),
        write_to_thread=lambda thread, content, quoted=None: append_assistant_line(
            content, cartella, thread=thread, quoted=quoted),
        ceiling=soffitto or SoffittoFinto(),
    )


def _crea_chiedi(archivio, thread=PAOLO):
    return archivio.create({
        "specie": "chiedi", "frase": FRASE_CHIEDI, "quando_ts": ADESSO + 10,
        "domanda": "e' aumentata?",
    }, thread=thread, now=ADESSO)["promessa"]["id"]


def _crea_fai(archivio, thread=PAOLO):
    return archivio.create({
        "specie": "fai", "frase": FRASE_FAI, "quando_ts": ADESSO + 10,
        "chiamata": {"servizio": "light.turn_on",
                     "bersaglio": {"entita": ["light.studio"]}},
    }, thread=thread, now=ADESSO)["promessa"]["id"]


def _semina_orfana(archivio, verb="chiedi"):
    """Una promessa nata prima delle promesse divise, mai adottata: senza filo."""
    if verb == "chiedi":
        archivio._conn.execute(
            "INSERT INTO promesse(id,specie,frase,quando_ts,domanda,stato,nata_ts) "
            "VALUES('orfana','chiedi','detta prima',?,'?','in_attesa',?)",
            (ADESSO + 10, ADESSO))
    else:
        archivio._conn.execute(
            "INSERT INTO promesse(id,specie,frase,quando_ts,chiamata_json,stato,nata_ts) "
            "VALUES('orfana','fai','detta prima',?,?,'in_attesa',?)",
            (ADESSO + 10, ('{"servizio": "light.turn_on", "bersaglio": '
                           '{"entita": ["light.studio"]}}'), ADESSO))
    archivio._conn.commit()
    return "orfana"


def _chat_rows(cartella):
    conn = _get_store(cartella)._conn
    sessioni = conn.execute(
        "SELECT subject_key, entry_point FROM chat_sessions").fetchall()
    messaggi = conn.execute("SELECT role, content FROM chat_messages").fetchall()
    return [tuple(s) for s in sessioni], [tuple(m) for m in messaggi]


# ---------------------------------------------------------------------------
# chiedi: il messaggio nel filo, la push al recapito
# ---------------------------------------------------------------------------


async def test_l_esito_di_paolo_entra_nel_filo_di_paolo_e_non_in_quello_di_marta(
        archivio, cartella):
    """3.2: esattamente UN messaggio `assistant` nella conversazione attiva di
    Paolo, che nomina la promessa (la frase di allora) e porta l'esito; nel
    filo di Marta niente."""
    _crea_chiedi(archivio)
    porta = PortaFinta()
    recapito = RecapitoFinto(["notify.mobile_app_iphone_bet"])
    turno = TurnoFinto({"avvisare": True, "testo": "e' salita di 2 gradi"})

    await _orologio(archivio, cartella, porta=porta, turno=turno,
                    recapito=recapito).batti(ADESSO + 11)

    paolo_rows = load_history(cartella, thread=PAOLO)
    assert len(paolo_rows) == 1
    assert paolo_rows[0]["role"] == "assistant"
    assert FRASE_CHIEDI in paolo_rows[0]["content"]
    assert "e' salita di 2 gradi" in paolo_rows[0]["content"]
    assert load_history(cartella, thread=MARTA) == []
    sessioni, _ = _chat_rows(cartella)
    assert sessioni == [("persona:paolo", "pannello")]


async def test_la_push_parte_per_ogni_servizio_del_recapito_con_la_forma_unica(
        archivio, cartella):
    """3.1: una chiamata per servizio, dalla porta, con la forma di
    `delivery_call` -- `dati` esattamente {message, title}, bersaglio vuoto."""
    ident = _crea_chiedi(archivio)
    porta = PortaFinta()
    recapito = RecapitoFinto(["notify.mobile_app_iphone_bet",
                              "notify.mobile_app_ipad_mini"])
    turno = TurnoFinto({"avvisare": True, "testo": "e' salita di 2 gradi"})

    await _orologio(archivio, cartella, porta=porta, turno=turno,
                    recapito=recapito).batti(ADESSO + 11)

    assert [c["servizio"] for c, _ in porta.chiamate] == [
        "notify.mobile_app_iphone_bet", "notify.mobile_app_ipad_mini"]
    for chiamata, attore in porta.chiamate:
        assert attore == "schedulatore"
        assert chiamata["bersaglio"] == {}
        assert set(chiamata["dati"]) == {"message", "title"}
        assert chiamata["dati"]["title"] == DELIVERY_TITLE
        assert chiamata["dati"]["message"] == "e' salita di 2 gradi"
    # La cronaca della push nomina chi l'aveva chiesta, come quella di un fai.
    assert porta.soggetti == [{"specie": "persona", "id": "paolo"}] * 2
    p = archivio.read(ident)
    assert (p["stato"], p["motivo"]) == ("mantenuta", None)


async def test_il_recapito_si_risolve_al_risveglio_dal_filo_senza_nome(
        archivio, cartella):
    """3.3: il soggetto che arriva al recapito e' ricostruito dal filo --
    specie e id -- e la domanda si fa quando la promessa si sveglia, non
    quando nasce."""
    _crea_chiedi(archivio)
    recapito = RecapitoFinto(["notify.mobile_app_iphone_bet"])
    assert recapito.soggetti == []  # alla nascita nessuno lo ha chiesto

    await _orologio(archivio, cartella, recapito=recapito,
                    turno=TurnoFinto({"avvisare": True, "testo": "fa caldo"}),
                    ).batti(ADESSO + 11)

    assert recapito.soggetti == [{"specie": "persona", "id": "paolo"}]


async def test_zero_servizi_niente_push_e_il_motivo_e_quello_del_recapito(
        archivio, cartella):
    """Il motivo registrato e' quello di `Recipients.reason` (Task 1), non una
    frase inventata qui; il messaggio nel filo c'e' lo stesso."""
    ident = _crea_chiedi(archivio)
    porta = PortaFinta()
    recapito = RecapitoFinto([], _REASON_LINK_PERSON)

    await _orologio(archivio, cartella, porta=porta, recapito=recapito,
                    turno=TurnoFinto({"avvisare": True, "testo": "fa caldo"}),
                    ).batti(ADESSO + 11)

    assert porta.chiamate == []
    p = archivio.read(ident)
    assert p["stato"] == "mantenuta"
    assert p["motivo"] == _REASON_LINK_PERSON
    assert len(load_history(cartella, thread=PAOLO)) == 1


async def test_senza_niente_da_dire_scrive_nel_filo_e_non_disturba(archivio, cartella):
    """`avvisare=false`: l'esito e' comunque la risposta a cio' che Paolo ha
    chiesto, e va nella sua chat; nessuna push, e il recapito non si chiede
    nemmeno."""
    ident = _crea_chiedi(archivio)
    porta = PortaFinta()
    recapito = RecapitoFinto(["notify.mobile_app_iphone_bet"])

    await _orologio(archivio, cartella, porta=porta, recapito=recapito,
                    turno=TurnoFinto({"avvisare": False,
                                      "testo": "non e' cambiata: 21,4 gradi"}),
                    ).batti(ADESSO + 11)

    assert porta.chiamate == []
    assert recapito.soggetti == []
    assert "21,4" in load_history(cartella, thread=PAOLO)[0]["content"]
    assert archivio.read(ident)["motivo"] is None


async def test_un_orfana_non_scrive_in_nessun_filo_e_dice_perche(archivio, cartella):
    """3.2: nessun filo inventato -- nessuna riga nella cronologia, nessuna
    sessione `nessuno:-` -- nessuna push, e il motivo lo dichiara."""
    ident = _semina_orfana(archivio)
    porta = PortaFinta()
    recapito = RecapitoFinto(["notify.mobile_app_iphone_bet"])

    await _orologio(archivio, cartella, porta=porta, recapito=recapito,
                    turno=TurnoFinto({"avvisare": True, "testo": "fa caldo"}),
                    ).batti(ADESSO + 11)

    assert _chat_rows(cartella) == ([], [])
    assert porta.chiamate == []
    assert recapito.soggetti == []
    p = archivio.read(ident)
    assert p["stato"] == "mantenuta"
    assert "non è mai stata adottata" in p["motivo"]


async def test_la_push_e_troncata_con_un_tetto_dichiarato_la_chat_no(archivio, cartella):
    """3.1 e (12) dei non pinnati: un testo lungo arriva al telefono tagliato
    al tetto, col marcatore; nella chat resta intero."""
    _crea_chiedi(archivio)
    porta = PortaFinta()
    lungo = "x" * 5000

    await _orologio(archivio, cartella, porta=porta,
                    recapito=RecapitoFinto(["notify.mobile_app_iphone_bet"]),
                    turno=TurnoFinto({"avvisare": True, "testo": lungo}),
                    ).batti(ADESSO + 11)

    messaggio = porta.chiamate[0][0]["dati"]["message"]
    assert len(messaggio) <= PUSH_MESSAGE_CAP
    assert messaggio.endswith(TRONCATO)
    assert lungo in load_history(cartella, thread=PAOLO)[0]["content"]


async def test_al_piu_tre_servizi_per_promessa(archivio, cartella):
    """Ruling 3.4: il tetto per risveglio e' dichiarato, e regge."""
    assert MAX_SERVICES_PER_PROMISE == 3
    _crea_chiedi(archivio)
    porta = PortaFinta()
    cinque = [f"notify.mobile_app_telefono_{n}" for n in range(5)]

    await _orologio(archivio, cartella, porta=porta,
                    recapito=RecapitoFinto(cinque),
                    turno=TurnoFinto({"avvisare": True, "testo": "fa caldo"}),
                    ).batti(ADESSO + 11)

    assert [c["servizio"] for c, _ in porta.chiamate] == cinque[:3]


async def test_lo_stesso_servizio_due_volte_riceve_una_push_sola(archivio, cartella):
    """Extra 5: anche se un recapito portasse un doppione, il telefono non
    riceve due notifiche per un esito."""
    _crea_chiedi(archivio)
    porta = PortaFinta()
    doppio = ["notify.mobile_app_iphone_bet", "notify.mobile_app_iphone_bet"]

    await _orologio(archivio, cartella, porta=porta,
                    recapito=RecapitoFinto(doppio),
                    turno=TurnoFinto({"avvisare": True, "testo": "fa caldo"}),
                    ).batti(ADESSO + 11)

    assert [c["servizio"] for c, _ in porta.chiamate] == ["notify.mobile_app_iphone_bet"]


@pytest.mark.parametrize("guasto", ["fallisce", "solleva"])
async def test_un_servizio_che_fallisce_si_dichiara_e_gli_altri_partono(
        archivio, cartella, guasto):
    """3.5: tre servizi, il secondo fallisce -> tre chiamate (nessuna
    deviazione altrove), e il motivo nomina il secondo."""
    ident = _crea_chiedi(archivio)
    tre = ["notify.mobile_app_a", "notify.mobile_app_b", "notify.mobile_app_c"]
    porta = PortaFinta(**{guasto: ["notify.mobile_app_b"]})

    await _orologio(archivio, cartella, porta=porta,
                    recapito=RecapitoFinto(tre),
                    turno=TurnoFinto({"avvisare": True, "testo": "fa caldo"}),
                    ).batti(ADESSO + 11)

    assert [c["servizio"] for c, _ in porta.chiamate] == tre
    p = archivio.read(ident)
    assert p["stato"] == "mantenuta"
    assert "notify.mobile_app_b" in p["motivo"]
    assert "notify.mobile_app_a" not in p["motivo"]
    assert "notify.mobile_app_c" not in p["motivo"]


async def test_un_testo_velenoso_non_entra_nella_chat(archivio, cartella):
    """3.2: il filtro dei turni velenosi vale anche per l'esito -- una
    sentinella d'errore tornerebbe al modello a ogni turno."""
    _crea_chiedi(archivio)

    await _orologio(archivio, cartella,
                    turno=TurnoFinto({"avvisare": False,
                                      "testo": "Rate limit — riprova tra poco."}),
                    ).batti(ADESSO + 11)

    assert load_history(cartella, thread=PAOLO) == []


async def test_i_log_della_consegna_non_portano_il_testo_ne_la_frase(
        archivio, cartella, caplog):
    """3.6: nei log id e conteggi, mai il testo del modello o la frase."""
    _crea_chiedi(archivio)
    caplog.set_level(logging.DEBUG, logger="hiris")

    await _orologio(archivio, cartella,
                    porta=PortaFinta(fallisce=["notify.mobile_app_b"]),
                    recapito=RecapitoFinto(["notify.mobile_app_a",
                                            "notify.mobile_app_b"]),
                    turno=TurnoFinto({"avvisare": True,
                                      "testo": "SEGRETO-DEL-TESTO"}),
                    ).batti(ADESSO + 11)

    assert "SEGRETO-DEL-TESTO" not in caplog.text
    assert FRASE_CHIEDI not in caplog.text


async def test_un_turno_fallito_lascia_una_riga_breve_nel_filo_e_nessuna_push(
        archivio, cartella):
    ident = _crea_chiedi(archivio)
    porta = PortaFinta()
    recapito = RecapitoFinto(["notify.mobile_app_a"])

    await _orologio(archivio, cartella, porta=porta, recapito=recapito,
                    turno=TurnoFinto({"errore": "il modello non ha risposto."}),
                    ).batti(ADESSO + 11)

    assert archivio.read(ident)["stato"] == "fallita"
    righe = load_history(cartella, thread=PAOLO)
    assert len(righe) == 1
    assert FRASE_CHIEDI in righe[0]["content"]
    assert "non si è potuta mantenere" in righe[0]["content"]
    assert porta.chiamate == []
    assert recapito.soggetti == []


async def test_una_promessa_saltata_lo_dice_nel_filo(archivio, cartella):
    ident = _crea_chiedi(archivio)

    await _orologio(archivio, cartella).batti(ADESSO + 10 + 10_000)

    assert archivio.read(ident)["stato"] == "saltata"
    righe = load_history(cartella, thread=PAOLO)
    assert len(righe) == 1 and "non si è potuta mantenere" in righe[0]["content"]


async def test_un_guasto_imprevisto_lo_dice_nel_filo_senza_il_testo_dell_eccezione(
        archivio, cartella):
    ident = _crea_chiedi(archivio)

    async def raising_turn(_promessa):
        raise RuntimeError("DETTAGLIO-INTERNO")

    await _orologio(archivio, cartella,
                    turno=raising_turn).batti(ADESSO + 11)

    assert archivio.read(ident)["stato"] == "fallita"
    righe = load_history(cartella, thread=PAOLO)
    assert len(righe) == 1
    assert "DETTAGLIO-INTERNO" not in righe[0]["content"]


# ---------------------------------------------------------------------------
# fai: il racconto, e il soffitto rivalutato al risveglio
# ---------------------------------------------------------------------------


async def test_un_fai_mantenuto_si_racconta_nel_filo_senza_push(archivio, cartella):
    _crea_fai(archivio)
    porta = PortaFinta()
    recapito = RecapitoFinto(["notify.mobile_app_a"])

    await _orologio(archivio, cartella, porta=porta,
                    recapito=recapito).batti(ADESSO + 11)

    assert [c["servizio"] for c, _ in porta.chiamate] == ["light.turn_on"]
    assert recapito.soggetti == []
    righe = load_history(cartella, thread=PAOLO)
    assert len(righe) == 1
    assert righe[0]["role"] == "assistant"
    assert FRASE_FAI in righe[0]["content"]


async def test_il_racconto_di_un_fai_fallito_ha_l_errore_tagliato(archivio, cartella):
    """3.7: il racconto e' composto da campi limitati -- l'errore della porta
    entra tagliato al tetto dichiarato, col marcatore."""
    _crea_fai(archivio)

    class PortaCheFallisceLungo(PortaFinta):
        async def __call__(self, chiamata, *, actor, subject=None):
            return {"eseguito": False, "errore": "e" * 5000}

    await _orologio(archivio, cartella,
                    porta=PortaCheFallisceLungo()).batti(ADESSO + 11)

    contenuto = load_history(cartella, thread=PAOLO)[0]["content"]
    assert TRONCATO in contenuto
    assert "e" * REASON_CAP not in contenuto
    assert len(contenuto) < REASON_CAP + 200


async def test_un_fai_di_chi_non_puo_piu_comandare_non_si_esegue(archivio, cartella):
    """Extra 2: il soffitto si rivaluta al risveglio. Chi e' stato declassato
    dopo la nascita non comanda la casa a scadenza: la promessa fallisce col
    `perche` del soffitto e la porta non vede niente."""
    ident = _crea_fai(archivio)
    porta = PortaFinta()
    soffitto = SoffittoFinto(comandare=False, perche="PERCHE-DEL-SOFFITTO")

    await _orologio(archivio, cartella, porta=porta,
                    soffitto=soffitto).batti(ADESSO + 11)

    assert porta.chiamate == []
    assert soffitto.soggetti == [{"specie": "persona", "id": "paolo"}]
    p = archivio.read(ident)
    assert (p["stato"], p["motivo"]) == ("fallita", "PERCHE-DEL-SOFFITTO")
    assert "PERCHE-DEL-SOFFITTO" in load_history(cartella, thread=PAOLO)[0]["content"]


async def test_un_fai_orfano_non_si_esegue(archivio, cartella):
    ident = _semina_orfana(archivio, "fai")
    porta = PortaFinta()
    soffitto = SoffittoFinto()

    await _orologio(archivio, cartella, porta=porta,
                    soffitto=soffitto).batti(ADESSO + 11)

    assert porta.chiamate == []
    assert soffitto.soggetti == []
    p = archivio.read(ident)
    assert p["stato"] == "fallita"
    assert "non è mai stata adottata" in p["motivo"]
    assert _chat_rows(cartella) == ([], [])


# ---------------------------------------------------------------------------
# Il soffitto al risveglio (extra 2): dal soggetto ricostruito {"specie","id"}
# ---------------------------------------------------------------------------


class _UtentiHA:
    def __init__(self, utenti):
        self._utenti = utenti

    async def users(self):
        return {"utenti": self._utenti}


def _app_with_ceiling(tmp_path, *, utenti=()):
    from hiris.app.api.servizi import ServiziStore
    from hiris.app.api.soffitto import prepara_ruoli

    app = {"ha_client": _UtentiHA(list(utenti)),
           "servizi": ServiziStore(str(tmp_path / "servizi.db"))}
    prepara_ruoli(app)
    return app


def _approva(app, nome, chiave, *, ruolo, specie="luogo"):
    app["servizi"].presenta(nome=nome, chiave=chiave, indirizzo="1.2.3.4",
                            now_ts=ADESSO)
    assert app["servizi"].approva(chiave, ruolo=ruolo, specie=specie, now_ts=ADESSO)


async def test_al_risveglio_una_persona_amministratrice_comanda_come_prima(tmp_path):
    from hiris.app.api.soffitto import ceiling_at_wake

    app = _app_with_ceiling(tmp_path, utenti=[{"id": "paolo", "amministratore": True}])
    try:
        soffitto = await ceiling_at_wake(app, {"specie": "persona", "id": "paolo"})
        assert soffitto["comandare"] is True
    finally:
        app["servizi"].close()


async def test_al_risveglio_il_ruolo_di_un_servizio_si_rilegge_dall_archivio(tmp_path):
    """Il soggetto ricostruito dal filo non porta il ruolo: si rilegge dal
    servizio approvato, per nome. Declassato dopo la nascita -> non comanda."""
    from hiris.app.api.soffitto import ceiling_at_wake

    app = _app_with_ceiling(tmp_path)
    try:
        _approva(app, "pannello-cucina", "k1", ruolo="utente")
        prima = await ceiling_at_wake(app, {"specie": "luogo", "id": "pannello-cucina"})
        assert prima["comandare"] is True

        assert app["servizi"].approva("k1", ruolo="lettore", specie="luogo",
                                      now_ts=ADESSO + 1)
        dopo = await ceiling_at_wake(app, {"specie": "luogo", "id": "pannello-cucina"})
        assert dopo["comandare"] is False
        assert dopo["perche"]
    finally:
        app["servizi"].close()


@pytest.mark.parametrize("caso", ["revocato", "sconosciuto", "ambiguo", "senza_archivio"])
async def test_al_risveglio_un_servizio_che_non_si_sa_non_comanda(tmp_path, caso):
    """Fail closed: se il ruolo non si puo' sapere con certezza, niente
    azioni sulla casa a scadenza."""
    from hiris.app.api.soffitto import ceiling_at_wake

    app = _app_with_ceiling(tmp_path)
    try:
        if caso == "revocato":
            _approva(app, "pannello", "k1", ruolo="amministratore")
            app["servizi"].revoca("k1", now_ts=ADESSO + 1)
        elif caso == "ambiguo":
            _approva(app, "pannello", "k1", ruolo="amministratore")
            _approva(app, "pannello", "k2", ruolo="lettore")
        subject = {"specie": "luogo", "id": "pannello"}
        if caso == "senza_archivio":
            app["servizi"].close()
            app = {**app, "servizi": None}
            soffitto = await ceiling_at_wake(app, subject)
        else:
            soffitto = await ceiling_at_wake(app, subject)
        assert soffitto["comandare"] is False
    finally:
        if app.get("servizi") is not None:
            app["servizi"].close()


async def test_al_risveglio_il_ruolo_portato_dal_soggetto_non_vale(tmp_path):
    """Il ruolo non viaggia col soggetto ricostruito: se qualcuno ce lo
    mettesse, conta l'archivio."""
    from hiris.app.api.soffitto import ceiling_at_wake

    app = _app_with_ceiling(tmp_path)
    try:
        _approva(app, "pannello", "k1", ruolo="lettore")
        soffitto = await ceiling_at_wake(
            app, {"specie": "luogo", "id": "pannello", "ruolo": "amministratore"})
        assert soffitto["comandare"] is False
    finally:
        app["servizi"].close()


# ---------------------------------------------------------------------------
# Ruling 3.9: una conversazione aperta da un esito non ha una frase dell'utente
# ---------------------------------------------------------------------------


def test_una_conversazione_con_solo_l_esito_ha_il_titolo_dichiarato(cartella):
    from hiris.app.chat_store import (
        OUTCOME_ONLY_TITLE,
        conversation_title,
    )

    assert OUTCOME_ONLY_TITLE == "Esito di una promessa"
    assert append_assistant_line("Esito della promessa «x»: fatto", cartella,
                                 thread=PAOLO) is True
    righe = load_history(cartella, thread=PAOLO)
    assert conversation_title(righe) == OUTCOME_ONLY_TITLE
    # Nessun turno utente inventato: la conversazione e' l'esito e basta.
    assert [r["role"] for r in righe] == ["assistant"]
    assert conversation_title(righe + [{"role": "user", "content": "grazie mille"}]) \
        == "grazie mille"


async def test_al_risveglio_senza_soggetto_non_si_comanda(tmp_path):
    from hiris.app.api.soffitto import ceiling_at_wake

    app = _app_with_ceiling(tmp_path)
    try:
        assert (await ceiling_at_wake(app, None))["comandare"] is False
        assert (await ceiling_at_wake(app, {}))["comandare"] is False
    finally:
        app["servizi"].close()


@pytest.mark.parametrize("come", ["saltata", "turno_fallito", "guasto"])
async def test_un_orfana_che_fallisce_non_scrive_in_nessun_filo(archivio, cartella, come):
    """3.2 anche sui fallimenti: nessun filo inventato per dire che non e'
    andata (mutazione eseguita: un `_tell` che ripiega su un filo
    `nessuno:-` fa diventare rosso questo test)."""
    ident = _semina_orfana(archivio)

    async def raising_turn(_promessa):
        raise RuntimeError("guasto")

    turno = {"turno_fallito": TurnoFinto({"errore": "il modello non ha risposto."}),
             "guasto": raising_turn}.get(come)
    istante = ADESSO + 10 + (10_000 if come == "saltata" else 1)

    await _orologio(archivio, cartella, turno=turno).batti(istante)

    assert archivio.read(ident)["stato"] in ("saltata", "fallita")
    assert _chat_rows(cartella) == ([], [])
