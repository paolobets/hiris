"""Leggere i file di configurazione di Home Assistant senza inciampare.

HA usa tag YAML propri — `!secret`, `!include`, `!input` — che `safe_load`
rifiuta sollevando. Un solo `!secret` in `automations.yaml` farebbe fallire la
lettura di TUTTE le automazioni, e il guasto arriverebbe a chi legge come
«nessuna automazione»: un silenzio travestito da dato.

Qui i tag sconosciuti diventano un segnaposto leggibile invece di un'eccezione.
Il valore vero non lo conosciamo — `!secret` sta apposta altrove — ma **si vede
che c'era qualcosa**, e questo basta a chi deve capire cosa fa un'automazione.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class _CaricatoreHA(yaml.SafeLoader):
    """SafeLoader che tollera i tag di Home Assistant.

    **Eredita da SafeLoader, non da Loader**, e questo non e' un dettaglio: e'
    cio' che impedisce a `!!python/object/apply:os.system` di eseguire codice.
    I tag `!!python/...` si risolvono in `tag:yaml.org,2002:python/...`, che
    NON comincia per `!` e quindi non arriva mai al costruttore permissivo qui
    sotto: resta rifiutato da SafeLoader.
    """


def _tag_sconosciuto(loader: yaml.Loader, suffisso: str, nodo: yaml.Node) -> str:
    """Un tag che non conosciamo diventa il suo nome, non un'eccezione.

    Restituisce **sempre una stringa** e non costruisce mai un oggetto: anche
    se un giorno un tag inatteso finisse qui, il peggio che puo' succedere e'
    un segnaposto di troppo.
    """
    if isinstance(nodo, yaml.ScalarNode):
        return f"<{suffisso} {nodo.value}>"
    return f"<{suffisso}>"


# Solo i tag che cominciano per `!` — quelli di Home Assistant. Il namespace
# `tag:yaml.org,2002:` (dove vivono i `!!python/...`) non e' coperto, e resta
# in mano a SafeLoader, che lo rifiuta. C'e' un test che lo dimostra.
_CaricatoreHA.add_multi_constructor("!", _tag_sconosciuto)


def carica_yaml(testo: str) -> Any:
    """Il contenuto del testo YAML. Solleva se il testo e' malformato.

    Solleva di proposito: restituire una lista vuota renderebbe un file rotto
    indistinguibile da un file senza automazioni, e chi legge ci costruirebbe
    sopra.
    """
    return yaml.load(testo, Loader=_CaricatoreHA)


def carica_file(percorso: Path) -> Any:
    """Il contenuto del file, o `None` se il file non esiste.

    `None` e `[]` sono cose diverse: «non c'e' nessun file delle automazioni»
    e «il file c'e' ed e' vuoto» dicono due cose diverse sulla casa.
    """
    if not percorso.exists():
        return None
    contenuto = carica_yaml(percorso.read_text(encoding="utf-8-sig", errors="replace"))
    return [] if contenuto is None else contenuto
