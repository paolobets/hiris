# Il registro dei doppioni — la lista di lavoro dello sprint «Una fonte sola di verità»

Nato il 01/10/2026 sulla v3.72.2 come indice v2 dell'analisi. È la lista di lavoro: una riga per voce, i dettagli restano nei rapporti a cui la riga rimanda.
**Si legge con un programma**: `python scripts/registro.py conta` dice quante voci sono aperte e chiuse; `chiudi <id>` sposta una voce nella sezione «Chiuse» in fondo; `verifica` gira nel cancello. La prova è `tests/test_registro.py`.
Fonde il registro v1 (`REGISTRO-DEI-DOPPIONI.md`: 155 voci A–G e T, 41 righe M, 20 righe X) con le parti 2 e 3 dei nove rapporti di copertura (`copertura-1…9-*.md`, sigle `cop-1`…`cop-9`).
**Regola di chiusura: una voce si chiude solo quando la copia è cancellata.** Una prova che passa o un commento che promette non chiudono niente.
Gli id del registro v1 non cambiano; i reperti nuovi continuano la numerazione del capitolo (A da A-19, B da B-30, C da C-28, D da D-34, E da E-09, F da F-14, G da G-16, T da T-13, M da M-42, X da X-21). Il capitolo S è nuovo.
Legenda. `Stato`: `E` equivalente · `D` divergente · `NV` non verificato (anche quando il rapporto marca lo stato come dedotto, [D]) · `RITIRATA`. `Unirla`: `PS` pura sostituzione · `CC` cambia comportamento · `DP` decisione del proprietario · `—` non dichiarata dal rapporto. Se il rapporto ne dà due, vale la prima.
`Sulla casa vera`: il numero misurato sulla casa, quando un rapporto ce l'ha; vuoto altrimenti (i conti letti dal codice non sono misure e non stanno qui). Nei capitoli M e X la colonna `Righe` dice dove sta il reperto (`file:riga`).
`Corretta da`: il rapporto di copertura che ha corretto la voce, col tipo di correzione; il testo di ogni correzione è nelle sezioni 2 e 5 in coda. `Fonti`: `reg` = registro v1 (che a sua volta cita d1…d8, db, sonda…); `cop-N` da solo = quel rapporto ha riletto e confermato; `cop-N <id>` = reperto di quel rapporto (id locale suo; dove il rapporto non numera, capitolo + ordinale nella sua parte 2).
Stato e rischio sono copiati dai rapporti, non rivalutati. Dove due rapporti danno verdetti diversi sulla stessa voce stanno entrambi, marcati `CONTRADDIZIONE`.
File relativi a `hiris/app/` salvo diverso avviso.

---

## A. Leggere da Home Assistant

| Id | Voce (max 14 parole) | Stato | Unirla | Sulla casa vera | Corretta da | Fonti |
|---|---|---|---|---|---|---|
| A-01 | Il registro di HA letto da quattro percorsi (`read_registries`: 11 comandi su 2 connessioni) | E | CC |  | cop-5 (conteggio); cop-9 (incompleta) | reg · cop-5 · cop-9 |
| A-02 | `repairs/list_issues` letto da due giri (5 e 10 minuti: 432 letture al giorno) | E | PS |  | cop-1 (conteggio) | reg · cop-1 · cop-2 |
| A-03 | `GET /api/states` intero riletto da tre percorsi oltre allo specchio | NV | DP |  | cop-9 (incompleta) | reg · cop-9 |
| A-04 | `GET /api/services`: il registro servizi e il bypass di `recipient` | E | CC |  | cop-9 (incompleta) | reg · cop-9 |
| A-05 | `recorder/list_statistic_ids` letto due volte da due giri | E | PS |  |  | reg |
| A-06 | `config/entity_registry/get_entries` scaricato per intero, usato solo `aliases` | E | CC |  | cop-5 (incompleta) | reg · cop-5 |
| A-07 | Avvio e riconnessione: la stessa casa riletta 3-4 volte nei primi secondi | E | PS |  | cop-2 (incompleta, conteggio) | reg · cop-2 |
| A-08 | Anagrafe e specchio degli stati: due rappresentazioni vive della stessa casa, non coordinate | NV | DP |  | cop-4 (conteggio) | reg · cop-4 N-15 |
| A-09 | Lo specchio non riprova se `get_states` fallisce dopo il riavvio di HA | NV | CC |  |  | reg · cop-5 |
| A-10 | Anagrafe parziale che sostituisce quella buona: spariscono gli alias di tutta la casa | NV | CC |  |  | reg · cop-4 · cop-5 |
| A-11 | `integrazioni.stato` dell'anagrafe: nessun evento la aggiorna | D | CC |  |  | reg · cop-4 · cop-5 |
| A-12 | Comportamento delle automazioni (`attiva`, `nome`) in RAM fino a 5 minuti contro lo specchio | D | CC |  | cop-3 (imprecisa) | reg · cop-3 · cop-4 |
| A-13 | Indice `Lookup` costruito in tre posti con tre ingressi; il di più è inerte | D | PS |  | cop-9 (verdetto) | reg · cop-3 · cop-8 · cop-9 N-B-1 |
| A-14 | Traduzioni degli stati: lingua vecchia fino a 5 minuti dopo un cambio di riferimento | NV | CC |  |  | reg |
| A-15 | `workshop._reread`: la terza casa dello stato | NV | DP |  |  | reg · cop-9 |
| A-16 | Dizionari ricostruiti al volo che ricopiano l'anagrafe | D | CC |  | cop-1 (righe, incompleta); cop-4 (righe); cop-6 (conteggio, righe, incompleta) | reg · cop-1 · cop-4 · cop-6 |
| A-17 | Copie dei dati nei DB del cervello e della memoria: volute e non volute | D | DP |  | cop-6 (incompleta) | reg · cop-6 · cop-9 |
| A-18 | Contenitori che invecchiano per scelta dichiarata | E | DP |  | cop-6 (incompleta, righe) | reg · cop-4 · cop-6 |
| A-19 | La finestra di memoria rimisurata a ogni lotto della campagna, su tutte le entità | NV (cop-1) · E (cop-6) — CONTRADDIZIONE | CC (cop-1) · PS (cop-6) — CONTRADDIZIONE |  |  | cop-1 A1 · cop-6 N-01 |
| A-20 | `recipe_round` paga `statistic_ids()` ogni 10 minuti anche senza niente da chiedere | NV | CC |  |  | cop-1 A2 |
| A-21 | `watch_automation_outcomes`: una lettura WS per automazione segnata, ogni 2 minuti, per sempre | NV | CC |  |  | cop-1 A3 |
| A-22 | `hiris_state_translations` rifà ogni 5 minuti significati e `seed` anche da cache | NV | CC |  |  | cop-2 A1 |
| A-23 | Il ponte interroga via HTTP ogni 3 secondi la coda dello stesso processo | NV | DP |  |  | cop-2 A2 |
| A-24 | `tools._state_readings` copia riga per riga di `ActionActuator._states` (specchio per id) | E | PS |  |  | cop-3 A-n1 |
| A-25 | «Lo specchio è leggibile?» composto a mano cinque volte in `tools.py` | E | PS |  |  | cop-3 A-n2 |
| A-26 | Leggere un istante ISO: `instant_epoch` «unica lettura» e altre tre (`_age_s`, `_in_home_zone`, `usage/store`) | D | PS |  |  | cop-3 A-n3 |
| A-27 | Il taglio dell'URL dello storico vive nello strumento, non in `HAClient.history` | NV | PS |  |  | cop-3 A-n4 |
| A-28 | Ogni lettura WebSocket apre sessione e autenticazione nuove; un comando in tre modi | E | PS |  |  | cop-5 A1 |
| A-29 | «Home Assistant non ha risposto» in tre modi; connessione caduta resa «forma inattesa» | D | CC |  |  | cop-5 A2 |
| A-30 | Le forme di ritorno di `HAClient`: sette, per la stessa domanda «è andata?» | D | CC |  |  | cop-5 A3 |
| A-31 | `load` e `reload` dello specchio: due riletture, una sola protegge gli eventi | D | PS |  |  | cop-5 A4 |
| A-32 | Le tracce lette un'automazione alla volta (`automation_traces`) quando la raffica `traces` esiste | E | PS |  |  | cop-5 A5 |
| A-33 | Le etichette lette con lo stesso comando da due metodi e due buste | E | CC |  |  | cop-5 A6 |
| A-34 | `calendars()` chiede a HA ciò che lo specchio ha già; eventi letti in fila | NV | CC |  |  | cop-5 A7 |
| A-35 | Lo specchio non risponde per id: tutti scandiscono `all_states()` | E | PS |  |  | cop-5 A8 |
| A-36 | Due modi di leggere lo storico dettagliato (REST `history`, WS `recorded_changes`) | NV | DP |  |  | cop-5 A9 |
| A-37 | `decide_scope` rilegge TUTTA la tabella `scope` per ogni decisione | E | PS |  |  | cop-6 N-02 |
| A-38 | «Chi ha già una ricetta?»: una SELECT e una scansione dell'anagrafe per dispositivo | E | PS |  |  | cop-6 N-03 |
| A-39 | `last_before` eseguita due volte quando si rifà una cronaca (`day_boundaries` pure) | E | PS |  |  | cop-6 N-04 |

---

## B. L'oggetto «casa» e le sue regole

| Id | Voce (max 14 parole) | Stato | Unirla | Sulla casa vera | Corretta da | Fonti |
|---|---|---|---|---|---|---|
| B-01 | «Questa entità è fuori?»: partizione, digesto e le loro copie | E | PS | 10 coppie di copie identiche su 1525 entità; hierarchy visibile 954 contro digesto 324 (per costruzione) | cop-3 (incompleta); cop-4 (righe) | reg · cop-3 · cop-4 |
| B-02 | Regole «fuori» più strette per scelta: `_view_integration`, `_unreliable_state`, conteggi, «senza nome» | D | DP | totali diversi in 17 integrazioni su 39 (974 contro 324); 35 senza nome, 10 fuori dal digesto | cop-4 (righe) | reg · cop-3 · cop-4 |
| B-03 | Le entità di un dispositivo senza filtro: `recipe_turn.device_lines` | D | CC | 1138 entità in più di `house_lines` su 1413; 548 disabilitate contate | cop-6 (nome) | reg · cop-6 |
| B-04 | `action/verification.py:613-625`: «ha uno stato» al posto di «è disabilitata» | D | DP | differisce dal digesto per 650 entità (974 contro 324) |  | reg |
| B-05 | Come si chiama un'entità: più politiche (3-4 vive, più quella delle automazioni) | D | CC | nome di `guarda` ≠ `search` per 944 entità su 1525; nome davvero diverso: 0 casi | cop-3 (incompleta); cop-4 (righe); cop-6 (incompleta); cop-9 (conteggio) | reg · cop-3 · cop-4 · cop-6 · cop-9 |
| B-06 | Nome del dispositivo: derivazioni e campo senza lettori | E | PS |  |  | reg · cop-4 |
| B-07 | «È un valore o un non-valore?»: `privacy._NEUTRAL_STATES` | E | PS | 0 stati cambiati su 169 entità mobili |  | reg · cop-5 · cop-6 |
| B-08 | `briefing._unreliable_state` conta solo `unknown` | D | CC | 328 entità `unavailable` su 974; esito invariato sulla casa (diverge solo la controprova sintetica) |  | reg · cop-4 |
| B-09 | `queries._view_integration` e `entity_cache.py:530`: letterali di stato | E | DP | 0 integrazioni su 39 |  | reg · cop-4 · cop-5 |
| B-10 | In che area sta un'entità | D | CC | 194 entità guardabili su 324 arrivano all'osservatore senza area |  | reg · cop-4 · cop-6 |
| B-11 | «Quali entità sono di un dispositivo»: `dispositivo_id` in linea | E | PS |  |  | reg · cop-3 · cop-4 · cop-6 |
| B-12 | «Ha statistiche?»: tre formule | E | CC | 0 casi su 232 entità watcher |  | reg · cop-3 · cop-5 · cop-6 |
| B-13 | Conti primo/ultimo/min/max/media/consumato: due case | D | CC | differiscono in 2/2040 (1 giorno), 28/272 (7 giorni), 9/68 (30 giorni) |  | reg · cop-3 |
| B-14 | Integrazione sana: due lettori, una costante doppia | E | PS |  | cop-4 (righe) | reg · cop-4 · cop-5 · cop-6 |
| B-15 | Fuso, confini del giorno, «oggi»: accessori e copie | E | PS |  | cop-1 (conteggio); cop-3 (incompleta); cop-7 (incompleta) | reg · cop-1 · cop-3 · cop-4 · cop-6 · cop-7 |
| B-16 | L'etichetta di data delle sessioni passate in UTC | D | CC | 3450 campioni sbagliati su 52560 nel 2026 |  | reg · cop-8 |
| B-17 | Unità e classe: il vivo batte il registro, applicato due volte | E | CC | 0 casi | cop-4 (incompleta); cop-6 (imprecisa) | reg · cop-3 · cop-4 · cop-6 |
| B-18 | Riferimento testuale: `search` contro `guarda`/resolver | D | CC | 118 casi su 39 integrazioni; 12 casi su 10 aree; «senza accenti» 0 casi | cop-3 (incompleta) | reg · cop-3 |
| B-19 | Due motori di ricerca per nome: `name_matches` e `Lookup.find` | D | PS | un solo candidato: 450 `search` (134 anche `find`), 21 solo `find`, 408 nessuno |  | reg · cop-3 |
| B-20 | Piegatura degli accenti in tre posti | D | CC |  |  | reg · cop-9 |
| B-21 | Slug: `composer.available_slug` e `recipient._slugify` | D | CC |  |  | reg · cop-9 |
| B-22 | Vocabolari dei tipi: giudizi e significati in più case | NV | DP |  | cop-5 (incompleta); cop-6 (righe) | reg · cop-5 · cop-6 |
| B-23 | Tabelle di nomi italiani di domini e struttura «automazione/script/scena» | E | PS |  | cop-4 (conteggio); cop-5 (imprecisa) | reg · cop-4 · cop-5 · cop-9 |
| B-24 | Identificatori e costanti piccole: `_ENTITY_ID_RE`, dominio da entity_id, tetti | E | PS |  | cop-3 (incompleta); cop-5 (incompleta); cop-6 (incompleta) | reg · cop-3 · cop-4 · cop-5 · cop-6 · cop-9 |
| B-25 | Stato della fonte: dove il dato c'è e si perde | NV | DP | 44 delle 95 entità «DENTRO» (46%) non sono fonte sana | cop-5 (imprecisa) | reg · cop-4 · cop-5 · cop-6 |
| B-26 | Motivo scritto per le misure non calcolabili: cinque stringhe, cause vere che non coincidono | D | CC | 74 misure non calcolabili; il motivo «manca `state_class`» falso in 21/21 |  | reg |
| B-27 | Dentro `mind/operations` e `mind/analyst`: controlli ripetuti e due forme di «non lo so» | E | PS |  |  | reg |
| B-28 | Ordinamento degli appuntamenti e due semantiche di `fine` | E | PS |  |  | reg · cop-5 |
| B-29 | Quote FV: «autoconsumo» esclude la batteria | D | CC | 29/09: quota_autoconsumo 31% contro 74,7% di FV non immesso |  | reg |
| B-30 | La regola della profondità scritta due volte (`search`, `history`), e una terza fissa | D | CC |  |  | cop-3 B-n1 |
| B-31 | `tipo=automation/script` → genere: conversione in due posti | E | PS |  |  | cop-3 B-n2 |
| B-32 | «Quale filtro vale per quale genere»: due tabelle, due frasi | NV | PS |  |  | cop-3 B-n3 |
| B-33 | Una durata, tre grammatiche; `calendar` taglia in silenzio, gli altri rifiutano | D | CC |  |  | cop-3 B-n4 |
| B-34 | «Tipi di ancora non verificabili adesso»: scritto due volte (`_remember`, `_unverifiable_types`) | NV | PS |  |  | cop-3 B-n5 |
| B-35 | `house_history` importa da `mind` (`integration_of`), contro «`home_space` non importa da `mind`» | D (cop-3) · E (cop-6) — CONTRADDIZIONE | PS |  |  | cop-3 B-n6 · cop-6 N-07 |
| B-36 | `actual_class` e `actual_unit` sono la stessa funzione; «stringa non vuota ripulita» sei volte | E | PS |  |  | cop-4 N-01 |
| B-37 | «È una pseudo-area?» scritto a mano tre volte; `is_pseudo_area` senza chiamanti esterni | NV | PS |  |  | cop-4 N-02 |
| B-38 | La mappa etichette `{label_id: nome}` riscritta a mano in `handlers_home_space` | E | PS |  |  | cop-4 N-03 · cop-8 C1 |
| B-39 | Conteggio per tipo del comportamento in tre punti, `senza_corpo` in quattro | NV | PS |  |  | cop-4 N-04 · cop-8 C2 |
| B-40 | Il formato «(id: X)» scritto a mano in `_device_annotation` | E | PS |  |  | cop-4 N-05 |
| B-41 | Lo specchio vivo in due forme: tupla di sei dizionari e sei argomenti separati | E | PS |  |  | cop-4 N-06 |
| B-42 | Credenziale o attributo dichiarato: lo decide l'ordine dei rami (9 nomi in due tabelle) | E | DP |  |  | cop-5 B1 |
| B-43 | Le provenienze: tre in `type_vocabulary`, cinque in `mind/knowledge`, stesso nome `PROVENANCES` | D | PS |  |  | cop-5 B2 |
| B-44 | La versione di HA pinnata in tre costanti; una sola confrontata con la casa | E | PS |  |  | cop-5 B3 |
| B-45 | Il trattino di «senza classe» (`NO_DEVICE_CLASS`) e la chiave di traduzione scritti più volte | E | PS |  |  | cop-5 B4 |
| B-46 | I nomi dei campi dei giudizi in due vocabolari; la mappa ne salta uno | E | PS |  |  | cop-5 B5 |
| B-47 | Provenienza non dichiarata, o dichiarata per il pezzo sbagliato (`ha_vocabulary`, `_FEATURE_TABLES`) | NV | DP |  |  | cop-5 B6 |
| B-48 | I quattordici tipi di `related` scritti due volte (`RELATED_ITEM_TYPES`, `LINK_NAME`) | E | PS |  |  | cop-5 B7 |
| B-49 | Il soggetto di un tipo (`dominio.classe`) composto in tre posti; docstring «un posto solo» | E | PS |  |  | cop-6 N-05 |
| B-50 | Il nome di un'integrazione inventato dallo slug, mentre l'anagrafe ha il titolo vero | D | DP |  |  | cop-6 N-06 |
| B-51 | I tipi di ancora scritti due volte; `name_matches` vive in `memory/` col codice morto | E | PS |  |  | cop-9 N-B-2 |
| B-52 | `ChatThread` ricostruito in tre archivi; la condizione SQL del filo in undici posti | E | PS |  |  | cop-9 N-B-3 |
| B-53 | Costante «64» duplicata con legame solo a commento (`MAX_TRACKED`, `_MAX_TRACKED_EXCHANGES`) | E | PS |  |  | cop-9 N-B-4 |
| B-54 | «300» per i motivi che entrano in un racconto: tre nomi in tre moduli | E | PS |  |  | cop-9 N-B-5 |

---

## C. La resa in uscita e i nomi dei campi

| Id | Voce (max 14 parole) | Stato | Unirla | Sulla casa vera | Corretta da | Fonti |
|---|---|---|---|---|---|---|
| C-01 | Dodici renditori di «un'entità col suo stato», tre copie del dizionario base | D | CC |  |  | reg · cop-3 · cop-4 |
| C-02 | Dispositivo, area, integrazione, misura, stato tradotto: più renditori della stessa cosa | D | CC |  |  | reg · cop-3 |
| C-03 | Lo stesso fatto detto con nomi diversi | D | CC |  |  | reg |
| C-04 | Lo stesso nome per fatti diversi | D | CC |  | cop-3 (incompleta); cop-4 (incompleta) | reg · cop-3 · cop-4 |
| C-05 | Un fatto che esce da una porta e non da un'altra | D | CC |  | cop-3 (imprecisa) | reg · cop-3 |
| C-06 | Chiave dell'errore: `error` contro `errore` | D | CC |  | cop-5 (incompleta); cop-8 (incompleta, imprecisa) | reg · cop-5 · cop-8 |
| C-07 | Altre forme dell'errore HTTP e righe ripetute negli handler | E | PS |  | cop-8 (incompleta) | reg · cop-8 · cop-9 N-C-2 |
| C-08 | I mappatori della stessa riga di `/api/usage` | D | CC |  |  | reg |
| C-09 | Il frontend che rifà regole del server: la copia parola per parola | E | PS |  |  | reg · cop-6 |
| C-10 | Grammatica dei soggetti e vocabolari chiusi scritti in Python e in JS | E | PS |  | cop-6 (incompleta, due etichette sbagliate) | reg · cop-6 |
| C-11 | Prosa del JS che ricopia costanti dello scheduler e dell'archivio | NV | PS |  |  | reg · cop-2 · cop-6 |
| C-12 | Regole di dominio che vivono solo nel JS | NV | DP |  |  | reg · cop-6 |
| C-13 | Il JS ricostruisce un dato che il server ha, o gliene manca uno | D | CC |  | cop-6 (incompleta); cop-9 (incompleta) | reg · cop-6 · cop-9 |
| C-14 | Agenda e Proposte: finestra da 200 contro conteggio completo | D | CC |  |  | reg |
| C-15 | Chat: contatore dei turni, limite, due forme di risposta | D | CC |  | cop-8 (righe, incompleta) | reg · cop-8 |
| C-16 | Tema: quattro posti, e il tema del server vale solo per la chat | D | CC |  |  | reg |
| C-17 | Fuso e formati delle date: il browser contro la casa | D | DP |  |  | reg · cop-2 |
| C-18 | Nome di pagina: «Costruzioni» nella prosa del server, «Proposte» nel menu | D | PS |  |  | reg · cop-3 · cop-9 |
| C-19 | Intestazione anti-CSRF: una copia diversa | D | PS |  |  | reg |
| C-20 | Utilità JS ricopiate per file | E | PS |  |  | reg |
| C-21 | Stato doppio client/server | D | DP |  |  | reg |
| C-22 | Le due applicazioni (chat e configurazione): cosa condividono e cosa duplicano | E | PS |  |  | reg |
| C-23 | Campi che arrivano e nessun JS legge | E | PS |  |  | reg |
| C-24 | CSS: due sistemi di variabili, stili in-linea ripetuti, override caricato prima | NV | PS |  |  | reg |
| C-25 | Nomi che collidono e notizie con due nomi nella pagina dell'osservatore | D | DP |  |  | reg |
| C-26 | Apostrofi `'` e `’` mischiati nello stesso messaggio | E | PS |  | cop-9 (incompleta) | reg · cop-9 N-C-7 |
| C-27 | Cronaca e primo piano: lo stesso fatto in più voci | E | DP |  |  | reg |
| C-28 | La specie «attuatore» in letterali sparsi invece del vocabolario di `steering.SPECIE` | E | PS |  |  | cop-1 C1 |
| C-29 | `_serve_index` e `_serve_config` sono la stessa funzione (cambia solo la chiave) | E | PS |  |  | cop-2 C1 |
| C-30 | `/api/health`: due forme scelte dal ruolo, tre stati di tipo diverso in un oggetto | NV | DP |  |  | cop-2 C2 |
| C-31 | L'involucro della risposta (`trovate/escluse/…/finestra`) montato in tre posti | E | PS |  |  | cop-3 C-n1 |
| C-32 | Un istante esce in quattro forme dagli strumenti (UTC, fuso casa, epoch, «mai») | D | CC |  |  | cop-3 C-n2 |
| C-33 | Righe della stessa risposta con chiavi diverse; `genere` manca all'entità nella corta | D | CC |  |  | cop-3 C-n3 |
| C-34 | Nella media `attributi` sono le ceste grezze, senza il filtro della completa | D | CC |  |  | cop-3 C-n4 |
| C-35 | Frasi fisse ripetute per riga o per risposta, già scritte nella descrizione | E | DP |  |  | cop-3 C-n5 |
| C-36 | I `punti` a fasce portano `somma` non spiegata e tre `null` per i contatori | NV | CC |  |  | cop-3 C-n6 |
| C-37 | La traccia passo per passo (`run_detail`) esce senza nessun tetto | NV | CC |  |  | cop-3 C-n7 |
| C-38 | `calendar`: unico lettore senza tetto di righe e con un involucro suo | D | CC |  |  | cop-3 C-n8 |
| C-39 | Lo strumento `agenda` taglia a 50 in silenzio e porta 18 chiavi per promessa | D | CC |  |  | cop-3 C-n9 |
| C-40 | `unita` è tre fatti con una parola (stringa dell'entità, dizionario del frame, limite) | D | CC |  |  | cop-4 N-07 |
| C-41 | Il ricordo ha due forme: `view(ricordo)` senza `corretto_da_utente`, le righe ancorate con | D | CC |  |  | cop-4 N-08 |
| C-42 | `attiva` dell'automazione esce solo dal nucleo: dettaglio e riga di `search` no | D | CC |  |  | cop-4 N-09 |
| C-43 | Le pseudo-aree hanno forma diversa dalle aree vere; dizionario letterale scritto quattro volte | D | PS |  |  | cop-4 N-10 |
| C-44 | Due buste nello stesso modulo `state_translations`: `letto` e `lette` | D | CC |  |  | cop-5 C1 |
| C-45 | Tre forme dell'assenza nella stessa voce dello specchio (`""`, `None`, chiave mancante) | D | CC |  |  | cop-5 C2 |
| C-46 | La stessa colonna (`scope.decided_ts`) esce con due nomi nella stessa risposta (`da_quando_ts`, `deciso_ts`) | E | PS |  |  | cop-6 N-08 |
| C-47 | `as_document`: istanti come epoch grezzo sotto un'intestazione inglese | NV | DP |  |  | cop-6 N-09 |
| C-48 | I corpi JSON dell'archivio dell'osservatore: tre letture con la guardia, quattro senza | D | CC |  |  | cop-6 N-10 |
| C-49 | Resoconti, analisi, scope e obiettivo non sono chiedibili dalla chat | NV | DP |  |  | cop-6 N-11 |
| C-50 | La chat risponde l'errore in quattro forme, due lingue, due volte con stato 200 | D | CC |  |  | cop-8 C3 |
| C-51 | Cancellare un ricordo che non esiste è un successo (204); correggerlo è un 404 | D | CC |  |  | cop-8 C4 |
| C-52 | `handle_services` risponde 503 con `"servizi": []`, contro la regola scritta altrove | D | PS |  |  | cop-8 C5 |
| C-53 | `propose` restituisce il motivo del consigliere due volte (anteprima e `consiglio`) | E | CC |  |  | cop-9 N-C-1 |
| C-54 | Lo stato grezzo arriva al modello: `READABLE_STATE` solo per le costruzioni, `cancel` scrive `in_corso` | D | PS |  |  | cop-9 N-C-3 |
| C-55 | Troncamenti a mano (`…`) accanto a `truncate_with_marker` (` [troncato]`): due marcatori | D | CC |  |  | cop-9 N-C-4 |
| C-56 | Nota «il Piano non ha risposto» due volte; nome del provider in nove stringhe | D | CC |  |  | cop-9 N-C-5 |

---

## D. Un turno verso un modello

| Id | Voce (max 14 parole) | Stato | Unirla | Sulla casa vera | Corretta da | Fonti |
|---|---|---|---|---|---|---|
| D-01 | Comporre il system prompt: più compositori | D | PS |  |  | reg · cop-7 |
| D-02 | `BASE_TOOL_RULES` ai turni che non hanno strumenti | D | CC | system dell'analista 1162 caratteri sul ponte, 7205 sulla catena; attuatore `tools_sent: 0`, `guide_chars: 7970` | cop-7 (righe, incompleta) | reg · cop-7 |
| D-03 | Regole d'uso degli strumenti: `BASE_TOOL_RULES` contro `_GUIDE_WITH_TOOLS` | D | CC |  | cop-7 (conteggio, incompleta) | reg · cop-7 |
| D-04 | Recinto del contesto: sul ponte sì, sulla catena no | D | CC |  |  | reg · cop-7 |
| D-05 | Il contratto di risposta due volte sul ponte (analista, ricette) | D | CC |  | cop-6 (imprecisa) | reg · cop-6 · cop-7 |
| D-06 | Chi risponde: una decisione, sette chiamanti, quattro «dopo» | D | CC |  |  | reg · cop-7 · cop-8 |
| D-07 | Accodare sul ponte: sei `enqueue`, il modello scelto vale solo per la chat | D | CC |  | cop-1 (incompleta); cop-7 (righe, conteggio); cop-8 (conteggio) | reg · cop-1 · cop-7 · cop-8 |
| D-08 | Raccogliere la risposta del ponte: quattro `_collect_*` e quattro «già letto» | D | CC |  | cop-1 (incompleta) | reg · cop-1 · cop-7 · cop-8 |
| D-09 | Predefiniti del ponte e di Ollama riletti in molti punti | E | PS |  | cop-1 (incompleta); cop-7 (conteggio); cop-8 (incompleta) | reg · cop-1 · cop-2 · cop-7 · cop-8 · cop-9 |
| D-10 | Il ciclo degli strumenti: quattro cicli, tre unità di tetto | D | CC |  | cop-7 (righe) | reg · cop-7 |
| D-11 | Leggere un JSON dalla risposta: cinque lettori, tre strategie, una regex duplicata | D | CC |  | cop-6 (righe) | reg · cop-6 · cop-7 |
| D-12 | Validare, rifiutare, registrare l'esito, frenare: quattro `apply_*`, quattro registri, tre freni | D | CC | analista 01/10: 8 turni orari, 7 troncati a 4096 token |  | reg |
| D-13 | Tetti e limiti: `max_tokens` in cinque posti, nessuna temperatura | D | CC |  | cop-7 (incompleta) | reg · cop-6 · cop-7 · cop-9 |
| D-14 | Misurare un turno: due scrittori di turni, tre di consumo, vocabolario dei nomi | D | PS |  | cop-7 (righe, incompleta); cop-8 (conteggio) | reg · cop-7 · cop-8 |
| D-15 | Cosa finisce nella storia dopo un errore, e cosa conta come «tossico» | D | CC |  | cop-8 (incompleta) | reg · cop-7 · cop-8 |
| D-16 | Il fallback della catena rifà l'intero turno con lo stesso dispatcher | NV | DP |  |  | reg |
| D-17 | Tre chiamate a `runner.chat` per la chat (12 kwarg), impostazioni fotografate, `thinking_budget` | E | CC |  | cop-8 (conteggio) | reg · cop-7 · cop-8 |
| D-18 | Storia, nota «hai gli strumenti», avviso sui nomi vecchi: catena contro ponte | D | DP |  |  | reg · cop-7 |
| D-19 | Cosa arriva davvero al modello della casa, turno per turno | D | CC |  | cop-6 (conteggio non riscontrato) | reg · cop-6 |
| D-20 | `fetch` contro `search`: i ricordi ancorati (`search(genere=ricordo)` apre soltanto) | D | CC | `search(genere=ricordo)` 4 volte in 131 chiamate; `fetch` 11 chiamate in 7 giorni | cop-3 (SBAGLIATA in parte); cop-4 (doppio conteggio) | reg · cop-3 · cop-4 |
| D-21 | Il filtro per ancora: `per_tether` e `_tethered_memories` | E | PS |  | cop-3 (incompleta) | reg · cop-3 |
| D-22 | Altre sovrapposizioni fra strumenti (11 proprietà condivise fra `search` e `history`) | E | DP |  | cop-3 (conteggio, righe) | reg · cop-3 |
| D-23 | Il soffitto (chi può cosa) chiesto a mano in sette punti dentro i gestori | D | DP |  | cop-3 (conteggio, righe) | reg · cop-3 |
| D-24 | Promesse: tre archivi dell'esito, quattro frasi, tre macchine a stati, tre vie di chiusura | D | CC |  | cop-9 (righe, incompleta) | reg · cop-9 |
| D-25 | Validazione dello stesso ingresso in più punti | E | DP |  |  | reg · cop-3 |
| D-26 | Costruire: due archivi dello stesso esito, tre porte, due «_preview» | E | PS |  | cop-3 (imprecisa) | reg · cop-3 · cop-9 |
| D-27 | Archivi per `data_dir` e migrazioni «chat divise» | E | PS |  | cop-3 (rimando rotto) | reg · cop-3 |
| D-28 | Tre costruzioni dell'indice per «questo id esiste?» | E | PS |  |  | reg · cop-3 |
| D-29 | Riservatezza: sette maschere, uscite che non passano da nessuna | D | CC |  | cop-3 (incompleta); cop-5 (righe); cop-9 (righe, incompleta) | reg · cop-3 · cop-5 · cop-9 |
| D-30 | Strumenti di lettura nei turni degli attori: cosa manca al turno | NV | DP |  | cop-8 (righe) | reg · cop-8 |
| D-31 | Riparazione delle ricette: lo stesso turno `recipe_turn.ask` composto in due modi | D | CC | 01/10: due riparazioni (ricetta già sana; ricetta inesistente), rifatte identiche alle 09:20 e 10:20 |  | reg |
| D-32 | I giri del cervello dentro `server.py` | E | PS |  |  | reg · cop-1 B1 · cop-2 |
| D-33 | Lo stesso tema ogni giorno, con parole diverse (analisi, esiti, proposte) | D | CC | coppie già presenti il giorno prima: 2 su 7, 3 su 8, 4 su 8 | cop-6 (righe) | reg · cop-6 |
| D-34 | La serie dell'analista composta due volte, riga per riga (`server.py:1964`, `:2431`) | E | PS |  |  | cop-1 D1 |
| D-35 | `llm_router or claude_runner` scritto 10 volte; il ramo destro non può mai scattare | E | PS |  |  | cop-1 D2 · cop-2 M1 |
| D-36 | Il resoconto di un giorno scritto con le stesse due chiamate in tre punti | E | PS |  |  | cop-1 D3 |
| D-37 | `_write_analysis` e `_write_actuation`: stesso scheletro | E | PS |  |  | cop-1 D4 |
| D-38 | Indice del modello → riga dell'elenco, due volte (`server.py:2195`, `:2256`) | E | PS |  |  | cop-1 D5 |
| D-39 | Tre tabelle a mano per nome di strumento; la terza fuori dal `try` | E | PS |  |  | cop-3 D-n1 |
| D-40 | Il cancello degli argomenti non legge `enum` né `type`: vocabolari rivalidati a mano | D | PS |  |  | cop-3 D-n2 |
| D-41 | La risorsa che serve a uno strumento decisa in due posti | E | PS |  |  | cop-3 D-n3 |
| D-42 | Il rifiuto «nessun filo» ripetuto in tre gestori | E | PS |  |  | cop-3 D-n4 |
| D-43 | «Cosa HA riserva agli amministratori» in due moduli, tre case | E | PS |  |  | cop-3 D-n5 |
| D-44 | Il sigillo del registro errori vive in `tools.py`: `mind/watcher` lo salta | D | CC |  |  | cop-3 D-n6 |
| D-45 | `search` non sa elencare integrazioni né ricordi; per solo nome non li cerca | D | CC |  |  | cop-3 D-n7 |
| D-46 | Il confine di sanificazione protegge i nomi, non gli altri testi di HA | NV | CC |  |  | cop-4 N-11 |
| D-47 | La sezione dei guasti del nucleo non ha tetto (dichiara 6.800 caratteri) | D | CC |  |  | cop-4 N-12 |
| D-48 | «Corpo non disponibile» detto tre volte nel nucleo, una quarta nella pagina | NV | CC |  |  | cop-4 N-13 |
| D-49 | Il nucleo dichiara cause di problema («id duplicati, voci malformate») che nessun codice produce | D | CC |  |  | cop-4 N-14 |
| D-50 | A ogni turno il nucleo rilegge TUTTI i ricordi: 1 + 2N interrogazioni SQLite | NV (cop-4) · E (cop-9) — CONTRADDIZIONE | PS |  |  | cop-4 N-16 · cop-9 N-D-2 |
| D-51 | Cache del prompt: l'ora nel nucleo, punti di taglio che non coprono il ciclo | NV | DP (cop-4) · CC (cop-7) — CONTRADDIZIONE |  |  | cop-4 N-17 · cop-7 N-D6 |
| D-52 | Gli attributi «già calcolati» ricalcolati tre volte per il dettaglio di un'entità | E | PS |  |  | cop-4 N-18 |
| D-53 | Le righe annidate si arricchiscono TUTTE e poi si tagliano a 50 | E | PS |  |  | cop-4 N-19 |
| D-54 | L'id del soggetto ricavato spezzando la riga scritta per il modello (`house_lines` due volte) | E | PS |  |  | cop-6 N-12 |
| D-55 | All'analista vanno due campi per riga che non può più usare (`soggetto`, `operazione`) | NV | CC |  |  | cop-6 N-13 |
| D-56 | Promessa sul ponte: la guida nomina 7 strumenti assenti e non `conclude`; regole triplicate | D | CC |  |  | cop-7 N-D4 |
| D-57 | La guida del ponte: secondo catalogo a mano, `mcp__hiris__` ricopiato venti volte (in potenza) | D | PS |  |  | cop-7 N-D5 |
| D-58 | `esito = riuscito` per una risposta troncata o con uno strumento «scappato» | D | CC |  |  | cop-7 N-D10 |
| D-59 | Il vocabolario degli stati di `reasoning_jobs`: letterali in tre file, in due lingue | E | PS |  |  | cop-7 N-D11 |
| D-60 | Costo e nome del provider scritti due volte, con due formule (0 contro NULL) | D | CC |  |  | cop-7 N-D13 |
| D-61 | Due pesatori del carico, una forma, tre definizioni di «guida» | D | CC |  |  | cop-7 N-D14 |
| D-62 | `reasoning/queue.py`: `get()`/`latest()` due forme, mezzanotte ricalcolata, `SELECT *` col nucleo | D | PS |  |  | cop-7 N-D15 |
| D-63 | Sul ponte ogni `tools/call` rifà ciò che la catena fa una volta per turno | D | DP |  |  | cop-8 D1 |
| D-64 | Il nucleo che non si compone: tre chiamanti, tre comportamenti | D | CC |  |  | cop-8 D2 · cop-9 N-D-1 |
| D-65 | «Qual è la conversazione attiva di questo filo» chiesta tre volte per turno | NV | CC |  |  | cop-8 D3 |
| D-66 | Leggere un corpo JSON: cinque stili; chat, `submit` e servizi rispondono 500 | D | PS |  |  | cop-8 D4 |

---

## E. Scrivere su Home Assistant

| Id | Voce (max 14 parole) | Stato | Unirla | Sulla casa vera | Corretta da | Fonti |
|---|---|---|---|---|---|---|
| E-01 | Scritture verso HA che non passano da nessuna delle due porte | D | DP |  |  | reg · cop-2 · cop-5 |
| E-02 | La cronaca delle azioni: una tabella, due scrittori | E | PS |  |  | reg · cop-9 |
| E-03 | «HA ha rifiutato la chiamata» e l'occorrenza di successo, due volte in `actuator` | E | PS |  |  | reg |
| E-04 | Le forme del rifiuto e del successo fra le due porte | D | CC |  | cop-9 (righe) | reg · cop-9 |
| E-05 | Cosa controlla una porta e l'altra no | D | DP |  |  | reg · cop-9 |
| E-06 | Più client verso HA e verso il Supervisor | E | DP |  |  | reg |
| E-07 | Il contratto dell'«intenzione» dell'attuatore contro l'officina | D | CC | 13 esiti `proposta`: 9 in coda, 3 scartati, 1 persa; le 2 `costruibile` non in coda |  | reg · cop-9 |
| E-08 | La cartella di configurazione di HA cercata in due case | E | PS |  |  | reg · cop-1 |
| E-09 | «Verificare senza eseguire» non è un metodo della porta: `promise` lo ricompone | D | CC |  |  | cop-3 E-n1 |
| E-10 | `call_service` butta il motivo di HA, senza guardia; le primitive di configurazione no | D | CC |  |  | cop-5 E1 |
| E-11 | «La scrittura è arrivata?»: due regole opposte; la riga incerta esce dalla potatura | D | DP |  |  | cop-9 N-E-2 |
| E-12 | Il dominio dell'helper non si valida alla proposta: l'errore arriva dopo il «sì» | D | CC |  |  | cop-9 N-E-3 |
| E-13 | «Verificare senza eseguire» non ha una porta pubblica: `verification()` è atomica, `ActionActuator.verify(call)` non esiste; chi ne ha bisogno ricompone il pre-volo (si lega a E-09) | D | CC |  |  | compl §2.1 |

---

## F. Chi sei, cosa puoi, quali modelli

| Id | Voce (max 14 parole) | Stato | Unirla | Sulla casa vera | Corretta da | Fonti |
|---|---|---|---|---|---|---|
| F-01 | «Chi sei e cosa puoi»: scritto in più di sette punti | E | PS |  | cop-8 (conteggio) | reg · cop-8 |
| F-02 | Il vocabolario dei ruoli definito due volte | E | PS |  | cop-8 (incompleta) | reg · cop-5 · cop-8 |
| F-03 | `costruire` e `amministrare` sono un bit; `_solo_amministratori` copia `require_builder` | D | CC |  |  | reg · cop-8 |
| F-04 | Gli elenchi di provider: ~21 posti | D | CC |  |  | reg |
| F-05 | L'ordine dei provider: cinque ordini | D | CC |  |  | reg · cop-2 |
| F-06 | Il nome di un provider: due tabelle | D | CC |  |  | reg |
| F-07 | `ponte` contro `subscription`: due chiavi per un provider | D | CC |  | cop-9 (righe) | reg · cop-9 |
| F-08 | La credenziale di un provider: cinque definizioni | D | CC |  | cop-2 (conteggio) | reg · cop-2 |
| F-09 | Id di modello, prezzo, modello automatico e prefissi: tenuti allineati a mano | E | PS |  | cop-7 (incompleta) | reg · cop-7 |
| F-10 | Opzioni e variabili d'ambiente | E | PS |  | cop-8 (imprecisa) | reg · cop-2 · cop-8 |
| F-11 | Scrittura atomica di un JSON in `/data`: tre implementazioni | D | CC |  |  | reg |
| F-12 | Il modello della «migrazione come era»: tre pezzi | E | PS |  |  | reg |
| F-13 | `handlers_models.py` ospita cose che non sono sue | E | PS |  |  | reg |
| F-14 | «Chi può rispondere» calcolato due volte all'avvio: quinta definizione della credenziale (`_recompute_chain`) | NV | CC |  |  | cop-2 F1 |
| F-15 | `agent_type` non sceglie nulla su Claude; su OpenAI analista/attuatore/«Rifalla» vanno su `gpt-4o` | D | DP |  |  | cop-7 N-F1 |
| F-16 | I default numerici dei runner senza unità nel nome e senza un posto comune | E | PS |  |  | cop-7 N-F2 |
| F-17 | `amministrare` vale negli strumenti, non nelle rotte: i corpi delle automazioni ai servizi firmati | D | DP |  |  | cop-8 F3 |
| F-18 | «Solo il ponte»: lo stesso cancello due volte, con insiemi, chiavi e testi diversi | E | PS |  |  | cop-8 F4 |
| F-19 | La forma del soggetto: quattro costruttori nel middleware, tre fuori, due forme | E | PS |  |  | cop-8 F5 |
| F-20 | Costanti piccole del permesso scritte due volte (metodi sicuri, specie ignota, «nessun gesto») | E | PS |  |  | cop-8 F6 |
| F-21 | `FINESTRA_S`: un nome, due fatti (600 s accoppiamento, 30 s firma) | D | PS |  |  | cop-8 F7 |

---

## G. Gli archivi che seguono la casa

| Id | Voce (max 14 parole) | Stato | Unirla | Sulla casa vera | Corretta da | Fonti |
|---|---|---|---|---|---|---|
| G-01 | Lo scope tiene decisioni su entità che non ci sono più | D | CC | 413 soggetti decisi, 86 senza stato in HA (21%); 26 dei 95 «dentro» |  | reg · cop-6 |
| G-02 | Ricette e rifiuti di dispositivi disabilitati o spariti restano e girano | D | CC | 13 dispositivi disabilitati su 32 soggetti di misura; `ricetta_non_serve` 60 righe |  | reg · cop-6 |
| G-03 | Resoconti scritti da fonti ferme, per sempre | D | DP | 36 resoconti; 814 misure su 1809 «non calcolabili» (45%) |  | reg |
| G-04 | Proposte «a mano» dell'attuatore in attesa su dati rotti, e antiripetizione | D | DP | 9 righe `proposte` (7 `attesa`, 2 `rifiutata`): 0 utili, 4 sbagliate, 5 vaghe |  | reg · cop-6 |
| G-05 | Righe del sapere senza lettore, e valori ammessi che nessuno produce | E | PS | 396 righe nel sapere: 14 `direzione:*`, 23 `notevole`; 275 non leggibili dall'API |  | reg · cop-5 · cop-6 |
| G-06 | Colonne scritte e mai lette in `osservazioni.db` | E | PS |  | cop-6 (incompleta) | reg · cop-6 |
| G-07 | Colonne scritte con cura e mai consumate negli altri DB | E | CC |  | cop-9 (file, incompleta) | reg · cop-3 · cop-9 |
| G-08 | `promesse.recapito`: colonna morta | E | PS |  |  | reg · cop-9 |
| G-09 | `turn` e `payload`: 30 colonne lette solo dalla diagnosi | E | DP |  |  | reg · cop-9 |
| G-10 | Potature: otto implementazioni, otto finestre | D | CC |  | cop-6 (incompleta); cop-9 (incompleta) | reg · cop-2 G1 · cop-6 · cop-7 · cop-8 · cop-9 |
| G-11 | `reasoning.db`: la potatura sta dietro il gate `bridge_active` | NV | CC | ponte spento: le righe `decided/expired/failed` vecchie restano | cop-7 (imprecisa) | reg · cop-2 · cop-7 |
| G-12 | File residui in `/data` | NV | DP |  | cop-2 (incompleta) | reg · cop-2 · cop-3 |
| G-13 | Migrazione di schema SQLite: 19 occorrenze dello stesso idioma, migrazioni con scadenza scritta | E | PS |  |  | reg · cop-9 |
| G-14 | Lingua dei nomi di colonna e convenzioni del tempo | NV | DP |  |  | reg · cop-9 N-G-5 |
| G-15 | `scope.author`: i valori `analyst` e `owner` senza produttore | E | DP | 318/318 `fuori` con autore `observer` |  | reg |
| G-16 | Lettura sospetta: le guardie conservano la replica del comportamento senza dichiararla al nucleo | D | CC |  |  | cop-4 N-20 |
| G-17 | «L'obiettivo di adesso» e «a un istante»: la stessa query scritta tre volte | NV | PS |  |  | cop-6 N-14 |
| G-18 | I 22 giorni del grezzo scritti due volte; `prune` taglia con la seconda | E | PS |  |  | cop-6 N-28 |
| G-19 | Tre macchine a stati con parole diverse; `rifiutata` con due significati | D | DP |  |  | cop-9 N-G-1 |
| G-20 | `promesse.risvegliata_ts` è anche l'istante di disdetta, conclusione e «saltata»: il nome mente | E | DP |  |  | cop-9 N-G-2 |
| G-21 | Ancore dei ricordi: la pagina dice se esistono e il nome, il modello no | D | CC |  |  | cop-9 N-G-3 |
| G-22 | «Riparti da adesso»: i ripieghi (`fallback`) non si azzerano come i consumi | D | CC |  |  | cop-9 N-G-4 |
| G-23 | «Lo stato più debole» due volte: `piu_debole` e `MIN(costo_stato)` in SQL, coincidono per caso | E | PS |  |  | cop-9 N-G-7 |

---

## T. La suite di test

| Id | Voce (max 14 parole) | Stato | Unirla | Sulla casa vera | Corretta da | Fonti |
|---|---|---|---|---|---|---|
| T-01 | Finte di `HAClient` ripetute (68 classi in 41 file) | E | PS |  |  | reg · cop-5 |
| T-02 | Altre finte duplicate (specchio, store, scheduler, runner, mock) | E | PS |  |  | reg |
| T-03 | Finte fetch del JS: 78 assegnazioni, `stubFetch` che risponde 200 a tutto | E | PS |  |  | reg |
| T-04 | Finte che rispondono in forma diversa dal vero | D | CC |  |  | reg · cop-5 |
| T-05 | Test orfani: provano codice senza chiamanti di produzione | E | PS |  |  | reg |
| T-06 | Test che non possono fallire o non discriminano | NV | DP |  |  | reg · cop-3 |
| T-07 | Prove fragili sul testo del sorgente di `server.py` | D | PS |  |  | reg · cop-1 |
| T-08 | Cancelli utili: da non toccare | E | PS |  |  | reg |
| T-09 | Moduli di produzione senza test che li importino | NV | DP |  |  | reg |
| T-10 | La suite ha congelato la duplicazione del JS | E | PS |  |  | reg |
| T-11 | Ridondanza fra test e prove che pinnano nomi vecchi | NV | DP |  |  | reg |
| T-12 | Cosa i test non hanno mai confrontato | NV | DP |  |  | reg |
| T-13 | Un test (`test_queries.py:390-405`) descrive una mutazione su codice inesistente e passa per altra ragione | D | PS |  |  | cop-4 N-31 |
| T-14 | Due prove che fissano il contrario di ciò che serve (`test_shared_chat_context.py:233-241`, `test_internal_auth_middleware.py:54`) | NV | PS |  |  | cop-8 T1 |
| T-15 | Prove che pinnano codice senza chiamante di produzione o un comportamento da decidere | E | — |  |  | cop-9 N-T-1 |
| T-16 | Nessuna prova di freschezza all'applicazione o al ripristino di una costruzione | NV | — |  |  | cop-9 N-T-2 |

---

## M. Codice morto e residui

| Id | Reperto | Righe | Corretta da | Fonti |
|---|---|---|---|---|
| M-02 | `_resolve_current_model` (due runner) senza chiamanti di produzione: lo usano 15 asserzioni di `tests/test_provider_default_model.py` come cucitura di prova. Esce alla Tappa 1, quando quelle prove passano da `chat()`. La parte `simple_chat` x4 e' USCITA con la Tappa 0, Task 10 (38684dae) | `claude_runner.py`; `openai_compat_runner.py` | cop-7 (incompleta) | reg · cop-7 |
| M-07 | `llm_router._STRATEGY_ORDER`/`_norm_policy`/`chat_policy`/`strategy`: solo ramo «libreria» e `_chain_as_it_was` | `llm_router.py:52-62`; `server.py:3240,5258-5266` |  | reg · cop-2 |
| M-11 | L'attuatore in pausa dal 3.72.2: 318 righe in `server.py`, `mind/actuator.py` 82, `actuator_turn.py` 221 | `server.py:2001-2336,4508` | cop-1 (incompleta) | reg · cop-1 · cop-2 |
| M-12 | `mind/scope.ANALYST` e `OWNER` mai passati come `author` in produzione | `mind/scope.py:44`; `observer.py:282,299` |  | reg |
| M-13 | `mind/operations.UNKNOWN_UNIT`: zero lettori, zero test | `mind/operations.py:87` |  | reg |
| M-14 | `Operation.refuses_when` (14 voci) non letto; quattro `SHAPE_*` letti solo nel file e nei test | `mind/operations.py`; `recipes.py:281` |  | reg |
| M-15 | `api/ingresso.prepara_ingresso(app)`: corpo = docstring; `import ipaddress as _ip` ridondante | `api/ingresso.py:145,161-168`; `server.py:5686` |  | reg · cop-2 |
| M-16 | `auth_via == "token"` mai assegnato dal 22/09/2026, ancora accettato e documentato | `handlers_mcp.py:656-687`; `server.py:5648`; `handlers_reasoning.py:39` | cop-8 (incompleta) | reg · cop-2 · cop-8 |
| M-17 | Campi `notable` e `operable` dei giudizi senza lettore di produzione (36 righe del seme su 121) | `type_judgments.py:30-35,401`; `type_vocabulary.py:910-946` | cop-5 (SBAGLIATA in parte) | reg · cop-5 |
| M-18 | Residui di `direzione:*`: taglio in `knowledge.summary()` ed etichetta nel JS | `knowledge.py:762-776`; `watcher-sapere.js:87` |  | reg |
| M-19 | Quattro funzioni senza chiamanti (censimento): `_fact_row`, `_record_repair`, `_translations_report`, `_ws_call` (le due del censore sono uscite col Task 14, `b6a2c155`) | `mind/store.py:692`; `server.py:1408`; `handlers_mind.py:274`; `ha_client.py:1470` |  | reg · cop-1 M1 · cop-5 · cop-6 |
| M-20 | Due usate solo dai test (censimento): `actuator_round` (in pausa, non morta), `objective_history`; le cinque del censore sono negli attrezzi dal Task 14 (`b6a2c155`); `get_config` TOLTA: è letta in produzione (`topology.py:142` via `getattr`, dentro `rebuild`) | `server.py:1999`; `mind/store.py:1157` | cop-4 (conteggio, SBAGLIATA in parte); cop-5 (conteggio, SBAGLIATA in parte) | reg · cop-4 · cop-5 |
| M-21 | `mind/store.objective_history` (ha un test) e `_fact_row` | `mind/store.py:692,1157` |  | reg |
| M-22 | Rotta senza chiamante di produzione: `GET /api/misure`. **Resta per scelta** (dichiarazione D5 della Tappa 0): la usano `scripts/misure.py` e le batterie. La parte `GET /api/entities` (tutto `handlers_entities.py`) e' USCITA con la Tappa 0, Task 9 | `server.py` (rotta `/api/misure`) | cop-8 (conteggio, incompleta) | reg · cop-2 · cop-3 · cop-8 |
| M-23 | `HAClient.render_template`: nessun chiamante di produzione | `ha_client.py:124-129,1363` | cop-5 (incompleta) | reg · cop-5 |
| M-24 | `ServiceRegistry.age_seconds` letto solo da `ensure_fresh` | `action/registry.py` |  | reg |
| M-25 | `behavior_reader.look(force)`: resta nella firma e non fa più niente | `server.py:3039-3044` | cop-1 (righe); cop-2 (righe) | reg · cop-1 · cop-2 |
| M-26 | `model_activation.py` (51 righe, una funzione): si fonde in `model_resolution` | `model_activation.py` |  | reg |
| M-27 | `model_resolution` campo `quando: ""`: chiave sempre vuota | `model_resolution.py:1129` |  | reg |
| M-28 | Migrazioni con la scadenza scritta: sette variabili morte, `HISTORY_RETENTION_DAYS`, `options_migration.seed*`, ramo `"model" in raw` | `server.py:3600-3606,4099-4106`; `chat_settings.py:223,308-325`; `options_migration.py` |  | reg |
| M-29 | `chat_store._TOXIC_ASSISTANT_RE` alias; `conversation_title` usata solo da `list_conversations` | `chat_store.py:99` |  | reg |
| M-30 | `app["model_chain"]` scritto due volte; `app["ultima_riparazione"]` tre (una in codice morto) | `server.py:3232,5250`; `server.py:1421,1494,1536` | cop-1 (conteggio); cop-2 (conteggio) | reg · cop-1 · cop-2 |
| M-31 | Segnali in uscita senza lettore: `debug.thinking_blocks`, `tools_called`, `"input"` | `handlers_chat.py:1399-1400,1413` | cop-8 (incompleta) | reg · cop-8 |
| M-32 | `queries._view_behavior` chiede `ricordi` per automazione/script: ramo sempre `[]` [D] | `queries.py:1369` | cop-4 (doppio conteggio) | reg · cop-4 |
| M-33 | `handlers_mind._TECHNICAL_PREFIXES`: definita e mai usata | `handlers_mind.py:130` |  | reg · cop-6 |
| M-34 | `LookupCache` per `slot`: la generalità non ha un secondo cliente | `memory/lookup_cache.py` |  | reg |
| M-35 | `reader`: `nome_utente`, `unique_id`, `config_entry_id`, `original_name` senza lettori fuori da `reader.py` (`dispositivo_id` TOLTO: ha 6 lettori di produzione) | `reader.py:143-145` | cop-4 (SBAGLIATA in parte) | reg · cop-4 |
| M-36 | Frontend: funzioni esportate, seam di test e residui senza chiamanti (`sendQuick`, `HirisState`, `_rendi`, `#hc-version-side`…) | `send.js:211,274`; `state.js`; `dashboard.js:437`; `tree-route.js:569`; `config.html:51`; `services-route.js:385`; `index.html:156-160` |  | reg |
| M-37 | CSS definito e mai citato: 92 classi su 292; `hiris-config-override.css` quasi tutto vecchia UI [D da script] | `hiris-config.css`; `hiris-theme.css`; `hiris-config-override.css` |  | reg |
| M-38 | `scripts/`: `backup-nas.ps1` senza riferimenti; `censimento.py` e `doppioni.py` non agganciati a hook né CI | `scripts/` |  | reg |
| M-39 | Prompt in `agent/prompts.py`: nessun prompt morto (voce negativa, conservata) | `agent/prompts.py` |  | reg · cop-7 |
| M-40 | Residui per tabelle: `casa.db` non aperto da nessun codice, `cambi.state_class`/`source_type` (vedi G-12, G-06) | — |  | reg |
| M-41 | `server.py` «Disinstallazione della card Lovelace»: ~190 righe eseguite a ogni avvio (vedi E-01, E-08) | `server.py:353-603,3399` |  | reg · cop-1 · cop-2 |
| M-42 | `_attempt_detail`: un solo chiamante, una riga di formattazione (indirezione, non morta) | `server.py:2795-2798` |  | cop-1 M2 |
| M-44 | `import time as _time` dentro `_on_startup` accanto a `time` di modulo | `server.py:3321` contro `:9` |  | cop-2 M3 |
| M-45 | `resolved.get("entity")`: chiave che il risolutore non restituisce mai | `tools.py:2491`; `ha_client.py:830` |  | cop-3 M-n1 |
| M-46 | `Subject.last` calcolato per stati e valori e mai letto | `house_history.py:340-343` |  | cop-3 M-n2 |
| M-47 | `_BEHAVIOR_KINDS`: dizionario di cui si usano solo le chiavi, sotto un commento orfano | `house_query.py:35-38` |  | cop-3 M-n3 |
| M-48 | `_ha_channel()`: accessore di una riga con 23 righe di storia, aggirato nello stesso file | `tools.py:1610-1634,2462` |  | cop-3 M-n4 |
| M-49 | Tre costanti senza lettore in `behavior.py` (`FILE_GENUINELY_ABSENT`, `FOLDER_UNREACHABLE`, `_ABSENT`) e i loro commenti | `behavior.py:47-98` |  | cop-4 N-21 |
| M-50 | `_entity_rows(disabled)` riceve sempre `False`: ogni riga annidata porta `disabilitata: false` | `queries.py:514-550,627-629,644-647,1278,1283-1285,1592-1596` |  | cop-4 N-22 |
| M-51 | `HomeSpace.close()` è vuoto, un solo chiamante di produzione | `reader.py:441-446`; `server.py:5366` |  | cop-4 N-23 |
| M-52 | Campi dell'anagrafe mai letti: `icona` (piano, area, etichetta) e `colore` (etichetta) | `reader.py:114,127,155` |  | cop-4 N-24 |
| M-53 | `_plural` chiamata con singolare e plurale uguali («giro a vuoto») | `briefing.py:804` contro `:1601-1605` |  | cop-4 N-25 |
| M-54 | `HAClient.PROBLEM_SEVERITY`: alias di classe con zero lettori di produzione | `ha_client.py:1696-1700` |  | cop-5 M1 |
| M-55 | `HAClient.get_states(entity_ids)`: il ramo del filtro mai raggiunto in produzione (cinque chiamanti passano `[]`) | `ha_client.py:364-365` |  | cop-5 M2 |
| M-56 | `type_vocabulary.CAPABILITY_ATTRIBUTES_ADDED`: mai popolata, mai letta | `type_vocabulary.py:472-474` |  | cop-5 M3 |
| M-59 | 22 righe del vocabolario senza nessun campo: le legge solo il censore, che dal Task 14 è un attrezzo (`scripts/censore_tipi.py`). Non sono morte: toglierle riapre 22 voci del censore. Da decidere | `type_vocabulary.py` (righe senza campi) |  | cop-5 M6 |
| M-61 | Il giudizio `accendibile` non ha lettori nel prodotto: `operable_domains` lo legge solo il censore (attrezzo dal Task 14). `da_sapere_subito` ha un chiamante interno e non è un reperto. Da decidere se il giudizio serve | `type_judgments.py:401` |  | cop-5 M8 |
| M-63 | Commenti-lapide di metodi usciti: 92 righe in `ha_client.py`, 62 in `entity_cache.py` | `ha_client.py:16-22,207-237,383-392,893-905,1000-1005,1389-1406,2058-2066`; `entity_cache.py:13,591-596,723-777` |  | cop-5 M10 |
| M-64 | `report.section()` e il «meccanismo delle porzioni»: zero chiamanti | `mind/report.py:479-483,554-567` |  | cop-6 N-15 |
| M-65 | `as_document`, `measured_value` e tre forme di rotta (`formato=documento`, senza `day`): nessun lettore | `mind/report.py:450-472,486-551`; `handlers_mind.py:227-241,254-259,442-446` |  | cop-6 N-16 |
| M-66 | `KnowledgeStore.read` e `KnowledgeStore.count`: solo test | `mind/knowledge.py:694-702,819-821` |  | cop-6 N-17 |
| M-67 | Costanti e parametri senza lettori: `OUTCOME_GESTURES`, `facts.GENRES`, `readings(subject=)`, `readings_count(source=)` | `actuator_turn.py:41`; `facts.py:75`; `mind/store.py:849,877` |  | cop-6 N-18 |
| M-68 | `OpenAICompatRunner.circuit_state()`: NON e' codice morto (la chiama `_circuit_is_open`, riletto il 02/10/2026); resta vero che nessuno fuori dal runner puo' chiedere lo stato del circuito: e' un dato che c'e' e nessuno puo' chiedere, Tappa 6 | `openai_compat_runner.py` |  | cop-7 N-M2 |
| M-71 | `servizi.STATI`: definita, mai letta (stati come letterali nell'SQL) | `api/servizi.py:51` |  | cop-8 M1 |
| M-72 | `outcome` della consegna al ponte: otto valori che nessuno legge (`error` esce con `ok: true`) | `api/handlers_reasoning.py:88-184` |  | cop-8 M2 |
| M-73 | Il ramo «ruolo non l'ho potuto sapere (trattato come utente)» irraggiungibile [D] | `api/handlers_chat.py:359-363`; `soffitto.py:150-164` |  | cop-8 M3 |
| M-74 | Segnali e cuciture di prova nel prodotto (`app["_clock"]`, `"input"`, `thread_to_context`, rami dichiarati irraggiungibili) | `handlers_reasoning.py:50-51`; `handlers_chat.py:53-54,544,1400`; `chat_thread.py:78-85`; `handlers_home_space.py:46-84,216-228` |  | cop-8 M4 |
| M-75 | Il ramo «ripristino dalla chat» di `Workshop.restore` non ha chiamanti di produzione | `workshop.py:987-1001` |  | cop-9 N-M-1 |
| M-76 | `REASON_DISDETTA`, il `motivo` delle righe `disdetta` e `_migration_3`: scritti, mai letti | `revisions.py:50,110-130,404-406`; `constructions-route.js:633-644` |  | cop-9 N-M-2 |
| M-78 | 10 operazioni su 18 di `mind/operations.py` più `Period` (~530 righe) vivono solo nelle prove; i commenti dicono che le usa `aggregate_day`: falso | `mind/operations.py` |  | compl N-2 |

---

## X. Documenti e commenti che dicono il falso

| Id | Reperto | Righe | Corretta da | Fonti |
|---|---|---|---|---|
| X-01 | Numeri degli strumenti falsi: «otto lettori», «dieci… sedici», «trentaquattro», «quattro» (veri 5 lettori, 6 e 12) | `handlers_mcp.py:60,350,749`; `agent/runner.py:9,93,538-539,1478`; `handlers_chat.py:1175`; `tools.py:1,14-16`; `claude_runner.py:19,1249-1250`; `openai_compat_runner.py:1053-1056`; `BACKLOG.md:2905` | cop-7 (incompleta); cop-8 (incompleta) | reg · cop-3 · cop-7 N-X5 · cop-8 · cop-9 |
| X-02 | Residui di `view`/`guarda`/`cerca`/`ricorda`/`richiama`/`esegui` come vivi (~60 punti nel registro v1, di più dopo la copertura) | `tools.py`; `queries.py` (42); `topology.py`; `reader.py:6,59`; `_sanitize.py:20,42,65`; `handlers_mcp.py:21,125,162`; `handlers_home_space.py:33,112,127,332`; `handlers_chat.py:263,266`; `static/chat/messages.js:151` | cop-3 (incompleta); cop-4 (incompleta, conteggio); cop-7 (incompleta); cop-8 (incompleta) | reg · cop-3 · cop-4 · cop-7 · cop-8 |
| X-03 | `CLAUDE.md`: righe di `server.py`, conteggi dei moduli, «nessun linter», «due porte», numero dei test (CONTRADDIZIONE sui conteggi) | `CLAUDE.md:119-124,199,244,253,267,274,302-303,454-460` |  | reg |
| X-04 | `README.md`: `## AI providers` descrive il mondo pre-3.0.0 e contraddice `## Configuration` | `README.md:224,303,316-345,354` |  | reg |
| X-05 | `scripts/doppioni.py:51` «per .githooks/pre-push»: l'hook non lo invoca | `scripts/doppioni.py:51` |  | reg |
| X-06 | Token interno e segreto condiviso: docstring e commenti falsi dal 22/09/2026; `internal_token.py` citato e inesistente | `handlers_mcp.py:660-675`; `server.py:5648`; `handlers_settings.py:180`; `chat_settings.py:49,362,374`; `middleware_internal_auth.py:71,247-251`; `middleware_csrf.py:11-14,54-57`; `credenziali.py:19-22,38-39` | cop-8 (incompleta) | reg · cop-2 · cop-8 |
| X-07 | `server._timezone_from_home_space_store` cita `casa/strumenti.py::_fuso` (inesistente) | `server.py:1202-1233` |  | reg · cop-3 |
| X-08 | Docstring di provider/modelli: `FIXED_ORDER` «lo stesso di config.yaml», `DISPLAY_NAMES` «mai due», `_bridge_on`, «tetto 150»… | `model_resolution.py:74,151,648-651`; `steering.py:52,90-101`; `redaction.py:146-161`; `handlers_models.py:384-387` | cop-7 (incompleta) | reg · cop-7 |
| X-09 | Motivazioni scritte nel JS: «i test caricano ciascuna route da sola», commento su `editor-kit.js` | `agenda-route.js`; `config/main.js:3-6` |  | reg |
| X-10 | Commenti che citano ciò che non esiste (`casa.db`, opzione `canali`, `HomeSpaceStore.replace`, `handlers_chatbots.py`…); `ChatSettings.load` «non solleva mai» [E] | `reader.py:272-277`; `server.py:3671`; `tools.py:104`; `canali.py:27-31`; `journal.py:177-180`; `_sanitize.py`; `handlers_settings.py`; `chat_settings.py:285-295`; `handlers_chat.py:448-458`; `briefing.py:256,288,1653`; `topology.py:44` | cop-4 (incompleta); cop-8 (righe, incompleta) | reg · cop-2 · cop-3 · cop-4 · cop-8 |
| X-11 | `recipe_turn.device_lines`: «stessi campi e stesso separatore di `observer.house_lines`» (4 su 6, non filtra) | `recipe_turn.py:169-174` |  | reg · cop-6 |
| X-12 | Messaggio fisso «le tiene solo per le entità che dichiarano uno `state_class`» stampato per ogni id fuori da `statistic_ids` | `recipes.py:314-318`; `operations.py:548`; `recipe_turn.py:279-281` |  | reg |
| X-13 | `observer.SYSTEM`: «ciò che lasci FUORI non viene registrato affatto» | `observer.py:57-62` |  | reg · cop-6 |
| X-14 | `actuator_turn.SYSTEM` promette «INDAGINE — vai a vedere» a un turno senza strumenti; frasi false nella pagina dell'osservatore | `actuator_turn.py:51-54`; `watcher-lavoro.js:214` |  | reg · cop-6 |
| X-15 | Docstring di `decided_proposals` («torna solo se la prova cambia») contro `if key in decided: continue`; commento «rilascio A» stantio | `mind/store.py:1309-1314`; `server.py:2053-2056,2199` | cop-1 (righe) | reg · cop-1 X7 · cop-6 |
| X-16 | Descrizione di `search`/`related`: «Guarda `tipo`…», ma la riga porta `genere` (e non sempre) | `tools.py:331-333,357-360` | cop-3 (imprecisa) | reg · cop-3 |
| X-17 | `exchange._domanda` promette «valore, unità e istante» e non rende `misurato_ts` e `nota` che l'istantanea porta | `keeper/exchange.py:380-396`; `tools.py:2751-2757` | cop-9 (imprecisa) | reg · cop-9 N-C-6 |
| X-18 | Docstring di `costruisci_indice`: nome di registro «nullo QUASI OVUNQUE» contro la sonda (CONTRADDIZIONE del registro v1) | `memory/resolver.py` |  | reg · cop-9 |
| X-19 | `resolver.py:13` descrive `find` come «la RETE»; confine dei vocabolari «per questa fetta» (dichiarato, non falso) | `memory/resolver.py:13` |  | reg · cop-9 |
| X-20 | Prompt dell'analista: «dal … al 2026-09-30» letto come scadenza [D] | `analyst_turn.py:258-259`; `report.py:379-381` |  | reg |
| X-21 | `reconsideration_round`: «ogni dieci minuti… 144 misure al giorno», scatta ogni minuto | `server.py:1651-1654,1690-1692` contro `:1698,4440` |  | cop-1 X1 |
| X-22 | Riferimenti a nomi che non esistono più (`topology.sistema_di_riferimento`, `home_space/store.py`, `anagrafe.compare_with_home_assistant`) | `server.py:689,697,1095,1115` (lo stesso nome stantio fuori da `server.py`: vedi X-68) |  | cop-1 X2 |
| X-23 | Riparazione d'avvio: due motivazioni false («query SQL non protetta», «cinque uscite»), `adesso`/`now` | `server.py:1478-1483,1507-1518,1529` |  | cop-1 X3 |
| X-24 | `_close_expired_promise`: riga citata spostata (`handlers_chat.py:477` → `:716-723`) e minuti non quelli del job (vedi S-02) | `server.py:148-149,160-161` |  | cop-1 X4 |
| X-25 | `_promise_delivery`: «I tre collaboratori» sono quattro | `server.py:174-188,209-210` |  | cop-1 X5 |
| X-26 | Il commento del freno (`RETRY_BASE_S`/`RETRY_MAX_S`) attaccato sopra `SCOPE_BATCH` | `server.py:2801-2827` |  | cop-1 X6 |
| X-27 | Undici «silenzi dichiarati»: otto annunciano «resta intatto» prima della cancellazione, tre non girano mai (~330 righe) | `server.py:3918-3926,3942-3960,4002-4010,4218-4259,4708-4771` contro `:4261-4262,2663-2675` |  | cop-2 X1 |
| X-28 | Il commento di apertura della semina: «le sette variabili che run.sh esporta» (non le esporta) | `server.py:3594-3598` contro `:4031-4040`, `run.sh:8,28-68` |  | cop-2 X2 |
| X-29 | «UNA connessione sola» per le serie del resoconto: sono due chiamate (numero di connessioni dedotto) | `server.py:4541-4542,1790-1812` contro `:1831-1839` |  | cop-2 X3 |
| X-30 | Tre riferimenti di riga/luogo che non esistono più (`:633-690`, Google Fonts, `server.py:1169-1177`) | `server.py:3795,5851`; `tests/test_startup_legacy_db_silence.py:2` |  | cop-2 X4 |
| X-31 | La regola «non si scrive in `app[...]` a richiesta servita» dichiarata tre volte, violata in ≥17 punti | `server.py:5652-5681` contro `:737,1174,1421,2034,2523,3155,3208,3232`, `judgments.py:375`, `handlers_models.py:587`, `handlers_settings.py:361` |  | cop-2 X5 |
| X-32 | Nessuna delle ~63 chiavi di `app` è un `web.AppKey`: nessun posto le dichiara (warning non osservato) | 25 file; `handlers_mcp.py:198`, `usage/bridge_loads.py:22` |  | cop-2 X6 |
| X-33 | La descrizione di `related` nomina una chiave (`related`) che la risposta non ha (`legami`) | `tools.py:454,466`; `queries.py:1872-1873` |  | cop-3 X-n1 |
| X-34 | `history` dice «il `run_id` di una riga»: la riga lo porta sotto `esecuzione` | `tools.py:1012,1094-1096`; `house_history.py:216,904` |  | cop-3 X-n2 |
| X-35 | `fetch` consiglia l'impossibile («`fetch` senza ancore») | `tools.py:616-617,631,2249-2254` |  | cop-3 X-n3 |
| X-36 | Nomi di funzioni e moduli usciti in `tools.py`, oltre a X-02 (`anagrafe.*`, `domande.*`, `_specchio()`…) | `tools.py:100,129-131,1508,1523,1885,2042,2080,2098,2102,2257,2319-2320,2552,2761,2766,3135` |  | cop-3 X-n4 |
| X-37 | Il docstring di `_blind_spots` descrive una risposta (`trovati`) e un ramo che non ci sono | `tools.py:1828-1899` |  | cop-3 X-n5 |
| X-38 | Le ceste degli attributi dette «quattro», «cinque» e «sei»: sono sei | `tools.py:278,2057`; `queries.py:1171-1175,1724`; `topology.py:215`; vero `entity_cache.py:359-381` |  | cop-3 X-n6 · cop-4 N-29 |
| X-39 | Provenienze che puntano a nomi usciti da `historian.py` | `house_history.py:225,411,556,721` |  | cop-3 X-n7 |
| X-40 | «La profondità la decido io dal numero di soggetti» non vale per gli errori | `tools.py:1010`; `house_history.py:1263` |  | cop-3 X-n8 |
| X-41 | Le docstring di `compose` e `view` nominano parametri che non esistono (residui di rinomina) | `briefing.py:1447-1496`; `queries.py:1698-1718` |  | cop-4 N-26 |
| X-42 | Trentacinque citazioni di moduli e classi inesistenti scritte come vive (`anagrafe.*`, `domande.*`, `HomeSpaceStore`, `nucleo.*`, `comportamento.*`) | `behavior.py:260`; `briefing.py` x8; `queries.py` x13; `topology.py` x9; `reader.py:4,5,289` |  | cop-4 N-27 |
| X-43 | `topology.py:3`: «Quattro livelli di gerarchia» ma l'albero ne ha tre | `topology.py:3-5` contro `:739-740,896-957` |  | cop-4 N-28 |
| X-44 | `view` e `queries` si dichiarano puri: il ramo `entita` apre l'archivio del sapere | `queries.py:30-35,1754-1756` contro `:1030-1051` |  | cop-4 N-30 |
| X-45 | `ha_client.py`: nomi italiani usciti con la rinomina citati come vivi (`_richiedi_statistiche`, `leggi_registri`…) | `ha_client.py:71,170,960,981,1397,1404,1508,1625,2042,2079-2080,2300,2342,2383` |  | cop-5 X1 |
| X-46 | `ha_client.py`: «nessun consumatore» per `calendar_events`, «qui sopra» per metodi sotto, «uscita qui sotto» | `ha_client.py:16-17,218-237,1164-1166,1255-1256,1393` |  | cop-5 X2 |
| X-47 | `entity_cache.py`: «`loaded` non cambia», «il solo lettore è `handlers_entities`», «read-only access for the inventory API» | `entity_cache.py:24-27,418-429,648,780-781` |  | cop-5 X3 |
| X-48 | `state_translations.py:538-541`: «il censore le chiama direttamente» (non importa il modulo) | `state_translations.py:49-51,538-541` |  | cop-5 X4 |
| X-49 | `type_vocabulary.py`: numerazione delle «metriche»/«domande» incoerente (tre domande numerate 2-3-4, «metrica 4/5») | `type_vocabulary.py:17-42,872,1247,1741,1765,1789,1822` |  | cop-5 X5 |
| X-50 | Rinvii a righe e nomi che non ci sono più in `ha_vocabulary.py` e `type_judgments.py` | `ha_vocabulary.py:30,101`; `type_judgments.py:357,373` |  | cop-5 X6 |
| X-51 | Gli «oggetti» al presente in sei posti, dopo che la tabella è caduta il 15/09 | `mind/store.py:26-27,439-441,753-755`; `watcher.py:348-350`; `facts.py:1-5`; `mind/__init__.py:5` |  | cop-6 N-19 |
| X-52 | `mind/store.py:1378-1383`: un commento su un docstring che non c'è più | `mind/store.py:1354-1383` |  | cop-6 N-20 |
| X-53 | `mind/store.py:467-476`: il commento del resoconto sta sopra la tabella dell'analisi | `mind/store.py:467-487,523-527` |  | cop-6 N-21 |
| X-54 | Il resoconto «per l'analista»: tre docstring descrivono un percorso che non esiste | `mind/report.py:27-30,52-55`; `handlers_mind.py:214-216,264-265` |  | cop-6 N-22 |
| X-55 | `handlers_mind.py:8-24`: «non serializzano niente» e «l'unica eccezione è la resa dello stato» | `api/handlers_mind.py:8-24` |  | cop-6 N-23 |
| X-56 | `handlers_mind.py:66-99`: «tutte e cinque le parti» (sei) e una regola «mai scritta» che è scritta | `api/handlers_mind.py:66-99`; `watcher.py:267-296` |  | cop-6 N-24 |
| X-57 | `mind/watcher.py`: il pavimento, `self._watched` inesistente, log che nomina l'attributo sbagliato | `mind/watcher.py:7,150-154,337-339` |  | cop-6 N-25 |
| X-58 | `mind/seed.py:167-172` contro `:179-196`: tre attributi nel commento, due nella tabella | `mind/seed.py:167-196` |  | cop-6 N-26 |
| X-59 | Piccoli falsi di nome e di conto (`VERSIONE_REGISTRO`, «otto osservazioni» = nove, `reconsider` torna cinque chiavi…) | `recipe_turn.py:103`; `actuator.py:10-14`; `observer.py:323-324`; `analyst_turn.py:142`; `knowledge.py:102-104`; `facts.py:81-85` |  | cop-6 N-27 |
| X-60 | «Quel default (4096) non lo raggiunge nessun chiamante di produzione»: analista, attuatore, «Rifalla» sì | `claude_runner.py:365-373` contro `server.py:1984,2086`, `handlers_proposals.py:173` |  | cop-7 N-X1 |
| X-61 | «Il nucleo non timbra: `compose` non compone nessuna data» (porta l'ora) | `agent/prompts.py:109-112` contro `handlers_home_space.py:334`, `briefing.py:364-389` |  | cop-7 N-X2 |
| X-62 | La motivazione dell'import differito di `MCP_SERVER_NAME` non è più vera | `agent/runner.py:173-190` |  | cop-7 N-X3 |
| X-63 | Funzioni e parametri rinominati citati col nome vecchio (`strumenti_attivi`, `modello_cli`, `verifica_init` in un log…) | `agent/runner.py:42-43,156-157,177,260,608,1113,1725,1733,2083`; `prompts.py:135,144,157,548,561`; `claude_runner.py:19,145,360,845,984,987,1243`; `openai_compat_runner.py:1047` |  | cop-7 N-X4 |
| X-64 | Docstring e messaggi che descrivono ciò che non c'è più; due messaggi chiedono all'utente un'azione impossibile | `agent/runner.py:775-847`; `prompts.py:19-20,518-524`; `openai_compat_runner.py:165,881-883,1169-1171`; `claude_runner.py:140-148` |  | cop-7 N-X6 |
| X-65 | Blocchi di commento attaccati all'istruzione sbagliata (`RAGIONABILI`, `SPECIE`) | `agent/runner.py:1982-1996,2046`; `steering.py:90-111` |  | cop-7 N-X7 |
| X-66 | Il testo che dice al modello «trattato come utente» (un ruolo ignoto vale `lettore`) | `api/handlers_chat.py:321-325,362-363` |  | cop-8 X1 |
| X-67 | `handlers_chat.py`: tre affermazioni false («TERZO valore», `casa.db` in lock, `ALL_TOOL_DEFS`) | `api/handlers_chat.py:132-133,448-458,623-625` |  | cop-8 X2 |
| X-68 | `handlers_home_space.py`: moduli e funzioni usciti (`anagrafe.*`, `nucleo.*`, `comportamento.*`, `sistema_di_riferimento`), campo col nome vecchio | `api/handlers_home_space.py:32,74,112,127,137,148,166,186-199,284,303,349`; `handlers_entities.py:52` |  | cop-8 X3 |
| X-69 | `handlers_memory.py`: «lo specchio si legge già per le unità» (nel GET no); rinvio di riga spostato | `api/handlers_memory.py:67,153-154` |  | cop-8 X4 |
| X-70 | `handlers_servizi.py`/`servizi.py`: «Cinque rotte» (sei); `chiudi_finestra` che l'approvazione non chiama | `handlers_servizi.py:3`; `servizi.py:213-217` |  | cop-8 X5 |
| X-71 | `credenziali.py`: `_BIT = 32` (sono byte), «`ponte.bridge_deadline_min`, dieci di default» (è `scadenza_min`, 5) | `credenziali.py:19-22,38-40,109` |  | cop-8 X6 |
| X-72 | `handlers_mcp.py`, `soffitto.py`, middleware: «sedici strumenti», CLI 2.1.226, `debug.tools_called`, segreto condiviso, `giorni_conservazione` | `handlers_mcp.py:60,126,429`; `soffitto.py:612`; `middleware_internal_auth.py:42-45,98-103,247-251`; `middleware_csrf.py:11-14,54-57`; `handlers_chat_history.py:59`; `handlers_chat.py:568,1126` |  | cop-8 X7 |
| X-73 | Nomi di moduli e funzioni usciti in `keeper/store.py` (`orologio.py`, `promessa.py`, `turno.SOLA_LETTURA`) | `keeper/store.py:5,73,365,374,376` |  | cop-9 N-X-1 |
| X-74 | `HomeSpaceStore`, `home_space/store.py`, `casa.db`, `trova()`/`verifica()`/`_normalizza` citati come vivi in `memory/` | `memory/resolver.py:43,58,79,198,249-283,386-397,431,457`; `interpretation.py:89`; `memory/store.py:3,6,23,231,314` |  | cop-9 N-X-2 |
| X-75 | Commenti che descrivono un'altra cosa (`usage/store.py:173-174`, `revisions.py:373-377`, «quattro... anzi tre caselle», `tools.py:206-224`) | `usage/store.py:173-174`; `revisions.py:373-377`; `interpretation.py:48-53`; `tools.py:206-224` |  | cop-9 N-X-3 |
| X-76 | Il «solo scrittore» del registro degli esiti: i punti che scrivono sono 11 in 5 moduli | non dichiarate dal rapporto |  | compl N-6 |
| X-77 | `GET /api/pending`: il docstring promette due letture, ne fa due COUNT più una SELECT intera | non dichiarate dal rapporto |  | compl N-5 |

---

## S. Difetti che non sono doppioni

Difetti di comportamento che i rapporti descrivono senza una seconda copia, senza codice morto e senza un testo falso. Una riga ciascuno. `Gravità`: solo se il rapporto la dichiara (qui: la posizione nelle graduatorie che i rapporti danno). `Letto/Eseguito/Dedotto`: come lo marca il rapporto.

| Id | Difetto | Gravità | Letto / Eseguito / Dedotto | Nota | Fonti |
|---|---|---|---|---|---|
| S-01 | Turno dell'attuatore raccolto dal ponte: gli indici del modello applicati a un elenco rifatto «adesso» (oggi dormiente, giro in pausa) | 1° dei «5 più gravi» di cop-1 | DEDOTTO | cap. proposto D; Stato del rapporto: DIVERGENTE [D]; Unirla CC | cop-1 D6 |
| S-02 | `_close_expired_promise` dice «ho aspettato N minuti» con la `scadenza_min` di adesso, non la durata del job | 5° dei «5 più gravi» di cop-1 | LETTO | cap. proposto X (la parte di commento è X-24); Stato DIVERGENTE, Unirla CC; si lega a D-09 | cop-1 X4 |
| S-03 | «Per mano di HIRIS» (`_by_hand`) abbina anche gli atti NON eseguiti: ignora `eseguito` |  | LETTO (effetto DEDOTTO) | cap. proposto B; Stato NV, Unirla CC; era «fuori perimetro» di `db` nel registro v1 | cop-3 B-n7 |
| S-04 | Autenticazione WS fallita → `return`: il ciclo eventi non riparte fino al riavvio; `ws_ready` non si azzera |  | LETTO | `ha_client.py:2287-2291` | cop-5 S1 |
| S-05 | `read_dashboards`: `d.get("url_path")` senza `isinstance(d, dict)` |  | LETTO | `ha_client.py:966` (la `:985` lo ha) | cop-5 S2 |
| S-06 | `history`: `from_iso` entra nel percorso dell'URL senza `quote` |  | LETTO | `ha_client.py:1045`; oggi i chiamanti passano `isoformat()` | cop-5 S3 |
| S-07 | `context` (chi ha causato il cambio) non entra nello specchio |  | LETTO | `entity_cache.py:516-587`; vedi correzione a B-25 | cop-5 S4 |
| S-08 | L'argomento unico `-p` oltre 128 KiB: la CLI del ponte non parte (domanda dell'analista 136.822 caratteri) |  | DEDOTTO | cap. proposto D; Stato NV (limite del kernel noto, non provato); il guasto esce come «runner non disponibile» | cop-7 N-D1 |
| S-09 | Due orologi per la stessa scadenza: `timeout=300` fisso della CLI contro `scadenza_min`; due turni pagati per una domanda |  | LETTO (comportamento DEDOTTO) | cap. proposto D; Stato DIVERGENTE, Unirla CC | cop-7 N-D2 |
| S-10 | Il ponte è una corsia sola: un turno lungo blocca la chat; ~3,3 s medi aggiunti per risposta | 1° per peso sulla latenza (cop-7 §5.4) | LETTO (non verificato sul vivo) | cap. proposto D; Stato NV, Unirla CC | cop-7 N-D3 |
| S-11 | Un guasto del registro dei consumi fa cadere il turno (risposta già prodotta persa); la misura del turno è blindata |  | LETTO | cap. proposto D; Stato DIVERGENTE, Unirla CC | cop-7 N-D7 |
| S-12 | Le chiamate di strumento della stessa risposta partono in fila, non insieme (8 letture = 8 attese) | 3° per peso sulla latenza (cop-7 §5.4) | LETTO (effetto non verificato) | cap. proposto D; Stato NV, Unirla CC | cop-7 N-D8 |
| S-13 | Ritentativi impilati su Claude (SDK + 3 propri, 65 s), nessun circuito, nessun `timeout` dichiarato | 6° per peso sulla latenza (cop-7 §5.4) | DEDOTTO | cap. proposto D; Stato NV (default dell'SDK esterno al repo) | cop-7 N-D9 |
| S-14 | `OpenAICompatRunner` ignora le chiamate di strumento quando `finish_reason == "stop"` |  | DEDOTTO | cap. proposto D; Stato NV, Unirla CC | cop-7 N-D12 |
| S-15 | Perimetro dell'ingress: l'elenco VUOTO di reti fidate ripiega sulla rete Docker intera (`172.30.32.0/23`) |  | LETTO | cap. proposto F; Stato DIVERGENTE, Unirla CC; scatta solo se il nome `supervisor` non si risolve e il campo è tutto sbagliato | cop-8 F1 |
| S-16 | L'identità di un servizio firmato è la chiave, ma il suo `id` nel soggetto è il NOME (due servizi omonimi = stesso filo) |  | LETTO | cap. proposto F; Stato DIVERGENTE, Unirla DP (serve migrazione dei fili) | cop-8 F2 |
| S-17 | Costruire: il «prima» non si rilegge all'applicazione (fino a 7 giorni) né al ripristino: una modifica fatta a mano è sovrascritta e persa |  | LETTO | cap. proposto E; Stato DIVERGENTE, Unirla CC (rifiuto contro avviso: DP) | cop-9 N-E-1 |
| S-18 | `importa_legacy` non è atomica: due commit, un crash in mezzo raddoppia i totali ereditati |  | DEDOTTO | cap. proposto G; Stato NV, Unirla PS (una transazione) | cop-9 N-G-6 |
| S-19 | `ChatSettings.load` solleva (`[1,2]` → `AttributeError`; `thinking_budget: "abc"` → `ValueError`) e `server.py:3809` la chiama senza `try` |  | ESEGUITO | già nel registro v1 dentro X-10 (docstring «non solleva mai»); nessun rapporto di copertura l'ha riletta | reg X-10 (d7 §1.9) |
| S-20 | L'avviso «il bersaglio è cambiato» di una promessa non può mai partire: lo spazzino legge `occurrence["anteprima"]` (`sweeper.py:202-205`), la porta scrive `"bersaglio"` (`actuator.py:816`); alla nascita `_count_target` passa il bersaglio non tradotto, quindi `entities_at_birth` è sempre NULL |  | LETTO (non eseguito) | Stato DIVERGENTE, Unirla CC; la prova usa una porta finta | compl N-1 |
| S-21 | Nessuna prova fissa che un servizio firmato (`auth_via="canale"`) non arrivi a `/api/mcp`: il codice lo impedisce, ma senza sorveglianza |  | LETTO | dal censimento dell'MCP esterno (`mcp-esterno.md`, «Non stabilito»); e' un comportamento dei permessi: Tappa 7 | Tappa 0, Task 9 |
| S-22 | La pagina Memoria mostra il nome di un'entita' ancorata solo se il REGISTRO ne ha uno: per le entita' col nome solo nel `friendly_name` (la norma su questa casa) l'ancora esce senza nome. I nomi di ripiego che dovevano rimediare entravano solo nell'indice di `find()` e non hanno mai avuto effetto |  | LETTO | `api/handlers_memory.py::_resolve_tether` legge `nome`; dichiarazione D8 della Tappa 0: si ripara con la resa unica (Tappa 4) | Tappa 0, Task 13 |

---

# In coda

## 1. Sintesi

I conti si chiedono, non si ricopiano: `python scripts/registro.py conta`.
Questa sezione portava una tabella di totali scritta a mano il 01/10/2026 (458 voci, prima
delle sei aggiunte del complemento): i suoi numeri non coincidevano con quelli della spec che
li citava, ed è uscita con la Tappa 0.


Ritirate per intero: **0**. Nessuna correzione dichiara falsa una voce intera; sette voci perdono un pezzo (ritiri parziali, elencati nella sezione 2). Lo stato `RITIRATA` resta in legenda per le prossime revisioni.
«Due verdetti» = voci nuove trovate da due rapporti che non concordano sullo Stato o su Unirla (sezione 3). Lo Stato delle voci v1 non è cambiato per nessuna correzione; Unirla è cambiata per A-13 (da CC a PS).

## 2. Voci del registro v1 risultate sbagliate, imprecise o cambiate nel verdetto

### 2a. Sbagliate o imprecise nel contenuto (25 correzioni)

- **A-12** · cop-3 · imprecisa — l'automazione non «compare in entrambe le liste» nella stessa risposta: le due forme escono da due chiamate (`genere=entita`, `genere=automazione`)
- **A-13** · cop-9 · verdetto — «DIVERGENTE nell'ingresso, EQUIVALENTE nell'esito» di `verify`/`tutti`/`validate`: `nome_dedotto` non ha lettori (M-77), quindi Unirla passa da CC a PS (un solo costruttore, via cache, dopo aver cancellato `find`)
- **B-03** · cop-6 · nome — non esiste `_series_note`: è `_series_block` (`recipe_turn.py:264-289`)
- **B-17** · cop-6 · imprecisa — i «lettori della sola copia congelata» sono due copie: `observer.py:107` legge l'anagrafe, `facts.py:666`/`report.py:770` la classe archiviata dall'evento (terza copia, altra scadenza)
- **B-23** · cop-5 · imprecisa — `ha_client.py:1535-1536` è un'altra tabella (`_CONFIG_COMMAND_BY_DOMAIN`), non una copia; mancano `HELPER_DOMAINS` e `RELATED_ITEM_TYPES`↔`LINK_NAME`
- **B-25** · cop-5 · imprecisa — `restored` ARRIVA (cesta `values`); manca dall'elenco `context`, che non entra nello specchio
- **C-05** · cop-3 · imprecisa — `tools._snapshot` è di `promise` specie `chiedi`, non di `execute`; il reperto resta (zona di `person.*` in chiaro in `promessa.istantanea`)
- **C-06** · cop-8 · incompleta, imprecisa — `handlers_reasoning.py` sta in entrambe le colonne; il 401 HTTP di `handlers_mcp.py` è `{"error"}` (terza forma: `error` JSON-RPC); manca `{"status": "error", "message"}` della chat
- **C-10** · cop-6 · incompleta, due etichette sbagliate — i prefissi sono scritti a mano anche da chi produce i soggetti (`watcher.py:596,779,800,839`); `handlers_mind.py:344` non è «campi giudizio» (chiavi della POST); `OUTCOME_GESTURES` sono i GESTI di un esito, non «specie osservazione», senza lettori Python
- **D-05** · cop-6 · imprecisa — `actuator_turn` non ha nessun `bridge_turn` (il job è composto in `server.py:2331`); il contratto due volte vale per analista (`analyst_turn.py:271` + `:306-308`) e ricette (`recipe_turn.py:260` + `:577-579`)
- **D-20** · cop-3 · SBAGLIATA in parte — `search(genere=ricordo)` non «elenca e apre»: apre soltanto, e solo con un `riferimento` numerico [E]
- **D-20** · cop-4 · doppio conteggio — il ramo `_view_behavior`/`ricordi` (`queries.py:1369`) è lo STESSO reperto di M-32: si conta una volta
- **D-26** · cop-3 · imprecisa — la gemella di `actuator._states()` non è `tools._mirror` ma `tools._state_readings` (`:2758`); `_mirror` è una terza forma
- **D-27** · cop-3 · rimando rotto — «salvo la convenzione di tempo (G-08)»: G-08 è `promesse.recapito`; cop-3 rinvia al suo C-32; nel registro v1 la convenzione del tempo è in G-14
- **F-10** · cop-8 · imprecisa — `panel_visibility.parse_access_flag` non «ricopia l'idioma»: è più stretta apposta e lo dichiara
- **G-07** · cop-9 · file, incompleta — `serializza` è in `keeper/promise.py:283-319`, non `keeper/store.py`; `promesse.fuso` scritto e mai letto
- **G-11** · cop-7 · imprecisa — «`ripiego` mai potato»: `fail_stuck_downgrades` lo porta a `failed` oltre 2x scadenza e `prune` lo toglie a 7 giorni; vale solo dietro il gate `bridge_active` (il punto vero della voce)
- **M-08** · cop-9 · incompleta, imprecisa — inerti anche `nomi_di_ripiego` e la copia con `nome_dedotto`; il costo non è «a ogni `remember`»: la chat passa dalla cache, la pagina ricostruisce a ogni richiesta
- **M-17** · cop-5 · SBAGLIATA in parte — `operable` non ha il lettore `facts`: l'unico chiamante di `operable_domains()` è il censore; con `notevole` sono 36 righe del seme su 121 senza lettore [E]
- **M-20** · cop-4 · conteggio, SBAGLIATA in parte — `get_config` va tolta dall'elenco dei morti: ha ragione d1, il censimento non vede le chiamate via `getattr`
- **M-20** · cop-5 · conteggio, SBAGLIATA in parte — `get_config` è letta in produzione (`topology.py:142` via `getattr`): ha ragione d1; il censimento non vede cinque chiamate per stringa
- **M-32** · cop-4 · doppio conteggio — stesso reperto del ramo citato in D-20: si conta una volta (qui)
- **M-35** · cop-4 · SBAGLIATA in parte — `dispositivo_id` ha almeno 6 lettori di produzione (le copie di B-11); restano morti gli altri quattro; aggiungere `icona` x3 e `colore`
- **X-16** · cop-3 · imprecisa — una riga di `search` porta `genere` (non `tipo`): sempre per automazioni/script/aree/dispositivi, per le entità solo nella media; la voce completa porta `tipo`
- **X-17** · cop-9 · imprecisa — l'istantanea porta ANCHE `misurato_ts` e `nota`: il difetto è che `_domanda` non li rende, non che l'istante manchi

Ritiri parziali (il pezzo esce, la voce resta): **M-20** `get_config` (è letta in produzione) · **M-35** `dispositivo_id` (ha 6 lettori) · **M-17** il lettore `facts` di `operable` (non esiste) · **D-20** «`search(genere=ricordo)` elenca» (apre soltanto) · **B-25** «`restored` non arriva» (arriva) · **B-23** la «seconda copia» a `ha_client.py:1536` (è un'altra tabella) · **F-10** «`panel_visibility` ricopia l'idioma» (è più stretta apposta).
Cambiata nel verdetto: **A-13** (Unirla da CC a PS, cop-9). Doppio conteggio nel registro v1: il ramo `_view_behavior`/`ricordi` stava sia in **D-20** sia in **M-32** (cop-4): si conta in M-32.

### 2b. Conteggi corretti (23 correzioni)

- **A-01** · cop-5 · conteggio — `read_registries` manda 11 comandi su 2 connessioni (10 nel batch + `get_entries`), non 12
- **A-02** · cop-1 · conteggio — due letture dello stesso comando a 5 e 10 min: 432/giorno invece di 288
- **A-07** · cop-2 · incompleta, conteggio — conto d'avvio: anche `system_log` x1, `get_config` x2, `behavior_configs` x2, traduzioni x1, `extract_from_target` fino a 3, sincronia menu, card WS: ~17 connessioni WS di sola lettura + 4 `GET /api/states`
- **A-08** · cop-4 · conteggio — «mai misurati» superato per il numero di chiamate: 1 `hierarchy` + 1 `live_mirror` per turno di chat, da 1 a 4 `hierarchy` per `search`; il tempo resta non misurato
- **A-16** · cop-6 · conteggio, righe, incompleta — `server.py:~1816` e `:1805` sono la STESSA copia (`:1808-1809`); mancano tre dizionari rifatti al volo: `handlers_mind._entity_names`, `observer._area_names`, `recipe_turn._device_name`
- **B-05** · cop-9 · conteggio — la politica B del resolver non è in uso (`nome_dedotto` senza lettori, M-77): le politiche vive sono 3-4, non 4-5
- **B-15** · cop-1 · conteggio — accessori del nome del fuso: 8 chiamate in `server.py` + 2 esterne; il commento `:1217-1233` ne elenca cinque
- **B-23** · cop-4 · conteggio — `_DOMAIN_NAMES` ha 63 voci esatte (45 piattaforme + 18); `_BEHAVIOR_TYPES` derivabile da `BEHAVIOR_DOMAINS.values()`
- **D-03** · cop-7 · conteggio, incompleta — le regole ripetute sono 6, non 5; terza copia in `keeper/exchange.py:364-368`; [M] sovrapposizione lessicale 8-18%: riscritte, non copiate
- **D-07** · cop-7 · righe, conteggio — la riga è `agent/runner.py:1721`; i posti per l'alias di default sono almeno quattro (`runner.py:688`, `:1721`, `handlers_models.py:67`, `model_resolution.py:894`)
- **D-07** · cop-8 · conteggio — i posti dell'alias di default sono quattro: c'è il letterale `"sonnet"` in `handlers_chat.py:646`
- **D-09** · cop-7 · conteggio — `HIRIS_AGENT_POLL_SECONDS`: la lettura di `runner.py:2129` è in `poll_seconds()` morta; la lettura viva è una (`server.py:3160`)
- **D-14** · cop-8 · conteggio — gli scrittori del registro esiti per «subscription» sono quattro: manca `handlers_reasoning.py:144-149`
- **D-17** · cop-8 · conteggio — i kwarg delle tre chiamate sono 12, non 11 (`handlers_chat.py:1332-1344`)
- **D-19** · cop-6 · conteggio non riscontrato — «12 campi all'analista»: la riga di `series_of_measures` ne ha 9; gli altri li aggiunge `mind/analyst.py` (non letto da cop-6)
- **D-22** · cop-3 · conteggio, righe — le proprietà condivise sono 11, non 9 (`limite`, `salta`); 1.178 caratteri in `search`, 1.153 in `history` [E]; intervallo `tools.py:1060-1104`
- **D-23** · cop-3 · conteggio, righe — il titolo dice cinque, l'elenco ne ha sette; la chiamata è `tools.py:2873-2876` (`:2823` è la definizione)
- **F-01** · cop-8 · conteggio — «sette punti» è stretto: la stessa domanda anche in `handlers_mcp.py:681`, `handlers_reasoning.py:41`, `middleware_csrf.py:58`, `admission_refusal`, `adopt_if_owner`, `handlers_chat.py:888`, `_exchange_chat_job`/`_exchange_promise_id`; nota [D] su `_ENTRY_POINT_BY_AUTH` confermata [L]
- **F-08** · cop-2 · conteggio — cinque definizioni della credenziale (tre in `server.py`: `_credentials`, `_risponde`, `_recompute_chain.risponde`, più le due di `handlers_models`): scioglie la contraddizione d6/d7
- **M-22** · cop-8 · conteggio, incompleta — `handlers_entities.py` ha 91 righe; tetto muto a 1000 senza `total` (con 977 stati vivi è a 23 entità dal taglio); nessun filtro di visibilità né di riservatezza
- **M-30** · cop-1 · conteggio — `app["ultima_riparazione"]` scritto in tre punti (`:1421` morto, `:1494`, `:1536` vivi), non due
- **M-30** · cop-2 · conteggio — `app["ultima_riparazione"]` scritta tre volte (`:1421`, `:1494`, `:1536`); `model_chain` due confermato
- **X-02** · cop-4 · incompleta, conteggio — `topology.py` mancano le righe 168,171,179,349,806; `queries.py` ne ha 42; `briefing.py` e `behavior.py` 0

## 3. Contraddizioni

### 3a. Quelle del registro v1: sciolte, sciolte in parte, ancora aperte

1. **F-04 · quanti posti elencano i provider** (d6 «sette»/«~10», d7 «~21»). ANCORA APERTA: nessun rapporto di copertura ha ricontato.
2. **F-08 · quante definizioni della credenziale** (d6 quattro, d7 due). SCIOLTA da cop-2: sono cinque (`_credentials`, `_risponde`, `_recompute_chain.risponde` in `server.py`, più le due di `handlers_models`). Aveva torto per difetto anche d6.
3. **B-13 · quanto è raggiungibile `_first_last_difference`** (d2 contro sonda). ANCORA APERTA: cop-3 ha verificato le righe senza correzioni, cop-6 dichiara di non aver riletto `operations.py`.
4. **B-05 / X-18 · quanti nomi mancano nel registro** (docstring di `costruisci_indice` contro sonda). ANCORA APERTA: cop-9 ha verificato le righe di X-18 senza toccare i numeri.
5. **B-15 · quanti accessori del nome del fuso** (d2 tre, d6 sette, d7 «fino a cinque»). SCIOLTA IN PARTE da cop-1: l'accessore è uno (`_timezone_from_home_space_store`) con 8 chiamate in `server.py` e 2 esterne; il commento `server.py:1217-1233` ne elenca cinque, per difetto. Restano fuori dal conto le copie del calcolo trovate da cop-3 (`tools.py:3220-3224`, `house_history.py:126-129,145-146`) e cop-7 (`reasoning/queue.py:449-460`).
6. **C-06 · conteggi di `error`/`errore`** (d3, d7, d8). ANCORA APERTA sui numeri; cop-8 e cop-5 correggono la classificazione (`handlers_reasoning.py` in entrambe le colonne, il 401 di `handlers_mcp.py` è `error`, più due chiavi `error` nel client e la forma `{"status": "error", "message"}` della chat).
7. **D-01 · quanti compositori del system prompt** (d5 quattro, d4 tre). ANCORA APERTA come conteggio: cop-7 conferma le quattro righe (`:943`, `:747`, `:1090`, `:501`); la differenza resta se `chat_stream` (M-04, morto) si conta.
8. **M-20 · `get_config`** (d1 letta in produzione, censimento solo test). SCIOLTA da cop-4 e cop-5, concordi: ha ragione d1 (`topology.py:142`, via `getattr`, dentro `rebuild`); il censimento non vede le chiamate per stringa (cinque nel client).
9. **X-03 / T · conteggi della suite** (`CLAUDE.md`, d6, d8). ANCORA APERTA: nessun rapporto di copertura ha contato o lanciato la suite.

### 3b. Nuove: due rapporti di copertura sullo stesso reperto, verdetti diversi

- **A-19** · La finestra di memoria rimisurata a ogni lotto della campagna, su tutte le entità — Stato: NV (cop-1) · E (cop-6) · Unirla: CC (cop-1) · PS (cop-6). Fonti: cop-1 A1 · cop-6 N-01.
- **B-35** · `house_history` importa da `mind` (`integration_of`), contro «`home_space` non importa da `mind`» — Stato: D (cop-3) · E (cop-6) · Unirla: PS. Fonti: cop-3 B-n6 · cop-6 N-07.
- **D-50** · A ogni turno il nucleo rilegge TUTTI i ricordi: 1 + 2N interrogazioni SQLite — Stato: NV (cop-4) · E (cop-9) · Unirla: PS. Fonti: cop-4 N-16 · cop-9 N-D-2.
- **D-51** · Cache del prompt: l'ora nel nucleo, punti di taglio che non coprono il ciclo — Stato: NV · Unirla: DP (cop-4) · CC (cop-7). Fonti: cop-4 N-17 · cop-7 N-D6.

Note sulle quattro: in A (finestra di memoria) cop-1 dichiara dedotta l'invarianza del numero, cop-6 dichiara letto che il numero dei lotti dal secondo non ha lettori; in B (`integration_of`) cop-3 confronta la frase «`home_space` non importa da `mind`» col codice, cop-6 guarda la funzione, che è una sola; in D (cache) cop-4 vede tre commenti opposti e chiede una decisione, cop-7 propone il rimedio; in D (ricordi riletti) il «[D]» di cop-4 sta accanto allo Stato, quello di cop-9 solo accanto al costo.

### 3c. Nuove: rapporti di copertura che non concordano su una voce v1

- **D-07 · quanti posti per l'alias di default `sonnet`** (il registro v1 dice tre). cop-7: «almeno quattro» (`runner.py:688`, `:1721`, `handlers_models.py:67`, `model_resolution.py:894`). cop-8: «sono quattro», e il quarto è `handlers_chat.py:646`. I due elenchi non coincidono: l'unione ne fa cinque. Non scelto.
- **D-05 · il contratto due volte sul ponte.** cop-6: imprecisa (`actuator_turn` non ha `bridge_turn`; lo dice anche cop-1 correggendo D-07). cop-7: «confermata senza modifiche». Non scelto: la riga porta la correzione di cop-6 e la conferma di cop-7 nelle fonti.
- **B-05 · quante politiche di nome.** cop-9: le vive sono 3-4, non 4-5 (la politica B del resolver non ha lettori). cop-3: ne manca una (le automazioni). cop-6: la politica E è descritta a metà. Tre correzioni compatibili fra loro, ma il numero finale non lo dà nessuno.
- **A-13 · indice `Lookup`.** cop-3 e cop-8 confermano righe e contenuto; cop-9 ne cambia il verdetto (divergente solo nell'ingresso, Unirla PS). La riga porta la versione di cop-9.
- Conferma delle righe da un rapporto, correzione di contenuto da un altro (non sono contraddizioni: letture di file diversi): **A-12** (cop-3 imprecisa, cop-4 confermata) · **A-17** (cop-6 incompleta, cop-9 righe verificate) · **B-23** (cop-4 «giusto», cop-5 imprecisa su `ha_client.py:1536`) · **B-24** (cop-4 confermata, cop-3, cop-5, cop-6 incompleta) · **D-09** (cop-1 «giusta», cop-7 una sola lettura viva di `HIRIS_AGENT_POLL_SECONDS`) · **D-26** (cop-3 imprecisa, cop-9 righe verificate).
- Concordi su una correzione: **M-25** e **M-30** (cop-1 e cop-2) · **M-20** (cop-4 e cop-5) · **A-16** copia a `server.py:1808-1809` (cop-1 e cop-6).

## 4. Tabella di tracciabilità

Per ogni rapporto: quanti reperti nuovi dichiara, quanti ne contiene la sua parte 2, e dove è finito ciascuno. `id nuovi` = voce nuova in un capitolo · `in S` = capitolo S · `fusi in una voce v1` = il reperto era già nel registro con altre parole (regola 2a) · `fusi con un altro rapporto` = stessa cosa trovata da due rapporti (regola 2b; l'id è quello assegnato al primo).

| Rapporto | Dichiarati | Nella parte 2 | Id nuovi | In S | Fusi in una voce v1 | Fusi con un altro rapporto | Torna? |
|---|---|---|---|---|---|---|---|
| cop-1 | D 6 · A 3 · X 7 · M 2 · B 1 · C 1 | 20 | 16: D-34, D-35, D-36, D-37, D-38, A-19, A-20, A-21, X-21, X-22, X-23, X-24, X-25, X-26, M-42, C-28 | 2: S-01, S-02 | 3: X7→X-15, M1→M-19, B1→D-32 | 0: – | sì (20 = 20); X4 sta sia in X sia in S (una riga in più) |
| cop-2 | X 6 · M 4 (uno è conferma di M-01) · C 2 · A 2 · F 1 · G 1 | 16 | 13: X-27, X-28, X-29, X-30, X-31, X-32, M-43, M-44, C-29, C-30, A-22, A-23, F-14 | 0: – | 2: M4→M-01, G1→G-10 | 1: M1→D-35 | sì (16 = 16) |
| cop-3 | A 4 · B 7 · C 9 · D 7 · E 1 · M 4 · X 8 | 40 | 39: A-24, A-25, A-26, A-27, B-30, B-31, B-32, B-33, B-34, B-35, C-31, C-32, C-33, C-34, C-35, C-36, C-37, C-38, C-39, D-39, D-40, D-41, D-42, D-43, D-44, D-45, E-09, M-45, M-46, M-47, M-48, X-33, X-34, X-35, X-36, X-37, X-38, X-39, X-40 | 1: S-03 | 0: – | 0: – | sì (40 = 40) |
| cop-4 | A 1 · B 6 · C 4 · D 7 · G 1 · M 5 · X 5 · T 1 (ma l'elenco va da N-01 a N-31: nessun A, D 9) | 31 | 29: B-36, B-37, B-38, B-39, B-40, B-41, C-40, C-41, C-42, C-43, D-46, D-47, D-48, D-49, D-50, D-51, D-52, D-53, G-16, M-49, M-50, M-51, M-52, M-53, X-41, X-42, X-43, X-44, T-13 | 0: – | 1: N-15→A-08 | 1: N-29→X-38 | NO: dichiara 30, ne elenca 31 |
| cop-5 | A 9 · B 7 · C 2 · E 1 · M 10 · X 6 = 35, più 4 difetti letti non-doppioni | 39 | 35: A-28, A-29, A-30, A-31, A-32, A-33, A-34, A-35, A-36, B-42, B-43, B-44, B-45, B-46, B-47, B-48, C-44, C-45, E-10, M-54, M-55, M-56, M-57, M-58, M-59, M-60, M-61, M-62, M-63, X-45, X-46, X-47, X-48, X-49, X-50 | 4: S-04, S-05, S-06, S-07 | 0: – | 0: – | sì (39 = 39) |
| cop-6 | A 4 · B 3 · C 4 · D 2 · G 2 · M 4 · X 9 | 28 | 26: A-37, A-38, A-39, B-49, B-50, C-46, C-47, C-48, C-49, D-54, D-55, G-17, M-64, M-65, M-66, M-67, X-51, X-52, X-53, X-54, X-55, X-56, X-57, X-58, X-59, G-18 | 0: – | 0: – | 2: N-01→A-19, N-07→B-35 | sì (28 = 28) |
| cop-7 | nessun totale dichiarato; in parte 2: N-D1…N-D15, N-X1…N-X7, N-M1…N-M4, N-F1, N-F2 = 28 | 28 | 18: D-56, D-57, D-58, D-59, D-60, D-61, D-62, X-60, X-61, X-62, X-63, X-64, X-65, M-68, M-69, M-70, F-15, F-16 | 7: S-08, S-09, S-10, S-11, S-12, S-13, S-14 | 1: N-X5→X-01 | 2: N-D6→D-51, N-M1→M-43 | il rapporto non dichiara un totale; contati 28 |
| cop-8 | nessun totale dichiarato (il file non ha messaggio finale); in parte 2: F 7 · D 4 · C 5 · M 4 · X 7 · T 1 = 28 | 28 | 24: F-17, F-18, F-19, F-20, F-21, D-63, D-64, D-65, D-66, C-50, C-51, C-52, M-71, M-72, M-73, M-74, X-66, X-67, X-68, X-69, X-70, X-71, X-72, T-14 | 2: S-15, S-16 | 0: – | 2: C1→B-38, C2→B-39 | il rapporto non dichiara un totale; contati 28 |
| cop-9 | nessun totale dichiarato (il file non ha messaggio finale); in parte 2: E 3 · G 7 · B 5 · C 7 · D 2 · M 3 · X 3 · T 2 = 32 | 32 | 23: E-11, E-12, G-19, G-20, G-21, G-22, G-23, B-51, B-52, B-53, B-54, C-53, C-54, C-55, C-56, M-75, M-76, M-77, X-73, X-74, X-75, T-15, T-16 | 2: S-17, S-18 | 5: N-G-5→G-14, N-B-1→A-13, N-C-2→C-07, N-C-6→X-17, N-C-7→C-26 | 2: N-D-1→D-64, N-D-2→D-50 | il rapporto non dichiara un totale; contati 32 |
| **Totale** | | **262** | **223** | **18** | **12** | **10** | 262 reperti = 223 + 18 + 12 + 10 − 1 (i reperti con due righe) |

Numeri che non tornano, detti: **cop-4** dichiara 30 reperti («A 1 · D 7») e la sua parte 2 ne elenca 31 (N-01…N-31): nessun reperto A, nove reperti D (N-11…N-19). **cop-7**, **cop-8** e **cop-9** non dichiarano un totale (cop-8 e cop-9 non hanno messaggio finale): i reperti sono contati dalla parte 2. **cop-2** conta fra i suoi 16 la conferma di M-01. **cop-5** dichiara 35 «più 4 difetti letti non-doppioni»: i 4 sono in S (S-04…S-07) e nella tabella entrano nel conto della parte 2 (39). La riga S-19 (`ChatSettings.load`) non viene da un rapporto di copertura: è il pezzo eseguito di X-10 del registro v1.

### 4a. Reperti dichiarati nuovi e ricondotti a una voce del registro v1 (12)

- **X-15** ← cop-1 X7 — terzo punto del commento «rilascio A»: l'attuatore usa due versioni di «già deciso» nello stesso giro
- **M-19** ← cop-1 M1 — `_record_repair` confermato morto; `perche`/`giorni` di `ultima_riparazione` con un solo valore possibile
- **D-32** ← cop-1 B1 — import annidati verso privati dell'api e api che importa dal server: ciclo (pezzi già in D-32, D-09)
- **M-01** ← cop-2 M4 — conferma: `server.py:4167-4176` scrive, nessun lettore; `build_embedding_provider` costruito a ogni avvio
- **G-10** ← cop-2 G1 — cap. proposto G/B: due cron alle 03:00:00 (`hiris_mind_pruning`, `hiris_retention`) e il letterale `7 * 86400`
- **A-08** ← cop-4 N-15 — cap. proposto D: `hierarchy()`/`live_mirror()` ricalcolati a ogni chiamata: 1 per turno di chat, da 1 a 4 per `search` (conteggio letto, tempo non misurato)
- **X-01** ← cop-7 N-X5 — altre occorrenze dei conteggi falsi: `runner.py:9,93,538,1478`, `claude_runner.py:19,1249-1250`, `openai_compat_runner.py:1053-1056`
- **G-14** ← cop-9 N-G-5 — `ricordi.detto_il`: terzo formato di tempo (ISO `+00:00`), unico archivio senza `now=`; `said_by` = `subject_key` con un altro nome di colonna; Stato DIVERGENTE nel formato, Unirla DP
- **A-13** ← cop-9 N-B-1 — cap. proposto B: `Lookup` costruito in tre posti con tre ingressi; ciò che contiene in più dell'anagrafe è inerte; Stato «DIVERGENTE nell'ingresso, EQUIVALENTE nell'esito», Unirla PS
- **C-07** ← cop-9 N-C-2 — «Non ho nessun X con quell'identificatore»: quattro scritture e tre parole (`workshop.py:72,952`, `handlers_constructions.py:45`, `keeper/store.py:350`); Stato «DIVERGENTE nel testo, EQUIVALENTE nell'esito»
- **X-17** ← cop-9 N-C-6 — cap. proposto C: `_domanda` scarta `misurato_ts` e `nota` che l'istantanea porta; Stato DIVERGENTE, Unirla CC
- **C-26** ← cop-9 N-C-7 — apostrofi mescolati nella stessa frase: `workshop.py:62-63,72,290,663`, `keeper/store.py:350,352`, `recipient.py:144-145`, `exchange.py:62-74`; formato data server-side `workshop.py:221`

### 4b. Reperti trovati da due rapporti: una voce, due fonti (10)

- **D-35** = cop-1 D2 + cop-2 M1 — cap. proposto M/D: il ramo destro `or claude_runner` non può mai scattare [D]; 20 file di test impostano `app["claude_runner"]`
- **X-38** = cop-3 X-n6 + cop-4 N-29 — `topology.py:215`, `queries.py:1171-1175,1724`: «cinque»/«quattro», sono sei
- **A-19** = cop-1 A1 + cop-6 N-01 — Stato E, Unirla PS (misurare solo quando il lotto annota); 17 comandi × 1525 id per lotto, 4 lotti per campagna
- **B-35** = cop-3 B-n6 + cop-6 N-07 — Stato E (una funzione sola nel modulo sbagliato): `integration_of` vive in `mind/` ed è importata da `home_space/`; con `queries.py:1044` sono due i punti
- **D-51** = cop-4 N-17 + cop-7 N-D6 — cap. proposto D: su Claude i punti di taglio della cache non coprono il ciclo degli strumenti e il nucleo porta l'ora; Stato NV, Unirla CC
- **M-43** = cop-2 M2 + cop-7 N-M1 — `poll_seconds()` zero chiamanti in `hiris/app` e `tests/`
- **B-38** = cop-4 N-03 + cop-8 C1 — cap. proposto C: `handlers_home_space.py:117-118` copia byte per byte di `topology.label_names`
- **B-39** = cop-4 N-04 + cop-8 C2 — cap. proposto C: `senza_corpo` e conteggi ricalcolati nella rotta; Stato NV, Unirla PS
- **D-64** = cop-8 D2 + cop-9 N-D-1 — le due copie della `try/except` in `keeper/exchange.py:175-180,309-313` (fra loro EQUIVALENTI, PS)
- **D-50** = cop-4 N-16 + cop-9 N-D-2 — Stato E, Unirla PS: 200 ricordi = 401 istruzioni SQL per composizione del nucleo [D, non misurato]

## 5. Le altre correzioni al registro v1, una riga ciascuna (74: righe, nomi di riga, copie in più)

Non cambiano il verdetto: spostano una riga o aggiungono una copia che il registro non elencava. Il dettaglio è nella parte 3 del rapporto citato.

- **A-01** · cop-9 · incompleta — `read_registries` costa anche `get_entries` inutile ai due chiamanti; `recipient` non può passare dall'anagrafe com'è (serve il `name` grezzo, mai `name_by_user`); per `workshop` la lettura diretta può essere voluta [D]
- **A-03** · cop-9 · incompleta — `recipients_for` è chiamata anche alla nascita di ogni `chiedi` (`tools.py:2465-2469`): tre letture per un booleano, poi di nuovo al risveglio
- **A-04** · cop-9 · incompleta — `get_services()` torna l'elenco intero per cercare solo `notify.*`; stessa chiamata alla nascita
- **A-06** · cop-5 · incompleta — `get_entries` è pagato anche dai tre chiamanti che non usano gli alias (`server.py:852`, `recipient.py:285`, `workshop.py:868`)
- **A-16** · cop-1 · righe, incompleta — copia a `server.py:1808-1809` (non `~1816`/`:1805`); terza gemella `:1811-1814` (333 letture del sapere a resoconto)
- **A-16** · cop-4 · righe — `device_names` è `briefing.py:1658-1662`, non `:~1450`; lì la copia mette `""` e la divergenza è assorbita da `_device_annotation`
- **A-17** · cop-6 · incompleta — mancano `cambi.domain/title/first_occurred`, campi della cronaca, `resoconto.obiettivo`, `giudizio.impronta`, `analisi.osservazioni[]`, `proposte.impronta/prova_json`, ricette nel sapere (tabella 4c di cop-6)
- **A-18** · cop-6 · incompleta, righe — `_wanted_cache` a `watcher.py:131`; stessa sorte non elencata: `_marked_automations` (nome fissato al primo scatto), `_missing_rounds`, `_automation_faults`
- **B-01** · cop-3 · incompleta — una copia in più: `house_query.py:363-365` esclude i DISPOSITIVI disabilitati e li conta in `escluse["disabilitate"]`
- **B-01** · cop-4 · righe — la partizione è `topology.py:871-894` (decisione a `889-894`), non `881-891`
- **B-02** · cop-4 · righe — docstring `queries.py:1551-1560`; commento `briefing.py:1586-1596`
- **B-05** · cop-3 · incompleta — manca la politica delle automazioni: senza nome esce `nome: null` da `search` e col suo id da `history`
- **B-05** · cop-4 · righe — la politica C sta in `reader.py:197` e `:206` (`:213` è un commento)
- **B-05** · cop-6 · incompleta — politica E: la fonte «poi vivo» è `handlers_mind._entity_names`; ordine vero di `_resolved_name`: salvato → nome dell'integrazione → vivo; per le misure il nome del DISPOSITIVO
- **B-14** · cop-4 · righe — `queries._view_integration` è `queries.py:1444-1620`
- **B-15** · cop-3 · incompleta — «adesso nel fuso della casa» anche in `tools.py:3220-3224` e `house_history.py:126-129,145-146`
- **B-15** · cop-7 · incompleta — `reasoning/queue.py:449-460` rifà `historian.day_boundaries`
- **B-17** · cop-4 · incompleta — `actual_class` e `actual_unit` sono lo stesso corpo (B-36), non due regole parallele
- **B-18** · cop-3 · incompleta — altre tre copie del confronto esatto: `house_query.py:327`, `:356`, `house_history.py:1245`
- **B-22** · cop-5 · incompleta — mancano tre case (nomi dei campi in due vocabolari, `PROVENANCES`, tre costanti di versione); misura [E]: 76 righe, 187 campi; solo 6 tipi in entrambe le case e lì `type_vocabulary` è vuoto
- **B-22** · cop-6 · righe — `_WANTED_ATTRIBUTES` è a `seed.py:192`
- **B-24** · cop-3 · incompleta — dominio da id anche in `tools.py:2283,3008,3031`; tetti in più (`RECENT_RUNS`, `MESSAGE_MAX`, `MAX_CALENDAR_EVENTS`, 50 promesse, `MAX_HISTORY_POINTS`)
- **B-24** · cop-5 · incompleta — altre copie del dominio da id: `ha_client.py:1567`, `type_judgments.py:259`, `mind/facts.py:142`, `mind/report.py:640,769`
- **B-24** · cop-6 · incompleta — dominio da id anche in `mind/facts.py:142`, `mind/report.py:769`, `type_judgments.py:259`, `mind/watcher.py:293`
- **C-04** · cop-3 · incompleta — da aggiungere `genere` (parametro di `search` e di `history`), `non_letti` (lista/dizionario), `riferimento` (`string` o `integer` contro `string`)
- **C-04** · cop-4 · incompleta — il «`False` fisso nelle righe annidate» è prodotto da un parametro morto, `_entity_rows(disabled)` (M-50)
- **C-06** · cop-5 · incompleta — due chiavi `error` non elencate: `HAClient.render_template` e `entity_cache.unreadable_inventory_error`
- **C-07** · cop-8 · incompleta — `handlers_memory.py` ripete fra PATCH e DELETE il 503, la lettura dell'id e il 404
- **C-13** · cop-6 · incompleta — terzo punto senza nome: `handle_knowledge` → `non_capito[].soggetto` è l'id del dispositivo; per `integrazione:<id>` il titolo c'è due volte e non è portato
- **C-13** · cop-9 · incompleta — `_resolve_tether` non usa `nome_dedotto` perché nessun `Lookup` lo legge (M-77)
- **C-15** · cop-8 · righe, incompleta — il blocco è `handlers_chat.py:1008-1016`; `max_turns_reached` esce con stato 200
- **C-26** · cop-9 · incompleta — non elenca i file con più mescolanza (`workshop.py:62-63`, `keeper/store.py:350/352`)
- **D-02** · cop-7 · righe, incompleta — `BASE_TOOL_RULES` va da `:267` a `:352`; lo stesso difetto vale per la PROMESSA (6 strumenti su 12) e per `chat_stream`
- **D-07** · cop-1 · incompleta — `_enqueue_actuator_turn` è l'unica che scrive il job a mano: `actuator_turn` non ha `bridge_turn`
- **D-08** · cop-1 · incompleta — l'attuatore controlla `day != today` ma non `status`; il suo «già letto» confronta un valore diverso dalla traccia
- **D-09** · cop-1 · incompleta — il letterale `5` a `server.py:149` determina anche il testo del messaggio all'utente
- **D-09** · cop-8 · incompleta — `handlers_chat_history.py:50,81,91,100,112` usa `app["data_dir"]` senza ripiego: due stili per la stessa chiave
- **D-10** · cop-7 · righe — i cicli stanno a `claude_runner.py:1019` e `openai_compat_runner.py:791-792`
- **D-11** · cop-6 · righe — `read_analysis` è a `analyst_turn.py:52`; `read_actuation` `:101-121` è riga per riga `read_analysis` `:52-72`
- **D-13** · cop-7 · incompleta — mancano il commento falso che copre il 4096 (X-60), il default cloud `600.0`, `RETRY_DELAYS`/`MAX_RETRIES`
- **D-14** · cop-7 · righe, incompleta — `_log_usage("ponte", …)` è a `runner.py:1388`; gli scrittori di consumo non sono blindati (S-11); `esito` non vede le troncature (D-58)
- **D-15** · cop-8 · incompleta — terza regola: il ramo SSE scrive solo se non vuota e non tossica; il sincrono scrive anche una risposta vuota [D per l'effetto]
- **D-21** · cop-3 · incompleta — per ogni dettaglio completo si caricano e sanificano TUTTI i ricordi (`count()` + `fetch(limit=count())`) e poi se ne filtrano pochi
- **D-24** · cop-9 · righe, incompleta — `STATES_SOSPESO` è a `revisions.py:57`; i nomi delle tre macchine divergono (G-19) e `AgendaStore.cancel` espone lo stato grezzo (C-54)
- **D-29** · cop-3 · incompleta — un quarto troncamento (`house_history.py:1197-1200`); il sigillo M2 del registro errori sta in `tools.py` e l'altro lettore non lo applica
- **D-29** · cop-5 · righe — `:349` è dentro `_sanitized`, non `_to_minimal` (che sanifica a `:530-531`)
- **D-29** · cop-9 · righe, incompleta — `_ARG_TRUNCATED` a `usage/store.py:245`; troncamenti senza segno a `:262`, `:277`; mancano `workshop.py:148` e `exchange.py:242`
- **D-30** · cop-8 · righe — il dispatcher senza soffitto nasce a `handlers_mcp.py:571-572`, il catalogo intero a `:754`
- **D-33** · cop-6 · righe — `_with_outcomes` è a `handlers_mind.py:542-566` (sovrascrittura a `:556-557`)
- **E-04** · cop-9 · righe — successo a `workshop.py:594-595`, rifiuto con `esecuzione_id`/`guasto_rete` a `:786-794`
- **F-02** · cop-8 · incompleta — la specie ha una terza casa (`canali.SPECIE_IGNOTA`) e un letterale (`soffitto.py:464`)
- **F-07** · cop-9 · righe — `turn.provider` è a `agent/runner.py:1324`
- **F-09** · cop-7 · incompleta — i turni senza `agent_type` (analista, attuatore, «Rifalla») vanno su `gpt-4o`; su Claude tutti i valori usati danno lo stesso modello
- **G-06** · cop-6 · incompleta — da aggiungere: `cambi.domain` sempre `NULL` per `automazione:`
- **G-10** · cop-6 · incompleta — la finestra dei 22 giorni ha DUE costanti e `prune` usa quella non citata (G-18)
- **G-10** · cop-9 · incompleta — `usage._scadi_misure` parte a ogni `log_turn` (due DELETE a turno); la protezione di `revisions._prune` vale solo per `applicata`
- **G-12** · cop-2 · incompleta — 8 degli 11 file di `RESIDUI_DISMESSI` sono prima annunciati «resta su disco, intatto», 3 annunciati dopo la cancellazione
- **M-02** · cop-7 · incompleta — conferma; `ClaudeRunner._chosen_model` è VIVO (`:829`, usato da `chat`)
- **M-11** · cop-1 · incompleta — manca `ACTUATOR_AUTHOR` (`server.py:2144`), senza altri lettori; somma 318 confermata
- **M-16** · cop-8 · incompleta — da aggiungere il log `handlers_mcp.py:683-685` e il docstring `handlers_reasoning.py:39`
- **M-23** · cop-5 · incompleta — con `render_template` escono `MAX_TEMPLATE_LEN`, `MAX_TEMPLATE_RESPONSE_LEN` e tre prove
- **M-25** · cop-1 · righe — `look(force)` a `server.py:3039-3044`
- **M-25** · cop-2 · righe — `look(force)` a `server.py:3039-3044` (3030-3037 è `_folder`)
- **M-31** · cop-8 · incompleta — `"input"` (`handlers_chat.py:1400`) costruito e non letto nemmeno dal log
- **X-01** · cop-7 · incompleta — altre occorrenze: `runner.py:9,93,538,1478`, `claude_runner.py:19,1249-1250`, `openai_compat_runner.py:1053-1056`
- **X-01** · cop-8 · incompleta — una copia in più: `handlers_mcp.py:60`
- **X-02** · cop-3 · incompleta — righe in più in `tools.py`: 129-131, 1508, 1523, 1885, 2042, 2080, 2098, 2102, 2257, 2552, 2761-2766, 3135
- **X-02** · cop-7 · incompleta — famiglia più larga: nomi di FUNZIONI e PARAMETRI rinominati, incluso un messaggio di log (X-63)
- **X-02** · cop-8 · incompleta — copie in più: `handlers_home_space.py:112,127,332`, `handlers_chat.py:263,266`
- **X-06** · cop-8 · incompleta — copie in più: `middleware_internal_auth.py:247-251`, `middleware_csrf.py:11-14,54-57`, `credenziali.py:19-22,38-39`; l'intestazione `X-HIRIS-Internal-Token` porta ancora la credenziale di turno
- **X-08** · cop-7 · incompleta — il blocco di commento `steering.py:90-101` è attaccato agli `import`, non a `SPECIE`
- **X-10** · cop-4 · incompleta — aggiungere `home_space/store.py::sostituisci` (`briefing.py:256,288`) e `archivio.replace` (`topology.py:44`, `briefing.py:1653`)
- **X-10** · cop-8 · righe, incompleta — `canali.py`: il capoverso è `:27-31` e il file si contraddice (`:169-171`); copia in più di `casa.db` come vivo: `handlers_chat.py:448-458`
- **X-15** · cop-1 · righe — il commento falso è a `server.py:2053-2056` (un solo punto); `_file_proposals` (`:2189`) lo smentisce nello stesso giro

Voci v1 toccate dalla copertura: 152 su 216 (88 corrette almeno una volta, le altre solo confermate o arricchite di una fonte). Le restanti 64 non hanno ricevuto né una correzione né una conferma esplicita da un rapporto di copertura: A 2 (A-05, A-14) · B 4 (B-04, B-26, B-27, B-29) · C 12 (C-03, C-08, C-14, C-16, C-19, C-20, C-21, C-22, C-23, C-24, C-25, C-27) · D 3 (D-12, D-16, D-31) · E 2 (E-03, E-06) · F 5 (F-04, F-06, F-11, F-12, F-13) · G 2 (G-03, G-15) · T 8 (T-02, T-03, T-05, T-08, T-09, T-10, T-11, T-12) · M 20 (M-03, M-05, M-06, M-09, M-10, M-12, M-13, M-14, M-18, M-21, M-24, M-26, M-27, M-28, M-29, M-34, M-36, M-37, M-38, M-40) · X 6 (X-03, X-04, X-05, X-09, X-12, X-20).

---

## 6. Aggiunte del complemento della matrice (44 file riletti per la matrice, 01/10/2026)

Fonte: `MATRICE-COMPLEMENTO-44-FILE.md`, §7. Letto sul codice, non eseguito salvo dove detto.

Le sei voci del complemento (S-20, M-78, M-79, X-76, X-77, E-13) stanno ora nei loro capitoli:
una voce scritta fuori dal suo capitolo è una voce che un lettore dei capitoli non vede.

### Correzioni portate dal complemento

- **F-04** (contraddizione sciolta): i punti che rispondono a «quali provider esistono, in che ordine, con che modello, che credenziale, a che prezzo, come si chiamano» sono **37**, con una sola fonte vera (`models_config.json`), 9 tabelle parallele dei cinque id e 5 ordini letterali.
- **F-08**: le definizioni di «ha una credenziale» sono **6**, non 5; quella di Claude è letta in tre modi (compl N-4).
- **B-13** (contraddizione sciolta): `_first_last_difference` è irraggiungibile dalla produzione — `facts.py` non importa `operations`. La divergenza del consumato è di regola, non di numeri in pagina.
- **Matrice, contraddizione n.6**: la gemella di `actuator._states` è `tools._state_readings` (ragione a cop-3).
- **Matrice, contraddizione n.12**: nessun calendario nel contesto della chat (ragione a cop-4 e cop-8).
- `GET /api/misure`: l'N+1 arriva a 2.000 letture, non 500.
- `mind/operations.py`: le operazioni sono 18, non 14; 8 sono offribili al modello.

---

## Chiuse

Una voce arriva qui solo con `python scripts/registro.py chiudi`, quando la copia è cancellata.

| Id | Voce | Chiusa con | Commit | Cosa è stato cancellato |
|---|---|---|---|---|
| M-01 | `backends/embeddings.py` intero (259 righe): `app["embedding_provider"]` scritto e mai letto, `embed()` mai chiamato | 3.73.0 (da rilasciare) | 508a104f | backends/embeddings.py, le opzioni memory.*, le traduzioni e gli export di run.sh |
| M-03 | `backends/ollama.OllamaBackend` e `backends/base.LLMBackend` (55 + 9 righe): solo test | 3.73.0 (da rilasciare) | 38684dae | la classe OllamaBackend e backends/base.py; resta in ollama.py la guardia sull'indirizzo, che il registro non vedeva e che tre punti del prodotto chiamano |
| M-04 | `chat_stream` (due runner, router, ramo `wants_stream` di `handle_chat`): nessun JS lo chiede | 3.73.0 (da rilasciare) | 38684dae | chat_stream nei due runner e nel router, il ramo SSE di handle_chat |
| M-05 | `LLMRouter` ramo `model != "auto"` con `_route`, `_is_openrouter_model`, `_is_openai_model` | 3.73.0 (da rilasciare) | 38684dae | il ramo del modello esplicito di LLMRouter.chat, _route, _is_openai_model, _is_openrouter_model, _backend_name, _ordered_backends |
| M-06 | `AUTO_MODEL_MAP["agent"]` in entrambe le mappe: nessun `agent_type="agent"` | 3.73.0 (da rilasciare) | 38684dae | la voce agent delle due AUTO_MODEL_MAP e le prove che la fissavano |
| M-08 | `memory/resolver.Lookup.find` e l'indice dei termini: zero chiamanti di produzione | 3.73.0 (da rilasciare) | fa268542 | Lookup.find, l'indice dei termini, _compila, _normalize_con_mappa |
| M-43 | `agent/runner.poll_seconds()` senza chiamanti; la stessa lettura scritta a mano in `server.py:3160` | 3.73.0 (da rilasciare) | 38684dae | agent/runner.poll_seconds |
| M-69 | `openai_compat_runner._TOOL_LEAK_RE = LEAKED_TOOL_NAME_RE`: alias privato, un solo lettore | 3.73.0 (da rilasciare) | 38684dae | l'alias _TOOL_LEAK_RE |
| M-70 | Import locali ridondanti nei runner (`json as _json`, `hashlib as _hashlib`, costanti già importate in testa) | 3.73.0 (da rilasciare) | 38684dae | gli import locali dentro chat_stream, usciti con lei; l'alias hashlib di modulo in openai_compat_runner non e' un import locale e resta |
| M-77 | `nomi_di_ripiego` e `nome_dedotto` di `costruisci_indice` senza lettore: la correzione della pagina Memoria non ha mai funzionato | 3.73.0 (da rilasciare) | fa268542 | il parametro nomi_di_ripiego e nome_dedotto dell'indice; il difetto della pagina Memoria e' la voce S-22 |
| M-79 | `LLMRouter._all`: nessun chiamante | 3.73.0 (da rilasciare) | 38684dae | LLMRouter._all |
| M-09 | `action/registry.capability_bits` e `switchable_domains` con sei ausiliarie (~150 righe): solo uno script e le prove | 3.73.0 (da rilasciare) | b6a2c155 | Task 14 della Tappa 0 |
| M-10 | `home_space/type_census.py` (907 righe): strumento di prova nel pacchetto di produzione | 3.73.0 (da rilasciare) | b6a2c155 | Task 14 della Tappa 0 |
| M-57 | `type_vocabulary.Asked` (zero istanze), `PROVENANCES`, `FIELD_KINDS`: solo test | 3.73.0 (da rilasciare) | b6a2c155 | Task 14 della Tappa 0 |
| M-58 | Otto viste «per la prova» in `type_vocabulary.py` senza chiamanti di produzione (~95 righe) | 3.73.0 (da rilasciare) | b6a2c155 | Task 14 della Tappa 0 |
| M-60 | `state_translation`: il primo gradino (`translation_key` propria) mai alimentato; `SILENCES` solo test | 3.73.0 (da rilasciare) | b6a2c155 | Task 14 della Tappa 0 |
| M-62 | `ha_vocabulary`: `UNAVAILABLE_MEANING`/`UNKNOWN_MEANING` zero lettori, `STATE_CLASS_MEANING` solo censore, `ENTITY_CATEGORY_MEANING["config"]` mai letto | 3.73.0 (da rilasciare) | b6a2c155 | Task 14: le due spiegazioni sono un commento; STATE_CLASS_MEANING resta (la legge il censore); la voce config di ENTITY_CATEGORY_MEANING resta, e' la trascrizione dell'enumerazione di HA |
