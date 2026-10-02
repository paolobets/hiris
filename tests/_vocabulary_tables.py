"""Le tabelle intere del vocabolario dei tipi, per le prove che le riportano
alla fonte.

Il prodotto chiede il vocabolario UN tipo alla volta (`capability_names`,
`capability_attributes`, `state_attributes`...): nessuna sua riga ha mai
chiesto «tutte le tabelle dei bit» o «ogni attributo tolto, con la sua
ragione». Lo chiedono le prove -- quelle che confrontano le trascrizioni col
sorgente di Home Assistant e quelle che bocciano un giudizio senza ragione
scritta -- e fino al 02/10/2026 otto viste nate per loro stavano dentro
`type_vocabulary.py`, senza un chiamante di produzione. Stanno qui, accanto a
chi le legge.

**Sette delle otto erano la stessa comprensione** con un campo diverso:
adesso e' una funzione sola, `_table`. Non sono un secondo elenco: leggono le
stesse righe del vocabolario che il prodotto legge.
"""
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from hiris.app.home_space.type_vocabulary import (
    ASSUMABLE_ATTRIBUTES,
    CAPABILITY_ATTRIBUTES,
    CAPABILITY_ATTRIBUTES_DROPPED,
    CAPABILITY_NAMES,
    GROUP_MEMBERSHIP_ATTRIBUTES,
    PARAMETER_LIMITS,
    STATE_ATTRIBUTES,
    WORKING_STATES,
    _vocabulary,
)


def _table(field: str, shape=lambda value: value) -> Mapping:
    """Dominio -> il valore di `field`, per i soli domini che lo dichiarano."""
    return MappingProxyType({
        domain: shape(_vocabulary.value(domain, None, field))
        for domain in sorted(_vocabulary.domains())
        if _vocabulary.value(domain, None, field) is not None})


def declared_working_states() -> Mapping[str, Mapping[str, str]]:
    """Dominio -> `stato -> ragione`."""
    return _table(WORKING_STATES)


def capability_tables() -> Mapping[str, Mapping[int, str]]:
    """Tutte le tabelle dei bit di `supported_features`."""
    return _table(CAPABILITY_NAMES)


def capability_attribute_tables() -> Mapping[str, frozenset[str]]:
    """Le trascrizioni delle capacita', dominio per dominio, **come sono nella
    fonte** -- il giudizio nostro non le tocca."""
    return _table(CAPABILITY_ATTRIBUTES, frozenset)


def state_attribute_tables() -> Mapping[str, frozenset[str]]:
    """Come sopra, per la meta' «com'e' adesso»."""
    return _table(STATE_ATTRIBUTES, frozenset)


def dropped_capability_attributes() -> Mapping[str, Mapping[str, str]]:
    """Gli attributi che Home Assistant chiama capacita' e il vocabolario no,
    con la ragione scritta di ognuno."""
    return _table(CAPABILITY_ATTRIBUTES_DROPPED)


def declared_assumable_attributes() -> Mapping[str, Mapping[str, str]]:
    """Gli attributi che dicono «cosa puo' assumere», con la ragione scritta
    di ognuno."""
    return _table(ASSUMABLE_ATTRIBUTES)


def declared_parameter_limits() -> Mapping[str, Mapping[str, Mapping[str, str]]]:
    """Tutti i collegamenti parametro -> attributo."""
    return _table(PARAMETER_LIMITS)


def declared_group_membership_attributes() -> Mapping[str, str]:
    """I nomi della composizione, con la ragione scritta di ognuno."""
    return MappingProxyType(dict(GROUP_MEMBERSHIP_ATTRIBUTES.value))
