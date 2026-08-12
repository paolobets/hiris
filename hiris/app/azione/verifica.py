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
- **i bersagli che non sono entita'** (area, dispositivo, etichetta). La
  fetta 1 fa solo entita', e il rifiuto lo dice: il modello puo' risolvere
  un'area in entita' con `cerca` e richiamare.
- **i parametri di un servizio il cui `fields` non e' leggibile.** Il registro
  li normalizza a `None` invece di indovinarli, e qui `None` non diventa
  «nessun parametro»: il controllo si salta. Rifiutare su cio' che non si e'
  potuto misurare significherebbe dire «non accetta parametri» a un servizio
  che ne ha -- e, se la forma vera di `/api/services` fosse quella, dirlo di
  ogni servizio della casa.
"""
from dataclasses import dataclass, field

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


@dataclass(frozen=True)
class Verdetto:
    ok: bool
    motivo: str = ""
    dominio: str = ""
    servizio: str = ""
    entita: tuple[str, ...] = field(default_factory=tuple)


def _no(motivo: str) -> Verdetto:
    return Verdetto(ok=False, motivo=motivo)


def _elenco(voci, quante: int = 12) -> str:
    voci = sorted(voci)
    if len(voci) <= quante:
        return ", ".join(voci)
    return ", ".join(voci[:quante]) + f" (e altri {len(voci) - quante})"


def verifica(chiamata: dict, registro, stati: dict[str, dict]) -> Verdetto:
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

    bersaglio = chiamata.get("bersaglio") or {}
    entita = bersaglio.get("entita")
    # Una sola entita' arriva spesso come stringa nuda invece che come lista
    # di uno: e' una forma legittima, non un errore di forma da rifiutare.
    if isinstance(entita, str):
        entita = [entita]
    if not entita or not isinstance(entita, list):
        return _no("serve almeno un'entita' in «bersaglio.entita». "
                   "Se hai un'area e non le sue entita', usa prima «cerca».")

    for eid in entita:
        if not isinstance(eid, str) or eid not in stati:
            return _no(f"l'entita' «{eid}» non esiste in questa casa.")
        if dominio not in _DOMINI_UNIVERSALI and eid.split(".")[0] != dominio:
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

    return Verdetto(ok=True, dominio=dominio, servizio=nome, entita=tuple(entita))
