# Archivio — documenti superati

**Questi documenti sono STORIA, non specifica.**

Descrivono HIRIS com'era prima del **Refactor 2.0** (4 agosto 2026). Contengono decisioni,
vocabolario e architetture che sono state deliberatamente abbandonate.

> ⚠️ **Non usarli come fonte per capire come funziona HIRIS, né come base per scrivere codice.**
> Chi cerca la verità corrente ha tre documenti, tutti in `docs/design/`:
>
> | Domanda | Documento |
> |---|---|
> | Cosa **deve** fare HIRIS | `2026-08-04-scope-hiris.md` — il contratto |
> | Cosa **fa oggi** il codice | `2026-08-03-analisi-funzionale.md` — con riferimenti `file:riga` |
> | Che **stato tecnico** ha | `2026-08-03-revisione-tecnica.md` |

## Perché sono ancora qui

Perché spiegano **come ci siamo arrivati**. Diverse scelte del refactor si capiscono solo leggendo
la decisione che le ha precedute, e alcune trappole scoperte allora sono ancora vere anche se il
contesto è cambiato.

Sono stati **spostati, non cancellati**: git conserva comunque tutta la storia, ma un documento
archiviato in una cartella che dichiara di esserlo non inganna nessuno, mentre lo stesso documento
lasciato in `docs/design/` sì.

## Vocabolario che troverai qui e che non esiste più

| Termine archiviato | Cosa era | Oggi |
|---|---|---|
| **Sentinella** | il motore di sorveglianza proprio | assorbito: l'agente ha i propri sensi |
| **Agentbot** | l'entità autonoma a verdetto-JSON | si chiama **agente** |
| **Persona** / **Lente** | nomi intermedi mai consolidati | — |
| **Semaforo** (per-azione) | gate a 4 colori su ogni azione | assorbito nei **permessi del perimetro** |
| **Modalità regola** | agente senza ragionamento | non esiste: se non ragiona è un'automazione HA |
| **Workbench** | HIRIS come pannello di configurazione di entità AI | superato: HIRIS è l'intelligenza della casa |

## Contenuto

- `design/` — 27 documenti di design e piani di sprint, da giugno a inizio agosto 2026
- `design/plans/` — 7 piani di fase del *second brain* e dello storico
- `reviews/` — la revisione completa del codice del 25 luglio 2026 (i 4 CRITICAL e i 13 HIGH che
  vi sono descritti sono stati chiusi in v0.90.0)
