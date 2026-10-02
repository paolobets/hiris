#!/usr/bin/env python3
"""L'istantaneo di cio' che Home Assistant PUBBLICA, letto dalla casa vera.

Il censore (`scripts/censore_tipi.py`) confronta il vocabolario dei
tipi con cio' che Home Assistant dichiara. Ma **la suite gira senza la casa**:
nessuna prova puo' dipendere dalla rete. Quindi il confronto non legge Home
Assistant -- legge un istantaneo **versionato nel repository e datato**, e
questo script e' cio' che lo produce.

    python scripts/istantaneo_pubblicato.py            # dice cosa cambierebbe
    python scripts/istantaneo_pubblicato.py --scrivi   # lo riscrive

La casa si dichiara da fuori, mai qui dentro: `HIRIS_HOUSE_URL` (per esempio
`http://homeassistant.local:8123`) e un segno di riconoscimento in
`HIRIS_HOUSE_TOKEN_FILE` (`~/.ha-token` se non si dice altro). Nessuno dei due
finisce nell'istantaneo, e questo script non li stampa mai.

**La forma delle fonti la capisce il prodotto, non questo script**: la chiave
di una traduzione la apre `state_translations.entity_component_key`, la
risposta di `/api/services` la apre `action/registry.py` (`_detail`,
`field_filter`), le `device_class` le distilla la stessa
`published_device_classes` che il seme del sapere legge. Qui sopra stanno solo
le viste che nessuna riga del prodotto chiede -- domini, stati per tipo,
valori di `state_class`, bit di capacita', domini accendibili -- e che fino al
02/10/2026 vivevano dentro il prodotto con questo script come unico chiamante.

**Tre letture, e nessuna e' in piu' rispetto a quelle di ogni giorno**:
`frontend/get_translations` (le 801 chiavi che HIRIS gia' scarica per rendere
uno stato), `GET /api/services` (il registro che gia' tiene in memoria) e
`GET /api/states` -- quest'ultima per i domini VIVI, che non sono deducibili
dalle traduzioni: `conversation` e `zone` hanno entita' qui e non hanno
nessuna chiave `entity_component`. Un istantaneo dei soli domini tradotti
perderebbe proprio quelli che nessuno traduce.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
from datetime import UTC, datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import censore_tipi

from hiris.app.action import registry as service_registry
from hiris.app.proxy import state_translations
from hiris.app.proxy.state_translations import (
    NO_DEVICE_CLASS,
    entity_component_key,
    known,
    unreachable,
)

SNAPSHOT_PATH = (pathlib.Path(__file__).resolve().parents[1]
                 / "tests" / "data" / "pubblicato-dalla-casa.json")

DEFAULT_TOKEN_FILE = "~/.ha-token"


class ReadingFailed(RuntimeError):
    """La casa non ha risposto. Chi produce il motivo lo etichetta -- e chi
    chiama decide se saltare (la prova dal vivo) o fermarsi (questo script)."""


def house_url() -> str | None:
    return os.environ.get("HIRIS_HOUSE_URL") or None


def house_token() -> str | None:
    """Il segno di riconoscimento, letto dal file e mai stampato."""
    direct = os.environ.get("HIRIS_HOUSE_TOKEN")
    if direct:
        return direct.strip() or None
    path = pathlib.Path(os.path.expanduser(
        os.environ.get("HIRIS_HOUSE_TOKEN_FILE") or DEFAULT_TOKEN_FILE))
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


# --------------------------------------------------------------------------
# COSA LE TRADUZIONI DICONO SUI TIPI
# --------------------------------------------------------------------------
#
# Tre viste sulle chiavi di `frontend/get_translations`, accanto alla quarta
# (`state_translations.published_device_classes`) che resta nel prodotto perche'
# il seme del sapere la legge. La forma della chiave la capisce UN posto solo,
# `state_translations.entity_component_key`: queste la chiedono a lui.
#
# Stavano in `proxy/state_translations.py` fino al 02/10/2026, senza nessun
# chiamante nel prodotto: le chiamava solo questo script.


def published_domains(resources) -> frozenset[str]:
    """I domini che QUESTA casa ha caricato -- 53, misurati.

    Non e' l'elenco esaustivo delle piattaforme di Home Assistant (quello non
    lo pubblica nessuna API): e' cio' che questa installazione ha acceso, che
    e' la domanda a cui serve rispondere.
    """
    if not isinstance(resources, dict):
        return frozenset()
    return frozenset(parts[1] for parts in
                     (entity_component_key(key) for key in resources)
                     if parts is not None)


def published_states(resources) -> dict[tuple[str, str | None], frozenset[str]]:
    """(dominio, classe o `None`) -> gli stati canonici di quel tipo.

    **La chiave e' il TIPO**, la stessa del vocabolario dei tipi: un dominio, o
    una coppia. Il `_` di Home Assistant -- che significa «vale per il dominio,
    senza classe» -- diventa `None`, cosi' che nessun consumatore debba sapere
    che quel trattino basso e' una convenzione e non una classe di dispositivo.
    """
    per_type: dict[tuple[str, str | None], set[str]] = {}
    if not isinstance(resources, dict):
        return {}
    for key in resources:
        parts = entity_component_key(key)
        if parts is None or len(parts) < 6 or parts[4] != "state":
            continue
        device_class = None if parts[3] == NO_DEVICE_CLASS else parts[3]
        # Lo stato e' TUTTO cio' che resta: un valore con un punto dentro non
        # si taglia a meta'. Prendere `parts[5]` e basta produrrebbe uno stato
        # che non esiste, senza che niente lo segnali.
        per_type.setdefault((parts[1], device_class), set()).add(".".join(parts[5:]))
    return {type_key: frozenset(states) for type_key, states in per_type.items()}


#: L'attributo di stato di cui si vogliono i valori legali. Uno solo, e scritto
#: qui perche' e' l'unico che decide come si legge un numero: `total_increasing`
#: e `measurement` non si sommano allo stesso modo.
STATE_CLASS_ATTRIBUTE = "state_class"


def published_state_classes(resources) -> frozenset[str]:
    """I valori legali di `state_class`, come questa casa li pubblica.

    **Quattro, non tre**: `measurement`, `measurement_angle`, `total`,
    `total_increasing` (misurati). Il quarto -- `measurement_angle` -- e'
    esattamente il tipo di voce che una lista scritta a mano non guadagna mai:
    e' nato in Home Assistant, e nessuno qui se n'e' accorto.
    """
    values: set[str] = set()
    if not isinstance(resources, dict):
        return frozenset()
    for key in resources:
        parts = entity_component_key(key)
        if (parts is None or len(parts) < 8 or parts[4] != "state_attributes"
                or parts[5] != STATE_CLASS_ATTRIBUTE or parts[6] != "state"):
            continue
        values.add(".".join(parts[7:]))
    return frozenset(values)


# --------------------------------------------------------------------------
# COSA QUESTO REGISTRO DICE SUI TIPI, e non solo sui singoli servizi
# --------------------------------------------------------------------------
#
# Il registro dei servizi non serve solo a verificare una chiamata: **e' la
# seconda fonte viva dell'anagrafe dei tipi** (spec §4, C11 e C13), e costa
# zero chiamate nuove -- e' gia' in memoria, e si invalida gia' da se' sugli
# eventi `service_registered`/`service_removed` (`proxy/ha_client.py:68`).
#
# Due materie, misurate sulla casa vera l'08/09/2026 (HA `2026.9.1`, 84 domini
# di servizio, 604 campi):
#
#   bit di capacita' per dominio   16 domini bersaglio, `media_player` 22
#                                  valori distinti, `cover` 10
#   domini che si accendono        16: automation, camera, climate, cover, fan,
#                                  homeassistant, humidifier, input_boolean,
#                                  light, media_player, remote, script, siren,
#                                  switch, valve, water_heater
#
# **LA TRAPPOLA, ed e' misurata.** I valori che il registro porta sono
# COMBINATI, non singoli: `cover.toggle` dichiara `supported_features: [3]`,
# che e' `OPEN|CLOSE`; `media_player.media_play_pause` dichiara `[16385]`, che
# e' `PLAY|PAUSE`; ci sono anche `[48]` (`OPEN_TILT|CLOSE_TILT`), `[384]`,
# `[3]` su `siren` e su `valve`. Confrontarli tali e quali con una tabella di
# bit singoli non trova NIENTE e non fallisce: dice «questo dominio non ha
# capacita' che conosciamo» su un dominio che le ha tutte. **Si scompone
# prima**, sempre, e la scomposizione sta qui -- non in ogni chiamante.
#
# **Il dominio giusto e' quello del BERSAGLIO, non quello del servizio**, e
# anche questo e' misurato: `reolink.ptz_move` dichiara
# `target.entity[0] = {integration: reolink, domain: [button],
# supported_features: [2]}`. Attribuirlo a `reolink` -- che non e' un dominio
# di entita' -- perderebbe l'unica capacita' che questa casa dichiara su
# `button`, e la perderebbe in silenzio. Dove il bersaglio non dichiara nessun
# dominio non si attribuisce a nessuno: sulla casa vera non capita mai (zero
# casi su 604 campi), e indovinare il dominio del servizio sarebbe la stessa
# bugia detta al contrario.

#: I servizi che, presi insieme, dicono «questo dominio si accende e si
#: spegne». Sono i nomi che Home Assistant registra, non una nostra idea di
#: interruttore: `turn_on` **e** `turn_off`, oppure `toggle`.
_SWITCH_SERVICES = ("turn_on", "turn_off")
_TOGGLE_SERVICE = "toggle"


def single_bits(value) -> frozenset[int]:
    """Un valore di `supported_features` -> i bit che lo compongono.

    `3` -> `{1, 2}`, `16385` -> `{1, 16384}`, `48` -> `{16, 32}`. Un bit solo
    resta se stesso.

    `bool` e' una sottoclasse di `int`: senza l'esclusione, `True` diventerebbe
    il bit 1 e `False` un insieme vuoto -- la stessa guardia che
    `field_applies` qui sopra e `topology.decoded_capabilities` gia' hanno, per
    la stessa ragione. Zero e i negativi non portano nessun bit: Home Assistant
    non ne emette, e inventarne uno sarebbe una capacita' che non esiste.
    """
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return frozenset()
    return frozenset(1 << position for position in range(value.bit_length())
                     if value >> position & 1)


def _target_domains(detail) -> frozenset[str]:
    """I domini di entita' che questo servizio dichiara di bersagliare."""
    if not isinstance(detail, dict):
        return frozenset()
    target = detail.get("target")
    if not isinstance(target, dict):
        return frozenset()
    entities = target.get("entity")
    if isinstance(entities, dict):
        entities = [entities]
    if not isinstance(entities, list):
        return frozenset()
    domains: set[str] = set()
    for entry in entities:
        if not isinstance(entry, dict):
            continue
        declared = entry.get("domain")
        if isinstance(declared, str):
            domains.add(declared)
        elif isinstance(declared, list):
            domains.update(name for name in declared if isinstance(name, str))
    return frozenset(domains)


def _bits_declared_by(detail) -> frozenset[int]:
    """I bit che questo servizio nomina, **gia' scomposti**, dalle due sedi in
    cui Home Assistant li mette.

    1. `target.entity[*].supported_features` -- «questo servizio si applica
       alle entita' che sanno fare X»;
    2. `fields[*].filter.supported_features` -- «questo PARAMETRO si applica
       alle entita' che sanno fare X». `fields` e' gia' appiattito da
       `_fields`, quindi le sezioni di Home Assistant >= 2024.6 sono gia'
       aperte e nessun parametro avanzato si perde qui.
    """
    bits: set[int] = set()
    if not isinstance(detail, dict):
        return frozenset()
    target = detail.get("target")
    entities = target.get("entity") if isinstance(target, dict) else None
    if isinstance(entities, dict):
        entities = [entities]
    for entry in entities if isinstance(entities, list) else ():
        if not isinstance(entry, dict):
            continue
        declared = entry.get("supported_features")
        for value in declared if isinstance(declared, list) else ():
            bits |= single_bits(value)
    fields = detail.get("fields")
    for reading in fields.values() if isinstance(fields, dict) else ():
        per_field = service_registry.field_filter(reading)
        declared = per_field.get("supported_features") if per_field else None
        for value in declared if isinstance(declared, list) else ():
            bits |= single_bits(value)
    return frozenset(bits)


def _capability_bits(registry) -> dict[str, frozenset[int]]:
    """Dominio di entita' -> i bit di capacita' che questa casa dichiara.

    Una vista sul registro, non un secondo elenco: si ricostruisce a ogni
    domanda dalle stesse righe che `service()` restituisce, cosi' non puo'
    restare indietro rispetto a un'integrazione installata cinque minuti fa.
    """
    per_domain: dict[str, set[int]] = {}
    for service_domain in registry.domains():
        for name in registry.services_for(service_domain):
            detail = registry.service(service_domain, name)
            bits = _bits_declared_by(detail)
            if not bits:
                continue
            for domain in _target_domains(detail):
                per_domain.setdefault(domain, set()).update(bits)
    return {domain: frozenset(bits) for domain, bits in per_domain.items()}


def capability_bits(registry) -> dict:
    """I bit di capacita' per dominio, etichettati coi tre silenzi.

    `unreachable` quando il registro non e' mai stato letto: un registro
    assente e un registro senza bit rispondono uguale a chi guarda un
    dizionario vuoto, e sono due fatti opposti -- lo stesso motivo per cui
    `ServiceRegistry.empty()` esiste.
    """
    if registry is None:
        return unreachable("il registro dei servizi non e' collegato a questa istanza")
    if registry.empty():
        return unreachable("il registro dei servizi non e' mai stato letto da "
                           "Home Assistant")
    return known(_capability_bits(registry))


# `capability_bits_of` (i bit di UN dominio solo) e' stata cancellata (R6,
# revisione del tratto v3.23.0..HEAD, 08/09/2026): nessun chiamante di
# produzione la usava, solo le prove. `capability_bits()` qui sopra -- usata
# da `scripts/istantaneo_pubblicato.py` -- resta la sola porta viva; chi
# vuole i bit di un dominio solo fa `capability_bits(registro)["valore"].
# get(dominio)` e distingue da se' «letto» da «non letto» sull'esito di
# `capability_bits`, senza bisogno di una seconda funzione mai chiamata.


def switchable_domains(registry) -> dict:
    """I domini che Home Assistant dichiara accendibili -- 16, misurati.

    **E' una DERIVAZIONE, non un giudizio**, e non sostituisce il nostro: la
    spec (§4) lo dice per esteso -- questa lista guadagna `automation`,
    `script`, `input_boolean`, `camera`, `remote`, `siren` e `homeassistant`,
    dove `on` significa «abilitata» e non «accesa», e perde `vacuum`, che Home
    Assistant comanda con `start`/`stop`. Serve a SORVEGLIARE il giudizio, e
    chi la legge come un elenco di interruttori riapre il difetto che
    il campo `notable` di `type_vocabulary` documenta di aver gia' pagato.

    **Sono domini di SERVIZIO**, non di entita': `homeassistant` sta qui e non
    e' un dominio di entita'. E' un fatto della derivazione, non un difetto --
    ed e' una delle sette eccezioni che il censore dovra' motivare.
    """
    if registry is None:
        return unreachable("il registro dei servizi non e' collegato a questa istanza")
    if registry.empty():
        return unreachable("il registro dei servizi non e' mai stato letto da "
                           "Home Assistant")
    domains = set()
    for domain in registry.domains():
        names = set(registry.services_for(domain))
        if _TOGGLE_SERVICE in names or set(_SWITCH_SERVICES) <= names:
            domains.add(domain)
    return known(frozenset(domains))


class _ReadRegistry:
    """Il minimo che `action/registry.py` chiede per rispondere: quel modulo e'
    l'unico posto in cui la forma di `/api/services` va capita, e questo guscio
    esiste per non capirla una seconda volta qui."""

    def __init__(self, reading) -> None:
        self._per_domain: dict[str, dict[str, dict]] = {}
        for entry in reading or []:
            if not isinstance(entry, dict):
                continue
            domain = entry.get("domain")
            services = entry.get("services")
            if isinstance(domain, str) and isinstance(services, dict):
                self._per_domain[domain] = {
                    name: service_registry._detail(detail)
                    for name, detail in services.items() if isinstance(name, str)}

    def domains(self) -> list[str]:
        return sorted(self._per_domain)

    def services_for(self, domain: str) -> list[str]:
        return sorted(self._per_domain.get(domain, {}))

    def service(self, domain: str, name: str) -> dict | None:
        return self._per_domain.get(domain, {}).get(name)

    def empty(self) -> bool:
        return not self._per_domain


async def read_house(url: str, token: str) -> dict:
    """Le tre letture, e la distillazione con le funzioni del prodotto."""
    import aiohttp

    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{url}/api/config", headers=headers) as answer:
                config = await answer.json()
            async with session.get(f"{url}/api/services", headers=headers) as answer:
                services = await answer.json()
            async with session.get(f"{url}/api/states", headers=headers) as answer:
                states = await answer.json()
            language = config.get("language")
            if not language:
                raise ReadingFailed("la casa non dichiara la propria lingua")
            async with session.ws_connect(f"{url}/api/websocket") as socket:
                await socket.receive_json()
                await socket.send_json({"type": "auth", "access_token": token})
                welcome = await socket.receive_json()
                if welcome.get("type") != "auth_ok":
                    raise ReadingFailed("la casa non ha accettato il segno di "
                                        "riconoscimento")
                await socket.send_json({
                    "id": 1, "type": "frontend/get_translations",
                    "language": language,
                    "category": state_translations.STATE_TRANSLATIONS_CATEGORY})
                answer = await socket.receive_json()
    except ReadingFailed:
        raise
    except Exception as error:  # il motivo lo etichetta chi ha fallito, non chi legge
        raise ReadingFailed(f"{type(error).__name__}: {error}") from error

    resources = (answer.get("result") or {}).get("resources")
    if not isinstance(resources, dict) or not resources:
        raise ReadingFailed(
            "Home Assistant ha risposto senza errore e senza nessuna chiave: la "
            "categoria chiesta non e' fra quelle che pubblica")
    return distill(resources, services, states,
                   ha_version=config.get("version"), language=language)


def distill(resources, services, states, *, ha_version, language) -> dict:
    """Le sei materie, dalle funzioni del prodotto. Pura: nessuna rete."""
    registry = _ReadRegistry(services)
    live_domains = {entity["entity_id"].split(".")[0]
                    for entity in states or []
                    if isinstance(entity, dict) and isinstance(entity.get("entity_id"), str)
                    and "." in entity["entity_id"]}
    domains = set(published_domains(resources)) | live_domains
    classes = state_translations.published_device_classes(resources)
    per_type = published_states(resources)
    state_classes = published_state_classes(resources)
    bits = capability_bits(registry)
    switchable = switchable_domains(registry)
    if not bits.get("letto") or not switchable.get("letto"):
        raise ReadingFailed("il registro dei servizi non si e' potuto leggere: "
                            + str(bits.get("motivo") or switchable.get("motivo")))

    states_written: dict[str, dict[str, list[str]]] = {}
    for (domain, device_class), values in per_type.items():
        written = device_class or NO_DEVICE_CLASS
        states_written.setdefault(domain, {})[written] = sorted(values)

    return {
        censore_tipi.SNAPSHOT_READ_ON: datetime.now(UTC).date().isoformat(),
        censore_tipi.SNAPSHOT_HA_VERSION: ha_version,
        censore_tipi.SNAPSHOT_LANGUAGE: language,
        censore_tipi.SNAPSHOT_KEYS[censore_tipi.Subject.DOMAIN]: sorted(domains),
        censore_tipi.SNAPSHOT_KEYS[censore_tipi.Subject.DEVICE_CLASS]: {
            domain: sorted(values) for domain, values in sorted(classes.items())},
        censore_tipi.SNAPSHOT_KEYS[censore_tipi.Subject.STATE]: {
            domain: dict(sorted(values.items()))
            for domain, values in sorted(states_written.items())},
        censore_tipi.SNAPSHOT_KEYS[censore_tipi.Subject.STATE_CLASS]: sorted(state_classes),
        censore_tipi.SNAPSHOT_KEYS[censore_tipi.Subject.CAPABILITY_BIT]: {
            domain: sorted(values) for domain, values in sorted(bits["valore"].items())},
        censore_tipi.SNAPSHOT_KEYS[censore_tipi.Subject.SWITCHABLE]:
            sorted(switchable["valore"]),
    }


def stored_snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def materially_same(first: dict, second: dict) -> bool:
    """Uguali in cio' che il censore guarda -- la DATA di lettura non conta.

    Un istantaneo riletto oggi da una casa che non e' cambiata non e' un
    istantaneo nuovo: riscriverlo per far avanzare una data produrrebbe un
    commit che dice «la casa e' cambiata» quando non e' successo niente.
    """
    interesting = [key for subject, key in censore_tipi.SNAPSHOT_KEYS.items()] + [
        censore_tipi.SNAPSHOT_HA_VERSION, censore_tipi.SNAPSHOT_LANGUAGE]
    return all(first.get(key) == second.get(key) for key in interesting)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scrivi", action="store_true",
                        help="riscrive l'istantaneo invece di dire soltanto "
                             "cosa cambierebbe")
    arguments = parser.parse_args(argv)

    url, token = house_url(), house_token()
    if not url or not token:
        print("nessuna casa dichiarata: servono HIRIS_HOUSE_URL e un segno di "
              f"riconoscimento (HIRIS_HOUSE_TOKEN, o il file {DEFAULT_TOKEN_FILE})")
        return 2
    try:
        fresh = asyncio.run(read_house(url, token))
    except ReadingFailed as failure:
        print(f"la casa non ha risposto: {failure}")
        return 2

    stored = stored_snapshot() if SNAPSHOT_PATH.exists() else {}
    if stored and materially_same(stored, fresh):
        print(f"l'istantaneo del {stored.get(censore_tipi.SNAPSHOT_READ_ON)} e' ancora "
              f"quello di questa casa (HA {fresh[censore_tipi.SNAPSHOT_HA_VERSION]})")
        return 0
    for subject, key in censore_tipi.SNAPSHOT_KEYS.items():
        if stored.get(key) != fresh.get(key):
            print(f"cambiata la materia «{subject.value}»")
    if not arguments.scrivi:
        print("l'istantaneo e' scaduto -- rilancia con --scrivi per riscriverlo")
        return 1
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(json.dumps(fresh, ensure_ascii=False, indent=2,
                                        sort_keys=False) + "\n", encoding="utf-8")
    print(f"istantaneo riscritto: {SNAPSHOT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
