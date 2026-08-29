"""Guardia contro i doppi che divergono in silenzio dall'interfaccia vera.

Un finto scritto a mano (non un `Mock`) puo' rinominare i suoi parametri
indipendentemente da chi imita: se il chiamante vero e il finto vengono
rinominati insieme, ALLA STESSA maniera sbagliata, la suite resta verde
mentre il contratto reale e' gia' rotto (fetta «la rinomina», Task 7 —
review indipendente, tre Critical: `casa/strumenti.py` chiamava
`Workshop.proponi`/`applica` con `origine=`/`turno=`/`adesso=` mentre il
finto in `test_costruzione_strumenti.py` accettava esattamente quei nomi,
non quelli veri).

Confronta SOLO i parametri keyword-only (quelli dopo `*`): sono quelli che
un chiamante deve nominare esattamente, quindi quelli su cui una deriva e'
un `TypeError` vero. I parametri posizionali possono chiamarsi diversamente
nel finto (`intento` contro `intent`) senza rompere nessuna chiamata
posizionale -- confrontarli per nome darebbe falsi positivi che nessuno
vuole correggere.
"""
import inspect


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


def assert_stessa_firma(reale, finto, *, nome: str = "") -> None:
    """Solleva con un messaggio leggibile se `finto` non chiama `reale` come
    `reale` si aspetta di essere chiamato: stesso numero di posizionali,
    stessi nomi keyword-only."""
    etichetta = nome or getattr(reale, "__qualname__", str(reale))
    assert posizionali(reale) == posizionali(finto), (
        f"{etichetta}: il finto ha {posizionali(finto)} posizionali, "
        f"il vero {posizionali(reale)}")
    assert kwonly(reale) == kwonly(finto), (
        f"{etichetta}: il finto porta {sorted(kwonly(finto))}, "
        f"il vero si aspetta {sorted(kwonly(reale))}")
