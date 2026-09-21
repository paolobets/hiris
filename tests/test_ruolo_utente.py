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
import pytest

from hiris.app.proxy.ha_client import HAClient

_UTENTI = [
    {"id": "u-owner", "name": "Paolo", "is_owner": True,
     "system_generated": False, "group_ids": ["system-admin"]},
    {"id": "u-admin", "name": "Seconda", "is_owner": False,
     "system_generated": False, "group_ids": ["system-admin"]},
    {"id": "u-ospite", "name": "Ospite", "is_owner": False,
     "system_generated": False, "group_ids": ["system-users"]},
    {"id": "u-sistema", "name": "Supervisor", "is_owner": False,
     "system_generated": True, "group_ids": ["system-admin"]},
]


class _Finto(HAClient):
    def __init__(self, messaggio):
        self._messaggio = messaggio
        self.chiesto = []

    async def _ws_command(self, msg_type, extra=None, timeout=10.0):
        self.chiesto.append(msg_type)
        return self._messaggio


@pytest.mark.asyncio
async def test_il_ruolo_si_chiede_a_home_assistant():
    """Mutazione: dedurre l'amministratore dal nome o dall'ordine invece che dal
    gruppo -- rossa."""
    client = _Finto({"success": True, "result": _UTENTI})

    esito = await client.users()

    assert client.chiesto == ["config/auth/list"]
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
    client = _Finto({"success": True, "result": _UTENTI})

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
              for u in (await _Finto({"success": True, "result": _UTENTI}).users())["utenti"]}

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
    """
    for messaggio in (None,
                      {"success": False},
                      {"error": {"message": "unauthorized"}}):
        esito = await _Finto(messaggio).users()

        assert "errore" in esito, f"{messaggio!r} non ha prodotto un errore"
        assert "utenti" not in esito, (
            "un elenco vuoto accanto a un errore si legge come «non ce n'erano»")


@pytest.mark.asyncio
async def test_una_risposta_STORTA_non_fa_cadere_la_lettura():
    """Se il `result` non e' un elenco, si dichiara e non si esplode: questa
    lettura sta sul percorso di ogni richiesta, e un'eccezione qui spegnerebbe
    il pannello invece di negare un permesso.

    Mutazione: iterare il `result` senza guardarne la forma -- rossa."""
    esito = await _Finto({"success": True, "result": {"non": "un elenco"}}).users()

    assert "errore" in esito
