"""Le operazioni delle ricette e del resoconto chiedono i conti a
`home_space/counts.py` (B-13, la meta' di `mind/operations.py`: F7 della
Chiusura applica la patch di F1, 13/10/2026)."""
import ast
import inspect
import textwrap


def test_le_operazioni_chiedono_i_conti_a_counts():
    """`_sum_period` e `_average_min_max` (le operazioni delle ricette e del
    resoconto) chiedono le regole a `counts`, e non chiamano `sum`, `min` o
    `max` da se'. Mutazione ESEGUITA e ripristinata: il minimo di
    `_average_min_max` di nuovo `min(p["minimo"] for p in known)` -- rossa."""
    from hiris.app.mind import operations
    for function, rule in ((operations._sum_period, "hourly_consumed"),
                           (operations._average_min_max, "hourly_mean_min_max")):
        tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
        called = {node.func.id for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        assert rule in called, (function.__name__, called)
        assert not called & {"sum", "min", "max"}, (function.__name__, called)
