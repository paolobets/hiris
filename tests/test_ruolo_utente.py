"""Il RUOLO di chi chiede, chiesto a Home Assistant (invariante I-1).

L'intestazione dell'ingress porta **chi** (`X-Remote-User-Id`), non **cosa puo'
fare**. Il ruolo lo sa Home Assistant, e HIRIS puo' chiederglielo: verificato il
21/09/2026 sul sorgente di `components/config/auth.py`, `config/auth/list` e'
`@websocket_api.require_admin` e restituisce per ogni utente `id`, `name`,
`is_owner`, `system_generated` e `group_ids` -- **non `is_admin`**, che si ricava
dal gruppo `system-admin`.

Che HIRIS possa chiamarlo dipende da un secondo fatto, verificato sullo stesso
giro: il Supervisor proxa verso il nucleo **con la propria sessione
privilegiata**, quindi le chiamate dell'add-on sono attribuite a un utente di
sistema amministratore. E' anche la ragione tecnica per cui HIRIS oggi
**amplifica**: parla con Home Assistant da amministratore qualunque sia la
persona che ha scritto in chat.

**La regola che questo file custodisce e' il verso del dubbio.** Se Home
Assistant non risponde, o risponde male, o non conosce quell'identificatore, il
ruolo NON e' «amministratore»: e' «non lo so», e un soffitto che non sa si
comporta come col grado piu' basso. Il contrario -- ripiegare su amministratore
quando la lettura fallisce -- renderebbe un guasto di rete un aumento di
privilegi.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from casa_finta import CasaFinta

#: La forma VERA di `config/auth/list` (Core 2026.9.3,
#: `components/config/auth.py::_user_info`): porta anche `is_active`.
_UTENTI = [
    {"id": "u-owner", "name": "Paolo", "is_owner": True, "is_active": True,
     "system_generated": False, "group_ids": ["system-admin"]},
    {"id": "u-admin", "name": "Seconda", "is_owner": False, "is_active": True,
     "system_generated": False, "group_ids": ["system-admin"]},
    {"id": "u-ospite", "name": "Ospite", "is_owner": False, "is_active": True,
     "system_generated": False, "group_ids": ["system-users"]},
    {"id": "u-sistema", "name": "Supervisor", "is_owner": False, "is_active": True,
     "system_generated": True, "group_ids": ["system-admin"]},
]


def _casa(utenti):
    """Home Assistant che risponde `utenti` a `config/auth/list`: il client vero
    sulla casa finta (Tappa 2, Task 12), non un `_ws_send` scritto qui."""
    return CasaFinta({}, answers={"config/auth/list": lambda extra: utenti})


@pytest.mark.asyncio
async def test_il_ruolo_si_chiede_a_home_assistant():
    """Mutazione: dedurre l'amministratore dal nome o dall'ordine invece che dal
    gruppo -- rossa."""
    client = _casa(_UTENTI)

    esito = await client.users()

    assert client.calls == [("config/auth/list", None)]
    per_id = {u["id"]: u for u in esito["utenti"]}
    assert per_id["u-owner"]["amministratore"] is True
    assert per_id["u-admin"]["amministratore"] is True
    assert per_id["u-ospite"]["amministratore"] is False


@pytest.mark.asyncio
async def test_il_proprietario_si_distingue_dagli_altri_amministratori():
    """`is_owner` e' un fatto a parte, e Home Assistant lo tratta a parte: *«Le
    politiche non si applicano all'utente marcato come owner»*. Serve per sapere
    a chi e' di chi la casa senza chiederlo due volte.

    Mutazione: appiattire `proprietario` su `amministratore` -- rossa."""
    client = _casa(_UTENTI)

    per_id = {u["id"]: u for u in (await client.users())["utenti"]}

    assert per_id["u-owner"]["proprietario"] is True
    assert per_id["u-admin"]["proprietario"] is False


@pytest.mark.asyncio
async def test_gli_utenti_di_SISTEMA_si_riconoscono():
    """Il Supervisor stesso e' un utente amministratore generato dal sistema.
    Confonderlo con una persona vorrebbe dire attribuire a qualcuno gli atti di
    una macchina.

    Mutazione: non riportare `sistema` -- rossa."""
    per_id = {u["id"]: u
              for u in (await _casa(_UTENTI).users())["utenti"]}

    assert per_id["u-sistema"]["sistema"] is True
    assert per_id["u-owner"]["sistema"] is False


@pytest.mark.asyncio
async def test_se_home_assistant_NON_risponde_non_si_inventa_un_ruolo():
    """**Il verso del dubbio.** Un guasto di rete non deve diventare un aumento
    di privilegi.

    Mutazione ESEGUITA: ripiegare su un elenco vuoto senza dichiarare l'errore
    -- rossa (chi legge non distinguerebbe «nessun amministratore» da «non ho
    potuto guardare», e sono la stessa forma del difetto che questo prodotto
    insegue ovunque).

    I due modi in cui Home Assistant non risponde davvero: tace (la connessione
    cade) o rifiuta nella busta vera -- `config/auth/list` e'
    `@websocket_api.require_admin`, e il rifiuto e' `unauthorized` /
    «Unauthorized» (`websocket_api/connection.py`, letto sul tag 2026.9.4 il
    03/10/2026). Fino alla Tappa 2 la finta mandava anche
    `{"success": false}` senza `error` e un `error` senza `success`: forme che
    Home Assistant non produce (`websocket_api/messages.py::error_message`), e
    che il client legge comunque come il rifiuto.
    """
    for casa in (CasaFinta({}, silence={"config/auth/list"}),
                 CasaFinta({}, refuse={"config/auth/list": {
                     "code": "unauthorized", "message": "Unauthorized"}})):
        esito = await casa.users()

        assert "errore" in esito, f"{casa.calls!r} non ha prodotto un errore"
        assert "utenti" not in esito, (
            "un elenco vuoto accanto a un errore si legge come «non ce n'erano»")


@pytest.mark.asyncio
async def test_una_risposta_STORTA_non_fa_cadere_la_lettura():
    """Se il `result` non e' un elenco, si dichiara e non si esplode: questa
    lettura sta sul percorso di ogni richiesta, e un'eccezione qui spegnerebbe
    il pannello invece di negare un permesso.

    Mutazione: iterare il `result` senza guardarne la forma -- rossa."""
    esito = await _casa({"non": "un elenco"}).users()

    assert "errore" in esito


# --- chi e' amministratore lo dice la regola di Home Assistant (R-2.10) -----

async def _per_id(righe):
    esito = await _casa(righe).users()
    return {u["id"]: u for u in esito["utenti"]}


@pytest.mark.asyncio
async def test_il_PROPRIETARIO_e_amministratore_anche_fuori_dal_gruppo():
    """Core 2026.9.3, `auth/models.py::User.is_admin`: `is_owner or
    (is_active and system-admin)`. Un proprietario tolto dal gruppo resta
    amministratore per Home Assistant, e il cancello al confine non deve
    chiuderlo fuori.

    Mutazione ESEGUITA: tornare al solo gruppo -- rossa."""
    per_id = await _per_id([{"id": "u-owner", "is_owner": True, "is_active": True,
                             "group_ids": ["system-users"]}])

    assert per_id["u-owner"]["amministratore"] is True


@pytest.mark.asyncio
async def test_un_amministratore_DISATTIVATO_non_e_amministratore():
    """Stessa regola: senza `is_active` il gruppo non basta.

    Mutazione ESEGUITA: ignorare `is_active` -- rossa."""
    per_id = await _per_id([
        {"id": "u-spento", "is_owner": False, "is_active": False,
         "group_ids": ["system-admin"]},
        {"id": "u-muto", "is_owner": False, "group_ids": ["system-admin"]}])

    assert per_id["u-spento"]["amministratore"] is False
    assert per_id["u-muto"]["amministratore"] is False, (
        "un campo che manca non e' un «si'»")


@pytest.mark.asyncio
@pytest.mark.parametrize("gruppi,sola_lettura", [
    (["system-read-only"], True),
    # Core unisce le politiche dei gruppi (`auth/permissions/merge.py`): chi
    # e' anche in `system-users` comanda.
    (["system-read-only", "system-users"], False),
    (["system-users"], False),
])
async def test_il_gruppo_di_SOLA_LETTURA_si_riconosce(gruppi, sola_lettura):
    """R-2.10b: chi in Home Assistant legge e basta non deve comandare da HIRIS.

    Mutazione ESEGUITA: `sola_lettura` sempre falso -- rossa."""
    per_id = await _per_id([{"id": "u-x", "is_owner": False, "is_active": True,
                             "group_ids": gruppi}])

    assert per_id["u-x"]["sola_lettura"] is sola_lettura
    assert per_id["u-x"]["amministratore"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("gruppi,senza", [([], True), (["system-users"], False)])
async def test_chi_non_ha_GRUPPI_si_riconosce(gruppi, senza):
    """Fix round 1, I5: Core 2026.9.3, `auth/models.py::User.permissions` --
    chi non e' il proprietario ha `merge_policies` dei suoi gruppi, e senza
    gruppi non ha nessun permesso.

    Mutazione ESEGUITA: `senza_gruppi` sempre falso -- rossa."""
    per_id = await _per_id([{"id": "u-x", "is_owner": False, "is_active": True,
                             "group_ids": gruppi}])

    assert per_id["u-x"]["senza_gruppi"] is senza
