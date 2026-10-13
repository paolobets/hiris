"""I conti di un periodo fatto di ore: una casa sola (B-13).

Home Assistant consegna le statistiche orarie gia' calcolate
(`recorder/statistics_during_period`, tradotte da
`proxy/ha_client._translate_statistics`): un contatore porta il `cambio`
dell'ora, gia' corretto per gli azzeramenti; una misura istantanea porta
`media`, `minimo` e `massimo` dell'ora. I conti del periodo si fanno su quelle
ore, e le regole sono due:

- **il consumato e' la somma dei cambi**, non la differenza fra l'ultima e la
  prima lettura (che un azzeramento rovescerebbe);
- **la media e' la media delle medie orarie** (ore di peso uguale), **il
  minimo il piu' piccolo dei minimi orari, il massimo il piu' grande dei
  massimi**: una stanza che scende a 14 gradi alle sei del mattino ha una media
  oraria di 16, e il minimo delle medie direbbe 16, nascondendo proprio cio'
  che si cercava. Un'ora che non porta un estremo vale per quell'estremo la sua
  media.

**Perche' qui.** Fino al 13/10/2026 (F1 della Chiusura) le stesse regole erano
scritte due volte: in `mind/operations.py` (`_sum_period`, `_average_min_max`,
le operazioni delle ricette e del resoconto) e in
`home_space/house_history.py` (`_band_counts`, la storia della chat). Due
copie che coincidevano, salvo un caso: con alcune ore senza `minimo` la storia
prendeva il minimo dei soli minimi, le operazioni quello di ogni ora. Ora
vale la regola per ora, per tutte e due.

**I conti non arrotondano.** L'arrotondamento e' di chi rende: le operazioni a
due decimali, la storia a tre (piano della Tappa 3, D4). Ne' giudicano la
copertura: quella e' delle operazioni (`NotComputable`), che sanno quante ore
il periodo doveva avere.
"""
from __future__ import annotations

from collections.abc import Iterable


def hourly_consumed(changes: Iterable[float]) -> float:
    """Il consumato del periodo: la somma dei `cambio` orari."""
    return sum(changes)


def hourly_mean_min_max(hours: Iterable[tuple[float, float | None, float | None]]) -> dict | None:
    """`(media, minimo, massimo)` di ogni ora -> `{"media", "minimo",
    "massimo"}` del periodo, o `None` senza nessuna ora. Un estremo `None`
    vale la media della sua ora."""
    hours = list(hours)
    if not hours:
        return None
    return {"media": sum(mean for mean, _low, _high in hours) / len(hours),
            "minimo": min(mean if low is None else low for mean, low, _high in hours),
            "massimo": max(mean if high is None else high for mean, _low, high in hours)}
