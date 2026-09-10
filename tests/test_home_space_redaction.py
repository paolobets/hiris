"""I segreti si oscurano al confine, con lo stesso segnaposto di sempre.

**Perche' esiste questo confine.** Finche' HIRIS leggeva le automazioni dal
file, `!secret` non veniva risolto: `yaml_loader` lo rendeva `<secret nome>` --
«il valore vero non lo conosciamo, sta apposta altrove». Dal 10/09/2026 il
corpo di un'automazione si legge da Home Assistant (`automation/config`), e li'
il YAML e' **gia' risolto**: verificato sul sorgente della libreria che HA usa
(`annotatedyaml/loader.py`), `secret_yaml` torna `secrets[secret]` -- il valore
vero -- e `components/config/automation.py` non oscura niente.

Quindi il segnaposto tocca a noi, e **la fonte di cosa sia segreto e'
`secrets.yaml`**: e' il posto in cui il proprietario ha dichiarato cosa e'
segreto. Indovinare dai nomi delle chiavi (`password`, `token`, `api_key`)
sbaglierebbe in silenzio, ed e' proprio cio' che il corollario di `CLAUDE.md`
vieta: quando HA ha una fonte dichiarativa, quella e' la risposta.
"""
import pytest
import yaml

from hiris.app.home_space.redaction import SecretSeal

_SEGRETI = {
    "notify_token": "abc123-token-vero",
    "casa_wifi": "una password lunga",
    "webhook": "wh_9f3a",
}


@pytest.fixture
def sigillo(tmp_path):
    percorso = tmp_path / "secrets.yaml"
    percorso.write_text(yaml.safe_dump(_SEGRETI), encoding="utf-8")
    return SecretSeal.from_file(percorso)


def test_un_valore_segreto_diventa_il_segnaposto_col_suo_nome(sigillo):
    """Lo stesso identico segnaposto che produceva il lettore di file: la
    forma non cambia da nessuna delle due porte (fondamenta 3).

    Mutazione che la uccide: scrivere un segnaposto generico (`<secret>`)
    senza il nome -- chi legge perderebbe QUALE segreto serve li'.
    """
    assert sigillo.redact("abc123-token-vero") == "<secret notify_token>"


def test_il_segreto_si_trova_dovunque_sia_annidato(sigillo):
    """Il confronto e' sul VALORE, non sulla chiave: un segreto in fondo a una
    lista dentro un dizionario e' un segreto uguale.

    Mutazione che la uccide: guardare solo il primo livello del dizionario.
    """
    config = {"alias": "Avvisa", "actions": [
        {"action": "notify.telegram",
         "data": {"token": "abc123-token-vero", "message": "ciao"}},
        {"action": "webhook", "data": {"id": "wh_9f3a"}}]}

    pulita = sigillo.redact(config)

    assert pulita["actions"][0]["data"]["token"] == "<secret notify_token>"
    assert pulita["actions"][0]["data"]["message"] == "ciao"
    assert pulita["actions"][1]["data"]["id"] == "<secret webhook>"
    assert pulita["alias"] == "Avvisa"


def test_cio_che_non_e_dichiarato_segreto_non_si_tocca(sigillo):
    """Oscurare troppo e' l'altra meta' del difetto: un'automazione illeggibile
    non si puo' ne' capire ne' spiegare. Si oscura **solo** cio' che il
    proprietario ha dichiarato segreto."""
    config = {"trigger": [{"platform": "time", "at": "07:00"}],
              "note": "la password e' nel cassetto"}

    assert sigillo.redact(config) == config


def test_il_sigillo_non_conserva_i_valori_in_chiaro(sigillo):
    """**I valori servono solo a confrontare.** Del segreto si tiene
    l'impronta, non il testo: cosi' un dump dell'oggetto, un log di eccezione
    o un `repr` finito in un rapporto non possono ripubblicarlo.

    Mutazione che la uccide: tenere `{valore: nome}` invece di
    `{impronta: nome}` -- il valore vero comparirebbe nello stato dell'oggetto.
    """
    testo = repr(sigillo) + repr(sigillo.__dict__)

    for valore in _SEGRETI.values():
        assert valore not in testo


def test_senza_il_file_dei_segreti_il_sigillo_lo_dichiara(tmp_path):
    """**Se non si e' potuto controllare, non si indovina.** Un sigillo che
    non ha letto niente e uno che ha letto una casa senza segreti direbbero
    entrambi «niente da oscurare», e sono due fatti diversi: chi chiama deve
    poterli distinguere per decidere se archiviare un corpo o dichiarare un
    buco.

    Mutazione che la uccide: far tornare `readable = True` quando il file
    manca.
    """
    assente = SecretSeal.from_file(tmp_path / "non_c_e.yaml")
    vuoto = SecretSeal.from_file(_scrivi(tmp_path, "vuoto.yaml", {}))

    assert assente.readable is False
    assert vuoto.readable is True
    assert assente.redact("qualunque cosa") == "qualunque cosa"


def test_un_file_dei_segreti_illeggibile_non_e_un_file_assente(tmp_path):
    """Un `secrets.yaml` rotto e' un guasto di adesso, non un'assenza: si
    dichiara non leggibile, esattamente come se non ci fosse, invece di
    sollevare e fermare la lettura del comportamento."""
    rotto = tmp_path / "secrets.yaml"
    rotto.write_text("chiave: [non chiusa\n", encoding="utf-8")

    assert SecretSeal.from_file(rotto).readable is False


def _scrivi(tmp_path, nome, contenuto):
    percorso = tmp_path / nome
    percorso.write_text(yaml.safe_dump(contenuto), encoding="utf-8")
    return percorso
