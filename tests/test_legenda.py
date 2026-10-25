"""La legenda: come si legge una risposta di `search` e di `history`, detto
nella risposta (Fase 2 dello sprint «Il giro snello», 25/10/2026).

Le frasi stavano nelle descrizioni dei due strumenti e partivano a ogni giro;
ora `home_space/legend.py` le aggiunge a una risposta solo per le chiavi che
quella risposta porta.

Mutazioni ESEGUITE il 25/10/2026:
- `with_legend` che torna `answer` com'e' -- rosse le due prove sul
  dispatcher (search e history);
- la frase di `volte` rimessa anche nella descrizione di `history` -- rossa
  `test_nessuna_frase_della_legenda_sta_anche_in_una_descrizione`, col nome;
- `_keys` che scende anche dentro `membri` -- rossa la prova sui membri.
"""
from __future__ import annotations

import pytest

from hiris.app.home_space.legend import READINGS, legend, with_legend
from hiris.app.home_space.tools import KNOWLEDGE_TOOLS, ToolDispatcher
from tests.test_history_tool import _house

# Le finte di `test_knowledge_tools`: importate, non ricopiate.
from tests.test_knowledge_tools import archivio_casa, dispatcher, memoria  # noqa: F401


def _text(reading) -> str:
    return reading if isinstance(reading, str) else ""


def test_la_tabella_non_e_vuota():
    """La derivazione qui sotto guarda le frasi della tabella: una tabella
    vuota renderebbe verdi le prove senza guardare niente."""
    assert len(READINGS) >= 10, sorted(map(str, READINGS))


def test_solo_le_chiavi_che_escono_portano_la_loro_frase():
    oraria = {"trovate": 1, "grana": "oraria", "voci": [{"id": "sensor.x", "dal": "..."}]}
    assert legend(oraria) == {"grana": READINGS[("grana", "oraria")],
                              "dal": READINGS["dal"]}
    assert legend({"trovate": 1, "voci": [{"id": "sensor.x", "stato": "on"}]}) == {}


def test_le_grane_diverse_si_dicono_tutte_e_due():
    risposta = {"grana": "per serie",
                "voci": [{"id": "a", "grana": "oraria"}, {"id": "b", "grana": "dettaglio"}]}
    frase = legend(risposta)["grana"]
    for valore in ("per serie", "oraria", "dettaglio"):
        assert READINGS[("grana", valore)] in frase, valore


def test_i_punti_di_una_riga_si_guardano():
    risposta = {"voci": [{"id": "sensor.x", "punti": [{"cambio": 1, "somma": 4}]}]}
    assert set(legend(risposta)) == {"cambio", "somma"}


def test_dentro_i_membri_la_stessa_parola_non_si_spiega():
    """`membri.non_letti` sono i membri di un gruppo non letti, non le
    esecuzioni: la legenda non scende li'."""
    risposta = {"voci": [{"id": "light.gruppo", "membri": {"non_letti": ["light.a"]}}]}
    assert legend(risposta) == {}


def test_una_risposta_con_errore_resta_com_e():
    errore = {"errore": "Home Assistant non ha risposto", "grana": "oraria"}
    assert with_legend(errore) is errore


def test_nessuna_frase_della_legenda_sta_anche_in_una_descrizione():
    """La ragione della legenda: una frase in un posto solo. Le descrizioni
    si chiedono al catalogo, schema compreso."""
    import json

    catalogo = json.dumps(KNOWLEDGE_TOOLS, ensure_ascii=False)
    doppie = [chiave for chiave, frase in READINGS.items() if _text(frase) in catalogo]
    assert doppie == []


@pytest.mark.asyncio
async def test_history_porta_la_legenda_dal_dispatcher():
    registro = [{"level": "ERROR", "name": "homeassistant.components.zha",
                 "message": ["timeout"], "count": 3}]
    d = ToolDispatcher(None, None, ha=_house(registro=registro))
    esito = await d.dispatch("history", {"cosa": "errori"})
    assert esito["legenda"]["volte"] == READINGS["volte"]


@pytest.mark.asyncio
async def test_search_porta_la_legenda_dal_dispatcher(dispatcher):
    """Una ricerca per nome che non trova niente: `nulla_riconosciuto` si
    spiega nella risposta, non piu' nella descrizione di `search`."""
    esito = await dispatcher.dispatch("search", {"nome": "xyzzy qwerty"})
    assert esito.get("nulla_riconosciuto") is True, esito
    assert esito["legenda"]["nulla_riconosciuto"] == READINGS["nulla_riconosciuto"]
