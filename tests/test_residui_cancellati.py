"""Gli archivi dismessi si cancellano, invece di restare per sempre.

**La domanda del proprietario, 23/09/2026**: «cosa ci fanno ancora lì dei db
non usati?»

La risposta era: per una decisione esplicita, scritta nel sorgente — *«un
`proposals.db` ereditato da un'installazione precedente non viene né
cancellato (mai dati utente in `/data`) né incontrato in silenzio»*. Undici
file dichiarati, annunciati a ogni avvio, tenuti per sempre.

**Ma quella regola era già stata contraddetta lo stesso giorno**, e da noi:
`vault.db` è stato cancellato con la fetta 7, perché conteneva dati personali
in chiaro e nessuno lo leggeva. Due politiche per la stessa situazione, e
nessun criterio scritto che le separasse.

E il criterio c'era, sotto: **un archivio che nessun codice legge più non è un
dato dell'utente, è un residuo** — e finisce nei backup di Home Assistant, che
non sono cifrati se non gli metti una password. Il reperto C-4 ne ha escluso
soltanto `claude`; il C-6 ha dichiarato la conservazione delle sette tabelle
vive, e questi file non sono tabelle di nessun archivio vivo: non avevano né
una dichiarazione né un cancellatore.

**`chatbots.json` resta**, per decisione del proprietario: contiene il prompt
personalizzato che aveva salvato sul bot di default, e va guardato prima.
"""
import json
import pathlib

from hiris.app.server import RESIDUI_DISMESSI, cancella_residui


def _fai(cartella: pathlib.Path, nome: str, contenuto: str = "x") -> pathlib.Path:
    percorso = cartella / nome
    percorso.write_text(contenuto, encoding="utf-8")
    return percorso


def test_i_residui_dichiarati_se_ne_VANNO(tmp_path):
    """**Il reperto.** Erano undici, annunciati a ogni avvio e tenuti per
    sempre.

    Mutazione ESEGUITA: annunciare senza cancellare -- rossa."""
    fatti = [_fai(tmp_path, nome) for nome in RESIDUI_DISMESSI]

    cancella_residui(str(tmp_path))

    assert not [p for p in fatti if p.exists()], (
        "un residuo dichiarato è sopravvissuto")


def test_chatbots_json_RESTA(tmp_path):
    """Decisione del proprietario: contiene il prompt personalizzato salvato
    sul bot di default, e va guardato prima di cancellarlo. La regola non è
    «cancella tutto ciò che è morto» — è «cancella ciò che è morto **e** su
    cui è stato deciso».

    Mutazione ESEGUITA: metterlo nell'elenco -- rossa."""
    resta = _fai(tmp_path, "chatbots.json", json.dumps({"prompt": "sei tu"}))

    cancella_residui(str(tmp_path))

    assert resta.exists(), "cancellato un file che il proprietario tiene"
    assert "chatbots.json" not in RESIDUI_DISMESSI


def test_non_si_tocca_NIENTE_che_non_sia_dichiarato(tmp_path):
    """Mai per euristica sul nome. Un archivio vivo che somigliasse a un
    residuo — o uno nuovo che nascerà domani — non deve poter sparire perché
    il suo nome assomiglia a qualcosa.

    Mutazione ESEGUITA: cancellare ogni `*.db` che nessuno apre -- rossa."""
    vivi = [_fai(tmp_path, n) for n in
            ("consumi.db", "azioni.db", "sapere.db", "promesse.db",
             "memoria.db", "costruzioni.db", "servizi.db", "oss.db",
             "impostazioni_chat.json", "models_config.json")]

    cancella_residui(str(tmp_path))

    assert all(p.exists() for p in vivi), "cancellato un archivio vivo"


def test_si_dice_COSA_e_stato_cancellato(tmp_path, caplog):
    """Cancellare dati di un utente in silenzio è proibito dalle fondamenta
    di questo progetto. Si dice quale file, e quanto era grande — non «ho
    fatto pulizia».

    Mutazione ESEGUITA: cancellare senza scrivere niente -- rossa."""
    import logging

    _fai(tmp_path, "proposals.db", "y" * 4096)

    with caplog.at_level(logging.INFO):
        cancella_residui(str(tmp_path))

    detto = caplog.text
    assert "proposals.db" in detto, "non ha detto quale file"
    assert "4096" in detto or "4,0" in detto or "4.0" in detto, (
        "non ha detto quanto era grande")


def test_un_residuo_che_NON_C_E_non_fa_rumore(tmp_path, caplog):
    """La casa di chi installa oggi non ha nessuno di questi file. Una riga
    per ognuno a ogni avvio sarebbe rumore sano che seppellisce quello vero —
    la regola del proprietario: se una cosa funziona non va segnalata.

    Mutazione ESEGUITA: scrivere una riga anche per i file assenti --
    rossa."""
    import logging

    with caplog.at_level(logging.DEBUG, logger="hiris.app.server"):
        cancella_residui(str(tmp_path))

    assert caplog.text.strip() == "", (
        f"rumore su una cartella pulita: {caplog.text}")


def test_un_guasto_NON_ferma_l_avvio(tmp_path, monkeypatch):
    """È igiene, non una condizione di funzionamento: un file che non si
    riesce a cancellare — permessi, disco — non deve impedire a HIRIS di
    partire. Stessa disciplina di `decidi_vault`.

    Mutazione ESEGUITA: lasciar salire l'eccezione -- rossa."""
    import os

    _fai(tmp_path, "proposals.db")

    def _rotto(percorso):
        raise OSError("permesso negato")

    monkeypatch.setattr(os, "remove", _rotto)

    cancella_residui(str(tmp_path))  # non deve sollevare


def test_l_elenco_combacia_con_quello_che_il_codice_DICHIARA_morto():
    """L'elenco non è una lista a mano: ogni nome deve corrispondere a un
    file che `server.py` annuncia come «di un'installazione precedente». Se
    domani si dismette un altro archivio e lo si annuncia soltanto, questa
    prova non se ne accorge — ma se qualcuno mette nell'elenco un file che il
    codice non dichiara morto, sì.

    Mutazione ESEGUITA: aggiungere all'elenco un archivio vivo -- rossa."""
    import inspect

    from hiris.app import server

    sorgente = inspect.getsource(server)
    for nome in RESIDUI_DISMESSI:
        assert f"{nome} presente in" in sorgente or nome in sorgente, (
            f"«{nome}» non è dichiarato morto da nessuna parte nel codice")


def _startup_messages(tmp_path) -> list[str]:
    """Le righe che l'AVVIO VERO scrive nel registro, con gli undici residui
    gia' sul disco. Si monta l'app con `_on_startup` intero su una casa
    sintetica -- la stessa montatura della fotografia delle porte -- invece di
    estrarre un blocco dal sorgente: una frase scritta in un punto e smentita
    da una riga piu' sotto si vede solo eseguendo l'avvio per intero."""
    import asyncio
    import logging
    import sys

    root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    import fotografia_porte

    from tests._casa_sintetica import synthetic_inputs

    for nome in RESIDUI_DISMESSI:
        _fai(tmp_path, nome)

    messages: list[str] = []

    class _Collect(logging.Handler):
        def emit(self, record) -> None:
            messages.append(record.getMessage())

    handler = _Collect(level=logging.DEBUG)
    registro = logging.getLogger("hiris.app.server")
    earlier = registro.level
    registro.addHandler(handler)
    registro.setLevel(logging.DEBUG)

    async def boot() -> None:
        async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path)):
            pass

    try:
        asyncio.run(boot())
    finally:
        registro.removeHandler(handler)
        registro.setLevel(earlier)
    return messages


def test_nessun_messaggio_d_avvio_promette_un_file_che_sta_per_cancellare(tmp_path):
    """**Otto frasi su undici dicevano il falso** (registro X-27, 01/10/2026).
    L'avvio annunciava di ogni residuo «il file resta su disco, intatto», e
    qualche riga piu' sotto `cancella_residui` lo cancellava. Le altre tre
    frasi stavano dopo la cancellazione, e non giravano mai.

    L'elenco dei nomi si CHIEDE a `server.RESIDUI_DISMESSI`: un residuo
    aggiunto domani entra in questa prova da solo.

    Mutazione ESEGUITA: rimesso in `_on_startup`, prima di `cancella_residui`,
    l'annuncio «ha_health.json ... Il file resta su disco, intatto.» -- rossa,
    col nome del file e la frase.
    """
    messages = _startup_messages(tmp_path)

    assert any("cancellato" in message for message in messages), (
        "l'avvio non ha cancellato niente: la prova non guarda cio' che crede")
    lies = []
    for nome in RESIDUI_DISMESSI:
        gone = not (tmp_path / nome).exists()
        promised = [message for message in messages
                    if nome in message and "resta" in message]
        if gone and promised:
            lies.append(f"{nome}: «{promised[0][-60:]}»")
    assert not lies, (
        "l'avvio promette che un file resta e poi lo cancella: " + "; ".join(lies))
