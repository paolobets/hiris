"""L'anagrafe delle prove: l'anagrafe VERA (N160-2, 14/10/2026).

Fino a oggi ogni file di prova si scriveva il suo `app[HOME_SPACE_KEY]`:
misurate il 14/10/2026, 17 classi in 13 file definivano a mano `read`,
`unavailable`, `energy`, `reference_frame` o `behavior` di `HomeSpace`, con
risposte inventate da ognuna (chi `[]`, chi `()` per i registri caduti; chi
`{}`, chi un'anagrafe di tabelle vuote per «mai letta»).

`AnagrafeFinta` E' un `HomeSpace`, come `SpecchioFinto` e' un `EntityCache`:
non imita nessun metodo. L'anagrafe arriva dalla porta vera (`hold`), e la
cornice (`reference_frame`) dal file in cui il prodotto la conserva fra un
riavvio e l'altro, scritto in una cartella temporanea sua prima di aprirla.
`read`, `unavailable`, `energy`, `behavior`, `reference_frame` e la forma di
ognuno sono quelli del prodotto per costruzione.

Chi deve rompere un metodo a comando lo fa con una sottoclasse che lo
sovrascrive, e lo dice. Il cancello e' `tests/test_finte_condivise.py`.
"""
from __future__ import annotations

import json
import os
import tempfile

from hiris.app.home_space.reader import REFERENCE_FRAME_FILE, HomeSpace


class AnagrafeFinta(HomeSpace):
    """L'anagrafe vera.

    - `anagrafe`: le tabelle (`entita`, `aree`, ...) prese in consegna con
      `hold`; `None` e' l'anagrafe mai letta (`read()` restituisce `{}`).
    - `cornice`: il sistema di riferimento (`fuso`, `versione_ha`, ...), come
      lo trova all'avvio.
    - `registri_caduti`: i registri che non hanno risposto (`unavailable`).
    - `mirror`: lo specchio, per `behavior()`.
    """

    def __init__(self, anagrafe: dict | None = None, *, cornice: dict | None = None,
                 registri_caduti: list[str] | tuple = (), mirror=None) -> None:
        self._cartella = tempfile.TemporaryDirectory(prefix="hiris-anagrafe-finta-")
        if cornice is not None:
            with open(os.path.join(self._cartella.name, REFERENCE_FRAME_FILE), "w",
                      encoding="utf-8") as f:
                json.dump(cornice, f)
        super().__init__(self._cartella.name, mirror=mirror)
        if anagrafe is not None:
            self.hold(anagrafe, unavailable=list(registri_caduti))
