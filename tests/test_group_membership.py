"""**L'appartenenza a un gruppo non e' una cosa che si puo' chiedere.**

Il difetto, misurato sulla casa vera il 09/09/2026 (Home Assistant `2026.9.1`,
837 entita' lette): `light.lampadario_sala_da_pranzo` e' un gruppo di tre
luci, e i suoi tre membri uscivano dentro `campo_di_manovra` -- la cesta che
dice *cosa si puo' chiedere a questa cosa* -- sotto la chiave `entity_id`,
accanto a `effect_list` e a `supported_color_modes`, cioe' accanto ai
parametri veri di `light.turn_on`. Nel nucleo uscivano come «entity_id=3
voci» in mezzo alle capacita'.

**Una sola entita' su 837 lo esponeva**, ed e' il motivo per cui e'
sopravvissuto: un difetto che si vede su una riga in ottocento non lo trova
nessuno rileggendo.

E il guadagno vero non e' lo spostamento: e' la frase che i membri rendono
possibile. Home Assistant, su un gruppo, dichiara l'UNIONE delle capacita' dei
membri -- verificato al tag `2026.9.1`, `components/group/light.py:283-295`
(`set().union(*all_supported_color_modes)`), `:263-273` (gli effetti),
`:250-261` (`reduce=min`/`max` sui kelvin), `:319-328` (l'OR di
`supported_features`). Un gruppo di tre luci di cui UNA sola fa colore
dichiara «faccio colore», il controllo lascia passare il comando, e Home
Assistant lo applica **solo a quella che puo'**, ignorando le altre in
silenzio.

**Sulla casa vera quella frase non compare mai**: i tre membri del lampadario
hanno capacita' identiche (`supported_color_modes: [color_temp, hs]`,
`supported_features: 36` tutti e tre -- misurato). Per questo il gruppo misto
qui sotto e' COSTRUITO e dichiarato tale: una prova che girasse solo sul caso
omogeneo passerebbe anche con la frase mai implementata.
"""
import pytest

from hiris.app.home_space.queries import group_membership, view
from hiris.app.home_space.topology import live_mirror
from hiris.app.home_space.type_vocabulary import (
    capability_attributes,
    declared_group_membership_attributes,
    group_membership_attributes,
)
from hiris.app.proxy.entity_cache import (
    CAPABILITIES,
    MEMBERS,
    _to_minimal,
    disclosable_attributes,
    group_members,
    inherited_attributes,
)

# --------------------------------------------------------------------------
# I PAYLOAD VERI -- il gruppo della casa e i suoi tre membri, letti dal vivo
# il 09/09/2026 da `GET /api/states`. I `None` sono quelli veri: le luci erano
# spente.
# --------------------------------------------------------------------------

GROUP = {
    "entity_id": "light.lampadario_sala_da_pranzo", "state": "off",
    "attributes": {
        "min_color_temp_kelvin": 1500, "max_color_temp_kelvin": 9000,
        "effect_list": ["effect_colorloop", "effect_pulse", "effect_stop"],
        "supported_color_modes": ["color_temp", "hs"],
        "effect": None, "color_mode": None, "brightness": None,
        "color_temp_kelvin": None, "hs_color": None, "rgb_color": None,
        "xy_color": None,
        "entity_id": ["light.lampadario", "light.lampadario_2",
                      "light.lampadario_3"],
        "friendly_name": "Lampadario sala da pranzo", "supported_features": 36,
    },
}


def _member(entity_id: str, name: str) -> dict:
    """Uno dei tre membri veri: capacita' IDENTICHE fra loro e al gruppo."""
    return {
        "entity_id": entity_id, "state": "off",
        "attributes": {
            "min_color_temp_kelvin": 1500, "max_color_temp_kelvin": 9000,
            "effect_list": ["effect_colorloop", "effect_pulse", "effect_stop"],
            "supported_color_modes": ["color_temp", "hs"],
            "color_mode": None, "brightness": None,
            "friendly_name": name, "supported_features": 36,
        },
    }


MEMBER_ONE = _member("light.lampadario", "Lampadario")
MEMBER_TWO = _member("light.lampadario_2", "Lampadario 2")
MEMBER_THREE = _member("light.lampadario_3", "Lampadario 3")

# IL GRUPPO MISTO, ed e' COSTRUITO: questa casa non ne ha nessuno, e la prova
# lo dichiara invece di far finta. La forma e' quella che Home Assistant
# produrrebbe davvero -- l'unione: il gruppo dichiara colore e effetti perche'
# UNA delle tre luci li fa, le altre due sono due prese `onoff`.
MIXED_GROUP = {
    "entity_id": "light.gruppo_misto", "state": "off",
    "attributes": {
        "min_color_temp_kelvin": 1500, "max_color_temp_kelvin": 9000,
        "effect_list": ["effect_colorloop"],
        "supported_color_modes": ["color_temp", "hs"],
        "entity_id": ["light.che_fa_colore", "light.solo_accesa_spenta",
                      "light.solo_accesa_spenta_2"],
        "friendly_name": "Gruppo misto", "supported_features": 36,
    },
}
MIXED_COLOUR = {
    "entity_id": "light.che_fa_colore", "state": "off",
    "attributes": {
        "min_color_temp_kelvin": 1500, "max_color_temp_kelvin": 9000,
        "effect_list": ["effect_colorloop"],
        "supported_color_modes": ["color_temp", "hs"],
        "friendly_name": "Che fa colore", "supported_features": 36,
    },
}


def _plain(entity_id: str, name: str) -> dict:
    return {
        "entity_id": entity_id, "state": "off",
        "attributes": {"supported_color_modes": ["onoff"],
                       "friendly_name": name, "supported_features": 0},
    }


MIXED_PLAIN_ONE = _plain("light.solo_accesa_spenta", "Solo accesa spenta")
MIXED_PLAIN_TWO = _plain("light.solo_accesa_spenta_2", "Solo accesa spenta 2")


def _house(*raw: dict) -> dict:
    return {
        "aree": [{"id": "casa", "nome": "Casa"}],
        "entita": [{"id": r["entity_id"],
                    "nome": r["attributes"].get("friendly_name"),
                    "area_id": "casa", "dispositivo_id": None,
                    "classe": None, "disabilitata": False} for r in raw],
        "dispositivi": [],
    }


def _detail(target: dict, *present: dict) -> dict:
    """LA CATENA VERA, dallo stato grezzo fino a cio' che `guarda` consegna --
    `_to_minimal` -> `live_mirror` -> `view`. Mai uno specchio scritto a mano:
    e' la trappola dello stato condiviso pigro, e in questo prodotto ha gia'
    lasciato passare un difetto che nessuna prova vedeva."""
    state, names, unit, classes, since, attributes = live_mirror(
        [_to_minimal(r) for r in present])
    return view(_house(*present), [], [], state, "entita", target["entity_id"],
                fallback_names=names, reported_units=unit,
                reported_classes=classes, reported_since_when=since,
                reported_attributes=attributes)


def _mirror(*present: dict) -> dict:
    return live_mirror([_to_minimal(r) for r in present])[5]


# --------------------------------------------------------------------------
# 1 · `entity_id` ESCE DAL CAMPO DI MANOVRA
# --------------------------------------------------------------------------

def test_l_appartenenza_a_un_gruppo_non_e_una_capacita():
    """La sottrazione sta nell'anagrafe dei tipi, non in un `if` a valle: ne'
    `entity_id` ne' `group_entities` sono un campo di manovra di nessun
    dominio.

    Mutazione (eseguita): togliere `- group_membership_attributes()` dal
    ritorno di `type_vocabulary.capability_attributes` -- il test torna rosso
    su `assert name not in capability_attributes(domain)`."""
    for domain in ("light", "sensor", "climate", "switch", "cover"):
        for name in group_membership_attributes():
            assert name not in capability_attributes(domain)


def test_il_gruppo_vero_della_casa_non_porta_piu_i_membri_fra_le_capacita():
    """Il caso misurato. Prima del 09/09/2026 questa entita' consegnava
    `campo_di_manovra: {"entity_id": [tre luci]}`; adesso il campo di manovra
    porta i quattro limiti veri di `light.turn_on` e nient'altro.

    Mutazione (eseguita): rimettere `entity_id` fra le capacita' universali
    com'era prima della fetta -- il test torna rosso su
    `assert "entity_id" not in campo`."""
    detail = _detail(GROUP, GROUP, MEMBER_ONE, MEMBER_TWO, MEMBER_THREE)
    campo = detail["attributi"]["campo_di_manovra"]
    assert "entity_id" not in campo
    assert "group_entities" not in campo
    assert set(campo) == {"min_color_temp_kelvin", "max_color_temp_kelvin",
                          "effect_list", "supported_color_modes"}
    # E non e' scivolato fra i non interpretati ne' fra i valori: sarebbe
    # sparire in un'altra cesta invece che dire cosa e'.
    for basket in ("valori", "non_interpretati", "valori_che_puo_assumere"):
        assert "entity_id" not in (detail["attributi"].get(basket) or {})


def test_i_membri_escono_da_una_chiave_che_dice_cosa_sono():
    """Dove sono finiti: una chiave propria del dettaglio, `membri`, accanto a
    `capacita` e a `comandi` -- non dentro `attributi`. Il nome della chiave
    e' l'informazione: chi legge `membri: {entita: [...]}` non puo'
    scambiarlo per un parametro di servizio.

    Mutazione (eseguita): togliere il blocco `membership` da `_view_entity` --
    il test torna rosso su `detail["membri"]` (`KeyError`), e le tre luci
    sparirebbero senza che nessuno lo dica."""
    detail = _detail(GROUP, GROUP, MEMBER_ONE, MEMBER_TWO, MEMBER_THREE)
    assert detail["membri"]["entita"] == [
        "light.lampadario", "light.lampadario_2", "light.lampadario_3"]
    assert "membri" not in detail["attributi"]


def test_i_membri_non_spariscono_dalla_voce_minimale():
    """La partizione di `test_inherited_attributes` vale anche per la cesta
    nuova: `entity_id` e' in UNA cesta, e in quella dei membri.

    Mutazione (eseguita): far cadere il ramo `MEMBERS` di
    `inherited_attributes` -- il test torna rosso su `baskets[MEMBERS]`
    (`KeyError`)."""
    baskets = inherited_attributes(GROUP["attributes"], "light")
    assert baskets[MEMBERS] == {"entity_id": [
        "light.lampadario", "light.lampadario_2", "light.lampadario_3"]}
    assert "entity_id" not in baskets[CAPABILITIES]
    assert group_members(baskets) == (
        "light.lampadario", "light.lampadario_2", "light.lampadario_3")
    # Chi cerca un attributo per nome lo trova lo stesso: i membri non sono
    # una credenziale, e un gruppo a cui si toglie una luce E' cambiato.
    assert "entity_id" in disclosable_attributes(baskets)


def test_ogni_nome_della_composizione_porta_la_sua_ragione():
    """La cura non e' una lista nera: e' un giudizio dichiarato. Una voce
    senza ragione scritta non passa di qui -- stessa disciplina di
    `declared_assumable_attributes`.

    Mutazione (eseguita): svuotare la ragione di `group_entities` in
    `GROUP_MEMBERSHIP_ATTRIBUTES` -- il test torna rosso su
    `assert isinstance(reason, str) and len(reason.strip()) > 40`."""
    declared = declared_group_membership_attributes()
    assert set(declared) == set(group_membership_attributes())
    assert set(declared) == {"group_entities", "entity_id"}
    for name, reason in declared.items():
        assert isinstance(reason, str) and len(reason.strip()) > 40, name


# --------------------------------------------------------------------------
# 2 · IL GRUPPO OMOGENEO NON DIVENTA PIU' RUMOROSO
# --------------------------------------------------------------------------

def test_un_gruppo_omogeneo_non_produce_nessuna_frase_in_piu():
    """E' la casa vera: i tre membri del lampadario dichiarano le stesse
    capacita' e gli stessi bit. Non c'e' niente da avvisare, e HIRIS tace.

    **Una prova che passa perche' non c'e' niente da trovare non dimostra di
    saper trovare**: questa vale solo accanto a quella del gruppo misto, ed e'
    per questo che le due si leggono insieme.

    Mutazione (eseguita): confrontare i membri con l'uguaglianza invece che
    per appartenenza (`count += 1 if item in mine` -> `count += 0`) -- il test
    torna rosso su `detail["membri"] == {...}`, e la casa vera si riempirebbe
    di avvisi falsi."""
    detail = _detail(GROUP, GROUP, MEMBER_ONE, MEMBER_TWO, MEMBER_THREE)
    assert detail["membri"] == {"entita": ["light.lampadario",
                                           "light.lampadario_2",
                                           "light.lampadario_3"]}


# --------------------------------------------------------------------------
# 3 · IL GRUPPO MISTO, E QUALE CAPACITA' NON E' DI TUTTI
# --------------------------------------------------------------------------

def test_un_gruppo_misto_nomina_la_capacita_che_non_e_di_tutti():
    """Il guadagno vero. Tre luci, una sola fa colore: il gruppo dichiara
    `hs` perche' Home Assistant unisce, il comando passa, e HA lo applica solo
    a quella che puo'. HIRIS adesso lo DICE, e dice quale.

    Mutazione (eseguita): far tornare sempre `None` a `_not_shared_by_all` --
    il test torna rosso su `detail["membri"]["capacita_non_di_tutti"]`
    (`KeyError`), che e' esattamente il silenzio di prima della fetta."""
    detail = _detail(MIXED_GROUP, MIXED_GROUP, MIXED_COLOUR,
                     MIXED_PLAIN_ONE, MIXED_PLAIN_TWO)
    avvisi = detail["membri"]["capacita_non_di_tutti"]
    assert avvisi["supported_color_modes"] == (
        "«color_temp»: 1 dei 3 membri letti; «hs»: 1 dei 3 membri letti")
    assert avvisi["effect_list"] == "«effect_colorloop»: 1 dei 3 membri letti"
    assert avvisi["min_color_temp_kelvin"] == "«1500»: 1 dei 3 membri letti"
    assert avvisi["max_color_temp_kelvin"] == "«9000»: 1 dei 3 membri letti"
    # E i bit di `supported_features` entrano nello stesso conto: Home
    # Assistant li unisce con un OR (`components/group/light.py:319-328`)
    # esattamente come unisce gli elenchi. Escono col nome con cui il
    # dettaglio li consegna gia' decodificati.
    assert avvisi["capacita"] == (
        "«effetti»: 1 dei 3 membri letti; «transizione»: 1 dei 3 membri letti")
    assert detail["capacita"] == ["effetti", "transizione"]


def test_cio_che_i_membri_condividono_non_finisce_fra_gli_avvisi():
    """Il verso opposto, sullo stesso gruppo misto: `supported_color_modes`
    e' nominato, ma una capacita' che tutti e tre dichiarano non lo e'.
    Senza questa meta' basterebbe nominare tutto per passare.

    Mutazione (eseguita): togliere la guardia `if count < read` -- il test
    torna rosso sull'uguaglianza fra insiemi, perche' ogni voce condivisa
    comincerebbe a comparire."""
    detail = _detail(MIXED_GROUP, MIXED_GROUP, MIXED_COLOUR,
                     MIXED_PLAIN_ONE, MIXED_PLAIN_TWO)
    avvisi = detail["membri"]["capacita_non_di_tutti"]
    # Il gruppo dichiara quattro capacita' piu' i bit: cinque avvisi, non uno
    # di piu' -- e nessuno su una voce che i membri hanno tutti.
    assert set(avvisi) == {"supported_color_modes", "effect_list",
                           "min_color_temp_kelvin", "max_color_temp_kelvin",
                           "capacita"}
    detail_uniforme = _detail(GROUP, GROUP, MEMBER_ONE, MEMBER_TWO, MEMBER_THREE)
    assert "capacita_non_di_tutti" not in detail_uniforme["membri"]


def test_una_capacita_che_nessun_membro_dichiara_si_conta_da_zero():
    """Il caso che il default di Home Assistant rende reale: su un gruppo
    senza nessun membro che dichiari `supported_color_modes`, HA scrive
    `{ColorMode.ONOFF}` da se' (`components/group/light.py:284`). Zero non e'
    «uno»: la frase lo dice con una parola diversa.

    Mutazione (eseguita): far tornare a `_how_many_members` la stessa forma
    per zero e per uno -- il test torna rosso su
    `«onoff»: nessuno dei 2 membri letti`."""
    group = {
        "entity_id": "light.gruppo_onoff", "state": "off",
        "attributes": {"supported_color_modes": ["onoff"],
                       "entity_id": ["light.senza_modi", "light.senza_modi_2"],
                       "friendly_name": "Gruppo onoff",
                       "supported_features": 0},
    }
    bare = [{"entity_id": eid, "state": "off",
             "attributes": {"friendly_name": eid, "supported_features": 0}}
            for eid in ("light.senza_modi", "light.senza_modi_2")]
    detail = _detail(group, group, *bare)
    assert detail["membri"]["capacita_non_di_tutti"]["supported_color_modes"] == (
        "«onoff»: nessuno dei 2 membri letti")


# --------------------------------------------------------------------------
# 4 · I MEMBRI CHE NON HO POTUTO GUARDARE SI DICHIARANO
# --------------------------------------------------------------------------

def test_i_membri_fuori_dallo_specchio_si_dichiarano_non_si_assumono_uguali():
    """«Non ho potuto guardare i membri» non e' «i membri sono tutti uguali»,
    e la differenza si vede: i non letti escono con nome e ragione, e la
    chiave degli avvisi non compare affatto -- tacerne sarebbe far leggere
    «sono tutti uguali» a chi non ha guardato niente.

    Mutazione (eseguita): togliere il blocco `unread` e tenere tutti i membri
    fra i letti -- il test torna rosso su `detail["membri"]["non_letti"]`
    (`KeyError`), e un gruppo di gruppi passerebbe per omogeneo."""
    detail = _detail(GROUP, GROUP)
    membri = detail["membri"]
    assert membri["entita"] == ["light.lampadario", "light.lampadario_2",
                                "light.lampadario_3"]
    assert set(membri["non_letti"]) == {"light.lampadario", "light.lampadario_2",
                                        "light.lampadario_3"}
    for reason in membri["non_letti"].values():
        assert "non ho potuto guardare" in reason
    assert "capacita_non_di_tutti" not in membri


def test_con_un_membro_solo_non_letto_il_conto_dice_su_quanti_e_vero():
    """Il caso parziale, che e' il piu' insidioso: due membri letti su tre.
    Si dice cio' che si e' misurato, e si dice **su quanti** -- «1 dei 2
    membri letti», non «1 dei 3» -- e il terzo esce nominato.

    Mutazione (eseguita): mettere il numero dei membri al posto di quello dei
    letti come denominatore -- il test torna rosso su `1 dei 2 membri letti`,
    e HIRIS conterebbe su un membro che non ha guardato."""
    detail = _detail(MIXED_GROUP, MIXED_GROUP, MIXED_COLOUR, MIXED_PLAIN_ONE)
    membri = detail["membri"]
    assert set(membri["non_letti"]) == {"light.solo_accesa_spenta_2"}
    assert membri["capacita_non_di_tutti"]["supported_color_modes"] == (
        "«color_temp»: 1 dei 2 membri letti; «hs»: 1 dei 2 membri letti")


def test_cio_che_non_e_un_gruppo_non_porta_la_chiave():
    """`membri: []` su ogni luce della casa sarebbe rumore in ogni risposta --
    stessa disciplina di `unita`, `capacita` e `categoria`.

    Mutazione (eseguita): far tornare a `group_membership` la vista anche con
    l'elenco dei membri vuoto -- il test torna rosso su
    `assert "membri" not in detail`."""
    detail = _detail(MEMBER_ONE, MEMBER_ONE)
    assert "membri" not in detail
    assert group_membership("light.lampadario", _mirror(MEMBER_ONE)) == {}
    assert group_membership("light.mai_vista", _mirror(MEMBER_ONE)) == {}
    assert group_membership("light.lampadario", None) == {}


@pytest.mark.parametrize("mirror", [None, {}, {"light.x": None}, "non un dizionario"])
def test_uno_specchio_che_non_c_e_non_inventa_un_gruppo(mirror):
    """Le forme in cui lo specchio puo' non esserci non devono produrre ne'
    un'eccezione ne' un gruppo finto."""
    assert group_membership("light.x", mirror) == {}
