# HIRIS assistente in Home Assistant — le decisioni, i fatti, l'attivazione

`spec · 16/09/2026 · bozza: raccoglie il brainstorming; il disegno a sezioni e' ancora da approvare`

Questa e' la **meta' 2** dello sprint dichiarato il 16/09/2026: i comandi verso Home Assistant e
HIRIS come assistente di Assist. Il documento nasce dal brainstorming del 16/09, **ripartito da
zero** su richiesta del proprietario, e fissa tre cose: **le decisioni** (sue, una domanda alla
volta), **i fatti** su cui poggiano (verificati sul sorgente, con la fonte), e **l'attivazione** —
cio' che chi installa HIRIS deve fare perche' l'assistente funzioni. Il disegno di HIRIS (cosa
cambia dentro l'add-on) e' la sezione che manca, e va approvato prima di diventare piano.

Il vincolo che governa tutto resta quello della spec dei tre attori: **HIRIS verra' distribuito ad
altre case**. Ogni scelta si giudica anche con *«cosa succede a chi installa HIRIS su una casa che
non abbiamo mai visto?»*

---

## §0 · Le decisioni del proprietario (16/09/2026)

| # | Domanda | Decisione |
|---|---|---|
| 1 | Cosa deve poter fare | **(a)** chiedere a HIRIS dal telefono, dentro l'app di HA, a testo o a voce · **(d)** comandare la casa con frasi libere · **(c)** HIRIS che avvisa da solo · **poi** l'uso dal **Retro Panel** |
| 2 | In che ordine | **(a) e (d) insieme, poi (c).** Dopo, **la sicurezza costruita sull'intero scenario, per disegno** |
| 3 | Chi risponde | **HIRIS e' l'agente di Assist** (Wyoming), non strumenti per un altro modello |
| 4 | Che risposta | **Ogni frase e' un turno completo di HIRIS**, identico alla chat. Velocizzare voce e chat si indaga **dopo**, sulle misure dell'uso vero |
| 5 | In quale conversazione | **Un filo per ogni conversazione di Assist** (`conversation_id`), separato dalla chat della pagina: e' la strada della **divisione delle chat per utente** che il proprietario vuole introdurre |
| 6 | Chi prova per primo | **Prima HA, poi HIRIS** (`prefer_local_intents`) |
| 7 | Il primo avvio | Il proprietario **conferma in HA**; poi, **su sua richiesta**, HIRIS crea la pipeline «HIRIS» senza renderla predefinita |
| 8 | La voce | **Whisper e Piper in casa**, in locale. HIRIS **non** trascrive: la trascrizione non richiede giudizio, e rifarla dentro HIRIS sarebbe un doppione di un pezzo ufficiale di HA (prima legge, seconda fondamenta) |

**Punto aperto, da portare al proprietario al rilascio:** fra questa fetta e lo sprint della
sicurezza, i comandi via Assist restano **accesi o spenti di fabbrica**?

---

## §1 · I fatti

Ogni riga e' verificata sul sorgente il 16/09/2026; la fonte e' fra parentesi. Dove un fatto viene
solo dalla documentazione, lo si dice.

### Come un add-on diventa agente di Assist

1. **Un add-on puo' essere agente di conversazione senza custom component.** Espone un server
   **Wyoming** che in `describe` dichiara un programma *handle*; HA ne fa una `ConversationEntity`
   (`homeassistant/components/wyoming/data.py`: con un *handle* installato aggiunge
   `Platform.CONVERSATION`; `wyoming/conversation.py`). Precedente ufficiale: l'add-on
   **Script Agent** di OHF-Voice (`OHF-Voice/apps/script-agent/config.yaml`: `discovery: [wyoming]`,
   `homeassistant_api: true`).
2. **Cosa riceve HIRIS**: il testo, la lingua, `conversation_id`, e se ci sono `device_id` e
   `satellite_id` (`wyoming/conversation.py`). **Non l'utente.**
3. **Cosa restituisce**: un testo solo (`Handled` / `NotHandled`). HA **non** usa lo streaming
   (`HandledChunk` esiste nella libreria, HA non lo consuma).
4. **La scoperta**: `discovery: [wyoming]` nel `config.yaml` dell'add-on e un messaggio di
   discovery al Supervisor con `tcp://<host>:<porta>`; HA chiede **una conferma** all'utente
   (`wyoming/config_flow.py`, `async_step_hassio`). Via REST o WebSocket un agente **non** si
   registra.
5. **Lo stesso canale sa anche trascrivere**: un programma *asr* diventa un'entita' `stt`
   (`wyoming/data.py:34-35`). Non lo usiamo (decisione 8).

### La pipeline di Assist

6. **Prima HA, poi l'agente**: con `prefer_local_intents` la pipeline prova le frasi personalizzate
   (`sentence trigger`), poi gli intenti locali di HA, e solo se nessuno ha capito passa all'agente;
   se l'agente dichiara la capacita' di comandare, HA filtra gli intenti locali che interferirebbero
   (`assist_pipeline/default_pipeline.py`).
7. **Le pipeline si creano da fuori**: comandi WebSocket `assist_pipeline/pipeline/create`,
   `update`, `list`, `delete`, `set_preferred` (`assist_pipeline/pipeline.py`,
   `helpers/collection.py`).
8. **Nessun taglio a 15 secondi**: il limite di un'esecuzione della pipeline e' **300 s**
   (`assist_pipeline/const.py:9`, `DEFAULT_PIPELINE_TIMEOUT`); la fase di conversazione non ha un
   limite suo, e il client Wyoming aspetta la risposta senza timeout.

### La voce dalle app

9. **Senza trascrizione nella pipeline la voce viene rifiutata**: «the pipeline does not support
   speech-to-text» (`assist_pipeline/pipeline.py:1841-1843`). Su **Android** il microfono sparisce
   (app Android, `AssistViewModel.kt`); su **iPhone** compare, e la richiesta fallisce.
10. **Senza sintesi nella pipeline**: su **Android** la risposta resta scritta (l'app chiede la voce
    solo se la pipeline ce l'ha); su **iPhone** l'app la chiede comunque
    (`AssistViewModel.swift:236`) e HA rifiuta («does not support text-to-speech»,
    `pipeline.py:1863-1866`) finche' nell'app non si disattiva la voce o si attiva la sintesi sul
    telefono.
11. **L'iPhone ha un orecchio suo**: nell'app Companion, sezione *Labs* (iOS 17+), la trascrizione
    e la sintesi avvengono **sul telefono** e a HA arriva solo testo
    (`App/Assist/Local/SpeechTranscriber.swift`, `requiresOnDeviceRecognition = true`).

### I motori in italiano

12. **Whisper** (add-on ufficiale, 3.5.3): `language` accetta `it`; di fabbrica e' `en`; con `auto`
    la documentazione dice che e' «molto piu' lento». `model: auto` sceglie `base-int8` su x86 e
    `tiny-int8` su ARM (`addons/whisper/config.yaml`, `DOCS.md`). Capisce **testo libero**.
13. **Piper** (add-on ufficiale, 2.5.2): voci italiane `it_IT-paola-medium`, `it_IT-serena-medium`,
    `it_IT-serena-high`, `it_IT-riccardo-x_low` (`addons/piper/config.yaml`).
14. **Speech-to-Phrase** capisce solo frasi fisse: **non adatto** a HIRIS
    (`OHF-Voice/speech-to-phrase/README.md`).

### Il Retro Panel

15. **Puo' parlare con HIRIS a testo** con `conversation/process` (WebSocket, o
    `POST /api/conversation/process`) indicando `agent_id`, `conversation_id`, `language`
    (`conversation/http.py`). Vincolo gia' noto: iOS 12, niente input vocale del browser.

---

## §2 · Le misure sulla casa (16/09/2026)

| | |
|---|---|
| Home Assistant | `2026.9.2`, Home Assistant OS 18.2 |
| Host | `generic-x86-64`, 90,8 GB liberi; **CPU e RAM non lette** |
| Add-on vocali installati | **nessuno** (11 add-on in tutto) |
| Entita' `stt` · `tts` · `wake_word` · `assist_satellite` | **0** ciascuna |
| Agenti di conversazione | 1, `conversation.home_assistant` |
| Telefoni | 2 iPhone (`iphone_bet`, `iphone_di_marta`) e un iPad mini; versione di iOS **non letta** |
| Un turno di chat di HIRIS | **14,8 s** dall'invio alla risposta, **un campione** (202 in 0,5 s, poi la coda del ponte) |

### I motori della voce, misurati il 16/09/2026 dopo l'installazione

**Metodo.** Cinque frasi italiane da HIRIS sintetizzate da Piper e trascritte da Whisper attraverso
le API di HA (`POST /api/tts_get_url`, `POST /api/stt/stt.faster_whisper`), **lo stesso audio** per
ogni modello. La voce e' sintetica e pulita: **i tempi valgono, l'accuratezza e' ottimista**. Host:
~8 GB di memoria (limite del container di HA), CPU non letta. Whisper `language: it`, `beam_size: 0`
(di fabbrica).

| Whisper | frasi esatte | trascrizione di 2,4–2,9 s di audio | errori tipici |
|---|---|---|---|
| `tiny-int8` | **0 su 5** | **2,2–2,5 s** | «fotovultai conci», «lucitrami con la», «dieri» |
| `base-int8` (`auto` su x86) | **1 su 5** | **4,0–4,3 s** | «Spemi… trani… daletto», «mercole di» |
| `small-int8` | **5 su 5** nel significato | **11,7–12,6 s** (due giri, stabile) | solo forma: «Come è», «alle 9» |
| `small-int8`, `beam_size: 1` | **5 su 5**, trascrizioni identiche | **10,9–11,5 s** (due giri) | come sopra |

**`beam_size: 1` guadagna circa un secondo, non di piu'**: l'attesa scritta prima della misura
(«sensibilmente piu' veloce») era sbagliata. Il tempo resta quasi uguale al variare della lunghezza
della frase, e questo fa pensare che conti soprattutto il lavoro fisso del modello su questo host —
ipotesi, non misurata.

| Piper | sintesi |
|---|---|
| `it_IT-serena-high` | **5,7–6,5 s** per frasi brevi |
| `it_IT-serena-medium` | **1,0 s** per 60 caratteri, **1,9 s** per 123 (a regime; 7,4 s il primo, caricamento) |

**Trappola di misura trovata:** HA tiene in cache l'audio di una frase gia' sintetizzata — una
seconda misura sulle stesse frasi restituisce l'audio vecchio (anche con una voce cambiata) in
0,1 s. Le misure di sintesi si fanno con `"cache": false`.

**Decisione del proprietario, 17/09/2026:** la configurazione di partenza e' `small-int8` con `beam_size: 1` e `it_IT-serena-medium`; si **prova dal vivo appena l'implementazione dell'assistente e' finita**, si misurano i tempi veri da capo a fondo e solo allora si decide se e dove intervenire.

**La pipeline di prova, 17/09/2026.** Creata con il consenso del proprietario, separata e **non** predefinita: «Prova voce HIRIS» (id `01m2qbx4nqdfbwd8r87yjt39tw`), lingua `it`, agente `conversation.home_assistant`, Whisper, Piper `it_IT-serena-medium`, `prefer_local_intents: true`. Provata a testo con `assist_pipeline/run` (intent → tts): «che temperatura c'e' in soggiorno» → «24.0 gradi», gestita in locale da HA, **0,70 s** fino a `run-end` (la sintesi in streaming parte dopo). Serve a misurare la trascrizione con voci VERE dall'app, prima che HIRIS diventi agente. Si cancella quando la pipeline «HIRIS» esiste.

**La prova dal telefono vero, 17/09/2026 14:01-14:02** (iPhone del proprietario, pipeline «Prova voce HIRIS», frasi DETTE a voce, risposta sentita a voce). Le 4 esecuzioni (`assist_pipeline/pipeline_debug`) **non hanno la fase di trascrizione**: a HA e' arrivato testo gia' trascritto dall'iPhone (fatto 11), con punteggiatura e apostrofi corretti — «Com'e' andata la casa oggi?», «Puoi spegnere tutte le luci tranne quella di camera da letto». HA ha risposto in **0,08-0,15 s** e, come atteso, non ha capito le frasi libere. **Whisper non e' stato usato**: su questa casa (due iPhone) la trascrizione del telefono e' esatta e non costa tempo ad HA; Whisper serve ad Android e ai futuri altoparlanti, e la sua misura con voce vera resta da fare.

**Un turno a voce, sommando le parti misurate** (non misurato da capo a fondo): con `small-int8` e
`serena-medium` circa **12 + 15 + 2 ≈ 29 s**; con `base-int8` circa **4 + 15 + 2 ≈ 21 s**, ma con
un comando su cinque storpiato.

---

## §3 · L'attivazione — cosa deve fare chi installa

Questa sezione e' la **fonte** della guida per l'utente. La guida (README) si scrive **al rilascio**,
quando la funzione esiste: documentarla prima sarebbe il difetto gia' aperto in backlog («Il README
documenta sei rotte che non esistono»). Il piano la porta come passo obbligatorio.

### 1 · I motori della voce (in Home Assistant)

| Motore | Serve per | Senza |
|---|---|---|
| **Whisper** | **parlare** ad Assist | si puo' solo **scrivere** (fatto 9); da iPhone resta la trascrizione sul telefono (fatto 11) |
| **Piper** | **sentire** la risposta | la risposta resta **scritta**; sugli iPhone va disattivata la voce nell'app, o attivata la sintesi sul telefono (fatto 10) |

Per la voce da ogni dispositivo, e per un altoparlante futuro (che non ha uno schermo), servono
**entrambi**.

1. **Impostazioni → Add-on → Negozio degli add-on → Whisper → Installa.** Configurazione:
   **`language: it`** (obbligatorio: di fabbrica e' `en`), `model: auto` per cominciare. Avvia, con
   «Avvia all'accensione».
2. **Negozio degli add-on → Piper → Installa.** Configurazione: **`voice`** fra le quattro italiane
   (fatto 13). Avvia, con «Avvia all'accensione».
3. **Impostazioni → Dispositivi e servizi**: compaiono due voci **Wyoming** rilevate → **Configura**
   su entrambe. Nascono un'entita' `stt` e una `tts`.

### 2 · HIRIS come agente

4. **Impostazioni → Dispositivi e servizi**: compare **HIRIS** rilevato (Wyoming) → **Configura**.
   E' la conferma che HIRIS non puo' saltare (fatto 4). Nasce l'agente «HIRIS».
5. **Nella pagina di HIRIS → «Crea la pipeline HIRIS»**: HIRIS la crea con prima HA poi HIRIS
   (`prefer_local_intents`), lingua italiana, e i motori della voce che trova in casa. **Non** la
   rende predefinita e **non** tocca la pipeline di serie.

### 3 · Sui telefoni

6. **App Companion → Assist**: scegliere la pipeline **«HIRIS»**.
7. **Solo iPhone, facoltativo**: in *Labs* (iOS 17+) si puo' attivare la trascrizione e la voce sul
   telefono. Senza Piper in casa, sugli iPhone va fatto questo, oppure disattivata la voce (fatto 10).

### 4 · Cosa aspettarsi

- I comandi che HA conosce («accendi la luce della cucina») li esegue **HA**, subito, e **non**
  passano da HIRIS: non entrano nella sua cronaca ne' nel filo (decisione 6).
- Il resto va a HIRIS, che risponde come nella chat: oggi **circa 15 secondi** (§2).
- Ogni conversazione di Assist e' **un filo suo**, separato dalla chat della pagina (decisione 5).

---

## §4 · Il disegno di HIRIS — IN CORSO (sezioni approvate dal proprietario)

- **Sezione 1, il canale — APPROVATA il 17/09/2026.** Server TCP Wyoming nello stesso processo, porta 10600 non esposta sull'host (`ports: "10600/tcp": null`, come Whisper 10300 e Script Agent 10500), libreria ufficiale `wyoming`, `describe` con programma *handle* (HIRIS, `it`, `supports_home_control`), scoperta mandata da Python col `SUPERVISOR_TOKEN` dopo che il server ascolta, esito in `/api/health`; `config.yaml` con `discovery: [wyoming]`. Rischio dichiarato: Wyoming non ha autenticazione (sprint sicurezza).
- **Sezione 2, il turno — APPROVATA il 17/09/2026.** Un turno solo estratto dall'handler HTTP e chiamato da pagina e Wyoming; Wyoming attende l'esito dentro il processo (coda del ponte, ricaduta alla catena esistente); una chat in volo per filo e non globale (verificare il lavoratore del ponte, un job alla volta); quando HIRIS non puo' rispondere lo dice con una frase breve e vera; limite nostro proposto 90 s sotto i 300 s di HA; il contesto dice «da Assist, dispositivo X» per risposte in forma parlata.

## §4 (vecchio titolo) · Il disegno di HIRIS — DA FARE

Cosa cambia dentro l'add-on (il server Wyoming, il filo per conversazione nell'archivio della chat,
la creazione della pipeline, la pagina, i comandi, le prove, la verifica dal vivo) **non e' ancora
disegnato**: si presenta a sezioni al proprietario, come per la meta' 1, e solo dopo la sua
approvazione diventa piano.
