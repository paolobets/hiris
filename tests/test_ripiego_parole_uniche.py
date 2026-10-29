"""Le parole del ripiego dal ponte alla catena sono scritte una volta sola.

Il motivo di un ripiego e' una **chiave** di
`model_resolution._DOWNGRADE_REASONS`, e una chiave che non corrispondesse
alla parola di chi la scrive non produrrebbe un errore: produrrebbe silenzio,
cioe' un passaggio dal forfait al consumo che nessuno annuncia. Fino al giro
222 del revisore «scadenza» e «tetto giornaliero» erano ricopiate fra chi le
scrive (`steering`, `api/handlers_chat`) e la tabella: adesso sono costanti di
`answer_reasons`, e «manca il token» vive in `providers`.

La prova non ricopia l'elenco delle parole: lo chiede alla tabella stessa, e
cerca nel prodotto ogni letterale uguale a una sua chiave. Ognuna deve
comparire una volta sola, dove nasce. Zero volte vorrebbe dire che la ricerca
non guarda piu' dove deve; due volte, che una copia e' tornata.
"""
from __future__ import annotations

import ast
from pathlib import Path

from hiris.app.model_resolution import _DOWNGRADE_REASONS

APP = Path(__file__).resolve().parent.parent / "hiris" / "app"


def _letterali(chiavi: set[str]) -> dict[str, list[str]]:
    """Dove ogni chiave compare come stringa nel prodotto, docstring escluse."""
    trovati: dict[str, list[str]] = {chiave: [] for chiave in chiavi}
    for percorso in sorted(APP.rglob("*.py")):
        albero = ast.parse(percorso.read_text(encoding="utf-8"))
        docstring = {id(nodo.value) for nodo in ast.walk(albero)
                     if isinstance(nodo, ast.Expr)
                     and isinstance(nodo.value, ast.Constant)}
        for nodo in ast.walk(albero):
            if (isinstance(nodo, ast.Constant) and nodo.value in trovati
                    and id(nodo) not in docstring):
                trovati[nodo.value].append(
                    f"{percorso.relative_to(APP).as_posix()}:{nodo.lineno}")
    return trovati


def test_ogni_motivo_ripiego_scritto_una_volta_sola():
    chiavi = set(_DOWNGRADE_REASONS)
    assert chiavi, "la tabella dei ripieghi e' vuota: la prova non guarda niente"
    for chiave, dove in _letterali(chiavi).items():
        assert len(dove) == 1, (
            f"«{chiave}» compare {len(dove)} volte nel prodotto ({dove}): si "
            "importa la costante da dove nasce, non si ricopia la parola")
