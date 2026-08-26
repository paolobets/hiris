"""L'aggregazione: dai cambi grezzi agli oggetti.

**Un oggetto e' una cosa compiuta della casa**: qualcosa che e' cominciato, e'
durato, e' finito -- con dentro chi lo ha fatto e cosa c'era attorno mentre
durava.

    Riscaldamento camera: acceso 15:30 -> 17:05. Temperatura da 18,2 a 21,0.

**E' l'unico posto di questa fetta dove si giudica**, ed e' voluto: un giudizio
qui si rifa' finche' il grezzo esiste (22 giorni: 21 di promessa, uno di
guardia -- vedi `archivio.CONSERVAZIONE_CAMBI_S`), uno preso in scrittura non
si corregge piu'.

**L'obiettivo sceglie QUALI entita', la natura decide CHE TIPO di oggetto ne
esce.** Nessuna delle due e' una lista scritta a mano: la natura la dichiara
Home Assistant.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..casa.tempo import _zona
from .pavimento import gamba

# `aggrega_giorno` e' SINCRONA: non fa nessuna lettura di rete. I comprimari
# arrivano gia' risolti dal chiamante (vedi il Task 6), proprio perche' una
# chiamata a `legami` dentro il ciclo farebbe migliaia di richieste per una
# giornata. Renderla `async` "per il futuro" sarebbe generalita' speculativa.

GENERI = ("funzionamento", "presenza", "consumo", "guasto")

# I domini che «funzionano»: si accendono e si spengono, si aprono e si
# chiudono. Sono i protagonisti degli oggetti di funzionamento.
_FUNZIONANO = frozenset({"climate", "cover", "switch", "light", "fan", "water_heater"})
# Gli stati che valgono «spento/chiuso/finito». "locked" e "disarmed" sono gli
# «a riposo» della sesta gamba (serratura, pannello dell'allarme): senza
# questi due un lock/alarm_control_panel che apre un oggetto non si
# richiuderebbe mai, perche' ne' "locked" ne' "unlocked" (ne' "armed_*"/
# "disarmed") sono "off" o "closed" in inglese.
_SPENTO = frozenset({"off", "closed", "unavailable", "unknown", "none", "",
                     "locked", "disarmed"})


def genere_di(soggetto: str, gamba_: str | None) -> str | None:
    """Che tipo di oggetto puo' nascere da questo soggetto, o `None` se non ne
    nasce nessuno.

    **I sensori da soli non generano oggetti**: «la temperatura e' salita» non
    e' una cosa compiuta, e' il CONTESTO di qualcosa che e' successo. Se ne
    generassero, una giornata ne produrrebbe migliaia e nessuno sarebbe
    leggibile.

    **La sesta gamba (sicurezza) e' un guasto, non un buco.** Serrature,
    pannello dell'allarme, sirene, e i sensori di fumo/gas/monossido/
    allagamento/manomissione/guasto/calore/gelo sono una minaccia, non un
    funzionamento normale: hanno la stessa forma di una condizione di
    sistema -- nascono, durano, finiscono o restano aperti. La review del
    primo task ha gia' trovato una volta il buco di dimenticarli (spec §4);
    qui il criterio e' `gamba_ == "sicurezza"`, qualunque sia il dominio, cosi'
    non serve ripetere l'elenco dei domini/classi che il pavimento gia' tiene.
    """
    if soggetto.startswith(("problema:", "integrazione:")):
        return "guasto"
    dominio = soggetto.split(".")[0]
    if dominio in _FUNZIONANO:
        return "funzionamento"
    if dominio in ("person", "device_tracker"):
        return "presenza"
    if dominio == "sensor" and gamba_ == "consumo":
        return "consumo"
    if gamba_ == "sicurezza":
        return "guasto"
    return None


def _gamba_del_cambio(soggetto: str) -> str | None:
    """La gamba del soggetto, per quanto si puo' saperne qui.

    Il grezzo non porta gli attributi dell'entita' (§3 della spec: «non porta
    il contesto attorno»), quindi `pavimento.gamba` viene chiamato SENZA
    attributi -- funziona per i domini che si risolvono dal solo nome (person,
    lock/alarm_control_panel/siren, climate, cover), non per quelli che
    dipendono da `device_class` (sensor, binary_sensor): la gamba VERA di quei
    domini e' nota solo al momento della scrittura (`osservatore.py`,
    `self._viste`) e non arriva fin qui. **E' un limite noto e dichiarato, non
    un difetto silenzioso**: `consumo` e i rilevatori di sicurezza per classe
    (fumo, gas, CO, ...) restano percio' non raggiungibili da questa funzione
    oggi -- si correggera' quando la classe entrera' nel grezzo, non
    indovinandola qui.
    """
    if soggetto.startswith(("problema:", "integrazione:")):
        return None
    return gamba(soggetto, {})


def _confini(giorno: str, fuso: str | None) -> tuple[float, float]:
    """L'inizio e la fine di un giorno **nel fuso della casa**.

    Le 23:30 di Roma sono le 21:30 UTC: un giorno calcolato in UTC spezzerebbe
    ogni serata in due, e la fetta dello schedulatore ha gia' pagato un difetto
    di orologi diversi.

    **La finestra di `archivio.cambi` e' semi-aperta (`[da_ts, a_ts)`)**, e
    questi confini ci contano sopra cosi' come sono: un `-1` o un `-0.001` "per
    stare sicuri" riaprirebbe un buco di un secondo a ogni mezzanotte, e con
    due confini inclusivi un cambio esattamente a mezzanotte finirebbe contato
    in due giorni.
    """
    zona = _zona(fuso)
    inizio = datetime.fromisoformat(giorno).replace(tzinfo=zona)
    return inizio.timestamp(), (inizio + timedelta(days=1)).timestamp()


def _acceso(valore) -> bool:
    return str(valore or "").strip().lower() not in _SPENTO


def aggrega_giorno(*, archivio, giorno: str, fuso: str | None,
                         comprimari=None) -> int:
    """Costruisce gli oggetti di un giorno. Torna quanti ne ha scritti.

    **Idempotente**: rifare un giorno lo SOSTITUISCE, non lo accoda. Gli
    oggetti si accumulano in una lista e si consegnano tutti insieme, in una
    volta sola, ad `archivio.sostituisci_giorno` -- cancellare e poi inserire
    uno per uno, con un commit per ciascuno, lascerebbe un giorno mezzo
    scritto indistinguibile da uno completo se qualcosa muore a meta'. E'
    esattamente il difetto gemello che il vecchio «costruire» ha gia' pagato
    (accodava invece di sostituire, e le ancore YAML lo nascondevano).

    `comprimari(soggetto) -> list[str]` dice quali altre cose stanno con il
    protagonista. E' iniettabile perche' nella vita vera lo chiede a `legami`
    (una chiamata di rete) e nei test no. **Non si indovina dal nome**: e' il
    caso misurato del lampadario, dove tre lampade, il loro gruppo e
    l'interruttore fisico sono un sistema solo.
    """
    da_ts, a_ts = _confini(giorno, fuso)
    righe = archivio.cambi(da_ts=da_ts, a_ts=a_ts)

    # Prima passata: le misure, per soggetto. Servono come contesto e non
    # generano oggetti da sole.
    misure: dict[str, list[tuple[float, str]]] = {}
    for r in righe:
        misure.setdefault(r["soggetto"], []).append((r["quando_ts"], r["a"]))

    aperti: dict[str, dict] = {}
    costruiti: list[dict] = []

    def chiudi(soggetto: str, quando: float | None) -> None:
        o = aperti.pop(soggetto, None)
        if o is None:
            return
        corpo = {"stato": o["stato"], "comprimari": [], "misure": {}}
        for altro in (comprimari(soggetto) if comprimari else []):
            # Il limite superiore e' la fine della GIORNATA (`a_ts`), non
            # l'istante di chiusura dell'oggetto: «temperatura da 18,2 a
            # 21,0» dell'esempio fondativo e' l'ultima misura nota di quella
            # giornata per il comprimario, anche se arriva dopo che il
            # riscaldamento si e' spento -- e' cio' che si sapeva della
            # grandezza collegata mentre l'oggetto durava E subito dopo,
            # prima del prossimo cambio di argomento.
            punti = [(t, v) for t, v in misure.get(altro, [])
                     if o["inizio"] <= t < a_ts]
            corpo["comprimari"].append(altro)
            if punti:
                corpo["misure"][altro] = {"da": punti[0][1], "a": punti[-1][1]}
        costruiti.append({"genere": o["genere"], "protagonista": soggetto,
                          "inizio_ts": o["inizio"], "fine_ts": quando,
                          "corpo": corpo})

    for r in righe:
        soggetto = r["soggetto"]
        genere = genere_di(soggetto, _gamba_del_cambio(soggetto))
        if genere is None:
            continue
        if genere == "guasto":
            if soggetto.startswith(("problema:", "integrazione:")):
                # Convenzione di sistema (`osservatore.guarda_sistema`):
                # "aperto" nasce, "chiuso" e nient'altro finisce.
                if r["a"] == "aperto":
                    aperti[soggetto] = {"genere": genere, "inizio": r["quando_ts"],
                                        "stato": "aperto"}
                else:
                    chiudi(soggetto, r["quando_ts"])
            else:
                # Sesta gamba, entita' vera: stessa logica acceso/spento del
                # funzionamento -- il genere e' diverso, la forma no.
                if _acceso(r["a"]):
                    if soggetto not in aperti:
                        aperti[soggetto] = {"genere": genere, "inizio": r["quando_ts"],
                                            "stato": r["a"]}
                else:
                    chiudi(soggetto, r["quando_ts"])
            continue
        if genere == "presenza":
            # «home» e' il riposo, come «off» lo e' per un funzionamento:
            # l'oggetto e' l'ASSENZA, «fuori casa dalle 8:10 alle 17:34», non
            # il ritorno. Trattare anche il ritorno come un secondo oggetto
            # aperto duplicherebbe lo stesso fatto (l'orario del rientro e'
            # gia' `fine_ts` dell'assenza) e a fine giornata lascerebbe per
            # sempre un oggetto «in casa» ancora aperto, per ogni persona,
            # ogni notte -- rumore, non un fatto compiuto.
            if r["a"] == "home":
                chiudi(soggetto, r["quando_ts"])
            elif soggetto not in aperti:
                aperti[soggetto] = {"genere": genere, "inizio": r["quando_ts"],
                                    "stato": r["a"]}
            continue
        if genere == "funzionamento":
            if _acceso(r["a"]):
                if soggetto not in aperti:
                    aperti[soggetto] = {"genere": genere, "inizio": r["quando_ts"],
                                        "stato": r["a"]}
            else:
                chiudi(soggetto, r["quando_ts"])
            continue
        if genere == "consumo" and soggetto not in aperti:
            aperti[soggetto] = {"genere": genere, "inizio": r["quando_ts"],
                                "stato": r["a"]}

    # Cio' che a fine giornata e' ancora in corso resta APERTO: `fine_ts` a
    # `None` e' un fatto, zero direbbe «finita subito».
    for soggetto in list(aperti):
        chiudi(soggetto, None)

    return archivio.sostituisci_giorno(giorno, costruiti)
