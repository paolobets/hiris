"""B-47 (Tappa 8, D8): le tabelle che traducono chiavi di Home Assistant dicono
«chiave importata, parola nostra», e citano per ogni dominio il tag in cui la
chiave esiste.

**La misura e' riscritta qui a mano, non importata** -- la stessa ragione di
`test_feature_tables_pinned_to_source.py`: il sorgente di Home Assistant non si
interroga dalle prove (niente rete), e una mutazione della tabella non deve
poter muovere anche il proprio metro. L'elenco qui E' il fatto misurato.

Misurato l'08/10/2026 su `raw.githubusercontent.com/home-assistant/core/<tag>/
homeassistant/components/<dominio>/{const.py,__init__.py}`, ai tag `2024.7.0` e
`2026.9.1`: per ogni dominio, se TUTTE le chiavi della tabella (i bit di
`*EntityFeature`, le classi di `*DeviceClass`) esistono a quel tag.

Mutazioni ESEGUITE (08/10/2026): citare `cover` anche a `2024.7.0` in
`type_vocabulary.FEATURE_TAGS` -- rossa; citare `sensor` anche a `2024.7.0` in
`ha_vocabulary.DEVICE_CLASS_TAGS` -- rossa; togliere «parola nostra» dalla
fonte -- rossa.
"""
from __future__ import annotations

import pytest

from hiris.app.home_space import ha_vocabulary, type_vocabulary
from hiris.app.home_space.type_vocabulary import capability_names
from hiris.app.mind.seed import meaning_seed

VECCHIO, RECENTE = "2024.7.0", "2026.9.1"

#: I domini delle capacita' le cui chiavi esistono TUTTE solo al tag recente,
#: con cio' che manca al vecchio (misurato).
_CAPACITA_SOLO_RECENTE = {
    "climate": "bit 512 (SWING_HORIZONTAL_MODE)",
    "media_player": "bit 4194304 (SEARCH_MEDIA)",
    "cover": "bit 256 (SPEED)",
    "fan": "bit 16 e 32 (TURN_OFF, TURN_ON)",
    "vacuum": "bit 16384 (CLEAN_AREA)",
    "conversation": "nessun ConversationEntityFeature",
    "assist_satellite": "il componente non esiste",
}
_CAPACITA_DUE_TAG = {
    "update", "light", "notify", "camera", "valve", "water_heater", "weather",
    "siren", "todo", "alarm_control_panel", "calendar", "remote", "lock",
    "humidifier", "lawn_mower",
}

#: Le classi: `sensor` a `2024.7.0` non ha `uptime`.
_CLASSI_SOLO_RECENTE = {"sensor": "uptime"}
_CLASSI_DUE_TAG = {"number", "button", "switch", "update", "media_player", "valve"}


def _atteso(solo_recente, ai_due) -> dict[str, tuple[str, ...]]:
    return {**{d: (RECENTE,) for d in solo_recente}, **{d: (VECCHIO, RECENTE) for d in ai_due}}


def test_tag_capacita_misurati():
    assert type_vocabulary.FEATURE_TAGS == _atteso(_CAPACITA_SOLO_RECENTE, _CAPACITA_DUE_TAG)


def test_tag_classi_misurati():
    assert ha_vocabulary.DEVICE_CLASS_TAGS == _atteso(_CLASSI_SOLO_RECENTE, _CLASSI_DUE_TAG)


def test_ogni_dominio_ha_tag():
    """Chiesto alle tabelle: un dominio nuovo senza tag non si cita, e qui
    arrossisce invece di passare con la fonte di un altro."""
    domini_classi = {d for d, _ in ha_vocabulary.DEVICE_CLASS_MEANING}
    assert set(ha_vocabulary.DEVICE_CLASS_TAGS) == domini_classi
    domini_capacita = {d for d in type_vocabulary._FEATURE_TABLES if capability_names(d)}
    assert domini_capacita == set(type_vocabulary.FEATURE_TAGS)
    assert len(domini_capacita) == len(_CAPACITA_SOLO_RECENTE) + len(_CAPACITA_DUE_TAG)


@pytest.mark.parametrize("domain", sorted(_CAPACITA_SOLO_RECENTE | dict.fromkeys(
    _CAPACITA_DUE_TAG)))
def test_fonte_capacita_dice_chiave_importata_parola_nostra(domain):
    row = type_vocabulary._vocabulary.row(domain)
    fonte = row.fields[type_vocabulary.CAPABILITY_NAMES].source
    assert fonte.startswith("chiave importata, parola nostra")
    assert f"`{domain}`" in fonte and RECENTE in fonte
    assert (VECCHIO in fonte) == (domain in _CAPACITA_DUE_TAG)


def test_seme_significati_cita_tag_dominio():
    for fact in meaning_seed(when_ts=1.0):
        domain = fact.subject.split(".")[0]
        assert fact.provenance == "importato"
        assert fact.source.startswith("chiave importata, parola nostra")
        assert f"`{domain}`" in fact.source
        assert (VECCHIO in fact.source) == (domain in _CLASSI_DUE_TAG)
