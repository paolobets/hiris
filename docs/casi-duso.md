> ## ⚠️ Documento superato — Refactor 2.0 (4 agosto 2026)
>
> Questo documento descrive HIRIS **prima** del Refactor 2.0. Parla di *Sentinella*, *Agentbot*,
> *semaforo* a quattro colori e di un pannello di configurazione di entità AI: tutte cose che il
> refactor ha mandato in pensione o riscritto.
>
> **Cosa HIRIS deve essere oggi:** [`docs/design/2026-08-04-scope-hiris.md`](design/2026-08-04-scope-hiris.md)
> **Cosa fa oggi il codice:** [`docs/design/2026-08-03-analisi-funzionale.md`](design/2026-08-03-analisi-funzionale.md)
>
> Restano utili le parti puramente operative (installazione, chiavi, opzioni dell'add-on). Sarà
> riscritto come atto finale del refactor, sul prodotto vero.

# HIRIS — Casi d'uso ed esempi

> Versione: 1.0.0 · Aggiornato: 2026-07-29

HIRIS mette a disposizione due entità con cui costruire comportamenti,
entrambe filtrate dallo stesso semaforo di sicurezza ed entrambe alimentano
il **Brain** (la home dell'app, `#/`, che osserva la casa e propone nuovi
Agentbot o automazioni):

- **Agentbot** — il livello proattivo. Scatta da solo, su un proprio
  trigger (evento o pianificazione), e notifica o esegue **un'unica azione
  dichiarata** — mai un'azione inventata dall'AI. Sulla stessa pagina
  `#/agentbots` convivono due forme: un set fisso di **detector/situazioni
  built-in** (si abilitano e si tarano, senza scriverli) e gli **Agentbot
  personalizzati** che crei tu (trigger + azione + ragionamento AI
  opzionale).
- **Chatbot** — il livello chat. Una configurazione (prompt, scope
  tool/entità/servizi, scope memoria, politica di conversazione) usata su
  richiesta dall'utente; non ha un trigger proprio e non gira mai se non lo
  interpelli.

Questo documento raccoglie esempi realistici per entrambe.

---

## Agentbot — detector, situazioni e preparazione built-in

Le card "Detector", "Situazioni" e "Preparazione" della pagina `#/agentbots`
espongono un set fisso di controlli built-in — si abilitano e si tarano
(entità, soglie), senza doverli scrivere:

| Detector | Cosa rileva | Parametri tarabili |
|---|---|---|
| `opening` | Porta/finestra aperta oltre una soglia | entità, minuti |
| `fridge_temp` | Temperatura frigo/freezer fuori soglia per troppo tempo | entità, °C max, durata min |
| `power` | Consumo istantaneo sopra soglia | entità, watt max |
| `battery` | Batteria di un sensore/dispositivo sotto soglia | entità, % minima |

| Situazione / preparazione | Cosa fa | Parametri tarabili |
|---|---|---|
| `hot_and_away` | Fa caldo fuori e non c'è nessuno in casa → esegue un'unica azione (es. irrigazione) per qualche minuto | sensore temp. esterna, soglia °C, entità valvola/switch, minuti di funzionamento, salta se pioggia prevista |
| `away_alarm_off` | Segnala quando l'allarme viene disinserito mentre tutti sono fuori | entità allarme |
| `holistic` | Riepilogo giornaliero della casa a un'ora fissa | ora, invii al giorno |
| `evening_arrival` (preparazione) | Prepara una scena in vista di un rientro serale atteso | scena/entità target, entità sole, ora "non prima di" |

Ogni built-in segue lo stesso schema: **detector/situazione → segnale →
reasoner (Claude Haiku di default) → semaforo → notifica e/o azione**. Non
c'è un system prompt da scrivere: il reasoner ha un prompt fisso, condiviso
da tutti i built-in, e risponde sempre con lo stesso schema JSON interno
(`verdict`, `severity`, `message`, `action`).

### Esempio — detector `opening` (ex "Porta lasciata aperta")

**Obiettivo:** essere avvisati se la porta d'ingresso resta aperta troppo a lungo.

**Configurazione (`#/agentbots` → card Detector):**
```json
{
  "detectors": {
    "opening": {
      "enabled": true,
      "entities": ["binary_sensor.porta_ingresso"],
      "open_minutes": 10
    }
  }
}
```

**Cosa succede:** quando `binary_sensor.porta_ingresso` passa a `on`, il
detector emette un segnale con soglia 10 minuti. Se la porta resta aperta
oltre la soglia, il reasoner valuta il contesto e — se lo ritiene opportuno
— notifica.

```
🚪 La porta d'ingresso è aperta da 12 minuti.
```

### Esempio — detector `power` (ex "Rilevamento anomalie energetiche")

**Obiettivo:** essere avvisati di un consumo anomalo prima che arrivi la bolletta.

```json
{
  "detectors": {
    "power": {
      "enabled": true,
      "entities": ["sensor.potenza_rete"],
      "max_watt": 3000
    }
  }
}
```

**Cosa succede:** quando `sensor.potenza_rete` supera 3000 W, il reasoner
valuta il segnale e notifica se lo ritiene un'anomalia:
```
⚡ Consumo anomalo: 3.8 kW alle 02:30.
```

### Esempio — situazione `hot_and_away` (ex "Pianificatore irrigazione intelligente")

**Obiettivo:** quando fa caldo e non c'è nessuno in casa, far partire per
qualche minuto un'utenza (es. l'irrigazione) senza dover programmare nulla
manualmente.

```json
{
  "situations": {
    "presence_entity": "binary_sensor.presenza_casa",
    "hot_and_away": {
      "enabled": true,
      "outside_temp_entity": "sensor.temperatura_esterna",
      "hot_threshold_c": 32,
      "valve_entity": "switch.irrigazione_prato",
      "run_minutes": 5,
      "skip_if_rain": true
    }
  }
}
```

**Cosa succede:** ogni volta che la ronda periodica di HIRIS gira (ogni
`sentinel_ronda_min` minuti), se la temperatura esterna supera 32°C, in casa
non c'è nessuno e non è prevista pioggia, propone di accendere
`switch.irrigazione_prato` per 5 minuti.

**Nota:** non è un pianificatore multi-zona — valuta un'unica
soglia/relè con una singola decisione, non un piano per-zona con durate
calcolate su piogge/umidità/orientamento di ogni aiuola. Quel livello di
ragionamento richiede una lettura vera di previsioni/storico, che è esattamente
a cosa serve l'accesso ai tool di un **Chatbot** (vedi sotto), non una
situazione built-in.

---

## Agentbot — regole personalizzate (definite dall'utente)

Oltre ai built-in, `#/agentbots/new` (oppure il flusso goal-first
`#/nuovo`) permette di creare un tuo Agentbot: un **trigger** (evento su
un'entità, oppure una pianificazione — cron o intervallo), un'**azione
dichiarata** (`notify`, oppure una chiamata `service` concreta con
`domain`/`service`/`entity_id`), un **passo di ragionamento AI opzionale** e
una severità.

Il passo di ragionamento, se abilitato, gira **senza alcun accesso a tool**
e può produrre solo verdict/severity/message — non può mai inventare o
cambiare l'azione. L'azione che scatta davvero è sempre quella dichiarata
nella configurazione dell'Agentbot; se l'output JSON del modello include un
proprio `action`, viene scartato. Un Agentbot di tipo `notify` non può
quindi mai eseguire nulla sulla casa, ragionamento abilitato o no.

### Esempio — avviso porta personalizzato con messaggio discorsivo

**Obiettivo:** ricevere un avviso formulato in linguaggio naturale (non un
template fisso) quando la porta d'ingresso resta aperta troppo a lungo —
stesso trigger del detector built-in `opening`, ma come Agentbot autonomo
con un proprio ragionamento.

```json
{
  "name": "Controllo porta ingresso",
  "trigger": {
    "type": "event",
    "entity_id": "binary_sensor.porta_ingresso",
    "operator": "==",
    "threshold": "on",
    "duration_min": 10
  },
  "action": { "type": "notify" },
  "severity": "warn",
  "reasoning": { "enabled": true, "model": "auto" }
}
```

### Esempio — spegnimento su orario fisso

**Obiettivo:** spegnere le luci del giardino ogni sera alle 23:30, senza
bisogno di ragionamento AI.

```json
{
  "name": "Spegni luci giardino",
  "trigger": { "type": "schedule", "cron": "30 23 * * *" },
  "action": {
    "type": "service",
    "domain": "light",
    "service": "turn_off",
    "entity_id": "light.giardino"
  },
  "reasoning": { "enabled": false },
  "severity": "info"
}
```

---

## Cosa non è ancora ottenibile come Agentbot autonomo

Il trigger di un Agentbot legge **un'unica** entità (più, per un trigger a
pianificazione, un'eventuale condizione secondaria), e il suo passo di
ragionamento opzionale **non ha accesso a tool** — vede solo l'evidenza che
HIRIS gli passa, mai una lettura live del meteo, del calendario, o di un
secondo/terzo sensore. Questo esclude, come regola autonoma:

- Un briefing mattutino che unisce in un unico messaggio il consumo di ieri,
  le previsioni di oggi e gli eventi di calendario.
- Un pre-riscaldamento deciso dinamicamente sulle previsioni di domani.
- Un controllo notturno combinato su più sensori porta/finestra/presenza in
  un'unica valutazione.
- Qualunque cosa richieda di ragionare su più fonti dati live insieme.

Puoi comunque ottenere lo stesso risultato **su richiesta**, chiedendolo a
un Chatbot in chat (vedi sotto) — oppure proponendotelo da solo: il
**Brain** osserva pattern come questi e può proporre un Agentbot o
un'automazione HA corrispondente da approvare, ma l'AI non esegue mai
ragionamento libero multi-fonte in modo ricorrente e non presidiato.

---

## Chatbot — agenti chat

Un Chatbot è definito da:
- **Prompt** — `system_prompt` + `strategic_context` (contesto della casa/famiglia).
- **Scope tool** — `allowed_tools`.
- **Scope entità/servizi** — `allowed_entities`, `allowed_services`, `allowed_endpoints`.
- **Scope memoria** — `knowledge_access` (dati sensibili, quali categorie).
- **Politica di conversazione** — `max_chat_turns`, `require_confirmation`, `response_mode`.
- **Override modello** — `model`, `max_tokens`, `thinking_budget`.

Un Chatbot non ha `trigger`, scheduling né esecuzione autonoma — è a
questo che serve un Agentbot. I costi sono tracciati (`budget_eur` per
Chatbot) ma senza tetto per-Chatbot e senza auto-disable.

### Esempio — Assistente per ospiti

**Obiettivo:** un Chatbot ristretto che gli ospiti possono usare per
controllare luci e temperatura, senza accedere a dati sensibili.

```json
{
  "name": "Assistente Ospiti",
  "system_prompt": "Sei un assistente domotico per gli ospiti. Puoi controllare luci e temperatura della camera ospiti e del soggiorno. Sii sempre cortese e chiedi conferma prima di fare modifiche. Non discutere di costi energetici, abitudini della famiglia o informazioni sulla sicurezza. Se ti chiedono qualcosa al di fuori di luci e temperatura, declina gentilmente.",
  "strategic_context": "Camera ospiti: light.camera_ospiti, climate.camera_ospiti. Soggiorno: light.soggiorno, climate.soggiorno.",
  "allowed_tools": ["get_entity_states", "call_ha_service"],
  "allowed_entities": ["light.camera_ospiti", "light.soggiorno", "climate.camera_ospiti", "climate.soggiorno"],
  "allowed_services": ["light.*", "climate.set_temperature"],
  "restrict_to_home": true,
  "require_confirmation": true,
  "model": "auto"
}
```

**Esempio conversazione:**
```
Ospite: "Puoi abbassare la luce della camera al 40%?"
HIRIS:  "Imposto la luce della camera ospiti al 40%. Confermo?"
Ospite: "Sì"
HIRIS:  "Fatto — luce camera ospiti al 40%."

Ospite: "Quanto paga di bolletta il proprietario?"
HIRIS:  "Sono configurato solo per luci e temperatura. Per altre domande,
         chiedi al proprietario di casa."
```

### Esempio — Controllo multi-stanza con un messaggio

**Obiettivo:** usare un Chatbot per controllare più stanze con un singolo
comando in linguaggio naturale.

```
Tu:    "Fa freddo, porta tutti i termostati a 21 gradi"
HIRIS: [chiama get_entities_by_domain("climate")]
HIRIS: "Ho trovato 4 termostati: soggiorno (attuale 19°C), cucina (20°C),
        camera matrimoniale (18°C), camera ospiti (17°C). Li imposto tutti a 21°C..."
        [chiama call_ha_service per ogni termostato]
HIRIS: "Fatto — 4 termostati impostati a 21°C. Camera matrimoniale e camera ospiti
        impiegheranno più tempo a scaldarsi (più distanti dal target)."

Tu:    "La camera ospiti lasciala a 18, è vuota"
HIRIS: [chiama call_ha_service per climate.camera_ospiti con temperature: 18]
HIRIS: "Camera ospiti aggiornata a 18°C. Gli altri tre rimangono a 21°C."
```

### Esempio — chiedere un riepilogo su richiesta (ex "Briefing mattutino")

**Obiettivo:** ottenere lo stesso tipo di riepilogo che un Agentbot non può
produrre da solo (vedi sopra), chiedendolo esplicitamente a un Chatbot.

```
Tu:    "Dammi il riepilogo energetico di ieri e il meteo di oggi"
HIRIS: [chiama get_energy_history(days=1), get_weather_forecast(hours=12)]
HIRIS: "Ieri: 18,2 kWh consumati, 12,4 kWh prodotti (solare ha coperto il 68%).
        Oggi: parzialmente nuvoloso, 14→22°C."
```

A differenza di un Agentbot pianificato, questa richiesta va posta quando
serve — non gira da sola a un orario fisso. Se lo vuoi ogni mattina, chiedilo
al Brain: può proporti di trasformarlo in un Agentbot ricorrente una volta
notato il pattern, nei limiti di ciò che un Agentbot può davvero valutare
(un trigger a pianificazione, un'azione notify dichiarata, nessuna lettura
live multi-fonte).

---

## Consigli per configurare Agentbot e Chatbot

**Il proattivo si tara o si dichiara, non si prompta:** i detector/situazioni
built-in non si programmano scrivendo un prompt — si abilitano e si tarano
(entità, soglie) dalla pagina `#/agentbots`. L'*azione* di un Agentbot
personalizzato è sempre dichiarata esplicitamente in configurazione; il suo
ragionamento opzionale giudica solo verdict/severity/message.

**Non sai se ti serve un Chatbot o un Agentbot?** Parti da `#/nuovo` e
descrivi l'obiettivo in linguaggio naturale — HIRIS suggerisce il tipo
giusto con un'euristica deterministica (nessuna chiamata LLM), e puoi sempre
correggerla.

**Sii esplicito nel prompt di un Chatbot:** invece di "dimmi se qualcosa non
va", scrivi "dimmi se il consumo supera 3kW".

**Dai contesto sulla tua casa:** includi gli entity ID, i valori tipici, gli
orari della famiglia in `strategic_context`. Claude usa questo per calibrare
le risposte.

**Usa `require_confirmation` per azioni irreversibili:** qualsiasi Chatbot
che controlla riscaldamento, elettrodomestici o sicurezza dovrebbe averlo
abilitato. È un'istruzione al modello, non un blocco tecnico: non sostituisce
il semaforo, che è l'argine che regge da solo su `call_ha_service`,
`trigger_automation`, `toggle_automation` e `set_input_helper`. Unica
eccezione, `create_ha_config`: il semaforo non lo copre, quindi lì questa
conferma è l'unico passaggio prima dell'effetto. Impostalo insieme ai tier.

**Restringi lo scope:** `allowed_tools`/`allowed_entities`/`allowed_services`
più stretti possibile per ogni Chatbot — soprattutto per assistenti condivisi
con ospiti.
