"""Le domande per id dello specchio, per le finte che sanno solo `all_states()`.

Dal 03/10/2026 (Tappa 2, Task 6, A-35) chi cerca un'entita' la chiede allo
specchio per id (`EntityCache.get`, `EntityCache.states_for`) invece di
scandirne tutte le righe. Le finte dello specchio delle prove sapevano dire
solo «ecco tutte le righe»: con questa base rispondono alle due domande nuove
ricavandole dalle loro righe, cosi' ognuna resta com'era (anche quelle che
contano le letture o che si rompono a comando dentro `all_states`).

Le firme sono quelle dello specchio vero, e lo verifica
`tests/test_specchio_per_id.py`. Quando le finte convergeranno su uno specchio
vero (Task 12 della Tappa 2) questa base esce con loro.
"""
from __future__ import annotations


class MirrorById:
    def get(self, entity_id: str) -> dict | None:
        return self.states_for().get(entity_id)

    def states_for(self, entity_ids=None) -> dict[str, dict]:
        rows = {row["id"]: row for row in self.all_states()
                if isinstance(row, dict) and row.get("id")}
        if entity_ids is None:
            return rows
        return {eid: rows[eid] for eid in entity_ids if eid in rows}
