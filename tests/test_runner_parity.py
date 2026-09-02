"""La parita' fra i due runner: una regola del progetto che nessuno difendeva.

**La regola esiste da prima di questa fetta** -- «ogni kwarg nuovo di
`ClaudeRunner` dev'essere accettato anche dal runner compatibile» -- ed **era
gia' difesa, piu' debolmente**, da `tests/test_runner_catalog.py:59,69`, che
pretende che i due runner accettino `tools` e `dispatcher`. Questo cancello non
e' nuovo: e' piu' forte, perche' confronta le firme INTERE (ordine, nomi,
default) invece di due nomi, e perche' i metodi li DERIVA invece di
elencarli. Il router (`steering.py`) sceglie
fra i due per DUCK-TYPING: chiama `chat(...)` su qualunque runner la catena gli
metta davanti, e se le due firme divergono il ripiego da un provider all'altro
si rompe **sul percorso che esiste apposta per non rompersi**.

Il costo di non averla difesa e' stato misurato dal lotto di `backends/` (fetta
«la rinomina»): `strumenti`, `modello` e `scelto` sono rimasti italiani li'
**perche' tradurne meta' avrebbe rotto la coppia**, e nessun cancello lo
avrebbe detto. Il residuo era la scelta giusta; l'assenza di rete no.

**Cosa NON pretende, e perche'.** I due costruttori divergono di proposito:
`OpenAICompatRunner` vuole `base_url`, `local` e `timeout_s`, che per Claude
non hanno senso. Pretendere l'identita' li' sarebbe un cancello che arrossisce
su un progetto corretto. Si pretende invece che i kwarg CONDIVISI -- quelli che
la regola del progetto nomina -- esistano in tutti e due con lo stesso
default: e' esattamente la superficie che il chiamante comune usa.
"""
import inspect

from hiris.app.backends.openai_compat_runner import OpenAICompatRunner
from hiris.app.claude_runner import ClaudeRunner
from tests._contracts import assert_stessa_firma

# I kwarg che la regola del progetto nomina: chi ne aggiunge uno a
# `ClaudeRunner` deve aggiungerlo anche qui, e questo elenco e' il posto dove
# lo si scrive.
_KWARG_CONDIVISI = ("read_model", "log_usage")


def _metodi_condivisi() -> list[str]:
    """I metodi che i due runner portano entrambi, `__init__` escluso.

    Derivato, non trascritto: un metodo nuovo aggiunto a tutti e due entra
    nella parita' senza che nessuno se ne ricordi.
    """
    return sorted(
        ({n for n, v in vars(ClaudeRunner).items() if callable(v)}
         & {n for n, v in vars(OpenAICompatRunner).items() if callable(v)})
        - {"__init__"})


def test_i_due_runner_hanno_la_stessa_interfaccia():
    """Il cancello che mancava.

    Provato per mutazione: rinominato `strumenti` in `tools` nella sola
    `OpenAICompatRunner.chat`, questo test va rosso nominando la coppia --
    cioe' esattamente il difetto che il lotto di `backends/` ha evitato a mano.
    """
    condivisi = _metodi_condivisi()
    assert "chat" in condivisi and "chat_stream" in condivisi, (
        "i due runner non condividono piu' `chat`/`chat_stream`: o l'hanno "
        "rinominato, o questo cancello ha smesso di guardare cio' che conta")
    for nome in condivisi:
        assert_stessa_firma(getattr(ClaudeRunner, nome),
                            getattr(OpenAICompatRunner, nome),
                            nome=f"ClaudeRunner.{nome} contro "
                                 f"OpenAICompatRunner.{nome}")


def test_i_kwarg_condivisi_del_costruttore_esistono_in_tutti_e_due():
    """I due `__init__` divergono di proposito (`base_url`, `local`,
    `timeout_s` non hanno senso per Claude): si pretende la sola superficie
    che il chiamante comune usa."""
    for cls in (ClaudeRunner, OpenAICompatRunner):
        firma = inspect.signature(cls.__init__).parameters
        for kw in _KWARG_CONDIVISI:
            assert kw in firma, (
                f"{cls.__name__}.__init__ non accetta piu' «{kw}»: e' un "
                "kwarg che il chiamante passa a ENTRAMBI i runner, e uno dei "
                "due lo rifiuterebbe con un TypeError alla prima catena che "
                "ripiega")
            assert firma[kw].default is None, (
                f"{cls.__name__}.__init__ da' a «{kw}» un default diverso da "
                "`None`: i due runner devono comportarsi uguale quando il "
                "chiamante non lo passa")
