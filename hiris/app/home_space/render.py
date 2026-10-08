"""La resa: una funzione per genere di oggetto (Tappa 9, «Una resa per
oggetto»; piano della Tappa 4, Task 7-8).

Ogni oggetto della casa che HIRIS mostra -- al modello, a una pagina, a un
servizio firmato -- esce da UNA funzione di questo modulo, col vocabolario
dei campi (`field_vocabulary`) e a una delle tre profondita' (corta, media,
completa). Le porte chiamano la resa e inoltrano il suo dizionario: non lo
compongono (R3, `tests/test_resa_unica.py`).
"""
from __future__ import annotations
