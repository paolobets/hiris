# BACKLOG — gli argomenti in attesa di uno sprint

Questo documento non e' storia: e' il **registro**. Ci si scrive quando nasce un argomento, ci si
legge quando si sceglie cosa fare. Non porta una data di redazione perche' non e' la fotografia di
un giorno: e' vivo.

**Sta in git, e non e' un accidente.** Il progetto aveva gia' avuto una `docs/ROADMAP.md`: e' stata
tolta dal tracciamento e messa in `.gitignore` il 30/04/2026 (commit `8c4d615d`), e oggi non esiste
piu' nemmeno sul disco. Un registro che git non vede e' un registro che nessuna sessione puo'
leggere, e sparisce senza che nessuno se ne accorga. Questo file non ha quella scusa: se una voce
non c'e', e' perche' nessuno ce l'ha scritta.

## Come ci si scrive

**Quando il proprietario dice «inseriamo per il prossimo sprint», la voce entra qui, subito**,
prima di continuare il discorso. Non in un appunto, non in una risposta in chat, non nella memoria
di una sessione: qui. Una voce annotata altrove e' una voce persa — ed e' gia' successo.

Una voce e' **atomica**: si deve capire cosa chiede senza andare a cercare altrove. Se il dettaglio
merita un documento, la voce lo nomina; se il documento non esiste, la voce dice «nessun documento»
e si porta dentro tutto cio' che serve a ricostruirla.

Ogni voce dichiara **da dove viene**. La provenienza non e' cortesia: distingue cio' che il
proprietario ha chiesto da cio' che e' emerso misurando, e le due cose non hanno lo stesso peso
quando si sceglie.

## Come si legge

Le voci stanno in tre stati, e lo stato e' **la sezione in cui la voce si trova** — non una colonna
che puo' restare indietro rispetto ai fatti.

| Stato | Vuol dire |
|---|---|
| **In attesa** | Nessuno l'ha ancora scelta. E' il magazzino da cui si pesca. |
| **Scelto** | Entra nello sprint in corso. |
| **Uscito** | Chiuso da un rilascio, che la voce nomina. Il dettaglio sta nel CHANGELOG. |

Una voce non si cancella quando esce: si sposta. Un backlog che dimentica cosa ne e' stato delle sue
voci non sa dire se il lavoro procede.

---

## Scelti — sprint in corso

*Nessuno. L'ultimo sprint chiuso e' «i menu esecutivi» (3.21.0 / 3.21.1, 04/09/2026).*

---

## In attesa

> **Avvertenza sulla prima stesura (04/09/2026).** Il proprietario aveva chiesto di annotare una
> lista di argomenti per il prossimo sprint, e quella lista **non e' stata salvata da nessuna
> parte**: cercata in tutto il repository, nelle cartelle ignorate, nelle issue e nelle milestone di
> GitHub, non esiste. Le voci qui sotto **non sono quella lista**: sono ricostruite dai documenti
> del repository e da cio' che e' stato misurato sulla casa vera. La lista del proprietario va
> reinserita da lui, e queste voci vanno lette come un fondo di magazzino, non come una sua scelta.

### I comandi verso Home Assistant

`origine: deciso dal proprietario il 04/09/2026` · `documento: docs/design/2026-09-04-i-comandi-verso-home-assistant.md`

Colmare i buchi di scrittura verso HA emersi dallo studio di `ha-mcp`: plance, categorie, etichette
(update e delete), aree e piani, zone, calendari con ricorrenze, gruppi e liste, i 17 helper a
config-flow, blueprint. Lo studio porta la chiamata esatta di ognuno, letta nel loro sorgente. **Non
e' una specifica**: il perimetro non e' stato scelto.

### La sicurezza

`origine: deciso dal proprietario il 04/09/2026` · `documento: docs/design/2026-09-04-la-sicurezza-il-seme.md`

Sprint a se', **dopo** quello dei comandi. Il reperto che lo apre: HIRIS non ha nessuna lista di
servizi vietati. Cio' che oggi rende irraggiungibili `homeassistant.restart`, `hassio.host_reboot`,
`recorder.purge`, `shell_command.*` e' un accidente di forma — quei servizi non dichiarano un
`target`, e un bersaglio vuoto e' sempre stato un rifiuto. La difesa non e' progettata: e'
incidentale, e cade tutta insieme il giorno in cui quella condizione si allarga.

### La scheda della proposta dentro la chat

`origine: il proprietario, segnalata il 03/09/2026` · `documento: docs/design/2026-09-03-i-menu-esecutivi.md §6.4`

L'anteprima con Approva e Rifiuta li' dove la frase la annuncia, senza cambiare pagina. Il
proprietario l'ha voluta segnalata, non fatta allora. Costa **rimettere `tools_called` nella
risposta della chat**, tolto il 17/08.

### Il vocabolario del dato

`origine: il proprietario, rimandata il 03/09/2026` · `documento: docs/design/2026-09-03-i-menu-esecutivi.md §7`

La lingua del database, i valori di dominio e le chiavi dei record fra motore e pagina: **una fetta
sola**, perche' sono la stessa cosa. Rinominare i fatti che ci sono costa la riscrittura di ogni
query che li nomina — al contrario di aggiungere un fatto che manca, che costa una migrazione
additiva e reversibile.

### Le tracce delle automazioni e il log di sistema

`origine: deciso dal proprietario il 31/08/2026` · `nessun documento`

Due fonti nuove di HA, e devono essere disponibili **a entrambi i lettori**: lo strumento della chat
E l'osservatore. Una fonte sola, due lettori — l'osservatore «non apre un secondo rubinetto», perche'
due sorgenti degli stessi eventi possono divergere. Le chiamate sono `trace/list`, `trace/get`,
`trace/contexts` e `system_log/list`, tutte WS e tutte `require_admin`.

Misurato sulla casa il 30-31/08: 72 tracce su 16 automazioni, 64 `finished`, 7 `failed_conditions`,
1 `error` — e un'automazione rotta davvero, mai segnalata al proprietario; 17 voci di log, 11
WARNING e 6 ERROR.

Due trappole gia' pagate, che decidono il lavoro e non si vedono nella documentazione:
**le tracce hanno una finestra** (HA ne conserva 5 per automazione, poi la sesta cancella la prima —
decide se si puo' guardare a cadenza o si devono seguire mentre accadono); e **il log arriva gia'
giudicato**, perche' `system_log/list` consegna righe raggruppate da HA con `count` e
`first_occurred`, il che rompe la legge dell'osservatore «scrivi il grezzo, giudica dopo».

### `get_error_log()` si cancella

`origine: deciso dal proprietario il 31/08/2026` · `nessun documento`

`proxy/ha_client.py::get_error_log()` ha i test e **zero chiamanti vivi**. Punta a
`/api/error_log`, che su HA 2026.8.3 risponde 404, e **inghiotte il 404 restituendo
`{"errors": 0, "warnings": 0}`**: collegarlo com'e' farebbe dire a HIRIS «zero errori» su una casa
che ne ha 6+11. E' lo zero che afferma. Non e' una migrazione — il vecchio punta a un endpoint che
non esiste piu' e mente quando non lo trova: si cancella il metodo e si cancellano i suoi test.

### La salute di un'integrazione non e' il suo stato

`origine: misurato sulla casa vera il 02/09/2026` · `nessun documento`

Un'integrazione `loaded` con **tutte** le entita' morte oggi e' invisibile. Sulla casa: 162 entita'
su 827 (19,6%) sono `unavailable` o `unknown`, comprese tutte e 16 quelle dell'irrigazione
(Hydrawise risponde 403, 40 errori nel log). Ma `hydrawise` e' `loaded`, quindi non compare fra i
guasti, e il briefing non nomina mai «non disponibile». L'irrigazione e' ferma e HIRIS non lo
direbbe. La salute di un'integrazione e' **quante delle sue entita' rispondono**, non il suo `state`.

### Un episodio per condizione, non venticinque

`origine: misurato sulla casa vera il 02/09/2026` · `nessun documento`

L'osservatore apre un episodio nuovo a ogni sfarfallio: **25 episodi di guasto per una sola
integrazione** (`lifx / Abat-jour`, `setup_retry`), e cinque aperti contemporaneamente per la stessa
cosa. Una condizione che va e viene dovrebbe essere un episodio finche' non finisce: il genere
decide la forma, e la forma di una condizione e' la **durata**.

### La piattaforma non e' cercabile

`origine: misurato sulla casa vera il 02/09/2026` · `nessun documento`

`view` restituisce gia' `"piattaforma": "hydrawise"`, ma `search` indicizza solo nome, area e
dispositivo. Non si puo' chiedere «cosa espone l'integrazione Sonos», ne' «l'irrigazione funziona».
Misurato: `search "sonos"` → **0 risultati**, mentre HA ha 13 entita' con piattaforma `sonos` — si
chiamano «Sala da pranzo».

### La gamba «acqua» dell'osservatore

`origine: dichiarata nella spec dell'osservatore, mai fatta` · `documento: docs/design/2026-08-26-l-osservatore.md`

32 entita' di irrigazione, **zero osservate**. La gamba e' progettata e non fatta: `valve`+`water` e
`sensor`+`water` — che oggi finirebbe nell'energia, ed e' una risorsa diversa.

### Il prompt dell'obiettivo dell'osservatore

`origine: dichiarata nella spec dell'osservatore, mai fatta` · `documento: docs/design/2026-08-26-l-osservatore.md`

Non esiste ancora: il pavimento e' fisso, e il prompt dovra' solo allargarlo. E' il motivo per cui
**8 domini su 10** fra quelli elencati come funzionanti (luci, interruttori, ventilatori, media
player, valvole...) oggi non producono nessun oggetto — il pavimento non li lascia passare.

### `build.yaml` dichiara una licenza che non e' la nostra

`origine: rilevato il 10/08/2026` · `nessun documento`

`hiris/build.yaml:9` dichiara `org.opencontainers.image.licenses: "MIT"`, etichetta che finisce
nell'immagine Docker pubblicata, mentre `LICENSE` dice «PROPRIETARY SOFTWARE LICENSE». Da sanare
prima di un rilascio.

---

## Usciti

*Nessuno ancora: il registro nasce oggi, 04/09/2026.*
