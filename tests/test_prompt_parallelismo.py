"""fetta "i riferimenti" (Task 5, R3+R8): il tetto delle iterazioni sale a
50 e il prompt impara a insegnare il parallelismo che il ciclo gia' sa fare
(vedi `test_chat_processes_all_tool_use_blocks_of_one_response_in_one_iteration`
in `tests/test_claude_runner.py` per la prova che il ciclo processi davvero
piu' blocchi `tool_use` di una risposta in un solo giro).

Questo file pinna le istruzioni nuove -- "risolvi piu' nomi con UNA chiamata
cerca" e la riga raccolta dal Task 4 che lega gli id `(id: X)` dell'albero
agli strumenti -- su ENTRAMBE le guide: `claude_runner.BASE_REGOLE_STRUMENTI`
(il percorso sincrono, con chiave API) e `agent.prompts._GUIDA_CON_STRUMENTI`
(il ponte, chat in abbonamento) -- guardare `tests/test_prompt_azione.py` per
il perche' un'istruzione di prodotto deve stare in BASE_REGOLE_STRUMENTI e non
nella sola guida del ponte.

Fix finale ② (review 2026-08-20): il parallelismo NON e' piu' un'istruzione
identica sulle due guide, perche' la sua giustificazione non e' vera nello
stesso modo sui due percorsi:
- sincrono (`BASE_REGOLE_STRUMENTI`): il ciclo di `claude_runner.py` conta
  UN giro per risposta, non per chiamata -- N `tool_use` nella stessa
  risposta costano un'iterazione sola. La giustificazione e' vera, e resta;
- ponte (`_GUIDA_CON_STRUMENTI`): il tetto vero e' quello del server MCP
  (`MAX_GIRI_STRUMENTI` in `api/handlers_mcp.py`), e `_conta_giro` incrementa
  a OGNI `tools/call` -- 8 `guarda` paralleli nella stessa risposta della CLI
  costano comunque 8 giri. La VECCHIA frase ("il ciclo conta un giro per
  risposta, non per chiamata") era falsa su questo percorso: qui il
  risparmio vero e' il batch di `cerca` e la parsimonia, non il
  parallelismo -- vedi `test_solo_il_ponte_insegna_ogni_chiamata_conta` sotto.

Fix "il ponte muore a 9" (2026-08-21): `MAX_GIRI_STRUMENTI` era rimasto a 10
mentre questo file era scritto (la fetta aveva alzato solo il tetto
sincrono); un turno reale sul ponte moriva prima di arrivare a `prometti`.
La decisione del proprietario era "50 per chat e promessa", non "50 solo
sul ramo sincrono": i due tetti tornano allo stesso NUMERO per la stessa
decisione. Cio' che questo file continua a provare -- e che resta vero
anche col numero allineato -- e' che i due percorsi contano UNITA' diverse
(risposta contro singola chiamata): e' quella differenza, non il valore
assoluto, a rendere ancora necessaria una guida diversa sul ponte.

Sono test di presenza-testo: deboli in generale (un sinonimo li elude), ma
qui SONO il contratto -- e' il prompt che deve dire queste parole al modello,
non un comportamento osservabile da un altro lato. Dichiararlo qui perche' un
domani chi legge sappia perche' un assert cosi' semplice sopravvive in questo
progetto.
"""
from hiris.app.agent.prompts import _GUIDA_CON_STRUMENTI
from hiris.app.claude_runner import BASE_REGOLE_STRUMENTI


def _le_due_guide() -> dict[str, str]:
    return {
        "sincrono (BASE_REGOLE_STRUMENTI)": BASE_REGOLE_STRUMENTI,
        "ponte (_GUIDA_CON_STRUMENTI)": _GUIDA_CON_STRUMENTI,
    }


def test_entrambe_le_guide_insegnano_il_batch_di_cerca():
    """"Piu' nomi -> UNA chiamata cerca col testo intero" (R8: la capacita'
    c'e' gia' in `Indice.trova`, misurata 8 su 8 in una chiamata -- nessun
    prompt lo diceva)."""
    for percorso, testo in _le_due_guide().items():
        basso = testo.lower()
        assert "cerca" in basso and "una sola volta" in basso, (
            f"la guida {percorso} non insegna piu' il batch di cerca: un "
            "turno che deve risolvere N nomi torna a chiamare cerca N volte, "
            "il costo che questo task doveva evitare")


def test_entrambe_le_guide_legano_gli_id_dell_albero_agli_strumenti():
    """Raccolta dal Task 4 (nota in progress.md): l'albero della casa ora
    porta gli id fra parentesi (`Nome (id: X)`, T4), ma senza questa riga
    nessuna guida diceva al modello che sono ESATTAMENTE gli identificatori
    da passare agli strumenti -- il modello chiamerebbe comunque `cerca` per
    qualcosa che il contesto gli sta gia' dando."""
    for percorso, testo in _le_due_guide().items():
        assert "(id: X)" in testo, (
            f"la guida {percorso} non lega piu' gli id fra parentesi "
            "dell'albero agli strumenti")


def test_entrambe_le_guide_legano_anche_gli_script_agli_id_dell_albero():
    """Fix finale ③: l'albero annota gli id anche per gli SCRIPT
    (`nucleo.py::_righe_comportamento`, stessa forma di aree/piani/
    automazioni), ma la riga che lega gli id fra parentesi agli strumenti
    nominava solo "un'area, un piano o un'automazione" -- dimenticando lo
    script, che porta l'id con la stessa identica annotazione."""
    for percorso, testo in _le_due_guide().items():
        assert "o uno script" in testo, (
            f"la guida {percorso} non menziona piu' lo script fra le cose "
            "che portano l'id fra parentesi nell'albero")


def test_il_sincrono_insegna_il_parallelismo_col_conteggio_vero():
    """Sul percorso sincrono la giustificazione e' vera (il ciclo di
    `claude_runner.py` conta un giro per risposta, non per chiamata): resta
    l'istruzione originale, invariata."""
    assert "IN PARALLELO" in BASE_REGOLE_STRUMENTI
    assert "il ciclo conta un giro per risposta, non per" in BASE_REGOLE_STRUMENTI


def test_solo_il_ponte_insegna_ogni_chiamata_conta():
    """Sul ponte il tetto vero e' quello MCP (`MAX_GIRI_STRUMENTI`,
    `api/handlers_mcp.py`), e `_conta_giro` incrementa a OGNI `tools/call`:
    8 `guarda` paralleli nella stessa risposta della CLI costano comunque 8
    giri. La guida del ponte non deve piu' promettere il risparmio falso
    ("un giro per risposta, non per chiamata") -- deve dire che ogni
    chiamata conta, e che il risparmio vero e' il batch di `cerca` piu' la
    parsimonia."""
    assert "il ciclo conta un giro per risposta, non per" not in _GUIDA_CON_STRUMENTI, (
        "la guida del ponte ripete ancora la giustificazione falsa: sul "
        "ponte ogni chiamata (anche parallela) consuma un giro del tetto MCP")
    basso = _GUIDA_CON_STRUMENTI.lower()
    assert "ogni chiamata conta" in basso
    assert "parsimoni" in basso


def test_il_tetto_delle_iterazioni_e_50():
    """Decisione del proprietario (spec, sez. 2): il tetto sale da 10 a 50,
    in chat E nella promessa (stesso runner). Pin diretto sulla costante, non
    sul comportamento -- il comportamento (una iterazione per N blocchi
    tool_use) lo prova `test_claude_runner.py` sopra citato."""
    from hiris.app.claude_runner import MAX_TOOL_ITERATIONS
    assert MAX_TOOL_ITERATIONS == 50


def test_il_tetto_del_ponte_e_50():
    """Fix "il ponte muore a 9" (2026-08-21, misurato dal vivo): un turno
    reale sul ponte (8 `guarda` per le stanze + 1 `cerca` + la `prometti`
    finale = 10 chiamate) moriva contro il vecchio `MAX_GIRI_STRUMENTI = 10`
    prima di arrivare a `prometti`. La decisione del proprietario citata dal
    test sopra era "tetto a 50 per chat E promessa", non "50 solo sul ramo
    sincrono": il ponte E' la chat quando l'abbonamento e' attivo, e il suo
    costo e' forfettario (nessun costo marginale sulle chiamate in piu').

    Pin diretto sulla costante (non sul comportamento, gia' pinnato da
    `tests/test_rotta_mcp.py`): senza questo test la suite restava verde
    anche riportando il tetto del ponte a 10, perche' nessun altro test lo
    lega al valore -- tutti usano `handlers_mcp.MAX_GIRI_STRUMENTI` in modo
    relativo. Se qualcuno lo riabbassa senza dichiararlo qui, questo test
    diventa rosso."""
    from hiris.app.api.handlers_mcp import MAX_GIRI_STRUMENTI
    assert MAX_GIRI_STRUMENTI == 50


def test_il_tetto_ollama_resta_proporzionato():
    """`_OLLAMA_MAX_TOOL_ITERATIONS` era meta' del tetto sincrono (5 su 10);
    la proporzione -- non il valore assoluto -- e' cio' che il brief chiedeva
    di mantenere: 25 su 50."""
    from hiris.app.backends.openai_compat_runner import (
        MAX_TOOL_ITERATIONS as _sincrono,
        _OLLAMA_MAX_TOOL_ITERATIONS as _ollama,
    )
    assert _sincrono == 50
    assert _ollama == 25
    assert _ollama == _sincrono // 2
