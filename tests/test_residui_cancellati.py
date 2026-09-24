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
