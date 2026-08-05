/* HIRIS · Designer · templates + tool/action catalogs
   TEMPLATES seeds the f-template dropdown (prompt + strategic_context only —
   Task 4/Slice 5 dropped the agent-type/trigger/states preset fields along
   with the action/trigger machinery).
   TOOLS, ACTIONS feed HirisEditorKit.checkGroup (config/editor-kit.js,
   SP-4 Fase B Task 3 — prima buildToolChecks/buildActionChecks in permessi.js). */

var TEMPLATES = [
  {
    id: 'energy-solar',
    label: 'Monitor Energia Solare',
    strategic: 'SISTEMA ENERGETICO:\nUsa get_home_status() per elencare le entità disponibili, poi individua fra i risultati (dal nome):\n- il sensore di produzione fotovoltaica\n- la percentuale di carica della batteria\n- il consumo totale di potenza della casa\n- il sensore di importazione dalla rete elettrica\n\nSOGLIE:\n- Importazione > 100W sostenuta: stai comprando energia — avvisa\n- Batteria < 15%: livello critico — avvisa\n- Surplus solare > 300W: momento ottimale per carichi\n\nCARICHI DIFFERIBILI: lavatrice, lavastoviglie, forno elettrico\nPICCO SOLARE: tipicamente 10:00-14:00',
    prompt: 'Quando ti chiedo dello stato energetico, controlla produzione solare, batteria e consumo casa. Segnalami se c\'è importazione dalla rete o la batteria è scarica, e suggeriscimi quando conviene avviare un carico differibile in caso di surplus solare.',
  },
  {
    id: 'security',
    label: 'Sicurezza Casa',
    strategic: 'SENSORI:\n- Porte/finestre/movimento: get_home_status(), individua i sensori del dominio "binary_sensor" dal nome o dal device_class (door, window, motion)\n- Persone in casa: person.* (state="home" = presente)\n\nREGOLE:\n- Porta/finestra aperta oltre 30 min: notifica\n- Movimento con nessuno in casa: notifica urgente\n- Controlla presenze con get_home_status() prima di agire',
    prompt: 'Quando ti chiedo della sicurezza in casa, controlla porte, finestre e sensori di movimento, e segnalami eventuali anomalie.',
  },
  {
    id: 'family-presence',
    label: 'Presenza Famiglia',
    strategic: 'PERSONE:\n- Tracker: get_home_status(), cerca fra i risultati le entità person.* — state="home" significa in casa\n\nAZIONI TIPICHE:\n- Arrivo: pre-riscalda climate, accendi luci benvenuto\n- Partenza: spegni climate, luci off, verifica serrature\n\nABITUDINI:\n- Rientro tipico: [modifica qui]\n- Temperatura preferita: [modifica qui, es. 21°C diurno / 18°C notturno]',
    prompt: 'Quando ti chiedo di chi è in casa, controlla le presenze e suggeriscimi le regolazioni di riscaldamento e luci più adatte in base agli arrivi o alle partenze.',
  },
  {
    id: 'climate',
    label: 'Monitor Clima',
    strategic: 'TERMOSTATI: get_home_status(), cerca fra i risultati le entità climate.*\nMETEO: get_weather_forecast(hours=24) — se questo strumento non è fra quelli disponibili, usa i sensori meteo di Home Assistant\n\nPREFERENCE:\n- Temperatura diurna: [es. 21°C]\n- Temperatura notturna: [es. 18°C]\n- Orario diurno: 07:00-23:00\n\nREGOLE:\n- Non riscaldare con finestre aperte (get_home_status(), cerca i sensori finestra)\n- Anticipa riscaldamento di 30 min rispetto al rientro\n- In estate: preferisci ventilazione naturale a condizionamento',
    prompt: 'Quando ti chiedo del clima in casa, confronta la temperatura attuale con quella preferita e suggeriscimi le regolazioni più adatte per il riscaldamento, segnalando eventuali anomalie (es. finestre aperte col riscaldamento acceso).',
  },
  {
    id: 'irrigation',
    label: 'Irrigazione Giardino',
    strategic: 'ZONE DI IRRIGAZIONE:\n[Descrivi qui le zone — usa valve.* se disponibile (HA 2023.9+), altrimenti switch.*]\n[Es. "Prato nord" valve.irrigazione_prato_nord, "Aiuole" valve.irrigazione_aiuole]\n[Indica posizione e tipo di terreno: es. "Prato nord — terreno argilloso, esposizione sole pieno"]\n\nSENSOR METEO:\n- Pioggia recente: get_home_status(), cerca un sensore di pioggia o precipitazione\n- Umidità suolo: nello stesso elenco, cerca un sensore di umidità per ogni zona se disponibile\n- Meteo: get_weather_forecast(hours=48) per previsioni 2 giorni — se questo strumento non è fra quelli disponibili, usa i sensori meteo di Home Assistant\n\nSTATI IRRIGAZIONE:\n- SKIP: ha piovuto abbastanza o previste piogge significative oggi/domani\n- LEGGERA: irrigazione breve (10-15 min per zona) — condizioni borderline\n- PIENA: irrigazione completa (20-30 min per zona) — terreno asciutto, nessuna pioggia prevista\n\nSOGLIE PIOGGIA:\n- Pioggia passata 24h > 5mm: SKIP\n- Pioggia passata 48h > 10mm: SKIP o LEGGERA\n- Previsione pioggia oggi > 3mm: SKIP\n- Previsione pioggia domani > 5mm: considera LEGGERA invece di PIENA',
    prompt: 'Quando ti chiedo se irrigare il giardino, controlla le precipitazioni degli ultimi giorni con get_entity_states sui sensori pioggia, le previsioni meteo con get_weather_forecast(hours=48), e l\'umidità del suolo se disponibile.\n\nPer ogni zona suggeriscimi una durata in minuti (0 = salta), motivando brevemente la scelta (SKIP / irrigazione leggera / completa).\n\nEsegui l\'irrigazione solo se te lo chiedo esplicitamente, chiamando il servizio Home Assistant sulla valvola/switch della zona indicata (valve: service=open_valve poi close_valve; switch: service=turn_on poi turn_off), una zona alla volta per non sovraccaricare la pompa.',
  },
];

function populateTemplateSelector() {
  var sel = document.getElementById('f-template');
  if (!sel || sel.options.length > 1) return;
  TEMPLATES.forEach(function(t) {
    var opt = document.createElement('option');
    opt.value = t.id;
    opt.textContent = t.label;
    sel.appendChild(opt);
  });
  sel.addEventListener('change', function(e) {
    var id = e.target.value;
    if (!id) return;
    var tpl = TEMPLATES.filter(function(x) { return x.id === id; })[0];
    if (!tpl) return;
    document.getElementById('f-strategic').value = tpl.strategic || '';
    document.getElementById('f-prompt').value = tpl.prompt || '';
    e.target.value = '';
  });
}

var TOOLS = [
  { id: 'get_entity_states',      label: 'get_entity_states',      desc: 'Legge stato entità HA (luce, clima, sensori…)' },
  { id: 'get_home_status',        label: 'get_home_status',        desc: 'Panoramica compatta di tutti i dispositivi utili' },
  { id: 'get_entities_on',        label: 'get_entities_on',        desc: 'Tutti i dispositivi attualmente accesi' },
  { id: 'get_entities_by_domain', label: 'get_entities_by_domain', desc: 'Tutte le entità di un dominio (es. light, sensor)' },
  { id: 'get_area_entities',      label: 'get_area_entities',      desc: 'Scopre stanze/aree e i dispositivi associati' },
  { id: 'get_history',            label: 'get_history',            desc: 'Storico di un\'entità: andamento nel tempo, min/max/media' },
  { id: 'get_energy_history',     label: 'get_energy_history',     desc: 'Storico consumi energetici' },
  { id: 'get_weather_forecast',   label: 'get_weather_forecast',   desc: 'Previsioni meteo (Open-Meteo)' },
  { id: 'call_ha_service',        label: 'call_ha_service',        desc: 'Chiama un servizio HA (luci, clima, switch…)' },
  { id: 'send_notification',      label: 'send_notification',      desc: 'Invia notifica (HA push / Telegram / RetroPanel)' },
  { id: 'get_ha_automations',     label: 'get_ha_automations',     desc: 'Elenco automazioni HA' },
  { id: 'get_automation_config',  label: 'get_automation_config',  desc: 'Legge la configurazione completa di un\'automazione HA' },
  { id: 'trigger_automation',     label: 'trigger_automation',     desc: 'Avvia un\'automazione HA' },
  { id: 'toggle_automation',      label: 'toggle_automation',      desc: 'Abilita/disabilita automazione HA' },
  { id: 'create_task',            label: 'create_task',            desc: 'Pianifica un task differito (promemoria, notifica, azione a orario)' },
  { id: 'list_tasks',             label: 'list_tasks',             desc: 'Elenca i task pianificati e il loro stato' },
  { id: 'cancel_task',            label: 'cancel_task',            desc: 'Annulla un task pianificato non ancora eseguito' },
  { id: 'get_calendar_events',    label: 'get_calendar_events',    desc: 'Prossimi eventi dai calendari HA' },
  { id: 'create_calendar_event',  label: 'create_calendar_event',  desc: 'Crea un evento su un calendario HA' },
  { id: 'set_input_helper',       label: 'set_input_helper',       desc: 'Imposta un input helper HA (boolean, number, text, select)' },
  { id: 'recall_memory',          label: 'recall_memory',          desc: 'Cerca in cio\' che HIRIS ricorda: preferenze, fatti, scadenze, spese, appunti' },
  { id: 'save_memory',            label: 'save_memory',            desc: 'Salva subito qualcosa da ricordare (preferenza, fatto, scadenza, spesa, appunto), senza approvazione' },
  { id: 'get_ha_health',          label: 'get_ha_health',          desc: 'Report di salute del sistema Home Assistant (entità non disponibili, integrazioni, log, aggiornamenti)' },
  { id: 'get_advisories',         label: 'get_advisories',         desc: 'Segnalazioni di salute aperte rilevate dal Brain' },
  { id: 'get_logbook',            label: 'get_logbook',            desc: 'Cronologia eventi: cosa è successo e chi ha fatto cosa' },
  { id: 'render_template',        label: 'render_template',        desc: 'Valuta un template Jinja di HA (diagnosi). Legge tutta la casa: la lista di entità concesse al bot non si applica. Solo bot di chat' },
  { id: 'create_automation_proposal', label: 'create_automation_proposal', desc: 'Propone una nuova automazione HA o agente HIRIS (richiede approvazione dell\'utente)' },
  { id: 'create_ha_config',       label: 'create_ha_config',       desc: 'Crea uno script o una scena HA, applicati subito' },
  { id: 'list_dashboards',        label: 'list_dashboards',        desc: 'Elenca le plance (dashboard Lovelace) esistenti' },
  { id: 'get_dashboard_config',   label: 'get_dashboard_config',   desc: 'Legge viste e card di una plancia esistente' },
  { id: 'propose_dashboard',      label: 'propose_dashboard',      desc: 'Propone di creare o sostituire una plancia (approvazione dalle Proposte)' },
  { id: 'daily_briefing',         label: 'daily_briefing',         desc: 'Riepilogo del maggiordomo: scadenze imminenti e stato notevole della casa' },
  { id: 'confirm_pending',        label: 'confirm_pending',        desc: 'Conferma un\'azione a rischio in attesa con il codice OTP ricevuto sul telefono' },
];

var ACTIONS = [
  { id: 'light.*',         label: 'Luci',          desc: 'Accendi, spegni, regola intensità e colore' },
  { id: 'climate.*',       label: 'Clima',          desc: 'Termostati e condizionatori' },
  { id: 'switch.*',        label: 'Switch',         desc: 'Interruttori e prese smart' },
  { id: 'cover.*',         label: 'Tapparelle',     desc: 'Tende, tapparelle e serrande' },
  { id: 'valve.*',         label: 'Valvole',        desc: 'Valvole irrigazione e controllo fluidi' },
  { id: 'notify.*',        label: 'Notifiche',      desc: 'Servizi di notifica push' },
  { id: 'input_boolean.*', label: 'Input Boolean',  desc: 'Toggle e variabili booleane virtuali' },
  { id: 'script.*',        label: 'Script',         desc: 'Esegui script e automazioni personalizzate' },
];

/* KNOWLEDGE_KINDS feeds HirisEditorKit.checkGroup nella sezione Knowledge
   (SP-4 Fase B Task 4, chatbot-editor.js populateKnowledge()). Sono 5 dei 6
   `kind` che save_memory accetta (hiris/app/tools/memory_tools.py
   SAVE_MEMORY_TOOL_DEF.input_schema.properties.kind.enum -- il sesto e'
   'memory', il ricordo generico dell'agente, che non e' un filtro di
   ricerca sul second brain) -- il filtro lato UI deve restare in sincrono
   con ciò che il second brain sa salvare. */
var KNOWLEDGE_KINDS = [
  { id: 'fact',        label: 'Fatti',       desc: 'Informazioni stabili su casa/famiglia' },
  { id: 'preference',  label: 'Preferenze',  desc: 'Abitudini e preferenze personali' },
  { id: 'obligation',  label: 'Scadenze',    desc: 'Impegni e scadenze' },
  { id: 'expense',     label: 'Spese',       desc: 'Spese registrate' },
  { id: 'note',        label: 'Note',        desc: 'Appunti generici' },
];
