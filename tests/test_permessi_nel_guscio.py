"""I permessi arrivano dentro la pagina (Fase S, S.6, 29/10/2026).

Fino al 29/10 il browser ricordava `can_configure` e `can_build` in
`localStorage`, per browser e non per persona: su un dispositivo condiviso chi
veniva dopo un amministratore vedeva per un attimo il suo menu, e `/config`
aspettava fino a tre secondi la prima risposta di `GET /api/pending` prima di
scegliere la pagina. Adesso il guscio, servito richiesta per richiesta e mai
tenuto in cache, li porta scritti dal server: la stessa domanda della rotta
(`admission.request_permissions`), una casa sola.
"""
from __future__ import annotations

import html
import json
import re

import pytest
import pytest_asyncio

from hiris.app.action.construction.revisions import CONSTRUCTIONS_KEY, ConstructionStore
from hiris.app.api import shell
from hiris.app.api.admission import NOT_ADMITTED
from hiris.app.api.servizi import SERVICES_KEY
from hiris.app.chat_store import close_all_stores
from hiris.app.keeper.store import AGENDA_KEY, AgendaStore
from hiris.app.memory.store import MEMORY_STORE_KEY
from tests.test_admission import _compose, _persona

_META = re.compile(r'<meta name="hiris-permessi" content="([^"]*)">')


def _permissions(page: str) -> dict:
    [content] = _META.findall(page)
    return json.loads(html.unescape(content))


@pytest_asyncio.fixture
async def casa(aiohttp_client, tmp_path, monkeypatch):
    monkeypatch.delenv("HIRIS_ALLOW_NO_TOKEN", raising=False)
    monkeypatch.delenv("HIRIS_ALLOW_NO_CSRF", raising=False)
    app = _compose(tmp_path, access=True)
    shell._read_static_pages(app)
    app[AGENDA_KEY] = AgendaStore(str(tmp_path / "promesse.db"))
    app[CONSTRUCTIONS_KEY] = ConstructionStore(str(tmp_path / "costruzioni.db"))
    client = await aiohttp_client(app)
    yield client
    app[AGENDA_KEY].close()
    app[CONSTRUCTIONS_KEY].close()
    app[MEMORY_STORE_KEY].close()
    app[SERVICES_KEY].close()
    close_all_stores()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/", "/config"])
async def test_il_guscio_di_chi_amministra_porta_i_suoi_permessi(casa, path):
    """Mutazione ESEGUITA: `_serve_shell` senza `request_permissions(request)`
    -- rossa, nessuna meta nella pagina."""
    pagina = await (await casa.get(path, headers=_persona("u-admin"))).text()
    assert _permissions(pagina) == {"can_build": True, "can_configure": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/", "/config"])
async def test_il_guscio_di_chi_non_amministra_porta_il_no_e_il_suo_testo(casa, path):
    pagina = await (await casa.get(path, headers=_persona("u-marta"))).text()
    assert _permissions(pagina) == {"can_build": False, "can_configure": False,
                                    "configure_refusal": NOT_ADMITTED}


@pytest.mark.asyncio
async def test_la_pagina_e_la_rotta_dicono_la_stessa_cosa(casa):
    """Una domanda, due porte: cio' che la pagina porta e' cio' che
    `api/pending` ripete, chiave per chiave."""
    for utente in ("u-admin", "u-marta"):
        pagina = await (await casa.get("/config", headers=_persona(utente))).text()
        pending = await (await casa.get("/api/pending", headers=_persona(utente))).json()
        permessi = _permissions(pagina)
        assert {k: pending[k] for k in permessi} == permessi
        assert set(pending) - set(permessi) == {"agenda_unread", "constructions_pending"}


@pytest.mark.asyncio
async def test_il_guscio_coi_permessi_non_si_tiene_in_cache(casa):
    """La pagina e' di chi l'ha chiesta: una copia tenuta da un proxy o dal
    browser porterebbe i permessi di un altro."""
    risposta = await casa.get("/", headers=_persona("u-marta"))
    assert risposta.headers["Cache-Control"] == "no-store"


def test_il_testo_del_rifiuto_resta_testo_nella_meta():
    """Il JSON entra in un attributo: virgolette e parentesi angolari escono
    come entita', e la meta non si chiude prima del tempo."""
    out = shell._inject_version("<head></head>", "1", "",
                                {"configure_refusal": '"><script>x</script>'})
    assert "<script>" not in out
    assert _permissions(out) == {"configure_refusal": '"><script>x</script>'}
