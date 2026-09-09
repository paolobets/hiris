"""La parte che dice di no, e dice perche'.

Funzione pura: nessuna rete, nessun client, nessuno stato interno. Riceve
cio' che il modello propone, il registro (cosa esiste) e lo specchio dello
stato vivo (cosa c'e' in casa), e risponde un `Verdict`.

**Perche' e' separata dalla porta.** La parte che decide se toccare la casa
non deve aver bisogno della casa per essere provata: qui ogni caso di rifiuto
ha un test che gira in millisecondi, senza Home Assistant.

**Cosa NON verifica, di proposito** -- e' dichiarato qui perche' un lettore
futuro non lo scambi per una dimenticanza:

- **i valori dei parametri.** Il registro porta i selettori, ma la loro
  varieta' e' grande: una validazione approssimativa RIFIUTEREBBE chiamate
  legittime, che e' peggio di lasciar passare un valore che Home Assistant
  rigetta con un errore chiaro. Il modello lo legge e si corregge.
- **i parametri di un servizio il cui `fields` non e' leggibile.** Il registro
  li normalizza a `None` invece di indovinarli, e qui `None` non diventa
  «nessun parametro»: il controllo si salta. Rifiutare su cio' che non si e'
  potuto misurare significherebbe dire «non accetta parametri» a un servizio
  che ne ha -- e, se la forma vera di `/api/services` fosse quella, dirlo di
  ogni servizio della casa.

**Le capacita' fini, invece, ADESSO si verificano** -- e fino al 07/09/2026
erano il terzo punto di questo elenco, con la ragione «il fine richiede di
interpretare bitmask dominio per dominio». **Quella ragione non vale piu', e
non perche' qualcuno abbia imparato a leggere le bitmask: perche' non serve.**
Home Assistant pubblica lui stesso, campo per campo, un `filter` che dichiara
a quali entita' quel parametro si applica, e lo fa nominando l'attributo da
guardare (`supported_color_modes`) o il bit (`32`) -- gia' risolto in numero.
Nessuna tabella nostra, nessun dominio da interpretare: la regola di confronto
e' trascritta dal frontend di Home Assistant in `action/registry.field_applies`,
con la fonte citata riga per riga.

Quindi «cambia colore alla presa della lavatrice» -- e, piu' finemente,
«cambia colore a una luce che fa solo acceso/spento» -- si rifiuta QUI, con
una frase che dice perche', invece di partire e tornare come errore tecnico di
Home Assistant.

**E questa funzione resta pura.** Il `filter` va confrontato con gli attributi
dell'entita', che sono un dato vivo -- ma quel dato **arriva gia' da fuori**:
e' `stati`, lo specchio che il chiamante passa e che dalla fetta
dell'eredita' (07/09/2026) porta le ceste degli attributi. E' la stessa forma
del giro in due tempi dei bersagli, scritta piu' sotto: la parte che dice di
no resta UNA e non chiama nessuno, chi ha la casa gliela consegna. Le prove di
questo file continuano a girare senza Home Assistant.

**Tre cose che il controllo sulle capacita' NON fa**, dichiarate perche' un
lettore futuro non le scambi per dimenticanze:

- **non verifica i VALORI**, e la prima riga di questo elenco resta vera:
  `light.turn_on` con `color_temp_kelvin: 8000` passa. Il selettore generico
  di Home Assistant si ferma a 6500 K, ma l'Alberello dichiara
  `max_color_temp_kelvin: 9000` -- **vince l'entita'**, il selettore descrive
  il campo di un cursore, non il dispositivo. Chi restringesse sul selettore
  negherebbe una temperatura che quella lampadina sa fare davvero. I limiti
  veri escono verso il modello dalla vista di `guarda`
  (`home_space/queries.commands_for`), che li prende dall'entita';
- **non rifiuta su cio' che non si e' potuto misurare**: `field_applies`
  risponde `None` e qui `None` non diventa un no. Stessa disciplina di
  `fields` due paragrafi sotto;
- **su un bersaglio con piu' entita' si rifiuta solo se NESSUNA accetta quel
  parametro** -- e' la stessa regola che Home Assistant applica per decidere
  se disegnare il campo (`.some(...)`). Un bersaglio misto («abbassa le luci
  del salotto», dove tre sanno attenuarsi e due no) passa, e le due che non
  sanno le rifiuta Home Assistant una per una. **E' un limite dichiarato**:
  qui non c'e' ancora una cesta «entita' a cui questo parametro non si
  applica» accanto a `scartate` e `sconosciute`.

**I bersagli che non sono entita' (area, piano, etichetta, dispositivo).**
Fino alla fetta «i bersagli» questa funzione li rifiutava, e il difetto non
era il rifiuto: era cosa il modello faceva dopo. «Spegni tutto in cucina»
lo obbligava a chiamare `search`, raccogliere gli id a mano e passarli tutti
qui; se ne perdeva uno -- e su una cucina con quindici entita' ne perdeva uno
-- HIRIS ne spegneva quattordici e **dichiarava di aver spento tutto**. Una
risposta sbagliata detta con sicurezza.

A risolverli e' Home Assistant (`extract_from_target`, vedi
`proxy/ha_client.extract_from_target`), che questa funzione -- pura -- non
puo' chiamare. Quindi il giro e' in due tempi, e la parte che dice di no
resta UNA:

1. `verification(chiamata, registro, stati)` su un bersaglio ricco risponde un
   verdetto NEGATIVO con `da_risolvere=True` e il bersaglio gia' tradotto
   nella forma di Home Assistant. Negativo e non «in attesa» di proposito:
   un chiamante che ignorasse il campo nuovo non eseguirebbe niente, invece
   di eseguire su un elenco vuoto.
2. la porta lo risolve e richiama `verification(..., resolved=<cio' che HA ha
   detto>)`, che rifa' TUTTI i controlli con l'elenco in mano.

Cio' che si e' scelto di NON fare, perche' un lettore futuro non lo scambi
per una dimenticanza:

- **le entita' di un bersaglio risolto non si rifiutano una per una.** Una
  cucina contiene sensori, prese e media player: pretendere che siano tutte
  del dominio del servizio farebbe rifiutare «spegni le luci in cucina» in
  ogni casa vera. Si tengono quelle a cui il servizio si applica e si
  DICHIARANO le altre (`scartate`, `sconosciute`) -- che e' cio' che fa Home
  Assistant stesso, che non chiama un servizio su un'entita' che non e' del
  suo componente.
- **le entita' che il modello ha NOMINATO restano strette.** Un id che non
  esiste, o di un altro dominio, e' un'affermazione sbagliata del modello e
  si rifiuta come sempre -- anche quando arriva insieme a un'area.

**I servizi che non hanno niente da bersagliare.** Review finale, rilievo
CRITICO ①. Fino a questa passata un bersaglio vuoto era SEMPRE un rifiuto,
anche per un servizio come `notify.*` che non accetta un `target` -- e questo
significava che una promessa «chiedi» non poteva mai notificare
(`keeper/sweeper.py` costruisce la sua chiamata con `"bersaglio": {}`,
e questa funzione la rifiutava incondizionatamente, PRIMA di guardare il
servizio). Adesso un bersaglio vuoto e' legittimo quando -- e solo quando --
il servizio non dichiara un `target` **e** appartiene alla famiglia dei
recapiti (`_DOMINI_DI_RECAPITO`: `notify`, `persistent_notification`). Per
ogni altro servizio il rifiuto resta identico a prima, parola per parola.

**Perche' e' ristretto ai recapiti, e non a "qualunque servizio senza
target".** La prima versione di questo fix (re-review indipendente) allargava
su QUALUNQUE servizio senza `target`: avrebbe reso raggiungibili dalla porta
anche `homeassistant.restart`, `hassio.host_reboot`, `recorder.purge`,
`automation.reload`, `shell_command.*` -- servizi di sistema oggi DI FATTO
irraggiungibili, perche' un bersaglio vuoto era sempre un rifiuto e non esiste
nessuna lista nera che li fermi altrimenti. C'e' anche un'asimmetria che il
reviewer ha trovato leggendo la nota sopra `_DOMINI_UNIVERSALI`: lo stesso
campo `target` e' gia' giudicato INAFFIDABILE per RESTRINGERE (mai misurato su
un'installazione vera), e non si puo' usarlo per ALLARGARE nello stesso
momento senza la stessa cautela. Restringersi ai recapiti e' la famiglia che
serve ADESSO (la notifica dello Schedulatore), non un'ipotesi sul resto.
"""
from dataclasses import dataclass, field

from ..home_space.topology import domain_of
from ..home_space.type_vocabulary import capability_names
from ..proxy.entity_cache import disclosable_attributes
from .registry import field_applies, field_filter

# I servizi di questo dominio si applicano a QUALUNQUE dominio di entita'
# (`homeassistant.turn_off` spegne luci, prese, media player...). Senza
# l'esenzione il controllo sul dominio rifiuterebbe chiamate legittime.
#
# **L'esenzione e' piu' larga della ragione che la giustifica, ed e' voluto
# per ora** (R-4 della review della fetta). Vale sul dominio INTERO, non sui
# soli servizi che agiscono sull'entita' nominata: `homeassistant.restart` con
# `light.cucina` nel bersaglio passa di qui ed esce verso Home Assistant. Non
# e' un cancello mancante -- nessuno lo chiama se l'utente non lo chiede -- ma
# il controllo sul dominio e' l'unico contenimento strutturale che questa
# fetta possiede, e li' non c'e'.
#
# Stringerla e' possibile e non e' stato fatto: le definizioni dei servizi
# portano un campo `target`, e un servizio che non ne dichiara nessuno non
# guarda l'entita' che gli si passa.
#
# **Corretto il 09/09/2026: il dato che questo commento diceva mancare c'e'.**
# `target` vive nella stessa risposta di `/api/services` che `action/
# registry.py` misura gia' (84 domini di servizio, 604 campi, 08/09/2026 --
# vedi il suo docstring "COSA QUESTO REGISTRO DICE SUI TIPI"): non e' piu'
# vero che «nessuno l'ha misurato». Misurato di nuovo, sulla casa vera,
# proprio sui tre servizi che contano qui: `homeassistant.turn_off` dichiara
# `target: {}` (bersaglio ammesso, anche vuoto), `homeassistant.restart` e
# `homeassistant.reload_all` NON hanno la chiave affatto (nessun bersaglio
# dichiarato). E' esattamente il dato che la nota B di
# `docs/prova-azione.md` chiedeva di leggere dall'output della prova 1.
#
# **La restrizione resta non fatta**, ed e' una decisione, non una svista:
# stringere `_DOMINI_UNIVERSALI` in base a questo dato e' un cambio di
# comportamento su un percorso che tocca la casa vera (rifiuterebbe chiamate
# oggi accettate), e la nota B lo affida al proprietario che legge il
# `curl` a mano -- non a chi scrive un commento. Restringere al buio
# sarebbe stato lo stesso difetto di allargare al buio; restringere ora che
# il dato c'e', senza il suo giro di verifica, sarebbe lo stesso difetto
# corso in fretta.
_DOMINI_UNIVERSALI = frozenset({"homeassistant"})


def _declare_target(definition: dict) -> bool:
    """Vero se questo servizio si aspetta un bersaglio (entita', area...).

    Review finale, rilievo CRITICO ①. Il campo e' `target` di
    `/api/services`, che `action/registry.py` conserva TALE E QUALE (vedi il
    suo docstring): quando c'e' -- anche vuoto, `{}` -- il servizio accetta un
    bersaglio, e un bersaglio vuoto resta un errore, come e' sempre stato.
    Quando manca, o e' `None`, il servizio non lo dichiara affatto: e' il
    caso di `notify.*` e di parecchi servizi di sistema, che oggi HIRIS
    rifiuta SEMPRE anche quando non hanno niente da bersagliare -- il difetto
    per cui una promessa «chiedi» non poteva mai notificare (vedi
    `keeper/sweeper.py::_keep_chiedi`).

    **Il verso e' quello prudente.** Si allarga SOLO quando il dato dice
    esplicitamente «niente bersaglio» (`isinstance(..., dict)` falso): mai per
    un'assenza ambigua che potrebbe voler dire «questa installazione non lo
    misura». E' la stessa cautela gia' scritta sopra `_DOMINI_UNIVERSALI` per
    lo stesso campo -- usata li' per allargare un'ESENZIONE (rischioso: un
    falso negativo apre un dominio intero), qui per allargare la sola
    ammissione di un bersaglio vuoto su un servizio specifico (un falso
    negativo qui richiede comunque un bersaglio in piu', mai in meno: per
    tutti gli altri servizi il rifiuto resta identico a prima, parola per
    parola).

    **Non basta da sola** -- vedi `_allows_empty_target`, che la
    combina con l'appartenenza alla famiglia dei recapiti: usata qui isolata
    allargherebbe su qualunque servizio senza `target`, non solo su chi
    serve davvero.
    """
    return isinstance(definition.get("target"), dict)


# I domini "di recapito": la SOLA famiglia per cui un bersaglio vuoto e'
# ammesso quando il servizio non dichiara un `target` (review indipendente,
# punto ①). Una casa sola, e provvisoria di proposito: non e' una lista nera
# travestita da regola, e' una regola STRETTA in attesa di un dato. Si
# allarghera' -- se si allarghera' -- quando la prova 1 di
# `docs/prova-azione.md` avra' MISURATO cosa dichiara davvero `target` su
# un'installazione vera per i servizi di sistema (`homeassistant.restart`,
# `hassio.host_reboot`, `recorder.purge`, `automation.reload`,
# `shell_command.*`...), non prima. Finche' quel dato non c'e', restano
# rifiutati come sempre.
_DOMINI_DI_RECAPITO = frozenset({"notify", "persistent_notification"})


def _allows_empty_target(domain: str, definition: dict) -> bool:
    """Vero se un bersaglio vuoto e' la forma giusta per QUESTA chiamata.

    Combina le due condizioni che, insieme, restano dentro il perimetro
    misurato: il servizio non dichiara un `target` (`_declare_target`) E
    il suo dominio e' uno dei recapiti (`_DOMINI_DI_RECAPITO`). La prima da
    sola era troppo larga -- vedi il docstring del modulo.
    """
    return domain in _DOMINI_DI_RECAPITO and not _declare_target(definition)


# I cinque modi in cui un bersaglio puo' nominare cio' che va toccato, e il
# campo di Home Assistant che gli corrisponde. Le chiavi sono quelle che il
# modello scrive (`strumenti.EXECUTE_TOOL_DEF`), i valori sono quelli di
# `cv.TARGET_FIELDS` -- la traduzione vive QUI, in un posto solo: `ha_client`
# riceve gia' la forma di Home Assistant e non ha un'opinione sull'italiano
# del modello.
#
# I cinque nomi italiani coincidono con cinque delle etichette dell'albero in
# pagina, e non sono la stessa cosa: li' e' un vocabolario di REGISTRI da
# mostrare (che comprende anche categorie e integrazioni), qui e' l'elenco di
# cio' che Home Assistant accetta come bersaglio. Unirli renderebbe
# bersagliabile cio' che non lo e'.
# DOPPIONE DICHIARATO: registri da mostrare contro bersagli accettati da HA
TARGETS = {
    "entita": "entity_id",
    "dispositivi": "device_id",
    "aree": "area_id",
    "piani": "floor_id",
    "etichette": "label_id",
}

# Come si nomina, in un rifiuto, cio' che il bersaglio ha chiesto e non
# esiste. La chiave e' quella con cui `ha_client.extract_from_target`
# restituisce i mancanti; l'ordine e' quello in cui il rifiuto li elenca.
_MANCANTI = (
    ("piani_mancanti", "piani"),
    ("aree_mancanti", "aree"),
    ("dispositivi_mancanti", "dispositivi"),
    ("etichette_mancanti", "etichette"),
)


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str = ""
    domain: str = ""
    service: str = ""
    entity: tuple[str, ...] = field(default_factory=tuple)
    # Il bersaglio nella forma di Home Assistant, gia' tradotto e ripulito:
    # e' cio' che si manda a `extract_from_target`. C'e' anche nei verdetti
    # positivi, cosi' l'esito puo' dire cosa e' stato chiesto e non solo cosa
    # ne e' uscito.
    target: dict = field(default_factory=dict)
    # `True` quando il bersaglio nomina qualcosa che solo Home Assistant sa
    # risolvere e nessuno gliel'ha ancora chiesto. Va sempre insieme a
    # `ok=False`: vedi il docstring del modulo.
    da_risolvere: bool = False
    # Le due meta' di cio' che il bersaglio conteneva e non si tocca. Sono
    # nel verdetto e non in un log perche' l'esito le deve poter dichiarare:
    # «ho toccato 9 delle 15 cose che ci sono in cucina» e' un fatto, «ho
    # spento tutto» dopo averne saltate sei e' il difetto che questa fetta
    # chiude.
    scartate: tuple[str, ...] = field(default_factory=tuple)   # altro dominio
    sconosciute: tuple[str, ...] = field(default_factory=tuple)  # senza stato
    # Vero quando il verdetto e' positivo e il servizio non dichiara un
    # `target` **ed e' un recapito** (vedi `_allows_empty_target`):
    # `entita` e `bersaglio` restano vuoti apposta, e non e' un difetto -- e'
    # la forma giusta per un servizio come `notify.*`, che non ha niente da
    # bersagliare. La porta lo legge per non iniettare `entity_id: []` (che
    # direbbe una cosa diversa da «nessun bersaglio») e per non aprire un
    # ascolto di stato che non avrebbe niente da attendere (review finale,
    # rilievo CRITICO ①; ristretto ai recapiti dalla review indipendente).
    no_target: bool = False


def _no(reason: str) -> Verdict:
    return Verdict(ok=False, reason=reason)


def translate_target(target) -> tuple[dict, list[str]]:
    """Il bersaglio del modello nella forma di Home Assistant, e cio' che di
    quel bersaglio non si e' saputo leggere.

    Restituisce `(tradotto, illeggibili)`. `tradotto` vuoto significa «non
    nomina niente di utilizzabile», e comprende sia il bersaglio assente sia
    quello scritto in un modo che nessuno sa leggere: per chi deve agire i due
    casi valgono uguale, e il rifiuto e' lo stesso.

    **`illeggibili` non e' un dettaglio di forma.** Una lista di aree con
    dentro un numero, o un `None`, si tradurrebbe benissimo saltando la voce
    guasta -- e sarebbe un bersaglio RIDOTTO IN SILENZIO, cioe' il difetto che
    questa fetta esiste per chiudere, alla riga sbagliata. Si dichiara e chi
    chiama rifiuta.

    Una voce sola arriva spesso come stringa nuda invece che come lista di
    uno -- vale per gli id delle entita' come per il nome di un'area -- ed e'
    una forma legittima: rifiutarla sarebbe rifiutare per punteggiatura.
    """
    if not isinstance(target, dict):
        return {}, []
    translated: dict[str, list[str]] = {}
    illeggibili: list[str] = []
    for nostro, loro in TARGETS.items():
        entries = target.get(nostro)
        if entries is None:
            continue
        if isinstance(entries, str):
            entries = [entries]
        if not isinstance(entries, list):
            illeggibili.append(f"«{nostro}» non e' un elenco")
            continue
        buone = []
        for entry in entries:
            if isinstance(entry, str) and entry.strip():
                buone.append(entry.strip())
            else:
                illeggibili.append(f"«{nostro}» contiene {entry!r}, "
                                   f"che non e' un identificatore")
        if buone:
            translated[loro] = buone
    return translated, illeggibili


def _cosa_non_esiste(resolved: dict) -> str:
    """L'elenco di cio' che il bersaglio nominava e non esiste, gia' scritto.

    Stringa vuota quando esiste tutto. E' separata dal resto perche' e' la
    meta' della risposta di Home Assistant che dice una cosa DIVERSA dalle
    entita': «quell'area non c'e'» non e' «quell'area e' vuota».
    """
    parts = []
    for key, name in _MANCANTI:
        entries = [v for v in resolved.get(key) or [] if isinstance(v, str)]
        if entries:
            parts.append(f"{name} {_list(entries)}")
    return "; ".join(parts)


def _list(entries, count: int = 12) -> str:
    entries = sorted(entries)
    if len(entries) <= count:
        return ", ".join(entries)
    return ", ".join(entries[:count]) + f" (e altri {len(entries) - count})"


def _disclosed(entry) -> dict:
    """Gli attributi di un'entita' dello specchio, piatti e senza credenziali.

    `entity_cache.disclosable_attributes` e non una lettura diretta delle
    ceste: chi cerca `supported_color_modes` per nome non deve sapere in quale
    cesta sta, ed e' la stessa porta che usano lo stato leggibile e l'impronta
    di un'azione. Un'entita' che lo specchio non ha (o che porta una forma che
    nessuno sa leggere) risponde `{}`, che `field_applies` traduce in «non
    l'ho potuto misurare» -- mai in un no.
    """
    if not isinstance(entry, dict):
        return {}
    return disclosable_attributes(entry.get("attributes"))


def _who(entities: tuple[str, ...] | list) -> str:
    """Come si nomina, in un rifiuto, cio' che non accetta un parametro."""
    if len(entities) == 1:
        return f"«{entities[0]}»"
    return f"nessuna delle {len(entities)} entita' che questo bersaglio tocca"


def _declares(name: str, pictures: list[dict]) -> str:
    """Cosa le entita' bersagliate dichiarano DAVVERO in quell'attributo.

    Non e' un ornamento del messaggio: senza, il rifiuto dice cosa serviva e
    non cosa c'e', e il modello non ha da cosa correggersi. Con una entita'
    sola si nomina il suo valore; con piu' di una si dice che nessuna
    corrisponde, perche' elencarne quindici sarebbe un muro.
    """
    dichiarati = sorted({str(v) for p in pictures if name in p
                         for v in (p[name] if isinstance(p[name], (list, tuple))
                                   else [p[name]])})
    if not dichiarati:
        return f"e {'questa' if len(pictures) == 1 else 'nessuna di loro'} non lo dichiara affatto"
    if len(pictures) == 1:
        return f"e questa dichiara {_list(dichiarati)}"
    return f"e quelle che lo dichiarano valgono {_list(dichiarati)}"


def _unmet_reason(key: str, reading: str, domain: str, detail,
                  entities, pictures: list[dict]) -> str:
    """Perche' questo parametro non si applica a queste entita', in parole.

    Legge il `filter` che Home Assistant pubblica e lo dice: quale attributo
    guarda, quali valori ammette, cosa c'e' invece. La forma per capacita' usa
    i nomi dei bit dell'anagrafe dei tipi quando ci sono
    (`capability_names`) -- «sa fare la transizione» invece di «il bit 32» --
    e ripiega sul numero quando per quel dominio non ne abbiamo una tabella
    verificata alla fonte: un numero vero vale piu' di un nome inventato.
    """
    reading_filter = field_filter(detail) or {}
    per_attribute = reading_filter.get("attribute")
    if isinstance(per_attribute, dict) and per_attribute:
        name, admitted = min(per_attribute.items())
        ammessi = _list([str(v) for v in admitted]) if isinstance(admitted, list) else "?"
        return (f"«{key}» di «{reading}» non si applica a {_who(entities)}: Home "
                f"Assistant offre questo parametro solo alle entita' il cui "
                f"«{name}» vale una fra {ammessi}, {_declares(name, pictures)}. "
                f"Guarda l'entita' con «view»: sotto «comandi» c'e' cosa accetta "
                f"davvero.")
    bits = [b for b in reading_filter.get("supported_features") or []
            if isinstance(b, int) and not isinstance(b, bool)]
    names = capability_names(domain) or {}
    detti = [names[b] for b in bits if b in names]
    serve = _list(detti) if detti else _list([str(b) for b in bits])
    return (f"«{key}» di «{reading}» non si applica a {_who(entities)}: Home "
            f"Assistant offre questo parametro solo alle entita' che dichiarano "
            f"{serve}, e {'questa' if len(entities) == 1 else 'nessuna di loro'} "
            f"non lo fa. Guarda l'entita' con «view»: sotto «comandi» c'e' cosa "
            f"accetta davvero.")


def _capability_refusal(reading: str, domain: str, definition: dict, data: dict,
                        entities, states: dict[str, dict]) -> str:
    """Il rifiuto sulle capacita' fini, o stringa vuota se non c'e' niente da
    dire.

    Si chiama nei DUE punti in cui l'elenco definitivo delle entita' esiste --
    il bersaglio di sole entita', e il bersaglio risolto da Home Assistant --
    e non e' un doppione: e' una funzione sola chiamata due volte, come
    `verification()` stessa viene richiamata intera dopo la risoluzione
    invece di farsi aggiungere un pezzo. Scriverne una copia in ciascun ramo
    sarebbe la seconda casa che questo prodotto passa il tempo a chiudere.

    Si rifiuta **solo quando nessuna** delle entita' bersagliate accetta il
    parametro (`is not False` su tutte e tre le risposte possibili): un `True`
    o anche un solo `None` -- «non l'ho potuto misurare» -- lasciano passare.
    """
    fields = definition.get("fields")
    if not isinstance(fields, dict) or not entities or not data:
        return ""
    pictures = [_disclosed(states.get(eid)) for eid in entities]
    for key in data:
        detail = fields.get(key)
        if any(field_applies(detail, picture) is not False for picture in pictures):
            continue
        return _unmet_reason(key, reading, domain, detail, entities, pictures)
    return ""


def verification(call: dict, registry, states: dict[str, dict],
             *, resolved: dict | None = None) -> Verdict:
    """Il verdetto su una chiamata. `risolto` e' cio' che Home Assistant ha
    risposto su questo bersaglio (`ha_client.extract_from_target`), e serve
    solo ai bersagli che nominano aree, piani, etichette o dispositivi: su un
    bersaglio di sole entita' non si chiede niente a nessuno, ed e' voluto --
    un giro di rete per una cosa gia' scritta nella chiamata sarebbe un costo
    senza una domanda."""
    reading = call.get("servizio")
    if not isinstance(reading, str) or reading.count(".") != 1:
        return _no("il servizio va scritto come «dominio.servizio», "
                   "per esempio «light.turn_off».")
    domain, name = reading.split(".")

    if domain not in registry.domains():
        return _no(f"il dominio «{domain}» non esiste in questa casa. "
                   f"Domini disponibili: {_list(registry.domains())}.")

    # `is None`, mai `if not`: il registro risponde `{}` -- falso in booleano
    # -- per un servizio che ESISTE ma non dichiara ne' campi ne' bersaglio.
    # Con la verita' booleana HIRIS rifiuterebbe una chiamata legittima, e
    # col motivo sbagliato («non esiste» invece di niente).
    definition = registry.service(domain, name)
    if definition is None:
        return _no(f"«{reading}» non esiste. I servizi di «{domain}» sono: "
                   f"{_list(registry.services_for(domain))}.")

    ha_target, illeggibili = translate_target(call.get("bersaglio"))
    if illeggibili:
        # Prima di dire «non c'e' niente»: un bersaglio scritto meta' bene si
        # rifiuta INTERO. Tradurne la meta' buona e tacere l'altra vorrebbe
        # dire toccare meno di quanto e' stato chiesto senza dirlo.
        return _no(f"questo bersaglio non si legge: {'; '.join(illeggibili)}. "
                   f"Ogni voce dev'essere un identificatore, o un elenco di "
                   f"identificatori.")
    if not ha_target and not _allows_empty_target(domain, definition):
        return _no("serve un bersaglio: «entita» con gli id esatti, oppure "
                   "«aree», «piani», «etichette» o «dispositivi» -- Home "
                   "Assistant risolve da se' cosa contengono, e non serve "
                   "elencare le entita' a mano.")
    # Se `ha_target` e' vuoto ED e' arrivato fin qui, il servizio non
    # dichiara un target ED e' un recapito (review indipendente, punto ①):
    # non si rifiuta subito, si scende fino in fondo alla funzione -- che
    # riconosce questo caso all'UNICO altro punto in cui puo' arrivarci
    # vuoto -- cosi' i controlli sui parametri restano gli stessi di ogni
    # altra chiamata, invece di separare un binario apposta per lui.

    # Le entita' che il modello ha NOMINATO restano strette, anche quando
    # arrivano insieme a un'area: un id inventato o di un altro dominio e' una
    # sua affermazione sbagliata, e il rifiuto che dice quale glielo fa
    # correggere. Le entita' che escono da un'area sono un'altra cosa -- le
    # dice Home Assistant, non lui -- e si filtrano piu' sotto.
    nominate = ha_target.get("entity_id") or []
    for eid in nominate:
        if eid not in states:
            return _no(f"l'entita' «{eid}» non esiste in questa casa.")
        if domain not in _DOMINI_UNIVERSALI and domain_of(eid) != domain:
            return _no(f"«{reading}» non si applica a «{eid}», che e' del "
                       f"dominio «{eid.split('.')[0]}».")

    data = call.get("dati") or {}
    if not isinstance(data, dict):
        return _no("«dati» dev'essere un oggetto di parametri.")
    # `fields` arriva gia' normalizzato dal registro (`registro._fields`): o una
    # mappa di nomi, o `None` quando c'era ma in una forma che nessuno ha
    # saputo leggere. Il controllo `isinstance` qui non e' una ripetizione di
    # quello: e' cio' che rende vera, da sola, la promessa del docstring della
    # porta -- «non solleva mai». Prima era `set(definition.get("fields") or
    # {})`, e un `fields` che fosse una lista di oggetti faceva risalire un
    # `TypeError` fino al modello, che riceveva `unhashable type: 'dict'` come
    # motivo del rifiuto. Un registro costruito altrove, o una forma futura,
    # non deve poter riaprire quella strada.
    fields = definition.get("fields", {})
    if isinstance(fields, dict):
        names = {c for c in fields if isinstance(c, str)}
        for key in data:
            if key not in names:
                if not names:
                    return _no(f"«{reading}» non accetta parametri, e ne hai passato «{key}».")
                return _no(f"«{key}» non e' un parametro di «{reading}». "
                           f"Quelli veri sono: {_list(names)}.")
    # Se non e' una mappa non si verifica: rifiutare vorrebbe dire elencare
    # «quelli veri» senza saperli, o dire «non accetta parametri» di un
    # servizio che ne ha -- una frase falsa detta con sicurezza, e per giunta
    # su OGNI servizio della casa se la forma vera fosse quella. Lasciar
    # passare costa un errore chiaro di Home Assistant, che il modello legge e
    # da cui si corregge: e' la stessa regola gia' dichiarata qui sopra per i
    # valori dei parametri.

    if not ha_target:
        # Ci si arriva SOLO se il controllo sopra ha gia' lasciato passare
        # perche' il servizio non dichiara un target ED e' un recapito: un
        # bersaglio vuoto e' la forma giusta per chiamarlo, non un errore
        # (review indipendente, punto ①). Vedi `Verdict.no_target`.
        return Verdict(ok=True, domain=domain, service=name,
                        entity=(), target={}, no_target=True)

    if set(ha_target) == {"entity_id"}:
        # Il caso di sempre: il modello ha detto esattamente cosa toccare, e
        # non c'e' niente da risolvere. Le capacita' fini si guardano QUI,
        # dove l'elenco delle entita' e' gia' definitivo: e' il primo dei due
        # punti in cui `_capability_refusal` viene chiamata.
        rejection = _capability_refusal(reading, domain, definition, data,
                                        nominate, states)
        if rejection:
            return _no(rejection)
        return Verdict(ok=True, domain=domain, service=name,
                        entity=tuple(nominate), target=ha_target)

    if resolved is None:
        # Negativo, non «in attesa»: chi non sa risolvere non esegue. Il
        # motivo non e' scritto per il modello -- non gli arriva mai, la porta
        # risolve e richiama -- ma per chi cablasse questa funzione altrove.
        return Verdict(ok=False, domain=domain, service=name,
                        target=ha_target, da_risolvere=True,
                        reason="questo bersaglio nomina aree, piani, etichette o "
                               "dispositivi: va risolto da Home Assistant prima "
                               "di poter essere eseguito.")

    non_esiste = _cosa_non_esiste(resolved)
    if non_esiste:
        # Si RIFIUTA, non si riduce. Eseguire su cio' che resta sarebbe fare
        # meno di quel che e' stato chiesto e dirlo in una nota che il modello
        # puo' non riferire -- cioe' lo stesso difetto di partenza, con un
        # alibi. E' anche la stessa disciplina che questa funzione usa da
        # sempre sulle entita' nominate: cio' che non esiste si dice, e chi ha
        # chiesto corregge.
        return _no(f"questo bersaglio nomina cose che non esistono in questa "
                   f"casa: {non_esiste}. Non ho toccato niente. Usa «search» per "
                   f"trovare il nome giusto e ripeti il comando.")

    trovate = [e for e in resolved.get("entita") or [] if isinstance(e, str)]
    if not trovate:
        return _no("il bersaglio esiste ma non contiene nessuna entita': "
                   "Home Assistant non ha niente da toccare li' dentro.")

    in_domain = [e for e in trovate
                   if domain in _DOMINI_UNIVERSALI or domain_of(e) == domain]
    scartate = [e for e in trovate if e not in set(in_domain)]
    if not in_domain:
        return _no(f"il bersaglio contiene {len(trovate)} entita' e nessuna e' del "
                   f"dominio «{domain}»: «{reading}» non si applica a niente di "
                   f"cio' che c'e' li' dentro.")

    # Un'entita' che sta nel registro e non nello specchio dello stato --
    # disabilitata, o di un'integrazione non caricata -- Home Assistant non la
    # tocca comunque: non e' fra i candidati del servizio. Tenerla nell'elenco
    # non la accenderebbe, e in cambio farebbe dire all'esito «non so cosa sia
    # cambiato» dell'INTERA chiamata, perche' di lei nessuno annuncera' mai
    # niente. Si toglie e si dichiara.
    tenute = [e for e in in_domain if e in states]
    sconosciute = [e for e in in_domain if e not in states]
    if not tenute:
        return _no(f"le {len(in_domain)} entita' del dominio «{domain}» che "
                   f"questo bersaglio contiene non hanno uno stato in questa casa "
                   f"(disabilitate, o non caricate): non c'e' niente che io possa "
                   f"toccare e poi rileggere.")

    # Il secondo punto in cui l'elenco e' definitivo: dopo la risoluzione di
    # Home Assistant, e sulle sole entita' TENUTE -- non su quelle scartate
    # per dominio o senza stato, che non verranno toccate comunque.
    rejection = _capability_refusal(reading, domain, definition, data, tenute, states)
    if rejection:
        return _no(rejection)

    return Verdict(ok=True, domain=domain, service=name, entity=tuple(tenute),
                    target=ha_target, scartate=tuple(scartate),
                    sconosciute=tuple(sconosciute))
