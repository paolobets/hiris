# HIRIS — Testbook

Raccolta dei test UAT (User Acceptance Testing) per ogni rilascio di HIRIS.

## Struttura

Ogni rilascio ha il proprio file `vX.Y.Z-UAT.md`:

```
Testbook/
├── README.md          ← questo file
├── v0.0.2-UAT.md
├── v0.0.3-UAT.md
└── ...
```

## Come si usa

1. **Prima del rilascio** — esegui tutti i casi di test del file UAT corrispondente
2. **Per ogni caso** — aggiorna lo `Status` e annota eventuali problemi nella sezione `Issues`
3. **Rilascio approvato** — tutti i casi obbligatori (🔴) devono essere `PASS`

## Stato dei test

| Simbolo | Significato |
|---------|-------------|
| `⬜ PENDING` | Non ancora eseguito |
| `✅ PASS` | Superato |
| `❌ FAIL` | Fallito — vedi Issues |
| `⏭ SKIP` | Saltato (prerequisito mancante, es. no Telegram) |

## Priorità

| Simbolo | Significato |
|---------|-------------|
| 🔴 | Obbligatorio — blocca il rilascio se fallisce |
| 🟡 | Importante — da risolvere prima della GA |
| 🟢 | Nice to have — gestibile dopo il rilascio |

## Sezione Issues

Ogni caso di test ha una sezione `Issues` dove annotare:
- bug riscontrati (con descrizione breve)
- link a GitHub issue se aperta
- workaround temporanei

Esempio:
```
**Issues:**
- [BUG] Il pulsante Save non risponde su Safari mobile → #12
- [WORKAROUND] Usare Chrome fino al fix
```
