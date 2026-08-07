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


class Indice:
    """L'indice dei nomi e alias di una casa, pronto per riconoscere e
    verificare. Si costruisce con `costruisci_indice()`, non direttamente."""

    def __init__(self, termini: list[tuple[str, str, str]],
                 per_tipo: dict[str, dict[str, dict]]) -> None:
        # I termini piu' lunghi vincono e consumano il testo, cosi' "sala da
        # pranzo" non collassa su "sala": l'ordine e' deciso una volta sola
        # qui, non a ogni chiamata di trova(). A parita' di lunghezza resta
        # l'ordine di raccolta (aree, poi entita', poi dispositivi) perche'
        # sorted() e' stabile.
        self._termini = sorted(termini, key=lambda t: len(t[0]), reverse=True)
        self._per_tipo = per_tipo

    def trova(self, frase: str) -> list[dict]:
        """I riferimenti riconosciuti in `frase`, sui confini di parola.

        Nessun risultato non e' un errore: e' la regola (3) della struttura
        (docs/design/2026-08-05-la-conoscenza-di-hiris.md) -- "non riconosce
        niente? resta testo e funziona come oggi". "cucinare" non nomina la
        cucina perche' il confine di parola dopo "cucina" non c'e'.
        """
        normalizzata = _normalizza(frase)
        if not normalizzata:
            return []

        intervalli_occupati: list[tuple[int, int]] = []
        trovate: list[tuple[int, dict]] = []
        for termine, tipo, riferimento in self._termini:
            if not termine:
                continue
            pattern = re.compile(r"\b" + re.escape(termine) + r"\b")
            for m in pattern.finditer(normalizzata):
                inizio, fine = m.span()
                if any(inizio < f and i < fine for i, f in intervalli_occupati):
                    continue
                intervalli_occupati.append((inizio, fine))
                trovate.append((inizio, {
                    "tipo": tipo,
                    "riferimento": riferimento,
                    "nome_visto": normalizzata[inizio:fine],
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
    dispositivi, normalizzati e pronti per trova()/verifica()."""
    termini: list[tuple[str, str, str]] = []
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
                if termine_normalizzato:
                    termini.append((termine_normalizzato, tipo, riferimento))

    return Indice(termini, per_tipo)
