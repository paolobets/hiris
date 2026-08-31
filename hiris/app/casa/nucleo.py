"""Il nucleo -- il testo che il modello ha SEMPRE davanti.

E' il punto in cui muore la sovrapposizione n.1 della mappa del prodotto:
la chat riceveva una mappa senza il ritratto, il Brain il ritratto senza
la mappa -- due intelligenze nella stessa casa che ne vedono due diverse
(vedi docs/design/2026-08-05-la-conoscenza-di-hiris.md, §7). Ritratto e
Brain sono usciti per intero nella fetta E3 ("esce la casa vecchia"): oggi
il nucleo e' l'unica rappresentazione della casa rimasta, e resta
**lo stesso per chiunque ragioni**: chat, e un domani Brain e agenti, quando
torneranno con un progetto proprio.

Con trecento entita' elencarle tutte sfonderebbe il contesto a ogni
messaggio: il nucleo CONTA, non elenca -- "Cucina: 2 luci, 1 sensore", non i
loro `entity_id`. L'unica eccezione sono i ricordi: sono pochi, ed e' l'unica
cosa che non si puo' andare a cercare -- se il modello dovesse *ricordarsi*
di cercarli, se ne dimenticherebbe. Entrano interi.

`componi()` e' PURA: prende dati gia' letti dal chiamante (l'anagrafe, il
comportamento, i ricordi, lo stato vivo) e non apre archivi ne' chiama la
rete. E' cio' che la rende verificabile senza finti elaborati -- vedi
tests/test_nucleo.py.

**Un nucleo troncato in silenzio e' un HIRIS che crede di sapere.** Quando il
tetto di caratteri costringe a tagliare, il taglio e' scritto DENTRO il
nucleo (sezione 5, "cio' che HIRIS ignora"), non solo in un riepilogo che
nessuno legge.

La priorita' di taglio NON e' "cosa e' recuperabile": tutto qui dentro lo e',
un ricordo tagliato incluso -- sta in SQLite e si raggiunge con
`guarda("ricordo", id)`, esattamente come un'area o un dispositivo (una
versione precedente di questo commento affermava il contrario: era falso, e
motivava con una bugia una scelta che una ragione vera ha comunque). La
priorita' vera e' "cosa il modello perde la possibilita' di SAPERE che
esiste", perche' il nucleo e' l'unico posto da cui puo' scoprirlo: un
ricordo mai comparso qui non e' uno che il modello sa di dover cercare (vedi
sopra, "entrano interi"), ma la mappa delle aree e' cio' che costa meno per
riga e serve di piu' per orientarsi -- senza, il modello non sa nemmeno quali
stanze esistono, il che e' peggio che non sapere una singola preferenza
detta una volta. Per questo la mappa ha una riserva minima che il taglio non
tocca (`_RISERVA_MINIMA_RIGHE_CASA`), e i ricordi restano l'ultima cosa a
sparire -- non perche' irrecuperabili, ma perche' e' l'unico contenuto per
cui il nucleo e' l'unica via di scoperta.
"""
from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .anagrafe import (
    PROBLEM_SEVERITY,
    actual_class,
    domain_of,
    hierarchy,
    is_pseudo_area,
    name_with_id,
    translate_state,
)
from .domande import sanitized_memories

# Il TIPO di un'entita' si ricava dal dominio del suo entity_id (la parte
# prima del punto) -- lo dichiara Home Assistant nell'id stesso, non un
# elenco nostro. Questa mappa serve solo a renderlo leggibile in italiano
# (singolare, plurale: "1 luce" e non "1 luci" -- il nucleo lo legge anche
# una persona, vedi il brief); un dominio che non conosciamo resta visibile
# col proprio nome invece di sparire, cosi' un tipo nuovo si legge diverso
# ma non si perde.
_DOMAIN_NAMES = {
    # --- le 45 piattaforme dichiarate da Home Assistant ---
    # Copiate da `homeassistant/generated/entity_platforms.py` (l'elenco che HA
    # genera da se'), non ricordate: ognuna e' stata verificata come componente
    # vero del sorgente. Il singolare e il plurale sono DICHIARATI uno per uno
    # perche' l'italiano non fa il plurale aggiungendo una lettera --
    # "aspirapolvere" resta "aspirapolvere", "analisi" resta "analisi" -- e
    # dedurlo produrrebbe "aspirapolveres".
    "ai_task": ("compito IA", "compiti IA"),
    "air_quality": ("qualita' dell'aria", "qualita' dell'aria"),
    "alarm_control_panel": ("pannello allarme", "pannelli allarme"),
    "assist_satellite": ("satellite vocale", "satelliti vocali"),
    "binary_sensor": ("sensore binario", "sensori binari"),
    "button": ("pulsante", "pulsanti"),
    "calendar": ("calendario", "calendari"),
    "camera": ("telecamera", "telecamere"),
    "climate": ("termostato", "termostati"),
    "conversation": ("agente conversazionale", "agenti conversazionali"),
    "cover": ("tapparella", "tapparelle"),
    "date": ("data", "date"),
    "datetime": ("data e ora", "date e ore"),
    "device_tracker": ("localizzatore", "localizzatori"),
    "event": ("evento", "eventi"),
    "fan": ("ventola", "ventole"),
    "geo_location": ("posizione geografica", "posizioni geografiche"),
    "humidifier": ("umidificatore", "umidificatori"),
    "image": ("immagine", "immagini"),
    "image_processing": ("analisi immagine", "analisi immagini"),
    "infrared": ("infrarossi", "infrarossi"),
    "lawn_mower": ("tosaerba", "tosaerba"),
    "light": ("luce", "luci"),
    "lock": ("serratura", "serrature"),
    "media_player": ("lettore multimediale", "lettori multimediali"),
    "notify": ("notificatore", "notificatori"),
    "number": ("numero", "numeri"),
    "radio_frequency": ("radiofrequenza", "radiofrequenze"),
    "remote": ("telecomando", "telecomandi"),
    "scene": ("scena", "scene"),
    "select": ("selettore", "selettori"),
    "sensor": ("sensore", "sensori"),
    "siren": ("sirena", "sirene"),
    "stt": ("riconoscimento vocale", "riconoscimenti vocali"),
    "switch": ("interruttore", "interruttori"),
    "text": ("testo", "testi"),
    "time": ("ora", "ore"),
    "todo": ("lista di cose da fare", "liste di cose da fare"),
    "tts": ("sintesi vocale", "sintesi vocali"),
    "update": ("aggiornamento", "aggiornamenti"),
    "vacuum": ("aspirapolvere", "aspirapolvere"),
    "valve": ("valvola", "valvole"),
    "wake_word": ("parola di attivazione", "parole di attivazione"),
    "water_heater": ("scaldacqua", "scaldacqua"),
    "weather": ("meteo", "meteo"),

    # --- i domini che non sono piattaforme ---
    # Gli helper che l'utente crea dall'interfaccia e le cose che Home
    # Assistant crea da se'. Non stanno nell'elenco generato delle
    # piattaforme, ma esistono come entita' in ogni casa vera -- lasciarli
    # fuori avrebbe fatto stampare "3 input_number" a chiunque usi gli helper.
    "automation": ("automazione", "automazioni"),
    "script": ("script", "script"),
    "person": ("persona", "persone"),
    "zone": ("zona", "zone"),
    "group": ("gruppo", "gruppi"),
    "sun": ("sole", "sole"),
    # "tag" NON e' "etichetta": in HIRIS quella parola significa gia' le label
    # che l'utente scrive in Home Assistant (che ora escono da `guarda` e si
    # cercano). Due significati per la stessa parola nella stessa risposta e'
    # esattamente cio' che la consistenza vieta.
    "tag": ("tag NFC", "tag NFC"),
    "plant": ("pianta", "piante"),
    "counter": ("contatore", "contatori"),
    "timer": ("timer", "timer"),
    "schedule": ("programmazione", "programmazioni"),
    "persistent_notification": ("notifica", "notifiche"),
    "input_boolean": ("interruttore helper", "interruttori helper"),
    "input_number": ("numero helper", "numeri helper"),
    "input_select": ("selettore helper", "selettori helper"),
    "input_text": ("testo helper", "testi helper"),
    "input_datetime": ("data helper", "date helper"),
    "input_button": ("pulsante helper", "pulsanti helper"),
}

# Stati che rendono un'entita' NOTEVOLE adesso: acceso, aperto, in allarme
# SCATTATO. Il resto e' rumore in una casa da trecento entita' -- una
# temperatura di 19.5 non e' notevole solo perche' e' un numero, uno stato
# "on"/"open" lo e' perche' e' un'eccezione rispetto al riposo.
#
# Per l'allarme (`alarm_control_panel`) SOLO "triggered" e' notevole: e'
# l'unico stato che significa "sta succedendo qualcosa adesso". Gli altri
# stati veri di Home Assistant -- "armed_home", "armed_away", "armed_night",
# "armed_vacation", "armed_custom_bypass", "arming", "pending", "disarmed" --
# sono la routine quotidiana (si arma e si disarma piu' volte al giorno,
# come si accende e si spegne una luce): non sono un'eccezione rispetto al
# riposo, sono il riposo. (Il letterale "alarm" che stava qui non era MAI
# stato uno stato reale di Home Assistant: era voce morta che affermava di
# coprire un caso che non copriva.)
# Gli stati ATTIVI dei domini in cui l'attivo e' un'eccezione (vedi
# `_DOMINI_EVENTO`). Non basta piu' un insieme di stringhe: `on` su una luce e
# `on` su un'automazione sono due fatti diversi, e fino alla fetta «il
# vocabolario delle tipologie» erano la stessa riga.
#
# La fonte, stato per stato -- verificata su home-assistant/core il
# 20/08/2026 (ramo `dev`, non un modulo installato: nucleo.py resta PURO,
# vedi il docstring in testa al file):
#   "on"       -- STATE_ON,       homeassistant/const.py
#   "open"     -- STATE_OPEN,     homeassistant/const.py
#   "playing"  -- STATE_PLAYING,  homeassistant/const.py
#   "unlocked" -- LockState.UNLOCKED,   homeassistant/components/lock/const.py
#   "cleaning" -- VacuumActivity.CLEANING, homeassistant/components/vacuum/const.py
# Senza Home Assistant installato non c'e' un enum da importare e confrontare
# a runtime: l'elenco e' ricopiato a mano e pinnato (con lo stesso limite
# dichiarato) in tests/test_vocabolario_tipologie.py. Da riguardare quando
# `_DOMINI_EVENTO` guadagna un dominio nuovo -- porta con se' il proprio
# stato "attivo" da aggiungere qui.
_ACTIVE_STATES = {"on", "open", "unlocked", "playing", "cleaning"}

# I domini in cui l'attivo e' un'ECCEZIONE rispetto al riposo -- cioe' in cui
# «acceso» significa che qualcuno o qualcosa lo ha acceso.
#
# Chi NON c'e', e perche' (misurato sull'impianto del proprietario, 845 entita'):
#   - `automation`/`script`/`input_boolean`: `on` significa ABILITATA. Erano 18,
#     ed erano riposo travestito da eccezione.
#   - `device_tracker`/`person`: `home` e' una CONDIZIONE (un telefono a casa e'
#     il riposo). Erano 49. Non sono esclusi dal prodotto: `guarda` e `cerca` li
#     riportano quando li chiedi -- e' la differenza fra un vocabolario e un
#     filtro, ed e' pinnata in tests/test_vocabolario_tipologie.py.
#   - `sensor`/`number`/`weather`/`sun`: sono MISURE. Un numero non e' un evento.
#   - `button`/`event`/`tag`/`notify`/`image`: non hanno uno stato utile -- 57
#     dei 72 `button` di questa casa sono `unknown` per costruzione.
#
# Ognuno dei dieci e' una piattaforma vera di Home Assistant (sottoinsieme
# dichiarato di `_PIATTAFORME_HA`, la stessa fonte -- homeassistant/generated/
# entity_platforms.py -- copiata in tests/test_vocabolario_domini.py); QUALE
# sottoinsieme merita il trattamento "evento" e' un giudizio del prodotto,
# non qualcosa che HA dichiara da se'. Pinnato in
# tests/test_vocabolario_tipologie.py: da riguardare quando un dominio nuovo
# entra nel prodotto e ha un proprio stato "attivo" degno di annuncio.
_EVENT_DOMAINS = {
    "light", "switch", "cover", "lock", "fan",
    "media_player", "valve", "remote", "siren", "vacuum",
}

# Per `binary_sensor` il dominio non basta: e' la CLASSE a dire se `on` e' un
# allagamento o il corridoio attraversato trenta secondi fa. Qui stanno gli
# allarmi e le aperture; restano fuori i transitori (`motion`, `occupancy`,
# `presence`, `sound`, `vibration`, `light`, `running`, `moving`, `power`,
# `plug`) e la manutenzione (`battery`, `connectivity`, `update`,
# `battery_charging`), che si vanno a chiedere e non si annunciano.
#
# Sottoinsieme DICHIARATO delle classi di
# developers.home-assistant.io/docs/core/entity/binary-sensor/ -- la STESSA
# fonte di `_SIGNIFICATO_CLASSE` in anagrafe.py (verificata il 16/08/2026):
# ogni classe qui elencata deve comparire anche li', altrimenti si leggerebbe
# «acceso» invece del suo significato -- e' l'incoerenza pinnata da
# test_ogni_classe_di_evento_ha_anche_un_significato (sottoinsieme, piu'
# forte di un elenco ricopiato). L'elenco stesso e' pinnato di suo (mutazione:
# toglierne una classe fa rosso) in tests/test_vocabolario_tipologie.py; da
# riguardare quando HA aggiunge una nuova device_class di allarme o apertura.
_EVENT_CLASSES = {
    # allarmi
    "moisture", "smoke", "gas", "carbon_monoxide", "safety", "tamper", "problem",
    "heat", "cold",
    # aperture
    "door", "window", "garage_door", "opening",
}

# Oltre questa quantita' di elementi notevoli, elencarli uno per uno
# sfonderebbe il nucleo tanto quanto elencare le trecento entita' della casa
# (vedi il docstring del modulo): si raggruppa per area, dominio e stato --
# vedi `_raggruppa_notevoli`.
_INDIVIDUAL_HIGHLIGHT_THRESHOLD = 15


# Il buffer riservato alla sezione "cio' che HIRIS ignora": deve poter contenere
# l'avviso di taglio anche quando il taglio e' avvenuto, quindi si sottrae
# dal budget PRIMA di tagliare, non dopo -- altrimenti l'avviso stesso
# rischierebbe di essere cio' che sfonda il tetto. E' un MINIMO, non un
# valore fisso: se le lacune GIA' note (prima ancora di tagliare) pesano
# piu' di questo, il budget per il resto si restringe di conseguenza (vedi
# `componi()`) -- altrimenti l'avviso stesso, cresciuto oltre la stima,
# sarebbe cio' che sfonda il tetto in silenzio (IMPORTANT ④).
_GAP_SECTION_RESERVE = 400

# Quante righe della mappa (`_righe_casa`) il taglio non tocca MAI. E' la
# sezione piu' economica per riga e la piu' utile per orientarsi (vedi
# `componi()`): senza un minimo, con molti ricordi lunghi il taglio la
# svuota per intero PRIMA di toccare un solo ricordo, perche' "casa" viene
# prima di "ricordi" nell'ordine di taglio -- un modello che legge quel
# nucleo non saprebbe piu' quali stanze esistono (IMPORTANT ⑥).
_MIN_HOME_SPACE_LINES_RESERVE = 3

# L'intestazione della sezione dei guasti. E' una domanda a cui l'utente vuole
# una risposta, non una categoria di archivio: «cosa non va» si legge e si
# riferisce, «cio' che HIRIS ignora» si salta.
_FAULTS_HEADING = "## Cosa non va in casa"


# Quanti nomi di dispositivo una riga di conteggio puo' citare prima di
# smettere di CONTARE e cominciare a ELENCARE. **Uno**, e il numero e'
# misurato, non scelto per gusto.
#
# La regola della specifica ("annota quando le entita' contate appartengono a
# MENO dispositivi di quante sono") si spegne davvero da sola sul 75% delle
# righe: una presa, una lampadina, un contatto portano un'entita' per dominio
# e non producono niente. Sul restante 25% pero' NON e' limitata: su una casa
# della forma di quella del proprietario (20 aree, 240 dispositivi, ~1.300
# entita') sono 61 righe annotabili che citerebbero 344 nomi, cioe' 5.294
# caratteri su un tetto di 6.000 -- e quel nucleo tronca gia' oggi. Misurato:
# citando tutti i nomi sopravvivono 7 aree su 20 invece di 17. Citarne uno
# solo costa 174 caratteri e ne fa sopravvivere 16.
#
# Uno e' anche l'unico caso in cui il nome E' l'informazione: "4 valve" che
# sono quattro cose separate non ha bisogno di nessuna annotazione, "4 valve"
# che sono un irrigatore solo ha bisogno di sapersi chiamare. Sopra l'uno il
# nucleo torna a fare quello che dichiara di fare nel docstring del modulo:
# conta, non elenca.
_MAX_DEVICE_NAMES_IN_LINE = 1


def _carriers(area_entities: list[dict], domain: str) -> tuple[list[str], int]:
    """Chi PORTA le entita' di `dominio` in quest'area: gli id dei dispositivi
    distinti, e quante entita' non ne hanno nessuno.

    Le entita' senza dispositivo contano **una a testa**, non zero: sono cose
    separate quanto un dispositivo per una: contarle come zero portatori
    farebbe scattare l'annotazione su una riga che non mente affatto (dieci
    helper `input_boolean` in cucina sono davvero dieci cose).

    Gli id si accumulano in una lista e non in un `set` per la stessa ragione
    per cui `_conta_per_dominio` ordina: l'ordine dev'essere quello
    dell'anagrafe, non quello dell'hash, o due letture della stessa casa
    producono due nuclei diversi."""
    devices: list[str] = []
    without = 0
    for entity in area_entities:
        if domain_of(entity["id"]) != domain:
            continue
        device_id = entity.get("dispositivo_id")
        if not device_id:
            without += 1
        elif device_id not in devices:
            devices.append(device_id)
    return devices, without


def _device_annotation(area_entities: list[dict], domain: str, count: int,
                             device_names: dict[str, str] | None) -> str:
    """Il pezzo fra parentesi da attaccare a «4 valve» -- o "" quando la riga
    non mente per omissione.

    «Esterno: 4 valve» e' vero e distrugge una cosa: non dice se sono quattro
    dispositivi o uno. Quando sono quattro il conteggio e' tutto cio' che
    serve; quando sono un irrigatore solo, la riga ha cancellato l'unica
    informazione che contava -- e il modello, per raggrupparle, dovrebbe
    INDOVINARE di cercare un dispositivo di cui non conosce il nome.

    `nomi_dispositivo` a `None` significa «non ho potuto guardare», non
    «nessun dispositivo»: col registro "dispositivi" caduto la tabella e'
    VUOTA (casa/archivio.py::sostituisci cancella tutto e reinserisce cio'
    che e' arrivato), quindi un dizionario vuoto renderebbe ogni
    `dispositivo_id` un riferimento al nulla e l'annotazione stamperebbe
    "(id: ...)" su tutta la casa. La lacuna e' gia' dichiarata in "cio' che
    HIRIS ignora": qui non si aggiunge un secondo silenzio."""
    if device_names is None:
        return ""
    devices, without = _carriers(area_entities, domain)
    if len(devices) + without >= count:
        # Tante cose quante entita': il conteggio dice gia' tutto.
        return ""
    if without or len(devices) > _MAX_DEVICE_NAMES_IN_LINE:
        # Piu' di un portatore: si conta, non si elenca (vedi la costante).
        # `senza` non nullo con un solo dispositivo e' lo stesso caso visto da
        # un'altra parte -- il nome coprirebbe solo una parte delle entita'
        # contate, e un'annotazione parziale afferma piu' di quel che sa.
        return ""
    if not devices:
        # Irraggiungibile da `_righe_casa`, che conta e raggruppa sulla STESSA
        # lista con lo STESSO `_dominio`: con zero portatori e zero entita'
        # senza dispositivo, `quante` e' zero e il confronto `>= quante` ha gia'
        # deciso. La guardia c'e' lo stesso perche' qui sbagliarsi non costa un
        # conteggio storto: questo testo entra nel prompt di OGNI messaggio,
        # quindi un `IndexError` non degrada il nucleo -- SPEGNE LA CHAT. Un
        # chiamante futuro che passasse un `quante` preso da un'altra parte (un
        # totale d'area, un conteggio precalcolato) qui trova una riga senza
        # annotazione invece di una casa senza assistente.
        return ""
    device_id = devices[0]
    name = (device_names.get(device_id) or "").strip()
    if name:
        return f" ({name})"
    # Un dispositivo senza nome esiste davvero: `casa/archivio.py` scrive
    # `name_by_user or name`, ed entrambi sono nullable. Si mostra l'id
    # MARCATO come id -- la stessa convenzione di `_nome_area_visualizzato`
    # (IMPORTANT ⑦) -- perche' e' l'unica chiave con cui
    # `guarda("dispositivo", ...)` lo ritrova, e perche' un id tecnico non va
    # mai spacciato per un nome dichiarato dall'utente.
    return f" (id: {device_id})"


def _domain_name(domain: str, n: int) -> str:
    pair = _DOMAIN_NAMES.get(domain)
    if pair is None:
        return domain
    singular, plural = pair
    return singular if n == 1 else plural


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural




def _is_event(domain: str, device_class: str | None, value) -> bool:
    """Sta SUCCEDENDO qualcosa? -- non «e' cosi'», non «vale tanto».

    E' la domanda che il digesto deve porsi, ed e' diversa da «vale la pena
    saperlo»: una condizione stabile (un telefono a casa) e una misura (19,5 °C)
    si sanno benissimo, si vanno a chiedere, e non si annunciano.

    Fino alla fetta «il vocabolario delle tipologie» questa funzione non
    esisteva e al suo posto c'era un `in _STATI_NOTEVOLI` cieco al tipo: 300
    elementi su 845, e il dettaglio individuale perso sotto il raggruppamento.
    """
    v = str(value).lower()
    if domain == "alarm_control_panel":
        # Solo "triggered": armato e disarmato sono la routine quotidiana, non
        # un'eccezione. Regola gia' presente prima di questa fetta, conservata.
        return v == "triggered"
    if domain == "binary_sensor":
        return v == "on" and device_class in _EVENT_CLASSES
    if domain in _EVENT_DOMAINS:
        return v in _ACTIVE_STATES
    return False


def _count_per_domain(entity: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in entity:
        domain = domain_of(e["id"])
        counts[domain] = counts.get(domain, 0) + 1
    # Ordine alfabetico sul dominio: stabile, non dipende dall'ordine in cui
    # i registri sono stati letti o restituiti.
    return {domain: counts[domain] for domain in sorted(counts)}


# `nome_con_id` (R1, fetta "i riferimenti", incidente 2026-08-20) ora vive in
# `anagrafe.py`: T8 (R2) la riusa per le etichette di `guarda`, e una regola
# che deve valere per OGNI riferimento della casa non puo' avere due sedi --
# scritta due volte sarebbe la stessa forma di difetto che sta chiudendo.


def _displayed_area_name(area: dict) -> str:
    """Il nome di un'area per il PREFISSO di "Notevole adesso"
    (`_area_di_ogni_entita`): l'id accanto solo se e' una pseudo-area
    (IMPORTANT ⑦): "Senza area", "Aree non lette" & co. non esistono
    nell'anagrafe grezza di Home Assistant, quindi ne' `cerca()` ne'
    `guarda('area', nome)` le trovano per nome -- solo per id
    (`guarda('area', '__senza_area__')`). Mostrare solo il nome e' un vicolo
    cieco: le entita' che piu' meritano attenzione (orfane, non lette)
    finirebbero contate nel nucleo e irraggiungibili nel dettaglio.

    Le aree REALI non mostrano qui il proprio id (decisione del proprietario,
    spec "i riferimenti"): a differenza delle pseudo-aree sono comunque
    risolvibili per nome da `cerca`/`guarda`, e ripeterlo a ogni entita'
    notevole costerebbe piu' di quel che rende. Per l'albero di "La casa",
    che puo' permetterselo (una riga per area, non una per entita'), vedi
    `_nome_area_per_albero`."""
    if is_pseudo_area(area["id"]):
        return name_with_id(area["nome"], area["id"])
    return area["nome"]


def _tree_area_name(area: dict) -> str:
    """Il nome di un'area per l'albero di "La casa" (`_righe_casa`): l'id
    accanto SEMPRE che differisca dal nome, reale o pseudo che sia -- e' il
    reperto R1 dell'incidente 2026-08-20: l'albero mostrava solo nomi,
    `guarda`/`esegui` pretendono l'id esatto e vietano di indovinarlo dal
    nome mostrato. A differenza di `_nome_area_visualizzato`, che alimenta
    anche il prefisso di "Notevole adesso" (dove l'id resta fuori, vedi
    li'), qui il costo e' una riga per area."""
    return name_with_id(area["nome"], area["id"])


# I nomi italiani delle otto misure del sistema di unita' di Home Assistant.
# Le chiavi a sinistra sono quelle vere di `UnitSystem.as_dict()` (verificate
# in `homeassistant/const.py`, non trascritte da una tabella di
# documentazione: e' esattamente il modo in cui "co" sarebbe dovuto essere
# "carbon_monoxide" e un allarme monossido sarebbe sparito in silenzio).
_MEASUREMENT_NAMES = {
    "temperature": "temperatura",
    "length": "lunghezza",
    "mass": "massa",
    "pressure": "pressione",
    "volume": "volume",
    "wind_speed": "vento",
    "accumulated_precipitation": "pioggia",
    "area": "area",
}


def _now_line(frame: dict | None, now: float | None) -> str:
    """Che ore sono, nel fuso della casa. Vuota se nessuno l'ha detto.

    Nasce da un difetto misurato sull'add-on vero il 21/08/2026: `prometti`
    ordina al modello «`quando` e' un istante ISO-8601 col fuso: risolvilo tu
    da "fra un'ora"», e il nucleo dichiarava il fuso e MAI l'ora. Alle 21:01
    il modello ha creduto fossero le 23:52 e ha fissato una promessa alle
    23:55. Il server l'ora ce l'ha esatta -- la usa per validare l'istante che
    il modello ha indovinato: si chiedeva al modello un fatto che HIRIS
    possiede (fondamenta n.2, ogni fatto ha una sola casa).

    L'ora esce insieme al suo fuso, sempre: un orario senza fuso e' il «72»
    senza i gradi. Se il fuso della casa manca o non e' un fuso vero si dice
    UTC E LO SI SCRIVE -- non e' il ripiego silenzioso che questo modulo
    vieta, e' un'altra affermazione vera.
    """
    if now is None:
        return ""
    name = (frame or {}).get("fuso") or ""
    try:
        timezone, label = (ZoneInfo(name), name) if name else (UTC, "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        timezone, label = UTC, "UTC"
    when = datetime.fromtimestamp(now, timezone)
    return "Adesso sono le {} del {} (fuso {}).".format(
        when.strftime("%H:%M"), when.strftime("%d/%m/%Y"), label)


def _reference_frame_lines(frame: dict | None, now: float | None = None) -> list[str]:
    """Il sistema di riferimento della casa, in una o due righe.

    Va PRIMA di tutto il resto perche' e' cio' che rende leggibile tutto il
    resto: un digesto pieno di numeri senza scala ne' fuso e' un digesto di
    numeri, non di fatti.

    Tace se non lo sa. Una riga che afferma un fuso a caso e' peggio del
    silenzio: il modello che non legge un fuso chiede, quello che ne legge uno
    sbagliato risponde sbagliato con sicurezza.

    La frase finale fra parentesi non e' cortesia: e' la sola cosa che impedisce
    a chi legge -- il modello -- di fare da solo l'errore che il codice non fa
    piu', cioe' applicare l'unita' della casa a un'entita' che non ce l'ha.
    Home Assistant converte all'INGRESSO dell'entita': una casa metrica puo'
    contenere un sensore in Fahrenheit, e un indice senza unita' non diventa
    "gradi" perche' la casa e' metrica.
    """
    if not frame:
        return []
    lines = []
    identity = []
    # Il nome che l'utente ha dato alla casa in Home Assistant. Entrava nel
    # sistema di riferimento e non usciva da questa riga: la fetta A dichiarava
    # «esce da due porte, con la stessa forma», e ne usciva da una e mezza.
    # Per primo, perche' e' il nome della cosa di cui parla tutto il resto.
    if frame.get("nome"):
        identity.append(f"casa «{frame['nome']}»")
    if frame.get("fuso"):
        identity.append(f"fuso {frame['fuso']}")
    if frame.get("lingua"):
        identity.append(f"lingua {frame['lingua']}")
    if frame.get("valuta"):
        identity.append(f"valuta {frame['valuta']}")
    if frame.get("paese"):
        identity.append(f"paese {frame['paese']}")
    if frame.get("versione_ha"):
        identity.append(f"Home Assistant {frame['versione_ha']}")
    if identity:
        lines.append("Riferimento: " + ", ".join(identity) + ".")
    # Subito dopo il fuso, perche' e' lo stesso oggetto: l'ora e il sistema in
    # cui leggerla. Dentro `righe_sistema` e non accanto, cosi' eredita il peso
    # 0 del taglio (`pesi_casa` in `componi`): un nucleo che tronca via
    # l'orologio rimetterebbe il modello a indovinare l'ora proprio nei casi
    # in cui la casa e' grande.
    now_line = _now_line(frame, now)
    if now_line:
        lines.append(now_line)

    unit = frame.get("unita") or {}
    if isinstance(unit, dict):
        # Ordine dichiarato da `_NOMI_MISURA`, non quello del dizionario che
        # arriva da HA: due case identiche devono produrre lo stesso digesto.
        measurements = [f"{name} {unit[key]}"
                  for key, name in _MEASUREMENT_NAMES.items() if unit.get(key)]
        if measurements:
            lines.append(
                "Unita' con cui ragiona la casa: " + ", ".join(measurements)
                + " (ogni entita' porta la propria: se manca, manca -- non e'"
                  " questa).")
    return lines


def _home_space_lines(floors: list[dict],
                device_names: dict[str, str] | None) -> list[str]:
    """Piano per piano, area per area: quante entita' per tipo. Non i nomi
    -- vedi il docstring del modulo sul perche'.

    Prende l'albero gia' costruito da `gerarchia()` (con `non_disponibili`
    applicato dal chiamante, `componi()`) invece di ricostruirselo: cosi'
    "La casa" e "Notevole adesso" -- che condividono lo stesso albero --
    non possono mai raccontare due storie diverse sulla stessa area.

    `nomi_dispositivo` (id -> nome, `None` quando il registro dei
    dispositivi non ha risposto) serve alle ANNOTAZIONI: un conteggio che
    raggruppa entita' di un dispositivo solo non dice se sono quattro cose
    o una, e questo e' il posto in cui lo dice -- vedi
    `_annotazione_dispositivo`. Non e' "mettere i dispositivi nel nucleo":
    240 righe sfonderebbero il budget e violerebbero "conta, non elenca".
    E' annotare i conteggi che mentono per omissione.

    Senza valore predefinito, e non per pedanteria: l'unico chiamante e'
    `componi()`, quindi un default non terrebbe compatibile nessuno --
    lascerebbe solo un modo di chiamare questa funzione che produce una
    mappa muta senza che nessuno l'abbia deciso. In un modulo che esiste per
    non degradare in silenzio, chi chiama dichiara se i nomi ce li ha."""
    if not floors:
        return ["Nessun piano registrato."]
    lines = []
    for floor in floors:
        lines.append(f"{name_with_id(floor['nome'], floor['id'])}:")
        if not floor["aree"]:
            lines.append("  - (nessuna area)")
            continue
        for area in floor["aree"]:
            counts = _count_per_domain(area["entita"])
            if counts:
                detail = ", ".join(
                    f"{n} {_domain_name(dom, n)}"
                    + _device_annotation(area["entita"], dom, n, device_names)
                    for dom, n in counts.items())
            else:
                detail = "nessuna entita'"
            lines.append(f"  - {_tree_area_name(area)}: {detail}")
    return lines


def _area_per_entity(floors: list[dict]) -> dict[str, str]:
    """entity_id -> nome dell'area (o pseudo-area: "Senza area", "Aree non
    lette", ...) che le e' stata assegnata, letta dallo STESSO albero usato
    per "La casa". Serve a "Notevole adesso" per non ricalcolare l'area a
    mano con una logica propria che finirebbe per divergere da quella di
    `gerarchia()` -- e per raccontare, di un'entita' con un riferimento
    penzolante o un registro caduto, esattamente cio' che "La casa" ne
    direbbe, invece di lasciarla senza prefisso in silenzio."""
    area_lookup = {}
    for floor in floors:
        for area in floor["aree"]:
            name = _displayed_area_name(area)
            for entity in area["entita"]:
                area_lookup[entity["id"]] = name
    return area_lookup


def _group_highlights(entries: list[dict]) -> list[tuple[int, str]]:
    """Oltre `_SOGLIA_NOTEVOLE_INDIVIDUALE`, "Notevole adesso" CONTA anche
    lei invece di elencare -- "Cucina: 3 luci (accese)" invece di tre righe.

    Restituisce `(peso, riga)`: il PESO (quante entita' individuali quella
    riga rappresenta) serve a chi taglia (`componi()`) per dichiarare
    correttamente quanti ELEMENTI sono esclusi quando una riga raggruppata
    viene tagliata, non quante RIGHE (IMPORTANT ⑤) -- una riga puo' valere
    per cento entita'."""
    counts: dict[tuple[str, str, str], int] = {}
    order: list[tuple[str, str, str]] = []
    for v in entries:
        key = (v["area_nome"] or "Fuori da un'area nota", v["dominio"], v["stato_leggibile"])
        if key not in counts:
            order.append(key)
        counts[key] = counts.get(key, 0) + 1
    # Le righe si raccolgono nell'ordine in cui capitano le entita', che e'
    # quello dell'anagrafe: la stessa area finirebbe sparsa in tre punti
    # diversi dell'elenco. Qui si tengono insieme -- la leggibilita' non e' un
    # abbellimento, e' cio' che permette a chi legge (una persona dalla pagina,
    # o il modello nel prompt) di vedere una stanza per volta invece di
    # ricomporla a mente.
    lines = []
    for area_name, domain, readable_state in sorted(order):
        n = counts[(area_name, domain, readable_state)]
        line = f"- {area_name}: {n} {_domain_name(domain, n)} ({readable_state})"
        lines.append((n, line))
    return lines


def _grouped_highlights_heading(total: int) -> str:
    """La riga di testa di "Notevole adesso" quando raggruppato, ricostruita
    dal TOTALE ATTUALMENTE mostrato -- non da quello originale prima di un
    eventuale taglio (IMPORTANT ⑤): un'intestazione che dice "150 elementi"
    sopra righe che ne sommano 95 e' il nucleo che si contraddice da solo."""
    entry = _plural(total, "elemento notevole", "elementi notevoli")
    return (f"({total} {entry}: raggruppati per area, dominio e stato -- "
            f"oltre {_INDIVIDUAL_HIGHLIGHT_THRESHOLD} il dettaglio individuale non ci sta.)")


def _unreliable_state(home_space: dict, state: dict, reliable_state: bool,
                        unavailable: tuple[str, ...] = ()) -> bool:
    """Distingue «ho guardato ed e' tutto tranquillo» da «non ho guardato»:
    sono due cose diverse, e la Sezione 2 deve dirle diversamente (CRITICAL
    ②). Tre modi per finirci dentro:

    - il chiamante lo dichiara esplicitamente (`stato_affidabile=False`) --
      per esempio una lettura iniziata ma non ancora conclusa;
    - il registro "entita" non ha risposto (in `non_disponibili`): dopo un
      `sostituisci` parziale la tabella e' VUOTA, non piccola. Senza questo
      controllo, `casa.get("entita", [])` vuota fa scattare il ramo "casa
      senza entita' = niente da guardare" qui sotto -- ma non e' una casa
      senza entita', e' un registro che non ha risposto: cinque luci accese
      nella cache viva (che non passa da questa lista) resterebbero "niente
      di notevole", contraddette due sezioni dopo dall'avviso sul registro
      caduto;
    - lo si deduce: se in anagrafe ci sono entita' ma NESSUNA ha uno stato
      leggibile (assente da `stato`, o "unknown" -- lo stato comunissimo di
      un'entita' subito dopo un riavvio di Home Assistant, prima che il
      primo aggiornamento arrivi), il nucleo non ha visto una casa tranquilla:
      non ha visto niente.

    Una casa senza entita' non ci finisce: li' "niente di notevole" e'
    vero, non e' un silenzio -- non c'e' nulla da guardare."""
    if not reliable_state:
        return True
    if "entita" in unavailable:
        return True
    active_entities = [e for e in home_space.get("entita", []) if not e.get("disabilitata")]
    if not active_entities:
        return False
    for e in active_entities:
        value = state.get(e["id"])
        if value is not None and str(value).lower() != "unknown":
            return False
    return True


def _highlight_lines(home_space: dict, state: dict, floors: list[dict],
                    unreliable_state: bool,
                    reported_classes: dict[str, str] | None = None
                    ) -> tuple[list[str], list[int], bool]:
    """Cio' che e' notevole ADESSO: acceso, aperto, in allarme scattato.
    Serve lo stato vivo, che arriva dal chiamante -- il nucleo non lo va a
    cercare -- e l'albero gia' costruito da `gerarchia()` per l'area, non
    uno ricalcolato a mano (vedi `_area_di_ogni_entita`).

    Restituisce `(righe, pesi, raggruppato)`. `pesi` e' parallelo a `righe`:
    quante entita' individuali OGNI riga rappresenta (1 quando non
    raggruppato, il conteggio del gruppo quando lo e') -- serve al taglio in
    `componi()` per dichiarare ELEMENTI esclusi, non righe (IMPORTANT ⑤).
    `raggruppato` dice se serve ricostruire l'intestazione dopo un eventuale
    taglio (vedi `_intestazione_notevoli_raggruppati`): l'intestazione non e'
    nelle righe tagliabili apposta, per poterla ricalcolare sul totale VERO
    dopo il taglio invece di lasciarla affermare un numero che le righe
    sotto non confermano piu'."""
    if unreliable_state:
        return ([
            ("Stato non letto (o dichiarato non attendibile): non si puo' dire se in "
            "questo momento c'e' qualcosa di notevole -- non e' lo stesso di "
            "'niente di notevole'.")
        ], [1], False)
    area_per_entity = _area_per_entity(floors)
    # La classe viene dallo SPECCHIO: il registro delle entita' non la manda
    # (`anagrafe.classe_effettiva`). Finche' si e' letta solo dal registro,
    # `_e_un_evento` ha sempre ricevuto `None` per ogni sensore binario --
    # quindi nessun allagamento, nessun fumo, nessun monossido e' MAI entrato
    # in questa sezione, e le voci di `_SIGNIFICATO_CLASSE` non sono mai
    # state raggiunte.
    reported = reported_classes or {}
    entries = []
    unreachable = 0
    for e in home_space.get("entita", []):
        if e.get("disabilitata"):
            continue
        # I DUE CAMPI CHE HOME ASSISTANT DICHIARA, e che questo digesto
        # ignorava. Sull'impianto del proprietario tolgono 179 elementi su 300:
        # 113 `config` + 66 `diagnostic`, piu' 10 nascoste a mano. La doc di HA
        # dice che «diagnostic and config entities are typically hidden from
        # primary UI displays»: qui vale lo stesso, perche' un digesto e' una
        # vista principale -- e' cio' che HIRIS dice senza che tu abbia chiesto.
        #
        # NON valgono per `guarda`/`cerca`: li' hai chiesto tu, e filtrare una
        # risposta esplicita sarebbe nascondere.
        if e.get("categoria"):          # "config" o "diagnostic"
            continue
        if e.get("nascosta"):
            continue
        entity_id = e["id"]
        if entity_id not in state:
            continue
        value = state[entity_id]
        # Le irraggiungibili non sono «cosa sta facendo la casa»: sono SALUTE,
        # ed erano 119 -- 76 righe di digesto. Il fatto resta (una riga di
        # conteggio, sotto), il dettaglio e' della fetta «salute di HA».
        if str(value).lower() == "unavailable":
            unreachable += 1
            continue
        if not _is_event(
            domain_of(entity_id), actual_class(e.get("classe"), reported.get(entity_id)), value,
        ):
            continue
        entries.append({
            "area_nome": area_per_entity.get(entity_id),
            "dominio": domain_of(entity_id),
            "stato_leggibile": translate_state(
                value, actual_class(e.get("classe"), reported.get(entity_id)),
            ),
            "nome": e.get("nome") or entity_id,
        })
    # La riga delle irraggiungibili sta IN TESTA e pesa ZERO, e nessuna delle
    # due cose e' estetica: `componi()` taglia dal fondo, quindi in coda
    # sarebbe la prima a cadere; e `_intestazione_notevoli_raggruppati` conta
    # la somma dei pesi, quindi con peso 1 direbbe «N+1 elementi notevoli»
    # includendo una riga che non e' un elemento ma un riassunto.
    unreachable_line = ([f"- {unreachable} entità non rispondono."]
                if unreachable else [])
    unreachable_weight = [0] if unreachable else []

    if not entries:
        # «Niente di notevole» resta vero anche con delle irraggiungibili: sono
        # due frasi diverse e si dicono tutte e due.
        return (unreachable_line + ["Niente di notevole al momento."],
                unreachable_weight + [1], False)
    if len(entries) > _INDIVIDUAL_HIGHLIGHT_THRESHOLD:
        groups = _group_highlights(entries)
        return (unreachable_line + [line for _, line in groups],
                unreachable_weight + [weight for weight, _ in groups], True)
    lines = []
    for v in entries:
        prefix = f"{v['area_nome']}: " if v["area_nome"] else ""
        lines.append(f"- {prefix}{v['nome']} ({v['stato_leggibile']})")
    return (unreachable_line + lines, unreachable_weight + [1] * len(lines), False)


def _behavior_lines(behavior: list[dict]) -> list[str]:
    """I NOMI di cio' che la casa fa gia' da sola, con l'id accanto (R1,
    stessa regola di `nome_con_id` in `anagrafe.py`: fetta "i riferimenti",
    incidente 2026-08-20) -- `guarda('automazione'/'script', ...)` pretende l'id
    esatto, e senza di qui il modello non aveva da dove prenderlo. Il corpo
    si va a chiedere -- per trecento automazioni non ci sta, e qui serve solo
    sapere che esistono. Chi non ha il corpo lo dichiara in riga."""
    if not behavior:
        return ["Nessuna automazione o script registrati."]
    lines = []
    for v in behavior:
        id_ = v.get("id")
        name = v.get("nome") or id_ or "(senza nome)"
        kind = v.get("tipo", "?")
        line = f"- {name_with_id(name, id_)} ({kind})"
        if v.get("corpo") is None:
            line += " -- corpo non disponibile, solo il nome"
        lines.append(line)
    return lines


# Gli stati in cui un'integrazione di Home Assistant NON sta funzionando.
# I valori sono quelli veri di `ConfigEntryState` (`homeassistant/config_entries.py`),
# verificati: `loaded` e' l'unico stato sano, `setup_in_progress` e
# `unload_in_progress` sono momentanei e non si annunciano.
_BROKEN_INTEGRATION_STATES = {
    "setup_error", "setup_retry", "migration_error", "failed_unload", "not_loaded",
}


def _integrations_notice(integrations: list[dict]) -> str | None:
    """«Perche' la telecamera del giardino non risponde?»

    Un'integrazione caduta e' la spiegazione piu' probabile di un gruppo di
    entita' che non rispondono, e Home Assistant la diagnostica gia' da se':
    manda lo stato E il motivo dentro la stessa risposta che l'anagrafe legge
    a ogni ricostruzione. HIRIS salvava lo stato, buttava il motivo, e non
    leggeva ne' l'uno ne' l'altro -- poteva solo contare le entita' non
    disponibili e non sapere perche'.

    Sta fra gli AVVISI e non in «Notevole adesso» perche' non e' un evento:
    e' una condizione, e resta vera finche' qualcuno non la ripara. E' anche
    la sezione giusta per un altro motivo: dichiara cio' che HIRIS NON puo'
    raccontare della casa, ed e' esattamente il caso -- le entita' di
    quell'integrazione non hanno uno stato leggibile.

    Il motivo esce solo se c'e': HA lo riempie per `setup_error` e
    `setup_retry`, non sempre per `not_loaded`. Inventarlo sarebbe peggio.
    """
    broken = [i for i in integrations or []
             if (i.get("stato") or "") in _BROKEN_INTEGRATION_STATES]
    if not broken:
        return None
    # Una voce per NOME+STATO+MOTIVO, non una per config entry.
    #
    # Home Assistant permette piu' voci di configurazione con lo stesso titolo
    # -- due repeater identici, la stessa integrazione aggiunta due volte -- e
    # sull'impianto vero questo produceva «Fritz-esterno (not_loaded),
    # Fritz-studio (not_loaded), FRITZ!Repeater (not_loaded), Fritz-esterno
    # (not_loaded), Fritz-studio (not_loaded), FRITZ!Repeater (not_loaded)»:
    # nove voci per sei cose. Ripetere lo stesso nome non aggiunge un fatto,
    # consuma l'attenzione di chi legge e fa sembrare il guasto piu' grande di
    # quello che e'.
    #
    # Quante volte compare lo si DICE («x2»), invece di far contare le
    # ripetizioni a chi legge: due voci giu' con lo stesso nome sono due cose,
    # e tacerlo sarebbe l'errore opposto.
    #
    # Il titolo si ripulisce dagli spazi: sull'impianto vero c'e' un
    # «Abat-jour » con lo spazio in coda, e uscirebbe cosi' nel testo.
    counts: dict[tuple, int] = {}
    for i in sorted(broken, key=lambda x: (x.get("dominio") or "", x.get("titolo") or "")):
        name = (i.get("titolo") or i.get("dominio") or "senza nome").strip() or "senza nome"
        reason = (i.get("motivo") or "").strip()
        key = (name, i.get("stato"), reason)
        counts[key] = counts.get(key, 0) + 1
    entries = []
    for (name, state, reason), count in counts.items():
        repeat_suffix = f" x{count}" if count > 1 else ""
        entries.append(f"{name}{repeat_suffix} ({state}{': ' + reason if reason else ''})")
    total = sum(counts.values())
    count_phrase = "Un'integrazione" if total == 1 else f"{total} integrazioni"
    verb = "non sta funzionando" if total == 1 else "non stanno funzionando"
    return (f"{count_phrase} di Home Assistant {verb}: {', '.join(entries)}. "
            "Le entita' che dipendono da loro possono non rispondere.")


# LA SOGLIA dei problemi diagnosticati da Home Assistant, e il perche'.
#
# Molte case hanno stabilmente due o tre `repairs` aperti e innocui: uno YAML
# deprecato, un'integrazione da riautenticare quando capitera'. Un nucleo che
# li ripete a OGNI messaggio insegna a chi legge a saltare quella riga, e il
# giorno del guasto vero non se ne accorge nessuno. Il filtro non e' un
# risparmio di caratteri: e' cio' che tiene viva la riga.
#
# La soglia e' scritta al CONTRARIO -- non «cosa si dice» ma «cosa si tace» --
# e non e' un vezzo: e' l'unica forma in cui il ramo `else` e' sicuro. Un
# elenco di severita' da dire tacerebbe da solo tutto cio' che non conosce
# (una severita' nuova di Home Assistant, o assente: `severity` e'
# `IssueSeverity | None` in `helpers/issue_registry.py`, verificato alla
# fonte), e un problema silenziato perche' non lo si e' saputo leggere e'
# esattamente la bugia che questa fetta esiste per chiudere.
#
# Quindi tace SOLO il `warning`, e nemmeno sempre: un `warning` con
# `breaks_in_ha_version` non e' un consiglio, e' una SCADENZA -- diventera' un
# guasto da solo, e l'unico momento in cui saperlo serve e' prima. Tutto il
# resto (`critical`, `error`, una severita' che non sappiamo giudicare) si
# dice per nome.
_SILENCED_PROBLEM_SEVERITIES = ("warning",)

# Quanti problemi si citano per nome prima di tornare a CONTARE -- la regola
# del modulo (docstring in cima) applicata anche qui. Gli avvisi non passano
# per il taglio di `componi()`: una casa con venti guasti gravi produrrebbe un
# avviso di millecinquecento caratteri che niente puo' accorciare, dentro un
# nucleo che ne ha seimila in tutto. Cinque bastano a far capire di che
# famiglia sono; il numero degli altri resta dichiarato.
_LISTED_PROBLEMS_CEILING = 5

# Dove si vanno a leggere per esteso. Il registro NON porta il testo del
# problema -- porta una `translation_key` che vive nello `strings.json`
# dell'integrazione, e HIRIS non ce l'ha. Mandare l'utente dove il testo c'e'
# e' l'unica cosa onesta da fare al posto di inventarlo.
_REPAIR_LOCATION = "Impostazioni -> Riparazioni di Home Assistant"


def _problem_entry(p: dict) -> str:
    """Un problema in una riga, coi soli campi che si sanno interpretare.

    Il nome e' `dominio: chiave` ed e' lo STESSO ripiego che usa Home
    Assistant quando non trova la traduzione (`ha-config-repairs.ts`:
    `` `${issue.domain}: ${issue.translation_key || issue.issue_id}` ``,
    verificato alla fonte). Copiarlo non e' pigrizia: e' cio' che fa
    coincidere il nome che il modello legge con quello che l'utente vede
    davanti a se' quando apre la pagina delle riparazioni.

    Cosa NON entra, e perche':
    - `translation_placeholders`: sono i buchi di una frase che non abbiamo.
      Un valore senza la sua frase non e' un oggetto, e' un frammento
      (fondamenta: atomicita') -- «integration: Reolink» senza sapere cosa la
      frase dicesse di Reolink afferma meno di quanto sembri;
    - `learn_more_url`: un indirizzo che il modello non puo' aprire. Chi puo'
      aprirlo lo trova gia' nella pagina delle riparazioni;
    - `created`: il registro dei problemi si rilegge ogni pochi minuti (vedi
      `server.rileggi_problemi_ha`), e una data di apertura non cambia cosa
      c'e' da fare.
    """
    name = f"{p.get('domain') or 'senza dominio'}: " \
           f"{p.get('translation_key') or p.get('issue_id') or 'senza chiave'}"
    details = [(p.get("severity") or "").strip().lower() or "severita' non dichiarata"]
    deadline = (p.get("breaks_in_ha_version") or "").strip()
    if deadline:
        details.append(f"si rompe in {deadline}")
    # `is_fixable` e' `bool | None`: `None` non e' `False`, e' «HA non lo dice».
    # Si annota solo il si', perche' e' l'unico che cambia cosa puo' fare chi
    # legge -- un clic invece di una modifica a mano.
    if p.get("is_fixable"):
        details.append("Home Assistant sa ripararlo da solo")
    return f"{name} ({', '.join(details)})"


def _problems_notice(problems: dict | None) -> str | None:
    """Cio' che Home Assistant ha GIA' diagnosticato come rotto.

    Gemello di `_avviso_integrazioni`, e sta nella stessa sezione per la
    stessa ragione: quello dice PERCHE' un'integrazione non e' partita,
    questo dice cosa HA ha diagnosticato in generale. Nessuno dei due e' un
    evento -- sono condizioni, e restano vere finche' qualcuno non le ripara.
    In «Notevole adesso» annuncerebbero a ogni messaggio una cosa che non e'
    successa adesso.

    `problemi` arriva gia' letto dal chiamante (`handlers_casa.compose_briefing`,
    da `app["problemi_ha"]`), esattamente come `stato` e
    `sistema_di_riferimento`: `componi()` resta PURA.

    I tre valori, e sono tre cose diverse:
    - `None`: il chiamante non ha chiesto. Silenzio -- e' l'unico caso in cui
      tacere non afferma niente;
    - `{"errore": ...}`: non si e' potuto guardare. Si DICHIARA: un guasto di
      lettura non e' una casa sana, e un elenco vuoto qui significherebbe
      «non c'e' niente che non va»;
    - `{"problemi": [...]}`: le righe come HA le manda, gia' senza le ignorate
      dall'utente (`HAClient.problemi`).
    """
    if problems is None:
        return None

    error = (problems.get("errore") or "").strip()
    if error:
        return ("il registro dei problemi di Home Assistant non si e' potuto "
                f"leggere ({error}): qui non si sta dicendo che la casa e' "
                "sana, si sta dicendo che non si e' potuto guardare.")

    to_report: list[dict] = []
    silenced = 0
    for p in problems.get("problemi") or []:
        if not isinstance(p, dict):
            continue
        severity = (p.get("severity") or "").strip().lower()
        deadline = (p.get("breaks_in_ha_version") or "").strip()
        if severity in _SILENCED_PROBLEM_SEVERITIES and not deadline:
            silenced += 1
            continue
        to_report.append(p)

    # L'ordine di gravita' NON si riscrive qui: `SEVERITA_PROBLEMA` e'
    # gia' ordinata dalla piu' grave, ed e' la sua unica casa (fondamenta:
    # nessun doppione). Serve perche' il tetto qui sotto taglia dalla coda:
    # senza, cinque `warning` in scadenza potrebbero nascondere un `critical`.
    # Chi ha una severita' che non conosciamo finisce in fondo -- si dice
    # comunque, ma dopo cio' che sappiamo graduare. A parita', dominio e
    # chiave: due letture identiche devono produrre lo stesso nucleo.
    def _severity_rank(p: dict) -> tuple[int, str, str]:
        severity = (p.get("severity") or "").strip().lower()
        rank = (PROBLEM_SEVERITY.index(severity)
                 if severity in PROBLEM_SEVERITY
                 else len(PROBLEM_SEVERITY))
        return (rank, p.get("domain") or "", p.get("issue_id") or "")

    to_report.sort(key=_severity_rank)
    unlisted = max(0, len(to_report) - _LISTED_PROBLEMS_CEILING)

    # Il numero dei taciuti esce SEMPRE che ce ne siano, anche quando non c'e'
    # nient'altro da dire. Un filtro silenzioso e' un altro modo di mentire, e
    # il modulo dichiara gia' che la priorita' non e' «cosa e' recuperabile»
    # ma «cosa il modello perde la possibilita' di SAPERE che esiste»: il
    # numero glielo lascia, il testo si va a leggere dove il testo c'e'.
    silenced_tail = ""
    if silenced:
        # La frase intera cambia al singolare, non solo la desinenza: «Altri 1
        # problema ... non sono elencato» e' cio' che succede a concordare un
        # pezzo per volta. Stessa disciplina di `_avviso_taglio`, che per la
        # stessa ragione riceve le frasi gia' concordate.
        silenced_tail = (" Un altro problema di severita' minore non e' elencato"
                        if silenced == 1 else
                        f" Altri {silenced} problemi di severita' minore non sono elencati")
        silenced_tail += " (warning senza una versione di rottura dichiarata)."

    if not to_report:
        if not silenced:
            # Il registro c'e' ed e' vuoto: non si dice niente, che e' la cosa
            # giusta da dire. Stessa scelta di `_avviso_integrazioni` su una
            # casa sana.
            return None
        # Anche qui la frase intera, non la desinenza (vedi `coda_taciuti`).
        count_and_which = ("1 problema aperto di severita' minore" if silenced == 1
                          else f"{silenced} problemi aperti di severita' minore")
        closing_phrase = ("non e' elencato qui, si legge" if silenced == 1
                    else "non sono elencati qui, si leggono")
        return (f"Home Assistant ha {count_and_which} (warning senza una "
                f"versione di rottura dichiarata): {closing_phrase} in "
                f"{_REPAIR_LOCATION}.")

    entries = "; ".join(_problem_entry(p) for p in to_report[:_LISTED_PROBLEMS_CEILING])
    count = len(to_report)
    entry = _plural(count, "problema", "problemi")
    unlisted_tail = ""
    if unlisted:
        unlisted_tail = ("; e un altro problema della stessa lista, non elencato"
                             if unlisted == 1 else
                             f"; e altri {unlisted} problemi della stessa "
                             "lista, non elencati")
    return (f"Home Assistant ha gia' diagnosticato {count} {entry}: {entries}"
            f"{unlisted_tail}.{silenced_tail} "
            f"Si {_plural(count, 'legge', 'leggono')} per esteso e si "
            f"{_plural(count, 'ripara', 'riparano')} in {_REPAIR_LOCATION}.")


# Quanti `entity_id` si citano per area prima di tornare a CONTARE -- la
# regola del modulo (docstring in cima) applicata anche qui, e per la stessa
# ragione di `_TETTO_PROBLEMI_ELENCATI`: gli avvisi non passano per il taglio
# di `componi()`, quindi un'area che diverge di quaranta entita' scriverebbe
# una riga che niente puo' accorciare. Quattro bastano a far capire di che
# famiglia sono (una piattaforma sola? un dispositivo solo?); il numero degli
# altri resta dichiarato.
_COMPARISON_ENTITIES_CEILING = 4


def _cited_entities(identifiers: list[str]) -> str:
    """Gli id di un'area, tagliati al tetto e col resto DICHIARATO. Mai un
    elenco accorciato in silenzio: sarebbe la stessa bugia del filtro muto."""
    cited = list(identifiers)[:_COMPARISON_ENTITIES_CEILING]
    rest = len(identifiers) - len(cited)
    text = ", ".join(cited)
    if rest == 1:
        text += ", e un'altra"
    elif rest > 1:
        text += f", e altre {rest}"
    return text


def _comparison_notice(comparison: dict | None) -> str | None:
    """L'albero raccontato da HIRIS contro la casa che Home Assistant risolve.

    Fino a questa fetta `gerarchia()` era un'AFFERMAZIONE che niente
    verificava. `HAClient.estrai_dal_bersaglio` chiede a Home Assistant cosa
    contiene un'area davvero, e `anagrafe.confronta_con_home_assistant` mette
    le due liste una accanto all'altra su un campione di aree.

    `confronto` arriva gia' letto dal chiamante (`handlers_casa.compose_briefing`,
    da `app["confronto_albero"]`), esattamente come `stato`, `problemi` e
    `sistema_di_riferimento`: `componi()` resta PURA.

    **TRE ESITI, TRE DICITURE DIVERSE** -- la stessa disciplina con cui
    `gerarchia()` distingue «Senza area» da «Area sconosciuta» da «Aree non
    lette»:

    - **combaciano**: non si dice NIENTE. E' la cosa giusta da dire, ed e'
      anche il caso normale: un avviso che compare sempre smette di essere
      letto, e allora il giorno che compare quello vero non lo legge piu'
      nessuno. Il nucleo non afferma da nessuna parte che l'albero sia
      verificato, quindi tacere qui non promette niente;
    - **HIRIS ne ha di MENO**: Home Assistant riporta nell'area cose che
      l'albero non le attribuisce. La replica e' piu' vecchia della casa, o un
      registro e' caduto -- si dichiara, come si dichiara `non_disponibili`;
    - **HIRIS ne ha di PIU'**: l'albero attribuisce all'area cose che
      l'originale non conferma. E' il CASO PEGGIORE, e per questo si dice per
      primo: e' quello che produce risposte sbagliate dette con sicurezza.

    E un quarto stato che non e' un esito: **non letto**. Un confronto che non
    si e' potuto fare non e' un confronto riuscito, e vale per la singola area
    come per il giro intero -- `None` invece significa che il chiamante non ha
    chiesto, ed e' l'unico caso in cui il silenzio non afferma niente.
    """
    if comparison is None:
        return None

    error = str(comparison.get("errore") or "").strip()
    if error:
        return ("il confronto fra l'albero della casa e Home Assistant non si e' "
                f"potuto fare ({error}): qui non si sta dicendo che l'albero "
                "combacia, si sta dicendo che non si e' potuto controllare.")

    checked = [g for g in comparison.get("guardate") or [] if isinstance(g, dict)]
    if not checked:
        # Nessuna area confrontata (una casa senza aree, o un giro che non e'
        # ancora partito). Si tace, e tacere qui non afferma niente: l'albero
        # non si dichiara verificato in nessun altro punto del nucleo.
        return None

    extra = [g for g in checked if g.get("in_piu") or g.get("assente_in_ha")]
    missing = [g for g in checked if g.get("mancanti")]
    not_loaded = [g for g in checked if g.get("errore")]
    if not (extra or missing or not_loaded):
        # COMBACIANO. Vedi il docstring: e' il caso normale, e il silenzio e'
        # la cosa giusta da dire.
        return None

    phrases: list[str] = []

    if extra:
        entries = []
        for g in extra:
            if g.get("assente_in_ha"):
                # L'area intera non c'e' piu': si dice questo e non l'elenco
                # delle sue entita', che sarebbe la stessa notizia detta a
                # pezzi.
                entries.append(f"{g.get('nome')} ({g.get('area')}) non esiste "
                            "piu' in Home Assistant")
            else:
                entries.append(f"{g.get('nome')}: {_cited_entities(g.get('in_piu') or [])}")
        count_phrase = _plural(len(entries), "un'area", f"{len(entries)} aree")
        phrases.append(
            f"In {count_phrase} l'albero di HIRIS afferma qualcosa che Home Assistant "
            f"non conferma -- {'; '.join(entries)}. E' il caso peggiore dei due: "
            "e' cosi' che nasce una risposta sbagliata detta con sicurezza, e "
            "finche' l'anagrafe non si ricostruisce quelle attribuzioni non "
            "reggono.")

    if missing:
        entries = [f"{g.get('nome')}: {_cited_entities(g.get('mancanti') or [])}"
                for g in missing]
        count_phrase = _plural(len(entries), "un'area", f"{len(entries)} aree")
        phrases.append(
            f"In {count_phrase} Home Assistant riporta entita' che l'albero di HIRIS "
            f"non ci attribuisce -- {'; '.join(entries)}. La replica dell'anagrafe "
            "e' piu' vecchia della casa, o un registro non ha risposto.")

    if not_loaded:
        entries = [f"{g.get('nome')} ({g.get('errore')})" for g in not_loaded]
        count_phrase = _plural(len(entries), "un'area", f"{len(entries)} aree")
        phrases.append(
            f"Su {count_phrase} il confronto non si e' potuto fare -- {'; '.join(entries)}: "
            "non si sta dicendo che quelle aree combaciano, si sta dicendo che "
            "non si sono potute controllare.")

    # Il CAMPIONE, sempre, e nello stesso avviso: un campione taciuto fa
    # sembrare completo un controllo parziale -- «una divergenza in un'area»
    # detto senza dire che le aree guardate erano tre su sedici lascia credere
    # che le altre tredici siano state trovate a posto.
    totals = comparison.get("aree_totali")
    n = len(checked)
    verb = _plural(n, "Confrontata", "Confrontate")
    count_phrase = _plural(n, "1 area", f"{n} aree")
    if isinstance(totals, int) and 0 < totals <= n:
        sample = f"{verb} {count_phrase}: tutte quelle della casa."
    elif isinstance(totals, int) and totals > 0:
        sample = (f"{verb} {count_phrase} sulle {totals} della casa; le altre non "
                    "sono state guardate in questo giro.")
    else:
        sample = f"{verb} {count_phrase} della casa."
    phrases.append(sample)

    # Le frasi sono FRASI, ognuna con la maiuscola: dopo un punto una
    # minuscola si legge come un errore di stampa, e un avviso che sembra rotto
    # si legge male anche quando dice la cosa giusta.
    return "Confronto con Home Assistant -- " + " ".join(phrases)


def _memory_lines(memories: list[dict]) -> list[str]:
    """I ricordi ENTRANO INTERI, con chi li ha detti -- l'unica eccezione
    al "conta, non elencare" (vedi docstring del modulo).

    Ordinati QUI, esplicitamente, dal piu' recente al piu' vecchio (per
    `id`, che in `MemoryStore` e' AUTOINCREMENT: monotono con l'ordine
    di scrittura). Il taglio in `componi()` toglie dalla coda dichiarando
    "il piu' vecchio prima" -- una promessa che oggi e' vera solo perche'
    `MemoryStore.fetch()` fa gia' `ORDER BY id DESC`: se un
    chiamante futuro passasse i ricordi in un altro ordine, si
    scarterebbero i piu' recenti mentre l'avviso continuerebbe ad
    affermare il contrario. Ordinando qui, la promessa la mantiene il
    codice, non il caso con cui arrivano gli argomenti."""
    if not memories:
        return ["Nessun ricordo registrato."]
    # N1 (review indipendente 25/08/2026): questa riga chiamava
    # `sanitize_text` inline invece di `ricordi_sanificati()` -- la funzione
    # CONDIVISA introdotta apposta perche' un ricordo non potesse piu' uscire
    # filtrato da una porta e grezzo da un'altra (I1). Il nucleo era filtrato
    # comunque, ma smentiva l'argomento stesso con cui la funzione condivisa
    # e' nata: "un punto solo, non una terza copia". Ora e' un punto solo
    # anche qui -- il docstring di `_sanitize.py` che elenca le porte diventa
    # vero da se', non per una lista da tenere aggiornata a mano.
    #
    # C-2 (L1-sicurezza.md): il ricordo e' l'UNICA cosa che entra intera
    # nel nucleo, a OGNI turno, senza che il modello lo richieda -- e'
    # il canale piu' pericoloso per un'iniezione che deve sopravvivere
    # (I-1: una `ricorda()` avvenuta in un turno iniettato tornerebbe nel
    # contesto di ogni turno successivo, per sempre). Sanificato QUI,
    # dove il testo diventa parte di cio' che il modello legge sempre --
    # non nell'archivio (`memoria/archivio.py`), che resta la verita'
    # cosi' come e' stata detta (regola 1 del modulo): il testo
    # ARCHIVIATO non cambia, cambia solo cio' che esce da questa porta.
    sorted_memories = sorted(sanitized_memories(memories), key=lambda r: r.get("id", 0),
                              reverse=True)
    lines = []
    for r in sorted_memories:
        said_by = r.get("detto_da") or "qualcuno"
        # L'ID, che mancava. Il modulo dichiara a inizio file che un ricordo
        # tagliato «si raggiunge con `guarda("ricordo", id)`» -- ma l'id non
        # era stampato da nessuna porta, e `richiama` esige un'ancora che i
        # ricordi come «mi piace il caffe'» non hanno. Il digesto dichiarava
        # una lacuna («12 ricordi non inclusi») e chiudeva l'unica strada per
        # colmarla.
        lines.append(f"- [#{r.get('id')}] \"{r['testo']}\" (detto da {said_by})")
    return lines


def _gap_lines(notices: list[str]) -> list[str]:
    if not notices:
        return ["Nessuna lacuna nota."]
    return [f"- {a}" for a in notices]


def _cut_notice(excluded_per_pool: dict[str, int], cut_order, ceiling: int) -> str:
    """La frase che dichiara il taglio DENTRO il nucleo -- non solo nel
    riepilogo. Ricostruita da zero ogni volta che `esclusi_per_pool` cambia,
    cosi' non puo' mai restare disallineata da cio' che e' stato tagliato
    davvero.

    `ordine_taglio` porta la frase (singolare, plurale) GIA' concordata --
    generi diversi ("riga ... inclusa" contro "elemento ... incluso") non si
    possono comporre con un participio unico senza sbagliarne meta'.
    """
    parts = []
    for pool_name, singular, plural in cut_order:
        n = excluded_per_pool.get(pool_name, 0)
        if n:
            parts.append(f"{n} {_plural(n, singular, plural)}")
    return f"Il nucleo superava il tetto di {ceiling} caratteri: " + "; ".join(parts) + "."


def _assemble(sections: list[tuple[str, list[str]]]) -> str:
    blocks = []
    for title, lines in sections:
        block = title if not lines else title + "\n" + "\n".join(lines)
        blocks.append(block)
    return "\n\n".join(blocks)


def compose(home_space: dict, behavior: list[dict], memories: list[dict],
            state: dict, ceiling: int = 6000,
            unavailable: tuple[str, ...] = (),
            reliable_state: bool = True,
            behavior_problems: tuple[str, ...] = (),
            unloaded_behavior_files: dict[str, str] | None = None,
            reference_frame: dict | None = None,
            reported_classes: dict[str, str] | None = None,
            problems: dict | None = None,
            comparison: dict | None = None,
            now: float | None = None) -> tuple[str, dict]:
    """Compone il nucleo: la stessa casa per chiunque ragioni.

    Pura -- nessun I/O, nessuna rete. Restituisce `(testo, riepilogo)`:
    il riepilogo (`caratteri`, `troncato`, `ricordi_esclusi`, `avvisi`) non
    puo' mentire su cio' che il testo non contiene, perche' e' costruito
    dagli stessi tagli che il testo dichiara -- vedi `test_nucleo.py`.

    L'ordine, deciso e fisso: 1) la casa (conteggi), 2) cio' che e' notevole
    adesso, 3) cio' che la casa fa gia' da sola, 4) cio' che le persone
    hanno detto, 5) cio' che HIRIS ignora (incluso l'eventuale taglio).

    `non_disponibili` sono i registri dell'anagrafe che non hanno risposto
    all'ultima lettura (`ArchivioCasa.non_disponibili()`). Senza, ne' "La
    casa" ne' "cio' che HIRIS ignora" potrebbero nominare la lacuna piu'
    grave che esista: una casa letta a meta' che il nucleo racconterebbe
    come una casa piccola (o senz'area) invece che come una casa non letta
    per intero. Va passato a `gerarchia()` (tramite `_righe_casa`) E a
    `_stato_inaffidabile`/`_righe_notevole` -- attraverso lo STESSO albero,
    cosi' le sezioni non possono raccontarla in modo incompatibile. Una casa
    non ancora letta non e' una casa cambiata.

    `stato_affidabile=False` dichiara esplicitamente che `stato` non ci si
    puo' fidare (es. una lettura iniziata ma non ancora conclusa): senza un
    modo per dirlo, il chiamante non avrebbe potuto distinguere "ho letto lo
    stato ed e' vuoto/sospetto" da "questo e' lo stato vero". Anche senza
    dichiararlo, il nucleo lo deduce da solo se in anagrafe ci sono entita'
    ma nessuna ha uno stato leggibile, o se il registro "entita" stesso non
    ha risposto (CRITICAL ②, tabella vuota dopo un `sostituisci` parziale) --
    vedi `_stato_inaffidabile`.

    `problemi` sono i guasti che Home Assistant ha GIA' diagnosticato
    (`repairs/list_issues`, letti da `HAClient.problemi()`), nella forma in cui
    quella funzione li restituisce: `{"problemi": [...]}` o `{"errore": ...}`.
    Arrivano come ARGOMENTO, come `stato` e `sistema_di_riferimento`, perche'
    questa funzione non apre connessioni. `None` significa «il chiamante non ha
    chiesto» e non «non c'e' niente che non va»: vedi `_avviso_problemi`, che
    decide anche cosa dire e cosa tacere.

    `confronto` e' l'esito dell'ultimo giro di verifica dell'albero contro
    Home Assistant (`anagrafe.confronta_con_home_assistant`, alimentato da
    `server.giro_di_confronto_albero`). Arriva come ARGOMENTO per la stessa
    ragione di `problemi`: questa funzione non apre connessioni, e chiedere a
    HA cosa contiene un'area e' una chiamata di rete. `None` significa «il
    chiamante non ha chiesto», e NON «l'albero combacia»: vedi
    `_avviso_confronto`, che tiene separati i tre esiti e il non-letto.

    `problemi_comportamento`/`file_non_letti_comportamento` sono le
    dichiarazioni che `comportamento.reread()` costruisce gia' e che
    `/api/casa` espone (`ArchivioCasa.problemi_comportamento()`/
    `.file_non_letti()`): senza un parametro per riceverle, il PERCHE' di
    un'automazione sconosciuta (id duplicato, file malformato) non arrivava
    mai al modello (IMPORTANT ⑧).

    Quando serve tagliare per stare sotto `tetto`, si tagliano prima gli
    elementi notevoli (raggruppati o no, vedi `_righe_notevole`), poi cio'
    che la casa fa da sola, poi -- fino a una riserva minima che non si
    tocca mai (`_RISERVA_MINIMA_RIGHE_CASA`, IMPORTANT ⑥) -- i conteggi
    della casa, e per ultimi i ricordi. Il PERCHE' di quest'ordine e' nel
    docstring del modulo: non e' "cosa e' recuperabile" (lo e' tutto), e'
    "cosa il modello perde la possibilita' di sapere che esiste".
    """
    notices: list[str] = []

    # DUE ELENCHI, non uno, e la differenza e' quella che ha fatto sbagliare
    # una risposta vera il 2026-08-18.
    #
    # `guasti_casa` sono FATTI SULLA CASA: nove integrazioni giu' col loro
    # motivo, i problemi che Home Assistant ha diagnosticato. Chi chiede «come
    # sta la casa» sta chiedendo ESATTAMENTE questo.
    #
    # `avvisi` sono i LIMITI DI CIO' CHE SO: un registro che non ha risposto,
    # un corpo di automazione mancante, il taglio del nucleo, le nascoste.
    #
    # Stavano insieme, sotto l'intestazione «Cio' che HIRIS ignora». E un
    # modello che legge quel titolo capisce «roba che non so, non da riferire»:
    # infatti, davanti a una casa con 77 entita' mute e nove integrazioni
    # cadute -- col motivo scritto due righe piu' su -- ha riportato il
    # SINTOMO e taciuto la CAUSA che aveva sotto gli occhi.
    #
    # Non e' stato un errore del modello: era il titolo a dire il falso. Nove
    # integrazioni rotte non sono cio' che HIRIS ignora, sono cio' che HIRIS
    # SA e deve dire.
    home_space_faults: list[str] = []

    fault = _integrations_notice(home_space.get("integrazioni") or [])
    if fault:
        home_space_faults.append(fault)

    # Subito dopo le integrazioni rotte, e non altrove: sono la stessa specie
    # di fatto -- cio' che HA ha diagnosticato -- e chi legge deve trovarli
    # accanto. Separarli significherebbe far cercare due volte la stessa
    # risposta.
    diagnosis = _problems_notice(problems)
    if diagnosis:
        home_space_faults.append(diagnosis)

    if unavailable:
        notices.append(
            "registri di Home Assistant che non hanno risposto all'ultima "
            f"lettura: {', '.join(sorted(unavailable))}. "
            "Cio' che manca qui sotto potrebbe esistere lo stesso.")

    # Subito dopo i registri caduti, e prima di tutto il resto: sono la stessa
    # specie di dichiarazione -- quanto ci si puo' fidare dell'albero che
    # "La casa" racconta qui sotto. Un registro caduto dice che l'albero e'
    # INCOMPLETO, il confronto dice che potrebbe essere SBAGLIATO, e chi legge
    # deve trovare le due cose una accanto all'altra. Gli avvisi di HA
    # (integrazioni, problemi) restano sopra perche' parlano della casa, non
    # della nostra copia.
    divergence = _comparison_notice(comparison)
    if divergence:
        notices.append(divergence)

    # Le NASCOSTE: fuori dalle gestioni, dentro la conoscenza.
    #
    # Dalla fetta «il vocabolario delle tipologie» un'entita' nascosta in Home
    # Assistant non entra piu' in «Notevole adesso»: e' una scelta esplicita
    # dell'utente e il digesto la rispetta. Ma «non la annuncio» e «non so che
    # esiste» sono due cose diverse, e la seconda sarebbe una perdita: alla
    # domanda «quante entita' nascoste ci sono?» HIRIS deve saper rispondere.
    #
    # Qui, e non altrove, perche' questa sezione esiste per dire cio' che HIRIS
    # NON porta nel discorso -- ed e' l'unico posto da cui la risposta si legge
    # senza chiamare uno strumento per ognuna delle sedici aree. `guarda` le
    # riporta gia' (filtra `disabilitata`, mai `nascosta`): la conoscenza c'era,
    # mancava il numero.
    hidden = [e for e in home_space.get("entita", [])
                if e.get("nascosta") and not e.get("disabilitata")]
    if hidden:
        n = len(hidden)
        entry = _plural(n, "entita' nascosta", "entita' nascoste")
        notices.append(
            f"{n} {entry} in Home Assistant: non entrano in «Notevole adesso» "
            "perche' l'utente le ha nascoste, ma esistono e `guarda` le "
            "riporta se gliele chiedi.")

    # IMPORTANT ④: si CONTA, non si elenca -- la stessa regola che il
    # nucleo applica a trecento entita' (vedi il docstring del modulo),
    # applicata qui al modulo stesso. Con cento script `solo_stato` (il
    # caso comunissimo delle scene importate) elencare tutti i nomi
    # sfondava il tetto del 94% da solo, e duplicava un'informazione gia'
    # visibile riga per riga in "Cio' che la casa fa gia' da sola"
    # (`_righe_comportamento` marca ogni voce senza corpo in linea).
    missing_bodies = [v for v in behavior if v.get("corpo") is None]
    if missing_bodies:
        n = len(missing_bodies)
        entry = _plural(n, "voce di comportamento", "voci di comportamento")
        notices.append(f"{n} {entry} senza corpo disponibile (solo il nome).")

    if behavior_problems:
        n = len(behavior_problems)
        entry = _plural(n, "problema", "problemi")
        notices.append(
            f"{n} {entry} nella lettura del comportamento (id duplicati, voci "
            "malformate: vedi /api/casa per il dettaglio).")

    if unloaded_behavior_files:
        names = ", ".join(sorted(unloaded_behavior_files))
        notices.append(f"file di comportamento non letti: {names}.")

    # `componi()` resta PURA. I nomi dei dispositivi non si vanno a prendere:
    # sono gia' in `casa["dispositivi"]`, la stessa struttura che il chiamante
    # ha letto con `ArchivioCasa.leggi()` (handlers_casa.compose_briefing) e
    # che questa funzione riceve da sempre -- fino a oggi ne buttava via un
    # campo. Nessun archivio aperto, nessuna rete.
    #
    # `None` e non `{}` col registro caduto: la tabella "dispositivi" caduta e'
    # VUOTA, non piccola (`archivio.sostituisci` cancella tutto e reinserisce
    # cio' che e' arrivato), quindi `{}` renderebbe ogni `dispositivo_id` un
    # riferimento al nulla e l'annotazione stamperebbe "(id: ...)" su tutta la
    # casa. La lacuna e' gia' dichiarata negli avvisi e in "cio' che HIRIS
    # ignora": qui si tace, non si inventa. Vedi `_annotazione_dispositivo`.
    if "dispositivi" in unavailable:
        device_names: dict[str, str] | None = None
    else:
        device_names = {d["id"]: (d.get("nome") or "")
                            for d in home_space.get("dispositivi") or [] if d.get("id")}

    # Un solo albero (`gerarchia()`, con `non_disponibili` applicato),
    # condiviso da "La casa" e da "Notevole adesso": prima di questo fix
    # `_righe_notevole` se ne ricalcolava uno proprio a mano, che poteva
    # dire "Senza area" dove "La casa" -- correttamente -- diceva "Aree non
    # lette" (CRITICAL ①).
    floors = hierarchy(home_space, unavailable)
    # Il riferimento sta in testa a "La casa" e non in una sezione sua: e' una
    # proprieta' della casa, e una sezione in piu' avrebbe voluto dire un'altra
    # intestazione da spendere per due righe. In testa perche' il taglio parte
    # dal fondo -- e perche' e' la chiave di lettura di tutto cio' che segue.
    reference_frame_lines = _reference_frame_lines(reference_frame, now)
    home_space_lines = reference_frame_lines + _home_space_lines(floors, device_names)

    unreliable = _unreliable_state(home_space, state, reliable_state, unavailable)
    if unreliable:
        notices.append(
            "lo stato delle entita' non e' stato letto, o e' stato dichiarato non "
            "attendibile: 'Notevole adesso' qui sotto non dice che va tutto bene, "
            "dice che non si e' potuto guardare.")
    highlight_lines, highlight_weights, grouped_highlight = _highlight_lines(
        home_space, state, floors, unreliable, reported_classes)
    behavior_lines = _behavior_lines(behavior)
    memory_lines = _memory_lines(memories)

    # Peso 0 al riferimento: l'intestazione somma i pesi per dire quante righe
    # di conteggio ci sono, e il riferimento non e' un conteggio -- contarlo
    # avrebbe fatto dire al nucleo un numero di aree piu' alto del vero.
    home_space_weights = ([0] * len(reference_frame_lines)
                           + [1] * (len(home_space_lines) - len(reference_frame_lines)))
    # La riserva che non si taglia mai vale i CONTEGGI: si alza di quanto
    # occupa il riferimento, cosi' aggiungerlo non toglie in silenzio una riga
    # di casa a chi legge (IMPORTANT (6)).
    home_space_reserve = _MIN_HOME_SPACE_LINES_RESERVE + len(reference_frame_lines)
    behavior_weights = [1] * len(behavior_lines)
    memory_weights = [1] * len(memory_lines)

    def _current_highlight_section() -> list[str]:
        # L'intestazione raggruppata (se serve) si ricostruisce dal totale
        # ATTUALMENTE rappresentato dalle righe rimaste, mai da quello
        # originale: dopo un taglio, un'intestazione che afferma il numero
        # di PRIMA sopra righe che ne sommano meno e' il nucleo che si
        # contraddice da solo (IMPORTANT ⑤).
        if grouped_highlight and highlight_lines:
            return [_grouped_highlights_heading(sum(highlight_weights))] + highlight_lines
        return list(highlight_lines)

    # L'ordine di STAMPA e' fisso (vedi docstring); l'ordine di TAGLIO e'
    # diverso e definito piu' sotto (`ordine_taglio`).
    home_space_section = ("## La casa", home_space_lines)
    highlight_section = ("## Notevole adesso", _current_highlight_section())
    behavior_section = ("## Cio' che la casa fa gia' da sola", behavior_lines)
    memory_section = ("## Cio' che le persone hanno detto", memory_lines)

    print_order = [home_space_section, highlight_section, behavior_section, memory_section]

    def _refresh_highlight_section() -> None:
        print_order[1] = ("## Notevole adesso", _current_highlight_section())

    # (chiave, righe, pesi, riserva minima) -- l'ordine qui e' l'ordine di
    # taglio: dal meno utile al piu' prezioso. Prima si tagliano gli
    # elementi notevoli (la sezione senza tetto proprio, e la piu' pesante
    # per riga quando la casa e' grande -- vedi `_raggruppa_notevoli` per
    # come si comprime prima ancora di arrivare qui), poi cio' che la casa
    # fa da sola, poi -- fino alla riserva minima, MAI oltre
    # (`_RISERVA_MINIMA_RIGHE_CASA`, IMPORTANT ⑥) -- i conteggi della casa:
    # e' la mappa che costa meno per riga e serve di piu' per orientarsi. I
    # ricordi restano gli ultimi in assoluto (vedi il docstring del modulo
    # sul perche' non e' "recuperabilita'").
    #
    # Quando lo stato e' inaffidabile, "Notevole adesso" e' UNA riga sola --
    # la dichiarazione stessa di "non ho guardato" (CRITICAL ②). Metterla
    # nel pool tagliabile la renderebbe la prima cosa a sparire, il che la
    # ricreerebbe esattamente: un silenzio non dichiarato. Resta fuori dal
    # taglio; se il nucleo sfora lo stesso, ci pensa la rete di sicurezza
    # piu' sotto.
    cut_order: list[tuple[str, list[str], list[int], int]] = []
    if not unreliable:
        cut_order.append(("notevole", highlight_lines, highlight_weights, 0))
    cut_order += [
        ("comportamento", behavior_lines, behavior_weights, 0),
        ("casa", home_space_lines, home_space_weights, home_space_reserve),
        ("ricordi", memory_lines, memory_weights, 0),
    ]
    # (chiave, frase singolare, frase plurale) GIA' concordate col genere
    # del sostantivo -- vedi il docstring di `_avviso_taglio`.
    cut_labels = [
        ("notevole", "elemento notevole non incluso",
                     "elementi notevoli non inclusi"),
        ("comportamento", "voce di comportamento non inclusa",
                          "voci di comportamento non incluse"),
        ("casa", "riga di conteggio della casa non inclusa",
                 "righe di conteggio della casa non incluse"),
        ("ricordi", "ricordo non incluso (il piu' vecchio prima)",
                    "ricordi non inclusi (i piu' vecchi prima)"),
    ]

    truncated = False
    excluded_per_pool: dict[str, int] = {}

    def _pop(pool_name: str, lines_pool: list[str], pool_weights: list[int], reserve: int) -> None:
        # IMPORTANT ⑤: si conta il PESO (quante entita'/elementi la riga
        # rappresenta davvero -- per "notevole" raggruppato puo' essere
        # molto piu' di 1), non la riga. Sottostimare l'escluso di nove
        # volte sulla lacuna piu' calda della casa e' peggio di non
        # dichiararlo affatto: sembra onesto e non lo e'.
        nonlocal truncated
        lines_pool.pop()  # dalla coda: l'ultima voce e' la meno prioritaria
        weight = pool_weights.pop()
        truncated = True
        excluded_per_pool[pool_name] = excluded_per_pool.get(pool_name, 0) + weight
        if pool_name == "notevole":
            _refresh_highlight_section()
        if pool_name == "casa":
            # MINOR: un'intestazione di piano ("Primo piano:") senza righe
            # sotto e' un artefatto del taglio, non un'informazione -- si
            # toglie a sua volta. Non conta come elemento escluso: le aree
            # che c'erano sotto sono gia' state contate ai loro rispettivi
            # pop, questo e' solo il titolo rimasto orfano.
            while (len(lines_pool) > reserve and lines_pool
                   and lines_pool[-1].endswith(":") and not lines_pool[-1].startswith("  ")):
                lines_pool.pop()
                pool_weights.pop()

    # IMPORTANT ④: il budget per casa/notevole/comportamento/ricordi non e'
    # `tetto - _RISERVA_SEZIONE_LACUNE` alla cieca. Se le lacune GIA' note
    # (registri caduti, corpi mancanti, problemi di comportamento, stato
    # inaffidabile...) pesano gia' piu' della riserva stimata, il budget per
    # il resto si restringe di conseguenza -- altrimenti il resto del
    # nucleo occuperebbe uno spazio che le lacune, gia' dichiarate, non
    # avrebbero avuto, e la rete di sicurezza sotto sarebbe l'unica cosa a
    # farsi carico dello sforamento.
    known_gaps_length = len(_assemble([("## Cio' che HIRIS ignora", _gap_lines(notices))]))
    # La sezione dei guasti entra nel conto come le lacune: sta FUORI dal
    # taglio -- non si accorcia mai, perche' e' la risposta alla domanda piu'
    # comune che si faccia a questo prodotto -- quindi lo spazio che occupa va
    # sottratto prima, o a farsi carico dello sforamento resterebbe solo la
    # rete di sicurezza in fondo.
    faults_length = (len(_assemble([(_FAULTS_HEADING, list(home_space_faults))]))
                        if home_space_faults else 0)
    gap_reserve = max(_GAP_SECTION_RESERVE, known_gaps_length + _GAP_SECTION_RESERVE)
    budget = max(0, ceiling - gap_reserve - faults_length)

    for pool_name, lines_pool, pool_weights, reserve in cut_order:
        while len(lines_pool) > reserve and len(_assemble(print_order)) > budget:
            _pop(pool_name, lines_pool, pool_weights, reserve)
        if len(_assemble(print_order)) <= budget:
            break

    # L'indice dell'avviso di taglio dentro `avvisi`, se e quando esiste --
    # serve a poterlo RISCRIVERE (rete di sicurezza sotto) senza rischiare
    # di sovrascrivere un avviso diverso che gli stesse accanto (es. i
    # corpi mancanti), che una sostituzione posizionale "ultimo elemento"
    # romperebbe silenziosamente se il taglio scattasse solo piu' avanti.
    cut_notice_index = None
    if truncated:
        notices.append(_cut_notice(excluded_per_pool, cut_labels, ceiling))
        cut_notice_index = len(notices) - 1

    gap_section = ("## Cio' che HIRIS ignora", _gap_lines(notices))

    # DOVE va la sezione dei guasti: subito dopo «La casa» e PRIMA di «Notevole
    # adesso». L'ordine di lettura diventa: com'e' fatta -> cosa e' rotto ->
    # cosa sta succedendo. Metterla in fondo, accanto alle lacune, e' cio' che
    # l'ha fatta ignorare; metterla in cima al posto della mappa toglierebbe a
    # chi legge il riferimento per capire i nomi che ci trova dentro.
    #
    # Fuori dal pool di taglio, come le lacune: non si accorcia mai.
    def _with_faults(sections: list) -> list:
        if not home_space_faults:
            return sections
        return [sections[0], (_FAULTS_HEADING, list(home_space_faults))] + sections[1:]

    text = _assemble(_with_faults(print_order) + [gap_section])

    # Rete di sicurezza: se anche cosi' il testo sfora, si continua a
    # tagliare -- ricordi prima (gia' l'ultima cosa nell'ordine di taglio),
    # ma NON SOLO ricordi (IMPORTANT ④): una casa con pochi o zero ricordi
    # che sfora lo stesso (es. lacune cresciute oltre ogni stima) non deve
    # fermarsi solo perche' "non ci sono piu' ricordi da tagliare" --
    # sforerebbe il tetto in silenzio, che e' peggio di un taglio
    # dichiarato in piu'. Si scende fino alla riserva minima della mappa;
    # oltre quella, mai (IMPORTANT ⑥): sforare il tetto in modo dichiarato
    # e' meno grave che svuotare anche la mappa in silenzio.
    safety_pools = [
        ("ricordi", memory_lines, memory_weights, 0),
        ("comportamento", behavior_lines, behavior_weights, 0),
        ("casa", home_space_lines, home_space_weights, home_space_reserve),
    ]
    if not unreliable:
        safety_pools.append(("notevole", highlight_lines, highlight_weights, 0))

    while len(text) > int(ceiling * 1.1):
        cut = False
        for pool_name, lines_pool, pool_weights, reserve in safety_pools:
            if len(lines_pool) > reserve:
                _pop(pool_name, lines_pool, pool_weights, reserve)
                cut = True
                break
        if not cut:
            break
        message = _cut_notice(excluded_per_pool, cut_labels, ceiling)
        if cut_notice_index is None:
            notices.append(message)
            cut_notice_index = len(notices) - 1
        else:
            notices[cut_notice_index] = message
        gap_section = ("## Cio' che HIRIS ignora", _gap_lines(notices))
        text = _assemble(_with_faults(print_order) + [gap_section])

    memories_excluded = excluded_per_pool.get("ricordi", 0)

    summary = {
        "caratteri": len(text),
        "troncato": truncated,
        "ricordi_esclusi": memories_excluded,
        # Due chiavi come le due sezioni, e per la stessa ragione: `guasti`
        # sono fatti sulla CASA, `avvisi` sono i limiti di cio' che HIRIS sa.
        # Tenerli in un elenco solo qui rimetterebbe in piedi la confusione che
        # nel testo e' appena stata sciolta -- e il riepilogo non puo'
        # raccontare una forma diversa da quella che il testo ha.
        "guasti": home_space_faults,
        "avvisi": notices,
    }
    return text, summary
