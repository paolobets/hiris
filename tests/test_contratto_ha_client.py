"""La rete sui doppi di `HAClient`, derivata invece che elencata.

**Perche' esiste.** `tests/_contratti.py` e' la guardia contro «la finta e il
chiamante rinominati insieme nel modo sbagliato»: esiste da tre giorni, e
copriva **sei** doppi di `HAClient` -- `leggi_registri`, `diario`, `storico`,
`statistiche`. Il lotto 16 della rinomina, il commit piu' rischioso della
fetta, ha riscritto **20 firme finte** senza che nessuna di quelle venti
passasse per la guardia: `call_service` (cinque finte, otto firme riscritte a
mano), `salva_configurazione`, `_ws_request`, `statistiche_orarie`, `legami`,
`crea_helper`, `cancella_helper`, `leggi_configurazione`,
`cancella_configurazione`, `aggiungi_etichetta_a`, `_ws_batch`. Erano tutte
allineate -- verificate una per una dal revisore -- **ma lo erano perche'
qualcuno e' stato attento, non perche' una rete lo garantisse.**

**Perche' non e' un elenco di dodici righe.** Dodici `assert_stessa_firma`
scritte a mano avrebbero chiuso i dodici casi noti e riaperto il buco alla
tredicesima finta: e' la stessa malattia che il progetto ha gia' diagnosticato
tre volte (i percorsi di import in `scripts/rinomina.py`, i sottosistemi in
`tests/test_preposizioni_italiane.py`, le giunture italiane in quello stesso
file, incomplete per tre volte di fila). Qui l'elenco si DERIVA: `doppi`
legge le classi di ogni modulo di test e trova i doppi da se'.

**Cosa NON copre, dichiarato.** Le finte definite DENTRO il corpo di una
funzione di test (`test_azione_porta.py` ne ha quattro, tutte
`ClientCheRompe`, tutte sottoclassi di `FintoClient` che ne riscrivono
`call_service`): non sono attributi del modulo, e nessuna enumerazione statica
le vede. Il rischio residuo e' piccolo perche' la loro classe base e' coperta
qui, ma e' un rischio, non un'assenza.
"""
import importlib
import sys
from pathlib import Path

from hiris.app.proxy.ha_client import HAClient
from tests._contratti import doppi

ROOT = Path(__file__).resolve().parents[1]


def _moduli():
    """Ogni modulo `tests/test_*.py`, letto dal disco e non da un elenco.

    Sotto la suite intera sono gia' tutti importati e questo e' una lettura di
    `sys.modules`; lanciando il solo file, li importa davvero (~15s misurati).
    Un import che fallisse NON si salta in silenzio: si raccoglie e si
    dichiara, perche' un modulo saltato e' un modulo non coperto.
    """
    moduli, falliti = [], []
    for f in sorted(ROOT.joinpath("tests").glob("test_*.py")):
        nome = "tests." + f.stem
        if nome == __name__:
            continue
        try:
            moduli.append(sys.modules.get(nome) or importlib.import_module(nome))
        except Exception as exc:
            falliti.append((f.stem, repr(exc)))
    assert not falliti, f"moduli di test non importabili, quindi non coperti: {falliti}"
    return moduli


def test_ogni_doppio_di_haclient_porta_la_firma_vera():
    """Il conto NON e' scritto qui: si deriva e si stampa.

    Un numero trascritto in un docstring mente appena il codice si muove -- e'
    successo tre volte in tre giorni su altrettante tarature. Qui l'unica
    asserzione sul numero e' che non sia zero: un'enumerazione che smettesse di
    trovare doppi passerebbe verde dicendo di aver controllato tutto.

    Provato per mutazione: rinominato `domain -> dominio` nella firma di
    `FintoClientPorta.call_service` (`tests/test_azione_bersagli.py`), questo
    test va rosso nominando la coppia esatta; ripristinato, torna verde.
    """
    coppie = doppi(HAClient, _moduli())
    print(f"\n{len(coppie)} doppi di HAClient verificati, in "
          f"{len({c for c, _ in coppie})} classi finte")
    assert coppie, ("nessun doppio di HAClient trovato: o le finte sono "
                    "sparite, o l'enumerazione ha smesso di vederle -- e il "
                    "secondo caso e' un cancello che passa senza guardare")


def test_il_doppio_piu_riscritto_e_dentro_l_enumerazione():
    """La sentinella, e non e' un doppione del test sopra.

    `call_service` e' il metodo su cui il lotto 16 ha riscritto piu' firme a
    mano (otto, in cinque finte). Se un domani `doppi` smettesse di vederlo
    -- un criterio cambiato, un modulo rinominato -- il test sopra resterebbe
    verde: `coppie` non sarebbe vuota, sarebbe solo piu' corta, ed e'
    esattamente il modo in cui un cancello si spegne senza dirlo.
    """
    coppie = doppi(HAClient, _moduli())
    assert any(metodo == "call_service" for _, metodo in coppie), (
        "l'enumerazione non trova piu' nessuna finta di `call_service`: "
        "controlla il criterio di `doppi` prima di credere che le finte "
        "siano sparite")
