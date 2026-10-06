"""Cio' che il cervello guarda e ha capito, da leggere: un oggetto solo per la
pagina e per il modello (Tappa 5, Task 8; R8 della spec «Una fonte sola di
verita'», decisione D1 del piano: «iniettare»).

**Perche' un oggetto, e non le rotte.** Fino al 06/10/2026 le composizioni
che rendono leggibile lo scope, i resoconti e le analisi -- l'integrazione
delle voci tecniche, le escluse, le righe al giorno, i nomi risolti adesso, gli esiti
dell'attuatore accanto alla loro osservazione -- vivevano DENTRO le rotte di
`api/handlers_mind.py`. La pagina le vedeva; il modello no, perche' una rotta
non e' un metodo che uno strumento puo' chiamare. E' la fondamenta 4: un dato
che c'e' e nessuno puo' chiedere non esiste. Qui vivono una volta, e la rotta
e lo strumento `mind` (`home_space/tools.py`) chiamano gli stessi metodi:
stessa risposta da tutte e due le porte (fondamenta 3).

**Perche' lo si inietta.** `home_space` non importa da `mind`
(`tests/test_confine_home_space.py`, `AMMESSI` vuoto): il dispatcher degli
strumenti riceve questo oggetto gia' costruito, come riceve il sapere, la
cronaca e l'officina (`api/handlers_chat.create_tool_dispatcher`).

**Le parti che mancano si dichiarano `None`/`[]`, non si inventano.** Chi
costruisce questo oggetto gli passa cio' che c'e'; un archivio assente non e'
un archivio vuoto, e la distinzione la fa chi chiama (la rotta con un 503, lo
strumento con un `errore`).
"""
from __future__ import annotations

from datetime import timedelta

from ..home_space import historian
from ..home_space.house import House
from ..home_space.log_source import integration_of
from ..home_space.topology import read_mirror
from .actuator import observation_key
from .report import NIGHTLY_HOUR, NIGHTLY_MINUTE, as_page

#: Quanti giorni di righe grezze si mostrano (`volume`). **Non e' la durata del grezzo**
#: (22 giorni, `store.READING_RETENTION_S`): e' quanto serve a vedere se il
#: filtro dello scope sta funzionando -- una settimana, cioe' abbastanza da
#: distinguere un giorno storto da una tendenza.
VOLUME_DAYS = 7

#: Quanti giorni di resoconti e di analisi escono quando non se ne chiede uno.
#: Lo stesso numero che le rotte usavano dal 13/09/2026, quando vivevano in
#: `api/handlers_mind.py`.
RECENT_DAYS = 30


class MindView:
    """Le letture del cervello: lo scope, l'obiettivo, i resoconti, le analisi.

    - `store`: l'archivio delle osservazioni (`mind/store.ObservationsStore`);
    - `watcher`: l'osservatore (`mind/watcher.Watcher`), per cio' che si guarda;
    - `home_space`: l'anagrafe (`home_space/reader.HomeSpace`), per i nomi dei
      dispositivi, la fonte di ogni soggetto e il fuso della casa;
    - `cache`: lo specchio dello stato vivo, per i nomi delle entita';
    - `judgments`: l'istantanea dei giudizi sui tipi, per il primo piano del
      resoconto (`report.as_page`).

    Ognuno puo' mancare: vedi il docstring del modulo.
    """

    def __init__(self, *, store=None, watcher=None, home_space=None, cache=None,
                 judgments=None) -> None:
        self.store = store
        self.watcher = watcher
        self._home_space = home_space
        self._cache = cache
        self._judgments = judgments

    # -- lo scope ---------------------------------------------------------

    def scope(self) -> dict | None:
        """**Cosa guardo, perche', da quando, e quanto costa**, in una
        risposta sola; `None` senza osservatore.

        Spec §5.1 e §11 **non sono due letture**: l'elenco di cio' che si
        guarda e' anche la prova che l'obiettivo e' stato capito, e chi legge
        deve poter confrontare le scelte con la domanda a cui rispondono.

        - `watching` -- cio' che si guarda, col **motivo** e l'**autore** di
          ogni voce (`Watcher.watching()`, che le prende dallo scope), e per
          ogni entita' la sua **fonte** (`House.source`: viva, spenta,
          sparita...);
        - `fuori` -- cio' che e' stato **lasciato fuori**, con la sua ragione.
          E' l'altra meta' della trasparenza: un elenco di sole cose guardate
          non direbbe se un'entita' manca perche' esclusa o perche' mai
          considerata;
        - `obiettivo` -- la domanda rispetto a cui si e' deciso;
        - `riconsiderazione` -- quando si e' ripensata tutta la casa, la
          **finestra di memoria misurata** e la **cadenza** che ne esce;
        - `tentativi` -- gli ultimi giri **riusciti o no**, dal piu' recente:
          risponde a «sta funzionando?». Misurato sulla casa vera
          l'11/09/2026: l'osservatore ha provato e fallito quattro volte in
          quaranta minuti, e la pagina diceva soltanto «non e' mai stata
          fatta»;
        - `volume` -- **quante righe grezze al giorno**: la contropartita
          onesta dello scope. Il 15/09/2026 ha smentito la promessa della spec
          §5.3 (-83%): rispondeva circa il triplo, perche' mancava la regola
          «chi ha `state_class` non si registra a campione».

        **Le parti che mancano si dichiarano `None`/`[]`**: l'osservatore puo'
        esserci e l'archivio no (avvio a meta', o un guasto).
        """
        if self.watcher is None:
            return None
        store = self.store
        return {
            "watching": _with_integration(self.watcher.watching(house=self._house_read())),
            "fuori": self._left_out(),
            "obiettivo": store.objective() if store is not None else None,
            "riconsiderazione": store.last_reconsideration() if store is not None else None,
            "tentativi": store.recent_attempts() if store is not None else None,
            "volume": self._volume(),
        }

    def objective(self) -> dict | None:
        """L'obiettivo della casa, la sola manopola del prodotto; `None`
        senza archivio. E' lo stesso `obiettivo` dello scope."""
        return self.store.objective() if self.store is not None else None

    def _house_read(self) -> House | None:
        """La casa del momento, per la fonte di ogni soggetto (Task 1.5, G-01).

        Senza anagrafe -- archivio assente, o nessuna lettura ancora riuscita
        (`HomeSpace.read()` torna `{}`) -- non si chiede: una casa vuota
        farebbe «sconosciuto» di ogni soggetto, che e' un'affermazione, non un
        silenzio."""
        if self._home_space is None:
            return None
        house = House.read(self._home_space, self._cache)
        return house if house.home_space else None

    def _left_out(self) -> list[dict]:
        """Cio' su cui qualcuno ha deciso **di no**, con la ragione e l'autore.

        Chi non e' nello scope affatto non compare: non e' stato lasciato
        fuori, non e' stato considerato -- e dirlo di 452 entita' riempirebbe
        la lettura di righe senza ragione accanto."""
        if self.store is None:
            return []
        return sorted(
            ({"soggetto": subject, "motivo": v["motivo"], "autore": v["autore"],
              "quando": v["quando"]}
             for subject, v in self.store.scope().items() if not v["dentro"]),
            key=lambda v: v["soggetto"])

    def _volume(self) -> list[dict]:
        """Quante righe grezze per ciascuno degli ultimi giorni, **dal piu'
        vecchio**: si legge come una tendenza, e una tendenza si legge in
        avanti.

        I confini sono quelli del giorno LOCALE (`historian.day_boundaries`
        col fuso della casa), gli stessi che usa l'aggregazione notturna: un
        conteggio su giorni UTC direbbe numeri che non combaciano con
        nessun'altra lettura."""
        if self.store is None:
            return []
        timezone = historian.house_timezone(self._home_space)
        today = historian.today(timezone)
        volume = []
        for back in range(VOLUME_DAYS - 1, -1, -1):
            day = (today - timedelta(days=back)).isoformat()
            from_ts, to_ts = historian.day_boundaries(day, timezone)
            volume.append({"giorno": day,
                           "righe": self.store.readings_count(from_ts=from_ts, to_ts=to_ts)})
        return volume

    # -- i resoconti ------------------------------------------------------

    def reports(self) -> list[dict]:
        """**Le misure degli ultimi giorni**, e l'obiettivo di ognuno.

        Solo le misure: la cronaca si chiede un giorno alla volta
        (`report(day)`). **E l'obiettivo di ogni giorno** (spec §11, trovato
        dalla live review del 15/09/2026): chi legge trenta giorni di misure
        in serie deve sapere se in mezzo la domanda e' cambiata, o legge una
        tendenza dove c'e' un cambio di domanda."""
        names = self.device_names()
        return [{"giorno": r.get("giorno"), "obiettivo": r.get("obiettivo"),
                 "misure": _named(names, r.get("misure"))}
                for r in self.store.reports(limit=RECENT_DAYS)]

    def report(self, day: str) -> dict | None:
        """Il resoconto di un giorno **reso** (`report.as_page`), o `None` se
        quel giorno non e' stato aggregato: «quel giorno non e' successo
        niente» e «quel giorno non l'abbiamo guardato» sono due cose diverse.

        **Misure E forme** portano il nome risolto adesso: portano lo stesso
        `soggetto`, e risolverne uno solo rifarebbe -- dentro la stessa
        risposta -- il difetto che la 3.46.0 ha chiuso fra misure e cronaca
        (revisione indipendente, 15/09/2026). Il nome sempre, e la banda di
        cio' che esce dal solito, sono della resa (spec 2026-09-18 §3): non
        toccano cio' che e' archiviato."""
        found = self.store.report(day)
        if found is None:
            return None
        names = self.device_names()
        found = {**found,
                 "misure": _named(names, found.get("misure")),
                 "forme": _named(names, found.get("forme"))}
        return as_page(found, judgments=self._judgments, names=self.entity_names())

    @staticmethod
    def nightly_time() -> str:
        """Quando si scrive il resoconto di un giorno, «HH:MM»: chi chiede un
        giorno non ancora aggregato lo riceve accanto al rifiuto (C-11,
        Tappa 4, Task 5), dalla rotta e dallo strumento."""
        return f"{NIGHTLY_HOUR:02d}:{NIGHTLY_MINUTE:02d}"

    # -- le analisi -------------------------------------------------------

    def analyses(self) -> list[dict]:
        """Le ultime analisi, dalla piu' recente, coi nomi risolti adesso."""
        names = self.device_names()
        return [{**a, "osservazioni": _named(names, a.get("osservazioni"))}
                for a in self.store.analyses(limit=RECENT_DAYS)]

    def analysis(self, day: str) -> dict | None:
        """L'analisi di un giorno, o `None` se quel giorno non e' stato
        analizzato: «ho guardato e non c'era niente da dire» e «non ho
        guardato» sono due cose diverse, e la prima e' una riga con zero
        osservazioni.

        **L'archivio dice cio' che sapeva; chi legge risolve cio' che puo'
        oggi.** Un'analisi si scrive una volta sola -- un giorno ne ha una --
        e quella del 15/09/2026 e' nata prima che i nomi dei dispositivi
        arrivassero: porta `nome: null`, e riscriverla costerebbe 35.000 token
        per cambiare un'etichetta. Accanto a ogni osservazione, l'esito
        dell'attuatore (`_with_outcomes`)."""
        found = self.store.analysis(day)
        if found is None:
            return None
        names = self.device_names()
        if names:
            found = {**found, "osservazioni": _named(names, found.get("osservazioni"))}
        return _with_outcomes(found)

    # -- i nomi -----------------------------------------------------------

    def device_names(self) -> dict:
        """I nomi dei dispositivi di **adesso**, o `{}` se l'anagrafe non c'e'.

        **Un posto solo.** Fino al 15/09/2026 una copia identica viveva anche
        in `server.py`; fino al 06/10/2026 questa stava in una rotta, e il
        server la importava da li'. Il nome, altrimenti l'id (`House.name`,
        A-16, 04/10/2026): un dispositivo senza nome usciva dalla mappa, e chi
        legge lo vedeva senza niente."""
        if self._home_space is None:
            return {}
        house = House.read(self._home_space, self._cache)
        return {device_id: house.name("dispositivo", device_id)
                for device_id in house.device_ids()}

    def entity_names(self) -> dict:
        """I nomi **vivi** delle entita', dallo specchio, o `{}` se non c'e'.

        Il gemello di `device_names`, per l'altro genere di soggetto: le
        misure parlano di dispositivi (l'anagrafe), la cronaca di entita' (lo
        specchio). **Serve perche' il grezzo il nome non sempre ce l'ha**:
        misurato sulla casa vera il 18/09/2026, 7 voci di cronaca su 75 erano
        senza, e fra loro l'allarme del piano terra.

        **I nomi li legge `topology.read_mirror`**, la stessa lettura dello
        specchio della ricerca e delle pagine (A-35, 03/10/2026); uno specchio
        guasto da' `{}` invece di far cadere chi legge (B-41)."""
        return read_mirror(self._cache).names


def _with_integration(lines: list[dict]) -> list[dict]:
    """Le voci tecniche con **l'integrazione da cui vengono, e il suo nome**.

    Misurato il 18/09/2026: dei 153 soggetti guardati 39 sono tecnici, e
    vengono da **30 logger distinti che sono 23 integrazioni**: trentanove
    righe per dirne ventitre.

    **La regola e' quella del primo piano** (`home_space/log_source.integration_of`),
    e non una seconda scritta qui o in JavaScript: due letture dello stesso
    logger darebbero due nomi per la stessa cosa nelle due schede della stessa
    pagina. Le voci che non sono tecniche non guadagnano nessuna chiave:
    `light.studio` ha un dominio, non un'integrazione."""
    seen = []
    for line in lines or []:
        subject = str(line.get("soggetto") or "")
        slug = None
        if subject.startswith("log:"):
            rest = subject[len("log:"):]
            slug = integration_of(rest.split("@")[0])
        elif subject.startswith("problema:"):
            slug = integration_of(subject[len("problema:"):])
        if slug:
            name, identifier = slug
            line = {**line, "integrazione": identifier, "nome": name}
        seen.append(line)
    return seen


def _named(names: dict, lines) -> list:
    """Le righe con **il nome del soggetto risolto dove manca**.

    **La regola e' una sola, e vale per ogni porta del cervello.** L'archivio
    dice cio' che sapeva; chi legge risolve cio' che puo' oggi. Una riga che
    il nome ce l'ha tiene il suo -- e' quello di ALLORA, ed e' piu' vero: un
    dispositivo si puo' rinominare. Un soggetto che l'anagrafe non conosce
    resta senza: chi legge vede l'identificatore, che e' la verita', non un
    buco. Misurato sulla casa vera il 15/09/2026: delle cinque porte del
    cervello **una sola** risolveva i nomi."""
    if not names:
        return list(lines or [])
    seen = []
    for line in lines or []:
        if isinstance(line, dict) and not line.get("nome"):
            found = names.get(line.get("soggetto"))
            line = {**line, "nome": found} if found else line
        seen.append(line)
    return seen


def _with_outcomes(analysis: dict) -> dict:
    """L'analisi con **l'esito dell'attuatore accanto alla sua osservazione**.

    Gli esiti sono la risposta alle domande dell'analista, e si leggono dove
    la domanda sta. La regola dell'impronta e' dell'attuatore
    (`actuator.observation_key`): rifarla in JavaScript sarebbe il secondo
    posto in cui si decide chi risponde a chi.

    **Chi non ha un esito non ne guadagna uno vuoto**: il silenzio
    dell'attuatore e' un fatto, e un `{}` somiglierebbe a una risposta."""
    actuation = analysis.get("attuazione") or {}
    by_key = {o.get("impronta"): o for o in actuation.get("esiti") or []
              if o.get("impronta")}
    if not by_key:
        return analysis
    seen = []
    for observation in analysis.get("osservazioni") or []:
        outcome = by_key.get(observation_key(observation))
        seen.append({**observation, "esito": outcome} if outcome else observation)
    return {**analysis, "osservazioni": seen}
