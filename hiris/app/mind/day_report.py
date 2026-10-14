"""I **resoconti del giorno**: come si compongono, si recuperano e si riparano.

Nasce il 14/10/2026 col vocabolario della riparazione (N161-1, revisore giro
161): `REPAIR_STATES` e' il gemello di `agent/runner.INIT_STATES` e di
`mind/judgments.SNAPSHOT_STATES`, e non poteva restare in `server.py`. Le
funzioni dei resoconti lo raggiungono qui alla Chiusura (F8 passo 3), con un
commit di solo spostamento.
"""
from __future__ import annotations

#: Il vocabolario chiuso di `stato` in `app["ultima_riparazione"]` (C-30): la
#: forma comune degli oggetti diagnostici di `/api/health`, che aprono tutti
#: con `stato` e `perche` (come `agent/runner.INIT_STATES` e
#: `mind/judgments.SNAPSHOT_STATES`). Fino alla Chiusura la chiave era
#: `oggetti`.
REPAIR_DONE, REPAIR_RAISED = "fatta", "sollevata"
REPAIR_STATES = (REPAIR_DONE, REPAIR_RAISED)
