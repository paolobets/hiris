# HIRIS — Casi d'uso ed esempi

> Versione: 0.33.0 · Aggiornato: 2026-07-24

A partire da questa versione HIRIS ragiona sulla casa in due soli modi:

- **Sentinella** — il livello proattivo. Un set fisso di **lenti** built-in
  (detector/situazioni), ciascuna abilitabile e tarabile singolarmente
  (selettore entità + soglie) dalla pagina di configurazione Sentinella. Non
  esistono più agenti autonomi con prompt, regole (`rules`) e stati (`states`)
  personalizzati: quando una lente rileva qualcosa, un reasoner LLM
  single-shot valuta il segnale e — filtrato dal semaforo di sicurezza — può
  notificare e/o suggerire un'unica azione a basso rischio.
- **Personas** — la chat. Una Persona è una configurazione (prompt, scope
  tool/entità/servizi, scope memoria, politica di conversazione) usata su
  richiesta dall'utente; non ha scheduling proprio.

Le **lenti definite dall'utente** (trigger e prompt personalizzati, per
coprire scenari oltre i built-in) sono previste in una versione successiva —
non in questa.

Questo documento raccoglie esempi realistici per entrambi i livelli.

---

## Sentinella — lenti built-in

| Lente | Cosa rileva | Parametri tarabili |
|---|---|---|
| `opening` | Porta/finestra aperta oltre una soglia | entità, minuti |
| `fridge_temp` | Temperatura frigo/freezer fuori soglia per troppo tempo | entità, °C max, durata min |
| `power` | Consumo istantaneo sopra soglia | entità, watt max |
| `battery` | Batteria di un sensore/dispositivo sotto soglia | entità, % minima |
| `hot_and_away` | Fa caldo fuori e non c'è nessuno in casa | sensore temp. esterna, soglia °C, entità valvola/relè, minuti di funzionamento, salta se pioggia prevista |
| `evening_arrival` | Rientro serale (presenza torna a `on` di sera) | entità presenza, entità scena/target, entità sole, ora dopo cui è "sera" |

Ogni lente segue lo stesso schema: **detector/situazione → segnale →
reasoner (Claude Haiku di default) → semaforo → notifica e/o azione**. Non
c'è un system prompt da scrivere: il reasoner della Sentinella ha un prompt
fisso, condiviso da tutte le lenti, e risponde sempre con lo stesso schema
JSON interno (`verdict`, `severity`, `message`, `action`) — non più con la
sintassi `VALUTAZIONE:`/`AZIONI:` di prima.

### Esempio — lente `opening` (ex "Porta lasciata aperta")

**Obiettivo:** essere avvisati se la porta d'ingresso resta aperta troppo a lungo.

**Configurazione (pagina Sentinella):**
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
oltre la soglia, la Sentinella sveglia il reasoner, che valuta il contesto e
— se lo ritiene opportuno — notifica.

```
🚪 La porta d'ingresso è aperta da 12 minuti.
```

### Esempio — lente `power` (ex "Rilevamento anomalie energetiche")

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

**Cosa succede:** quando `sensor.potenza_rete` supera 3000 W, la Sentinella
valuta il segnale e notifica se lo ritiene un'anomalia:
```
⚡ Consumo anomalo: 3.8 kW alle 02:30.
```

### Esempio — lente `hot_and_away` (ex "Pianificatore irrigazione intelligente")

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

**Cosa succede:** ogni volta che la Sentinella osserva lo snapshot periodico
della casa, se la temperatura esterna supera 32°C, in casa non c'è nessuno e
non è prevista pioggia, propone di accendere `switch.irrigazione_prato` per 5
minuti.

**Nota — non è più il pianificatore multi-zona di prima:** questa lente
valuta un'unica soglia/relè con una singola decisione, non un piano per-zona
con durate calcolate dal modello su piogge/umidità/orientamento di ogni
aiuola. Quel livello di ragionamento personalizzato richiede prompt e trigger
su misura — cioè le **lenti definite dall'utente**, non ancora disponibili
in questa versione.

### Cosa non è più disponibile come agente autonomo

I vecchi agenti "monitor/reattivi/preventivi" con prompt, regole e stati
personalizzati sono stati ritirati insieme alla loro macchina di esecuzione.
Casi come "briefing mattutino automatico alle 7:00", "pre-riscaldamento in
base alle previsioni", "ottimizzatore autoconsumo solare" o "controllo di
sicurezza notturno combinato" non hanno oggi un equivalente autonomo: il
livello proattivo copre solo le lenti built-in sopra. Puoi comunque ottenere
lo stesso risultato **su richiesta**, chiedendolo a una Persona in chat (vedi
sotto). Le lenti definite dall'utente, quando arriveranno, colmeranno questo
divario per gli scenari ricorrenti.

---

## Personas — agenti chat

Una Persona è definita da:
- **Prompt** — `system_prompt` + `strategic_context` (contesto della casa/famiglia).
- **Scope tool** — `allowed_tools`.
- **Scope entità/servizi** — `allowed_entities`, `allowed_services`, `allowed_endpoints`.
- **Scope memoria** — `knowledge_access` (dati sensibili, quali categorie).
- **Politica di conversazione** — `max_chat_turns`, `require_confirmation`, `response_mode`.
- **Override modello** — `model`, `max_tokens`, `thinking_budget`.

Non esistono più `type`, `triggers`, `action_mode`, `rules`, `states` né
`budget_eur_limit`: una Persona non ha scheduling né esecuzione autonoma, e i
costi sono tracciati ma senza tetto per-persona (nessun auto-disable).

### Esempio — Assistente per ospiti

**Obiettivo:** una Persona ristretta che gli ospiti possono usare per
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

**Obiettivo:** usare una Persona per controllare più stanze con un singolo
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

**Obiettivo:** ottenere lo stesso tipo di riepilogo che prima girava da solo
ogni mattina, ora chiedendolo esplicitamente a una Persona.

```
Tu:    "Dammi il riepilogo energetico di ieri e il meteo di oggi"
HIRIS: [chiama get_energy_history(days=1), get_weather_forecast(hours=12)]
HIRIS: "Ieri: 18,2 kWh consumati, 12,4 kWh prodotti (solare ha coperto il 68%).
        Oggi: parzialmente nuvoloso, 14→22°C."
```

A differenza del vecchio agente cron, questa richiesta va posta quando serve
— non gira più autonomamente a un orario fisso.

---

## Consigli per configurare Sentinella e Personas

**Per il proattivo, taratura non prompt:** le lenti della Sentinella non si
programmano scrivendo un prompt — si abilitano e si tarano (entità, soglie)
dalla pagina Sentinella. Non serve (e non è più possibile) scrivere
`VALUTAZIONE:` o definire `rules`/`states` personalizzati.

**Sii esplicito nel prompt di una Persona:** invece di "dimmi se qualcosa non
va", scrivi "dimmi se il consumo supera 3kW".

**Dai contesto sulla tua casa:** includi gli entity ID, i valori tipici, gli
orari della famiglia in `strategic_context`. Claude usa questo per calibrare
le risposte.

**Usa `require_confirmation` per azioni irreversibili:** qualsiasi Persona che
controlla riscaldamento, elettrodomestici o sicurezza dovrebbe averlo
abilitato.

**Restringi lo scope:** `allowed_tools`/`allowed_entities`/`allowed_services`
più stretti possibile per ogni Persona — soprattutto per assistenti condivisi
con ospiti.
