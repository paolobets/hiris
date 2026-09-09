from __future__ import annotations

import logging
import re

from ..home_space import type_vocabulary
from ..home_space.topology import domain_of
from ._sanitize import sanitize_ha_value

logger = logging.getLogger(__name__)

# `NOISE_DOMAINS` e' uscito con `get_all_useful`, il suo unico lettore.

# Messaggi per chi legge l'inventario quando l'inventario non e' leggibile.
# Un elenco vuoto direbbe "la casa e' vuota"; questi dicono "non ho potuto
# guardare", che e' l'unica frase vera. I due casi restano distinti perche'
# suggeriscono all'utente due cose diverse: uno e' configurazione mancante,
# l'altro passa da solo (il lavoro periodico di ricarica ritenta).
#
# Vivono qui, accanto alla bandiera `loaded` che li governa, perche' duplicarne
# il testo era esattamente il modo in cui il difetto e' sopravvissuto nei
# fratelli. Al momento in cui questi messaggi sono nati li usavano quattro
# moduli (dispatcher, ha_tools, briefing, api/handlers_entities): i primi tre
# sono usciti nella demolizione (rispettivamente 68d3670, bca1b85, 2441b7d) --
# oggi il solo lettore di produzione e' `api/handlers_entities.py`, via
# `unreadable_inventory_error()` sotto.
NO_INVENTORY_ERROR = (
    "Non sono riuscito a leggere lo stato della casa: l’inventario delle "
    "entità non è disponibile. Non posso dire che non ci sia nulla, solo che "
    "non ho potuto controllare."
)
INVENTORY_NOT_READY_ERROR = (
    "Non sono riuscito a leggere lo stato della casa: l’inventario delle "
    "entità non è ancora pronto (la lettura iniziale da Home Assistant non è "
    "andata a buon fine o è ancora in corso). Riprova fra poco."
)


def inventory_is_readable(cache) -> bool:
    """True quando dalla cache si puo' leggere un inventario che vale come
    fotografia della casa.

    `getattr(..., True)`: una cache finta senza l'attributo `loaded` (i doppi
    usati nei test e nel cablaggio esistente) e' considerata pronta, cosi'
    questa distinzione non ne rompe nessuna.
    """
    return cache is not None and bool(getattr(cache, "loaded", True))


def automation_config_id(cache, entity_id: str) -> str | None:
    """L'id di CONFIGURAZIONE dell'automazione `entity_id`, o `None` se non
    si riesce a ricavarlo.

    **Perche' esiste, e perche' sta qui.** Home Assistant archivia le tracce
    di un'automazione sotto `automation.<id della configurazione>`, non sotto
    il suo `object_id` (catena verificata sui tag `2024.7.0` e `2026.9.0`,
    scritta per esteso in `HAClient.automation_traces()`). L'unico posto in
    cui quell'id vive gia', senza aprire un secondo rubinetto verso Home
    Assistant, e' lo specchio dello stato: `_to_minimal` lo porta in
    `automation_id`. I due chiamanti che devono risolverlo -- il collettore
    delle tracce in `server.py` e lo strumento `automation_trace` in
    `home_space/tools.py` -- farebbero altrimenti la stessa scansione due
    volte, in due file diversi: e' un solo posto, come per
    `inventory_is_readable` qui sopra.

    **`None` significa «non riesco a risolvere», MAI «non ha mai girato».**
    Sono tre casi distinti e nessuno dei tre e' un fatto sull'automazione:
    lo specchio non e' cablato o non e' ancora pronto; l'entita' non c'e'
    (nome sbagliato, o automazione appena creata che lo specchio non ha
    ancora visto); l'automazione esiste ma la sua configurazione non ha
    `id:` (YAML scritto a mano) e allora `attributes["id"]` non esiste
    proprio -- le sue tracce finiscono sotto la chiave condivisa
    `"automation.None"` e non sono indirizzabili per automazione. Chi chiama
    deve DIRLO, non ripiegare sull'`object_id`: un elenco vuoto e un id
    irrisolto sono due cose diverse.

    `getattr(..., None)` su `all_states` per la stessa ragione di
    `inventory_is_readable`: una cache finta senza quel metodo non deve far
    sollevare un lettore, deve risultare «non risolvibile».
    """
    if not inventory_is_readable(cache):
        return None
    all_states = getattr(cache, "all_states", None)
    if not callable(all_states):
        return None
    for state in all_states() or []:
        if not isinstance(state, dict) or state.get("id") != entity_id:
            continue
        automation_id = state.get("automation_id")
        return automation_id if isinstance(automation_id, str) and automation_id else None
    return None


def unreadable_inventory_error(cache) -> dict | None:
    """None se l'inventario e' utilizzabile, altrimenti l'errore da restituire
    subito al chiamante.

    Tre casi, due esiti. Cache assente (mai cablata) e cache presente ma mai
    caricata sono entrambe un guasto: non abbiamo potuto guardare. Cache
    caricata e vuota e' invece un risultato legittimo -- una casa senza
    entita', o senza luci accese, esiste davvero -- e prosegue.
    """
    if cache is None:
        logger.warning("lettura entita' rifiutata: nessun inventario configurato")
        return {"error": NO_INVENTORY_ERROR}
    if not inventory_is_readable(cache):
        logger.warning("lettura entita' rifiutata: inventario non ancora caricato")
        return {"error": INVENTORY_NOT_READY_ERROR}
    return None


# Una lettura sola per tutti, in `home_space/topology.domain_of`: era scritta sei
# volte, e due copie non erano d'accordo su un id senza punto.
_domain = domain_of


# --------------------------------------------------------------------------
# L'EREDITA': tutto cio' che Home Assistant espone di un'entita', separato in
# sei ceste invece di essere buttato in tre quarti.
# --------------------------------------------------------------------------
#
# **Cosa c'era prima, e perche' non poteva funzionare.** Fino al 07/09/2026
# questa proiezione teneva `_DOMAIN_ATTRS`: una lista di AMMESSI scritta a
# mano, NOVE domini su trenta, e per quei nove i soli valori correnti. Tutto
# il resto veniva buttato prima ancora di arrivare a chiunque. Misurato sulla
# casa vera il 07/09/2026, eseguendo il codice sul payload di
# `GET /api/states` (835 entita', 30 domini, 278 coppie dominio-attributo):
#
#   - attributi consegnati a **51 entita' su 835**, 2.582 byte in tutto;
#   - `light.alberello` espone `supported_color_modes`, `min/max_color_temp_
#     kelvin` (1500/9000), tre effetti -- e consegnava `{'brightness': None}`,
#     cioe' «questa luce non ha luminosita'» mentre era solo spenta;
#   - `climate.camera_t_camera_t` espone `hvac_modes` (sa raffrescare),
#     `min_temp`/`max_temp` (5-40), `target_temp_step` (0,5) -- e consegnava
#     tre valori correnti e nessun campo di manovra;
#   - `sun.sun` e `update.adguard_home` valevano **2 byte**: `{}`;
#   - tre chiavi della lista erano MORTE NEL SORGENTE di Home Assistant, non
#     solo assenti qui: `climate.hvac_mode` (e' lo `state`,
#     `components/climate/__init__.py:289-299`), `light.color_temp`
#     (sopravvive solo come VALORE di `ColorMode`), `valve.reports_position`
#     (zero occorrenze nel componente). Una chiave che non trattiene niente
#     non fa rumore: nessuno se n'era accorto.
#
# **Il requisito che la sostituisce**, dettato dal proprietario il 07/09/2026
# (`docs/design/2026-09-07-l-anagrafe-dei-tipi.md` §12): «*vorrei che di
# un'entita' vengano ereditati da HIRIS tutti gli attributi, per capire fino
# in fondo cosa puo' fare e cosa sta facendo ora*». Il metro di accettazione:
# HIRIS deve poter capire di un dispositivo cio' che Home Assistant capisce.
# Il volume non e' mai stato il problema -- 121 KB per tutte le 835 entita'.
#
# **Quindi non c'e' piu' nessuna lista di ammessi qui**, e non ce ne puo'
# tornare una: cio' che arriva viene ereditato per intero e SMISTATO. Le
# sei ceste rispondono a domande diverse, e tenerle separate e' la sola
# cosa che questa funzione decide:
#
#   `capabilities`   cosa l'entita' PUO' fare -- il campo di manovra
#   `members`        DI COSA e' fatta -- i membri, quando e' un gruppo
#   `assumable`      cosa puo' ASSUMERE, che non e' cosa le si puo' imporre
#   `values`         com'e' ADESSO
#   `uninterpreted`  cio' di cui nessuna fonte pubblica dichiara il significato
#   `credentials`    token e maniglie: ereditate e usabili, mai scritte in chat
#
# La separazione fra le prime due **non e' nostra**: la fa Home Assistant, che
# tiene `capability_attributes` e `state_attributes` distinte fino all'ultimo
# momento (`helpers/entity.py:787-794`, `:810-828`, fuse a `:1109-1124`) e le
# pubblica per dominio come `StrEnum` dal `2026.9.1`. Il dizionario che dice
# quale nome sta di qua e quale di la' vive nel vocabolario dei tipi, con
# provenienza `importato` e la versione da cui viene
# (`home_space/type_vocabulary.py`, metrica 4).
#
# `uninterpreted` e' la cesta che rende il requisito onesto: gli otto `ave_*`
# dei termostati AVE, i `marker_*`, `days_until`, `next_date` della raccolta
# differenziata escono lo stesso, ma NON mescolati alle capacita'. Verificato
# il 07/09/2026: `ave_window_state` vuol probabilmente dire «finestra aperta»,
# e **nessuna fonte pubblica lo dichiara** -- l'integrazione `ave_domina` non
# e' in Home Assistant core (manifest 404 al tag), non e' un repository
# pubblico su GitHub, e l'unica AVE pubblica (`emmeoerre/ave_dominaplus`)
# emette nomi diversi a ogni versione (zero occorrenze su cinque tag). Quel
# significato non si indovina: consegnarlo accanto a `hvac_modes` come se
# fosse la stessa qualita' di sapere sarebbe ripetere il difetto del
# termostato (`hvac_mode: heat` letto come «sta scaldando»), un piano sotto.


# Cio' che questa proiezione PROMUOVE a chiave propria, e che quindi non si
# ripete anche nelle ceste: sarebbe lo stesso fatto in due case
# (fondamenta 2). Non e' una trattenuta -- il valore e' nello stesso oggetto,
# una riga piu' su.
_ATTRIBUTES_PROMOTED_TO_THEIR_OWN_KEY = frozenset({
    "friendly_name",        # -> `name`
    "unit_of_measurement",  # -> `unit`
    "device_class",         # -> `device_class`
    "state_class",          # -> `state_class`
})


# LE CREDENZIALI E LE MANIGLIE -- l'unica famiglia che HIRIS eredita e NON
# scrive nel testo che il modello riceve.
#
# **Non e' un'eccezione al requisito**: la cesta `credentials` porta i valori
# veri, e chi in HIRIS deve usarli li trova li'. E' una scelta a valle, sul
# solo confine del modello, e ha una ragione operativa precisa: una
# trascrizione di chat si salva su disco e ci resta. Un token della telecamera
# scritto li' dentro ci resta con lei. Quindi nel testo che va al modello
# compare la FRASE -- «questa entita' porta un token di accesso al flusso
# video» -- invece della chiave: il fatto c'e', la credenziale no.
#
# **E la trattenuta e' dichiarata, mai muta.** `_view_entity` la mostra come
# `attributi.trattenuti`, nome per nome, con la ragione. Questo prodotto ha
# gia' pagato una volta «l'assenza NOSTRA spacciata per silenzio del
# fornitore»: un modello che non vede niente conclude che non c'e' niente.
#
# Misurato sulla casa vera il 07/09/2026: 19 coppie, 293 occorrenze -- 62 MAC,
# 62 nomi host, 61 indirizzi IP, 26 SSID, 18 numeri di serie, 9 token di
# telecamera, 9 URL con il token dentro. Le ragioni sono in italiano perche'
# e' testo che una persona (e il modello) legge.
#
# Dove Home Assistant li dichiara: `access_token` e'
# `CameraEntityStateAttribute.ACCESS_TOKEN` (`components/camera/const.py`) e
# `ImageEntityStateAttribute.ACCESS_TOKEN`; `entity_picture` e'
# `EntityStateAttribute.ENTITY_PICTURE` (`homeassistant/const.py:470-483`),
# cioe' un attributo che QUALUNQUE entita' puo' portare; `mac`/`ip`/
# `host_name` sono `ScannerEntityStateAttribute`
# (`components/device_tracker/const.py`). `vpn_url`/`local_url` no: sono di
# Netatmo, fuori standard -- ed e' il motivo per cui accanto ai nomi serve
# anche una regola sul VALORE.
_CREDENTIAL_ATTRIBUTES: dict[str, str] = {
    "access_token": "un token di accesso al flusso di questa entita'",
    "entity_picture": "un indirizzo di immagine che puo' contenere un token",
    "entity_picture_local": "un indirizzo di immagine che puo' contenere un token",
    "vpn_url": "un indirizzo remoto raggiungibile con la credenziale nel percorso",
    "local_url": "un indirizzo locale con la stessa credenziale",
    "uri_supported": "un indirizzo interno del dispositivo",
    "mac": "l’indirizzo MAC del dispositivo",
    "ip": "l’indirizzo IP sulla rete di casa",
    "host_name": "il nome host del dispositivo",
    "ssid": "il nome della rete Wi-Fi",
    "bssid": "l’indirizzo MAC dell’access point",
    "user_id": "l’identificativo dell’account Home Assistant",
    "last_scanned_by_device_id": "l’identificativo del dispositivo che ha letto il tag",
    "serial": "il numero di serie del dispositivo",
    "media_content_id": "l’indirizzo del contenuto, con la chiave della sessione dentro",
}

# La ragione con cui esce cio' che nessun nome della tabella prevedeva.
_CREDENTIAL_BY_VALUE = (
    "un valore che contiene una credenziale (un indirizzo con `token=`, "
    "una chiave esadecimale, o un indirizzo MAC)")

# LA REGOLA SUL VALORE, e non e' un lusso: `vpn_url` e `local_url` sono nomi
# che nessuna costante di Home Assistant contiene, e il prossimo fornitore
# chiamera' la stessa cosa in un terzo modo. Tre forme, tutte misurate sulla
# casa vera:
#   - un indirizzo con `token=` o `access_token=` (l'`entity_picture` di una
#     camera e di un Sonos);
#   - un segmento esadecimale di 32 cifre o piu' (un token nudo);
#   - un indirizzo MAC (`camera.id` su Netatmo vale `70:ee:50:26:b5:4e`, e li'
#     la chiave si chiama `id` -- nessun elenco di nomi lo prenderebbe).
_TOKEN_IN_URL = re.compile(r"[?&](?:access_)?token=", re.IGNORECASE)
_HEXADECIMAL_SECRET = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32,}(?![0-9a-fA-F])")
_MAC_ADDRESS = re.compile(r"^(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}$")


def _is_credential(name: str, value) -> bool:
    """Se questo attributo va trattenuto dal testo che il modello riceve.

    Per NOME o per VALORE, e i due non sono la stessa difesa: il nome copre
    cio' che Home Assistant dichiara, il valore copre cio' che un fornitore
    inventa. `update.entity_picture` e' trattenuto pur non portando token su
    questa casa (sono icone `/api/brands/...`): la regola si scrive sulla
    chiave, perche' la STESSA chiave porta un token su `camera`, `image` e
    `media_player`. E' una perdita accettata, non un'assenza.
    """
    if name in _CREDENTIAL_ATTRIBUTES:
        return True
    if not isinstance(value, str):
        return False
    return bool(_TOKEN_IN_URL.search(value) or _HEXADECIMAL_SECRET.search(value)
                or _MAC_ADDRESS.match(value.strip()))


def _has_nothing_to_say(value) -> bool:
    """Una chiave che non ha niente da dire non esce -- legge del prodotto.

    **Il `None` e' il caso misurato, e non e' «meno»: e' peggio di niente.**
    `light.alberello` consegnava `{'brightness': None}` e a un modello si legge
    «questa luce non ha luminosita'», mentre la luce era solo spenta. Home
    Assistant manda `brightness: None` su 10 delle 50 luci di questa casa
    proprio perche' sono spente.

    Un contenitore vuoto per la stessa ragione: `options: []` non e' un elenco
    di scelte, e' l'assenza di un elenco. `0`, `0.0` e `False` invece PARLANO
    -- `wind_bearing: 0` e' nord, `is_volume_muted: False` e' «non e' muto» --
    e non sono toccati da questa funzione.
    """
    if value is None:
        return True
    return isinstance(value, (str, list, tuple, dict, set, frozenset)) and not value


def _sanitized(value):
    """Ogni stringa che arriva da Home Assistant, filtrata -- non piu' un
    elenco di chiavi «di testo libero».

    Fino a questa fetta la difesa era `_FREE_TEXT_ATTRIBUTES`, tre nomi scelti
    a mano (`media_title`, `media_artist`, `source`). Con l'eredita' intera
    quell'elenco avrebbe dovuto crescere almeno a quattordici -- e sarebbe
    stata la stessa lista di ammessi di `_DOMAIN_ATTRS`, con lo stesso destino:
    `extra_state_attributes` e' aperta per costruzione, quindi il prossimo
    campo di testo libero non e' prevedibile. Misurato su questa casa:
    `event.voice_command` porta le frasi dette ad Alexa in chiaro,
    `update.release_summary` porta il testo che il fornitore ci scrive,
    `calendar.message` e `calendar.description` portano quello che l'utente
    scrive in agenda.

    Il criterio diventa quindi la FORMA e non il nome: **se e' una stringa che
    arriva da fuori, passa dal filtro**. Numeri, booleani e istanti non lo
    attraversano -- convertirli in stringa non chiude nessun rischio vero
    (C-2, L1-sicurezza.md).
    """
    if isinstance(value, str):
        return sanitize_ha_value(value)
    if isinstance(value, list):
        return [_sanitized(item) for item in value]
    if isinstance(value, dict):
        return {k: _sanitized(v) for k, v in value.items()}
    return value


#: I nomi delle sei ceste. Scritti una volta: una cesta cercata con una
#: stringa sbagliata risponderebbe «vuota» invece di sbagliare.
CAPABILITIES = "capabilities"
VALUES = "values"
UNINTERPRETED = "uninterpreted"
CREDENTIALS = "credentials"

#: La quinta, nata con la fetta dell'azione (07/09/2026): cosa questa entita'
#: puo' ASSUMERE, che non e' cosa le si puo' IMPORRE. `sensor.options` e
#: `select.options` uscivano sotto la stessa etichetta ed erano gia' due cose
#: diverse -- per chi legge una sfumatura, per chi comanda la differenza fra
#: un'azione possibile e una impossibile. La separazione e' alla FONTE
#: (`type_vocabulary.assumable_attributes`), non qui a valle: qui si legge
#: soltanto il giudizio gia' preso.
ASSUMABLE = "assumable"

#: La sesta, nata il 09/09/2026: DI COSA questa entita' e' fatta -- i membri,
#: quando e' un gruppo. Non e' una sfumatura del campo di manovra: e'
#: un'altra domanda. `light.lampadario_sala_da_pranzo` consegnava i suoi tre
#: membri sotto `entity_id` DENTRO le capacita', accanto a `effect_list` e a
#: `supported_color_modes` -- cioe' accanto ai parametri veri di
#: `light.turn_on` -- e chi legge poteva crederlo un parametro. La
#: separazione e' alla FONTE (`type_vocabulary.group_membership_attributes`,
#: con la ragione scritta voce per voce), non un `if` su un nome qui a valle.
MEMBERS = "members"

#: L'ordine in cui si leggono le cinque ceste che possono arrivare al modello.
#: I membri ci sono dentro: non sono una credenziale, e chi cerca un attributo
#: per nome -- l'impronta di un'azione, per dirne una -- deve trovarli. Un
#: gruppo a cui si toglie una luce E' cambiato, e un'impronta che non lo
#: vedesse direbbe «non e' successo niente».
_DISCLOSABLE_BASKETS = (CAPABILITIES, MEMBERS, ASSUMABLE, VALUES, UNINTERPRETED)


def inherited_attributes(raw_attributes: dict, domain: str) -> dict[str, dict]:
    """Gli attributi grezzi di un'entita' -> le sei ceste.

    **Nessun attributo sparisce**: ognuno finisce in una cesta, oppure e' gia'
    uscito da una chiave propria di `_to_minimal` (`friendly_name` -> `name`,
    ...), oppure non aveva niente da dire (`None`, elenco vuoto). Non c'e' un
    quarto esito, ed e' cio' che una prova verifica sui due casi veri della
    casa (`tests/test_inherited_attributes.py`).

    Le ceste vuote non compaiono: `{}` per una cesta e' l'assenza di quella
    cesta, e scriverla direbbe «ho guardato e non c'e' niente» su ogni entita'
    della casa.
    """
    capability_names = type_vocabulary.capability_attributes(domain)
    membership_names = type_vocabulary.group_membership_attributes()
    assumable_names = type_vocabulary.assumable_attributes(domain)
    declared_values = type_vocabulary.state_attributes(domain)
    baskets: dict[str, dict] = {}
    for name, value in raw_attributes.items():
        if not isinstance(name, str) or name in _ATTRIBUTES_PROMOTED_TO_THEIR_OWN_KEY:
            continue
        if _has_nothing_to_say(value):
            continue
        if _is_credential(name, value):
            basket = CREDENTIALS
        elif name in capability_names:
            basket = CAPABILITIES
        # I MEMBRI, e non fra le capacita': «di cosa sono fatto» non e' «cosa
        # mi si puo' chiedere». Anche questo insieme e' DISGIUNTO da quello
        # delle capacita' per costruzione -- e' l'anagrafe a sottrarli
        # (`capability_attributes`), non l'ordine di questi rami.
        elif name in membership_names:
            basket = MEMBERS
        # I due insiemi sono DISGIUNTI per costruzione -- e' l'anagrafe dei
        # tipi a togliere dalle capacita' cio' che dichiara assumibile
        # (`capability_attributes`), non l'ordine di questi rami. Un ordine
        # che decidesse al posto della fonte renderebbe invisibile una
        # sovrapposizione: la separazione sta in un posto solo, e qui si
        # legge il giudizio gia' preso.
        elif name in assumable_names:
            basket = ASSUMABLE
        elif name in declared_values:
            basket = VALUES
        else:
            basket = UNINTERPRETED
        baskets.setdefault(basket, {})[name] = _sanitized(value)
    return baskets


def disclosable_attributes(attributes) -> dict:
    """Le cinque ceste che possono arrivare al modello, in un dizionario
    piatto: capacita', membri, cio' che l'entita' puo' assumere, valori
    correnti e non interpretati. **Le credenziali no.**

    Esiste perche' i lettori che devono CERCARE un attributo per nome --
    `hvac_action` per lo stato leggibile, `supported_color_modes` per sapere
    se un parametro di servizio si applica, l'impronta di un'azione -- non
    debbano sapere in quale cesta sta: la cesta e' una distinzione per chi
    legge il risultato, non un labirinto per chi legge il codice.

    E le credenziali restano fuori anche di qui, per una ragione in piu' della
    chat: un token di telecamera RUOTA. Nell'impronta di un'azione
    (`action/actuator._fingerprint`) farebbe risultare «cambiata» ogni camera
    a ogni comando, che e' inventare un cambiamento -- il verso opposto del
    difetto che quell'impronta esiste per chiudere.
    """
    if not isinstance(attributes, dict):
        return {}
    flat: dict = {}
    for basket in _DISCLOSABLE_BASKETS:
        content = attributes.get(basket)
        if isinstance(content, dict):
            flat.update(content)
    return flat


def group_members(attributes) -> tuple[str, ...]:
    """Gli id delle entita' di cui questa e' fatta, quando e' un gruppo.
    Una tupla vuota quando non lo e'.

    **Le due forme si fondono qui**, e non a valle: a `2026.9.1` Home
    Assistant scrive i membri sotto `group_entities` oppure sotto la forma
    vecchia `entity_id`, e `components/group/entity.py:43-45` le nomina
    entrambe. Chi legge i membri non deve sapere quale delle due gli e'
    arrivata -- e sulla casa vera, misurata il 09/09/2026, l'unico gruppo
    delle 837 entita' porta la vecchia.

    L'ordine e' quello che Home Assistant ha mandato, i doppioni cadono: un
    membro nominato due volte e' un membro, e contarlo due volte
    falserebbe ogni «uno dei tre» che si dice di quel gruppo.
    """
    if not isinstance(attributes, dict):
        return ()
    carried = attributes.get(MEMBERS)
    if not isinstance(carried, dict):
        return ()
    members: list[str] = []
    for name in sorted(carried):
        value = carried[name]
        if not isinstance(value, (list, tuple)):
            continue
        for member in value:
            if isinstance(member, str) and member and member not in members:
                members.append(member)
    return tuple(members)


def withheld_credentials(attributes) -> dict[str, str]:
    """Nome -> ragione, per le credenziali che questa entita' porta e che non
    si scrivono nel testo del modello. Vuoto quando non ne porta nessuna.

    **E' la trattenuta resa visibile**, ed e' la condizione perche' la
    trattenuta sia lecita: senza questa vista il modello leggerebbe un'entita'
    con un token come una che non ne ha, e `camera.ingresso_cancellino`
    uscirebbe identica a `button.identifica` -- che non lo sono affatto.
    """
    if not isinstance(attributes, dict):
        return {}
    carried = attributes.get(CREDENTIALS)
    if not isinstance(carried, dict):
        return {}
    return {name: _CREDENTIAL_ATTRIBUTES.get(name, _CREDENTIAL_BY_VALUE)
            for name in sorted(carried)}


def _to_minimal(raw: dict) -> dict:
    attrs = raw.get("attributes") or {}
    eid = raw["entity_id"]
    dom = _domain(eid)
    result: dict = {
        "id": eid,
        # Il confine con Home Assistant: `state` e `friendly_name` sono
        # testo che l'entita' porta con se' e che HIRIS non controlla -- il
        # nome di un dispositivo che un ospite ha messo in rete, lo stato di
        # un sensore-messaggio (email/ntfy/SMS). Sanificarli QUI, nell'unico
        # punto in cui uno stato grezzo diventa cio' che ogni lettore vede
        # (`live_mirror`, `guarda`, `cerca`, il nucleo), significa che
        # nessun consumatore a valle deve ricordarsene da solo (C-2,
        # L1-sicurezza.md).
        "state": sanitize_ha_value(raw.get("state", "unknown")),
        "name": sanitize_ha_value(attrs.get("friendly_name") or ""),
        "unit": attrs.get("unit_of_measurement") or "",
        "domain": dom,
        "device_class": attrs.get("device_class"),
        # `state_class` (`measurement`, `total`, `total_increasing`) dice se un
        # numero e' una misura di adesso o un contatore che sale -- ed e' cio'
        # che dice a quali entita' si puo' chiedere una statistica, SENZA
        # doverlo domandare al recorder. Arrivava a ogni avvio dentro gli
        # attributi di ogni sensore, e questa proiezione lo buttava.
        # Il nome e' `sensor.const.ATTR_STATE_CLASS`, verificato.
        "state_class": attrs.get("state_class"),
        # `last_changed` arriva a OGNI cambio di stato e questa proiezione lo
        # buttava: HIRIS sapeva che in camera ci sono 22,4 gradi e non sapeva
        # da quando -- non poteva nemmeno dire «e' fermo da tre ore». Costa un
        # campo e zero chiamate a Home Assistant.
        # `last_changed` e non `last_updated`: il secondo si muove anche quando
        # cambia solo un attributo, e «da quando e' accesa» diventerebbe «da
        # quando qualcuno ne ha toccato la luminosita'».
        "last_changed": raw.get("last_changed"),
    }
    # L'id della CONFIGURAZIONE di un'automazione (`attributes["id"]`), che
    # NON e' l'`object_id` dell'entita' e che senza questa riga si perdeva
    # nella proiezione. E' la chiave con cui Home Assistant archivia le
    # tracce (`automation.<id di configurazione>`, catena verificata sui tag
    # `2024.7.0` e `2026.9.0` nel docstring di
    # `HAClient.automation_traces()`), quindi senza di essa lo specchio non
    # puo' rispondere alla domanda «come e' andata questa automazione?».
    #
    # E' PROMOSSA a chiave propria, e per questo esce dalle ceste degli
    # attributi -- stessa ragione di `friendly_name` e compagni, ma per un
    # dominio solo, e per questo la sottrazione e' scritta qui invece che in
    # `_ATTRIBUTES_PROMOTED_TO_THEIR_OWN_KEY`: su `person` `id` e' un attributo
    # dichiarato (`PersonEntityStateAttribute.ID`) e deve restare fra i valori.
    # Un timbro numerico di configurazione davanti al modello sarebbe rumore;
    # qui e' una chiave di giunzione per il codice.
    #
    # `attributes["id"]` c'e' solo quando l'automazione ha un `id:` nella sua
    # configurazione: `BaseAutomationEntity.capability_attributes` torna
    # `None` se `unique_id is None` (stessi due tag), e le capability
    # attributes entrano negli attributi dello stato via
    # `helpers/entity.py::__async_calculate_state`. Un'automazione YAML
    # scritta senza `id:` non ne ha, e chi legge deve dire «non riesco a
    # risolverla», non ripiegare sull'`object_id`.
    #
    # Solo su `automation`: una `scene` porta anch'essa un `attributes["id"]`
    # (`components/homeassistant/scene.py`), ma li' non e' la chiave delle
    # tracce -- le scene non ne hanno -- e raccoglierlo lo stesso metterebbe
    # in circolo un `automation_id` che non lo e'.
    if dom == "automation":
        automation_id = attrs.get("id")
        if isinstance(automation_id, str) and automation_id:
            result["automation_id"] = automation_id
            attrs = {k: v for k, v in attrs.items() if k != "id"}
    baskets = inherited_attributes(attrs, dom)
    if baskets:
        result["attributes"] = baskets
    return result


class EntityCache:
    # `_by_domain` (entity_id per dominio) e' USCITO l'09/09/2026: era
    # scritto in tre punti e letto in NESSUNO. Il commento che lo teneva in
    # piedi diceva «lo popola e lo legge `_index`», e `_index` non esiste su
    # HEAD -- il suo ultimo lettore era `get_by_domain`, uscito col censimento
    # del 17/08/2026. Aggiungerne la manutenzione anche nel ramo della
    # rimozione (sotto) sarebbe stato lavoro morto fatto da codice vivo.
    def __init__(self) -> None:
        self._states: dict[str, dict] = {}
        # False finche' load() non ha completato almeno una volta. Serve a
        # distinguere "inventario non ancora pronto" da "casa senza entita'":
        # server.py logga e prosegue se il caricamento iniziale fallisce, e i
        # tool che leggono da qui rispondevano con un elenco vuoto in entrambi
        # i casi ("la casa e' vuota"). Il controllo comune era
        # `ToolDispatcher._cache_non_leggibile`, uscito -- fetta E2 Task 7.
        self._loaded = False

    @property
    def loaded(self) -> bool:
        """True quando `load()` e' andata a buon fine almeno una volta.

        Solo allora un inventario vuoto significa davvero "nessuna entita'".
        `on_state_changed` NON alza questa bandiera di proposito: gli eventi
        arrivati dopo un caricamento fallito descrivono le poche entita' che si
        sono mosse, non la casa, e spacciarli per inventario completo
        riaprirebbe -- in forma piu' subdola -- lo stesso "la casa e' vuota".
        """
        return self._loaded

    async def load(self, ha_client) -> None:
        raw_states = await ha_client.get_states([])
        self._states = {}
        for raw in raw_states:
            eid = raw.get("entity_id")
            if not eid:
                continue
            self._states[eid] = _to_minimal(raw)
        # Solo dopo che la lettura e' arrivata in fondo: se get_states solleva,
        # la cache resta dichiaratamente non pronta.
        self._loaded = True

    def on_state_changed(self, event_data: dict) -> None:
        """L'unico rubinetto che tiene vivo lo specchio: `state_changed`.

        **Un `new_state` assente e' una RIMOZIONE, non un evento da buttare**
        (audit delle fondamenta, rilievo 7). Fonte, letta al tag `2026.9.1`:
        `homeassistant/core.py::StateMachine.async_remove` toglie l'entita'
        dalla macchina degli stati e emette `EVENT_STATE_CHANGED` con
        `{"entity_id": ..., "old_state": <State>, "new_state": None}` -- e'
        l'UNICO segnale che Home Assistant manda quando un'entita' sparisce, e
        fino all'09/09/2026 HIRIS lo scartava con un `return` muto. Nessun
        altro percorso toglieva una voce: `server.reload_entity_inventory`
        rilegge solo se il caricamento iniziale era fallito, e la
        riconnessione WS rifa' l'anagrafe e i servizi, non lo specchio.

        Il danno non era solo un elenco piu' lungo del vero: `GET
        /api/entities` continuava a mostrare l'ultimo stato di un'entita'
        cancellata, `action/verification` la dichiarava esistente («guarda lo
        specchio»), Home Assistant rispondeva 200 senza fare niente e
        l'attuatore rileggeva lo stesso specchio prima e dopo, riferendo un
        esito su un'entita' che non c'e'. Fondamenta 3: l'anagrafe dimentica
        a ogni `entity_registry_updated`, lo specchio no -- due porte, due
        case.

        **Il residuo dichiarato**: gli eventi emessi mentre la connessione WS
        era giu' non tornano (`ha_client._ws_loop` ricostruisce anagrafe,
        servizi e plance a ogni riconnessione, lo specchio no). Una rimozione
        avvenuta in quella finestra resta invisibile fino al riavvio
        dell'add-on, esattamente come vi resta un cambio di stato.
        """
        new_state = event_data.get("new_state")
        if not new_state:
            # `entity_id` sta nell'evento, non nello stato: e' la sola chiave
            # che una rimozione porta ancora (`old_state` c'e', ma prenderlo
            # di la' significherebbe fidarsi di due posti per lo stesso dato).
            eid = event_data.get("entity_id")
            if eid:
                self._states.pop(eid, None)
            return
        eid = new_state.get("entity_id")
        if not eid:
            return
        self._states[eid] = _to_minimal(new_state)

    # fetta E3 Task 12 ("esce il ritratto"): `get_state` e' uscito -- ORFANO
    # DICHIARATO dal Task 9, il cui unico chiamante era
    # `TaskEngine._evaluate_condition`, cancellato per intero col Task
    # Engine. Verificato di nuovo qui (grep sull'intero repo, zero
    # chiamanti): nessun successore.

    # `get_minimal` e `get_by_domain` sono USCITI (censimento del 17/08/2026,
    # zero chiamanti di produzione: il secondo era l'unico lettore del primo).
    # E con loro, l'09/09/2026, l'indice `_by_domain` che era rimasto a
    # riempirsi per nessuno -- vedi la nota in cima alla classe.

    # fetta E3 Task 12 ("esce il ritratto"): `domain_counts` e' uscito --
    # ORFANO DICHIARATO dal Task 7 (viveva per la UI della gateway policy,
    # cancellata insieme al semaforo). Verificato di nuovo qui: zero
    # chiamanti nell'intero repo.

    # `get_on` e `get_all_useful` sono USCITI (stesso censimento). Il secondo
    # era l'unico lettore di `NOISE_DOMAINS`, uscito con lui: quella lista
    # decideva cosa fosse "rumore" per un consumatore che non esiste piu', e la
    # domanda «cosa merita di essere detto» vive adesso in `home_space/briefing.py`, per
    # TIPOLOGIA e non per dominio (fetta «il vocabolario delle tipologie»).
    #
    # `load_area_registry`/`get_area_map` SONO usciti, insieme -- ed e' il
    # motivo per cui la nota di prima diceva "va deciso insieme, non a meta'":
    # il censimento segnalava l'accessore (zero letture di produzione) ma il
    # caricatore era chiamato davvero, due volte (avvio e riconnessione).
    # Lavoro morto fatto da codice vivo: due chiamate WebSocket a ogni avvio
    # per costruire una mappa che nessuno leggeva.
    #
    # E non era nemmeno una mappa giusta. Indicizzava per NOME dell'area --
    # due "Bagno" su piani diversi si fondevano in uno -- e ignorava l'area
    # EREDITATA dal dispositivo, che in una casa vera e' il caso normale, non
    # l'eccezione. `home_space/topology.hierarchy()` risponde alla stessa domanda
    # per id, con l'ereditarieta', e dichiarando quale registro non ha
    # risposto. Due risposte alla stessa domanda, una delle quali sbagliata e
    # letta da nessuno: NESSUN DOPPIONE.

    # `get_all` e' USCITO il 09/09/2026: portava lo STESSO corpo di
    # `all_states` (sotto) -- `return list(self._states.values())`, la
    # stessa riga in due metodi -- doppione misurato dall'audit delle
    # fondamenta (fondamenta 2, "nessun doppione"). L'unico chiamante di
    # produzione era `server.py::_retry_entity_inventory_if_needed`, dietro
    # un `hasattr` difensivo per un log di ricarica: ripuntato su
    # `all_states()`, il metodo vero che gia' leggono `ToolDispatcher`,
    # `action/actuator.py::Porta` e le porte API (vedi il docstring di
    # `_CacheFinta` in `tests/test_keeper_tools.py`, che documenta perche'
    # e' questo -- non l'altro -- il nome che conta).

    # fetta E3 Task 12 ("esce il ritratto"): `get_all_states` (la forma a
    # dizionario, entity_id -> stato) e' uscito -- ORFANO DICHIARATO dal
    # Task 2, il cui unico chiamante era `semantic_context_map`, cancellata
    # insieme alla context map. Verificato di nuovo qui: zero chiamanti.
    # Da non confondere con `all_states` (sotto), la forma a lista che
    # `api/handlers_home_space.py` e l'inventario entita' usano ancora: quella
    # resta.

    def all_states(self) -> list[dict]:
        """Return all cached entity states as a list (read-only access for the entity
        inventory API)."""
        return list(self._states.values())


