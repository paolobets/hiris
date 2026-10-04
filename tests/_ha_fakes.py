"""Le finte di `HAClient` condivise fra piu' prove.

**Una sola per contratto.** Prima ce n'erano quattro per `legami`, fra due
file, una delle quali definita due volte nello stesso: potevano divergere dal
contratto vero ciascuna per conto proprio, ed e' cosi' che una finta infedele
ha reso invisibile un difetto per settimane.

Questo file nasce il 15/09/2026, quando `test_mind_companions.py` e' uscito coi
comprimari (spec §13): le prove di `build_companions` sono morte con lui, ma la
finta serviva ancora a chi prova lo STRUMENTO `related` e i bilanci. **I
bilanci sono usciti il 01/10/2026** (`server.build_balances`, con
`tests/test_server_balances.py`): con loro e' uscita la meta' della finta che
fingeva `hourly_statistics` e la lettura dei registri, che nessun'altra prova
chiedeva. **La finta di `related` e' uscita il 04/10/2026** (Tappa 2, Task
12): `tests/test_related_tools.py` usa la casa finta (`scripts/casa_finta.py`),
cioe' il client vero col trasporto sostituito. Restano i due trasporti finti
qui sotto, per le prove del client che li usano.
"""


def ws_send_from_messages(fake):
    """Un `_ws_send` finto da una finta che risponde UN messaggio intero per
    comando (`{success, result, error}`, o `None` per «la connessione non
    c'e'»): `fake(msg_type, extra)`. Era la forma di `_ws_command`, uscito
    con A-28: le prove che fingevano un comando solo restano scritte cosi'."""
    async def ws_send(commands, timeout=10.0):
        return [await fake(msg_type, extra) for msg_type, extra in commands]
    return ws_send


def ws_send_from_results(fake):
    """Un `_ws_send` finto da una finta che risponde il solo `result` di un
    comando: `fake(msg_type, extra)`. `None` e' la connessione caduta (il
    messaggio non c'e'), ogni altro valore un successo con quel `result`. Era
    la forma di `_ws_request`, uscito con A-28."""
    async def ws_send(commands, timeout=10.0):
        replies = []
        for msg_type, extra in commands:
            result = await fake(msg_type, extra)
            replies.append(None if result is None else
                           {"type": "result", "success": True, "result": result})
        return replies
    return ws_send

