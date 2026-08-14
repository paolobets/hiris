"""Riconoscere di quale parte della casa parla una frase.

Oggi non esiste in HIRIS nessun codice che risolva un nome in un'entita':
nessuna normalizzazione, nessun indice sugli alias. Senza questo, "la sala
da pranzo" resta una parola e un'ancora di memoria non si puo' scrivere.

La semantica NON la fa questo modulo. Il modello, che ha la casa in
contesto, e' quello che capisce che "in salotto fa freddo" parla dell'area
"soggiorno" anche se l'utente non ha mai scritto quell'alias: e' esattamente
il principio della specifica -- il modello propone l'ancora nominando il suo
identificatore, e questo modulo restringe:

- `Indice.trova(frase)` e' la RETE: confronto letterale su nomi e alias
  DICHIARATI dall'utente in Home Assistant (sinonimi dati, non indovinati).
  Prende cio' che il modello si dimentica, e funziona anche senza modello.
  Due voci diverse possono normalizzarsi allo stesso testo (due aree
  chiamate "Bagno", un alias che e' il nome vero di un'altra area): quando
  succede, il termine e' AMBIGUO, e `trova()` lo dichiara -- ogni risultato
  porta la lista completa dei `candidati` che quel testo puo' significare,
  non uno scelto a caso. Scegliere spetta al modello, che ha la casa in
  contesto, o all'utente, che puo' correggere dalla pagina: questo modulo
  non sceglie per loro, si limita a non mentire.
- `Indice.verifica(tipo, riferimento)` e' il CANCELLO: controlla che
  l'identificatore che il modello ha nominato esista davvero, con quel
  tipo, nell'anagrafe. Se non esiste, l'ancora non si scrive.

Niente fuzzy, niente embedding: un sinonimo che l'utente non ha dichiarato
non e' un sinonimo, e di fabbrica l'embedder di HIRIS e' spento -- una
ricerca approssimata che ne dipendesse degraderebbe in silenzio.
"""
from __future__ import annotations

import re
import unicodedata

# Tipi che l'indice riconosce, nello spazio di nomi di verifica(): stessa
# forma dei termini che il modello vede quando la casa gli e' data in
# contesto, cosi' l'ancora che nomina "area" o "entita" e' gia' la chiave
# con cui si cerca qui.
_ARCHIVI = (("aree", "area"), ("entita", "entita"), ("dispositivi", "dispositivo"))

# Stessa mappa di _ARCHIVI, capovolta: dato il tipo di un'ancora, la chiave
# del registro che l'anagrafe usa per quel tipo. Pubblica perche' serve a chi
# deve sapere se QUEL registro specifico ha risposto all'ultima lettura
# (`ArchivioCasa.non_disponibili()`), non solo se l'anagrafe intera e' stata
# letta -- vedi handlers_memoria.py.
CHIAVE_ARCHIVIO_PER_TIPO: dict[str, str] = {tipo: chiave for chiave, tipo in _ARCHIVI}


def _normalizza(testo: str) -> str:
    """Minuscole, accenti tolti, spazi multipli compressi.

    E' l'unica forma di "somiglianza" che questo modulo si concede: non e'
    ricerca approssimata, e' la stessa parola scritta in modo diverso.
    """
    testo = testo.lower()
    decomposto = unicodedata.normalize("NFKD", testo)
    senza_accenti = "".join(c for c in decomposto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", senza_accenti).strip()


def _normalizza_con_mappa(testo: str) -> tuple[str, list[int]]:
    """Come `_normalizza`, ma restituisce anche la mappa posizione
    normalizzata -> posizione originale.

    `trova()` cerca sul testo normalizzato, ma `nome_visto` deve restare
    cio' che l'utente ha scritto davvero (maiuscole, accenti, spaziatura),
    non il testo normalizzato: oggi non morde perche' nessuno lo archivia,
    ma nella fetta E sarebbe gia' una riscrittura silenziosa di cio' che
    l'utente ha detto -- e il testo e' la verita' (memoria/archivio.py,
    regola 1).

    Minuscolo e NFKD-senza-combinanti sono, carattere per carattere, quasi
    sempre 1:1; la compressione degli spazi multipli invece sposta le
    posizioni, quindi va tracciata esplicitamente invece di essere assunta.
    """
    minuscolo = testo.lower()
    grezzo: list[str] = []
    mappa_grezza: list[int] = []
    for indice_originale, carattere in enumerate(minuscolo):
        decomposto = unicodedata.normalize("NFKD", carattere)
        for c in decomposto:
            if unicodedata.combining(c):
                continue
            grezzo.append(c)
            mappa_grezza.append(indice_originale)

    normalizzato: list[str] = []
    mappa: list[int] = []
    spazio_precedente = True  # tronca anche gli spazi iniziali, come .strip()
    for c, indice_originale in zip(grezzo, mappa_grezza):
        if re.match(r"\s", c):
            if spazio_precedente:
                continue
            spazio_precedente = True
            normalizzato.append(" ")
            mappa.append(indice_originale)
        else:
            spazio_precedente = False
            normalizzato.append(c)
            mappa.append(indice_originale)
    while normalizzato and normalizzato[-1] == " ":
        normalizzato.pop()
        mappa.pop()
    return "".join(normalizzato), mappa


def _e_carattere_di_parola(carattere: str) -> bool:
    return re.match(r"\w", carattere) is not None


def _compila(termine: str) -> re.Pattern[str]:
    """Compila il pattern di un termine una volta sola: farlo a ogni
    chiamata di trova() si appoggia alla cache implicita di `re`, che ha un
    tetto fisso di 512 pattern condiviso con tutto il processo -- oltre
    quella soglia ricompila in continuazione, ed e' li' che il costo esplode
    (misurato: 7 ms a 200 entita', 76 ms a 300).

    `\\b` e' un punto di transizione tra un carattere di parola e uno che non
    lo e': se il bordo del termine e' gia' non-parola (una parentesi, un
    apostrofo), pretendere `\\b` li' non trova mai nulla, perche' nel
    linguaggio naturale dopo/prima di quel bordo viene uno spazio, un altro
    segno di punteggiatura o la fine della frase. Il confine si mette solo
    dove il bordo e' un carattere di parola."""
    prefisso = r"(?<!\w)" if _e_carattere_di_parola(termine[0]) else ""
    suffisso = r"(?!\w)" if _e_carattere_di_parola(termine[-1]) else ""
    return re.compile(prefisso + re.escape(termine) + suffisso)


class Indice:
    """L'indice dei nomi e alias di una casa, pronto per riconoscere e
    verificare. Si costruisce con `costruisci_indice()`, non direttamente."""

    def __init__(self, termini: dict[str, list[tuple[str, str]]],
                 per_tipo: dict[str, dict[str, dict]]) -> None:
        # I termini piu' lunghi vincono e consumano il testo, cosi' "sala da
        # pranzo" non collassa su "sala": l'ordine e' deciso una volta sola,
        # non a ogni chiamata di trova(). Un testo normalizzato che piu'
        # voci condividono (due aree omonime, un alias che collide col nome
        # di un'altra) non viene deciso qui: resta un unico termine con piu'
        # candidati, ed e' trova() a dichiararlo, non a sceglierne uno.
        #
        # Le espressioni pero' NON si compilano qui: costruisci_indice()
        # gira a ogni GET/PATCH di /api/memoria (handlers_memoria.py), ma
        # quelle rotte usano solo verifica() -- un accesso a dizionario.
        # Compilare un pattern per termine per una richiesta che non chiama
        # mai trova() e' lavoro morto (misurato: 16,8 ms a 380 voci). Si
        # compila pigri, alla prima trova(), e resta cache per la vita di
        # questo Indice.
        self._termini_grezzi = sorted(termini.items(), key=lambda kv: len(kv[0]), reverse=True)
        self._termini_compilati: list[tuple[list[tuple[str, str]], re.Pattern[str]]] | None = None
        self._per_tipo = per_tipo

    def _termini(self) -> list[tuple[list[tuple[str, str]], re.Pattern[str]]]:
        if self._termini_compilati is None:
            self._termini_compilati = [
                (candidati, _compila(termine)) for termine, candidati in self._termini_grezzi
            ]
        return self._termini_compilati

    def trova(self, frase: str) -> list[dict]:
        """I riferimenti riconosciuti in `frase`, sui confini di parola.

        Nessun risultato non e' un errore: e' la regola (3) della struttura
        (docs/design/2026-08-05-la-conoscenza-di-hiris.md) -- "non riconosce
        niente? resta testo e funziona come oggi". "cucinare" non nomina la
        cucina perche' il confine di parola dopo "cucina" non c'e'.

        Ogni risultato porta `candidati`, la lista di TUTTE le voci (tipo +
        riferimento) che quel testo puo' significare, e `ambiguo`, vero
        quando sono piu' di una. Non c'e' un "il" riferimento: un testo che
        piu' voci condividono e' ambiguo per costruzione, e questo modulo
        non sceglie al posto del modello o dell'utente.

        `nome_visto` e' il testo ORIGINALE (maiuscole, accenti, spaziatura
        di chi ha scritto la frase), non il testo normalizzato su cui si
        cerca: il testo e' la verita' (memoria/archivio.py, regola 1), e
        vale anche per il frammento riconosciuto, non solo per la frase
        intera.
        """
        normalizzata, mappa = _normalizza_con_mappa(frase)
        if not normalizzata:
            return []

        intervalli_occupati: list[tuple[int, int]] = []
        trovate: list[tuple[int, dict]] = []
        for candidati, pattern in self._termini():
            for m in pattern.finditer(normalizzata):
                inizio, fine = m.span()
                if any(inizio < f and i < fine for i, f in intervalli_occupati):
                    continue
                intervalli_occupati.append((inizio, fine))
                inizio_originale = mappa[inizio]
                fine_originale = mappa[fine - 1] + 1
                trovate.append((inizio, {
                    "nome_visto": frase[inizio_originale:fine_originale],
                    "candidati": [{"tipo": tipo, "riferimento": riferimento}
                                  for tipo, riferimento in candidati],
                    "ambiguo": len(candidati) > 1,
                }))

        trovate.sort(key=lambda t: t[0])
        return [voce for _, voce in trovate]

    def verifica(self, tipo: str, riferimento: str) -> dict | None:
        """L'oggetto dell'anagrafe se `riferimento` esiste con quel `tipo`,
        altrimenti None.

        E' il punto in cui "il modello propone, il codice restringe"
        diventa codice: un'ancora che il modello si e' inventata non entra.
        Nessuna somiglianza qui -- tipi diversi sono spazi di nomi diversi,
        e un id di entita' passato come area non deve passare.
        """
        return self._per_tipo.get(tipo, {}).get(riferimento)

    def tutti(self, tipo: str) -> list[dict]:
        """Tutte le voci dell'anagrafe di un tipo — aree, entita' o dispositivi.

        Serve a chi deve DEDURRE qualcosa dalla casa invece che verificarla:
        per esempio l'unita' di misura di un'area, che si ricava dall'entita'
        di quell'area la cui classe combacia con la grandezza. E' pubblico
        perche' altrimenti chi ne ha bisogno finisce a leggere `_per_tipo`, e
        un accoppiamento a un dettaglio interno si propaga in silenzio.
        """
        return list(self._per_tipo.get(tipo, {}).values())


def costruisci_indice(casa: dict,
                      nomi_di_ripiego: dict[str, str] | None = None) -> Indice:
    """Costruisce l'indice di una casa: nome e alias di aree, entita' e
    dispositivi, normalizzati e pronti per trova()/verifica().

    Due voci diverse possono normalizzarsi allo stesso termine (due aree
    omonime, un alias che e' il nome vero di un'altra voce): il termine
    resta uno solo, ma raccoglie TUTTI i candidati che lo condividono,
    cosi' trova() puo' dichiarare l'ambiguita' invece di sceglierne uno in
    silenzio in base all'ordine di raccolta.

    `nomi_di_ripiego` (entity_id -> `friendly_name`) NON e' un rimedio per i
    casi rari in cui il nome manca: sull'impianto del proprietario, misurato
    il 14 agosto, e' la STRADA NORMALE. `casa/archivio.py:133` prende il nome
    dell'entita' da `name or original_name` del REGISTRO, e li' il nome e'
    nullo QUASI OVUNQUE (le quattro valvole dell'irrigazione, le abat-jour);
    nello specchio dello stato vivo il `friendly_name` c'e' invece su TUTTE
    e 849 le entita' vive -- zero vuote -- e sono i nomi buoni:
    `valve.giardino_ingresso` -> «Giardino ingresso»,
    `light.abat_jour_sinistra_abat_jour_sinistra` -> «Abat-jour sinistra».

    HIRIS leggeva i nomi dal posto sbagliato, e senza ripiego l'indice di
    ricerca e' quasi vuoto di nomi. Un'entita' senza nome non e' "non
    trovata": e' INESISTENTE nello spazio in cui si cerca -- nessun nome,
    nessun termine, invisibile. E' lo stesso criterio del nucleo: il modello
    perde la possibilita' di sapere che quella cosa esiste, e sono i quattro
    giri di `cerca` bruciati sulle abat-jour.

    Il ripiego e' il `friendly_name`, non l'`entity_id`: e' cio' che Home
    Assistant mostra all'utente ed e' la parola che una persona userebbe
    parlando. Lo specchio dello stato lo conserva gia'
    (`proxy/entity_cache._to_minimal`, chiave "name"). Un id tecnico non
    entra qui, ne' tale e quale ne' ingentilito: sarebbe un nome che nessuno
    ha mai pronunciato. E i nomi veri portano in dote un raggruppamento che
    nessun meccanismo deve costruire: quattro «Giardino ...» dicono da soli
    che sono un impianto solo.

    Un nome dedotto **non si spaccia per dichiarato**: la voce guadagna
    `nome_dedotto` e `nome` resta com'era nel registro (vuoto o None: non si
    riscrive). Chi legge puo' dirlo, e chi confronta i nomi DICHIARATI
    dall'utente non inciampa in uno che l'utente non ha mai scritto. Vale il
    doppio proprio perche' qui il dedotto e' la norma, non l'eccezione.

    **Cio' che il ripiego non copre, e che non si nasconde:** lo specchio
    dello stato conosce solo le entita' con uno stato vivo -- 849 contro le
    1.225 del registro. Per le altre 376 non esiste un `friendly_name` da
    nessuna parte: restano senza nome e quindi fuori da `trova()`,
    esattamente come oggi. Non spariscono (`verifica()` e `tutti()`
    continuano a vederle) e non si inventa loro un nome dall'id.

    Il ripiego vale solo per le entita': lo specchio dello stato non ha
    `friendly_name` per aree e dispositivi, e un ripiego li' sarebbe di
    nuovo un id travestito da nome.
    """
    termini: dict[str, list[tuple[str, str]]] = {}
    per_tipo: dict[str, dict[str, dict]] = {}
    ripiego = nomi_di_ripiego or {}

    for chiave_archivio, tipo in _ARCHIVI:
        registro = per_tipo.setdefault(tipo, {})
        for voce in casa.get(chiave_archivio) or []:
            riferimento = voce.get("id")
            if riferimento is None:
                continue

            nome = voce.get("nome") or ""
            dedotto = ""
            if not nome.strip() and tipo == "entita":
                dedotto = (ripiego.get(riferimento) or "").strip()
            if dedotto:
                # Copia, non mutazione in place: `voce` e' il dizionario che
                # `ArchivioCasa.leggi()` ha appena costruito per il
                # chiamante, e marcarlo li' accoppierebbe l'indice al ciclo
                # di vita di una struttura che non gli appartiene.
                voce = dict(voce)
                voce["nome_dedotto"] = dedotto
            registro[riferimento] = voce

            for termine_originale in [dedotto or nome, *(voce.get("alias") or [])]:
                termine_normalizzato = _normalizza(termine_originale)
                if not termine_normalizzato:
                    continue
                candidato = (tipo, riferimento)
                candidati = termini.setdefault(termine_normalizzato, [])
                if candidato not in candidati:
                    candidati.append(candidato)

    return Indice(termini, per_tipo)
