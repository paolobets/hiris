import pytest

from hiris.app.memoria.archivio import ArchivioMemoria

_FRASE = "d'inverno la sala da pranzo la preferisco fra 19 e 20 gradi quando sono a casa"


@pytest.fixture
def memoria(tmp_path):
    m = ArchivioMemoria(str(tmp_path / "memoria.db"))
    yield m
    m.chiudi()


def test_un_ricordo_nudo_si_salva_e_si_rilegge(memoria):
    """Regola 3: la struttura e' opzionale. Una frase senza interpretazione
    resta un ricordo intero, non un ricordo a meta'."""
    memoria.ricorda("il modulo meteo esterno e' guasto", detto_da="paolo")
    ricordi = memoria.richiama()
    assert ricordi[0]["testo"] == "il modulo meteo esterno e' guasto"
    assert ricordi[0]["detto_da"] == "paolo"
    assert ricordi[0]["ancore"] == []
    assert ricordi[0]["condizioni"] == []
    assert ricordi[0]["forza"] is None


def test_un_ricordo_interpretato_conserva_tutto(memoria):
    memoria.ricorda(
        _FRASE, detto_da="paolo",
        ancore=[{"tipo": "area", "riferimento": "sala_pranzo", "nome_visto": "sala da pranzo"}],
        condizioni=[{"tipo": "stagione", "valore": "inverno"},
                    {"tipo": "presenza", "valore": "casa"}],
        forza="preferenza", grandezza="temperature", minimo=19.0, massimo=20.0, unita="°C",
    )
    r = memoria.richiama()[0]
    assert r["testo"] == _FRASE                      # regola 1: il testo e' la verita'
    assert r["forza"] == "preferenza"
    assert (r["minimo"], r["massimo"], r["unita"]) == (19.0, 20.0, "°C")
    assert [a["riferimento"] for a in r["ancore"]] == ["sala_pranzo"]
    assert {c["tipo"] for c in r["condizioni"]} == {"stagione", "presenza"}


def test_si_trovano_i_ricordi_di_una_parte_della_casa(memoria):
    """«Quali preferenze riguardano la sala da pranzo?» deve avere risposta:
    e' il punto per cui le ancore esistono."""
    memoria.ricorda(_FRASE, detto_da="paolo",
                    ancore=[{"tipo": "area", "riferimento": "sala_pranzo", "nome_visto": "sala"}])
    memoria.ricorda("in cucina niente luci dopo le 23", detto_da="paolo",
                    ancore=[{"tipo": "area", "riferimento": "cucina", "nome_visto": "cucina"}])
    assert [r["testo"] for r in memoria.per_ancora("sala_pranzo")] == [_FRASE]


def test_correggere_l_interpretazione_non_tocca_il_testo(memoria):
    """Regola 2: si corregge cio' che HIRIS ha capito, lasciando la frase
    intatta. Il testo e' la verita' e non lo riscrive nessuno."""
    ident = memoria.ricorda(_FRASE, detto_da="paolo", forza="fatto", massimo=25.0)
    memoria.correggi(ident, forza="preferenza", massimo=20.0)
    r = memoria.richiama()[0]
    assert r["testo"] == _FRASE
    assert r["forza"] == "preferenza"
    assert r["massimo"] == 20.0
    assert r["corretto_da_utente"] == 1


def test_correggere_le_ancore_le_sostituisce_tutte(memoria):
    ident = memoria.ricorda(_FRASE, detto_da="paolo",
                            ancore=[{"tipo": "area", "riferimento": "sbagliata",
                                     "nome_visto": "sala"}])
    memoria.correggi(ident, ancore=[{"tipo": "area", "riferimento": "sala_pranzo",
                                     "nome_visto": "sala da pranzo"}])
    assert [a["riferimento"] for a in memoria.richiama()[0]["ancore"]] == ["sala_pranzo"]


def test_dimenticare_toglie_anche_ancore_e_condizioni(memoria):
    ident = memoria.ricorda(_FRASE, detto_da="paolo",
                            ancore=[{"tipo": "area", "riferimento": "sala_pranzo",
                                     "nome_visto": "sala"}],
                            condizioni=[{"tipo": "stagione", "valore": "inverno"}])
    memoria.dimentica(ident)
    assert memoria.richiama() == []
    assert memoria.per_ancora("sala_pranzo") == []


def test_la_memoria_non_evapora(memoria):
    """Contratto §1: niente scadenza. Non esiste nessun campo che la faccia
    sparire, e questo test esiste perche' nella 1.x c'era e ha fatto danni."""
    memoria.ricorda("una cosa vecchissima", detto_da="paolo")
    colonne = {r[1] for r in memoria._conn.execute("PRAGMA table_info(ricordi)")}
    assert "valid_until" not in colonne and "scade_il" not in colonne
    assert len(memoria.richiama()) == 1


def test_un_salvataggio_a_meta_non_lascia_un_ricordo_monco(memoria):
    memoria.ricorda("prima frase", detto_da="paolo")
    with pytest.raises(Exception):
        memoria.ricorda("seconda", detto_da="paolo",
                        ancore=[{"tipo": "area"}])       # manca `riferimento`
    assert [r["testo"] for r in memoria.richiama()] == ["prima frase"]
