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

from .anagrafe import e_pseudo_area, gerarchia

# Il TIPO di un'entita' si ricava dal dominio del suo entity_id (la parte
# prima del punto) -- lo dichiara Home Assistant nell'id stesso, non un
# elenco nostro. Questa mappa serve solo a renderlo leggibile in italiano
# (singolare, plurale: "1 luce" e non "1 luci" -- il nucleo lo legge anche
# una persona, vedi il brief); un dominio che non conosciamo resta visibile
# col proprio nome invece di sparire, cosi' un tipo nuovo si legge diverso
# ma non si perde.
_NOMI_DOMINIO = {
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
_STATI_ATTIVI = {"on", "open", "unlocked", "playing", "cleaning"}

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
_DOMINI_EVENTO = {
    "light", "switch", "cover", "lock", "fan",
    "media_player", "valve", "remote", "siren", "vacuum",
}

# Per `binary_sensor` il dominio non basta: e' la CLASSE a dire se `on` e' un
# allagamento o il corridoio attraversato trenta secondi fa. Qui stanno gli
# allarmi e le aperture; restano fuori i transitori (`motion`, `occupancy`,
# `presence`, `sound`, `vibration`, `light`, `running`, `moving`, `power`,
# `plug`) e la manutenzione (`battery`, `connectivity`, `update`,
# `battery_charging`), che si vanno a chiedere e non si annunciano.
_CLASSI_EVENTO = {
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
_SOGLIA_NOTEVOLE_INDIVIDUALE = 15

_TRADUZIONE_STATO = {
    "on": "acceso", "off": "spento", "open": "aperta", "closed": "chiusa",
    "home": "in casa", "not_home": "fuori casa", "unlocked": "sbloccata",
    "locked": "bloccata", "playing": "in riproduzione", "paused": "in pausa",
    "unavailable": "non disponibile", "detected": "rilevato",
    "problem": "in problema", "triggered": "in allarme",
}

# COSA SIGNIFICANO I VALORI, per classe.
#
# "on"/"off" non bastano per una porta o una finestra: "acceso"/"spento"
# affermerebbe un'alimentazione che l'oggetto non ha. Il principio era gia'
# scritto qui, e copriva CINQUE classi (`_CLASSI_APERTURA`) sulle ventotto che
# Home Assistant documenta: per questo un allagamento si leggeva «1 sensore
# binario (acceso)», indistinguibile da una lampadina.
#
# I significati NON sono inventati: sono quelli dichiarati in
# developers.home-assistant.io/docs/core/entity/binary-sensor/, verificati il
# 16/08/2026. Dove HA dice «on means wet», qui c'e' «bagnato».
_SIGNIFICATO_CLASSE: dict[str, tuple[str, str]] = {
    # allarmi
    "moisture": ("bagnato", "asciutto"),
    "smoke": ("fumo rilevato", "nessun fumo"),
    "gas": ("gas rilevato", "nessun gas"),
    # ATTENZIONE: il valore-stringa e' `carbon_monoxide`, NON `co`. E' l'unica
    # delle 28 classi in cui la stringa non e' il nome della costante in
    # minuscolo (`BinarySensorDeviceClass.CO = "carbon_monoxide"`, verificato
    # su homeassistant/components/binary_sensor/__init__.py). Scritto `co`,
    # un allarme monossido non entra nel digesto e non viene tradotto: la
    # classe piu' critica dell'elenco, muta.
    "carbon_monoxide": ("monossido rilevato", "nessun monossido"),
    "safety": ("non sicuro", "sicuro"),
    "tamper": ("manomissione rilevata", "nessuna manomissione"),
    "problem": ("problema rilevato", "nessun problema"),
    "heat": ("caldo", "normale"),
    "cold": ("freddo", "normale"),
    # aperture (erano `_CLASSI_APERTURA`: assorbite qui, non affiancate)
    "door": ("aperto", "chiuso"),
    "window": ("aperto", "chiuso"),
    "garage_door": ("aperto", "chiuso"),
    "opening": ("aperto", "chiuso"),
    "damper": ("aperto", "chiuso"),
    "lock": ("sbloccato", "bloccato"),
    # presenza e movimento
    "motion": ("movimento rilevato", "nessun movimento"),
    "occupancy": ("occupato", "libero"),
    "presence": ("in casa", "fuori"),
    "moving": ("in movimento", "fermo"),
    "vibration": ("vibrazione rilevata", "nessuna vibrazione"),
    # alimentazione e collegamento
    "plug": ("collegato", "scollegato"),
    "power": ("alimentato", "non alimentato"),
    "connectivity": ("connesso", "disconnesso"),
    "battery": ("carica bassa", "carica normale"),
    "battery_charging": ("in carica", "non in carica"),
    "running": ("in funzione", "fermo"),
    # altro
    "light": ("luce rilevata", "nessuna luce"),
    "sound": ("suono rilevato", "nessun suono"),
    "update": ("aggiornamento disponibile", "aggiornato"),
}

# Il buffer riservato alla sezione "cio' che HIRIS ignora": deve poter contenere
# l'avviso di taglio anche quando il taglio e' avvenuto, quindi si sottrae
# dal budget PRIMA di tagliare, non dopo -- altrimenti l'avviso stesso
# rischierebbe di essere cio' che sfonda il tetto. E' un MINIMO, non un
# valore fisso: se le lacune GIA' note (prima ancora di tagliare) pesano
# piu' di questo, il budget per il resto si restringe di conseguenza (vedi
# `componi()`) -- altrimenti l'avviso stesso, cresciuto oltre la stima,
# sarebbe cio' che sfonda il tetto in silenzio (IMPORTANT ④).
_RISERVA_SEZIONE_LACUNE = 400

# Quante righe della mappa (`_righe_casa`) il taglio non tocca MAI. E' la
# sezione piu' economica per riga e la piu' utile per orientarsi (vedi
# `componi()`): senza un minimo, con molti ricordi lunghi il taglio la
# svuota per intero PRIMA di toccare un solo ricordo, perche' "casa" viene
# prima di "ricordi" nell'ordine di taglio -- un modello che legge quel
# nucleo non saprebbe piu' quali stanze esistono (IMPORTANT ⑥).
_RISERVA_MINIMA_RIGHE_CASA = 3


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
_MAX_NOMI_DISPOSITIVO_IN_RIGA = 1


def _portatori(entita_area: list[dict], dominio: str) -> tuple[list[str], int]:
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
    dispositivi: list[str] = []
    senza = 0
    for entita in entita_area:
        if _dominio(entita["id"]) != dominio:
            continue
        dispositivo_id = entita.get("dispositivo_id")
        if not dispositivo_id:
            senza += 1
        elif dispositivo_id not in dispositivi:
            dispositivi.append(dispositivo_id)
    return dispositivi, senza


def _annotazione_dispositivo(entita_area: list[dict], dominio: str, quante: int,
                             nomi_dispositivo: dict[str, str] | None) -> str:
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
    if nomi_dispositivo is None:
        return ""
    dispositivi, senza = _portatori(entita_area, dominio)
    if len(dispositivi) + senza >= quante:
        # Tante cose quante entita': il conteggio dice gia' tutto.
        return ""
    if senza or len(dispositivi) > _MAX_NOMI_DISPOSITIVO_IN_RIGA:
        # Piu' di un portatore: si conta, non si elenca (vedi la costante).
        # `senza` non nullo con un solo dispositivo e' lo stesso caso visto da
        # un'altra parte -- il nome coprirebbe solo una parte delle entita'
        # contate, e un'annotazione parziale afferma piu' di quel che sa.
        return ""
    if not dispositivi:
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
    id_dispositivo = dispositivi[0]
    nome = (nomi_dispositivo.get(id_dispositivo) or "").strip()
    if nome:
        return f" ({nome})"
    # Un dispositivo senza nome esiste davvero: `casa/archivio.py` scrive
    # `name_by_user or name`, ed entrambi sono nullable. Si mostra l'id
    # MARCATO come id -- la stessa convenzione di `_nome_area_visualizzato`
    # (IMPORTANT ⑦) -- perche' e' l'unica chiave con cui
    # `guarda("dispositivo", ...)` lo ritrova, e perche' un id tecnico non va
    # mai spacciato per un nome dichiarato dall'utente.
    return f" (id: {id_dispositivo})"


def _dominio(entity_id: str) -> str:
    return entity_id.split(".", 1)[0] if "." in entity_id else entity_id


def _nome_dominio(dominio: str, n: int) -> str:
    coppia = _NOMI_DOMINIO.get(dominio)
    if coppia is None:
        return dominio
    singolare, plurale = coppia
    return singolare if n == 1 else plurale


def _plurale(n: int, singolare: str, plurale: str) -> str:
    return singolare if n == 1 else plurale


def _traduci_stato(valore, classe: str | None = None) -> str:
    """Il valore in parole. La CLASSE decide: `on` di un `moisture` e' «bagnato»,
    `on` di un `door` e' «aperto», `on` di una luce e' «acceso». Vedi
    `_SIGNIFICATO_CLASSE`, che porta i significati dichiarati da Home Assistant."""
    v = str(valore).lower()
    significato = _SIGNIFICATO_CLASSE.get(classe or "")
    if significato:
        if v == "on":
            return significato[0]
        if v == "off":
            return significato[1]
    return _TRADUZIONE_STATO.get(v, str(valore))


def _e_un_evento(dominio: str, classe: str | None, valore) -> bool:
    """Sta SUCCEDENDO qualcosa? -- non «e' cosi'», non «vale tanto».

    E' la domanda che il digesto deve porsi, ed e' diversa da «vale la pena
    saperlo»: una condizione stabile (un telefono a casa) e una misura (19,5 °C)
    si sanno benissimo, si vanno a chiedere, e non si annunciano.

    Fino alla fetta «il vocabolario delle tipologie» questa funzione non
    esisteva e al suo posto c'era un `in _STATI_NOTEVOLI` cieco al tipo: 300
    elementi su 845, e il dettaglio individuale perso sotto il raggruppamento.
    """
    v = str(valore).lower()
    if dominio == "alarm_control_panel":
        # Solo "triggered": armato e disarmato sono la routine quotidiana, non
        # un'eccezione. Regola gia' presente prima di questa fetta, conservata.
        return v == "triggered"
    if dominio == "binary_sensor":
        return v == "on" and classe in _CLASSI_EVENTO
    if dominio in _DOMINI_EVENTO:
        return v in _STATI_ATTIVI
    return False


def _conta_per_dominio(entita: list[dict]) -> dict[str, int]:
    conteggio: dict[str, int] = {}
    for e in entita:
        dominio = _dominio(e["id"])
        conteggio[dominio] = conteggio.get(dominio, 0) + 1
    # Ordine alfabetico sul dominio: stabile, non dipende dall'ordine in cui
    # i registri sono stati letti o restituiti.
    return {dominio: conteggio[dominio] for dominio in sorted(conteggio)}


def _nome_area_visualizzato(area: dict) -> str:
    """Il nome di un'area, con l'id accanto se e' una pseudo-area (IMPORTANT
    ⑦): "Senza area", "Aree non lette" & co. non esistono nell'anagrafe
    grezza di Home Assistant, quindi ne' `cerca()` ne' `guarda('area',
    nome)` le trovano per nome -- solo per id (`guarda('area',
    '__senza_area__')`). Mostrare solo il nome e' un vicolo cieco: le
    entita' che piu' meritano attenzione (orfane, non lette) finirebbero
    contate nel nucleo e irraggiungibili nel dettaglio."""
    if e_pseudo_area(area["id"]):
        return f"{area['nome']} (id: {area['id']})"
    return area["nome"]


# I nomi italiani delle otto misure del sistema di unita' di Home Assistant.
# Le chiavi a sinistra sono quelle vere di `UnitSystem.as_dict()` (verificate
# in `homeassistant/const.py`, non trascritte da una tabella di
# documentazione: e' esattamente il modo in cui "co" sarebbe dovuto essere
# "carbon_monoxide" e un allarme monossido sarebbe sparito in silenzio).
_NOMI_MISURA = {
    "temperature": "temperatura",
    "length": "lunghezza",
    "mass": "massa",
    "pressure": "pressione",
    "volume": "volume",
    "wind_speed": "vento",
    "accumulated_precipitation": "pioggia",
    "area": "area",
}


def _righe_sistema(sistema: dict | None) -> list[str]:
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
    if not sistema:
        return []
    righe = []
    identita = []
    if sistema.get("fuso"):
        identita.append(f"fuso {sistema['fuso']}")
    if sistema.get("lingua"):
        identita.append(f"lingua {sistema['lingua']}")
    if sistema.get("valuta"):
        identita.append(f"valuta {sistema['valuta']}")
    if sistema.get("paese"):
        identita.append(f"paese {sistema['paese']}")
    if sistema.get("versione_ha"):
        identita.append(f"Home Assistant {sistema['versione_ha']}")
    if identita:
        righe.append("Riferimento: " + ", ".join(identita) + ".")

    unita = sistema.get("unita") or {}
    if isinstance(unita, dict):
        # Ordine dichiarato da `_NOMI_MISURA`, non quello del dizionario che
        # arriva da HA: due case identiche devono produrre lo stesso digesto.
        misure = [f"{nome} {unita[chiave]}"
                  for chiave, nome in _NOMI_MISURA.items() if unita.get(chiave)]
        if misure:
            righe.append(
                "Unita' con cui ragiona la casa: " + ", ".join(misure)
                + " (ogni entita' porta la propria: se manca, manca -- non e'"
                  " questa).")
    return righe


def _righe_casa(piani: list[dict],
                nomi_dispositivo: dict[str, str] | None) -> list[str]:
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
    if not piani:
        return ["Nessun piano registrato."]
    righe = []
    for piano in piani:
        righe.append(f"{piano['nome']}:")
        if not piano["aree"]:
            righe.append("  - (nessuna area)")
            continue
        for area in piano["aree"]:
            conteggio = _conta_per_dominio(area["entita"])
            if conteggio:
                dettaglio = ", ".join(
                    f"{n} {_nome_dominio(dom, n)}"
                    + _annotazione_dispositivo(area["entita"], dom, n, nomi_dispositivo)
                    for dom, n in conteggio.items())
            else:
                dettaglio = "nessuna entita'"
            righe.append(f"  - {_nome_area_visualizzato(area)}: {dettaglio}")
    return righe


def _area_di_ogni_entita(piani: list[dict]) -> dict[str, str]:
    """entity_id -> nome dell'area (o pseudo-area: "Senza area", "Aree non
    lette", ...) che le e' stata assegnata, letta dallo STESSO albero usato
    per "La casa". Serve a "Notevole adesso" per non ricalcolare l'area a
    mano con una logica propria che finirebbe per divergere da quella di
    `gerarchia()` -- e per raccontare, di un'entita' con un riferimento
    penzolante o un registro caduto, esattamente cio' che "La casa" ne
    direbbe, invece di lasciarla senza prefisso in silenzio."""
    mappa = {}
    for piano in piani:
        for area in piano["aree"]:
            nome = _nome_area_visualizzato(area)
            for entita in area["entita"]:
                mappa[entita["id"]] = nome
    return mappa


def _raggruppa_notevoli(voci: list[dict]) -> list[tuple[int, str]]:
    """Oltre `_SOGLIA_NOTEVOLE_INDIVIDUALE`, "Notevole adesso" CONTA anche
    lei invece di elencare -- "Cucina: 3 luci (accese)" invece di tre righe.

    Restituisce `(peso, riga)`: il PESO (quante entita' individuali quella
    riga rappresenta) serve a chi taglia (`componi()`) per dichiarare
    correttamente quanti ELEMENTI sono esclusi quando una riga raggruppata
    viene tagliata, non quante RIGHE (IMPORTANT ⑤) -- una riga puo' valere
    per cento entita'."""
    conteggio: dict[tuple[str, str, str], int] = {}
    ordine: list[tuple[str, str, str]] = []
    for v in voci:
        chiave = (v["area_nome"] or "Fuori da un'area nota", v["dominio"], v["stato_leggibile"])
        if chiave not in conteggio:
            ordine.append(chiave)
        conteggio[chiave] = conteggio.get(chiave, 0) + 1
    # Le righe si raccolgono nell'ordine in cui capitano le entita', che e'
    # quello dell'anagrafe: la stessa area finirebbe sparsa in tre punti
    # diversi dell'elenco. Qui si tengono insieme -- la leggibilita' non e' un
    # abbellimento, e' cio' che permette a chi legge (una persona dalla pagina,
    # o il modello nel prompt) di vedere una stanza per volta invece di
    # ricomporla a mente.
    righe = []
    for area_nome, dominio, stato_leggibile in sorted(ordine):
        n = conteggio[(area_nome, dominio, stato_leggibile)]
        riga = f"- {area_nome}: {n} {_nome_dominio(dominio, n)} ({stato_leggibile})"
        righe.append((n, riga))
    return righe


def _intestazione_notevoli_raggruppati(totale: int) -> str:
    """La riga di testa di "Notevole adesso" quando raggruppato, ricostruita
    dal TOTALE ATTUALMENTE mostrato -- non da quello originale prima di un
    eventuale taglio (IMPORTANT ⑤): un'intestazione che dice "150 elementi"
    sopra righe che ne sommano 95 e' il nucleo che si contraddice da solo."""
    voce = _plurale(totale, "elemento notevole", "elementi notevoli")
    return (f"({totale} {voce}: raggruppati per area, dominio e stato -- "
            f"oltre {_SOGLIA_NOTEVOLE_INDIVIDUALE} il dettaglio individuale non ci sta.)")


def _stato_inaffidabile(casa: dict, stato: dict, stato_affidabile: bool,
                        non_disponibili: tuple[str, ...] = ()) -> bool:
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
    if not stato_affidabile:
        return True
    if "entita" in non_disponibili:
        return True
    entita_attive = [e for e in casa.get("entita", []) if not e.get("disabilitata")]
    if not entita_attive:
        return False
    for e in entita_attive:
        valore = stato.get(e["id"])
        if valore is not None and str(valore).lower() != "unknown":
            return False
    return True


def _righe_notevole(casa: dict, stato: dict, piani: list[dict],
                    stato_inaffidabile: bool) -> tuple[list[str], list[int], bool]:
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
    if stato_inaffidabile:
        return ([
            "Stato non letto (o dichiarato non attendibile): non si puo' dire se in "
            "questo momento c'e' qualcosa di notevole -- non e' lo stesso di "
            "'niente di notevole'."
        ], [1], False)
    area_per_entita = _area_di_ogni_entita(piani)
    voci = []
    irraggiungibili = 0
    for e in casa.get("entita", []):
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
        if entity_id not in stato:
            continue
        valore = stato[entity_id]
        # Le irraggiungibili non sono «cosa sta facendo la casa»: sono SALUTE,
        # ed erano 119 -- 76 righe di digesto. Il fatto resta (una riga di
        # conteggio, sotto), il dettaglio e' della fetta «salute di HA».
        if str(valore).lower() == "unavailable":
            irraggiungibili += 1
            continue
        if not _e_un_evento(_dominio(entity_id), e.get("classe"), valore):
            continue
        voci.append({
            "area_nome": area_per_entita.get(entity_id),
            "dominio": _dominio(entity_id),
            "stato_leggibile": _traduci_stato(valore, e.get("classe")),
            "nome": e.get("nome") or entity_id,
        })
    # La riga delle irraggiungibili sta IN TESTA e pesa ZERO, e nessuna delle
    # due cose e' estetica: `componi()` taglia dal fondo, quindi in coda
    # sarebbe la prima a cadere; e `_intestazione_notevoli_raggruppati` conta
    # la somma dei pesi, quindi con peso 1 direbbe «N+1 elementi notevoli»
    # includendo una riga che non e' un elemento ma un riassunto.
    riga_giu = ([f"- {irraggiungibili} entità non rispondono."]
                if irraggiungibili else [])
    peso_giu = [0] if irraggiungibili else []

    if not voci:
        # «Niente di notevole» resta vero anche con delle irraggiungibili: sono
        # due frasi diverse e si dicono tutte e due.
        return (riga_giu + ["Niente di notevole al momento."],
                peso_giu + [1], False)
    if len(voci) > _SOGLIA_NOTEVOLE_INDIVIDUALE:
        gruppi = _raggruppa_notevoli(voci)
        return (riga_giu + [riga for _, riga in gruppi],
                peso_giu + [peso for peso, _ in gruppi], True)
    righe = []
    for v in voci:
        prefisso = f"{v['area_nome']}: " if v["area_nome"] else ""
        righe.append(f"- {prefisso}{v['nome']} ({v['stato_leggibile']})")
    return (riga_giu + righe, peso_giu + [1] * len(righe), False)


def _righe_comportamento(comportamento: list[dict]) -> list[str]:
    """I NOMI di cio' che la casa fa gia' da sola. Il corpo si va a
    chiedere -- per trecento automazioni non ci sta, e qui serve solo
    sapere che esistono. Chi non ha il corpo lo dichiara in riga."""
    if not comportamento:
        return ["Nessuna automazione o script registrati."]
    righe = []
    for v in comportamento:
        nome = v.get("nome") or v.get("id") or "(senza nome)"
        tipo = v.get("tipo", "?")
        riga = f"- {nome} ({tipo})"
        if v.get("corpo") is None:
            riga += " -- corpo non disponibile, solo il nome"
        righe.append(riga)
    return righe


def _righe_ricordi(ricordi: list[dict]) -> list[str]:
    """I ricordi ENTRANO INTERI, con chi li ha detti -- l'unica eccezione
    al "conta, non elencare" (vedi docstring del modulo).

    Ordinati QUI, esplicitamente, dal piu' recente al piu' vecchio (per
    `id`, che in `ArchivioMemoria` e' AUTOINCREMENT: monotono con l'ordine
    di scrittura). Il taglio in `componi()` toglie dalla coda dichiarando
    "il piu' vecchio prima" -- una promessa che oggi e' vera solo perche'
    `ArchivioMemoria.richiama()` fa gia' `ORDER BY id DESC`: se un
    chiamante futuro passasse i ricordi in un altro ordine, si
    scarterebbero i piu' recenti mentre l'avviso continuerebbe ad
    affermare il contrario. Ordinando qui, la promessa la mantiene il
    codice, non il caso con cui arrivano gli argomenti."""
    if not ricordi:
        return ["Nessun ricordo registrato."]
    ricordi_ordinati = sorted(ricordi, key=lambda r: r.get("id", 0), reverse=True)
    righe = []
    for r in ricordi_ordinati:
        detto_da = r.get("detto_da") or "qualcuno"
        righe.append(f"- \"{r['testo']}\" (detto da {detto_da})")
    return righe


def _righe_lacune(avvisi: list[str]) -> list[str]:
    if not avvisi:
        return ["Nessuna lacuna nota."]
    return [f"- {a}" for a in avvisi]


def _avviso_taglio(esclusi_per_pool: dict[str, int], ordine_taglio, tetto: int) -> str:
    """La frase che dichiara il taglio DENTRO il nucleo -- non solo nel
    riepilogo. Ricostruita da zero ogni volta che `esclusi_per_pool` cambia,
    cosi' non puo' mai restare disallineata da cio' che e' stato tagliato
    davvero.

    `ordine_taglio` porta la frase (singolare, plurale) GIA' concordata --
    generi diversi ("riga ... inclusa" contro "elemento ... incluso") non si
    possono comporre con un participio unico senza sbagliarne meta'.
    """
    parti = []
    for nome_pool, singolare, plurale in ordine_taglio:
        n = esclusi_per_pool.get(nome_pool, 0)
        if n:
            parti.append(f"{n} {_plurale(n, singolare, plurale)}")
    return f"Il nucleo superava il tetto di {tetto} caratteri: " + "; ".join(parti) + "."


def _assembla(sezioni: list[tuple[str, list[str]]]) -> str:
    blocchi = []
    for titolo, righe in sezioni:
        blocco = titolo if not righe else titolo + "\n" + "\n".join(righe)
        blocchi.append(blocco)
    return "\n\n".join(blocchi)


def componi(casa: dict, comportamento: list[dict], ricordi: list[dict],
            stato: dict, tetto: int = 6000,
            non_disponibili: tuple[str, ...] = (),
            stato_affidabile: bool = True,
            problemi_comportamento: tuple[str, ...] = (),
            file_non_letti_comportamento: dict[str, str] | None = None,
            sistema_di_riferimento: dict | None = None) -> tuple[str, dict]:
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

    `problemi_comportamento`/`file_non_letti_comportamento` sono le
    dichiarazioni che `comportamento.rileggi()` costruisce gia' e che
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
    avvisi: list[str] = []

    if non_disponibili:
        avvisi.append(
            "registri di Home Assistant che non hanno risposto all'ultima "
            f"lettura: {', '.join(sorted(non_disponibili))}. "
            "Cio' che manca qui sotto potrebbe esistere lo stesso.")

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
    nascoste = [e for e in casa.get("entita", [])
                if e.get("nascosta") and not e.get("disabilitata")]
    if nascoste:
        n = len(nascoste)
        voce = _plurale(n, "entita' nascosta", "entita' nascoste")
        avvisi.append(
            f"{n} {voce} in Home Assistant: non entrano in «Notevole adesso» "
            "perche' l'utente le ha nascoste, ma esistono e `guarda` le "
            "riporta se gliele chiedi.")

    # IMPORTANT ④: si CONTA, non si elenca -- la stessa regola che il
    # nucleo applica a trecento entita' (vedi il docstring del modulo),
    # applicata qui al modulo stesso. Con cento script `solo_stato` (il
    # caso comunissimo delle scene importate) elencare tutti i nomi
    # sfondava il tetto del 94% da solo, e duplicava un'informazione gia'
    # visibile riga per riga in "Cio' che la casa fa gia' da sola"
    # (`_righe_comportamento` marca ogni voce senza corpo in linea).
    corpi_mancanti = [v for v in comportamento if v.get("corpo") is None]
    if corpi_mancanti:
        n = len(corpi_mancanti)
        voce = _plurale(n, "voce di comportamento", "voci di comportamento")
        avvisi.append(f"{n} {voce} senza corpo disponibile (solo il nome).")

    if problemi_comportamento:
        n = len(problemi_comportamento)
        voce = _plurale(n, "problema", "problemi")
        avvisi.append(
            f"{n} {voce} nella lettura del comportamento (id duplicati, voci "
            "malformate: vedi /api/casa per il dettaglio).")

    if file_non_letti_comportamento:
        nomi = ", ".join(sorted(file_non_letti_comportamento))
        avvisi.append(f"file di comportamento non letti: {nomi}.")

    # `componi()` resta PURA. I nomi dei dispositivi non si vanno a prendere:
    # sono gia' in `casa["dispositivi"]`, la stessa struttura che il chiamante
    # ha letto con `ArchivioCasa.leggi()` (handlers_casa.costruisci_nucleo) e
    # che questa funzione riceve da sempre -- fino a oggi ne buttava via un
    # campo. Nessun archivio aperto, nessuna rete.
    #
    # `None` e non `{}` col registro caduto: la tabella "dispositivi" caduta e'
    # VUOTA, non piccola (`archivio.sostituisci` cancella tutto e reinserisce
    # cio' che e' arrivato), quindi `{}` renderebbe ogni `dispositivo_id` un
    # riferimento al nulla e l'annotazione stamperebbe "(id: ...)" su tutta la
    # casa. La lacuna e' gia' dichiarata negli avvisi e in "cio' che HIRIS
    # ignora": qui si tace, non si inventa. Vedi `_annotazione_dispositivo`.
    if "dispositivi" in non_disponibili:
        nomi_dispositivo: dict[str, str] | None = None
    else:
        nomi_dispositivo = {d["id"]: (d.get("nome") or "")
                            for d in casa.get("dispositivi") or [] if d.get("id")}

    # Un solo albero (`gerarchia()`, con `non_disponibili` applicato),
    # condiviso da "La casa" e da "Notevole adesso": prima di questo fix
    # `_righe_notevole` se ne ricalcolava uno proprio a mano, che poteva
    # dire "Senza area" dove "La casa" -- correttamente -- diceva "Aree non
    # lette" (CRITICAL ①).
    piani = gerarchia(casa, non_disponibili)
    # Il riferimento sta in testa a "La casa" e non in una sezione sua: e' una
    # proprieta' della casa, e una sezione in piu' avrebbe voluto dire un'altra
    # intestazione da spendere per due righe. In testa perche' il taglio parte
    # dal fondo -- e perche' e' la chiave di lettura di tutto cio' che segue.
    righe_sistema = _righe_sistema(sistema_di_riferimento)
    righe_casa = righe_sistema + _righe_casa(piani, nomi_dispositivo)

    inaffidabile = _stato_inaffidabile(casa, stato, stato_affidabile, non_disponibili)
    if inaffidabile:
        avvisi.append(
            "lo stato delle entita' non e' stato letto, o e' stato dichiarato non "
            "attendibile: 'Notevole adesso' qui sotto non dice che va tutto bene, "
            "dice che non si e' potuto guardare.")
    righe_notevole, pesi_notevole, notevole_raggruppato = _righe_notevole(
        casa, stato, piani, inaffidabile)
    righe_comportamento = _righe_comportamento(comportamento)
    righe_ricordi = _righe_ricordi(ricordi)

    # Peso 0 al riferimento: l'intestazione somma i pesi per dire quante righe
    # di conteggio ci sono, e il riferimento non e' un conteggio -- contarlo
    # avrebbe fatto dire al nucleo un numero di aree piu' alto del vero.
    pesi_casa = [0] * len(righe_sistema) + [1] * (len(righe_casa) - len(righe_sistema))
    # La riserva che non si taglia mai vale i CONTEGGI: si alza di quanto
    # occupa il riferimento, cosi' aggiungerlo non toglie in silenzio una riga
    # di casa a chi legge (IMPORTANT (6)).
    riserva_casa = _RISERVA_MINIMA_RIGHE_CASA + len(righe_sistema)
    pesi_comportamento = [1] * len(righe_comportamento)
    pesi_ricordi = [1] * len(righe_ricordi)

    def _sezione_notevole_corrente() -> list[str]:
        # L'intestazione raggruppata (se serve) si ricostruisce dal totale
        # ATTUALMENTE rappresentato dalle righe rimaste, mai da quello
        # originale: dopo un taglio, un'intestazione che afferma il numero
        # di PRIMA sopra righe che ne sommano meno e' il nucleo che si
        # contraddice da solo (IMPORTANT ⑤).
        if notevole_raggruppato and righe_notevole:
            return [_intestazione_notevoli_raggruppati(sum(pesi_notevole))] + righe_notevole
        return list(righe_notevole)

    # L'ordine di STAMPA e' fisso (vedi docstring); l'ordine di TAGLIO e'
    # diverso e definito piu' sotto (`ordine_taglio`).
    sez_casa = ("## La casa", righe_casa)
    sez_notevole = ("## Notevole adesso", _sezione_notevole_corrente())
    sez_comportamento = ("## Cio' che la casa fa gia' da sola", righe_comportamento)
    sez_ricordi = ("## Cio' che le persone hanno detto", righe_ricordi)

    ordine_stampa = [sez_casa, sez_notevole, sez_comportamento, sez_ricordi]

    def _aggiorna_sezione_notevole() -> None:
        ordine_stampa[1] = ("## Notevole adesso", _sezione_notevole_corrente())

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
    ordine_taglio: list[tuple[str, list[str], list[int], int]] = []
    if not inaffidabile:
        ordine_taglio.append(("notevole", righe_notevole, pesi_notevole, 0))
    ordine_taglio += [
        ("comportamento", righe_comportamento, pesi_comportamento, 0),
        ("casa", righe_casa, pesi_casa, riserva_casa),
        ("ricordi", righe_ricordi, pesi_ricordi, 0),
    ]
    # (chiave, frase singolare, frase plurale) GIA' concordate col genere
    # del sostantivo -- vedi il docstring di `_avviso_taglio`.
    etichette_taglio = [
        ("notevole", "elemento notevole non incluso",
                     "elementi notevoli non inclusi"),
        ("comportamento", "voce di comportamento non inclusa",
                          "voci di comportamento non incluse"),
        ("casa", "riga di conteggio della casa non inclusa",
                 "righe di conteggio della casa non incluse"),
        ("ricordi", "ricordo non incluso (il piu' vecchio prima)",
                    "ricordi non inclusi (i piu' vecchi prima)"),
    ]

    troncato = False
    esclusi_per_pool: dict[str, int] = {}

    def _pop(nome_pool: str, righe_pool: list[str], pesi_pool: list[int], riserva: int) -> None:
        # IMPORTANT ⑤: si conta il PESO (quante entita'/elementi la riga
        # rappresenta davvero -- per "notevole" raggruppato puo' essere
        # molto piu' di 1), non la riga. Sottostimare l'escluso di nove
        # volte sulla lacuna piu' calda della casa e' peggio di non
        # dichiararlo affatto: sembra onesto e non lo e'.
        nonlocal troncato
        righe_pool.pop()  # dalla coda: l'ultima voce e' la meno prioritaria
        peso = pesi_pool.pop()
        troncato = True
        esclusi_per_pool[nome_pool] = esclusi_per_pool.get(nome_pool, 0) + peso
        if nome_pool == "notevole":
            _aggiorna_sezione_notevole()
        if nome_pool == "casa":
            # MINOR: un'intestazione di piano ("Primo piano:") senza righe
            # sotto e' un artefatto del taglio, non un'informazione -- si
            # toglie a sua volta. Non conta come elemento escluso: le aree
            # che c'erano sotto sono gia' state contate ai loro rispettivi
            # pop, questo e' solo il titolo rimasto orfano.
            while (len(righe_pool) > riserva and righe_pool
                   and righe_pool[-1].endswith(":") and not righe_pool[-1].startswith("  ")):
                righe_pool.pop()
                pesi_pool.pop()

    # IMPORTANT ④: il budget per casa/notevole/comportamento/ricordi non e'
    # `tetto - _RISERVA_SEZIONE_LACUNE` alla cieca. Se le lacune GIA' note
    # (registri caduti, corpi mancanti, problemi di comportamento, stato
    # inaffidabile...) pesano gia' piu' della riserva stimata, il budget per
    # il resto si restringe di conseguenza -- altrimenti il resto del
    # nucleo occuperebbe uno spazio che le lacune, gia' dichiarate, non
    # avrebbero avuto, e la rete di sicurezza sotto sarebbe l'unica cosa a
    # farsi carico dello sforamento.
    lunghezza_lacune_note = len(_assembla([("## Cio' che HIRIS ignora", _righe_lacune(avvisi))]))
    riserva_lacune = max(_RISERVA_SEZIONE_LACUNE, lunghezza_lacune_note + _RISERVA_SEZIONE_LACUNE)
    budget = max(0, tetto - riserva_lacune)

    for nome_pool, righe_pool, pesi_pool, riserva in ordine_taglio:
        while len(righe_pool) > riserva and len(_assembla(ordine_stampa)) > budget:
            _pop(nome_pool, righe_pool, pesi_pool, riserva)
        if len(_assembla(ordine_stampa)) <= budget:
            break

    # L'indice dell'avviso di taglio dentro `avvisi`, se e quando esiste --
    # serve a poterlo RISCRIVERE (rete di sicurezza sotto) senza rischiare
    # di sovrascrivere un avviso diverso che gli stesse accanto (es. i
    # corpi mancanti), che una sostituzione posizionale "ultimo elemento"
    # romperebbe silenziosamente se il taglio scattasse solo piu' avanti.
    indice_avviso_taglio = None
    if troncato:
        avvisi.append(_avviso_taglio(esclusi_per_pool, etichette_taglio, tetto))
        indice_avviso_taglio = len(avvisi) - 1

    sez_lacune = ("## Cio' che HIRIS ignora", _righe_lacune(avvisi))
    testo = _assembla(ordine_stampa + [sez_lacune])

    # Rete di sicurezza: se anche cosi' il testo sfora, si continua a
    # tagliare -- ricordi prima (gia' l'ultima cosa nell'ordine di taglio),
    # ma NON SOLO ricordi (IMPORTANT ④): una casa con pochi o zero ricordi
    # che sfora lo stesso (es. lacune cresciute oltre ogni stima) non deve
    # fermarsi solo perche' "non ci sono piu' ricordi da tagliare" --
    # sforerebbe il tetto in silenzio, che e' peggio di un taglio
    # dichiarato in piu'. Si scende fino alla riserva minima della mappa;
    # oltre quella, mai (IMPORTANT ⑥): sforare il tetto in modo dichiarato
    # e' meno grave che svuotare anche la mappa in silenzio.
    pools_sicurezza = [
        ("ricordi", righe_ricordi, pesi_ricordi, 0),
        ("comportamento", righe_comportamento, pesi_comportamento, 0),
        ("casa", righe_casa, pesi_casa, riserva_casa),
    ]
    if not inaffidabile:
        pools_sicurezza.append(("notevole", righe_notevole, pesi_notevole, 0))

    while len(testo) > int(tetto * 1.1):
        tagliato = False
        for nome_pool, righe_pool, pesi_pool, riserva in pools_sicurezza:
            if len(righe_pool) > riserva:
                _pop(nome_pool, righe_pool, pesi_pool, riserva)
                tagliato = True
                break
        if not tagliato:
            break
        messaggio = _avviso_taglio(esclusi_per_pool, etichette_taglio, tetto)
        if indice_avviso_taglio is None:
            avvisi.append(messaggio)
            indice_avviso_taglio = len(avvisi) - 1
        else:
            avvisi[indice_avviso_taglio] = messaggio
        sez_lacune = ("## Cio' che HIRIS ignora", _righe_lacune(avvisi))
        testo = _assembla(ordine_stampa + [sez_lacune])

    ricordi_esclusi = esclusi_per_pool.get("ricordi", 0)

    riepilogo = {
        "caratteri": len(testo),
        "troncato": troncato,
        "ricordi_esclusi": ricordi_esclusi,
        "avvisi": avvisi,
    }
    return testo, riepilogo
