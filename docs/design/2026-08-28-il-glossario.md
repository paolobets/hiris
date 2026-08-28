# Il glossario — come si chiamano le cose

**Data:** 28 agosto 2026
**Stato:** spec approvata, piano da scrivere
**Ramo:** `2.0`
**Segue:** «il linter e le best practice» (27/08), che ha reso possibile la rinomina.
**Precede:** la rinomina degli identificatori, e — piu' avanti — quella dei nomi degli strumenti.

---

## 1. Il mandato

> **Una lingua sola in tutta la codebase.** Deciso dal proprietario il 28 agosto 2026.

E la correzione che rende il mandato sensato, sua, nello stesso momento:

> **«`gamba = leg` non sempre e' giusto: capiamo invece quale la sua funzione.»**

Non si traduce, **si rinomina**. Il nome inglese non esce dal dizionario: esce da cosa la cosa fa.

**Questa fetta non tocca una riga di codice.** Decide **come si chiamano le cose**, e basta. La
rinomina e' la fetta dopo, ed e' meccanica proprio perche' questa l'ha preceduta: deciderla di
fretta mentre si rinomina significherebbe deciderla male su 786 funzioni insieme.

---

## 2. Il punto zero, misurato il 28/08/2026

Contato su `hiris/app` al commit `f667a08`. Nessun numero e' stimato.

| Misura | Valore |
|---|---|
| Funzioni e metodi | **786** |
| Parametri | **1.347** |
| Classi | **42** |
| Parole distinte non riconosciute come inglesi, negli identificatori | **740** |
| di cui usate **una o due volte** (la coda lunga) | **508** |
| Concetti che vivono **in due lingue** | **13** |
| Citazioni di codice **vere** nei documenti tracciati (dentro apici inversi) | **2.030** in **87** documenti su 97 |
| Nomi di strumenti esposti al modello | **13** |

### I 13 concetti che vivono in due lingue

`model` 33 / `modello` 24 (**negli stessi 5 file**) · `entity` 7 / `entita` 28 · `state` 5 /
`stato` 25 · `now` 10 / `adesso` 46 · `store` 1 / `archivio` 26 · `name` 8 / `nome` 19 ·
`value` 4 / `valore` 21 · `key` 8 / `chiave` 14 · `reason` 2 / `motivo` 17 · `path` 14 /
`percorso` 4 · `error` 2 / `errore` 5 · `list` 2 / `elenco` 3 · `read` 1 / `leggi` 20.

Non e' una questione di gusto: e' la **fondamenta n.3** — *la stessa cosa ha la stessa forma da
tutte le porte* — violata tredici volte.

### La mescolanza e' STRUTTURALE, non sparsa

Il reperto che ha dato la forma a questa fetta. La cucitura non passa dentro le righe: passa **fra
i sottosistemi**.

- **In inglese:** `reasoning/`, `backends/`, `proxy/`, `chat_store`, `llm_router`, `model_activation`
- **In italiano:** `casa/`, `cervello/`, `azione/`, `memoria/`, `schedulatore/`, `consumi/`

E si vede affiancando le classi che fanno la stessa cosa:

| Stesso ruolo | Nome italiano | Nome inglese |
|---|---|---|
| un deposito | `ArchivioMemoria`, `ArchivioCasa`, `ArchivioConsumi` | `ChatStore` |
| una coda di lavori | `schedulatore/` (`Orologio`, `Turno`) | `ReasoningQueue` |
| chi parla con un servizio esterno | `PortaAzione` | `HAClient`, `LLMRouter` |

**`Archivio` e `Store` sono la stessa cosa con due nomi.** E' cio' che vede chi apre questo codice
per la prima volta.

---

## 3. Le decisioni

### 3.1 Una lingua sola, e sara' l'inglese

All'italiano ovunque il **confine** si oppone: `model` e' la parola con cui parlano Anthropic e
OpenAI, `entity_id` e `state` sono le parole di Home Assistant. Tradurle dentro vorrebbe dire
ritradurle a ogni chiamata, in un punto in piu' che puo' divergere.

### 3.2 Si rinomina per funzione, non per dizionario

E' il mandato del §1. Per ogni concetto si scrive **prima** cosa fa, **poi** si cerca il nome.
`gamba` → la frase e' *«una delle sei dimensioni lungo cui l'osservatore guarda la casa»*, e da
quella frase `leg` non nasce nemmeno come candidato.

### 3.3 Il glossario decide TUTTO, l'applicazione va a scaglioni

Compresi i 13 nomi degli strumenti. **Decidere e' gratis, applicare no**: la loro rinomina e' una
fetta a se' (vedi §6), perche' non e' una rinomina.

### 3.4 Questa fetta non tocca codice

Il deliverable e' un documento. Zero righe cambiate, zero test nuovi, nessun rischio di
regressione. Il rischio di questa fetta e' di **decidere male**, e le difese sono nel metodo (§5).

---

## 4. Chi entra nel glossario

**Il criterio e' la natura, non la frequenza.** `giorno` e' frequente e non richiede nessun
giudizio; `comprimari` e' raro e lo richiede tutto.

### ① I concetti — entrano, uno per uno

Le parole che il progetto ha **inventato**, e che portano un significato costruito. Vivono
soprattutto nei **nomi dei moduli e delle classi**:

`pavimento` · `gamba` · `grezzo` · `notevole` · `comprimari` · `promessa` · `ponte` · `ripiego` ·
`turno` · `esito` · `officina` · `cronaca` · `anagrafe` · `nucleo` · `osservatore` · `porta` ·
`verdetto` · `rifiuto` · `mestiere` · `forme` · `orologio` · `instradamento` · `riconoscitore` ·
`archivio` · `comportamento` · `domande` · `strumenti` · `catena` · `semaforo` · `invocazione` ·
`registro` · `verifica` · `indice` · `spazio` · `vocabolario` · `interpretazione` …

**Stima: 40-60 parole.** L'elenco definitivo si chiude nel primo passo del piano, estraendo i nomi
di modulo e di classe e togliendo quelli gia' inglesi.

### ② Le parole ordinarie — non entrano

`giorno` · `riga` · `voce` · `valore` · `nome` · `chiave` · `motivo` · `testo` · `elenco` ·
`origine` · `percorso` · `errore` · `argomenti` · `condizioni` …

Hanno un equivalente diretto che **non perde niente**. Vanno in una **tabella di conversione**
decisa una volta e applicata meccanicamente, senza la domanda «che cosa fa». Le 508 parole della
coda lunga stanno quasi tutte qui.

### ③ I nomi degli strumenti — entrano nel glossario, non nella rinomina

`cerca` · `guarda` · `legami` · `ricorda` · `richiama` · `esegui` · `prometti` · `promesse` ·
`disdici` · `costruisci` · `conferma` · `andamento` · `accaduto`

**Non sono identificatori: sono dati.** Vivono come stringhe in tre posti che una rinomina
romperebbe in silenzio:

- `schedulatore/turno.py:38` — `SOLA_LETTURA = ("cerca", "guarda", "legami", …)`: una **lista
  bianca di sicurezza**, indicizzata per nome;
- `memoria/cache_indice.py:27` — l'etichetta `spazio` che identifica il chiamante (`"cerca"`,
  `"ricorda"`) e' **persistita nell'indice**;
- il testo del prompt dice al modello *«Usa "cerca" per trovare il nome giusto»*, in due punti
  (`casa/domande.py:386`, `memoria/interpretazione.py:198`).

Rinominarli e' **un cambio di prodotto con migrazione dati**. Il loro nome si decide qui; si applica
nella fetta che sa gestire la migrazione.

### ④ I valori di dominio — entrano nel glossario, non nella rinomina

**Aggiunto il 28/08 durante l'esecuzione: la spec non li aveva visti.** Emersi dalla review del
Task 1, che ha trovato `genere` — un concetto vero, assente dal glossario perché non è mai nome di
modulo né di classe.

Esiste uno strato di vocabolario che vive **come valore**, non come identificatore. Le tassonomie
del dominio, dichiarate come costanti e **persistite nei database**:

| costante | valori | dove vive |
|---|---|---|
| `GENERI` | funzionamento · presenza · energia · guasto · sicurezza · bilancio | colonna `genere` in `cervello/archivio.py:91` e `azione/cronaca.py:65` |
| `GAMBE` | chi c'e' · comfort · dispersione · energia · buono stato · sicurezza | il pavimento dell'osservatore |
| `SPECIE` | fai · chiedi | colonna `specie` in `schedulatore/archivio.py:34` |
| `STATI_CONCLUSI` | mantenuta · saltata · disdetta · fallita | stato delle promesse |
| `DIREZIONI_BILANCIO` | produzione · autoconsumo · immissione · prelievo · carica · scarica · consumo | i bilanci dell'energia |
| `FAMIGLIE` | credenziale · modello · irraggiungibile · scaduto · altro | gli esiti dei provider |
| `_GESTI` | crea · modifica · cancella | le costruzioni |
| `_TIPI_COMPORTAMENTO` | automazione · script | il comportamento della casa |

**Sono dati, esattamente come i 13 nomi degli strumenti** (③): stanno dentro colonne
`TEXT NOT NULL`, e cambiarli significa migrare quello che c'è già scritto. Stesso trattamento:
**il nome si decide qui, si applica in una fetta che sa gestire la migrazione.**

**Ma i nomi delle costanti sono un'altra cosa.** `genere`, `specie`, `famiglia`, `gesto`,
`direzione`, `stato` sono **identificatori** e **concetti**: vanno nell'insieme ①, si decidono col
metodo del §5, e si rinominano con tutto il resto. Il valore `'funzionamento'` è un dato; la parola
`genere` che lo classifica è un concetto. Sono due decisioni distinte sulla stessa riga di codice.

---

---

## 5. Il metodo — come si decide una parola

Tre passi in ordine, per ogni concetto dell'insieme ①.

### ① Si scrive cosa fa, senza usare la parola italiana

Una frase sola, ricavata **dal codice e dal docstring**, non dal dizionario. Il vincolo di non usare
la parola di partenza non e' una regola di stile: e' cio' che impedisce alla traduzione di
suggerirsi da sola.

> `gamba` → *«una delle sei dimensioni lungo cui l'osservatore guarda la casa: chi c'e', comfort,
> dispersione, energia, buono stato, sicurezza»* → candidati: `aspect`, `dimension`, `concern`.
> Mai `leg`.

### ② Si guarda se la parola esiste gia' al confine

Se Home Assistant o i provider hanno **gia'** un nome per quella cosa, quello vince. Non si inventa
un sinonimo di una parola che il sistema esterno usa gia': sarebbe creare la traduzione che questa
fetta esiste per togliere.

### ③ La prova del lettore nuovo

**E' la parte che trasforma il glossario da opinione a misura**, ed e' eseguibile.

Si dispaccia un agente **senza nessun contesto del progetto**, gli si da' **il solo nome inglese
candidato**, e gli si chiede: *«che cosa fa una cosa che si chiama cosi'?»*. Poi si confronta la sua
risposta con la frase del passo ①.

> **Se il lettore nuovo non ci arriva, il nome e' sbagliato — anche se a noi sembrava ovvio.**

E' la prova per mutazione applicata ai nomi: non «mi suona bene», ma **un esito che puo'
smentirci**. Vale anche in direzione opposta: se due nomi diversi producono la **stessa** risposta,
sono la stessa cosa e devono avere lo stesso nome — e' cosi' che si conferma il caso
`Archivio`/`Store`.

**Il candidato va dato NUDO.** Nessuna frase di contorno, nessun nome di modulo, nessun «in un
add-on di domotica»: qualunque contesto renderebbe la prova incapace di fallire, che e' il difetto
n.1 di questo progetto.

### Chi decide

Proposta con ① e ②, la prova ③ **scarta**, e il **proprietario arbitra** le parole che restano
contese. Saranno poche, e saranno quelle che contano.

---

## 6. Il deliverable

Un documento — **`docs/GLOSSARIO.md`** — con **una riga per concetto**:

Sta alla radice di `docs/`, **senza data e fuori da `design/`**, di proposito: un documento di
design fotografa una decisione presa in un giorno, un glossario e' **vivo** e viene consultato ogni
volta che nasce un nome. Metterlo fra i documenti datati significherebbe che fra sei mesi qualcuno
lo legge come storia invece che come regola.

| italiano | che cosa fa (senza usare la parola) | inglese | esito della prova del lettore nuovo |
|---|---|---|---|

Piu' tre sezioni brevi:

1. **La tabella di conversione** delle parole ordinarie (insieme ②), senza colonna «che cosa fa»;
2. **I 13 nomi degli strumenti**, con i loro nomi inglesi decisi e la nota che l'applicazione e'
   differita;
3. **Le parole contese e come sono state arbitrate**, con la ragione — perche' fra sei mesi la
   domanda «perche' si chiama cosi'?» avra' una risposta scritta invece di un ricordo.

**Criterio di completezza:** ogni concetto dell'insieme ① ha una riga, e ogni riga ha l'esito della
prova ③. Una riga senza esito non e' decisa: e' un'opinione.

---

## 7. Cosa resta fuori, dichiarato

- **La rinomina degli identificatori** — 786 funzioni, 1.347 parametri, 42 classi. E' la fetta
  successiva, ed e' meccanica: il cancello del 27/08 la protegge, e la condizione gia' scritta resta
  («un commit di sola rinomina: se il diff contiene una riga di logica, non e' una rinomina»).
- **I 2.030 riferimenti nei documenti.** Vanno con la rinomina, non prima. E **non sono
  automatizzabili**: i nomi di funzione di questo progetto sono anche parole italiane comuni
  (`stato`, `verifica`, `conta`, `salva`), quindi nessuna sostituzione meccanica puo' distinguere
  una citazione di codice da una frase in prosa. Misurato: senza il filtro degli apici inversi il
  conteggio sale a **10.454**, cioe' l'80% sarebbe prosa.
- **I 13 nomi degli strumenti**, applicati: fetta a se', con migrazione dati.
- **`ruff format`** — dopo la rinomina, come gia' deciso il 27/08.
- **`bandit` completo (26 rilievi) e il cricchetto sulla complessita'** (`C901` 37 in produzione,
  troppi argomenti 34, troppi rami 24): sono la gamba «sicurezza nella scrittura» e
  «comprensibilita'», **indipendenti da questa fetta** e da fare quando si vuole.

### Un reperto per chi accendera' le convenzioni

`N802` (nomi di funzione) da' **145 rilievi**, e sono **quasi tutti falsi positivi**: nomi di test
che usano il MAIUSCOLO per enfasi — `test_..._NON_porta_gli_attributi`,
`test_..._PRIMA_del_fix`, `test_spegni_tutto_in_cucina_tocca_TUTTE_le_luci`. E' una convenzione
**vera e utile** del progetto: la parola maiuscola porta il senso di cio' che il test asserisce.
Accendere `N` in blocco chiederebbe di distruggerla. Se un giorno la si accende, va accesa **con
`N802` spenta sui test e il perche' scritto**.
