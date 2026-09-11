"""Chi decide cosa si guarda, e con quanta informazione in mano.

Lo scope non e' una lista: e' un insieme di **decisioni con un autore**. La
spec prevedeva un movimento solo -- dalla pagina si puo' togliere qualcosa a
cio' che l'osservatore ha scelto (§11). Il proprietario ha aggiunto il secondo
(11/09/2026): **l'osservatore toglie, ma l'analista puo' far rientrare**, e
perche' qualcosa resti fuori davvero devono essere d'accordo in due.

**L'ordine qui sotto non e' una gerarchia di importanza: e' una gerarchia di
INFORMAZIONE.**

- l'**osservatore** decide guardando l'anagrafe e l'obiettivo: sa cosa la casa
  E', non cosa fa;
- l'**analista** decide dopo aver letto i resoconti: ha in mano una cosa che
  l'osservatore non aveva -- come la casa si e' comportata davvero. E' la
  forma che il §1 della consegna del 09/09 gia' descriveva, *«l'analista
  dovrebbe accorgersi che ci sono nuove entita' che permettono di capire meglio
  come la casa risponde»*;
- il **proprietario** sa perche' ha quella casa, e resta l'unica manopola.

**Chi sa di piu' non viene scavalcato da chi sa di meno**: e' l'unica regola
che rende vero l'emendamento. Senza, l'analista rimette dentro, l'osservatore
al giro successivo ritoglie, e la casa oscilla per sempre senza che nessuno lo
veda -- una decisione presa con piu' informazione cancellata da una presa con
meno.

**Chiunque puo' sempre cambiare la PROPRIA idea**: l'autorita' protegge da chi
sa meno, non da se stessi. Un osservatore che riconsidera la casa deve poter
correggere la propria decisione, o la cadenza di riconsiderazione non
servirebbe a niente.
"""
from __future__ import annotations

#: I tre autori, e il loro ordine. I nomi sono inglesi perche' finiscono in una
#: colonna nuova (regola del 04/09/2026); cio' che significano lo dice il
#: docstring qui sopra.
OBSERVER = "observer"
ANALYST = "analyst"
OWNER = "owner"

#: Quanta informazione aveva chi ha deciso. Il numero non ha nessun significato
#: fuori dal confronto: serve solo a rispondere a «questo autore puo'
#: sovrascrivere quell'altro?».
AUTHORITY = {OBSERVER: 1, ANALYST: 2, OWNER: 3}


def may_overwrite(new_author: str, standing_author: str | None) -> bool:
    """Se `new_author` puo' sostituire la decisione di `standing_author`.

    Nessuna decisione in piedi: chiunque puo' scriverla.

    Altrimenti decide il confronto, e **il confronto e' `>=`, non `>`**: e'
    quello che lascia a ciascuno la facolta' di cambiare la PROPRIA idea, senza
    bisogno di un ramo apposta. Un `>` sarebbe la stessa riga con un difetto
    dentro -- un osservatore che riconsidera la casa non potrebbe piu'
    correggersi, e la cadenza di riconsiderazione non servirebbe a niente.
    """
    if standing_author is None:
        return True
    return AUTHORITY.get(new_author, 0) >= AUTHORITY.get(standing_author, 0)
