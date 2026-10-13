"""Le righe annidate di una scheda si rendono solo se entrano (Tappa 9, F7;
D-53), e gli attributi di un'entita' si leggono una volta (D-52).
"""
from hiris.app.home_space import queries, render
from hiris.app.home_space.house import House
from hiris.app.home_space.topology import Mirror

QUANTE = queries.ROWS_MAX + 30


def _casa() -> House:
    casa = {
        "piani": [], "aree": [{"id": "garage", "nome": "Garage", "alias": [],
                               "etichette": []}],
        "dispositivi": [{"id": "nvr", "nome": "NVR", "area_id": "garage"}],
        "entita": [{"id": f"camera.c{n:03d}", "area_id": "garage",
                    "dispositivo_id": "nvr", "piattaforma": "onvif",
                    **({"nascosta": 1} if n % 2 else {})}
                   for n in range(QUANTE)],
        "etichette": [], "categorie": [], "integrazioni": [],
    }
    return House(casa, Mirror({}))


def _contate(monkeypatch, nome: str) -> list:
    chiamate: list = []
    originale = getattr(queries if nome == "render_entity" else render, nome)

    def contata(*args, **kwargs):
        chiamate.append(args)
        return originale(*args, **kwargs)
    monkeypatch.setattr(queries if nome == "render_entity" else render, nome, contata)
    return chiamate


def test_righe_eccedenti_non_rese(monkeypatch):
    """D-53: la scheda di un'area o di un dispositivo rendeva TUTTE le sue
    entita' e poi ne teneva `ROWS_MAX`. Sulla casa vera l'area Telecamere ne
    porta 287: 237 rese per niente. Ora si sceglie prima, e si rende solo cio'
    che entra; la scheda e' la stessa.

    Rossa prima: `QUANTE` rese per scheda. Mutazione ESEGUITA: rendere tutte
    le righe prima del taglio -- rossa col numero."""
    casa = _casa()
    for genere, ref in (("area", "garage"), ("dispositivo", "nvr")):
        rese = _contate(monkeypatch, "render_entity")
        scheda = queries.view(casa, [], [], genere, ref)
        assert len(rese) == queries.ROWS_MAX, (genere, len(rese))
        tenute = scheda["entita"] + scheda.get("entita_nascoste", [])
        assert len(tenute) == queries.ROWS_MAX
        lasciate = scheda["oltre"]
        assert lasciate["restano"] == QUANTE - queries.ROWS_MAX
        monkeypatch.undo()


def test_attributi_entita_letti_una_volta(monkeypatch):
    """D-52: la scheda di un'entita' ricalcolava gli attributi da mostrare tre
    volte (stato in parole, funzioni, comandi). Dalla resa unica (Tappa 9, F2)
    `render_entity` li legge una volta e li passa.

    Mutazione ESEGUITA: una seconda `disclosable_attributes` per i comandi --
    rossa con 2."""
    lette = _contate(monkeypatch, "disclosable_attributes")
    queries.view(_casa(), [], [], "entita", "camera.c000")
    assert len(lette) == 1, len(lette)
