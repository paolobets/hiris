"""Il registro di cio' che HIRIS sa calcolare (spec 2026-09-10 §6, Fetta 3).

**Chiuso e versionato**: ogni operazione dichiara ingressi, uscita, unita' e
copertura, e **non si puo' costruire senza**. Il precedente della disciplina e'
`home_space/type_vocabulary.Field`, che non si puo' costruire senza provenienza
-- e il meccanismo non e' un controllo a valle, e' la struttura.

**Le due forme di un risultato sono due CLASSI**, non un campo che puo' restare
vuoto: o e' una `Measurement` -- e allora porta il numero, la sua unita' e la sua
copertura -- oppure e' un `NotComputable`, e allora porta il PERCHE'. Un
numero senza unita' e una assenza senza ragione non esistono perche' non c'e'
nessun costruttore che li produca.

Il precedente e' gia' stato pagato in questo progetto: `_difference` con un
punto solo restituiva `0.0`, cioe' «non e' cambiato niente» travestito da dato
(`mind/facts.py`, corretto il 26/08/2026).
"""
import contextlib
import dataclasses
from zoneinfo import ZoneInfo

import pytest

from hiris.app.mind import operations as ops

#: Il fuso della casa, gia' risolto -- come lo riceve il registro, che non sa
#: dove sta la casa e non deve impararlo.
ROMA = ZoneInfo("Europe/Rome")


def _kwh(valore: float) -> "ops.Measurement":
    """Una misura in kWh a copertura piena -- quello che `quota` si aspetta da
    quando prende risultati invece di numeri nudi."""
    return ops.Measurement(valore, unit="kWh", coverage=1.0)

# -- il risultato: due forme, e nessuna scorciatoia ------------------------

def test_un_risultato_astratto_non_si_puo_costruire():
    """`Result` e' la forma, non una cosa che si possa avere in mano:
    averla concreta vorrebbe dire poter restituire «un risultato» senza dire
    se sia un numero o un rifiuto.

    Mutazione che la uccide: togliere l'astrattezza (il metodo astratto).
    """
    with pytest.raises(TypeError):
        ops.Result()


def test_una_misura_senza_unita_non_si_puo_costruire():
    """**Prima fondamenta**: un valore senza la sua unita' non e' un oggetto,
    e' un frammento -- HIRIS leggeva `72` e non sapeva se fossero gradi
    Celsius o Fahrenheit.

    Mutazione che la uccide: dare a `unit` un default.
    """
    with pytest.raises(TypeError):
        ops.Measurement(23.71, coverage=1.0)


def test_una_misura_senza_copertura_non_si_puo_costruire():
    """La copertura e' cio' che rende il set onesto (spec §6): dice quanta
    parte del periodo aveva dati. Un numero che non la porta e' un numero di
    cui chi legge non puo' giudicare il peso.

    Mutazione che la uccide: dare a `coverage` un default.
    """
    with pytest.raises(TypeError):
        ops.Measurement(23.71, unit="kWh")


def test_una_copertura_fuori_da_zero_uno_e_un_errore_subito():
    """Non e' pedanteria: una copertura di 1,3 o di -0,2 e' un conto sbagliato
    a monte, e lasciarla passare la farebbe finire in una pagina come se
    qualcuno l'avesse verificata."""
    with pytest.raises(ValueError):
        ops.Measurement(1.0, unit="kWh", coverage=1.3)
    with pytest.raises(ValueError):
        ops.Measurement(1.0, unit="kWh", coverage=-0.1)


def test_una_misura_porta_valore_unita_e_copertura():
    m = ops.Measurement(23.71, unit="kWh", coverage=1.0)

    assert m.computable is True
    assert (m.value, m.unit, m.coverage) == (23.71, "kWh", 1.0)


def test_un_non_calcolabile_senza_ragione_non_si_puo_costruire():
    """**«Non calcolabile» senza il perche' e' un silenzio, non una
    risposta.** La spec lo chiede alla lettera: «il risultato diventa "non
    calcolabile, E PERCHE'"».

    Mutazione che la uccide: rendere `reason` facoltativo.
    """
    with pytest.raises(TypeError):
        ops.NotComputable()


def test_un_non_calcolabile_con_una_ragione_vuota_e_un_errore():
    """Una stringa vuota passerebbe il controllo della firma e non direbbe
    niente: sarebbe il silenzio di prima, con una forma piu' rispettabile."""
    with pytest.raises(ValueError):
        ops.NotComputable("   ")


def test_un_non_calcolabile_dice_perche_e_non_ha_valore():
    n = ops.NotComputable("il periodo e' fuori dalla memoria disponibile")

    assert n.computable is False
    assert "memoria" in n.reason
    assert not hasattr(n, "valore")


# -- il periodo: un ELENCO di finestre, non un intervallo solo --------------
#
# Tre delle sette domande del proprietario (docs/design/
# 2026-09-11-le-domande-del-proprietario.md) chiedono la stessa cosa:
# restringere un calcolo ai periodi in cui qualcosa era vero -- «mentre il
# riscaldamento scaldava», «quando c'era qualcuno in casa». Sembrava
# un'operazione in piu'; non lo e', se il PERIODO e' un elenco di finestre:
# allora `episodio` produce finestre, e ogni altra operazione le accetta. La
# restrizione diventa composizione, e il registro resta a quindici mattoni.


def test_un_periodo_e_fatto_di_finestre_e_ne_conosce_la_durata():
    p = ops.Period([(0.0, 3600.0), (7200.0, 9000.0)])

    assert p.duration_s == 3600.0 + 1800.0


def test_un_periodo_senza_finestre_non_si_puo_costruire():
    """Un periodo vuoto non e' «tutto il tempo» ne' «nessun tempo»: e' una
    domanda mal posta, e lasciarla passare produrrebbe una copertura 0/0."""
    with pytest.raises(ValueError):
        ops.Period([])


def test_una_finestra_che_finisce_prima_di_cominciare_e_un_errore():
    with pytest.raises(ValueError):
        ops.Period([(3600.0, 0.0)])


def test_le_finestre_si_ORDINANO_e_si_FONDONO_quando_si_toccano():
    """Due episodi contigui dello stesso soggetto sono un periodo solo: se
    restassero separati, la durata sarebbe giusta ma la copertura di un
    conteggio a cavallo verrebbe contata due volte.

    Mutazione che la uccide: conservare le finestre come sono state date.
    """
    p = ops.Period([(7200.0, 9000.0), (0.0, 3600.0), (3600.0, 5400.0)])

    assert p.windows == ((0.0, 5400.0), (7200.0, 9000.0))


def test_un_periodo_dice_se_un_istante_gli_appartiene():
    p = ops.Period([(0.0, 3600.0), (7200.0, 9000.0)])

    assert p.contains(1800.0) is True
    assert p.contains(5000.0) is False
    # Il confine destro e' ESCLUSO: due finestre adiacenti non devono
    # contenere entrambe lo stesso istante, o un evento verrebbe contato due
    # volte.
    assert p.contains(3600.0) is False


# -- il registro: chiuso, versionato, e ogni voce dichiara tutto ------------


def test_ogni_operazione_dichiara_ingressi_uscita_e_quando_rifiuta():
    """Spec §6: *«Ogni operazione dichiara, e non si puo' costruire senza»*.
    Una voce muta sarebbe un nome in un elenco, e una ricetta (Fetta 4) non
    potrebbe essere RIFIUTATA prima di eseguirla -- che e' l'unica cosa che
    rende le ricette un dato invece che codice.

    **La prima riga non e' cerimonia**: senza, il ciclo su un registro vuoto
    non gira e la prova passa a vuoto -- il difetto n.1 di questo progetto,
    che qui sarebbe nato insieme al registro."""
    assert ops.REGISTRY, "un registro vuoto farebbe passare questa prova a vuoto"
    for name, operation in ops.REGISTRY.items():
        assert operation.name == name
        assert operation.inputs, f"{name} non dichiara i suoi ingressi"
        assert operation.returns, f"{name} non dichiara cosa restituisce"
        assert operation.refuses_when, f"{name} non dichiara quando rifiuta"
        assert callable(operation.run), f"{name} non e' eseguibile"


def test_un_operazione_senza_dichiarazione_non_si_puo_costruire():
    """Mutazione che la uccide: dare un default a uno dei campi."""
    with pytest.raises(TypeError):
        ops.Operation(name="somma_periodo")


def test_il_registro_e_CHIUSO_non_ci_si_puo_aggiungere_niente():
    """**«Chiuso» deve essere una proprieta', non una buona intenzione.** Una
    ricetta puo' nominare solo cio' che sta nel registro; se un modulo
    qualunque potesse aggiungerci una voce a caldo, la validazione delle
    ricette direbbe di si' a qualcosa che nessuno ha rivisto.

    Mutazione che la uccide: esporre il dizionario invece della sua vista di
    sola lettura.
    """
    with pytest.raises(TypeError):
        ops.REGISTRY["inventata"] = None


def test_il_registro_e_VERSIONATO():
    """Le ricette vivranno piu' a lungo del registro che le esegue: senza un
    numero, una ricetta scritta oggi e letta fra sei mesi non saprebbe dire
    se le operazioni che nomina siano ancora quelle."""
    assert isinstance(ops.REGISTRY_VERSION, int)
    assert ops.REGISTRY_VERSION >= 1


# -- somma_periodo: i sette totali dell'energia ------------------------------
#
# ESTRATTA da `mind/facts.build_balance_body`, dove il totale di una dimensione
# era «la somma delle ore CONOSCIUTE». Li' la copertura non usciva: un totale
# fatto di tre ore su ventiquattro aveva la stessa faccia di uno completo.


def _ore(values, start=0.0):
    """Punti orari nella forma che `HAClient.hourly_statistics` gia' produce:
    `value` a `None` e' un'ora SENZA dato, non un'ora a zero."""
    return [{"inizio": start + n * 3600.0, "fine": start + (n + 1) * 3600.0,
             "valore": v} for n, v in enumerate(values)]


def test_somma_periodo_somma_le_ore_conosciute_e_dichiara_la_copertura():
    r = ops.REGISTRY["somma_periodo"].run(_ore([1.0, 2.0, 3.0, 4.0]), unit="kWh")

    assert r.computable
    assert r.value == 10.0
    assert r.unit == "kWh"
    assert r.coverage == 1.0


def test_un_ora_senza_dato_non_vale_zero_e_abbassa_la_copertura():
    """**Mai uno zero al posto di un dato che non c'e'.** Un'ora senza dato
    toglie una parte del periodo, non aggiunge un valore nullo -- e chi legge
    il totale deve poterlo sapere dalla copertura.

    Mutazione che la uccide: trattare `None` come `0.0`.
    """
    r = ops.REGISTRY["somma_periodo"].run(_ore([1.0, None, 3.0, 4.0]), unit="kWh")

    assert r.value == 8.0
    assert r.coverage == 0.75


def test_sotto_la_soglia_un_totale_NON_si_restituisce_e_si_dice_perche():
    """Il precedente e' pagato: `_difference` con un punto solo restituiva
    `0.0`, «non e' cambiato niente» travestito da dato. Qui un totale del
    giorno fatto di due ore su ventiquattro sarebbe lo stesso difetto con una
    faccia piu' rispettabile.

    Mutazione che la uccide: restituire la misura comunque, con la copertura
    bassa accanto.
    """
    r = ops.REGISTRY["somma_periodo"].run(
        _ore([1.0] * 2 + [None] * 22), unit="kWh")

    assert not r.computable
    assert "copertura" in r.reason
    assert "8%" in r.reason or "0.08" in r.reason


def test_una_serie_del_tutto_vuota_dice_che_non_c_e_niente():
    """E' il caso vero delle due entita' misurate sulla casa l'11/09/2026 --
    `sensor.gestione_carichi_power` e `sensor.luci_di_natale_energia_totale` --
    che hanno `state_class` e ZERO punti di statistica."""
    r = ops.REGISTRY["somma_periodo"].run(_ore([None] * 24), unit="kWh")

    assert not r.computable
    assert "nessun" in r.reason.lower()


# -- le operazioni sui numeri e sulle serie ---------------------------------
#
# ESTRATTE da `mind/facts.py`: `_share` -> `quota`, il `consumo - prelievo` di
# `_balance_moments` -> `differenza_fra`, la somma delle ore conosciute di
# `build_balance_body` -> `somma_periodo`, `_dimension_points` + `forma` ->
# `per_ora`, `_difference` -> `primo_ultimo_differenza`.
#
# `media_min_max` **non e' estratta**: in `facts.py` non c'era nessuna media.
# (La riga precedente diceva che veniva da `_percent`, che invece e'
# l'arrotondamento della batteria a un decimale ed e' ancora li', al confine.)
# Nasce dalla domanda 4, sul comfort quando qualcuno c'e'.


def test_quota_e_una_frazione_fra_zero_e_uno():
    r = ops.REGISTRY["quota"].run(_kwh(3.15), _kwh(4.97))

    assert r.unit == "frazione"
    assert r.value == 0.634


def test_una_quota_NON_e_piu_sicura_del_suo_termine_piu_debole():
    """**La copertura si propaga, e prende la peggiore delle due.**

    Trovato in revisione il 12/09/2026: `quota` prendeva due numeri nudi, e
    con loro la copertura dei totali a monte si perdeva per strada. Una quota
    calcolata su un totale coperto all'80% usciva dichiarando 100% -- una
    certezza che nessuno aveva, nella pagina del bilancio.

    E' anche la ragione per cui prende `Result` e non `float`: la ricetta
    della spec (§7) -- `quota(differenza_fra(consumata, prelevata),
    consumata)` -- con due numeri nudi non si scrive affatto.

    Mutazione che la uccide: `coverage=1.0`.
    """
    r = ops.REGISTRY["quota"].run(
        ops.Measurement(3.0, unit="kWh", coverage=0.8),
        ops.Measurement(4.0, unit="kWh", coverage=1.0))

    assert r.value == 0.75
    assert r.coverage == 0.8


def test_una_quota_su_un_NON_CALCOLABILE_non_e_un_numero():
    """Il «non lo so» si propaga: un rapporto con un termine che non c'e' non
    e' un rapporto piu' incerto, non esiste.

    Mutazione che la uccide: togliere il giro sui due termini in `_ratio`.
    """
    r = ops.REGISTRY["quota"].run(
        ops.NotComputable("il contatore non ha statistiche"),
        ops.Measurement(4.0, unit="kWh", coverage=1.0))

    assert not r.computable
    assert "statistiche" in r.reason


def test_quota_di_un_denominatore_nullo_NON_e_zero():
    """«Zero produzione» non significa «zero autoconsumo»: significa «non lo
    so». E' la regola gia' presa da `_share`, e qui il «non lo so» ha finalmente
    un posto dove dire anche il perche'.

    Mutazione che la uccide: restituire `Measurement(0.0, ...)`.
    """
    r = ops.REGISTRY["quota"].run(_kwh(3.15), _kwh(0.0))

    assert not r.computable
    assert "denominatore" in r.reason


def test_una_quota_NEGATIVA_non_si_clampa_a_zero_e_si_dichiara():
    """Caso PREVISTO il 27/08/2026 e non ancora osservato su questa casa: il
    prelievo puo' superare il consumo quando la batteria si carica dalla rete.
    Zero affermerebbe «zero autosufficienza», e non lo sappiamo.

    Mutazione che la uccide: `max(0.0, valore)`.
    """
    r = ops.REGISTRY["quota"].run(_kwh(-1.0), _kwh(4.0))

    assert not r.computable
    assert "negativ" in r.reason


def test_differenza_fra_due_misure_tiene_l_unita_e_la_copertura_PEGGIORE():
    """**La copertura di una differenza e' la peggiore delle due**, non la
    media: un numero calcolato su due serie di cui una quasi vuota vale quanto
    la piu' debole.

    Mutazione che la uccide: usare la media, o la copertura del primo.
    """
    a = ops.Measurement(14.66, unit="kWh", coverage=1.0)
    b = ops.Measurement(9.60, unit="kWh", coverage=0.8)

    r = ops.REGISTRY["differenza_fra"].run(a, b)

    assert r.value == 5.06
    assert r.unit == "kWh"
    assert r.coverage == 0.8


def test_non_si_sottraggono_due_misure_di_UNITA_diverse():
    """Sottrarre kWh da gradi produce un numero, e quel numero e' una bugia.
    E' la prima fondamenta applicata all'aritmetica."""
    a = ops.Measurement(14.66, unit="kWh", coverage=1.0)
    b = ops.Measurement(21.0, unit="°C", coverage=1.0)

    r = ops.REGISTRY["differenza_fra"].run(a, b)

    assert not r.computable
    assert "unit" in r.reason


def test_una_differenza_che_parte_da_un_non_calcolabile_resta_non_calcolabile():
    """**Il «non lo so» si propaga.** Se uno dei due addendi non si e' potuto
    calcolare, il risultato non e' un numero piu' incerto: non c'e'.

    Mutazione che la uccide: trattare il `NotComputable` come zero.
    """
    a = ops.NotComputable("la serie e' vuota")
    b = ops.Measurement(9.60, unit="kWh", coverage=1.0)

    r = ops.REGISTRY["differenza_fra"].run(a, b)

    assert not r.computable
    assert "vuota" in r.reason


def test_media_min_max_porta_tutti_e_tre_i_numeri():
    r = ops.REGISTRY["media_min_max"].run(_ore([18.0, 20.0, 22.0, 21.0]),
                                             unit="°C")

    assert r.computable
    assert r.value == {"media": 20.25, "minimo": 18.0, "massimo": 22.0}
    assert r.unit == "°C"


def test_per_ora_tiene_l_ORA_di_ogni_punto_non_la_sua_posizione():
    """Correzione gia' pagata il 27/08/2026: la forma era una lista NUDA di
    valori, e Home Assistant OMETTE le ore senza dati -- quindi l'indice non
    era l'ora, e una giornata che comincia alle 7 aveva il primo valore in
    posizione zero.

    Mutazione che la uccide: restituire solo i valori.
    """
    r = ops.REGISTRY["per_ora"].run(_ore([1.0, None, 3.0, 4.0]), unit="kWh")

    assert [p["ora"] for p in r.value] == [0.0, 3600.0, 7200.0, 10800.0]
    assert [p["valore"] for p in r.value] == [1.0, None, 3.0, 4.0]


def test_primo_ultimo_differenza_con_UN_SOLO_punto_non_dice_zero():
    """**Il difetto fondativo di questa fetta.** Con un solo punto, iniziale e
    finale sono la stessa lettura: il conto tornerebbe `0.0`, cioe' «non e'
    cambiato niente» travestito da dato. Corretto in `None` il 26/08/2026; qui
    dice anche perche'.

    Mutazione che la uccide: togliere la guardia sul numero di punti.
    """
    r = ops.REGISTRY["primo_ultimo_differenza"].run(_ore([128.389]), unit="kWh")

    assert not r.computable
    assert "un solo punto" in r.reason


def test_primo_ultimo_differenza_dice_di_quanto_e_salito_il_contatore():
    """La conversione dal grezzo -- dove un contatore scrive stringhe -- avviene
    al confine, non qui: il registro parla una forma sola."""
    r = ops.REGISTRY["primo_ultimo_differenza"].run(
        _ore([127.628, 128.389]), unit="kWh")

    assert r.value == 0.76


# -- le operazioni sul grezzo: episodi, durate, conteggi --------------------
#
# ESTRATTE dal ciclo apri/chiudi di `mind/facts.aggregate_day`. Le letture sono
# `(istante, stato)` come le scrive `mind/watcher.watch_reading`.

ACCESO = ("heat", "on", "not_home")


def _acceso(state):
    return str(state).strip().lower() in ACCESO


def test_episodio_apre_e_chiude_e_restituisce_un_periodo():
    readings = [(0.0, "off"), (3600.0, "heat"), (9000.0, "off"), (18000.0, "heat")]

    r = ops.REGISTRY["episodio"].run(readings, is_on=_acceso, period_end=21600.0)

    assert r.computable
    assert r.value.windows == ((3600.0, 9000.0), (18000.0, 21600.0))


def test_un_episodio_ancora_APERTO_arriva_alla_fine_del_periodo_e_non_oltre():
    """Cio' che a fine giornata e' ancora in corso e' un fatto: chiuderlo
    all'istante dell'ultima lettura direbbe che e' finito quando invece non
    lo sappiamo.

    Mutazione che la uccide: chiudere all'ultima lettura.
    """
    r = ops.REGISTRY["episodio"].run([(3600.0, "heat")], is_on=_acceso,
                                        period_end=21600.0)

    assert r.value.windows == ((3600.0, 21600.0),)


def test_senza_nessun_acceso_non_c_e_nessun_episodio_e_si_dice():
    """Zero episodi non e' un periodo vuoto da restituire: e' una risposta, e
    va detta -- `Period` rifiuta un elenco vuoto apposta."""
    r = ops.REGISTRY["episodio"].run([(0.0, "off")], is_on=_acceso,
                                        period_end=3600.0)

    assert not r.computable
    assert "nessun episodio" in r.reason


def test_episodio_i_due_capi_NON_si_trattano_allo_stesso_modo():
    """In coda si va oltre l'ultima lettura, in testa no -- e la differenza e'
    quanto sappiamo dei due silenzi.

    Dopo l'ultimo «acceso» nessuno ha detto «finito»: l'assenza di uno
    spegnimento e' informazione, e l'episodio arriva a fine periodo. Prima
    della prima lettura invece non stavamo guardando: allungare all'indietro
    inventerebbe un acceso che nessuno ha visto. Chi SA che era gia' acceso lo
    dice consegnando una lettura all'inizio, come fa `aggregate_day` con lo
    stato ereditato dal giorno prima.

    Mutazione che la uccide: far cominciare la prima finestra a zero invece
    che alla prima lettura.
    """
    letture = [(3600.0, "heat"), (7200.0, "off"), (10800.0, "heat")]

    r = ops.REGISTRY["episodio"].run(
        letture, is_on=lambda s: s == "heat", period_end=86400.0)

    assert r.value.windows == ((3600.0, 7200.0), (10800.0, 86400.0))


def test_tempo_in_stato_e_la_durata_del_periodo():
    p = ops.Period([(3600.0, 9000.0), (18000.0, 21600.0)])

    r = ops.REGISTRY["tempo_in_stato"].run(p)

    assert r.value == 9000.0
    assert r.unit == "s"


def test_quante_volte_conta_le_ACCENSIONI_non_le_letture():
    """Otto termostati producono migliaia di righe al giorno e otto cambi
    veri: contare le letture darebbe un numero enorme e falso."""
    p = ops.Period([(3600.0, 9000.0), (18000.0, 21600.0)])

    r = ops.REGISTRY["quante_volte"].run(p)

    assert r.value == 2
    assert r.unit == "volte"


def test_quando_succede_dice_le_ORE_in_cui_comincia():
    """A che ore del giorno comincia -- serve alle domande 1 e 4bis del
    proprietario. L'ora si legge sul fuso della CASA, che arriva da fuori
    **gia' risolto**: un'ora calcolata sul fuso di chi guarda risponderebbe a
    un'altra domanda.

    **Questa prova e' nata verde e non poteva fallire.** La prima stesura
    asseriva `0 <= ora <= 23`, che e' vero in QUALUNQUE fuso: la mutazione
    `fromtimestamp(zona)` -> `utcfromtimestamp`, eseguita il 12/09/2026, la
    lasciava verde. Riscritta sugli istanti veri, la stessa mutazione la fa
    arrossire -- e' il difetto n.1 di questo progetto, trovato su una prova
    scritta per difendere proprio dal fuso sbagliato.

    Gli istanti sono le 15:30 del 10/09/2026 e le 16:05 dell'11/09/2026 sul
    fuso di Roma: in UTC sono le 13 e le 14, quindi l'asserzione distingue
    davvero i due letture.

    Mutazione che la uccide: usare l'ora UTC.
    """
    p = ops.Period([(1789047000.0, 1789050000.0),
                     (1789135500.0, 1789139000.0)])

    r = ops.REGISTRY["quando_succede"].run(p, zone=ROMA)

    assert r.value == [15, 16], "in UTC sarebbero le 13 e le 14"
    assert r.unit == "ora del giorno"


def test_misure_durante_prende_solo_cio_che_e_dentro_le_finestre():
    """*«Mentre scaldava, da 18 a 21»*. Il limite non e' estetico: una misura
    presa PRIMA che l'episodio cominciasse e' il clima di prima, non l'effetto
    di quell'episodio.

    Mutazione che la uccide: ignorare il periodo e prendere tutte le letture.
    """
    p = ops.Period([(3600.0, 9000.0)])
    readings = [(0.0, "15.0"), (4000.0, "18.0"), (8000.0, "21.0"), (12000.0, "24.0")]

    r = ops.REGISTRY["misure_durante"].run(readings, period=p, unit="°C")

    assert [x["valore"] for x in r.value] == [18.0, 21.0]


def test_misure_durante_senza_niente_dentro_le_finestre_lo_dice():
    p = ops.Period([(3600.0, 9000.0)])

    r = ops.REGISTRY["misure_durante"].run([(0.0, "15.0")], period=p, unit="°C")

    assert not r.computable
    assert "nessuna misura" in r.reason


# -- le cinque nuove: ognuna da una domanda posta davvero -------------------
#
# `docs/design/2026-09-11-le-domande-del-proprietario.md`. Nessuna di queste
# nasce da un preventivo: `confronto_periodi` e `tendenza` dalla domanda 2
# («si puo' ottimizzare gestendo la diversa produzione per mese?»),
# `correlazione` dalla 3 (l'irrigazione contro il tempo che fa),
# `somma_entita` dalla 5 (le ore irrigate di TUTTE le zone),
# `raggruppa_per` dalla 6 (la CO2 di tutto il piano terra).


def test_confronto_periodi_dice_la_differenza_e_di_quanto_in_percentuale():
    first = ops.Measurement(23.71, unit="kWh", coverage=1.0)
    later = ops.Measurement(18.97, unit="kWh", coverage=1.0)

    r = ops.REGISTRY["confronto_periodi"].run(first, later)

    assert r.value == {"differenza": -4.74, "variazione": -0.2}
    assert r.unit == "kWh"


def test_confronto_periodi_da_un_periodo_a_ZERO_non_inventa_una_percentuale():
    """Una variazione percentuale su una base nulla non esiste. La differenza
    si', e si dice quella.

    Mutazione che la uccide: dividere comunque, o restituire 0.
    """
    first = ops.Measurement(0.0, unit="kWh", coverage=1.0)
    later = ops.Measurement(18.97, unit="kWh", coverage=1.0)

    r = ops.REGISTRY["confronto_periodi"].run(first, later)

    assert r.value["differenza"] == 18.97
    assert r.value["variazione"] is None


def test_tendenza_dice_il_verso_e_quanto_e_sottile_la_base():
    """*«Non si inventa una soglia: si archivia e si interpreta»* (09/09/2026).
    La tendenza non giudica: dice il verso, la pendenza, e **su quanti punti**
    -- perche' con 28 giorni di storia va detto che la base e' sottile."""
    r = ops.REGISTRY["tendenza"].run(_ore([10.0, 12.0, 14.0, 16.0]), unit="kWh")

    assert r.value["verso"] == "in salita"
    assert r.value["punti"] == 4


def test_una_tendenza_su_DUE_punti_non_e_una_tendenza():
    """Due punti fanno sempre una retta perfetta: chiamarla tendenza sarebbe
    un numero plausibile al posto di un «non lo so».

    Mutazione che la uccide: abbassare il minimo a due.
    """
    r = ops.REGISTRY["tendenza"].run(_ore([10.0, 16.0]), unit="kWh")

    assert not r.computable
    assert "punti" in r.reason


def test_correlazione_fra_due_serie_che_salgono_insieme():
    a = _ore([1.0, 2.0, 3.0, 4.0, 5.0])
    b = _ore([2.0, 4.0, 6.0, 8.0, 10.0])

    r = ops.REGISTRY["correlazione"].run(a, b)

    assert r.value == 1.0
    assert r.unit == "coefficiente"


def test_correlazione_su_serie_di_LUNGHEZZA_diversa_non_si_calcola():
    """Accoppiare punti che non si corrispondono produce un coefficiente, e
    quel coefficiente non parla di niente."""
    r = ops.REGISTRY["correlazione"].run(_ore([1.0, 2.0, 3.0, 4.0]),
                                            _ore([1.0, 2.0]))

    assert not r.computable
    assert "lunghezza" in r.reason


def test_correlazione_ALTA_su_due_serie_che_NON_si_causano():
    """Il coefficiente e' un fatto; la causa non lo e'. La spec lo chiede
    esplicitamente all'analista (§10): l'autosufficienza crollata e' spiegata
    dal meteo, ed e' una conferma, non una scoperta.

    **Riscritta il 12/09/2026, dopo la revisione indipendente.** La prima
    stesura asseriva che la stringa `returns` contenesse «non» e «caus»:
    arrossiva solo se qualcuno riscriveva la prosa, cioe' difendeva una frase
    e non un comportamento. Adesso dimostra il fatto: due serie con
    correlazione **perfetta** e nessun rapporto di causa fra loro -- il numero
    dei giorni del mese e il consumo che sale -- escono a 1,0, e quel'1,0 non
    e' una prova di niente. E' cio' che la spec chiede di ricordare a chi
    legge, e che l'operazione deve continuare a NON aggiungere.
    """
    giorni = _ore([1.0, 2.0, 3.0, 4.0, 5.0])
    consumo = _ore([10.0, 20.0, 30.0, 40.0, 50.0])

    r = ops.REGISTRY["correlazione"].run(giorni, consumo)

    assert r.value == 1.0
    # L'operazione restituisce un coefficiente e basta: nessun campo dice
    # «causa», e non c'e' nessun posto dove uno potrebbe comparire.
    assert r.unit == "coefficiente"


def test_somma_entita_mette_insieme_piu_misure_della_stessa_unita():
    """Domanda 5: «il totale delle ore irrigate» -- tutte le zone insieme."""
    zone = [ops.Measurement(3600.0, unit="s", coverage=1.0),
            ops.Measurement(1800.0, unit="s", coverage=1.0)]

    r = ops.REGISTRY["somma_entita"].run(zone)

    assert r.value == 5400.0
    assert r.unit == "s"


def test_somma_entita_la_copertura_e_UNA_FRAZIONE_SOLA_e_chi_manca_vale_zero():
    """Una somma che ignorasse un'entita' non calcolabile direbbe un totale
    piu' piccolo con la faccia di uno completo: la copertura deve pagarlo.

    **La formula e' cambiata il 12/09/2026, dopo la revisione indipendente.**
    Era `min(copertura) * quota di calcolabili` -- due grandezze diverse
    moltiplicate in un numero solo: chi leggeva 0,6 non poteva sapere se fosse
    0,9 di tempo su due terzi delle zone o 0,6 di tempo su tutte. Adesso ogni
    entita' porta la SUA copertura, chi manca porta zero, e la media di quelle
    e' «quanta parte di cio' che serviva si e' avuta» -- la definizione che la
    spec da' alla parola (§6), una sola.

    Qui: tre zone, coperture 1,0 / assente / 0,9 -> (1,0 + 0 + 0,9) / 3.
    La vecchia formula avrebbe detto 0,9 x 2/3 = 0,6.

    Mutazione ESEGUITA: `coverage=1.0` -- rossa.
    """
    zone = [ops.Measurement(3600.0, unit="s", coverage=1.0),
            ops.NotComputable("questa zona non ha dati"),
            ops.Measurement(1800.0, unit="s", coverage=0.9)]

    r = ops.REGISTRY["somma_entita"].run(zone)

    assert r.value == 5400.0
    assert r.coverage == pytest.approx(1.9 / 3)


def test_media_entita_NON_e_la_loro_somma_e_paga_la_stessa_copertura():
    """La media fra entita', con la stessa regola di copertura della somma.

    Esiste perche' `raggruppa_per` la chiama per la domanda 6: sommare due
    concentrazioni non produce una concentrazione.

    Mutazione ESEGUITA: `coverage=1.0` in `_average_entities` -- rossa.
    """
    stanze = [ops.Measurement(400.0, unit="ppm", coverage=1.0),
              ops.NotComputable("questo sensore non risponde"),
              ops.Measurement(500.0, unit="ppm", coverage=0.5)]

    r = ops.REGISTRY["media_entita"].run(stanze)

    assert r.value == 450.0
    assert r.unit == "ppm"
    assert r.coverage == pytest.approx(1.5 / 3)


def test_media_entita_di_unita_diverse_non_misura_niente():
    """Gradi e ppm mediati insieme danno un numero: quel numero e' una bugia.

    Mutazione che la uccide: togliere il controllo sulle unita'.
    """
    r = ops.REGISTRY["media_entita"].run(
        [ops.Measurement(20.0, unit="°C", coverage=1.0),
         ops.Measurement(400.0, unit="ppm", coverage=1.0)])

    assert not r.computable
    assert "unita" in r.reason


def test_somma_entita_di_sole_non_calcolabili_non_e_zero():
    r = ops.REGISTRY["somma_entita"].run([ops.NotComputable("niente dati")])

    assert not r.computable


def test_raggruppa_per_mette_insieme_le_entita_per_una_chiave():
    """Domanda 6: «la CO2 di tutto il piano terra». Il raggruppamento e' su un
    ramo dell'anagrafe, e la chiave arriva da fuori: questo modulo non sa
    cos'e' un piano, e non deve impararlo."""
    measurements = {"sensor.a": ops.Measurement(400.0, unit="ppm", coverage=1.0),
              "sensor.b": ops.Measurement(500.0, unit="ppm", coverage=1.0),
              "sensor.c": ops.Measurement(900.0, unit="ppm", coverage=1.0)}
    key = {"sensor.a": "terra", "sensor.b": "terra", "sensor.c": "primo"}

    r = ops.REGISTRY["raggruppa_per"].run(
        measurements, key=key.get, reduce="media_entita")

    assert r.computable
    # 400 e 500 sul piano terra fanno 450 di media, non 900 di somma: due
    # concentrazioni sommate non sono una concentrazione.
    assert r.value["terra"].value == 450.0
    assert r.value["primo"].value == 900.0


def test_raggruppa_per_NON_sceglie_da_solo_come_ridurre_un_gruppo():
    """**Il difetto trovato in revisione il 12/09/2026.** La prima stesura
    riduceva ogni gruppo con `somma_entita` per difetto, e «la CO2 del piano
    terra» rispondeva 900 ppm sommando 400 e 500 -- un numero senza
    significato con un'unita' accanto, cioe' la prima fondamenta rotta dentro
    l'operazione che doveva difenderla.

    La cura non e' scegliere meglio il valore per difetto: e' toglierlo.
    Sommare e mediare sono due domande diverse, e nessuna delle due e' «quella
    normale».

    Mutazione che la uccide: rimettere un valore per difetto a `reduce`.
    """
    measurements = {"sensor.a": ops.Measurement(400.0, unit="ppm", coverage=1.0)}

    with pytest.raises(TypeError):
        ops.REGISTRY["raggruppa_per"].run(measurements, key=lambda _: "terra")


def test_raggruppa_per_con_un_riduttore_INESISTENTE_lo_dice():
    """Un nome che non e' nel registro non produce gruppi vuoti ne' un crash:
    produce un rifiuto che dice quale nome non esiste.

    Mutazione che la uccide: `_REGISTRY[reduce]` nudo -- solleverebbe
    `KeyError` dentro l'aggregazione notturna invece di rispondere.
    """
    measurements = {"sensor.a": ops.Measurement(400.0, unit="ppm", coverage=1.0)}

    r = ops.REGISTRY["raggruppa_per"].run(
        measurements, key=lambda _: "terra", reduce="media_aritmetica")

    assert not r.computable
    assert "media_aritmetica" in r.reason


def test_raggruppa_per_NON_inventa_un_gruppo_per_chi_non_ha_chiave():
    """Un'entita' senza area non finisce in un gruppo «altro»: comparirebbe in
    un totale che nessuno ha chiesto. Si dichiara fuori, e si conta."""
    measurements = {"sensor.a": ops.Measurement(400.0, unit="ppm", coverage=1.0),
              "sensor.orfana": ops.Measurement(500.0, unit="ppm", coverage=1.0)}

    r = ops.REGISTRY["raggruppa_per"].run(
        measurements, key=lambda e: "terra" if e == "sensor.a" else None,
        reduce="somma_entita")

    assert set(r.value) == {"terra"}
    assert r.value["terra"].value == 400.0


def test_dentro_restringe_un_periodo_a_un_altro():
    """Il mattone che il cancello ha scoperto mancare: incrociare due periodi.

    Mutazione che la uccide: prendere tutto il primo periodo invece
    dell'intersezione.
    """
    scalda = ops.Period([(0.0, 7200.0), (18000.0, 21600.0)])
    in_casa = ops.Period([(3600.0, 10800.0)])

    r = ops.REGISTRY["dentro"].run(scalda, in_casa)

    assert r.value.windows == ((3600.0, 7200.0),)


def test_due_periodi_che_non_si_toccano_MAI_lo_dicono(monkeypatch):
    """**Questa prova mancava, e la mutazione l'ha rivelato.** Il ramo di
    rifiuto di `inside` non era esercitato da nessuno: la mutazione che lo
    toglieva usciva VERDE (eseguita il 12/09/2026). Senza, un'intersezione
    vuota proverebbe a costruire un `Period([])` e solleverebbe, invece di
    dire cos'e' successo -- che e' il contrario del contratto del registro.
    """
    r = ops.REGISTRY["dentro"].run(ops.Period([(0.0, 3600.0)]),
                                      ops.Period([(7200.0, 10800.0)]))

    assert not r.computable
    assert "non si sovrappongono" in r.reason


# ── IL CANCELLO DELLA FETTA: le sette domande del proprietario ─────────────
#
# Spec §6: *«Il set non si dimensiona a preventivo: si chiude con un test -- e'
# abbastanza ricco quando le domande vere del proprietario e il resoconto
# giornaliero si esprimono tutti senza aggiungerne una»*.
#
# Le domande sono in `docs/design/2026-09-11-le-domande-del-proprietario.md`,
# raccolte l'11/09/2026 con le parole del proprietario. Ogni prova qui sotto
# **compone una domanda con i mattoni del registro** e mostra che esce una
# risposta -- o un rifiuto motivato, dove la risposta onesta e' che HIRIS non
# puo' saperlo.
#
# Il cancello chiude da DUE lati, e serve che li chiuda entrambi:
#   1. nessuna domanda ha bisogno di un'operazione che non c'e';
#   2. nessuna operazione del registro e' orfana -- se nessuna domanda la
#      chiama, per la regola della spec non deve esistere.


def _letture_stato(pairs):
    return list(pairs)


def test_domanda_1_il_riscaldamento_l_effetto_e_le_persone():
    """*«Quando si accende il riscaldamento e porta la casa in temperatura, poi
    qualcuno e' in casa o meno?»*

    Quattro mattoni in fila: l'episodio del termostato, l'effetto misurato
    mentre durava, a che ora capita, e -- la parte che conta -- **il pezzo di
    quell'episodio in cui qualcuno c'era davvero**.
    """
    termostato = _letture_stato([(0.0, "off"), (3600.0, "heat"), (10800.0, "off")])
    temperatura = [(3700.0, "18.0"), (10000.0, "21.0")]
    presenza = [(0.0, "home"), (7200.0, "not_home")]

    scalda = ops.REGISTRY["episodio"].run(
        termostato, is_on=lambda s: s == "heat", period_end=14400.0)
    effetto_scaldata = ops.REGISTRY["misure_durante"].run(
        temperatura, period=scalda.value, unit="°C")
    effetto = ops.REGISTRY["primo_ultimo_differenza"].run(
        effetto_scaldata.value, unit="°C")
    orario = ops.REGISTRY["quando_succede"].run(scalda.value, zone=ROMA)
    in_casa = ops.REGISTRY["episodio"].run(
        presenza, is_on=lambda s: s == "home", period_end=14400.0)
    utile = ops.REGISTRY["dentro"].run(scalda.value, in_casa.value)
    servito = ops.REGISTRY["tempo_in_stato"].run(utile.value)
    sprecato = ops.REGISTRY["differenza_fra"].run(
        ops.REGISTRY["tempo_in_stato"].run(scalda.value), servito)

    assert effetto.value == 3.0, "la casa e' salita di tre gradi mentre scaldava"
    assert orario.computable
    # Ha scaldato per due ore, di cui una sola con qualcuno in casa.
    assert servito.value == 3600.0
    assert sprecato.value == 3600.0


def test_domanda_2_l_energia_e_la_stagione():
    """*«La mia produzione energetica copre bene casa mia, o si puo' ottimizzare
    gestendo la diversa produzione per mese?»*"""
    produzione = _ore([2.0] * 12 + [0.0] * 12)
    consumo = _ore([1.0] * 24)

    prodotta = ops.REGISTRY["somma_periodo"].run(produzione, unit="kWh")
    consumata = ops.REGISTRY["somma_periodo"].run(consumo, unit="kWh")
    coverage = ops.REGISTRY["quota"].run(consumata, prodotta)
    profilo = ops.REGISTRY["per_ora"].run(produzione, unit="kWh")
    mese_scorso = ops.Measurement(30.0, unit="kWh", coverage=1.0)
    confronto = ops.REGISTRY["confronto_periodi"].run(mese_scorso, prodotta)
    dove_va = ops.REGISTRY["tendenza"].run(_ore([30.0, 28.0, 24.0]), unit="kWh")

    assert prodotta.value == 24.0
    assert coverage.value == 1.0
    assert len(profilo.value) == 24
    assert confronto.value["differenza"] == -6.0
    assert dove_va.value["verso"] == "in discesa"


def test_domanda_3_l_irrigazione_e_il_prato():
    """*«L'irrigazione sta gestendo bene il fabbisogno del prato per il periodo
    in cui siamo?»*

    Il **fabbisogno del prato** non e' un dato di Home Assistant, e il registro
    non finge di saperlo: produce quanto si e' irrigato, quando, e quanto va
    d'accordo col tempo che faceva. Il giudizio sta fuori.
    """
    valvola = _letture_stato([(0.0, "off"), (3600.0, "on"), (5400.0, "off"),
                              (90000.0, "on"), (93600.0, "off")])

    giri = ops.REGISTRY["episodio"].run(
        valvola, is_on=lambda s: s == "on", period_end=172800.0)
    quante = ops.REGISTRY["quante_volte"].run(giri.value)
    quanto = ops.REGISTRY["tempo_in_stato"].run(giri.value)
    correlazione_meteo = ops.REGISTRY["correlazione"].run(
        _ore([30.0, 28.0, 31.0, 33.0]), _ore([1.5, 1.0, 1.6, 1.8]))

    assert quante.value == 2
    assert quanto.value == 5400.0
    assert correlazione_meteo.computable


def test_domanda_4_il_comfort_quando_conta():
    """*«A livello di comfort la casa e' sana quando c'e' qualcuno in casa?»*

    Una media di ventiquattr'ore risponderebbe a un'altra domanda: la
    grandezza si restringe ai periodi in cui una persona c'era.
    """
    presenza = _letture_stato([(0.0, "not_home"), (7200.0, "home"), (18000.0, "not_home")])
    co2 = [(3600.0, "1400.0"), (9000.0, "600.0"), (14400.0, "700.0"),
           (20000.0, "1500.0")]

    in_casa = ops.REGISTRY["episodio"].run(
        presenza, is_on=lambda s: s == "home", period_end=21600.0)
    mentre = ops.REGISTRY["misure_durante"].run(
        co2, period=in_casa.value, unit="ppm")
    com_era = ops.REGISTRY["media_min_max"].run(mentre.value, unit="ppm")

    # I due picchi a 1400 e 1500 sono FUORI dalle finestre di presenza: una
    # media di ventiquattr'ore li avrebbe contati, e avrebbe risposto a
    # un'altra domanda.
    assert com_era.value == {"media": 650.0, "minimo": 600.0, "massimo": 700.0}


def test_domanda_4bis_le_automazioni_rispondono_ancora():
    """*«Le automazioni presenti rispondono alle esigenze della casa?»*"""
    esecuzioni = _letture_stato([(0.0, "off"), (3600.0, "on"), (3660.0, "off"),
                                 (90000.0, "on"), (90060.0, "off")])

    scatti = ops.REGISTRY["episodio"].run(
        esecuzioni, is_on=lambda s: s == "on", period_end=172800.0)
    quante = ops.REGISTRY["quante_volte"].run(scatti.value)
    quando = ops.REGISTRY["quando_succede"].run(scatti.value, zone=ROMA)

    assert quante.value == 2
    assert quando.computable


def test_domanda_5_le_ore_irrigate_su_una_STAGIONE_si_rifiuta_con_la_ragione():
    """*«Dammi il totale delle ore irrigate tra maggio e settembre.»*

    Cinque mesi, con 22 giorni di grezzo e una valvola di cui Home Assistant
    non tiene statistiche: la risposta onesta non e' il totale delle tre
    settimane che abbiamo, spacciato per cinque mesi. Quel difetto ha gia' un
    precedente pagato (`_difference` che restituiva `0.0`).

    **Attenzione a cosa prova davvero questa prova, e la revisione
    indipendente del 12/09/2026 ha avuto ragione a chiederlo.** Il docstring
    diceva *«e' l'unica che prova che il registro sappia dire di no»*: falso.
    Il rifiuto *«il periodo chiesto sta fuori dalla memoria disponibile»* lo
    costruisce il CHIAMANTE e glielo consegna -- nessuna operazione del
    registro sa cosa sia la memoria disponibile, e nessuna `refuses_when` lo
    dichiara. Qui si difende la propagazione: **un totale di soli «non lo so»
    non e' zero**, e il registro non lo trasforma in un numero.

    I due rifiuti che la spec §6 chiede -- «l'entita' non ha statistiche», «il
    periodo e' fuori dalla memoria disponibile» -- **non sono implementati da
    nessuna operazione**, perche' tutti e due hanno bisogno di sapere fin dove
    arriva l'archivio, che e' conoscenza della casa e non del calcolo. Sono a
    backlog col disegno (12/09/2026).

    Mutazione che la uccide: in `_sum_entities`, restituire `Measurement(0.0,
    ...)` quando nessuna entita' e' calcolabile.
    """
    zone = [ops.NotComputable("il periodo chiesto sta fuori dalla memoria "
                               "disponibile: la valvola non ha statistiche e il "
                               "grezzo arriva a 22 giorni")
            for _ in range(3)]

    totale = ops.REGISTRY["somma_entita"].run(zone)

    assert not totale.computable
    assert "zero" in totale.reason


def test_domanda_6_la_co2_di_un_piano():
    """*«Dammi il livello di CO2 di tutto il piano terra.»*

    «Tutto il piano terra» e' un ramo dell'anagrafe, e la chiave arriva da
    fuori: il registro non sa cos'e' un piano.
    """
    measurements = {"sensor.a": ops.Measurement(400.0, unit="ppm", coverage=1.0),
              "sensor.b": ops.Measurement(500.0, unit="ppm", coverage=1.0),
              "sensor.c": ops.Measurement(900.0, unit="ppm", coverage=1.0)}
    piano = {"sensor.a": "terra", "sensor.b": "terra", "sensor.c": "primo"}

    per_piano = ops.REGISTRY["raggruppa_per"].run(
        measurements, key=piano.get, reduce="media_entita")

    # **La media, non la somma**: 400 e 500 ppm fanno un piano a 450, non uno a
    # 900. Come ridurre il gruppo lo dice la domanda, e il registro non lo
    # sceglie per nessuno.
    assert per_piano.value["terra"].value == 450.0


def test_domanda_7_i_problemi_NON_hanno_bisogno_di_un_calcolo():
    """*«Dammi tutti i problemi emersi in casa.»*

    **La domanda che dice dove finisce il mestiere del registro.** La risposta
    e' la cronaca del resoconto giornaliero, non un'operazione: al registro
    servono solo l'episodio -- aperto quando, chiuso quando, o ancora aperto --
    e da quanto dura. Una prova che dimostri che non tutte le domande si
    rispondono con un calcolo vale quanto una che dimostri il contrario: il
    rischio opposto, inventare un'operazione per ogni domanda, e' il modo in cui
    un registro «chiuso» smette di esserlo.
    """
    guasto = _letture_stato([(0.0, "chiuso"), (3600.0, "setup_retry")])

    aperto = ops.REGISTRY["episodio"].run(
        guasto, is_on=lambda s: s != "chiuso", period_end=90000.0)
    durata_aperto = ops.REGISTRY["tempo_in_stato"].run(aperto.value)

    assert durata_aperto.value == 86400.0


@contextlib.contextmanager
def _registro_spiato(eseguite: set):
    """Il registro con ogni operazione avvolta da una spia che ne annota il nome.

    Si sostituiscono le voci di `_REGISTRY` -- non di `REGISTRY`, che e' la
    vista di sola lettura -- cosi' che anche le operazioni chiamate **da
    dentro** un'altra (`raggruppa_per` chiama il suo riduttore) finiscano
    annotate. `Operation` e' congelata: se ne fa una copia con `replace`.
    """
    originali = dict(ops._REGISTRY)
    try:
        for nome, operazione in originali.items():
            def spia(*a, _nome=nome, _run=operazione.run, **k):
                eseguite.add(_nome)
                return _run(*a, **k)
            ops._REGISTRY[nome] = dataclasses.replace(operazione, run=spia)
        yield
    finally:
        ops._REGISTRY.clear()
        ops._REGISTRY.update(originali)


def test_IL_CANCELLO_nessuna_operazione_del_registro_e_ORFANA():
    """**L'altra meta' del cancello.** La spec e' netta: *«le nuove nascono
    ciascuna da una domanda posta davvero, non da un preventivo»*. Se
    un'operazione non serve a nessuna delle domande, non deve stare nel
    registro.

    Questa prova ha gia' lavorato due volte: `somma_entita`/`raggruppa_per`
    stavano per essere cancellate, e sono state salvate dalle domande 5 e 6,
    che il proprietario ha dato quando gli e' stato chiesto se una domanda di
    quella forma gli venisse naturale; `dentro` e' nata perche' la domanda 1
    non si scriveva senza.

    **Riscritta il 12/09/2026, dopo la revisione indipendente.** La prima
    stesura cercava la stringa `REGISTRY["nome"]` nel proprio sorgente fra due
    marcatori: difendeva *«il testo lo nomina»*, non *«una domanda lo
    esegue»*. Un commento l'avrebbe soddisfatta, una domanda scritta sotto il
    marcatore sarebbe stata invisibile, e `media_entita` -- che `raggruppa_per`
    chiama per nome, non per citazione -- risultava orfana pur essendo la
    risposta alla domanda 6. Adesso le domande si **eseguono** e si guarda
    quali operazioni hanno girato davvero.

    **Meta' del cancello della spec non e' qui, ed e' dichiarato**: §6 chiude
    il set su *«le domande vere del proprietario E il resoconto giornaliero»*.
    Il resoconto e' la Fetta 5: finche' non esiste, questa prova difende la
    prima meta' e nient'altro.

    Mutazione ESEGUITA: registrare un'operazione che nessuna domanda chiama
    (`media_entita` prima che la domanda 6 la usasse) -- rossa, col nome
    nell'elenco.
    """
    eseguite: set[str] = set()
    domande = sorted((nome, f) for nome, f in globals().items()
                     if nome.startswith("test_domanda_") and callable(f))
    assert len(domande) >= 7, (
        f"le domande del proprietario sono sette, qui ne girano {len(domande)}: "
        "un cancello che non le esegue tutte non e' il cancello")

    with _registro_spiato(eseguite):
        for _, funzione in domande:
            funzione()

    orfane = sorted(set(ops.REGISTRY) - eseguite)

    assert not orfane, (
        f"operazioni che nessuna domanda del proprietario esegue: {orfane}. "
        "Per la regola della spec non devono esistere: si tolgono, oppure si "
        "chiede al proprietario la domanda che le giustifica")
