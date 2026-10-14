"""Il nucleo chiede i nomi dei dispositivi alla casa del turno (A-16).

Fino al 14/10/2026 `briefing.compose` rifaceva l'indice id -> nome dei
dispositivi dall'anagrafe, accanto a quello che `House` tiene gia'
(`House.device`). Ora le annotazioni dei conteggi («4 valve (Irrigazione)»)
chiedono `House.name("dispositivo", id)`, e la casa che il chiamante passa e'
la stessa da cui vengono anagrafe, registri caduti e albero.

F11 della Chiusura (14/10/2026).
"""
import copy

from hiris.app.home_space.house import House
from hiris.app.home_space.topology import Mirror
from tests.test_briefing import _CASA, _COMPORTAMENTO, _RICORDI, _STATO, compose


def _casa_irrigata() -> dict:
    casa = copy.deepcopy(_CASA)
    casa["dispositivi"] = [{"id": "dev1", "nome": "Irrigazione giardino"}]
    casa["entita"] += [
        {"id": f"valve.v{i}", "nome": f"Valvola {i}", "area_id": "sala",
         "dispositivo_id": "dev1", "classe": None, "unita": None, "disabilitata": 0}
        for i in range(4)]
    return casa


class _CasaParlante(House):
    """Una casa che risponde al nome del dispositivo con un nome suo: se il
    nucleo lo stampa, l'ha chiesto a lei e non all'anagrafe."""

    def name(self, kind, identifier):
        if kind == "dispositivo":
            return "Detto dalla casa"
        return super().name(kind, identifier)


def test_il_nucleo_chiede_il_nome_del_dispositivo_alla_casa_del_turno():
    """Mutazione ESEGUITA (14/10/2026): rimesso in `compose` l'indice
    `{d["id"]: device_name(d) for d in home_space["dispositivi"]}` -- rossa,
    la riga dice «Irrigazione giardino» invece del nome della casa."""
    casa = _casa_irrigata()
    testo, _ = compose(casa, _COMPORTAMENTO, _RICORDI, _STATO,
                       house=_CasaParlante(casa, Mirror()))
    assert "4 valvole (Detto dalla casa)" in testo, testo


def test_il_nome_e_quello_del_registro_dei_dispositivi():
    """Con la casa costruita dalla stessa anagrafe (`tests.test_briefing.
    compose`), il nome resta quello del registro."""
    testo, _ = compose(_casa_irrigata(), _COMPORTAMENTO, _RICORDI, _STATO)
    assert "4 valvole (Irrigazione giardino)" in testo, testo


def test_col_registro_dispositivi_caduto_la_casa_non_viene_interrogata():
    """«Non ho potuto guardare» non e' «nessun nome»: col registro caduto
    l'annotazione tace, e la casa non viene nemmeno chiesta."""
    chieste: list[str] = []

    class _CasaContatrice(House):
        def name(self, kind, identifier):
            chieste.append(kind)
            return super().name(kind, identifier)

    casa = _casa_irrigata()
    testo, _ = compose(casa, _COMPORTAMENTO, _RICORDI, _STATO,
                       unavailable=("dispositivi",),
                       house=_CasaContatrice(casa, Mirror(), ("dispositivi",)))
    assert "dispositivo" not in chieste
    assert "(Irrigazione giardino)" not in testo
