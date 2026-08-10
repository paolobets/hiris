"""fetta «il ponte riceve il nucleo» (parita' A, Task 2, fix round 1):
`BASE_SYSTEM_PROMPT` e' spezzato in due meta', e questo file difende sia il
taglio sia cio' che il taglio NON deve rompere.

Perche' esiste. Dal Task 2 `BASE_SYSTEM_PROMPT` arriva anche al ponte (la chat
in abbonamento), dove i quattro strumenti di `casa/strumenti.py` non esistono.
La prima stesura del task lo passava INTERO e lo faceva smentire dal testo che
lo segue -- ma dentro ci sono ORDINI di chiamare uno strumento («Usa SEMPRE
gli strumenti per dati sulla casa», «chiama ricorda subito»), e il commento
che questo prodotto ha scritto sopra quella costante
(`claude_runner.py`, sopra `BASE_IDENTITA`) dice che «un prompt che ordina di
chiamare uno strumento inesistente riapre dal lato del prompt esattamente il
bug per cui `ricorda` e' nato»: il modello risponde "preso nota" senza aver
salvato. Una smentita di TESTO non e' un meccanismo.

Il taglio ha due invarianti, e questo file le pinna entrambe:
① la FONTE resta una -- la concatenazione ordinata delle due meta' e'
   `BASE_SYSTEM_PROMPT`, byte per byte, e i tre chiamanti sincroni continuano
   a vedere quella costante e non le meta';
② il CRITERIO del taglio -- in `BASE_IDENTITA` non deve poter rientrare
   nessuna istruzione che nomini, ordini o presupponga uno strumento, perche'
   quella meta' e' l'unica che il ponte emette.
"""
import inspect

from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
from hiris.app.claude_runner import (
    BASE_IDENTITA,
    BASE_REGOLE_STRUMENTI,
    BASE_SYSTEM_PROMPT,
    ClaudeRunner,
)


def test_la_concatenazione_ordinata_e_la_costante_di_prima():
    """La fonte resta UNA: spezzare non deve cambiare di un byte cio' che il
    percorso sincrono manda al modello."""
    assert BASE_IDENTITA + BASE_REGOLE_STRUMENTI == BASE_SYSTEM_PROMPT


def test_base_identita_non_contiene_istruzioni_sugli_strumenti():
    """Il criterio del taglio, reso eseguibile. `BASE_IDENTITA` e' l'unica
    meta' che il ponte emette: se un domani qualcuno ci sposta dentro una
    riga che nomina uno strumento, il ponte torna a ordinare al modello di
    chiamare qualcosa che non ha -- il difetto che questo taglio chiude."""
    minuscolo = BASE_IDENTITA.lower()
    for proibito in ("strument", "tool", "ricorda", "richiama", "cerca", "guarda"):
        assert proibito not in minuscolo, (
            f"{proibito!r} e' rientrato in BASE_IDENTITA: e' la meta' che il "
            "ponte emette SENZA avere gli strumenti")


def test_base_regole_strumenti_tiene_gli_ordini_che_presuppongono_un_tool():
    """Il complemento: le quattro istruzioni che sul ponte sarebbero false o
    ineseguibili devono stare tutte di la'. Se una scivolasse in
    `BASE_IDENTITA` il test qui sopra la prenderebbe; se sparisse del tutto,
    la prende questo."""
    assert "Hai a disposizione strumenti" in BASE_REGOLE_STRUMENTI
    assert "Usa SEMPRE gli strumenti" in BASE_REGOLE_STRUMENTI
    assert "chiama ricorda subito" in BASE_REGOLE_STRUMENTI
    assert "l'azione" in BASE_REGOLE_STRUMENTI and "disclaimers" in BASE_REGOLE_STRUMENTI


def test_il_percorso_sincrono_continua_a_comporre_la_costante_intera():
    """I tre chiamanti sincroni non cambiano: compongono `BASE_SYSTEM_PROMPT`,
    non le meta'. Il taglio serve al ponte e solo al ponte -- di la' i quattro
    strumenti esistono davvero e le regole sono vere.

    (Che la regola arrivi davvero al modello lo verificano gia' i test di
    `tests/test_base_prompt_memoria.py`, che chiamano i runner veri con un
    client finto. Qui si difende il livello che quelli non vedono: DA QUALE
    costante il blocco viene preso.)"""
    for sorgente in (inspect.getsource(ClaudeRunner.chat),
                     inspect.getsource(OpenAICompatRunner.chat),
                     inspect.getsource(OpenAICompatRunner.chat_stream)):
        assert "BASE_SYSTEM_PROMPT" in sorgente
        assert "BASE_IDENTITA" not in sorgente, (
            "un percorso SINCRONO ha cominciato a comporre solo meta' BASE: "
            "di la' gli strumenti ci sono, e la meta' sugli strumenti serve")
