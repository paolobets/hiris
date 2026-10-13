"""Gli esiti che il proponente puo' dare a un'osservazione (attori, D12).

**Foglia** (G-24, Chiusura): non importa niente del prodotto. Fino alla
Chiusura le parole vivevano in `proposer_turn`, che sta sopra `mind/store`
negli import (`proposer_turn` -> `analyst_turn` -> `steering`), e l'archivio
che scrive i giri del «Rifalla» le ricopiava in un letterale
(`add_proposal_round`) per non importarlo. Qui le leggono tutti e due.
"""
from __future__ import annotations

#: La proposta e' nata come costruzione: HIRIS la sa scrivere.
BUILT = "costruita"
#: La proposta e' da fare a mano: la applica una persona.
BY_HAND = "a_mano"
#: Niente da proporre, col perche'.
NOTHING = "niente"
#: Tutti, nell'ordine in cui il proponente li dichiara al modello.
OUTCOMES = (BUILT, BY_HAND, NOTHING)
