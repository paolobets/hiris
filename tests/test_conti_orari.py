"""I conti di un periodo fatto di ore vivono in `home_space/counts.py` (B-13).

F1 della Chiusura (13/10/2026). Le regole (consumato = somma dei cambi; media
delle medie, minimo dei minimi, massimo dei massimi, l'estremo mancante di
un'ora che vale la sua media) erano scritte in `mind/operations.py` e in
`house_history._band_counts`. Mutazioni ESEGUITE e ripristinate (`git status`
pulito):
- in `counts.hourly_mean_min_max` il minimo preso dalle medie -- rosse
  `test_il_minimo_e_il_piu_piccolo_dei_minimi_orari` e
  `test_la_storia_chiede_i_conti_a_counts`;
- in `_band_counts` il minimo di nuovo `min(lows or means)` scritto in linea --
  rosse `test_la_storia_non_si_rifa_i_conti` e `test_la_storia_chiede_i_conti_a_counts`.
"""
import ast
import inspect
import textwrap

from hiris.app.home_space import counts, house_history


def test_il_minimo_e_il_piu_piccolo_dei_minimi_orari():
    found = counts.hourly_mean_min_max([(16.0, 14.0, 18.0), (18.0, None, None)])
    assert found == {"media": 17.0, "minimo": 14.0, "massimo": 18.0}


def test_un_ora_senza_estremi_vale_la_sua_media():
    found = counts.hourly_mean_min_max([(16.0, 15.0, 17.0), (12.0, None, None)])
    assert found["minimo"] == 12.0
    assert counts.hourly_mean_min_max([]) is None


def test_il_consumato_e_la_somma_dei_cambi():
    assert counts.hourly_consumed([1.5, 0.25, 0.0]) == 1.75


def test_la_storia_chiede_i_conti_a_counts():
    bands = [{"media": 16.0, "minimo": 14.0, "massimo": 18.0},
             {"media": 18.0}, {"media": 17.0, "minimo": 16.5, "massimo": 19.5}]
    found = house_history._band_counts(bands, "measurement")
    assert found == {"primo": 16.0, "ultimo": 17.0, "minimo": 14.0, "massimo": 19.5,
                     "media": 17.0}
    meter = house_history._band_counts(
        [{"a_fine_ora": 10.0, "cambio": 0.5}, {"a_fine_ora": 10.75, "cambio": 0.75}],
        "total_increasing")
    assert meter["consumato"] == 1.25


def test_la_storia_non_si_rifa_i_conti():
    """`_band_counts` non chiama `sum`, `min` o `max` sui valori: li chiede a
    `counts`. Gli estremi delle letture di fine ora di un contatore
    (`a_fine_ora`) non sono conti di ore e restano suoi."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(house_history._band_counts)))
    measure = max((node for node in ast.walk(tree) if isinstance(node, ast.Return)),
                  key=lambda node: node.lineno)
    called = {node.func.id for node in ast.walk(measure)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not called & {"sum", "min", "max"}, called
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert {"hourly_consumed", "hourly_mean_min_max"} <= names, names

