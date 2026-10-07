"""Il cervello di HIRIS.

Gli attori e cio' su cui lavorano (ricavato da `ls` il 28/09/2026):

- l'**osservatore** guarda la casa e ne ricava il resoconto di ogni giorno:
  `watcher`, `observer`, `scope`, `cadence`, `facts`, `report`;
- il **sapere** e le **ricette** -- cio' che HIRIS ha capito della casa e come
  si calcola una misura: `knowledge`, `seed`, `recipes`, `recipe_turn`,
  `operations`, `judgments`;
- l'**analista** legge le misure e ne trae osservazioni: `analyst`,
  `analyst_turn`;
- il **proponente** (fino al 06/10/2026 l'attuatore) propone, non tocca la
  casa: `proposer_turn` (il turno), `proposer_round` (il giro);
- l'archivio di tutti: `store`.

Il **verificatore** non c'e' ancora, e questo pacchetto NON prepara ingressi
per lui (vedi la spec §5: un ingresso che nessuno alimenta e' codice morto
travestito da previsione).
"""
