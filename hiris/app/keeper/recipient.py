"""Il recapito del soggetto (spec `docs/design/2026-09-26-il-seguito-delle-
chat-divise.md` §2.3, Task 1): per una promessa, a chi la spinge il sistema --
mai il modello.

Un punto solo, `recipients_for(subject, ha) -> Recipients`, che risponde per
genere: **persona** -> i servizi notify dei suoi dispositivi `mobile_app`
(dagli stati e dai registri di Home Assistant, VERI); **luogo**/
**integrazione** (i servizi firmati, Retro Panel incluso) -> nessuna strada
oggi; **nessuno**/anonimo/assente -> nessuna strada. Un servizio entra nel
risultato solo se esiste DAVVERO fra i notify che Home Assistant dichiara --
non si inventa mai un nome plausibile.

-- Come nasce `notify.mobile_app_<...>`, verificato sulla documentazione
ufficiale e sul sorgente (25/09/2026, RIVISTO il 26/09/2026 dal fix round 1
della review di sicurezza -- la prima stesura assumeva una coincidenza che
Home Assistant non garantisce, vedi sotto) --

`home-assistant.io/integrations/mobile_app/` non descrive la regola: la
pagina elenca le app ufficiali e rimanda alla documentazione companion, senza
dire come nasce il nome del servizio notify ne' se esiste un legame ufficiale
dispositivo -> servizio.

La regola vive nel sorgente (`home-assistant/core`, branch `dev`):

- **Registrazione** (`mobile_app/config_flow.py::async_step_registration`,
  letto 25/09/2026): l'entity_id del device_tracker nasce QUI, una volta
  sola --
  `entity_registry.async_get_or_create("device_tracker", DOMAIN,
  user_input[ATTR_DEVICE_ID], object_id_base=user_input[ATTR_DEVICE_NAME])`.
  Lo stesso `unique_id` (l'id del dispositivo) fa tornare SEMPRE la stessa
  voce di registro: l'object_id/entity_id resta **congelato** al nome che il
  dispositivo aveva alla PRIMA registrazione, e Home Assistant non lo
  rigenera mai da un nome cambiato dopo.
- **Rinomina** (`mobile_app/webhook.py::webhook_update_registration`, letto
  26/09/2026): quando l'app manda un nuovo `ATTR_DEVICE_NAME` (l'utente ha
  rinominato il telefono nelle impostazioni dell'app Companion), questa
  funzione riscrive **`device_registry.name`** col nome nuovo
  (`device_registry.async_get_or_create(..., name=new_registration
  [ATTR_DEVICE_NAME], ...)`), aggiorna `config_entry.data` e ricarica la
  piattaforma notify (`await hass_notify.async_reload(hass, DOMAIN)`).
- **Servizio** (`mobile_app/notify.py::push_registrations()` +
  `notify/legacy.py::PlatformNotify.async_register_services()`): dopo quel
  reload i bersagli tornano a leggere `entry.data[ATTR_DEVICE_NAME]` -- **il
  nome NUOVO** -- e il servizio si ri-registra come
  `slugify("mobile_app_" + nome_nuovo)`.

**Conseguenza misurabile: dopo una rinomina, l'entity_id del device_tracker
(congelato al nome VECCHIO) e il servizio notify (che segue il nome NUOVO)
divergono.** La prima stesura di questo modulo (25/09/2026) leggeva solo la
coda dell'entity_id: su una casa dove nessun dispositivo era mai stato
rinominato la coincidenza reggeva (la misura sotto, fatta quel giorno, lo
conferma), ma non e' una proprieta' che Home Assistant garantisce -- e un
dispositivo rinominato avrebbe smesso silenziosamente di ricevere le
notifiche.

**Il candidato giusto viene dal registro dei DISPOSITIVI** (`config/
device_registry/list`, il campo `name` -- **mai** `name_by_user`, l'etichetta
che l'utente scrive nell'interfaccia di Home Assistant e che nessuna delle
due funzioni sopra legge mai mentre calcola il nome del servizio; e **mai**
il titolo della config entry, che `webhook_update_registration` non
aggiorna), passato per la STESSA `slugify()` di Home Assistant
(`homeassistant.util.slugify(testo, separator="_")`, che a sua volta chiama
il pacchetto PyPI `python-slugify`) -- replicata qui in `_slugify()` invece
di aggiungere quella dipendenza per una funzione di poche righe
(`hiris/requirements.txt` la tiene minima di proposito, vedi il suo commento
sulla rimozione di `model2vec`). **L'entity_id resta un SECONDO candidato**,
non la fonte principale: un dispositivo mai rinominato, o un registro dei
dispositivi che non risponde, degrada su di lui. Per ogni tracker si prova
prima il candidato dal nome del dispositivo, poi quello dall'entity_id: il
PRIMO dei due che risulta davvero fra i servizi notify e' quello usato --
mai affermato, sempre verificato -- cosi' un dispositivo non spinge mai a
due servizi diversi per lo stesso telefono.

**Misurato sulla casa vera** (192.168.1.95, sola lettura, 25/09/2026, nessun
dispositivo era stato rinominato) sui quattro dispositivi della spec §1:
`device_tracker.iphone_bet` (dispositivo «iPhone Bet») ->
`notify.mobile_app_iphone_bet` esiste; `device_tracker.ipad_mini`
(«iPad mini») -> `notify.mobile_app_ipad_mini` esiste; `device_tracker.
iphone_di_marta` («iPhone di Marta») -> `notify.mobile_app_iphone_di_marta`
esiste; `device_tracker.iphone_bet_apple_watch` («iPhone Bet Apple Watch»,
il Watch, un device_tracker `mobile_app` senza registrazione push propria)
-> nessun servizio esiste per lui -- la regola regge, il Watch cade da se'
esattamente come previsto perche' la verifica contro `get_services()` lo
scarta, non perche' lo si riconosca per nome.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: La forma di UNA meta' di uno slug (`proxy/ha_client.py::_ENTITY_ID_RE`
#: impone la stessa cosa sull'intero entity_id): una guardia contro un
#: candidato che non potrebbe mai essere un servizio notify vero, non una
#: fonte -- l'esistenza si accerta comunque contro `get_services()`.
_SLUG_RE = re.compile(r"^[a-z0-9_]+$")


def _slugify(text: str | None) -> str:
    """Replica di `homeassistant.util.slugify(text, separator="_")`
    (che a sua volta chiama il pacchetto PyPI `python-slugify`), per i nomi
    Latini con accenti che un dispositivo smart-home porta nella pratica --
    niente dipendenza nuova per una funzione di poche righe.

    NFKD scompone un carattere accentato nella lettera base piu' il segno
    diacritico, che si scarta con la codifica ASCII: `"é"` -> `"e"`,
    `"à"` -> `"a"`. Copre il range Latino che un nome di dispositivo usa in
    pratica; **non** e' una traslitterazione fonetica come quella che
    `python-slugify` usa per altri alfabeti (cirillico, greco, CJK
    diventerebbero stringhe vuote qui, non una resa approssimata) -- se la
    casa vera lo richiedesse un giorno, la verifica contro `get_services()`
    piu' sotto scarta comunque un candidato sbagliato invece di spingere al
    posto sbagliato.

    Stessa forma dei due casi limite di HA (`homeassistant/util/
    __init__.py::slugify`): testo vuoto o `None` -> stringa vuota; testo che
    si riduce al niente dopo la traslitterazione -> `"unknown"`.

    **Pinnata** in `tests/test_keeper_recipient.py` con i quattro nomi
    misurati sulla casa vera piu' un caso con spazi e accenti (fix round 1,
    26/09/2026).
    """
    if text is None or text == "":
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_only.lower()).strip("_")
    return slug or "unknown"


#: Le due specie dei servizi firmati (`api/servizi.py::SPECIE`): nessuna
#: strada finche' Retro Panel e le integrazioni non dichiarano il proprio
#: gestore di notifiche (BACKLOG). Testo esatto della spec §2.3.
_REASON_NO_CHANNEL = "il servizio non ha ancora dichiarato come si avvisa."

#: La persona non e' collegata (nessun `person` in HA porta il suo
#: `user_id`) -- o non ha portato nessun id (persona anonima, l'ingress non
#: ha mandato `X-Remote-User-Id`). Stesso rimedio in entrambi i casi: e' la
#: pagina Persone che manca, non un guasto.
_REASON_LINK_PERSON = (
    "non so qual è il tuo telefono: collega la tua persona al tuo utente "
    "in Home Assistant (Impostazioni → Persone).")

#: La persona E' collegata, ma NESSUNO dei suoi `device_trackers` e' un
#: dispositivo `mobile_app` (o non ne ha affatto): non c'e' nessuna app
#: Home Assistant a cui riferirsi, e non e' un problema di notifiche.
_REASON_NO_MOBILE_APP_DEVICE = (
    "non so qual è il tuo telefono: nessun dispositivo della tua persona "
    "è collegato con l'app Home Assistant (Impostazioni → Persone).")

#: La persona ha almeno un `device_tracker` `mobile_app`, ma nessuno dei
#: candidati (nome del dispositivo, entity_id) risulta fra i servizi notify
#: che Home Assistant dichiara davvero: l'app c'e', le notifiche non sono
#: (ancora) attive su nessuno dei suoi dispositivi (fix round 1, 26/09/2026
#: -- prima era la stessa frase di `_REASON_NO_MOBILE_APP_DEVICE`, due fatti
#: diversi che il testo confondeva).
_REASON_NO_ACTIVE_NOTIFY = (
    "non so qual è il tuo telefono: i tuoi dispositivi non hanno ancora le "
    "notifiche attive. Apri l'app Home Assistant Companion per attivarle.")

#: Nessun soggetto affatto (`None`), o una specie che non e' ne' una persona
#: ne' un servizio firmato (`nessuno` -- il ponte che lavora per conto
#: proprio, o `sviluppo`).
_REASON_NO_SUBJECT = (
    "non so a chi mandare una notifica: questa richiesta non arriva da "
    "una persona.")

#: Un guasto di Home Assistant durante una qualunque delle tre letture. Non
#: si distingue QUALE lettura e' fallita nel motivo mostrato alla persona --
#: e' un dettaglio tecnico che non la aiuta a fare niente -- ma il registro
#: (sotto) lo tiene.
_REASON_HA_DOWN = (
    "non riesco a controllare il tuo telefono: Home Assistant non ha "
    "risposto. Riprova più tardi.")

#: PIU' di una `person` in HA porta lo stesso `user_id` (una casa mal
#: configurata, non il caso comune): scegliere la prima trovata sarebbe
#: indovinare quale delle due segue davvero questa persona -- meglio
#: dichiararlo che spingere a un dispositivo forse sbagliato (security
#: review, 26/09/2026, vincolo 1.5).
_REASON_AMBIGUOUS_PERSON = (
    "non so a quale tua persona mandare la notifica: più di una persona "
    "in Home Assistant risulta collegata allo stesso utente. Sistemalo in "
    "Impostazioni → Persone.")

#: Le due specie dei servizi firmati (Retro Panel e le integrazioni,
#: `api/servizi.py::SPECIE`): stessa non-strada per entrambe.
_SIGNED_SPECIES = ("luogo", "integrazione")


@dataclass(frozen=True)
class Recipients:
    """L'esito di `recipients_for`: i servizi notify VERI a cui spingere, o
    il motivo per cui non ce n'e' nessuno. `reason` e' valorizzato solo
    quando `services` e' vuota (fondamenta 1: si interpreta da solo -- chi
    legge zero servizi non deve indovinare perche')."""
    services: tuple[str, ...]
    reason: str | None = None


async def recipients_for(subject: dict | None, ha) -> Recipients:
    """Il recapito di CHI ha chiesto -- mai scelto dal modello (spec §2.3).

    Una lettura sola per ciascuno dei tre lettori che `ha` gia' ha
    (`get_states`, `read_registries`, `get_services`), e solo quelle che
    servono: una persona senza `id`, senza `person` collegata o senza
    `device_trackers` non arriva mai a leggere i registri o i servizi.

    Un guasto di una qualunque lettura torna **zero servizi col motivo del
    guasto**, mai un'eccezione: la promessa che stava per nascere (o
    risvegliarsi) non deve rompersi perche' Home Assistant non ha risposto.
    """
    if not subject:
        return Recipients((), _REASON_NO_SUBJECT)

    # Variabile locale chiamata `kind`, non `specie`: in questo stesso
    # ambito (`keeper`) `specie` e' gia' il nome chiuso dal giro di rinomina
    # per il VERBO di una promessa (`fai`/`chiedi`, vedi `promise.py::
    # validate`) -- un significato diverso da questo (persona/luogo/
    # integrazione/nessuno). Riusare lo stesso identificatore per un
    # concetto diverso avrebbe fatto scattare la riscrittura automatica su
    # QUESTA variabile (misurato: `test_gli_ambiti_chiusi_restano_
    # idempotenti` va rosso, il tool la rinomina in `verb`, che qui sarebbe
    # falso). La CHIAVE del dizionario resta `"specie"` -- quella e' un
    # valore di dominio, non un identificatore Python.
    kind = subject.get("specie")
    if kind in _SIGNED_SPECIES:
        return Recipients((), _REASON_NO_CHANNEL)
    if kind != "persona":
        return Recipients((), _REASON_NO_SUBJECT)

    user_id = subject.get("id")
    if not user_id:
        return Recipients((), _REASON_LINK_PERSON)

    try:
        states = await ha.get_states([])
    except Exception as exc:
        # Solo il TIPO del guasto, mai il suo testo: un messaggio di
        # eccezione di rete puo' portare dentro di se' un frammento della
        # richiesta che l'ha causato (security review, 26/09/2026, vincolo
        # 1.2 -- niente che non sia `subject_key`, id, conteggi nei log).
        logger.warning("recipients_for: stati non letti da Home Assistant (%s)",
                       type(exc).__name__)
        return Recipients((), _REASON_HA_DOWN)
    if not isinstance(states, list):
        logger.warning("recipients_for: gli stati non sono arrivati come lista")
        return Recipients((), _REASON_HA_DOWN)

    # **Uguaglianza ESATTA su `user_id`, e si contano TUTTE le corrispondenze
    # -- non la prima.** Una casa dove due `person` portano per errore lo
    # stesso `user_id` non ha un modo corretto di scegliere fra le due: la
    # prima trovata sarebbe una scelta indovinata, non dedotta (security
    # review, 26/09/2026, vincolo 1.5).
    matching_persons = [
        s for s in states
        if isinstance(s, dict)
        and str(s.get("entity_id") or "").startswith("person.")
        and (s.get("attributes") or {}).get("user_id") == user_id]
    if not matching_persons:
        return Recipients((), _REASON_LINK_PERSON)
    if len(matching_persons) > 1:
        logger.warning("recipients_for: %d persone collegate allo stesso utente",
                       len(matching_persons))
        return Recipients((), _REASON_AMBIGUOUS_PERSON)
    person = matching_persons[0]

    trackers_raw = (person.get("attributes") or {}).get("device_trackers")
    trackers = ([t for t in trackers_raw if isinstance(t, str)]
                if isinstance(trackers_raw, list) else [])
    if not trackers:
        return Recipients((), _REASON_NO_MOBILE_APP_DEVICE)

    # Un batch WS solo (`read_registries` gia' fa cosi': un comando per
    # registro, una connessione), ma resta un costo ad OGNI risveglio di
    # promessa -- l'intera anagrafe della casa per risolvere due o tre
    # tracker. Accettabile oggi (i registri sono nell'ordine delle migliaia
    # di righe, non milioni); un lettore piu' leggero, mirato ai soli
    # `entity_id`/`device_id` richiesti, e' una fetta successiva se la
    # cadenza dei risvegli lo rendesse un problema misurato.
    try:
        registries, unavailable = await ha.read_registries()
    except Exception as exc:
        logger.warning("recipients_for: registri non letti da Home Assistant (%s)",
                       type(exc).__name__)
        return Recipients((), _REASON_HA_DOWN)
    if "entita" in (unavailable or []):
        logger.warning("recipients_for: registro delle entita' non disponibile")
        return Recipients((), _REASON_HA_DOWN)

    entities = registries.get("entita") if isinstance(registries, dict) else None
    by_entity_id = {e.get("entity_id"): e for e in (entities or [])
                    if isinstance(e, dict)}
    # Il registro dei dispositivi puo' mancare (`non_disponibili`) senza
    # essere fatale: senza di lui si degrada sul solo candidato
    # dell'entity_id, che regge finche' nessun dispositivo e' stato
    # rinominato (vedi il docstring del modulo).
    devices = registries.get("dispositivi") if isinstance(registries, dict) else None
    by_device_id = {d.get("id"): d for d in (devices or []) if isinstance(d, dict)}

    mobile_app_trackers = [
        (tracker_id, entry)
        for tracker_id in trackers
        if (entry := by_entity_id.get(tracker_id))
        and entry.get("platform") == "mobile_app"]
    if not mobile_app_trackers:
        return Recipients((), _REASON_NO_MOBILE_APP_DEVICE)

    try:
        services = await ha.get_services()
    except Exception as exc:
        logger.warning("recipients_for: servizi non letti da Home Assistant (%s)",
                       type(exc).__name__)
        return Recipients((), _REASON_HA_DOWN)

    notify_services: set[str] = set()
    for entry in (services or []):
        if isinstance(entry, dict) and entry.get("domain") == "notify":
            declared = entry.get("services")
            if isinstance(declared, dict):
                notify_services.update(k for k in declared if isinstance(k, str))

    # Per ogni tracker, DUE candidati nell'ordine giusto (vedi il docstring
    # del modulo): prima il nome VERO di oggi (dal registro dei dispositivi,
    # segue una rinomina), poi la coda dell'entity_id (congelata alla prima
    # registrazione, il ripiego quando il dispositivo non e' mai stato
    # rinominato o il registro dei dispositivi non e' arrivato). Il PRIMO
    # che risulta fra i servizi notify vince -- mai i due insieme, o lo
    # stesso telefono riceverebbe due notifiche per un unico esito.
    resolved: list[str] = []
    for tracker_id, entry in mobile_app_trackers:
        slug_candidates = []
        device = by_device_id.get(entry.get("device_id"))
        if device:
            device_slug = _slugify(device.get("name"))
            if device_slug:
                slug_candidates.append(device_slug)
        _, _, suffix = tracker_id.partition(".")
        if suffix:
            slug_candidates.append(suffix)

        for slug in slug_candidates:
            if not _SLUG_RE.match(slug):
                continue
            candidate = f"mobile_app_{slug}"
            if candidate in notify_services:
                # Due tracker della stessa persona possono convergere sullo
                # STESSO servizio (un telefono nuovo che ha preso il nome del
                # vecchio, ancora collegato): un servizio compare una volta
                # sola, al posto del primo tracker che lo trova -- ordine
                # stabile, una push per telefono (extra 5 del Task 3).
                service = f"notify.{candidate}"
                if service not in resolved:
                    resolved.append(service)
                break

    if not resolved:
        return Recipients((), _REASON_NO_ACTIVE_NOTIFY)
    return Recipients(tuple(resolved), None)
