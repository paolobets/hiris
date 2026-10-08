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

`chatbots.json` e' restato per decisione del proprietario finche' non lo ha
guardato (D6 della Tappa 8): conteneva il prompt personalizzato del bot di
default. Lo Sprint gliel'ha mostrato l'08/10/2026, ed e' entrato fra i residui.
"""
import json
import pathlib

from hiris.app.conservazione import RESIDUI_DISMESSI, cancella_residui


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


def test_chatbots_json_si_cancella_DOPO_che_il_proprietario_lo_ha_guardato(tmp_path):
    """**Rovesciata l'08/10/2026.** Fino ad allora pretendeva che
    `chatbots.json` restasse: la regola non e' «cancella tutto cio' che e'
    morto», e' «cancella cio' che e' morto **e** su cui si e' deciso». Il
    proprietario lo ha guardato l'08/10/2026 (D6), e adesso e' deciso.

    Mutazione ESEGUITA: toglierlo dall'elenco -- rossa."""
    file = _fai(tmp_path, "chatbots.json", json.dumps({"prompt": "sei tu"}))

    cancella_residui(str(tmp_path))

    assert not file.exists()
    assert "chatbots.json" in RESIDUI_DISMESSI


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

    with caplog.at_level(logging.DEBUG, logger="hiris.app.conservazione"):
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


def _string_literals_in_the_product() -> list[tuple[str, str]]:
    """Ogni letterale stringa del prodotto, col file in cui sta. I docstring
    non sono letterali che il programma usa: restano fuori."""
    import ast

    found: list[tuple[str, str]] = []
    app = pathlib.Path(__file__).resolve().parents[1] / "hiris" / "app"
    for source in sorted(app.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                first = node.body[0] if node.body else None
                if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    docstrings.add(id(first.value))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docstrings):
                found.append((node.value, source.name))
    return found


def _named_by(name: str, literals: list[tuple[str, str]]) -> list[str]:
    """I file in cui un letterale NOMINA il file `name`: da solo, o in fondo a
    un percorso (`"/data/usage.json"`). `hiris_memory.db` non nomina
    `memory.db`: prima del nome ci vuole l'inizio o una barra."""
    return [where for value, where in literals
            if value == name or value.endswith("/" + name)]


def test_nessun_residuo_dell_elenco_e_un_archivio_che_il_prodotto_apre():
    """Cio' che questo elenco cancella a ogni avvio non deve essere un file
    che qualche riga del prodotto apre: il nome di ogni residuo compare nel
    codice UNA volta sola, dentro `RESIDUI_DISMESSI`. Un archivio vivo
    (`consumi.db`, `sapere.db`...) e' nominato anche da chi lo apre.

    La prova di prima confrontava l'elenco col sorgente di `server.py`, dove
    l'elenco stesso e' scritto: non poteva fallire (misurato dal revisore il
    02/10/2026, con la mutazione che il suo docstring dichiarava rossa).

    **Anche quando il nome sta in fondo a un percorso** (revisione del
    02/10/2026): `server.py` apriva `"/data/usage.json"`, e un confronto fra
    letterali interi non lo vedeva. Dall'08/10/2026 (D6) quel percorso e'
    `os.path.join(data_dir, "usage.json")`: il ramo del percorso si prova su
    un letterale fabbricato, il nome nudo sul prodotto.

    Mutazioni ESEGUITE, entrambe rosse col nome e i punti che lo nominano:
    aggiunto `"consumi.db"` a `RESIDUI_DISMESSI`; aggiunto `"usage.json"`
    (la seconda, prima, restava verde). Mutazione ESEGUITA l'08/10/2026
    (Tappa 8, Task 7): in `chat_settings.file_lacks_retention_days` un
    `os.path.exists(os.path.join(data_dir, "casa.db"))` -- rossa, con
    `casa.db` e i due file che lo nominano."""
    literals = _string_literals_in_the_product()
    assert len(literals) > 5000, "la raccolta dei letterali si e' rotta"
    assert _named_by("usage.json", literals), "la prova non vede piu' un nome nudo"
    assert _named_by("usage.json", [("/data/usage.json", "x.py")]) == ["x.py"], (
        "la prova non vede piu' un nome in fondo a un percorso")
    alive = {name: _named_by(name, literals) for name in RESIDUI_DISMESSI
             if len(_named_by(name, literals)) != 1}
    assert not alive, (
        "nomi dell'elenco dei residui che il prodotto nomina anche altrove "
        f"(o non nomina affatto): {alive}")


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
    registro = logging.getLogger("hiris.app.conservazione")
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

    L'elenco dei nomi si CHIEDE a `conservazione.RESIDUI_DISMESSI`: un residuo
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
                    if nome in message
                    and any(word in message for word in ("resta", "intatto", "non viene toccato"))]
        if gone and promised:
            lies.append(f"{nome}: «{promised[0][-60:]}»")
    assert not lies, (
        "l'avvio promette che un file resta e poi lo cancella: " + "; ".join(lies))


def test_un_contatore_IMPORTATO_sparisce_uno_illeggibile_resta(tmp_path):
    """D6 della Tappa 8: un `usage*.json` registrato in `legacy_importati`
    e' un residuo, e l'avvio lo cancella dopo averlo importato -- il suo
    totale e' gia' nell'archivio dei consumi. Uno illeggibile non si importa,
    quindi non si registra, e resta: il suo totale non e' da nessuna parte.

    Sull'avvio vero, perche' l'ordine conta: cancellare prima di importare
    perderebbe il totale.

    Mutazione ESEGUITA (08/10/2026): `cancella_residui` chiamato senza
    `imported` -- rossa (il contatore importato resta)."""
    import asyncio
    import sys

    root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    import fotografia_porte

    from tests._casa_sintetica import synthetic_inputs

    importato = _fai(tmp_path, "usage.json", json.dumps({"total_requests": 3}))
    rotto = _fai(tmp_path, "usage_openai.json", "{non e' json")
    seen: dict = {}

    async def boot() -> None:
        async with fotografia_porte.mounted(synthetic_inputs(), str(tmp_path)) as app:
            seen["richieste"] = app["usage"].totali()["richieste"]
            seen["importati"] = app["usage"].legacy_imported()

    asyncio.run(boot())

    assert seen["importati"] == [str(importato)]
    assert seen["richieste"] == 3
    assert not importato.exists(), "un contatore gia' importato e' rimasto su disco"
    assert rotto.exists(), "cancellato un contatore che non e' stato contato"


def test_gli_undici_file_scelti_dal_proprietario_se_ne_vanno_e_la_cornice_resta(tmp_path, caplog):
    """L'08/10/2026 il backup della casa ha mostrato undici file di
    installazioni precedenti che nessun codice nomina piu', e il proprietario
    ha scelto «Tutti». Se ne vanno col nome e la dimensione nel registro, come
    gli altri residui. `reference_frame.json` sta accanto ma e' vivo: lo
    legge e lo scrive l'anagrafe, e il nome si chiede a lei, non si ricopia.

    Mutazioni ESEGUITE: tolto `home_map.db` dall'elenco -- rossa; aggiunto
    `reference_frame.json` all'elenco -- rossa."""
    import logging

    from hiris.app.home_space.reader import REFERENCE_FRAME_FILE

    scelti = ("brain_reasoning.db", "suggestions.db", "hiris_knowledge.db",
              "home_map.db", "hiris_memory.db.migrated", "home_semantic_map.json",
              "semantic_context_map.json", "gateway_policy.json",
              "sentinel_policy.json", "chat_history_hiris-default.json",
              ".mqtt_discovery_migrated_v2")
    fatti = [_fai(tmp_path, nome) for nome in scelti]
    cornice = _fai(tmp_path, REFERENCE_FRAME_FILE, "{}")

    with caplog.at_level(logging.INFO, logger="hiris.app.conservazione"):
        cancella_residui(str(tmp_path))

    assert [p.name for p in fatti if p.exists()] == []
    for nome in scelti:
        assert any(r.getMessage().startswith(f"{nome} cancellato (1 byte)")
                   for r in caplog.records), nome
    assert cornice.exists()
    assert REFERENCE_FRAME_FILE not in RESIDUI_DISMESSI
