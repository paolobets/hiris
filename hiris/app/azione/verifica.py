"""La parte che dice di no, e dice perche'.

Funzione pura: nessuna rete, nessun client, nessuno stato interno. Riceve
cio' che il modello propone, il registro (cosa esiste) e lo specchio dello
stato vivo (cosa c'e' in casa), e risponde un `Verdetto`.

**Perche' e' separata dalla porta.** La parte che decide se toccare la casa
non deve aver bisogno della casa per essere provata: qui ogni caso di rifiuto
ha un test che gira in millisecondi, senza Home Assistant.

**Cosa NON verifica, di proposito** -- e' dichiarato qui perche' un lettore
futuro non lo scambi per una dimenticanza:

- **i valori dei parametri.** Il registro porta i selettori, ma la loro
  varieta' e' grande: una validazione approssimativa RIFIUTEREBBE chiamate
  legittime, che e' peggio di lasciar passare un valore che Home Assistant
  rigetta con un errore chiaro. Il modello lo legge e si corregge.
- **le capacita' fini** (`supported_features`: questa luce si attenua?).
  Il controllo sul dominio copre il caso grosso. Il fine richiede di
  interpretare bitmask dominio per dominio: sta nella fetta dei costruttori,
  che ne ha piu' bisogno.
- **i parametri di un servizio il cui `fields` non e' leggibile.** Il registro
  li normalizza a `None` invece di indovinarli, e qui `None` non diventa
  «nessun parametro»: il controllo si salta. Rifiutare su cio' che non si e'
  potuto misurare significherebbe dire «non accetta parametri» a un servizio
  che ne ha -- e, se la forma vera di `/api/services` fosse quella, dirlo di
  ogni servizio della casa.

**I bersagli che non sono entita' (area, piano, etichetta, dispositivo).**
Fino alla fetta «i bersagli» questa funzione li rifiutava, e il difetto non
era il rifiuto: era cosa il modello faceva dopo. «Spegni tutto in cucina»
lo obbligava a chiamare `cerca`, raccogliere gli id a mano e passarli tutti
qui; se ne perdeva uno -- e su una cucina con quindici entita' ne perdeva uno
-- HIRIS ne spegneva quattordici e **dichiarava di aver spento tutto**. Una
risposta sbagliata detta con sicurezza.

A risolverli e' Home Assistant (`extract_from_target`, vedi
`proxy/ha_client.estrai_dal_bersaglio`), che questa funzione -- pura -- non
puo' chiamare. Quindi il giro e' in due tempi, e la parte che dice di no
resta UNA:

1. `verifica(chiamata, registro, stati)` su un bersaglio ricco risponde un
   verdetto NEGATIVO con `da_risolvere=True` e il bersaglio gia' tradotto
   nella forma di Home Assistant. Negativo e non «in attesa» di proposito:
   un chiamante che ignorasse il campo nuovo non eseguirebbe niente, invece
   di eseguire su un elenco vuoto.
2. la porta lo risolve e richiama `verifica(..., risolto=<cio' che HA ha
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
(`schedulatore/orologio.py` costruisce la sua chiamata con `"bersaglio": {}`,
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
from ..casa.anagrafe import dominio_di

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
# guarda l'entita' che gli si passa. Ma `target` vive nella stessa risposta di
# `/api/services` che nessuno ha ancora misurato -- la stessa da cui vengono
# entrambi gli altri difetti chiusi in questa passata -- e se in una casa vera
# quel campo mancasse anche dove serve, la restrizione rifiuterebbe
# `homeassistant.turn_off`, cioe' proprio la chiamata che il foglio delle
# prove dice che DEVE funzionare. Restringere al buio e' lo stesso difetto che
# allargare al buio. La nota B di `docs/prova-azione.md` chiede ora ENTRAMBI i
# versi, e chiede di guardare `target` nell'output della prova 1: con quel
# dato in mano la decisione si prende misurata.
_DOMINI_UNIVERSALI = frozenset({"homeassistant"})


def _dichiara_bersaglio(definizione: dict) -> bool:
    """Vero se questo servizio si aspetta un bersaglio (entita', area...).

    Review finale, rilievo CRITICO ①. Il campo e' `target` di
    `/api/services`, che `azione/registro.py` conserva TALE E QUALE (vedi il
    suo docstring): quando c'e' -- anche vuoto, `{}` -- il servizio accetta un
    bersaglio, e un bersaglio vuoto resta un errore, come e' sempre stato.
    Quando manca, o e' `None`, il servizio non lo dichiara affatto: e' il
    caso di `notify.*` e di parecchi servizi di sistema, che oggi HIRIS
    rifiuta SEMPRE anche quando non hanno niente da bersagliare -- il difetto
    per cui una promessa «chiedi» non poteva mai notificare (vedi
    `schedulatore/orologio.py::_mantieni_chiedi`).

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

    **Non basta da sola** -- vedi `_bersaglio_vuoto_e_legittimo`, che la
    combina con l'appartenenza alla famiglia dei recapiti: usata qui isolata
    allargherebbe su qualunque servizio senza `target`, non solo su chi
    serve davvero.
    """
    return isinstance(definizione.get("target"), dict)


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


def _bersaglio_vuoto_e_legittimo(dominio: str, definizione: dict) -> bool:
    """Vero se un bersaglio vuoto e' la forma giusta per QUESTA chiamata.

    Combina le due condizioni che, insieme, restano dentro il perimetro
    misurato: il servizio non dichiara un `target` (`_dichiara_bersaglio`) E
    il suo dominio e' uno dei recapiti (`_DOMINI_DI_RECAPITO`). La prima da
    sola era troppo larga -- vedi il docstring del modulo.
    """
    return dominio in _DOMINI_DI_RECAPITO and not _dichiara_bersaglio(definizione)


# I cinque modi in cui un bersaglio puo' nominare cio' che va toccato, e il
# campo di Home Assistant che gli corrisponde. Le chiavi sono quelle che il
# modello scrive (`strumenti.ESEGUI_TOOL_DEF`), i valori sono quelli di
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
BERSAGLI = {
    "entita": "entity_id",
    "dispositivi": "device_id",
    "aree": "area_id",
    "piani": "floor_id",
    "etichette": "label_id",
}

# Come si nomina, in un rifiuto, cio' che il bersaglio ha chiesto e non
# esiste. La chiave e' quella con cui `ha_client.estrai_dal_bersaglio`
# restituisce i mancanti; l'ordine e' quello in cui il rifiuto li elenca.
_MANCANTI = (
    ("piani_mancanti", "piani"),
    ("aree_mancanti", "aree"),
    ("dispositivi_mancanti", "dispositivi"),
    ("etichette_mancanti", "etichette"),
)


@dataclass(frozen=True)
class Verdetto:
    ok: bool
    motivo: str = ""
    dominio: str = ""
    servizio: str = ""
    entita: tuple[str, ...] = field(default_factory=tuple)
    # Il bersaglio nella forma di Home Assistant, gia' tradotto e ripulito:
    # e' cio' che si manda a `extract_from_target`. C'e' anche nei verdetti
    # positivi, cosi' l'esito puo' dire cosa e' stato chiesto e non solo cosa
    # ne e' uscito.
    bersaglio: dict = field(default_factory=dict)
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
    # `target` **ed e' un recapito** (vedi `_bersaglio_vuoto_e_legittimo`):
    # `entita` e `bersaglio` restano vuoti apposta, e non e' un difetto -- e'
    # la forma giusta per un servizio come `notify.*`, che non ha niente da
    # bersagliare. La porta lo legge per non iniettare `entity_id: []` (che
    # direbbe una cosa diversa da «nessun bersaglio») e per non aprire un
    # ascolto di stato che non avrebbe niente da attendere (review finale,
    # rilievo CRITICO ①; ristretto ai recapiti dalla review indipendente).
    senza_bersaglio: bool = False


def _no(motivo: str) -> Verdetto:
    return Verdetto(ok=False, motivo=motivo)


def traduci_bersaglio(bersaglio) -> tuple[dict, list[str]]:
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
    if not isinstance(bersaglio, dict):
        return {}, []
    tradotto: dict[str, list[str]] = {}
    illeggibili: list[str] = []
    for nostro, loro in BERSAGLI.items():
        voci = bersaglio.get(nostro)
        if voci is None:
            continue
        if isinstance(voci, str):
            voci = [voci]
        if not isinstance(voci, list):
            illeggibili.append(f"«{nostro}» non e' un elenco")
            continue
        buone = []
        for voce in voci:
            if isinstance(voce, str) and voce.strip():
                buone.append(voce.strip())
            else:
                illeggibili.append(f"«{nostro}» contiene {voce!r}, "
                                   f"che non e' un identificatore")
        if buone:
            tradotto[loro] = buone
    return tradotto, illeggibili


def _cosa_non_esiste(risolto: dict) -> str:
    """L'elenco di cio' che il bersaglio nominava e non esiste, gia' scritto.

    Stringa vuota quando esiste tutto. E' separata dal resto perche' e' la
    meta' della risposta di Home Assistant che dice una cosa DIVERSA dalle
    entita': «quell'area non c'e'» non e' «quell'area e' vuota».
    """
    parti = []
    for chiave, nome in _MANCANTI:
        voci = [v for v in risolto.get(chiave) or [] if isinstance(v, str)]
        if voci:
            parti.append(f"{nome} {_elenco(voci)}")
    return "; ".join(parti)


def _elenco(voci, quante: int = 12) -> str:
    voci = sorted(voci)
    if len(voci) <= quante:
        return ", ".join(voci)
    return ", ".join(voci[:quante]) + f" (e altri {len(voci) - quante})"


def verifica(chiamata: dict, registro, stati: dict[str, dict],
             *, risolto: dict | None = None) -> Verdetto:
    """Il verdetto su una chiamata. `risolto` e' cio' che Home Assistant ha
    risposto su questo bersaglio (`ha_client.estrai_dal_bersaglio`), e serve
    solo ai bersagli che nominano aree, piani, etichette o dispositivi: su un
    bersaglio di sole entita' non si chiede niente a nessuno, ed e' voluto --
    un giro di rete per una cosa gia' scritta nella chiamata sarebbe un costo
    senza una domanda."""
    grezzo = chiamata.get("servizio")
    if not isinstance(grezzo, str) or grezzo.count(".") != 1:
        return _no("il servizio va scritto come «dominio.servizio», "
                   "per esempio «light.turn_off».")
    dominio, nome = grezzo.split(".")

    if dominio not in registro.domini():
        return _no(f"il dominio «{dominio}» non esiste in questa casa. "
                   f"Domini disponibili: {_elenco(registro.domini())}.")

    # `is None`, mai `if not`: il registro risponde `{}` -- falso in booleano
    # -- per un servizio che ESISTE ma non dichiara ne' campi ne' bersaglio.
    # Con la verita' booleana HIRIS rifiuterebbe una chiamata legittima, e
    # col motivo sbagliato («non esiste» invece di niente).
    definizione = registro.servizio(dominio, nome)
    if definizione is None:
        return _no(f"«{grezzo}» non esiste. I servizi di «{dominio}» sono: "
                   f"{_elenco(registro.servizi_di(dominio))}.")

    bersaglio_ha, illeggibili = traduci_bersaglio(chiamata.get("bersaglio"))
    if illeggibili:
        # Prima di dire «non c'e' niente»: un bersaglio scritto meta' bene si
        # rifiuta INTERO. Tradurne la meta' buona e tacere l'altra vorrebbe
        # dire toccare meno di quanto e' stato chiesto senza dirlo.
        return _no(f"questo bersaglio non si legge: {'; '.join(illeggibili)}. "
                   f"Ogni voce dev'essere un identificatore, o un elenco di "
                   f"identificatori.")
    if not bersaglio_ha and not _bersaglio_vuoto_e_legittimo(dominio, definizione):
        return _no("serve un bersaglio: «entita» con gli id esatti, oppure "
                   "«aree», «piani», «etichette» o «dispositivi» -- Home "
                   "Assistant risolve da se' cosa contengono, e non serve "
                   "elencare le entita' a mano.")
    # Se `bersaglio_ha` e' vuoto ED e' arrivato fin qui, il servizio non
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
    nominate = bersaglio_ha.get("entity_id") or []
    for eid in nominate:
        if eid not in stati:
            return _no(f"l'entita' «{eid}» non esiste in questa casa.")
        if dominio not in _DOMINI_UNIVERSALI and dominio_di(eid) != dominio:
            return _no(f"«{grezzo}» non si applica a «{eid}», che e' del "
                       f"dominio «{eid.split('.')[0]}».")

    dati = chiamata.get("dati") or {}
    if not isinstance(dati, dict):
        return _no("«dati» dev'essere un oggetto di parametri.")
    # `fields` arriva gia' normalizzato dal registro (`registro._campi`): o una
    # mappa di nomi, o `None` quando c'era ma in una forma che nessuno ha
    # saputo leggere. Il controllo `isinstance` qui non e' una ripetizione di
    # quello: e' cio' che rende vera, da sola, la promessa del docstring della
    # porta -- «non solleva mai». Prima era `set(definizione.get("fields") or
    # {})`, e un `fields` che fosse una lista di oggetti faceva risalire un
    # `TypeError` fino al modello, che riceveva `unhashable type: 'dict'` come
    # motivo del rifiuto. Un registro costruito altrove, o una forma futura,
    # non deve poter riaprire quella strada.
    campi = definizione.get("fields", {})
    if isinstance(campi, dict):
        nomi = {c for c in campi if isinstance(c, str)}
        for chiave in dati:
            if chiave not in nomi:
                if not nomi:
                    return _no(f"«{grezzo}» non accetta parametri, e ne hai passato «{chiave}».")
                return _no(f"«{chiave}» non e' un parametro di «{grezzo}». "
                           f"Quelli veri sono: {_elenco(nomi)}.")
    # Se non e' una mappa non si verifica: rifiutare vorrebbe dire elencare
    # «quelli veri» senza saperli, o dire «non accetta parametri» di un
    # servizio che ne ha -- una frase falsa detta con sicurezza, e per giunta
    # su OGNI servizio della casa se la forma vera fosse quella. Lasciar
    # passare costa un errore chiaro di Home Assistant, che il modello legge e
    # da cui si corregge: e' la stessa regola gia' dichiarata qui sopra per i
    # valori dei parametri.

    if not bersaglio_ha:
        # Ci si arriva SOLO se il controllo sopra ha gia' lasciato passare
        # perche' il servizio non dichiara un target ED e' un recapito: un
        # bersaglio vuoto e' la forma giusta per chiamarlo, non un errore
        # (review indipendente, punto ①). Vedi `Verdetto.senza_bersaglio`.
        return Verdetto(ok=True, dominio=dominio, servizio=nome,
                        entita=(), bersaglio={}, senza_bersaglio=True)

    if set(bersaglio_ha) == {"entity_id"}:
        # Il caso di sempre: il modello ha detto esattamente cosa toccare, e
        # non c'e' niente da risolvere.
        return Verdetto(ok=True, dominio=dominio, servizio=nome,
                        entita=tuple(nominate), bersaglio=bersaglio_ha)

    if risolto is None:
        # Negativo, non «in attesa»: chi non sa risolvere non esegue. Il
        # motivo non e' scritto per il modello -- non gli arriva mai, la porta
        # risolve e richiama -- ma per chi cablasse questa funzione altrove.
        return Verdetto(ok=False, dominio=dominio, servizio=nome,
                        bersaglio=bersaglio_ha, da_risolvere=True,
                        motivo="questo bersaglio nomina aree, piani, etichette o "
                               "dispositivi: va risolto da Home Assistant prima "
                               "di poter essere eseguito.")

    non_esiste = _cosa_non_esiste(risolto)
    if non_esiste:
        # Si RIFIUTA, non si riduce. Eseguire su cio' che resta sarebbe fare
        # meno di quel che e' stato chiesto e dirlo in una nota che il modello
        # puo' non riferire -- cioe' lo stesso difetto di partenza, con un
        # alibi. E' anche la stessa disciplina che questa funzione usa da
        # sempre sulle entita' nominate: cio' che non esiste si dice, e chi ha
        # chiesto corregge.
        return _no(f"questo bersaglio nomina cose che non esistono in questa "
                   f"casa: {non_esiste}. Non ho toccato niente. Usa «cerca» per "
                   f"trovare il nome giusto e ripeti il comando.")

    trovate = [e for e in risolto.get("entita") or [] if isinstance(e, str)]
    if not trovate:
        return _no("il bersaglio esiste ma non contiene nessuna entita': "
                   "Home Assistant non ha niente da toccare li' dentro.")

    del_dominio = [e for e in trovate
                   if dominio in _DOMINI_UNIVERSALI or dominio_di(e) == dominio]
    scartate = [e for e in trovate if e not in set(del_dominio)]
    if not del_dominio:
        return _no(f"il bersaglio contiene {len(trovate)} entita' e nessuna e' del "
                   f"dominio «{dominio}»: «{grezzo}» non si applica a niente di "
                   f"cio' che c'e' li' dentro.")

    # Un'entita' che sta nel registro e non nello specchio dello stato --
    # disabilitata, o di un'integrazione non caricata -- Home Assistant non la
    # tocca comunque: non e' fra i candidati del servizio. Tenerla nell'elenco
    # non la accenderebbe, e in cambio farebbe dire all'esito «non so cosa sia
    # cambiato» dell'INTERA chiamata, perche' di lei nessuno annuncera' mai
    # niente. Si toglie e si dichiara.
    tenute = [e for e in del_dominio if e in stati]
    sconosciute = [e for e in del_dominio if e not in stati]
    if not tenute:
        return _no(f"le {len(del_dominio)} entita' del dominio «{dominio}» che "
                   f"questo bersaglio contiene non hanno uno stato in questa casa "
                   f"(disabilitate, o non caricate): non c'e' niente che io possa "
                   f"toccare e poi rileggere.")

    return Verdetto(ok=True, dominio=dominio, servizio=nome, entita=tuple(tenute),
                    bersaglio=bersaglio_ha, scartate=tuple(scartate),
                    sconosciute=tuple(sconosciute))
