"""Lo specchio dello stato delle prove: lo specchio VERO (T-02, T-04, 14/10/2026).

Fino a oggi ogni file di prova si scriveva il suo specchio finto: misurate
il 14/10/2026, 37 classi con un `all_states()` in 25 file, 7 delle quali
poggiavano su `MirrorById` (`tests/_mirror_by_id.py`, uscito con loro).
Ognuna imitava a mano la forma di `EntityCache` -- e quasi nessuna la aveva
intera: chi solo `all_states()`, chi anche `loaded`, nessuna le domande per id
(`get`, `states_for`) se non per ereditarieta' da `MirrorById`.

`SpecchioFinto` E' un `EntityCache`, come `CasaFinta` e' un `HAClient`: non
imita nessun metodo. Le righe arrivano dagli stati GREZZI di Home Assistant
(`raw_state`, la forma di `GET /api/states`) attraverso il rubinetto vero
(`on_state_changed`), quindi passano per la proiezione vera (`_to_minimal`):
`loaded`, `stale`, `get`, `states_for`, `all_states` e la forma di ogni riga
sono quelli del prodotto per costruzione, e un metodo nuovo dello specchio
arriva qui per ereditarieta'.

Chi deve contare le letture o rompere lo specchio a comando lo fa con una
sottoclasse che sovrascrive il metodo che gli serve, e lo dice.
"""
from __future__ import annotations

from collections.abc import Iterable

from hiris.app.proxy.entity_cache import EntityCache
from tests._casa_sintetica import raw_state

__all__ = ["SpecchioFinto", "raw_state"]


class SpecchioFinto(EntityCache):
    """Lo specchio vero, riempito con `stati` (righe grezze, `raw_state`).

    `pronto` e' la bandiera `loaded`: `False` e' lo specchio la cui prima
    lettura non e' arrivata in fondo (`inventory_is_readable` lo dice non
    leggibile), anche se qualche evento ha gia' portato delle righe."""

    def __init__(self, stati: Iterable[dict] = (), *, pronto: bool = True) -> None:
        super().__init__()
        for grezzo in stati:
            self.on_state_changed({"entity_id": grezzo["entity_id"], "new_state": grezzo})
        self._loaded = pronto
