"""La copia di un registro caduto porta il suo istante (S-36, Tappa 8, Task 1).

`_carried_over` tiene al posto di un registro che non ha risposto la tabella
della ricostruzione di prima, e il nome resta in `unavailable`. Fino
all'08/10/2026 non diceva DA QUANDO: una copia di un'ora fa e una di tre
giorni fa erano la stessa riga. Le guardie della riconciliazione la leggono
come illeggibile (`mind/reconciliation.py`), e la pagina dell'anagrafe dice
l'istante (`non_disponibili_letti_il`).

Mutazione ESEGUITA: in `hold_registries` l'istante preso sempre dalla
ricostruzione di prima (senza guardare la copia gia' tenuta) -- rossa
`test_una_seconda_caduta_tiene_l_istante_della_prima_copia`.
"""
from datetime import UTC, datetime

import pytest

from hiris.app.home_space import reader
from hiris.app.home_space.reader import HomeSpace

_REGISTRI = {"piani": [], "aree": [{"area_id": "cucina", "name": "Cucina"}],
             "dispositivi": [], "entita": [], "etichette": [], "categorie": [],
             "integrazioni": []}


class _Orologio:
    """`reader.datetime` con un `now` che si sposta a comando."""
    adesso = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        return cls.adesso


@pytest.fixture
def anagrafe(tmp_path, monkeypatch):
    monkeypatch.setattr(reader, "datetime", _Orologio)
    _Orologio.adesso = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
    return HomeSpace(str(tmp_path))


def test_mai_letto_non_ha_copia(anagrafe):
    anagrafe.hold_registries(dict(_REGISTRI), unavailable=["aree"])
    assert anagrafe.unavailable_since() == {"aree": None}


def test_la_copia_porta_l_istante_della_lettura_buona(anagrafe):
    anagrafe.hold_registries(dict(_REGISTRI))
    _Orologio.adesso = datetime(2026, 10, 8, 7, 0, tzinfo=UTC)
    anagrafe.hold_registries({**_REGISTRI, "aree": []}, unavailable=["aree"])
    assert anagrafe.read()["aree"], "la copia di prima resta"
    assert anagrafe.unavailable_since() == {"aree": "2026-10-08T06:00:00+00:00"}


def test_una_seconda_caduta_tiene_l_istante_della_prima_copia(anagrafe):
    anagrafe.hold_registries(dict(_REGISTRI))
    _Orologio.adesso = datetime(2026, 10, 8, 7, 0, tzinfo=UTC)
    anagrafe.hold_registries({**_REGISTRI, "aree": []}, unavailable=["aree"])
    _Orologio.adesso = datetime(2026, 10, 8, 8, 0, tzinfo=UTC)
    anagrafe.hold_registries({**_REGISTRI, "aree": []}, unavailable=["aree"])
    assert anagrafe.unavailable_since() == {"aree": "2026-10-08T06:00:00+00:00"}


def test_riletto_esce_dalle_copie(anagrafe):
    anagrafe.hold_registries(dict(_REGISTRI))
    anagrafe.hold_registries({**_REGISTRI, "aree": []}, unavailable=["aree"])
    anagrafe.hold_registries(dict(_REGISTRI))
    assert anagrafe.unavailable_since() == {}
