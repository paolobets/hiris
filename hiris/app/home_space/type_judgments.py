"""L'istantanea dei giudizi sui tipi: cio' che HIRIS giudica di un tipo o di
un'entita', letto dal sapere e congelato.

**Puro.** Riceve righe e risponde: non apre archivi, non legge la rete, non ha
stato globale. Chi la costruisce dall'archivio e chi la sostituisce dopo una
scrittura e' la porta unica `mind/judgments.py` (spec 2026-09-16 §4).
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from types import MappingProxyType

Row = tuple[str, str, str, str]

GENRE_FIELD = "genere"
RESTING_FIELD = "riposo"
WORKING_FIELD = "lavoro"
NOTABLE_FIELD = "notevole"
OPERABLE_FIELD = "accendibile"
PARAMETER_LIMITS_FIELD = "limiti_parametri"
JUDGMENT_FIELD_NAMES = frozenset({
    GENRE_FIELD, RESTING_FIELD, WORKING_FIELD, NOTABLE_FIELD, OPERABLE_FIELD,
    PARAMETER_LIMITS_FIELD})
CHRONICLE_FIELDS = (GENRE_FIELD, RESTING_FIELD)
NO_GENRE = "nessuno"
_SUBJECT_KINDS = ("tipo", "entita")
_YES_NO = {"si": True, "no": False}
# Le due forme di un limite di parametro (spec §2).
_LIMIT_KEY_SETS = (frozenset({"min", "max"}), frozenset({"options"}))


class JudgmentError(ValueError):
    def __init__(self, rows: tuple[Row, ...], reasons: tuple[str, ...]) -> None:
        super().__init__("; ".join(reasons))
        self.rows = rows
        self.reasons = reasons


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(inner) for key, inner in value.items()})
    return value


def _unpack(row) -> Row:
    parts = tuple(row)
    if len(parts) != 4:
        raise ValueError(f"una riga ha quattro parti, questa ne ha {len(parts)}")
    if not all(isinstance(part, str) for part in parts):
        raise TypeError("le quattro parti di una riga sono testo")
    return parts


def _as_tuple(row) -> tuple:
    try:
        return tuple(row)
    except TypeError:
        return (row,)


def _check_parameter_limits(parsed: dict) -> None:
    for parameter, limit in parsed.items():
        if not isinstance(limit, dict):
            raise TypeError(f"il limite di {parameter!r} e' un oggetto JSON")
        if frozenset(limit) not in _LIMIT_KEY_SETS:
            raise ValueError(f"il limite di {parameter!r} ha chiavi {sorted(limit)}: "
                             "ammesse min+max oppure options")
        if not all(isinstance(attribute, str) for attribute in limit.values()):
            raise TypeError(f"gli attributi del limite di {parameter!r} sono testo")


def _parse(field: str, value: str, genres: frozenset[str], absent_forms: frozenset[str]):
    if field == GENRE_FIELD:
        if value != NO_GENRE and value not in genres:
            raise ValueError(f"genere fuori elenco: {value!r}")
        return value
    if field in (NOTABLE_FIELD, OPERABLE_FIELD):
        if value not in _YES_NO:
            raise ValueError(f"atteso si/no, trovato {value!r}")
        return _YES_NO[value]
    parsed = json.loads(value)
    if field == RESTING_FIELD:
        if not isinstance(parsed, list) or not all(isinstance(s, str) for s in parsed):
            raise ValueError("il riposo e' una lista di stati")
        if absent_forms & set(parsed):
            raise ValueError(f"le forme dell'assenza {sorted(absent_forms & set(parsed))} "
                             "non sono un riposo")
        return frozenset(parsed)
    if not isinstance(parsed, dict):
        raise TypeError(f"`{field}` e' un oggetto JSON")
    if field == WORKING_FIELD:
        if not all(isinstance(reason, str) for reason in parsed.values()):
            raise TypeError("la ragione di ogni stato di lavoro e' testo")
    else:
        _check_parameter_limits(parsed)
    return _freeze(parsed)


def _canonical(value):
    """La forma dell'impronta: il testo per `genere`, la lista ordinata per
    `riposo`. Una differenza solo tipografica nel JSON non la cambia."""
    return sorted(value) if isinstance(value, frozenset) else value


class TypeJudgments:
    __slots__ = ("_by_key", "_rows")

    def __init__(self, by_key: Mapping, rows: tuple[Row, ...]) -> None:
        object.__setattr__(self, "_by_key", MappingProxyType(dict(by_key)))
        object.__setattr__(self, "_rows", rows)

    def __setattr__(self, name, value):
        raise AttributeError("un'istantanea dei giudizi non si modifica: se ne costruisce un'altra")

    def __delattr__(self, name):
        raise AttributeError("un'istantanea dei giudizi non si modifica: se ne costruisce un'altra")

    @classmethod
    def from_rows(cls, rows: Iterable[Row], *, genres: Iterable[str],
                  absent_forms: Iterable[str]) -> TypeJudgments:
        """`genres` e `absent_forms` arrivano da chi chiama, come dati: i generi
        ammessi e le forme dell'assenza di stato (`none`, il vuoto: spec §5, non
        sono il riposo di nessuno) hanno la loro casa altrove -- le seconde in
        `type_vocabulary.ABSENT_STATE_FORMS` -- e questo modulo non importa dal
        repo. Ripeterle qui in un letterale sarebbe un secondo elenco degli
        stessi stati, che `test_un_tipo_ha_una_casa_sola` boccia."""
        allowed = frozenset(genres)
        absent = frozenset(absent_forms)
        by_key: dict = {}
        rows_by_key: dict[tuple[str, str, str], list[Row]] = {}
        bad, reasons = [], []
        for row in rows:
            try:
                kind, subject, field, value = _unpack(row)
                if kind not in _SUBJECT_KINDS:
                    raise ValueError(f"genere di soggetto non ammesso: {kind!r}")
                if field not in JUDGMENT_FIELD_NAMES:
                    raise ValueError(f"`{field}` non e' un giudizio")
                parsed = _parse(field, value, allowed, absent)
            except (ValueError, TypeError) as error:
                bad.append(_as_tuple(row))
                reasons.append(f"{_as_tuple(row)!r}: {error}")
                continue
            key = (kind, subject, field)
            by_key[key] = parsed
            rows_by_key.setdefault(key, []).append((kind, subject, field, value))
        for key, same in rows_by_key.items():
            if len(same) > 1:
                bad.extend(same)
                reasons.append(f"{'/'.join(key)}: chiave doppia, {len(same)} righe")
        if bad:
            raise JudgmentError(tuple(bad), tuple(reasons))
        kept = sorted(row for same in rows_by_key.values() for row in same)
        return cls(by_key, tuple(kept))

    def _lookup(self, field, domain, device_class=None, entity_id=None):
        keys = []
        if entity_id:
            keys.append(("entita", entity_id, field))
        if device_class:
            keys.append(("tipo", f"{domain}.{device_class}", field))
        keys.append(("tipo", domain, field))
        for key in keys:
            if key in self._by_key:
                return self._by_key[key]
        return None

    def genre_of(self, entity_id: str, device_class: str | None) -> str | None:
        domain = str(entity_id).split(".")[0]
        genre = self._lookup(GENRE_FIELD, domain, device_class, entity_id)
        return None if genre in (None, NO_GENRE) else genre

    def resting_of(self, domain, device_class=None, entity_id=None) -> frozenset[str]:
        return self._lookup(RESTING_FIELD, domain, device_class, entity_id) or frozenset()

    def working_of(self, domain, device_class=None) -> Mapping[str, str]:
        return self._lookup(WORKING_FIELD, domain, device_class) or MappingProxyType({})

    def is_notable(self, domain, device_class=None) -> bool:
        return bool(self._lookup(NOTABLE_FIELD, domain, device_class))

    def operable_domains(self) -> frozenset[str]:
        return frozenset(subject for (kind, subject, field), value in self._by_key.items()
                         if kind == "tipo" and field == OPERABLE_FIELD
                         and "." not in subject and value)

    def parameter_limits(self, domain, parameter) -> Mapping[str, str] | None:
        per_domain = self._lookup(PARAMETER_LIMITS_FIELD, domain)
        return None if per_domain is None else per_domain.get(parameter)

    def rows(self) -> tuple[Row, ...]:
        return self._rows

    def chronicle_fingerprint(self) -> str:
        relevant = sorted([kind, subject, field, _canonical(value)]
                          for (kind, subject, field), value in self._by_key.items()
                          if field in CHRONICLE_FIELDS)
        payload = json.dumps(relevant, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
