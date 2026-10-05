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

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field as _field

from ..home_space.ha_vocabulary import domain_of
from .operations import (
    REGISTRY,
    SHAPE_RESULT,
    SHAPE_SERIES,
    NotComputable,
    Result,
)

#: Il carattere che dice «questa e' un'entita' della casa».
ENTITY_MARK = "@"
#: Il carattere che dice «questo e' il risultato di un passo precedente».
STEP_MARK = "$"


# -- perche' un'entita' non da' una serie (B-26 meta'; Tappa 3, Task 8) -------
#
# Fino al 04/10/2026 il motivo era UNO per tutte le entita' fuori
# dall'elenco delle statistiche: «le tiene solo per le entita' che dichiarano
# uno `state_class`». Sui congelati del 03/10 era falso per 504 entita' su
# 1.284 chieste (sonda, domanda `fonte`): disabilitate, sparite, o che lo
# `state_class` lo dichiaravano. Ora la causa viene dalla fonte
# (`House.source`), e il testo la dice.

#: Il dominio per cui Home Assistant compila statistiche (vedi il commento
#: «quali `state_class` producono statistiche» in `ha_vocabulary.py`, letto
#: nel sorgente al tag 2026.9.1).
_STATISTICS_DOMAIN = "sensor"


def silence_reason(entity_id: str, source: dict | None,
                   state_class: str | None = None) -> str:
    """Perche' un'entita' che Home Assistant non elenca fra le statistiche
    non dara' una serie: la causa della FONTE prima, e solo per una fonte
    che parla la regola di Home Assistant sullo `state_class`."""
    never = "nessuna serie, non oggi e non un altro giorno finche' resta cosi'"
    state = (source or {}).get("stato")
    cause = (source or {}).get("causa")
    if source is None:
        return (f"{entity_id} non c'e' in Home Assistant, ne' nel registro ne' "
                f"negli stati: {never}")
    if state == "spenta_dal_proprietario":
        return (f"{entity_id} e' disabilitata in Home Assistant, spenta dal "
                f"proprietario (disabled_by: {cause}): non registra niente, {never}")
    if state == "spenta_da_home_assistant":
        return (f"{entity_id} e' disabilitata da Home Assistant o "
                f"dall'integrazione (disabled_by: {cause}): non registra niente, {never}")
    if state == "integrazione_ferma":
        return (f"l'integrazione di {entity_id} non e' caricata (stato "
                f"dell'istanza: {cause}): {never}")
    if state == "sparita":
        return (f"{entity_id} e' nel registro di Home Assistant ma non ha uno "
                f"stato: {never}")
    if domain_of(entity_id) != _STATISTICS_DOMAIN:
        return (f"{entity_id} non ha statistiche in Home Assistant: le compila "
                f"solo per i `{_STATISTICS_DOMAIN}`, e questa e' "
                f"«{domain_of(entity_id)}» -- {never}")
    if not state_class:
        return (f"{entity_id} non ha statistiche in Home Assistant: non dichiara "
                f"uno `state_class`, e Home Assistant le compila solo per i sensor "
                f"che lo dichiarano -- {never}")
    return (f"{entity_id} non ha statistiche in Home Assistant: dichiara uno "
            f"`state_class` ({state_class}), ma Home Assistant non la elenca fra "
            f"quelle che tiene -- {never}")


def silent_entities(house, entity_ids) -> dict[str, str] | None:
    """Le entita' fra `entity_ids` per cui Home Assistant non tiene
    statistiche, ognuna con la sua causa (`silence_reason`). `None` --
    non `{}` -- se la casa non ha l'elenco del giro: chi non ha potuto
    chiedere non afferma che non ne hanno."""
    if house.statistic_ids is None:
        return None
    return {entity_id: silence_reason(entity_id, house.source(entity_id),
                                      house.mirror.state_classes.get(entity_id))
            for entity_id in entity_ids if entity_id not in house.statistic_ids}


def unread_series_reason(error: str) -> str:
    """Il motivo di una misura quando le statistiche orarie non si sono
    potute leggere (trovato 7 del piano della Tappa 3, S-28): fino al
    04/10/2026 quel guasto usciva come «la serie e' vuota», cioe' come un
    giorno in cui non e' arrivato niente."""
    return (f"le statistiche di Home Assistant non si sono potute leggere per "
            f"questo giorno ({error}): non so se la serie ci sarebbe stata")


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


def _shape_of(given) -> str:
    """La forma di cio' che un ingresso consegna.

    Dentro una ricetta esistono **due sole sorgenti**: `@entita` da' la serie
    del periodo, `$passo` da' la misura di un passo precedente. Un letterale
    non e' ne' l'una ne' l'altra, e nessuna operazione del registro ne prende
    uno: dirlo con un nome suo fa uscire un rifiuto leggibile invece di un
    confronto che non torna mai.
    """
    if isinstance(given, str):
        if given.startswith(ENTITY_MARK):
            return SHAPE_SERIES
        if given.startswith(STEP_MARK):
            return SHAPE_RESULT
    return "un valore scritto a mano"


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
        invece di una per passo: `server._report_ingredients` raccoglie le
        entita' di tutte le ricette e chiede le statistiche orarie una volta.
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
        listed = list(inputs) if isinstance(inputs, (list, tuple)) else []
        given_count = len(listed)
        if not (least <= given_count <= most):
            wanted = (f"{least}" if least == most else f"da {least} a {most}")
            found.append(
                f"il passo «{step_name}» consegna {given_count} ingressi a "
                f"«{operation}», che ne vuole {wanted}")
            return found
        # 5. **di che FORMA sono?** L'ultimo anello, e il piu' silenzioso:
        #    `tempo_in_stato` vuole un periodo, una ricetta gli consegnava la
        #    serie di un'entita', e il motore moriva un passo dopo con
        #    `AttributeError: 'list' object has no attribute 'windows'`.
        #    Misurato sulla casa vera il 14/09/2026, dopo che la 3.34.0 aveva
        #    gia' chiuso nomi, parametri e numero di ingressi.
        for given, wanted_shape in zip(listed, entry.takes):
            actual = _shape_of(given)
            if actual != wanted_shape:
                found.append(
                    f"il passo «{step_name}» consegna {actual} dove "
                    f"«{operation}» vuole {wanted_shape}")
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

    def run(self, *, series: dict[str, list],
            silent: Mapping[str, str] | None = None) -> dict[str, Result]:
        """Esegue i passi in ordine e torna `{nome del passo: risultato}`.

        **Valida prima**, e se la ricetta non e' valida non esegue niente: una
        ricetta che scrivesse tre passi e poi scoprisse il quarto rotto
        avrebbe gia' consumato tre conti e lasciato un risultato parziale che
        somiglia a uno completo.

        **Un «non lo so» non ferma la ricetta**: e' un risultato come un
        altro, e i passi che lo leggono lo ereditano -- e' il registro a
        propagarlo, con la sua ragione (vedi `operations.Result`).

        **`silent` porta il primo dei due «rifiuta se» della spec §6**: le
        entita' che non daranno una serie, ognuna col suo PERCHE' --
        `silent_entities` (Home Assistant non tiene statistiche, con la causa
        della fonte) o `unread_series_reason` (le statistiche non si sono
        potute leggere).
        Il registro lo dichiara (`Operation.refuses_when`) e qui si produce,
        perche' e' qui che il fatto arriva: un'operazione riceve una lista di
        punti e non puo' distinguere *«quel giorno non e' arrivato niente»* da
        *«questa entita' non produrra' mai niente»*. Sono due cose, e dirle
        con una parola sola manda a cercare un buco nei dati che non c'e' --
        e soprattutto **non lo dice al modello**, a cui il rifiuto torna.

        Misurato sulla casa vera il 15/09/2026 (`recorder/list_statistic_ids`):
        **130 entita' su 1206 hanno statistiche, tutte `sensor`**. Nel
        resoconto del 14, **18 rifiuti su 28** erano di questa specie e
        dicevano «la serie e' vuota».

        `None` -- e non l'insieme vuoto -- vuol dire **«non lo so»**: chi non
        ha potuto chiedere a Home Assistant quali entita' abbiano statistiche
        non deve affermare che non ne hanno. Stessa regola con cui
        `ha_client._request_statistics` torna `{"errore"}` e mai `{}`.
        """
        outcome = self.validate(entities=set(series))
        if not outcome.valid:
            raise ValueError(
                "ricetta non valida, non eseguita: " + " · ".join(outcome.problems))

        mute = dict(silent or {})
        results: dict[str, Result] = {}
        for step in self._steps:
            name = str(step["name"]).strip()
            operation = REGISTRY[str(step["operation"]).strip()]
            mute_here = [str(i)[1:] for i in step.get("inputs") or []
                     if isinstance(i, str) and i.startswith(ENTITY_MARK)
                     and str(i)[1:] in mute]
            if mute_here:
                # Il rifiuto e' del PASSO, non della ricetta: gli altri passi
                # valgono, e mezzo resoconto e' meglio di nessuno.
                results[name] = NotComputable(
                    " · ".join(mute[entity] for entity in mute_here))
                continue
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
