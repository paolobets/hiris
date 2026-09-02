"""fetta «il ponte riceve il nucleo» (parita' A, Task 2, fix round 1):
`BASE_SYSTEM_PROMPT` e' spezzato in due meta', e questo file difende sia il
taglio sia cio' che il taglio NON deve rompere.

Perche' esiste. Dal Task 2 `BASE_SYSTEM_PROMPT` arriva anche al ponte (la chat
in abbonamento), dove gli strumenti di `home_space/tools.py` non esistono.
La prima stesura del task lo passava INTERO e lo faceva smentire dal testo che
lo segue -- ma dentro ci sono ORDINI di chiamare uno strumento («Usa SEMPRE
gli strumenti per dati sulla casa», «chiama remember subito»), e il commento
che questo prodotto ha scritto sopra quella costante
(`claude_runner.py`, sopra `BASE_IDENTITY`) dice che «un prompt che ordina di
chiamare uno strumento inesistente riapre dal lato del prompt esattamente il
bug per cui `remember` e' nato»: il modello risponde "preso nota" senza aver
salvato. Una smentita di TESTO non e' un meccanismo.

Il taglio ha due invarianti, e questo file le pinna entrambe:
① la FONTE resta una -- la concatenazione ordinata delle due meta' e'
   `BASE_SYSTEM_PROMPT`, byte per byte, e i tre chiamanti sincroni continuano
   a vedere quella costante e non le meta';
② il CRITERIO del taglio -- in `BASE_IDENTITY` non deve poter rientrare
   nessuna istruzione che nomini, ordini o presupponga uno strumento, perche'
   quella meta' e' l'unica che il ponte emette.
"""
import inspect

from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
from hiris.app.claude_runner import (
    BASE_IDENTITY,
    BASE_SYSTEM_PROMPT,
    BASE_TOOL_RULES,
    ClaudeRunner,
)


def test_la_concatenazione_ordinata_e_la_costante_di_prima():
    """La fonte resta UNA: spezzare non deve cambiare di un byte cio' che il
    percorso sincrono manda al modello."""
    assert BASE_IDENTITY + BASE_TOOL_RULES == BASE_SYSTEM_PROMPT


def test_base_identita_non_contiene_istruzioni_sugli_strumenti():
    """Il criterio del taglio, reso eseguibile. `BASE_IDENTITY` e' l'unica
    meta' che il ponte emette: se un domani qualcuno ci sposta dentro una
    riga che nomina uno strumento, il ponte torna a ordinare al modello di
    chiamare qualcosa che non ha -- il difetto che questo taglio chiude."""
    minuscolo = BASE_IDENTITY.lower()
    for proibito in ("strument", "tool", "remember", "fetch", "search", "view"):
        assert proibito not in minuscolo, (
            f"{proibito!r} e' rientrato in BASE_IDENTITY: e' la meta' che il "
            "ponte emette SENZA avere gli strumenti")


def test_base_regole_strumenti_tiene_gli_ordini_che_presuppongono_un_tool():
    """Il complemento: le quattro istruzioni che sul ponte sarebbero false o
    ineseguibili devono stare tutte di la'. Se una scivolasse in
    `BASE_IDENTITY` il test qui sopra la prenderebbe; se sparisse del tutto,
    la prende questo."""
    assert "Hai a disposizione strumenti" in BASE_TOOL_RULES
    assert "Usa SEMPRE gli strumenti" in BASE_TOOL_RULES
    assert "chiama remember subito" in BASE_TOOL_RULES
    assert "l'azione" in BASE_TOOL_RULES and "disclaimers" in BASE_TOOL_RULES


def test_la_riga_sulla_lingua_sta_nella_meta_che_il_ponte_emette():
    """Fix della review totale della fetta (m-2). "Rispondi nella lingua
    dell'utente" NON e' una regola sugli strumenti: non ne nomina, non ne
    ordina e non ne presuppone nessuno. Stava in `BASE_TOOL_RULES` per
    contiguita' (ultimo trattino dell'elenco), e quindi sul ponte -- che di
    BASE emette la sola `BASE_IDENTITY` -- non arrivava affatto: l'unica
    istruzione di lingua che gli restava era `prompts._CHAT_INSTRUCTION`, che
    imponeva SEMPRE l'italiano. Divergenza di comportamento fra i due percorsi
    di chat, in una fetta che si chiama "parita'".

    Questo test la pinna DA ENTRAMBI I LATI, cosi' non puo' rimigrare in
    silenzio: dev'essere nella meta' che il ponte emette, e non dev'essere in
    quella che il ponte NON emette."""
    riga = "Rispondi nella lingua dell'utente"
    assert riga in BASE_IDENTITY, (
        "la riga sulla lingua e' uscita da BASE_IDENTITY: il ponte torna "
        "senza istruzione di lingua, e _CHAT_INSTRUCTION da sola non basta")
    assert riga not in BASE_TOOL_RULES, (
        "la riga sulla lingua e' rientrata nella meta' che il ponte NON "
        "emette: e' il difetto m-2, riaperto")
    # e la fonte resta una: chi la legge da BASE_SYSTEM_PROMPT la trova ancora
    assert riga in BASE_SYSTEM_PROMPT


def test_il_ponte_e_il_sincrono_non_si_contraddicono_sulla_lingua():
    """L'altra meta' del fix m-2. `prompts._CHAT_INSTRUCTION` e' l'ultima riga
    del prompt UTENTE del ponte, letta dopo tutto il system: se dicesse
    «SEMPRE in italiano» mentre `BASE_IDENTITY` (che ora il ponte emette) dice
    «nella lingua dell'utente», il prompt si contraddirebbe da solo e
    vincerebbe l'ultima letta. Le due istruzioni devono dire la stessa cosa."""
    from hiris.app.agent import prompts

    assert "SEMPRE in italiano" not in prompts._CHAT_INSTRUCTION, (
        "il ponte impone di nuovo l'italiano mentre BASE_IDENTITY dice di "
        "rispondere nella lingua dell'utente: e' il difetto m-2, riaperto "
        "dall'altro lato")
    assert "lingua dell'utente" in prompts._CHAT_INSTRUCTION


def test_il_percorso_sincrono_continua_a_comporre_la_costante_intera():
    """I tre chiamanti sincroni non cambiano: compongono `BASE_SYSTEM_PROMPT`,
    non le meta'. Il taglio serve al ponte e solo al ponte -- di la' gli
    strumenti esistono davvero e le regole sono vere.

    (Che la regola arrivi davvero al modello lo verificano gia' i test di
    `tests/test_base_prompt_memory.py`, che chiamano i runner veri con un
    client finto. Qui si difende il livello che quelli non vedono: DA QUALE
    costante il blocco viene preso.)"""
    for sorgente in (inspect.getsource(ClaudeRunner.chat),
                     inspect.getsource(OpenAICompatRunner.chat),
                     inspect.getsource(OpenAICompatRunner.chat_stream)):
        assert "BASE_SYSTEM_PROMPT" in sorgente
        assert "BASE_IDENTITY" not in sorgente, (
            "un percorso SINCRONO ha cominciato a comporre solo meta' BASE: "
            "di la' gli strumenti ci sono, e la meta' sugli strumenti serve")
