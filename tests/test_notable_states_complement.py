"""Le sei liste sparse: dove sono finite, e la misura che ne ha fermata una.

**Due prove, e sono due domande diverse.**

La prima chiude la famiglia: nessuna delle liste traslocate esiste piu' come
insieme letterale a livello di modulo dove stava, e la prova lo verifica
leggendo i sorgenti -- cosi' la settima non nasce per distrazione, e chi ne
riporta una indietro trova un rosso invece di un commento di buone intenzioni.

La seconda e' il perche' della **sesta**. `briefing._ACTIVE_STATES` doveva
sciogliersi derivandola dai riposi che il vocabolario dei tipi gia' dichiara:
`unlocked` e' il complemento di `locked`, `open` di `closed`, `on` di `off` --
la stessa conoscenza, detta due volte dai due lati opposti. **Il complemento
non e' esatto**, e questa prova e' la misura: sui tipi che meritano un
annuncio, ci sono stati che questa casa PUBBLICA, che non sono riposi, e che
`_ACTIVE_STATES` non conta. Derivare li conterebbe tutti, e cambierebbe i
conteggi del nucleo -- una correzione, forse giusta, che va fatta in una fetta
sua col suo changelog.

Il verso opposto invece torna, ed e' l'altra meta' della misura: nessuna delle
cinque parole e' un riposo per nessun tipo che la puo' portare. Le due
direzioni si provano separate, perche' sono due fatti diversi e uno solo dei
due e' un problema.

Spec: `docs/design/2026-09-07-l-anagrafe-dei-tipi.md` §16.
"""
import ast
import json
from pathlib import Path

from hiris.app.home_space import briefing
from hiris.app.home_space.type_vocabulary import (
    notable_types,
    resting_states_of,
    unknown_states,
    working_states_of,
)

_PRODOTTO = Path(__file__).resolve().parents[1] / "hiris" / "app"
_PUBBLICATO = Path(__file__).resolve().parent / "data" / "pubblicato-dalla-casa.json"


# --- la famiglia chiusa ----------------------------------------------------

#: Nome dell'insieme -> (modulo dov'era, dove vive adesso). **Un insieme
#: letterale con uno di questi nomi, a livello di modulo, non deve esistere
#: piu'.** L'elenco non e' documentazione: e' cio' che la prova cerca.
_TRASLOCATE = {
    "_EVENT_DOMAINS": (
        "home_space/briefing.py",
        "il campo `notable` sulle righe di dominio di `type_vocabulary`"),
    "_EVENT_CLASSES": (
        "home_space/briefing.py",
        ("lo STESSO campo `notable`, sulle righe delle coppie "
         "(binary_sensor, classe)")),
    "_BROKEN_INTEGRATION_STATES": (
        "home_space/briefing.py",
        ("`ha_vocabulary.CONFIG_ENTRY_FAILURE_STATES`, con "
         "`config_entry_is_broken` che la legge")),
    "_HEALTHY_INTEGRATION_STATES": (
        "mind/watcher.py",
        ("la stessa enumerazione, letta da `config_entry_is_healthy`: era il "
         "gemello divergente del precedente")),
    "STATE_CLASSES_WITH_STATISTICS": (
        "home_space/historian.py",
        "`ha_vocabulary`, che per `state_class` aveva gia' una casa"),
}

#: L'unica delle sei rimasta dov'era, col suo motivo. **Sta qui perche' la
#: prova la pretenda**: se un giorno traslocasse e nessuno togliesse questa
#: riga, resterebbe una deroga che non copre piu' niente -- la stessa forma di
#: difetto che `test_un_tipo_ha_una_casa_sola` chiude dall'altro lato.
_RIMASTE = {
    "_ACTIVE_STATES": (
        "home_space/briefing.py",
        "il complemento dei riposi non e' esatto: vedi la misura qui sotto"),
}


def _insiemi_letterali(percorso: Path) -> set[str]:
    """I nomi assegnati a livello di modulo a un insieme, una tupla, una lista
    o un dizionario di sole stringhe.

    A livello di MODULO e non ovunque: un insieme costruito dentro una
    funzione nasce e muore li', e non e' una seconda casa per un fatto.
    """
    albero = ast.parse(percorso.read_text(encoding="utf-8"))
    nomi = set()
    for nodo in albero.body:
        if not isinstance(nodo, (ast.Assign, ast.AnnAssign)):
            continue
        valore = nodo.value
        if isinstance(valore, ast.Call) and isinstance(valore.func, ast.Name):
            if valore.func.id not in ("frozenset", "set", "tuple", "list", "dict"):
                continue
            valore = valore.args[0] if valore.args else None
        if not isinstance(valore, (ast.Set, ast.Tuple, ast.List, ast.Dict)):
            continue
        bersagli = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
        for bersaglio in bersagli:
            if isinstance(bersaglio, ast.Name):
                nomi.add(bersaglio.id)
    return nomi


def test_le_liste_traslocate_non_esistono_piu_dove_stavano():
    """Mutazione ESEGUITA: rimettere `_EVENT_DOMAINS = {"light", "switch"}` a
    livello di modulo in `briefing.py` -- questa prova lo nomina, col posto in
    cui quel fatto vive adesso.

    E' la prova che chiude la famiglia: senza, la settima lista nasce per
    distrazione, e nessuno se ne accorge finche' non diverge.
    """
    rinate = []
    for nome, (modulo, casa) in sorted(_TRASLOCATE.items()):
        if nome in _insiemi_letterali(_PRODOTTO / modulo):
            rinate.append(f"{modulo}::{nome} (quel fatto vive in {casa})")
    assert not rinate, (
        "insiemi letterali tornati dove non devono stare: "
        + "; ".join(rinate))


def test_l_unica_rimasta_e_dichiarata_e_c_e_ancora():
    """Il rovescio, e serve quanto la prova sopra: una deroga che non copre
    piu' niente e' una riga che difende una scelta che nessuno fa piu'.

    Mutazione: sciogliere `_ACTIVE_STATES` senza togliere la riga da
    `_RIMASTE` -- questa prova diventa rossa e obbliga ad aggiornare l'elenco.
    """
    for nome, (modulo, _motivo) in sorted(_RIMASTE.items()):
        assert nome in _insiemi_letterali(_PRODOTTO / modulo), (
            f"{modulo}::{nome} non esiste piu': se e' traslocata, togli la "
            "riga da `_RIMASTE` invece di lasciare una deroga vuota")


def test_ogni_motivo_e_scritto():
    """Un'eccezione senza motivo non passa -- la stessa regola del censore.
    «si'» o «ovvio» passerebbero un controllo di non-vuoto e non direbbero
    niente a chi legge fra sei mesi."""
    muti = [nome for nome, (_m, motivo) in _RIMASTE.items()
            if not motivo or len(motivo.strip()) < 15]
    assert not muti, f"deroghe senza un motivo scritto: {muti}"


# --- la misura che ha fermato la sesta -------------------------------------

def _stati_pubblicati(dominio: str) -> set[str]:
    """Gli stati che QUESTA casa pubblica per questo dominio, classe per
    classe. L'istantaneo e' versionato apposta: la suite gira senza la casa."""
    pubblicato = json.loads(_PUBBLICATO.read_text(encoding="utf-8"))
    stati = set()
    for elenco in (pubblicato["stati_per_tipo"].get(dominio) or {}).values():
        stati |= set(elenco)
    return stati


#: Il divario misurato l'08/09/2026 sull'istantaneo di questa casa: `tipo=stato`
#: che il vocabolario NON dichiara riposo e che `_ACTIVE_STATES` non conta.
#: **Sono gli undici che una derivazione dai riposi conterebbe in piu'**, cioe'
#: il cambio di comportamento che questa fetta non ha fatto.
_DIVARIO_MISURATO = {
    "cover=closing", "cover=opening",
    "lock=jammed", "lock=locking", "lock=opening", "lock=unlocking",
    "media_player=buffering", "media_player=paused",
    "vacuum=paused",
    "valve=closing", "valve=opening",
}


def test_il_complemento_dei_riposi_non_coincide_con_gli_stati_attivi():
    """**La misura che ha fermato la sesta lista**, e va letta prima di
    riprovarci.

    Per ogni dominio che merita un annuncio, si prendono gli stati che questa
    casa pubblica, si tolgono i riposi dichiarati e i due «non lo so»: cio' che
    resta e' il complemento. Se il complemento fosse `_ACTIVE_STATES`, la lista
    si scioglierebbe senza cambiare un solo conteggio. Non lo e'.

    Mutazione ESEGUITA: aggiungere `"paused"` a `_ACTIVE_STATES` -- il divario
    cala di due voci (`media_player=paused`, `vacuum=paused`) e questa prova le
    nomina.
    """
    divario = set()
    for dominio, classe in notable_types():
        if classe is not None:
            continue
        riposi = resting_states_of(dominio) | unknown_states()
        for stato in _stati_pubblicati(dominio) - riposi:
            if stato not in briefing._ACTIVE_STATES:
                divario.add(f"{dominio}={stato}")
    assert divario == _DIVARIO_MISURATO, (
        "il divario fra «non a riposo» e «attivo» e' cambiato -- in piu': "
        f"{sorted(divario - _DIVARIO_MISURATO)}, mancanti: "
        f"{sorted(_DIVARIO_MISURATO - divario)}. Se e' sparito del tutto, il "
        "complemento adesso e' esatto e `_ACTIVE_STATES` si puo' sciogliere.")


def test_nessuno_stato_attivo_e_il_riposo_di_un_tipo_che_lo_porta():
    """L'altra meta' della misura, ed e' quella che TORNA.

    Se una delle cinque parole fosse il riposo di un tipo, derivare dai riposi
    farebbe SPARIRE un conteggio invece di aggiungerne: sarebbe il difetto
    grave, non quello lieve. Non succede per nessuno dei dieci domini.

    Mutazione ESEGUITA: aggiungere `"on"` ai riposi di `switch` (che non ha
    stati di funzionamento dichiarati, quindi il guardiano all'importazione
    tace) -- questa prova nomina `switch=on`.
    """
    contraddizioni = sorted(
        f"{dominio}={stato}"
        for dominio, classe in notable_types() if classe is None
        for stato in briefing._ACTIVE_STATES
        if stato in resting_states_of(dominio))
    assert not contraddizioni, (
        "stati che il nucleo conta come attivi e il vocabolario dichiara "
        f"riposo: {contraddizioni}")


def test_il_divario_e_fatto_di_stati_che_il_vocabolario_ha_gia_guardato():
    """Il divario non e' un buco di conoscenza: e' un DISACCORDO.

    Dieci degli undici stati sono dichiarati «sta funzionando» dal vocabolario,
    con la loro ragione scritta -- cioe' qualcuno li ha guardati e ha detto che
    la' succede qualcosa, mentre il nucleo non li annuncia. L'undicesimo,
    `lock=jammed`, non e' ne' l'uno ne' l'altro: e' un GUASTO, deciso dal
    proprietario, e resta aperto in `type_census.OPEN_QUESTIONS`.

    E' la differenza che rende la fetta necessaria e non facoltativa: non
    manca una parola, si contraddicono due giudizi.
    """
    dichiarati, orfani = [], []
    for voce in sorted(_DIVARIO_MISURATO):
        dominio, _, stato = voce.partition("=")
        (dichiarati if stato in working_states_of(dominio) else orfani).append(voce)
    assert orfani == ["lock=jammed"], orfani
    assert len(dichiarati) == 10, dichiarati
