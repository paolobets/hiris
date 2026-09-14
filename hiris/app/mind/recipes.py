"""Le ricette: «come si calcola una cosa» e' un dato, e questo modulo lo esegue.

Spec `docs/design/2026-09-10-i-tre-attori.md` §7.

**Perche' esiste, con una prova storica -- e cosa questa fetta ne ha davvero
incassato.** Il 27/08/2026 la quota di autosufficienza di questa casa era
sbagliata: `autoconsumo/(autoconsumo + prelievo)` vale solo su certe
integrazioni, e su questa «autoconsumata» esclude la batteria -- misurato
**0,964 invece di 0,985**, e con piu' ciclo di accumulo **0,167 invece di
0,41**. Era *una ricetta specifica di un'integrazione, scritta dentro il motore
di aggregazione*, e per correggerla e' servito un rilascio.

**Quel rilascio servirebbe ancora**, e va detto invece di lasciarlo intuire
(revisione indipendente, 13/09/2026). La spec §7 vuole la ricetta **dentro il
sapere**, con provenienza e prove, cosi' da poterla correggere a caldo. Qui la
ricetta e' un dato **generato da un'altra funzione** e mai scritto
nell'archivio: non e' ancora quello. La meta' che vive in questo modulo e' la
meta' del motore -- si legge tutta, si valida, si rifiuta prima di eseguirla,
e i conti che compone stanno in un posto solo invece che in due. La meta' che
manca -- la ricetta come riga del sapere -- e' a backlog con la sua forma.

**Non e' un linguaggio, ed e' il punto.** Una sequenza di passi con nomi; un
passo puo' leggere il risultato dei passi **precedenti** e nient'altro. Niente
cicli, niente condizioni, niente funzioni nuove. E' cio' che rende una ricetta
leggibile tutta, provabile, e **rifiutabile prima di eseguirla** -- se un passo
potesse guardare avanti servirebbe un ordinatore, se due potessero guardarsi
servirebbe un rilevatore di cicli, e a quel punto non si sta piu' leggendo un
dato: si sta lanciando un programma.

**Si rifiuta, non si corregge.** Correggere una ricetta rotta vorrebbe dire
indovinare cosa intendeva chi l'ha scritta, ed e' il modo in cui una deduzione
diventa un fatto senza che nessuno se ne accorga. Il precedente della
disciplina e' `home_space/type_vocabulary.Field`: *«una prova dice che oggi
nessuno l'ha fatto, il costruttore dice che non si puo' fare»*.

## La forma del dato

    {
      "why": "l'inverter pesa sul risparmio energetico",
      "steps": [
        {"name": "consumata", "operation": "somma_periodo",
         "inputs": ["@sensor.energia_consumata_oggi"],
         "params": {"unit": "kWh", "expected_parts": 24}},
        {"name": "autosufficienza", "operation": "quota",
         "inputs": ["$autoprodotta", "$consumata"]}
      ]
    }

Le chiavi della struttura sono inglesi come il resto del codice; i **valori**
sono dominio -- i nomi delle operazioni (`somma_periodo`, `quota`) sono quelli
che il proprietario pronuncia, e i nomi dei passi li sceglie chi scrive la
ricetta. E' la stessa divisione di `GENRES` in `mind/facts.py`.

Un ingresso e' una di tre cose, e si riconosce dal primo carattere:

- `@qualcosa` -- la serie dell'entita' `qualcosa` nel periodo;
- `$qualcosa` -- il risultato del passo `qualcosa`, che deve venire **prima**;
- qualunque altra cosa -- un valore letterale, cosi' com'e'.

`params` sono i parametri per nome dell'operazione, **con i nomi che
l'operazione dichiara** (`unit`, `expected_parts`, `zone`, `reduce`): non c'e'
una seconda tabella che li traduce, perche' due tabelle divergono.
"""
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as _field

from .operations import REGISTRY, Result

#: Il carattere che dice «questa e' un'entita' della casa».
ENTITY_MARK = "@"
#: Il carattere che dice «questo e' il risultato di un passo precedente».
STEP_MARK = "$"


@dataclass(frozen=True)
class Validation:
    """L'esito di un controllo: valida, oppure **tutti** i problemi trovati.

    Tutti e non solo il primo: chi ha scritto la ricetta deve poterla
    correggere in un giro solo. Un rifiuto che dice un problema per volta
    costringe a tre giri di modello per tre errori, e ogni giro costa.
    """

    problems: list[str] = _field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.problems


class Recipe:
    """Una ricetta: il dato, il suo controllo, la sua esecuzione."""

    def __init__(self, data: dict) -> None:
        self._data = dict(data or {})
        self._steps = list(self._data.get("steps") or [])

    @property
    def why(self) -> str:
        return str(self._data.get("why") or "").strip()

    @property
    def steps(self) -> list[dict]:
        return list(self._steps)

    def entities(self) -> set[str]:
        """Le entita' che la ricetta nomina, **senza eseguirla**.

        Chi deve leggere le serie deve sapere quali prima di cominciare: e'
        cio' che permette **una lettura sola** di rete per tutta la ricetta
        invece di una per passo -- la stessa disciplina che `build_balances`
        applica gia' oggi alle statistiche orarie.
        """
        nomi: set[str] = set()
        for step in self._steps:
            for given in (step or {}).get("inputs") or []:
                if isinstance(given, str) and given.startswith(ENTITY_MARK):
                    nomi.add(given[1:])
        return nomi

    # -- il controllo ------------------------------------------------------

    def validate(self, *, entities: set[str]) -> Validation:
        """Cosa non va, tutto insieme. Vuoto = si puo' eseguire."""
        problems: list[str] = []
        if not self.why:
            problems.append(
                "la ricetta non dice PERCHE' esiste: senza la ragione non si "
                "puo' ne' rivederla ne' cancellarla quando l'obiettivo cambia")
        if not self._steps:
            problems.append(
                "la ricetta non ha nessun passo: non e' una ricetta che non "
                "calcola niente, e' una ricetta che nessuno ha finito di scrivere")

        seen: set[str] = set()
        for number, step in enumerate(self._steps, start=1):
            if not isinstance(step, dict):
                problems.append(f"il passo {number} non e' un passo: {step!r}")
                continue
            name = str(step.get("name") or "").strip()
            if not name:
                problems.append(f"il passo {number} non ha un nome, e nessuno "
                                "potra' leggerne il risultato")
            elif name in seen:
                problems.append(
                    f"il passo {number} si chiama «{name}» come uno precedente: "
                    "un riferimento a quel nome sarebbe ambiguo, e l'ambiguita' "
                    "non si risolve indovinando")
            operation = str(step.get("operation") or "").strip()
            problems.extend(self._problemi_operazione(
                operation, name or str(number), step.get("params"),
                step.get("inputs")))
            for given in step.get("inputs") or []:
                problems.extend(self._problemi_ingresso(
                    given, name or str(number), seen, entities))
            if name:
                seen.add(name)
        return Validation(problems)

    @staticmethod
    def _problemi_operazione(operation: str, step_name: str, params,
                             inputs) -> list[str]:
        """Quattro domande sull'operazione di un passo, e si fanno **tutte**.

        1. **esiste?** -- un nome fuori dal registro;
        2. **si puo' scrivere in una ricetta?** -- il registro e' il
           vocabolario del prodotto, e ne contiene voci che un dato non puo'
           portare: `episodio` vuole `is_on`, che e' una funzione. Prima del
           14/09/2026 questo controllo non c'era, il catalogo mostrava tutto al
           modello, e la prima ricetta che il modello abbia mai scritto ha
           ucciso la riaggregazione di due giorni con un `TypeError`;
        3. **ha i parametri obbligatori?** -- `somma_periodo` senza `unit`
           solleverebbe a meta' giornata invece di essere rifiutata prima di
           eseguire, che e' l'unica cosa che rende una ricetta un dato invece
           che codice;
        4. **quanti ingressi?** -- `quota` prende due cose; con tre, di nuovo
           `TypeError`.

        Le tre risposte che dipendono dalla forma di `run` si leggono dalla
        FIRMA (`required_params`, `input_range`), mai da un elenco scritto a
        mano accanto a essa: quello diverge al primo ritocco, ed e' la classe
        di difetto che questo progetto ha gia' pagato piu' volte.
        """
        if operation not in REGISTRY:
            return [(f"il passo «{step_name}» nomina l'operazione "
                     f"«{operation}», che non esiste nel registro")]
        entry = REGISTRY[operation]
        if not entry.in_recipes:
            return [(f"il passo «{step_name}» nomina l'operazione "
                     f"«{operation}», che **non si puo' scrivere in una ricetta**: "
                     "vuole un valore che un dato non sa portare (una funzione, o "
                     "un periodo da calcolare). Esiste nel registro perche' la usa "
                     "il codice dell'aggregazione, non una ricetta")]
        given_params = params if isinstance(params, dict) else {}
        found = [f"il passo «{step_name}» non da' il parametro obbligatorio "
                    f"«{n}», che «{operation}» pretende"
                 for n in entry.required_params if n not in given_params]
        least, most = entry.input_range
        given_count = len(inputs) if isinstance(inputs, (list, tuple)) else 0
        if not (least <= given_count <= most):
            wanted = (f"{least}" if least == most else f"da {least} a {most}")
            found.append(
                f"il passo «{step_name}» consegna {given_count} ingressi a "
                f"«{operation}», che ne vuole {wanted}")
        return found

    @staticmethod
    def _problemi_ingresso(given, step_name: str, seen: set[str],
                           entities: set[str]) -> list[str]:
        if not isinstance(given, str):
            return []
        if given.startswith(ENTITY_MARK):
            entity = given[1:]
            if entity not in entities:
                return [(f"il passo «{step_name}» nomina l'entita' "
                         f"«{entity}», che non e' fra quelle consegnate")]
        elif given.startswith(STEP_MARK):
            referenced = given[1:]
            if referenced not in seen:
                return [(f"il passo «{step_name}» legge «{referenced}», che "
                         "non e' un passo gia' calcolato: un passo puo' "
                         "leggere solo quelli PRIMA di lui")]
        return []

    # -- l'esecuzione ------------------------------------------------------

    def run(self, *, series: dict[str, list]) -> dict[str, Result]:
        """Esegue i passi in ordine e torna `{nome del passo: risultato}`.

        **Valida prima**, e se la ricetta non e' valida non esegue niente: una
        ricetta che scrivesse tre passi e poi scoprisse il quarto rotto
        avrebbe gia' consumato tre conti e lasciato un risultato parziale che
        somiglia a uno completo.

        **Un «non lo so» non ferma la ricetta**: e' un risultato come un
        altro, e i passi che lo leggono lo ereditano -- e' il registro a
        propagarlo, con la sua ragione (vedi `operations.Result`).
        """
        outcome = self.validate(entities=set(series))
        if not outcome.valid:
            raise ValueError(
                "ricetta non valida, non eseguita: " + " · ".join(outcome.problems))

        results: dict[str, Result] = {}
        for step in self._steps:
            name = str(step["name"]).strip()
            operation = REGISTRY[str(step["operation"]).strip()]
            given_values = [self._resolve(i, series, results)
                        for i in step.get("inputs") or []]
            params_of_step = dict(step.get("params") or {})
            results[name] = operation.run(*given_values, **params_of_step)
        return results

    @staticmethod
    def _resolve(given, series: dict, results: dict):
        if isinstance(given, str):
            if given.startswith(ENTITY_MARK):
                return series.get(given[1:]) or []
            if given.startswith(STEP_MARK):
                return results[given[1:]]
        return given
