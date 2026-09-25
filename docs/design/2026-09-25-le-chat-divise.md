# Le chat divise — un filo per chi parla, una memoria per la casa

`spec · 25/09/2026 · approvata dal proprietario in chat, stesso giorno`

Questa fetta chiude la fondamenta che tre documenti nominano senza costruirla: **«più chat, divise
per utente e per sistema»** (`docs/BACKLOG.md` «La chat è una sola per costruzione»; spec Assist
del 16/09, decisione 5; misure del 24/09, «il ponte non sa da quale chat viene»).

---

## §0 · Le decisioni del proprietario (25/09/2026)

| # | Domanda | Decisione |
|---|---|---|
| 1 | Cosa si divide | **La cronologia della chat.** La memoria (i ricordi) **resta di HIRIS, condivisa**: ogni ricordo sa **chi l'ha detto**, e il modello sa **chi gli sta parlando** — così sa a chi riproporre un'informazione |
| 2 | Quante chat per chi parla | **Un filo solo** per soggetto, col meccanismo di oggi (sessione chiusa da 2 ore di silenzio, riassunto). Più conversazioni con un elenco: eventualmente una fetta dopo |
| 3 | La chiave del filo | **(soggetto, ingresso)** — Paolo dal pannello e Paolo da Assist scritto sono due fili. È la decisione 5 della spec Assist |
| 4 | Chi legge il filo di chi | **Ognuno solo il suo**, amministratore compreso |
| 5 | La cronologia di oggi | **Va all'utente di Home Assistant proprietario** (`is_owner`), sull'ingresso del pannello |
| 6 | Il perimetro | Archivio, rotte, ponte (con il soffitto su `/api/mcp`), chi parla nel prompt, autore dei ricordi, `confirm` legata al filo. Fuori: vedi §6 |

---

## §1 · I fatti (misurati sul codice, 25/09/2026, HEAD `431db448`)

- **Il soggetto esiste al confine e si perde a valle.** `middleware_internal_auth.py` scrive
  `request["soggetto"]` per ogni richiesta (quattro specie: persona, luogo, integrazione, nessuno).
  Nessuno lo porta alla cronologia, alla memoria o al prompt.
- **La chat è una sola.** `chat_store.py`: `chat_sessions(session_id, started_at, last_msg_at,
  summary)` — nessuna colonna per chi. La sessione attiva è «l'ultima che ha parlato, chiunque
  fosse». `clear()` cancella tutto di tutti.
- **I freni sono della casa, non del filo.** `has_pending_chat()` (409 «risposta in arrivo») e
  `max_chat_turns` contano su tutte le persone insieme: se Marta aspetta, Paolo è bloccato.
- **Il ponte perde il soggetto per strada.** Il job `kind="chat"` porta `history, system_prompt,
  contesto, restrict_to_home, response_mode, model` — non chi ha chiesto. `/api/mcp` costruisce il
  dispatcher **senza soffitto né soggetto** (`handlers_mcp.py:438`): sul ponte il ruolo di chi
  chatta non limita gli strumenti, e la cronaca delle azioni registra `nessuno/ponte`.
  `_registra_turno_ponte` scrive `subject=None` e lo dichiara come buco da chiudere alla fonte.
- **Il poll della risposta non guarda chi chiede.** `GET /api/chat/reply/{job_id}` restituisce la
  risposta a chiunque conosca l'id; il ripiego sulla catena usa il soggetto **di chi fa il poll**.
- **L'autore di un ricordo lo indovina il modello.** `remember` ha un parametro `detto_da` «se lo
  sai» (`home_space/tools.py:622`); il nucleo carica **tutti** i ricordi a ogni turno e li rende
  `(detto da X|qualcuno)`.
- **`confirm` conferma la proposta di chiunque.** `workshop._only_pending` sceglie l'unica
  proposta `in_attesa` della casa; `costruzioni` non ha colonna per il filo.
- **Il proprietario si riconosce già.** `ha_client.users()` porta `proprietario` (`is_owner`), e
  la cache dei ruoli del soffitto (`app["ruoli"]["per_id"]`) la tiene per 60 s.

---

## §2 · Il filo

**Un filo è la coppia (soggetto, ingresso).** Vive in un modulo suo, `hiris/app/filo.py`, perché è
un oggetto (fondamenta 4) e perché cinque punti devono calcolarlo **nello stesso modo**
(fondamenta 2): la chat, il poll, la coda, la rotta MCP, l'officina.

- **`soggetto`** → chiave stabile `"<specie>:<id>"`: `persona:<id utente HA>`,
  `luogo:<servizio>`, `integrazione:<servizio>`, `sviluppo:-`. **Mai il nome**, che cambia.
  Una persona anonima (ingress senza intestazioni) è `persona:-`: un filo anonimo condiviso,
  dichiarato.
- **`ingresso`** → la porta da cui è entrata la richiesta, nel vocabolario di
  `2026-09-21-i-canali-e-i-ruoli.md` §5: oggi `pannello` (ingress), `firma` (servizio firmato),
  `sviluppo` (senza token). Card lovelace e Assist aggiungeranno il loro valore quando nasceranno.

**Parola scelta con cura.** «Canale» in questo codice significa già due cose — il servizio firmato
(`canali.py`) e la strada del modello (`misura_turno(canale="catena"|"ponte")`). Qui si usa
**ingresso**, la parola della spec dei ruoli, per non aggiungere un terzo significato alla stessa
parola.

Colonne nuove in inglese: **`subject_key`**, **`entry_point`** — con **gli stessi due nomi** in
tutte le tabelle che portano un filo (fondamenta 3).

---

## §3 · L'archivio della chat

- `chat_sessions` guadagna `subject_key` ed `entry_point` (schema v4, migrazione con `ALTER TABLE`,
  **senza** buttare righe). Indice su `(subject_key, entry_point, last_msg_at)`.
- Ogni operazione pubblica prende il filo: `append`, `load_context`, `get_past_summaries`,
  `count_user_turns`, `clear`. «L'ultima sessione aperta» diventa «l'ultima **di questo filo**»; la
  chiusura per silenzio chiude solo le sessioni di quel filo.
- `delete_old_messages` (potatura notturna) resta della casa: è igiene del disco, non lettura.
- **La cronologia di oggi (decisione 5).** Le righe esistenti restano con `subject_key IS NULL`
  — **orfane**, invisibili a tutti. La prima volta che una richiesta arriva da una persona che Home
  Assistant dice **proprietaria**, dall'ingresso `pannello`, gli orfani diventano suoi
  (`adopt_orphans`). Non all'avvio: all'avvio Home Assistant può non rispondere ancora, e un
  proprietario sbagliato non si ripara. Lo si registra nel log con quante sessioni passano.

---

## §4 · Le rotte e il ponte

**Sincrono.** `handle_chat` calcola il filo dalla richiesta e lo usa per cronologia, riassunti,
limite dei turni e scrittura. Il 409 «risposta in arrivo» diventa **per filo**.

**La coda.** `reasoning_jobs` guadagna `subject_key` ed `entry_point`; `enqueue` li scrive per i job
di chat, `has_pending_chat(filo)` conta solo quel filo. Il `context` del job porta anche il
`soggetto` intero (serve al soffitto e alla cronaca, che vogliono nome e specie, non solo la
chiave).

**Il poll.** `GET /api/chat/reply/{job_id}` risponde **solo se il job è del filo di chi chiede**;
altrimenti `404` — la stessa risposta di un id inesistente, per non confermare che esiste. Il
ripiego sulla catena usa il soggetto **del job**, non quello di chi fa il poll.

**La consegna.** `submit_chat_reply(reply, filo)` scrive nel filo del job.

**La rotta MCP (il buco di sicurezza).** Per un job di chat il runner manda
**`X-HIRIS-Chat: <job_id>`** nella `--mcp-config`, come già fa `X-HIRIS-Promessa` per le promesse.
**Non è un'autenticazione** (quella resta la credenziale di turno) e per questo si **verifica**:
vale solo se è un job `kind="chat"` in stato `claimed`. Da lì `/api/mcp` prende soggetto e frase
del job e costruisce il dispatcher **con soffitto, soggetto e frase**, come il ramo sincrono. Senza
intestazione (promesse, osservatore) resta com'è oggi.

Il soffitto si calcola da un soggetto, non da una richiesta: `soffitto.per_soggetto(app,
soggetto)`, e `per_richiesta` diventa una riga che la chiama — **una regola sola**.

**Il registro dei turni.** Il runner passa il soggetto del job a `log_turn`: la colonna
`turn.subject_json` smette di essere `NULL` sul ponte, e `_registra_turno_ponte` perde il commento
che dichiarava il buco.

---

## §5 · Il modello sa chi gli parla, i ricordi sanno chi li ha detti

**Chi parla.** `compose_chat_context(app, filo, soggetto)` aggiunge in testa una sezione
`## Chi ti sta parlando` — nome, specie, ruolo, ingresso — e prende i riassunti **del filo**.
È **un punto solo**: quella stringa arriva identica ai quattro compositori (catena Claude, catena
OpenAI a blocchi e in streaming, ponte), quindi nessuno dei quattro va toccato.

**Chi l'ha detto.** `remember` scrive l'autore **dal soggetto del turno**, non dal modello: il
parametro `detto_da` esce dallo schema dello strumento (un comportamento solo). La tabella
`ricordi` guadagna `said_by` (la chiave del soggetto, l'identità) accanto a `detto_da` (il nome
leggibile al momento). Il nucleo resta **uno per tutti** — nessun ricordo è nascosto — e continua a
rendere `(detto da X)`: con «stai parlando con X» accanto, il modello sa quando un'informazione
viene da un altro e a chi riproporla.

«*Mia moglie ha caldo*» detto da Paolo resta **detto da Paolo**: l'autore è chi l'ha detto, non di
chi si parla. Il testo del ricordo porta il resto.

**`confirm` è del filo.** `costruzioni` guadagna `subject_key` ed `entry_point`; `propose` li
scrive; `_only_pending` e la conferma per id **considerano solo le proposte del filo che
conferma**. Una proposta nata nel filo di Paolo non si conferma dal filo di Marta — e il rifiuto
non la nomina, per la decisione 4. Le proposte nate prima della fetta (senza filo)
non entrano nella scelta implicita: si confermano solo nominandole per id.

---

## §6 · Fuori, dichiarato (entra in `docs/BACKLOG.md`)

- **Chi ha chiesto una promessa** (spec dei ruoli §11): la promessa non porta il filo, e la sua
  notifica non sa a chi tornare.
- **L'autore del giudizio** fisso a `"proprietario"` (`mind/judgments.py:50`).
- **Assist e card lovelace**: useranno un `entry_point` nuovo; la fetta li rende possibili, non li
  costruisce.
- **Più conversazioni per filo**, con elenco nella pagina.
- **Retro Panel**: finché non si accoppia non parla (BACKLOG, fetta 2 dei ruoli).

---

## §7 · Come si prova

- **Archivio**: due fili non si vedono; la chiusura per silenzio di uno non tocca l'altro; `clear`
  di uno lascia l'altro; la migrazione v3→v4 conserva le righe come orfane; `adopt_orphans` le dà
  al proprietario una volta sola.
- **Rotte**: due persone (intestazioni ingress diverse) non leggono l'una la cronologia dell'altra;
  il 409 di una non blocca l'altra; il poll di un job altrui dà 404.
- **Ponte**: il job porta il filo; `/api/mcp` con `X-HIRIS-Chat` di un job `claimed` applica il
  soffitto di una persona non amministratrice (un `propose` rifiutato); con un id falso o di un job non `claimed` non
  concede niente in più; il registro dei turni porta il soggetto.
- **Prompt**: il contesto contiene «Chi ti sta parlando» col nome della persona.
- **Ricordi**: `remember` da un turno di Paolo scrive `said_by=persona:<id>` anche se il modello
  passa un altro `detto_da`.
- **Confirm**: la proposta del filo A non si conferma dal filo B.
- **Dal vivo** (porta 8099, casa vera): due utenti HA, due fili; il ponte che rifiuta una costruzione
  a un utente non amministratore; la cronologia di oggi che ricompare al proprietario.
