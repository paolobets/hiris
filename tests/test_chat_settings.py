"""fetta E4 Task 4 ("un bot solo"): `ChatSettings` sostituisce l'entita'
Chatbot. Il punto non e' solo lo shape -- e' che "mancare" non e' piu' uno
stato rappresentabile: `carica()` non solleva mai e non restituisce mai
`None`, a differenza di `engine.get_default_chatbot()` che poteva restituire
`None` se il seed non era mai girato (il degrado silenzioso che questo task
chiude, vedi handlers_chat.py)."""
import json

import pytest

from hiris.app.chat_settings import DEFAULT_SYSTEM_PROMPT, ChatSettings


def test_default_e_completo_senza_argomenti():
    imp = ChatSettings()
    assert imp.name == "HIRIS"
    assert imp.system_prompt == DEFAULT_SYSTEM_PROMPT
    assert imp.response_mode == "auto"
    assert imp.thinking_budget == 0
    assert imp.max_chat_turns == 0
    assert imp.restrict_to_home is False


def test_carica_senza_file_restituisce_i_default_nel_codice(tmp_path):
    """Nessun file sul disco -- il caso che prima faceva degradare
    handlers_chat.py: qui non solleva, non restituisce None, produce gli
    stessi default di `ChatSettings()`."""
    imp = ChatSettings.load(str(tmp_path))
    assert imp == ChatSettings()


def test_salva_poi_carica_ritorna_gli_stessi_valori(tmp_path):
    originale = ChatSettings(
        name="Casa",
        system_prompt="Sei utile e conciso.",
        response_mode="compact",
        thinking_budget=1024,
        max_chat_turns=5,
        restrict_to_home=True,
    )
    originale.save(str(tmp_path))

    ricaricato = ChatSettings.load(str(tmp_path))
    assert ricaricato == originale


def test_salva_scrittura_atomica_tmp_poi_replace(tmp_path):
    """Stessa disciplina di ChatbotEngine._save(): passa da un file .tmp,
    mai una scrittura diretta sul file finale."""
    ChatSettings(name="X").save(str(tmp_path))
    assert (tmp_path / "impostazioni_chat.json").exists()
    assert not (tmp_path / "impostazioni_chat.json.tmp").exists()


def test_carica_file_corrotto_non_solleva_usa_i_default(tmp_path, caplog):
    (tmp_path / "impostazioni_chat.json").write_text("{ non e' json valido", encoding="utf-8")
    with caplog.at_level("ERROR"):
        imp = ChatSettings.load(str(tmp_path))
    assert imp == ChatSettings()
    assert any("Impostazioni chat illeggibili" in rec.message for rec in caplog.records)


def test_carica_file_parziale_riempie_i_campi_mancanti_coi_default(tmp_path):
    """Un file scritto da una versione futura/passata con solo alcuni campi
    non deve far esplodere il caricamento -- ogni campo assente prende il
    proprio default nel codice, non KeyError."""
    (tmp_path / "impostazioni_chat.json").write_text(
        json.dumps({"nome": "Solo il nome"}), encoding="utf-8",
    )
    imp = ChatSettings.load(str(tmp_path))
    assert imp.name == "Solo il nome"
    assert imp.system_prompt == DEFAULT_SYSTEM_PROMPT
    assert imp.max_chat_turns == 0


def test_carica_system_prompt_vuoto_in_file_ricade_sul_default(tmp_path):
    """Una stringa vuota persistita (non l'assenza della chiave) deve
    comunque ricadere sul prompt di default -- mai una chat con prompt
    letteralmente vuoto."""
    (tmp_path / "impostazioni_chat.json").write_text(
        json.dumps({"system_prompt": ""}), encoding="utf-8",
    )
    imp = ChatSettings.load(str(tmp_path))
    assert imp.system_prompt == DEFAULT_SYSTEM_PROMPT


# fetta E5 Task 10 ("esce la superficie di compatibilita'"): test_id_chat_
# default_e_hiris_default pinnava `ID_CHAT_DEFAULT`, uscito da questo modulo
# insieme al suo unico chiamante di produzione (handlers_chatbots.py --
# `chat_store.py` non l'ha mai letto, nonostante il commento della costante
# lo affermasse: gia' falso al presente prima di questo task). Il docstring
# del test era anch'esso invecchiato: static/chat/agents.js non legge piu'
# "hiris-default" da un pezzo (fetta E5 Task 4, vedi la sua intestazione).
# Verificato che cadesse per costruzione (`ImportError: cannot import name
# 'ID_CHAT_DEFAULT'`) prima della cancellazione.


# ---------------------------------------------------------------------------
# fetta E5 Task 2: `save()` smette di essere orfana, e la sua scrittura si
# allinea al precedente di questo ramo per i file di /data che devono
# sopravvivere ai riavvii (token_interno._write_token).
# ---------------------------------------------------------------------------

def _chiamate_a_salva():
    r"""Le chiamate `qualcosa.save(...)` in `hiris/app`, trovate con l'AST.

    Fix round 1, I-3. La prima versione di questa guardia cercava
    `\.salva\(` con una regex riga per riga, scartando solo le righe che
    cominciano con `#`. Una DOCSTRING la soddisfaceva: la prosa in cima a
    `api/handlers_settings.py` contiene la frase «`ChatSettings.save()`
    non aveva nessun chiamante», che combacia col pattern e nomina il file
    cercato -- quindi entrambe le asserzioni sarebbero rimaste verdi anche
    cancellando la chiamata vera.

    E' esattamente il limite che il report di questo task imputa al censimento
    («il rilevatore crede il nome citato»), riprodotto dentro il test scritto
    per rimediarvi. Con l'AST la prosa smette di contare: si cercano nodi
    `Call` il cui `func` e' un `Attribute` di nome `save`, cioe' chiamate
    vere. Verificato per mutazione (vedi il report): cancellando la riga della
    chiamata e lasciando la docstring, il test diventa rosso.
    """
    import ast
    from pathlib import Path

    app = Path(__file__).resolve().parents[1] / "hiris" / "app"
    trovate = []
    for f in sorted(app.rglob("*.py")):
        try:
            albero = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - un file non parsabile e' gia' un guasto suo
            continue
        for nodo in ast.walk(albero):
            if (isinstance(nodo, ast.Call)
                    and isinstance(nodo.func, ast.Attribute)
                    and nodo.func.attr == "save"):
                trovate.append(f"{f.name}:{nodo.lineno}")
    return trovate


def test_salva_ha_un_chiamante_di_produzione():
    """Il difetto che il Task 2 della fetta E5 chiude, pinnato dove si vede.

    Fino a quel task le uniche chiamate a `ChatSettings.save()` in tutto
    il repo erano le due di questo file: i sette campi si potevano cambiare
    SOLO scrivendo a mano `/data/impostazioni_chat.json`. Se questo test
    tornasse a fallire significherebbe che la superficie HTTP che li salva e'
    uscita senza sostituto, cioe' che il buco si e' riaperto."""
    chiamanti = _chiamate_a_salva()
    assert chiamanti, (
        "ChatSettings.save() non ha nessun chiamante di produzione: i sette "
        "campi tornerebbero a essere modificabili solo scrivendo a mano il JSON "
        "in /data"
    )
    assert any(c.startswith("handlers_settings.py:") for c in chiamanti), chiamanti


def test_salva_non_lascia_il_temporaneo_se_la_scrittura_fallisce(tmp_path, monkeypatch):
    """Un errore a meta' scrittura non deve ne' pubblicare un file troncato ne'
    lasciare il `.tmp` a sporcare /data per sempre."""
    import json as _json

    def esplodi(*args, **kwargs):
        raise OSError("disco pieno")

    monkeypatch.setattr(_json, "dump", esplodi)
    with pytest.raises(OSError):
        ChatSettings(name="Mai scritto").save(str(tmp_path))
    assert not (tmp_path / "impostazioni_chat.json").exists()
    assert not (tmp_path / "impostazioni_chat.json.tmp").exists()


def test_salva_non_pubblica_un_file_su_un_errore_e_lascia_intatto_il_precedente(
    tmp_path, monkeypatch
):
    """Il caso vero: c'e' gia' un file buono e il salvataggio successivo
    fallisce. Il precedente deve restare leggibile e invariato -- e' cio' che
    l'add-on rileggera' al prossimo avvio."""
    import json as _json

    ChatSettings(name="Il buono").save(str(tmp_path))
    monkeypatch.setattr(_json, "dump", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        ChatSettings(name="Il rotto").save(str(tmp_path))
    assert ChatSettings.load(str(tmp_path)).name == "Il buono"


def test_salva_scrive_col_permesso_piu_stretto_disponibile(tmp_path):
    """Stessa disciplina di `token_interno._write_token`: i permessi si danno
    alla creazione del temporaneo, non con un chmod dopo la pubblicazione.

    Su Linux -- la piattaforma dell'add-on -- il file finisce 0600. Su Windows,
    dove gira solo la suite, i bit di gruppo/altri non esistono: si verifica
    cio' che quella piattaforma puo' garantire, cioe' che il proprietario
    legga e scriva, invece di asserire un valore che li' non significa
    niente."""
    import os
    import stat

    ChatSettings(name="Permessi").save(str(tmp_path))
    modo = stat.S_IMODE(os.stat(tmp_path / "impostazioni_chat.json").st_mode)
    assert modo & stat.S_IRUSR and modo & stat.S_IWUSR
    if os.name != "nt":
        assert modo & (stat.S_IRWXG | stat.S_IRWXO) == 0, oct(modo)


# ---------------------------------------------------------------------------
# fetta «la catena diventa l'unica verita'» (Task 4): il campo `model` esce.
# Non c'e' piu' un modello scelto qui che scavalchi la catena della pagina
# Modelli -- e un file scritto da una versione precedente non viene ne'
# migrato ne' ignorato in silenzio: viene DICHIARATO.
# ---------------------------------------------------------------------------

def test_le_impostazioni_non_hanno_piu_un_modello():
    assert not hasattr(ChatSettings(), "model")


def test_un_file_con_il_vecchio_modello_lo_dichiara_invece_di_ignorarlo(tmp_path, caplog):
    (tmp_path / "impostazioni_chat.json").write_text(
        '{"nome": "HIRIS", "model": "claude-opus-4-7"}', encoding="utf-8")
    with caplog.at_level("INFO"):
        imp = ChatSettings.load(str(tmp_path))
    assert imp.name == "HIRIS"
    testo = "\n".join(r.getMessage() for r in caplog.records)
    assert "claude-opus-4-7" in testo, testo


def test_un_file_senza_il_vecchio_modello_non_dice_niente(tmp_path, caplog):
    """La prova gemella: la dichiarazione non è una riga che si stampa sempre."""
    (tmp_path / "impostazioni_chat.json").write_text('{"nome": "HIRIS"}', encoding="utf-8")
    with caplog.at_level("INFO"):
        ChatSettings.load(str(tmp_path))
    assert "model" not in "\n".join(r.getMessage() for r in caplog.records)


def test_salva_non_riscrive_il_vecchio_modello_che_quindi_sparisce_dal_file(tmp_path):
    """Il secondo pezzo del silenzio dichiarato, quello che il log promette.

    A differenza di `brain_model` in `handlers_models.load_models_config` --
    che sopravvive perché `save_models_config` fa lettura-modifica-scrittura
    -- qui `save()` riscrive il file da zero coi sei campi veri: la chiave
    `model` sparisce al primo salvataggio dell'utente. Il log lo dice, e
    questo test verifica che sia vero."""
    import json as _json

    (tmp_path / "impostazioni_chat.json").write_text(
        '{"nome": "HIRIS", "model": "claude-opus-4-7"}', encoding="utf-8")
    ChatSettings.load(str(tmp_path)).save(str(tmp_path))
    su_disco = _json.loads((tmp_path / "impostazioni_chat.json").read_text(encoding="utf-8"))
    assert "model" not in su_disco, su_disco
    assert su_disco["nome"] == "HIRIS"


# ---------------------------------------------------------------------------
# fetta "Modelli" (2.0), Task 12: `giorni_conservazione` si sposta qui da
# `history_retention_days` (l'opzione dell'add-on). E' ancora la versione A
# della migrazione (Task 6): se il file non porta la chiave, il valore arriva
# dall'ambiente (`HISTORY_RETENTION_DAYS`, che `run.sh` esporta dall'opzione),
# dichiarato nel log -- non un seed permanente: un file che GIA' porta la
# chiave, 0 compreso, vince sempre.
# ---------------------------------------------------------------------------

def test_i_giorni_di_conservazione_vivono_nelle_impostazioni_della_chat():
    assert ChatSettings().retention_days == 90


def test_al_primo_avvio_il_valore_arriva_dall_opzione_dell_addon(tmp_path, monkeypatch, caplog):
    """Versione A applicata a questo valore: chi aveva 30 giorni non deve
    ritrovarsi a 90 senza una riga che lo dica. "Primo avvio" = nessun file
    ancora sul disco, non solo "chiave assente in un file esistente" --
    `load()` deve consultare l'ambiente in entrambi i casi."""
    monkeypatch.setenv("HISTORY_RETENTION_DAYS", "30")
    with caplog.at_level("INFO"):
        imp = ChatSettings.load(str(tmp_path))
    assert imp.retention_days == 30
    assert "30" in "\n".join(r.getMessage() for r in caplog.records)


def test_un_valore_gia_scelto_vince_sull_opzione(tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_RETENTION_DAYS", "30")
    (tmp_path / "impostazioni_chat.json").write_text(
        '{"giorni_conservazione": 7}', encoding="utf-8")
    assert ChatSettings.load(str(tmp_path)).retention_days == 7


def test_uno_zero_gia_scelto_vince_sull_opzione_e_non_diventa_il_default(tmp_path, monkeypatch):
    """La prova gemella, sul valore che il pattern `valore or predefinito`
    (usato per gli altri interi di questo file) romperebbe in silenzio: uno
    `0` esplicito nel file e' "non cancellare mai", non "chiave assente"."""
    monkeypatch.setenv("HISTORY_RETENTION_DAYS", "30")
    (tmp_path / "impostazioni_chat.json").write_text(
        '{"giorni_conservazione": 0}', encoding="utf-8")
    assert ChatSettings.load(str(tmp_path)).retention_days == 0


def test_un_ambiente_uguale_al_default_non_scrive_niente_nel_log(tmp_path, monkeypatch, caplog):
    """La prova gemella di `test_un_file_senza_il_vecchio_modello_non_dice_
    niente` sopra: un'installazione MAI toccata (opzione al suo stesso
    predefinito, 90) non deve leggere una riga di log a ogni riavvio --
    stessa disciplina del debito F della migrazione di `models_config.json`
    (Task 6/7)."""
    monkeypatch.setenv("HISTORY_RETENTION_DAYS", "90")
    with caplog.at_level("INFO"):
        imp = ChatSettings.load(str(tmp_path))
    assert imp.retention_days == 90
    assert "giorni_conservazione" not in "\n".join(r.getMessage() for r in caplog.records)
    assert "history_retention_days" not in "\n".join(r.getMessage() for r in caplog.records)


def test_un_ambiente_muto_non_solleva_e_ricade_sul_default(tmp_path, monkeypatch):
    """`HISTORY_RETENTION_DAYS` assente dall'ambiente (mai il caso reale
    sotto `run.sh`, che esporta sempre un valore -- ma questo modulo non deve
    fidarsi di chi lo chiama): nessun KeyError, nessun crash, il default nel
    codice."""
    monkeypatch.delenv("HISTORY_RETENTION_DAYS", raising=False)
    assert ChatSettings.load(str(tmp_path)).retention_days == 90


def test_un_ambiente_non_numerico_non_solleva_e_ricade_sul_default(tmp_path, monkeypatch):
    """`bashio::config` su un campo vuoto/malformato torna una stringa che
    `int()` non digerisce: stessa disciplina di `options_migration._integer`
    per gli altri sette valori che arrivano da `run.sh`."""
    monkeypatch.setenv("HISTORY_RETENTION_DAYS", "")
    assert ChatSettings.load(str(tmp_path)).retention_days == 90


def test_salva_scrive_i_giorni_di_conservazione(tmp_path):
    ChatSettings(retention_days=45).save(str(tmp_path))
    su_disco = json.loads((tmp_path / "impostazioni_chat.json").read_text(encoding="utf-8"))
    assert su_disco["giorni_conservazione"] == 45


# ---------------------------------------------------------------------------
# **C2 della revisione finale: la versione A, per questo campo, non migrava.**
#
# `carica()` LEGGE attraverso `HISTORY_RETENTION_DAYS` quando la chiave manca,
# ma non SCRIVE, e `save()` ha un solo chiamante di produzione: la PUT di
# «Impostazioni chat». Chi quella pagina non la apre mai non produce mai la
# chiave sul disco -- e il rilascio successivo (versione B, l'opzione fuori
# dallo schema) trova l'ambiente muto e fa valere il default del codice, 90.
# Chi aveva messo 30 se lo ritrova a 90 senza una riga che lo dica; chi aveva
# messo **0** («non cancellare mai») se lo ritrova a 90, e la potatura delle 3
# (`server._run_retention`) gli cancella le conversazioni piu' vecchie di
# novanta giorni. Perdita di dato irreversibile, e proprio la classe di perdita
# che la scelta di NON accorpare A e B esiste per impedire.
#
# Il cancello di rilascio non se ne accorgeva: le sue precondizioni guardavano
# solo `/data/models_config.json`. Adesso ne ha una quarta
# (`docs/prova-modelli-e-catena.md`).
#
# Si pinna il CABLAGGIO, non solo la funzione: la chiusura vive in
# `_on_startup`, quindi si estrae il blocco dal sorgente vero e lo si esegue
# isolato -- stessa tecnica (e stessa ragione: ogni fixture fa
# `app.on_startup.clear()`) di `tests/test_websocket_startup.py` e
# `tests/test_options_migration.py`.
# ---------------------------------------------------------------------------
def _blocco_giorni_dallo_startup():
    import inspect
    import textwrap

    from hiris.app import server

    src = inspect.getsource(server._on_startup)
    start = src.index("    chat_settings = ChatSettings.load(data_dir)")
    end = src.index('    _chatbots_json_path = os.path.join(', start)
    corpo = textwrap.dedent(src[start:end])
    firma = ("def _avvio(app, data_dir, logger, ChatSettings, "
             "file_lacks_retention_days):\n")
    namespace: dict = {}
    exec(compile(firma + textwrap.indent(corpo, "    "),
                 "<_on_startup giorni_conservazione>", "exec"), namespace)
    return namespace["_avvio"]


def _avvia(tmp_path):
    import logging

    from hiris.app.chat_settings import file_lacks_retention_days

    app: dict = {}
    _blocco_giorni_dallo_startup()(
        app, str(tmp_path), logging.getLogger("t"),
        ChatSettings, file_lacks_retention_days,
    )
    return app["impostazioni_chat"]


def test_i_giorni_di_conservazione_arrivano_sul_disco_al_primo_avvio(tmp_path, monkeypatch):
    """Rimettere il difetto -- togliere da `_on_startup` la chiamata a
    `save()` -- fa cadere questo test."""
    monkeypatch.setenv("HISTORY_RETENTION_DAYS", "30")
    assert _avvia(tmp_path).retention_days == 30
    su_disco = json.loads((tmp_path / "impostazioni_chat.json").read_text(encoding="utf-8"))
    assert su_disco["giorni_conservazione"] == 30, (
        "il valore che l'utente aveva nell'opzione dell'add-on non e' arrivato "
        "sul disco: la versione B lo perde e la potatura notturna cambia "
        "comportamento da sola"
    )


def test_lo_zero_sopravvive_alla_versione_b(tmp_path, monkeypatch):
    """Il caso che costa un dato: `0` significa «non cancellare mai», e il
    default del codice e' 90. Se la versione A non scrive, dopo la versione B
    la potatura delle 3 comincia a cancellare tutto cio' che ha piu' di
    novanta giorni -- senza che nessuno l'abbia chiesto e senza una riga che lo
    dica."""
    monkeypatch.setenv("HISTORY_RETENTION_DAYS", "0")
    assert _avvia(tmp_path).retention_days == 0

    # Versione B: l'opzione esce dallo schema, `run.sh` non esporta piu'
    # niente, l'ambiente e' muto.
    monkeypatch.delenv("HISTORY_RETENTION_DAYS", raising=False)
    assert ChatSettings.load(str(tmp_path)).retention_days == 0, (
        "dopo la versione B «non cancellare mai» e' diventato «cancella dopo "
        "90 giorni»: e' una perdita di dato, non un default"
    )


def test_il_secondo_avvio_non_riscrive_e_non_rilogga(tmp_path, monkeypatch, caplog):
    """Contorno di C2, ed e' il debito F di un altro archivio: finche' la
    chiave non arriva sul disco, la riga di migrazione ricompare a OGNI
    riavvio. Dal primo avvio in poi il file la porta, quindi
    `_retention_days_from_environment` non viene nemmeno consultata."""
    import logging

    monkeypatch.setenv("HISTORY_RETENTION_DAYS", "30")
    _avvia(tmp_path)
    # Fra i due avvii l'utente cambia il valore dalla pagina: il secondo avvio
    # non deve riportarlo a quello dell'opzione.
    ChatSettings(retention_days=7).save(str(tmp_path))
    with caplog.at_level(logging.INFO):
        assert _avvia(tmp_path).retention_days == 7
    assert "giorni_conservazione" not in caplog.text, (
        "la migrazione ha parlato di nuovo al secondo avvio: non era piu' il "
        "suo momento"
    )
