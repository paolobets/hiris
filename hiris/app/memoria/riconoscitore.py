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


def _normalizza(testo: str) -> str:
    """Minuscole, accenti tolti, spazi multipli compressi.

    E' l'unica forma di "somiglianza" che questo modulo si concede: non e'
    ricerca approssimata, e' la stessa parola scritta in modo diverso.
    """
    testo = testo.lower()
    decomposto = unicodedata.normalize("NFKD", testo)
    senza_accenti = "".join(c for c in decomposto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", senza_accenti).strip()


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
        # pranzo" non collassa su "sala": l'ordine e' deciso una volta sola
        # qui, non a ogni chiamata di trova(). Le espressioni si compilano
        # qui una volta sola (non dentro trova()): l'indice e' gia' l'unico
        # posto in cui questo costo va pagato. Un testo normalizzato che piu'
        # voci condividono (due aree omonime, un alias che collide col nome
        # di un'altra) non viene deciso qui: resta un unico termine con piu'
        # candidati, ed e' trova() a dichiararlo, non a sceglierne uno.
        self._termini = [
            (candidati, _compila(termine))
            for termine, candidati in sorted(termini.items(), key=lambda kv: len(kv[0]), reverse=True)
        ]
        self._per_tipo = per_tipo

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
        """
        normalizzata = _normalizza(frase)
        if not normalizzata:
            return []

        intervalli_occupati: list[tuple[int, int]] = []
        trovate: list[tuple[int, dict]] = []
        for candidati, pattern in self._termini:
            for m in pattern.finditer(normalizzata):
                inizio, fine = m.span()
                if any(inizio < f and i < fine for i, f in intervalli_occupati):
                    continue
                intervalli_occupati.append((inizio, fine))
                trovate.append((inizio, {
                    "nome_visto": normalizzata[inizio:fine],
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


def costruisci_indice(casa: dict) -> Indice:
    """Costruisce l'indice di una casa: nome e alias di aree, entita' e
    dispositivi, normalizzati e pronti per trova()/verifica().

    Due voci diverse possono normalizzarsi allo stesso termine (due aree
    omonime, un alias che e' il nome vero di un'altra voce): il termine
    resta uno solo, ma raccoglie TUTTI i candidati che lo condividono,
    cosi' trova() puo' dichiarare l'ambiguita' invece di sceglierne uno in
    silenzio in base all'ordine di raccolta."""
    termini: dict[str, list[tuple[str, str]]] = {}
    per_tipo: dict[str, dict[str, dict]] = {}

    for chiave_archivio, tipo in _ARCHIVI:
        registro = per_tipo.setdefault(tipo, {})
        for voce in casa.get(chiave_archivio) or []:
            riferimento = voce.get("id")
            if riferimento is None:
                continue
            registro[riferimento] = voce

            nome = voce.get("nome") or ""
            for termine_originale in [nome, *(voce.get("alias") or [])]:
                termine_normalizzato = _normalizza(termine_originale)
                if not termine_normalizzato:
                    continue
                candidato = (tipo, riferimento)
                candidati = termini.setdefault(termine_normalizzato, [])
                if candidato not in candidati:
                    candidati.append(candidato)

    return Indice(termini, per_tipo)
