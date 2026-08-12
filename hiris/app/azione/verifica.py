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
"""
from dataclasses import dataclass, field

# I servizi di questo dominio si applicano a QUALUNQUE dominio di entita'
# (`homeassistant.turn_off` spegne luci, prese, media player...). Senza
# l'esenzione il controllo sul dominio rifiuterebbe chiamate legittime.
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
    campi = set(definizione.get("fields") or {})
    for chiave in dati:
        if chiave not in campi:
            if not campi:
                return _no(f"«{grezzo}» non accetta parametri, e ne hai passato «{chiave}».")
            return _no(f"«{chiave}» non e' un parametro di «{grezzo}». "
                       f"Quelli veri sono: {_elenco(campi)}.")

    return Verdetto(ok=True, dominio=dominio, servizio=nome, entita=tuple(entita))
