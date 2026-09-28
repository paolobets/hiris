"""Il cervello di HIRIS.

Tre attori e cio' su cui lavorano (ricavato da `ls` il 28/09/2026):

- l'**osservatore** guarda la casa e ne ricava oggetti: `watcher`, `observer`,
  `scope`, `cadence`, `facts`, `report`;
- il **sapere** e le **ricette** -- cio' che HIRIS ha capito della casa e come
  si calcola una misura: `knowledge`, `seed`, `recipes`, `recipe_turn`,
  `operations`, `judgments`;
- l'**analista** legge le misure e ne trae osservazioni: `analyst`,
  `analyst_turn`;
- l'**attuatore** fa il passo successivo -- indaga o propone, non tocca la
  casa: `actuator`, `actuator_turn`;
- l'archivio di tutti: `store`.

Il **verificatore** non c'e' ancora, e questo pacchetto NON prepara ingressi
per lui (vedi la spec §5: un ingresso che nessuno alimenta e' codice morto
travestito da previsione).
"""
