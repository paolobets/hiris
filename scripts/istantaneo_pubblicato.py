#!/usr/bin/env python3
"""L'istantaneo di cio' che Home Assistant PUBBLICA, letto dalla casa vera.

Il censore (`hiris/app/home_space/type_census.py`) confronta il vocabolario dei
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

**Le materie escono dalle stesse funzioni che il prodotto usa davvero**
(`proxy/state_translations.py`, `action/registry.py`): un istantaneo distillato
da un secondo lettore scritto apposta racconterebbe una casa che HIRIS non
vede, ed e' proprio la divergenza che il censore esiste per trovare.

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

from hiris.app.action import registry as service_registry
from hiris.app.home_space import type_census
from hiris.app.proxy import state_translations

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
    domains = set(state_translations.published_domains(resources)) | live_domains
    classes = state_translations.published_device_classes(resources)
    per_type = state_translations.published_states(resources)
    state_classes = state_translations.published_state_classes(resources)
    bits = service_registry.capability_bits(registry)
    switchable = service_registry.switchable_domains(registry)
    if not bits.get("letto") or not switchable.get("letto"):
        raise ReadingFailed("il registro dei servizi non si e' potuto leggere: "
                            + str(bits.get("motivo") or switchable.get("motivo")))

    states_written: dict[str, dict[str, list[str]]] = {}
    for (domain, device_class), values in per_type.items():
        written = device_class or type_census.NO_DEVICE_CLASS
        states_written.setdefault(domain, {})[written] = sorted(values)

    return {
        type_census.SNAPSHOT_READ_ON: datetime.now(UTC).date().isoformat(),
        type_census.SNAPSHOT_HA_VERSION: ha_version,
        type_census.SNAPSHOT_LANGUAGE: language,
        type_census.SNAPSHOT_KEYS[type_census.Subject.DOMAIN]: sorted(domains),
        type_census.SNAPSHOT_KEYS[type_census.Subject.DEVICE_CLASS]: {
            domain: sorted(values) for domain, values in sorted(classes.items())},
        type_census.SNAPSHOT_KEYS[type_census.Subject.STATE]: {
            domain: dict(sorted(values.items()))
            for domain, values in sorted(states_written.items())},
        type_census.SNAPSHOT_KEYS[type_census.Subject.STATE_CLASS]: sorted(state_classes),
        type_census.SNAPSHOT_KEYS[type_census.Subject.CAPABILITY_BIT]: {
            domain: sorted(values) for domain, values in sorted(bits["valore"].items())},
        type_census.SNAPSHOT_KEYS[type_census.Subject.SWITCHABLE]:
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
    interesting = [key for subject, key in type_census.SNAPSHOT_KEYS.items()] + [
        type_census.SNAPSHOT_HA_VERSION, type_census.SNAPSHOT_LANGUAGE]
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
        print(f"l'istantaneo del {stored.get(type_census.SNAPSHOT_READ_ON)} e' ancora "
              f"quello di questa casa (HA {fresh[type_census.SNAPSHOT_HA_VERSION]})")
        return 0
    for subject, key in type_census.SNAPSHOT_KEYS.items():
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
