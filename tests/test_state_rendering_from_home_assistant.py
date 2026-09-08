"""Le parole con cui uno stato si legge le dice **Home Assistant**, non noi.

Quattro tabelle scritte a mano sono sparite l'08/09/2026 (spec §6):
`topology._STATE_TRANSLATION`, `_CLASS_MEANING`, `_READABLE_HVAC_MODE`,
`_READABLE_HVAC_ACTION`. Erano un doppione **peggiore dell'originale** -- cieche
al dominio, incomplete, e in italiano fisso su una casa che puo' cambiare
lingua -- e questo file e' cio' che tiene chiusa la porta dietro di loro.

**La trappola che rende questa fetta diversa dalle altre**: una tabella scritta
a mano non fallisce mai. Chi la leggeva non aveva nessun ramo per «non lo so»,
e sostituirla senza preparare i lettori avrebbe trasformato il primo guasto di
rete in un vuoto -- che su una pagina che il proprietario legge e' **peggio di
una traduzione approssimativa**. Meta' delle prove qui sotto guardano proprio
quello: cosa dice il lettore quando la tabella non c'e'.

Le chiavi e le parole vengono dalla casa vera (`tests/_house_translations.py`,
letta l'08/09/2026, Home Assistant `2026.9.1`, lingua `it`).
"""
import ast
import pathlib

from hiris.app.home_space import topology
from hiris.app.home_space.briefing import compose
from hiris.app.home_space.queries import view
from hiris.app.proxy import state_translations
from hiris.app.proxy.state_translations import StateTranslations
from tests._house_translations import house_translations, unread_translations

_PRODOTTO = pathlib.Path(__file__).resolve().parents[1] / "hiris"
_PROVE = pathlib.Path(__file__).resolve().parent

#: I quattro nomi che non devono piu' comparire in nessun codice -- ne' nel
#: prodotto ne' nelle prove. Restano leciti nella PROSA (commenti e docstring):
#: raccontare perche' una cosa non c'e' piu' e' l'unico modo perche' nessuno la
#: riscriva, e un controllo che vietasse anche quello spingerebbe a cancellare
#: la memoria invece del codice.
_TABELLE_CANCELLATE = ("_STATE_TRANSLATION", "_CLASS_MEANING",
                       "_READABLE_HVAC_MODE", "_READABLE_HVAC_ACTION")


def _nomi_usati(path: pathlib.Path) -> set[str]:
    """Gli identificatori che quel file USA davvero -- letti dall'albero
    sintattico, non cercati nel testo.

    Un `grep` non distingue una riga di codice da una riga di commento, e qui
    la differenza e' tutta: i quattro nomi sono citati apposta nei commenti che
    spiegano perche' non esistono piu'.
    """
    albero = ast.parse(path.read_text(encoding="utf-8"))
    usati = set()
    for node in ast.walk(albero):
        if isinstance(node, ast.Name):
            usati.add(node.id)
        elif isinstance(node, ast.Attribute):
            usati.add(node.attr)
        # Una stringa e' codice quando la si usa per raggiungere un attributo
        # (`getattr(topology, "_CLASS_MEANING")`): il nome sarebbe vivo e
        # l'albero, da solo, non lo direbbe.
        elif (isinstance(node, ast.Constant)
                and node.value in _TABELLE_CANCELLATE):
            usati.add(node.value)
    return usati


def test_le_quattro_tabelle_cancellate_non_hanno_piu_chiamanti():
    """Nessun codice le nomina piu', ne' nel prodotto ne' nelle prove.

    **Non e' la stessa cosa che «non esistono»**: una tabella cancellata di cui
    resta un lettore fa esplodere l'import, e questo si vedrebbe subito. Cio'
    che questa prova impedisce e' il ritorno -- qualcuno che, per far tacere un
    caso scomodo, ne riscriva una accanto alla lettura vera. Sarebbe la
    mutazione del capitolato: due significati per lo stesso stato, di nuovo.

    Mutazione ESEGUITA: rimettere in `topology.py` un
    `_STATE_TRANSLATION = {"on": "acceso"}` letto da `readable_state` -- questa
    prova nomina il file e il nome.
    """
    for nome in _TABELLE_CANCELLATE:
        assert not hasattr(topology, nome), (
            f"«{nome}» e' tornata: le parole degli stati le pubblica Home "
            "Assistant, e una tabella accanto e' un secondo significato")
    colpevoli = []
    for path in sorted([*_PRODOTTO.rglob("*.py"), *_PROVE.rglob("*.py")]):
        if path == pathlib.Path(__file__):
            continue
        usati = _nomi_usati(path)
        for nome in _TABELLE_CANCELLATE:
            if nome in usati:
                colpevoli.append(f"{path.name}: {nome}")
    assert not colpevoli, (
        "codice che usa ancora una delle quattro tabelle cancellate: "
        + ", ".join(colpevoli))


# ---------------------------------------------------------------------------
# IL DOMINIO DECIDE -- il difetto che ha fatto cancellare `_STATE_TRANSLATION`
# ---------------------------------------------------------------------------

def test_open_su_una_serratura_non_e_open_su_una_tapparella():
    """`_STATE_TRANSLATION` era **cieca al dominio**: `open` valeva «aperta»
    tanto su un `lock` quanto su un `cover`, con un genere grammaticale scelto
    per una delle due. Home Assistant no: la chiave porta il dominio dentro.

    Le due parole di questa prova sono inventate **apposta diverse**, e non e'
    una scorciatoia: sulla casa vera, in italiano, HA rende tutti e due
    «Aperto», quindi una prova costruita sulle sue parole non potrebbe
    distinguere il caso giusto da quello cieco. Cio' che si verifica qui e' la
    CHIAVE -- che ogni tipo riceva la propria -- e per vederla servono due
    risposte diverse. Che HA possa darle diverse davvero e' misurato altrove,
    sulle sue parole vere (`test_type_vocabulary.py`:
    `off` su `update` e' «Aggiornato», su `light` «Spento»).

    Mutazione ESEGUITA: in `state_translation`, costruire la chiave del terzo
    gradino con un dominio fisso -- una delle due asserzioni arrossisce
    qualunque dominio si scelga.
    """
    risorse = {
        "component.lock.entity_component._.state.open": "Aperta con la chiave",
        "component.cover.entity_component._.state.open": "Aperta a meta'",
    }
    traduzioni = {"lette": True, "lingua": "it", "risorse": risorse}
    assert topology.readable_state("open", domain="lock",
                                   translations=traduzioni)["valore"] == "Aperta con la chiave"
    assert topology.readable_state("open", domain="cover",
                                   translations=traduzioni)["valore"] == "Aperta a meta'"


def test_le_nove_azioni_del_termostato_arrivano_tutte_dalla_casa():
    """`_READABLE_HVAC_ACTION` ne aveva **sette**; Home Assistant ne pubblica
    **nove**. Le due che mancavano -- `defrosting` e `preheating` -- non erano
    una svista: erano il costo di una tabella che nessuno confronta con la
    fonte. Con la tabella cancellata escono da sole.

    Mutazione ESEGUITA: togliere
    `component.climate.entity_component._.state_attributes.hvac_action.state.defrosting`
    dalle risorse -- la prova nomina `defrosting`.
    """
    risorse = house_translations()["risorse"]
    senza = [azione for azione in
             ("cooling", "defrosting", "drying", "fan", "heating", "idle",
              "off", "preheating")
             if state_translations.attribute_value_translation(
                 azione, domain="climate", attribute=topology.HVAC_ACTION_ATTRIBUTE,
                 component_resources=risorse) is None]
    assert not senza, f"azioni del termostato senza resa: {senza}"
    reso = topology.readable_state("heat", domain="climate", hvac_action="defrosting",
                                   translations=house_translations())
    assert reso["valore"] == "impostato su Riscaldamento, azione in corso: Defrosting"


# ---------------------------------------------------------------------------
# LA COPPIA acceso/spento: si RICOSTRUISCE, e fallisce dichiarandolo
# ---------------------------------------------------------------------------

def test_la_coppia_si_ricostruisce_dalle_due_chiavi():
    """`_CLASS_MEANING["moisture"] = ("bagnato", "asciutto")` era l'unica cosa
    che quella tabella portava e che HA non da' gia' fatta: la coppia tenuta
    INSIEME. Si ricostruisce dalle due chiavi, e viene identica.

    Mutazione ESEGUITA: invertire l'ordine di `PAIR_STATES` -- la prova
    arrossisce, perche' consegnerebbe («Asciutto», «Bagnato»).
    """
    coppia = state_translations.published_pair(
        house_translations()["risorse"], domain="binary_sensor", device_class="moisture")
    assert coppia == {"letto": True, "valore": ("Bagnato", "Asciutto")}


def test_la_coppia_a_meta_FALLISCE_DICHIARANDOLO_e_non_si_inventa_l_altra_meta():
    """**Il secondo vincolo della spec §6.** Meta' coppia e' peggio di nessuna:
    consegnare «Bagnato» per `on` e la parola generica del dominio per `off`
    metterebbe insieme due meta' di due tipi diversi come se fossero un
    significato solo.

    Mutazione ESEGUITA: in `published_pair`, tornare `known` anche con una sola
    delle due chiavi -- la prova arrossisce su `letto is False`, e la seconda
    meta' (il messaggio che nomina la chiave mancante) sparisce.
    """
    meta = dict(house_translations()["risorse"])
    del meta["component.binary_sensor.entity_component.moisture.state.off"]
    esito = state_translations.published_pair(
        meta, domain="binary_sensor", device_class="moisture")
    assert esito["letto"] is False
    assert esito["silenzio"] == state_translations.SILENCE_ABSENT
    assert "`.state.off`" in esito["motivo"]
    assert "Bagnato" in esito["motivo"]


def test_con_la_coppia_a_meta_si_scende_al_dominio_invece_di_mescolare():
    """Il rovescio della prova sopra, sul lettore: `readable_state` non
    consegna la meta' che c'e' -- scende al gradino del DOMINIO, che e' un tipo
    solo e la coppia ce l'ha tutta. Cosi' `on` e `off` restano parole dello
    stesso tipo.

    Mutazione ESEGUITA: in `rendered_state`, usare la meta' pubblicata invece
    di scendere -- `on` tornerebbe «Bagnato» e `off` «Spento», e la prova
    arrossisce sulla prima asserzione.
    """
    meta = dict(house_translations()["risorse"])
    del meta["component.binary_sensor.entity_component.moisture.state.off"]
    traduzioni = {"lette": True, "lingua": "it", "risorse": meta}
    acceso = topology.readable_state("on", domain="binary_sensor",
                                     device_class="moisture", translations=traduzioni)
    spento = topology.readable_state("off", domain="binary_sensor",
                                     device_class="moisture", translations=traduzioni)
    assert acceso["valore"] == "Acceso"
    assert spento["valore"] == "Spento"


# ---------------------------------------------------------------------------
# I LETTORI PREPARATI: a traduzioni non lette, lo DICONO
# ---------------------------------------------------------------------------

_HOUSE_WITH_ONE_LIGHT = {
    "aree": [{"id": "cucina", "nome": "Cucina", "piano_id": None, "alias": [],
              "etichette": []}],
    "piani": [], "dispositivi": [],
    "entita": [{"id": "light.cucina", "nome": "Faretto", "area_id": "cucina",
                "dispositivo_id": None, "classe": None, "unita": None,
                "disabilitata": 0}],
}
_ONE_LIGHT_ON = {"light.cucina": "on"}


def _sezione_notevole(testo: str) -> str:
    return testo.split("## Notevole adesso")[1].split("## ")[0]


def test_il_nucleo_dichiara_le_traduzioni_non_lette_invece_di_mostrare_un_vuoto():
    """**La condizione della cancellazione** (spec §6, primo vincolo): si
    cancella una tabella solo se il consumatore sa dire «traduzioni non lette».

    Il nucleo mostra il grezzo -- `on` e' comunque il fatto -- e lo dichiara in
    testa alla sezione, col motivo di chi ha fallito. La riga pesa ZERO e sta
    in testa, come quella delle irraggiungibili: il taglio morde dal fondo, e
    un avviso in coda sarebbe il primo a cadere.

    Mutazione ESEGUITA: togliere il ramo che raccoglie `untranslated` in
    `_highlight_lines` -- la sezione mostra `- Cucina: Faretto (on)` e basta,
    e questa prova arrossisce sulla prima asserzione: un vuoto travestito da
    parola di Home Assistant.
    """
    testo, _ = compose(_HOUSE_WITH_ONE_LIGHT, [], [], _ONE_LIGHT_ON,
                       translations=unread_translations("Home Assistant non risponde"))
    sezione = _sezione_notevole(testo)
    assert "Le traduzioni di Home Assistant non sono state lette" in sezione
    assert "Home Assistant non risponde" in sezione
    assert "Faretto (on)" in sezione


def test_senza_nessun_esito_vale_come_non_lette_e_non_come_tutto_a_posto():
    """`None` significa «il chiamante non ha guardato», e non e' «non c'e'
    niente da tradurre»: la sezione lo dice lo stesso. E' la stessa disciplina
    di `problemi` e `confronto` in `compose()`.

    Mutazione ESEGUITA: far tornare a `rendered_state` una stringa vuota invece
    di un silenzio quando `translations` e' `None` -- la prova arrossisce.
    """
    testo, _ = compose(_HOUSE_WITH_ONE_LIGHT, [], [], _ONE_LIGHT_ON)
    assert "Le traduzioni di Home Assistant non sono state lette" in _sezione_notevole(testo)


def test_guarda_dice_il_motivo_al_posto_dello_stato_in_parole():
    """L'altra porta, e la stessa disciplina: `stato_leggibile` **tace** quando
    non c'e' una resa, e al suo posto compare il motivo etichettato. Lo `stato`
    grezzo non si tocca mai: e' il fatto.

    Prima dell'08/09/2026 questo ramo non poteva esistere -- la tabella
    rispondeva sempre -- ed e' esattamente per questo che andava scritto prima
    di toglierla.

    Mutazione ESEGUITA: in `_enrich_entity`, scrivere `stato_leggibile` col
    grezzo quando la resa manca -- la prova arrossisce sulla prima asserzione,
    e il modello leggerebbe «on» credendo che sia la parola di Home Assistant.
    """
    dettaglio = view(_HOUSE_WITH_ONE_LIGHT, [], [], _ONE_LIGHT_ON, "entita", "light.cucina",
                     translations=unread_translations("la casa non ha detto la sua lingua"))
    assert "stato_leggibile" not in dettaglio
    assert dettaglio["stato"] == "on"
    assert dettaglio["stato_non_reso"] == {
        "silenzio": state_translations.SILENCE_UNREACHABLE,
        "motivo": "la casa non ha detto la sua lingua",
    }


def test_i_tre_silenzi_non_collassano_fino_al_lettore():
    """**Spec §10.6.** «Non ho potuto chiedere» e «ho chiesto e non c’e'» sono
    due fatti diversi, e restano diversi fino a chi legge.

    Il caso vero: uno stato che quel tipo non pubblica (`cover` non ha `on`).
    Le traduzioni sono state lette per intero, quindi il nucleo **non** annuncia
    un guasto che non c'e' -- mostra il grezzo, come fa Home Assistant stesso
    («We don't know! Return the raw state») -- mentre `guarda` porta il silenzio
    giusto, che e' il secondo e non il primo.

    Mutazione ESEGUITA: in `_highlight_lines`, dichiarare anche il silenzio
    «ho chiesto e non c’e'» -- la prima asserzione arrossisce, e il nucleo
    direbbe al proprietario di non aver letto niente mentre ha letto tutto.
    """
    casa = {
        "aree": [{"id": "sala", "nome": "Sala", "piano_id": None, "alias": [],
                  "etichette": []}],
        "piani": [], "dispositivi": [],
        "entita": [{"id": "cover.tapparella", "nome": "Tapparella", "area_id": "sala",
                    "dispositivo_id": None, "classe": None, "unita": None,
                    "disabilitata": 0}],
    }
    stato = {"cover.tapparella": "on"}
    testo, _ = compose(casa, [], [], stato, translations=house_translations())
    sezione = _sezione_notevole(testo)
    assert "Le traduzioni di Home Assistant non sono state lette" not in sezione
    assert "Tapparella (on)" in sezione

    # E `guarda` **tace**, con lo `stato` grezzo al suo posto: e' la stessa
    # regola, e la lettura e' quella di `handlers_mind._with_rendered_states`
    # -- la chiave assente significa «questo stato non ha resa», la chiave
    # presente «non ho potuto chiedere». Misurato sulla casa vera: 431 entita'
    # su 841 (ogni `sensor`, ogni `number`, ogni `select`) non hanno una resa e
    # non devono averla, e dichiararle una per una avrebbe messo 431 blocchi di
    # scusa dentro le risposte.
    dettaglio = view(casa, [], [], stato, "entita", "cover.tapparella",
                     translations=house_translations())
    assert "stato_non_reso" not in dettaglio
    assert "stato_leggibile" not in dettaglio
    assert dettaglio["stato"] == "on"
    # La distinzione non e' persa: e' `readable_state` a portarla, e la porta
    # coi tre silenzi separati.
    esito = topology.readable_state("on", domain="cover",
                                    translations=house_translations())
    assert esito["silenzio"] == state_translations.SILENCE_ABSENT
    assert "cover" in esito["motivo"]


def test_una_categoria_che_non_esiste_e_il_terzo_silenzio_non_il_primo():
    """Il terzo: `frontend/get_translations` non valida `category`, e a una
    categoria inventata risponde `success: true` con **zero chiavi**
    (misurato). Una lettura riuscita e vuota non e' una lettura fallita, e
    nemmeno una casa senza stati.

    Mutazione ESEGUITA: in `rendered_state`, trattare le risorse vuote come
    `unreachable` -- la prova arrossisce sul silenzio.
    """
    esito = topology.readable_state("on", domain="light",
                                    translations={"lette": True, "risorse": {}})
    assert esito["silenzio"] == state_translations.SILENCE_UNDEFINED


def test_la_cache_non_va_in_rete_e_dichiara_di_non_aver_ancora_letto():
    """`cached()` e' cio' che permette al nucleo -- che si compone in una
    funzione SINCRONA -- di leggere le parole senza diventare `async`. Non
    chiede niente a nessuno: se nessuno ha ancora letto, lo dice.

    Mutazione ESEGUITA: far tornare a `cached()` un `{"lette": True,
    "risorse": {}}` quando non c'e' niente -- la prova arrossisce, e il nucleo
    direbbe «questa casa non pubblica niente» invece di «non ho ancora letto».
    """
    class _ClienteCheEsplode:
        async def get_translations(self, language, category):  # pragma: no cover
            raise AssertionError("`cached()` non deve andare in rete")

    cache = StateTranslations(_ClienteCheEsplode())
    esito = cache.cached()
    assert esito["lette"] is False
    assert "non sono ancora state lette" in esito["motivo"]
