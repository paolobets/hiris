# HIRIS — Casi d'uso ed esempi

> Versione: 0.6.7 · Aggiornato: 2026-04-28

Questo documento contiene configurazioni reali di HIRIS con YAML completo degli agenti, conversazioni di esempio e setup step-by-step per ogni scenario.

---

## 1. Briefing mattutino

**Obiettivo:** Ogni mattina alle 7:00 ricevere un riepilogo dei consumi di ieri, il meteo di oggi e le eventuali anomalie della notte.

**Tipo agente:** Preventive (cron schedulato)

**Configurazione:**
```json
{
  "name": "Briefing Mattutino",
  "type": "preventive",
  "trigger": {
    "type": "preventive",
    "cron": "0 7 * * *"
  },
  "system_prompt": "Sei un agente di briefing quotidiano. Ogni mattina recupera i dati energetici di ieri, le previsioni meteo per le prossime 12 ore e qualsiasi evento insolito della notte (porte lasciate aperte, consumi anomali). Scrivi un briefing conciso in 3-4 righe, adatto a una notifica push. Concludi con un suggerimento pratico per la giornata.",
  "strategic_context": "Casa di famiglia, 4 persone, pannelli solari 6kWp, pompa di calore per riscaldamento e acqua calda.",
  "allowed_tools": ["get_energy_history", "get_weather_forecast", "get_home_status", "send_notification"],
  "model": "auto",
  "actions": [
    {
      "type": "notify",
      "channel": "ha_push",
      "message": "{{result}}"
    }
  ]
}
```

**Esempio output (notifica):**
```
☀️ Buongiorno! Ieri: 18,2 kWh consumati, 12,4 kWh prodotti (solare ha coperto il 68%).
Oggi: parzialmente nuvoloso, 14→22°C. Previsione solare moderata dalle 10:00.
Nessuna anomalia notturna.
💡 Consiglio: fai girare la lavastoviglie tra le 11:00 e le 14:00 per massimizzare l'autoconsumo solare.
```

---

## 2. Rilevamento anomalie energetiche

**Obiettivo:** Rilevare consumi insoliti e avvisare prima che arrivi la bolletta.

**Tipo agente:** Monitor (periodico)

**Configurazione:**
```json
{
  "name": "Monitor Energia",
  "type": "monitor",
  "trigger": {
    "type": "schedule",
    "interval_minutes": 20
  },
  "system_prompt": "Sei un agente di monitoraggio energetico. Controlla il consumo attuale della casa. Confrontalo con l'orario e i pattern tipici (descritti nel contesto). Segnala ANOMALIA se: il consumo totale supera 3kW quando nessuno dovrebbe cucinare; lavatrice o lavastoviglie attive dopo mezzanotte; qualsiasi elettrodomestico con consumo superiore all'atteso. Rispondi con VALUTAZIONE: OK se nulla di insolito, VALUTAZIONE: ANOMALIA se serve intervento.",
  "strategic_context": "Consumo notturno normale (23:00-07:00): 200-400W (frigo + standby). Diurno normale: 400-1200W. Picchi cottura: 1500-3500W per 20-40 minuti.",
  "allowed_tools": ["get_home_status", "get_entities_by_domain", "get_energy_history"],
  "allowed_entities": ["sensor.*potenza*", "sensor.*energia*", "switch.*"],
  "model": "auto",
  "trigger_on": ["ANOMALIA"],
  "actions": [
    {
      "type": "notify",
      "channel": "ha_push",
      "message": "⚡ Anomalia energetica: {{result}}"
    }
  ]
}
```

**Esempio notifica:**
```
⚡ Anomalia energetica: sono le 02:30 e la casa assorbe 1,8 kW.
La lavatrice (1,4 kW) è in funzione da 2h 15min — insolito a quest'ora.
Totale attuale: 1,8 kW vs atteso 350 W.
```

---

## 3. Porta lasciata aperta

**Obiettivo:** Quando la porta d'ingresso è aperta da più di 5 minuti, verificare il contesto e notificare se necessario.

**Tipo agente:** Reactive (state_changed)

**Configurazione:**
```json
{
  "name": "Monitor Porta",
  "type": "reactive",
  "trigger": {
    "type": "state_changed",
    "entity_id": "binary_sensor.porta_ingresso"
  },
  "system_prompt": "Lo stato della porta d'ingresso è appena cambiato. Se si è aperta: controlla da quanto è aperta, verifica se c'è qualcuno in casa tramite i sensori di presenza, controlla se è un'ora insolita (tra le 23:00 e le 07:00). Notifica solo se la porta è aperta da più di 5 minuti E nessuno è rilevato dentro OPPURE è notte. Se la porta si è appena chiusa, nessuna azione necessaria.",
  "strategic_context": "Porta ingresso: binary_sensor.porta_ingresso. Sensori presenza: binary_sensor.pir_ingresso, binary_sensor.pir_salotto, binary_sensor.pir_cucina.",
  "allowed_tools": ["get_entity_states", "send_notification"],
  "allowed_entities": ["binary_sensor.porta_ingresso", "binary_sensor.pir_*"],
  "require_confirmation": false,
  "model": "auto",
  "trigger_on": ["ANOMALIA"],
  "actions": [
    {
      "type": "notify",
      "channel": "ha_push",
      "message": "🚪 {{result}}"
    }
  ]
}
```

**Esempio notifica:**
```
🚪 La porta d'ingresso è aperta da 8 minuti.
Nessun movimento rilevato in casa negli ultimi 15 minuti.
Ora attuale: 23:42. Situazione insolita — verificare.
```

---

## 4. Pre-riscaldamento anticipato

**Obiettivo:** Ogni pomeriggio, controlla le previsioni e avvia il riscaldamento in anticipo se farà freddo al rientro.

**Tipo agente:** Preventive (cron)

**Configurazione:**
```json
{
  "name": "Pre-riscaldamento",
  "type": "preventive",
  "trigger": {
    "type": "preventive",
    "cron": "30 16 * * 1-5"
  },
  "system_prompt": "Sono le 16:30 di un giorno feriale. La famiglia rientra tipicamente verso le 18:30. Controlla le previsioni meteo per le 18:00-19:00. Se la temperatura esterna sarà sotto 10°C e il termostato del soggiorno è in modalità 'away' o 'off', attiva il riscaldamento ora così la casa è calda all'arrivo. Imposta il soggiorno a 21°C. Se già in riscaldamento o temperatura mite (>15°C fuori), nessuna azione.",
  "strategic_context": "Termostato soggiorno: climate.soggiorno. Modalità assenza setpoint: 17°C. Setpoint comfort: 21°C.",
  "allowed_tools": ["get_weather_forecast", "get_entity_states", "call_ha_service"],
  "allowed_entities": ["climate.soggiorno", "climate.*"],
  "allowed_services": ["climate.*"],
  "model": "auto"
}
```

**Cosa succede:** alle 16:30 HIRIS controlla le previsioni delle 18:00. Se sono 8°C chiama `climate.set_temperature` e `climate.set_hvac_mode` automaticamente. Nessuna notifica a meno che non intervenga.

---

## 5. Controllo sicurezza notturno

**Obiettivo:** Ogni sera alle 23:00, verificare che porte e finestre siano chiuse e che non accada nulla di insolito.

**Tipo agente:** Preventive (cron)

**Configurazione:**
```json
{
  "name": "Sicurezza Notturna",
  "type": "preventive",
  "trigger": {
    "type": "preventive",
    "cron": "0 23 * * *"
  },
  "system_prompt": "Sono le 23:00. Esegui un controllo di sicurezza notturno: 1) elenca tutte le porte e finestre attualmente aperte. 2) verifica se ci sono luci esterne ancora accese. 3) controlla se l'allarme è inserito. Scrivi un report di sicurezza breve. Se tutto è ok, dillo in una riga. Se c'è qualcosa da segnalare, elencalo chiaramente.",
  "strategic_context": "Sensori porta/finestra: binary_sensor.porta_ingresso, binary_sensor.porta_retro, binary_sensor.finestra_cucina, binary_sensor.finestra_camera. Luci esterne: light.giardino, light.garage.",
  "allowed_tools": ["get_entities_by_domain", "get_entity_states", "send_notification"],
  "allowed_entities": ["binary_sensor.*porta*", "binary_sensor.*finestra*", "light.giardino", "light.garage"],
  "model": "auto",
  "trigger_on": ["ANOMALIA", "ATTENZIONE"],
  "actions": [
    {
      "type": "notify",
      "channel": "ha_push",
      "message": "🔒 {{result}}"
    }
  ]
}
```

**Esempio notifica quando qualcosa è aperto:**
```
🔒 Controllo notturno — attenzione richiesta:
• Finestra cucina: APERTA
• Luce giardino: ACCESA (dimenticata)
Tutto il resto a posto. Allarme: inserito.
```

---

## 6. Agente chat per ospiti

**Obiettivo:** Un agente chat ristretto che gli ospiti possono usare per controllare luci e temperatura, senza accedere a dati sensibili.

**Tipo agente:** Chat

**Configurazione:**
```json
{
  "name": "Assistente Ospiti",
  "type": "chat",
  "trigger": { "type": "manual" },
  "system_prompt": "Sei un assistente domotico per gli ospiti. Puoi controllare luci e temperatura della camera ospiti e del soggiorno. Sii sempre cortese e chiedi conferma prima di fare modifiche. Non discutere di costi energetici, abitudini della famiglia o informazioni sulla sicurezza. Se ti chiedono qualcosa al di fuori di luci e temperatura, declina gentilmente.",
  "strategic_context": "Camera ospiti: light.camera_ospiti, climate.camera_ospiti. Soggiorno: light.soggiorno, climate.soggiorno.",
  "allowed_tools": ["get_entity_states", "call_ha_service"],
  "allowed_entities": ["light.camera_ospiti", "light.soggiorno", "climate.camera_ospiti", "climate.soggiorno"],
  "allowed_services": ["light.*", "climate.set_temperature"],
  "restrict_to_home": true,
  "require_confirmation": true,
  "budget_eur_limit": 1.00,
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

---

## 7. Ottimizzatore autoconsumo solare

**Obiettivo:** Quando la produzione solare è alta, avviare automaticamente gli elettrodomestici ad alto consumo.

**Tipo agente:** Reactive (state_changed sul sensore solare)

**Configurazione:**
```json
{
  "name": "Ottimizzatore Solare",
  "type": "reactive",
  "trigger": {
    "type": "state_changed",
    "entity_id": "sensor.fotovoltaico"
  },
  "system_prompt": "La produzione solare è cambiata. Controlla produzione attuale (W) e consumo attuale (W). Calcola il surplus netto (produzione - consumo). Se surplus > 1500W: controlla se lo scaldabagno (switch.scaldabagno) è spento — se sì, accendilo per usare l'energia gratuita. Se il surplus scende sotto 500W: spegni lo scaldabagno per evitare di importare dalla rete. Agisci solo se la variazione di surplus è significativa (>300W rispetto all'ultimo stato).",
  "strategic_context": "Solare: sensor.fotovoltaico. Scambio rete: sensor.potenza_rete (positivo = importo, negativo = esporto). Scaldabagno: switch.scaldabagno (1800W quando acceso).",
  "allowed_tools": ["get_entity_states", "call_ha_service"],
  "allowed_entities": ["sensor.fotovoltaico", "sensor.potenza_rete", "switch.scaldabagno"],
  "allowed_services": ["switch.turn_on", "switch.turn_off"],
  "model": "auto"
}
```

---

## 8. Controllo multi-stanza con un messaggio

**Obiettivo:** Usare l'agente chat per controllare più stanze con un singolo comando in linguaggio naturale.

**Esempio conversazione:**
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

---

## Consigli per scrivere system prompt efficaci

**Sii esplicito sulle condizioni:** invece di "notifica se qualcosa non va", scrivi "notifica se il consumo supera 3kW tra le 23:00 e le 07:00".

**Dai contesto sulla tua casa:** includi gli entity ID, i valori di consumo tipici, gli orari della famiglia. Claude usa questo per calibrare il ragionamento.

**Definisci il formato di output per i monitor:** termina sempre i prompt dei monitor con il formato richiesto `VALUTAZIONE: OK|ATTENZIONE|ANOMALIA` — è quello che gestisce l'action chaining.

**Usa `require_confirmation` per azioni irreversibili:** qualsiasi agente che controlla riscaldamento, elettrodomestici o sicurezza dovrebbe averlo abilitato.

**Imposta sempre un budget:** anche un limite di 5 EUR/mese per ogni agente previene costi imprevisti da bug o comportamenti inattesi.
