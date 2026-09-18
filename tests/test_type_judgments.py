"""L'istantanea dei giudizi sui tipi (spec 2026-09-16 §3)."""
import pytest

from hiris.app.home_space.type_judgments import (
    NO_GENRE,
    JudgmentError,
    TypeJudgments,
)
from hiris.app.home_space.type_vocabulary import ABSENT_STATE_FORMS

GENERI = ("funzionamento", "presenza", "guasto", "sicurezza")


def _j(*rows):
    return TypeJudgments.from_rows(rows, genres=GENERI,
                                   absent_forms=ABSENT_STATE_FORMS.value)


def test_il_genere_si_cerca_dall_entita_alla_coppia_al_dominio():
    """Mutazione: invertire l'ordine della ricerca (dominio prima) -- rossa
    sulla seconda e sulla terza asserzione."""
    j = _j(("tipo", "binary_sensor", "genere", NO_GENRE),
           ("tipo", "binary_sensor.occupancy", "genere", "presenza"),
           ("entita", "binary_sensor.fp2", "genere", "sicurezza"))
    assert j.genre_of("binary_sensor.porta", None) is None
    assert j.genre_of("binary_sensor.fp300", "occupancy") == "presenza"
    assert j.genre_of("binary_sensor.fp2", "occupancy") == "sicurezza"


def test_nessuno_NEGA_il_livello_sopra_e_l_assenza_eredita():
    """`nessuno` e' un giudizio, l'assenza della riga no. Mutazione: trattare
    `nessuno` come assenza -- rossa, torna `funzionamento`."""
    j = _j(("tipo", "switch", "genere", "funzionamento"),
           ("entita", "switch.accesso_internet", "genere", NO_GENRE))
    assert j.genre_of("switch.presa", None) == "funzionamento"
    assert j.genre_of("switch.accesso_internet", None) is None


def test_il_riposo_e_del_SOGGETTO_e_non_contiene_le_forme_assenti():
    """`none` e il vuoto non sono un riposo (spec §5): non escono dalla lettura
    e, scritti dentro un riposo, rendono storta la riga (spec §3, decisione del
    controllore al giro di correzione 1). Le forme sono quelle VERE del
    vocabolario, `ABSENT_STATE_FORMS`, passate come dato.

    Mutazioni: (a) aggiungere `{"", "none"}` al risultato di `resting_of` --
    rossa; (b) togliere da `_parse` il rifiuto delle forme assenti -- rossa,
    le due righe entrano e la costruzione non solleva; (c) in `from_rows`
    rifiutare solo `none` (`absent = frozenset(absent_forms) - {""}`) -- rossa
    su `len(e.rows) == 2`."""
    j = _j(("tipo", "person", "riposo", '["home"]'),
           ("tipo", "binary_sensor", "riposo", '["off"]'))
    assert j.resting_of("person") == frozenset({"home"})
    assert j.resting_of("binary_sensor", "occupancy") == frozenset({"off"})
    assert "none" not in j.resting_of("person")
    with pytest.raises(JudgmentError) as e:
        _j(("tipo", "person", "riposo", '["home", "none"]'),
           ("tipo", "switch", "riposo", '["off", ""]'))
    assert len(e.value.rows) == 2


def test_un_valore_storto_ferma_la_costruzione_ELENCANDO_tutte_le_righe():
    """Si vede all'avvio, tutto insieme. Mutazione: sollevare alla prima riga
    storta invece di raccoglierle -- rossa su `len(e.rows) == 2`."""
    with pytest.raises(JudgmentError) as e:
        _j(("tipo", "light", "genere", "acceso"),
           ("tipo", "cover", "riposo", "[non json"))
    assert len(e.value.rows) == 2


def test_un_campo_che_non_e_un_giudizio_non_entra():
    """I fatti di HA restano codice (spec §2). Mutazione: accettare qualunque
    campo -- rossa."""
    with pytest.raises(JudgmentError):
        _j(("tipo", "climate", "capability_names", "{}"))


def test_l_impronta_cambia_SOLO_coi_campi_della_cronaca():
    """Correggere un limite non invecchia nessun giorno (spec §6). Mutazione:
    calcolare l'impronta su tutte le righe -- rossa sulla prima (`base` e
    `with_limit` non coincidono piu'). Eseguita il 17/09: la stesura del piano
    diceva «sulla seconda», ed era falso."""
    base = _j(("tipo", "light", "genere", "funzionamento"))
    with_limit = _j(("tipo", "light", "genere", "funzionamento"),
                    ("tipo", "light", "limiti_parametri",
                     '{"brightness": {"min": "min_b", "max": "max_b"}}'))
    with_genre = _j(("tipo", "light", "genere", "sicurezza"))
    assert base.chronicle_fingerprint() == with_limit.chronicle_fingerprint()
    assert base.chronicle_fingerprint() != with_genre.chronicle_fingerprint()
    assert len(base.chronicle_fingerprint()) == 16


def test_l_impronta_non_cambia_per_una_differenza_TIPOGRAFICA():
    """L'impronta si calcola sui valori interpretati, non sul testo: spazi e
    ordine dentro un riposo non invecchiano nessun giorno. Mutazione: calcolare
    l'impronta sul testo grezzo delle righe -- rossa."""
    compact = _j(("tipo", "cover", "riposo", '["closed","stopped"]'))
    spaced = _j(("tipo", "cover", "riposo", '[ "stopped", "closed" ]'))
    assert compact.chronicle_fingerprint() == spaced.chronicle_fingerprint()


def test_l_istantanea_e_IMMUTABILE():
    """Mutazione: togliere il blocco di `__setattr__` -- rossa."""
    j = _j(("tipo", "light", "genere", "funzionamento"))
    with pytest.raises(AttributeError):
        j._by_key = {}


def test_l_istantanea_non_si_CANCELLA():
    """Mutazione: togliere il blocco di `__delattr__` -- rossa."""
    j = _j(("tipo", "light", "genere", "funzionamento"))
    with pytest.raises(AttributeError):
        del j._by_key


def test_i_valori_annidati_sono_CONGELATI_anche_loro():
    """Un limite letto non si puo' correggere a mano: la prossima lettura
    risponde come la prima. Mutazione: congelare solo l'oggetto esterno di
    `_parse` (l'interno resta un `dict`) -- rossa."""
    j = _j(("tipo", "light", "limiti_parametri",
            '{"brightness": {"min": "min_b", "max": "max_b"}}'))
    limits = j.parameter_limits("light", "brightness")
    with pytest.raises(TypeError):
        limits["min"] = "HACKED"
    assert j.parameter_limits("light", "brightness")["min"] == "min_b"


def test_una_riga_MALFORMATA_si_raccoglie_come_le_altre():
    """Una riga che non ha quattro parti di testo e' storta come un valore
    storto: finisce nell'elenco, non scappa come eccezione nuda.

    Mutazioni: (a) spacchettare la riga fuori dal `try` -- rossa, esce un
    `ValueError` nudo; (b) togliere il controllo che le quattro parti siano
    testo -- rossa, la riga con soggetto `None` entra e `len(e.rows) == 2`."""
    with pytest.raises(JudgmentError) as e:
        _j(("tipo", "light", "genere", "acceso"),
           ("tipo", "light", "genere"),
           ("tipo", None, "genere", "presenza"))
    assert len(e.value.rows) == 3


def test_la_FORMA_di_lavoro_e_limiti_si_controlla_dentro():
    """Spec §2: `lavoro` e' `{stato: ragione}` di testo; `limiti_parametri` e'
    `{parametro: {"min", "max"} | {"options"}}` di testo. Ogni riga qui sotto
    viola una regola sola.

    Mutazioni: (a) togliere il controllo che le ragioni di `lavoro` siano
    testo -- rossa su `len(e.rows) == 5`; (b) togliere il controllo che un
    limite sia un oggetto -- rossa, la lista `["min", "max"]` supera l'insieme
    di chiavi e `.values()` scappa come `AttributeError` nudo; (c) togliere il
    controllo dell'insieme di chiavi e (d) quello che gli attributi di un
    limite siano testo -- rosse su `len(e.rows) == 5`.

    Riscritta al giro di correzione 1: il testimone di (b) era
    `{"brightness": "x"}`, e la mutazione (b) eseguita restava VERDE perche'
    `frozenset("x")` e' gia' respinto dal controllo delle chiavi."""
    with pytest.raises(JudgmentError) as e:
        _j(("tipo", "switch", "lavoro", '{"on": 5}'),
           ("tipo", "light", "limiti_parametri", '{"brightness": ["min", "max"]}'),
           ("tipo", "fan", "limiti_parametri", '{"percentage": {"min": "a"}}'),
           ("tipo", "climate", "limiti_parametri",
            '{"temperature": {"min": "a", "max": "b", "options": "c"}}'),
           ("tipo", "select", "limiti_parametri", '{"option": {"options": 3}}'))
    assert len(e.value.rows) == 5


def test_una_chiave_DOPPIA_e_storta():
    """Due righe con lo stesso soggetto e campo: nessuna vince in silenzio,
    entrambe finiscono nell'elenco. Mutazione: togliere il controllo delle
    chiavi doppie -- rossa, la costruzione riesce."""
    with pytest.raises(JudgmentError) as e:
        _j(("tipo", "light", "genere", "funzionamento"),
           ("tipo", "light", "genere", "sicurezza"))
    assert len(e.value.rows) == 2


def test_notevole_accendibile_limiti_assumibili_lavoro():
    """Mutazione: `is_notable` che non passa `device_class` alla ricerca
    (chiede solo il dominio) -- rossa su `is_notable("binary_sensor", "smoke")`."""
    j = _j(("tipo", "light", "notevole", "si"),
           ("tipo", "light", "accendibile", "si"),
           ("tipo", "binary_sensor", "notevole", "no"),
           ("tipo", "binary_sensor.smoke", "notevole", "si"),
           ("tipo", "light", "limiti_parametri",
            ('{"color_temp_kelvin": {"min": "min_color_temp_kelvin",'
             ' "max": "max_color_temp_kelvin"},'
             ' "effect": {"options": "effect_list"}}')),
           ("tipo", "alarm_control_panel", "lavoro",
            '{"triggered": "e\' il fatto piu\' notevole"}'))
    assert j.is_notable("light")
    assert not j.is_notable("binary_sensor") and j.is_notable("binary_sensor", "smoke")
    assert j.operable_domains() == frozenset({"light"})
    assert j.parameter_limits("light", "color_temp_kelvin")["min"] == "min_color_temp_kelvin"
    assert j.parameter_limits("light", "effect")["options"] == "effect_list"
    assert j.parameter_limits("light", "brightness") is None
    assert set(j.working_of("alarm_control_panel")) == {"triggered"}
