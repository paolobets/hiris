"""Guardia contro i doppi che divergono in silenzio dall'interfaccia vera.

Un finto scritto a mano (non un `Mock`) puo' rinominare i suoi parametri
indipendentemente da chi imita: se il chiamante vero e il finto vengono
rinominati insieme, ALLA STESSA maniera sbagliata, la suite resta verde
mentre il contratto reale e' gia' rotto (fetta «la rinomina», Task 7 —
review indipendente, tre Critical: `casa/strumenti.py` chiamava
`Workshop.proponi`/`applica` con `origine=`/`turno=`/`adesso=` mentre il
finto in `test_costruzione_strumenti.py` accettava esattamente quei nomi,
non quelli veri).

Cosa confronta, e perche' fin qui e non oltre (review Task 7, round 3 --
la prima versione di questo file confrontava SOLO il conteggio dei
posizionali e i nomi keyword-only; il round 3 ha dimostrato tre buchi
concreti e li chiude cosi'):

1. **Conteggio dei posizionali** (compreso `self`): se non torna, il finto
   non si puo' nemmeno chiamare come il vero si aspetta.
2. **Nomi keyword-only**: un chiamante DEVE nominarli esattamente, quindi
   una deriva li' e' un `TypeError` vero -- e' il modo esatto in cui sono
   passati i tre Critical.
3. **Valori di default, sia sui keyword-only sia sui posizionali**: un
   finto che aggiunge un default dove il vero lo pretende obbligatorio e'
   PIU' permissivo del vero, e questo e' pericoloso nella direzione giusta
   da temere -- lascia verde un chiamante che omette un parametro che in
   produzione servirebbe (provato: dare a un finto `list(*, da_ts=None,
   ...)` quando il vero vuole `da_ts` obbligatorio resta verde senza
   questo controllo).
4. **Ordine dei nomi posizionali, ma SOLO quando ce ne sono due o piu'
   oltre `self`**: con un solo posizionale non esiste "ordine" da violare,
   e quel posizionale puo' chiamarsi diversamente nel finto (`intento`
   contro `intent`, `chiamata` contro `call`) senza rompere nessuna
   chiamata posizionale -- pretendere l'identita' li' darebbe falsi
   positivi che nessuno vuole correggere, la stessa ragione che aveva
   giustificato di restare ciechi sui nomi fin dal round 2. Ma con DUE o
   piu' posizionali l'ordine e' osservabile e pericoloso: `service(self,
   name, domain)` passerebbe qualunque controllo di conteggio o di
   default, e romperebbe ogni chiamante posizionale (era il caso reale di
   `_RegistroFinto.service(self, dominio, nome)` contro il vero
   `ServiceRegistry.service(self, domain, name)` -- stesso conteggio,
   stessi default, ordine e nomi diversi, guardia precedente verde).
   Con due o piu' posizionali quindi i NOMI, IN ORDINE, devono combaciare
   esattamente: e' l'unico modo per distinguere un ordine corretto da uno
   scambiato quando entrambi i parametri sono obbligatori e dello stesso
   tipo.

Deciso di restare ciechi sui nomi dei posizionali SOLO nel caso a un
parametro (punto 4): e' la scelta esplicita richiesta dalla review, scritta
qui perche' chi legge sappia cosa questa guardia non promette.
"""
import inspect

_VUOTO = object()  # sentinella: "nessun default", per distinguerlo da default=None


def kwonly(func) -> set[str]:
    """I nomi dei parametri keyword-only di `func`."""
    return {
        nome
        for nome, parametro in inspect.signature(func).parameters.items()
        if parametro.kind is inspect.Parameter.KEYWORD_ONLY
    }


def posizionali(func) -> int:
    """Quanti parametri di `func` si passano per posizione (`self` compreso)."""
    return len([
        p for p in inspect.signature(func).parameters.values()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                      inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ])


def _posizionali_dopo_self(func) -> list[inspect.Parameter]:
    parametri = [
        p for p in inspect.signature(func).parameters.values()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                      inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    return parametri[1:] if parametri and parametri[0].name in ("self", "cls") else parametri


def _default(parametro: inspect.Parameter):
    return _VUOTO if parametro.default is inspect.Parameter.empty else parametro.default


def assert_stessa_firma(reale, finto, *, nome: str = "") -> None:
    """Solleva con un messaggio leggibile se `finto` non chiama `reale` come
    `reale` si aspetta di essere chiamato: stesso numero di posizionali,
    stessi nomi keyword-only, stessi default (su entrambi), e stesso ordine
    dei nomi posizionali quando sono due o piu'. Vedi il docstring del
    modulo per cosa NON copre e perche'."""
    etichetta = nome or getattr(reale, "__qualname__", str(reale))
    firma_reale = inspect.signature(reale)
    firma_finta = inspect.signature(finto)

    assert posizionali(reale) == posizionali(finto), (
        f"{etichetta}: il finto ha {posizionali(finto)} posizionali, "
        f"il vero {posizionali(reale)}")

    pos_reale = _posizionali_dopo_self(reale)
    pos_finta = _posizionali_dopo_self(finto)
    if len(pos_reale) >= 2:
        nomi_reale = tuple(p.name for p in pos_reale)
        nomi_finta = tuple(p.name for p in pos_finta)
        assert nomi_reale == nomi_finta, (
            f"{etichetta}: con due o piu' posizionali l'ordine/nome conta -- "
            f"il finto ha {nomi_finta}, il vero {nomi_reale}")
    for p_reale, p_finta in zip(pos_reale, pos_finta):
        assert _default(p_reale) == _default(p_finta), (
            f"{etichetta}: il posizionale «{p_reale.name}» ha default "
            f"{_default(p_reale)!r} nel vero e {_default(p_finta)!r} nel finto")

    assert kwonly(reale) == kwonly(finto), (
        f"{etichetta}: il finto porta {sorted(kwonly(finto))}, "
        f"il vero si aspetta {sorted(kwonly(reale))}")
    for nome_kw in kwonly(reale):
        d_reale = _default(firma_reale.parameters[nome_kw])
        d_finta = _default(firma_finta.parameters[nome_kw])
        assert d_reale == d_finta, (
            f"{etichetta}: il keyword-only «{nome_kw}» ha default "
            f"{d_reale!r} nel vero e {d_finta!r} nel finto -- un finto piu' "
            "permissivo del vero lascia verde un chiamante che omette un "
            "parametro obbligatorio")
