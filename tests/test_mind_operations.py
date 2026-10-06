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
import pytest

from hiris.app.mind import operations as ops


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
        ops.NotComputable("   ", cause=ops.COVERAGE_LOW)


def test_un_non_calcolabile_senza_causa_non_si_puo_costruire():
    """B-26 (attori, Task 1.2): la causa e' un CAMPO, non una parola da
    cercare nella prosa. Senza, la batteria conta «senza causa» e l'analista
    deve leggere la frase per sapere se la fonte e' spenta o la ricetta storta.
    """
    with pytest.raises(TypeError):
        ops.NotComputable("la serie e' vuota")


def test_una_causa_fuori_dal_vocabolario_non_si_puo_costruire():
    """Il vocabolario e' CHIUSO: una parola nuova entra in `MEASURE_CAUSES`
    con la sua ragione, o non entra."""
    with pytest.raises(ValueError):
        ops.NotComputable("la serie e' vuota", cause="vuota")


def test_le_cause_sono_gli_stati_della_fonte_piu_quelle_della_misura():
    """Un vocabolario, non due: gli stati della fonte (`House.source`, tutti
    tranne «viva», che non e' una causa di silenzio) e le cause che la misura
    aggiunge, ognuna con la sua ragione. Si CHIEDE alle due fonti."""
    from hiris.app.home_space.house import SOURCE_LIVE, SOURCE_STATES

    source_causes = set(SOURCE_STATES) - {SOURCE_LIVE}
    assert len(source_causes) == 6, "gli stati della fonte non si leggono piu'"
    assert ops.CAUSES == source_causes | set(ops.MEASURE_CAUSES)
    assert SOURCE_LIVE not in ops.CAUSES
    assert not source_causes & set(ops.MEASURE_CAUSES), (
        "una causa della misura ripete uno stato della fonte con la stessa parola")
    assert all(str(why).strip() for why in ops.MEASURE_CAUSES.values())


@pytest.mark.parametrize("cause", sorted(ops.CAUSES))
def test_ogni_causa_del_vocabolario_fa_un_non_calcolabile(cause):
    """Derivata: una causa che entra nel vocabolario entra qui senza toccare
    la prova."""
    refusal = ops.NotComputable("perche' si", cause=cause)
    assert refusal.cause == cause
    assert refusal == ops.NotComputable("perche' si", cause=cause)
    assert refusal != ops.NotComputable("perche' si", cause=next(
        c for c in sorted(ops.CAUSES) if c != cause))


def test_il_non_lo_so_si_propaga_CON_la_sua_causa():
    """Una quota su un contatore spento dal proprietario non e' una quota
    «senza causa»: la causa del termine mancante arriva fino in fondo, o il
    resoconto dice la cosa giusta solo per il primo passo della ricetta.

    Mutazione ESEGUITA: in `_ratio` tornare `NotComputable(r.reason,
    cause=COVERAGE_LOW)` invece di `r` -- rossa."""
    spento = ops.NotComputable("spento", cause="spenta_dal_proprietario")
    letto = ops.Measurement(4.0, unit="kWh", coverage=1.0)
    for operation, args in (("quota", (spento, letto)), ("quota", (letto, spento)),
                            ("differenza_fra", (spento, letto)),
                            ("confronto_periodi", (letto, spento))):
        result = ops.REGISTRY[operation].run(*args)
        assert result.cause == "spenta_dal_proprietario", operation


@pytest.mark.parametrize("operation, args, params, cause", [
    ("somma_periodo", ([],), {"unit": "kWh", "expected_parts": 24}, "copertura_bassa"),
    ("somma_periodo", ([{"valore": 1.0}] * 3,), {"unit": "kWh", "expected_parts": 24},
     "copertura_bassa"),
    ("somma_periodo", ([{"valore": 1.0}] * 30,), {"unit": "kWh", "expected_parts": 24},
     "ricetta_storta"),
    ("somma_periodo", ([{"media": 20.0, "minimo": 19.0, "massimo": 21.0}] * 24,),
     {"unit": "°C", "expected_parts": 24}, "ricetta_storta"),
    ("quota", (ops.Measurement(1.0, unit="kWh", coverage=1.0),
               ops.Measurement(0.0, unit="kWh", coverage=1.0)), {}, "senza_risposta"),
    ("differenza_fra", (ops.Measurement(1.0, unit="kWh", coverage=1.0),
                        ops.Measurement(1.0, unit="°C", coverage=1.0)), {},
     "ricetta_storta"),
])
def test_i_rifiuti_delle_operazioni_portano_la_loro_causa(operation, args, params, cause):
    """Ogni rifiuto di un'operazione dice DOVE sta il problema: nei dati del
    giorno (copertura bassa), nella ricetta (storta), o nella domanda, che coi
    dati giusti non ha risposta (denominatore nullo)."""
    result = ops.REGISTRY[operation].run(*args, **params)
    assert not result.computable
    assert result.cause == cause


def test_un_non_calcolabile_dice_perche_e_non_ha_valore():
    n = ops.NotComputable("il periodo e' fuori dalla memoria disponibile",
                          cause=ops.COVERAGE_LOW)

    assert n.computable is False
    assert "memoria" in n.reason
    assert not hasattr(n, "valore")


# -- il periodo: un ELENCO di finestre, non un intervallo solo --------------
#
# `episodio` lo produce e `tempo_in_stato` lo misura: e' la coppia che resta
# per la presenza (D7 del proprietario, 06/10/2026).


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
# ESTRATTA da `mind/facts.build_balance_body` (uscita il 01/10/2026), dove il
# totale di una dimensione era «la somma delle ore CONOSCIUTE». Li' la
# copertura non usciva: un totale fatto di tre ore su ventiquattro aveva la
# stessa faccia di uno completo. Le prove del bilancio che dicevano cose ancora
# vive delle operazioni sono state portate qui, accanto al loro soggetto.


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


def test_tre_ore_RICEVUTE_su_ventiquattro_attese_non_sono_un_totale_del_giorno():
    """**Le ore che Home Assistant NON manda sono il punto.** Portata qui il
    01/10/2026 da `test_mind_balance.py`, uscito col bilancio: la regola e'
    dell'operazione, e la usano ogni notte le ricette del sapere, che passano
    `expected_parts: 24`.

    La serie ha tre punti, tutti con un valore: contando solo i punti ricevuti
    la copertura direbbe 100%, e «3,0 kWh prodotti» avrebbe la faccia di un
    totale completo per una giornata di cui HIRIS ha visto un'ottava parte. E'
    `expected_parts` a dire quante ore doveva avere. La prova sopra
    (`test_sotto_la_soglia_...`) non lo coglie: le sue ore mancanti ci sono,
    con `valore: None`, e la lunghezza della serie basta gia'.

    Mutazione ESEGUITA: in `_known_points`, ignorare `expected_parts`
    (`expected = len(points)`) -- rossa.
    """
    tre_ore = _ore([1.0, 1.0, 1.0], start=6 * 3600.0)

    r = ops.REGISTRY["somma_periodo"].run(tre_ore, unit="kWh", expected_parts=24)

    assert not r.computable
    assert "copertura" in r.reason


# -- le operazioni sui numeri e sulle serie ---------------------------------
#
# ESTRATTE da `mind/facts.py`: `_share` -> `quota`, il `consumo - prelievo` di
# `_balance_moments` -> `differenza_fra`, la somma delle ore conosciute di
# `build_balance_body` -> `somma_periodo`, `_dimension_points` + `forma` ->
# `per_ora`. Le fonti sono uscite
# dal repo col bilancio il 01/10/2026; le operazioni restano, e le ricette del
# sapere le usano ogni notte.
#
# `media_min_max` **non e' estratta**: in `facts.py` non c'era nessuna media.
# (Una riga precedente diceva che veniva da `_percent`, che era
# l'arrotondamento della batteria a un decimale: e' uscito col bilancio.)


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
        ops.NotComputable("il contatore non ha statistiche", cause="senza_statistiche"),
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
    a = ops.NotComputable("la serie e' vuota", cause=ops.COVERAGE_LOW)
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


def test_per_ora_su_una_giornata_BUCATA_porta_l_ora_vera_non_quella_ricostruita():
    """**La prova sopra non distingue l'ora vera da «primo istante + indice»**:
    i suoi punti sono contigui, e su punti contigui le due cose coincidono per
    caso. E' gia' successo: un revisore ha rimesso lo stesso difetto
    ricostruendo l'ora dall'indice, e le prove restavano verdi perche' ogni
    giornata finta era contigua (mandato «il bilancio dell'energia», punto 1,
    27/08/2026). Portata qui il 01/10/2026 da `test_mind_balance.py`, uscito
    col bilancio: la forma la producono oggi le ricette del sapere, con
    `per_ora`.

    Qui Home Assistant ha OMESSO le 10 e le 11: con l'ora ricostruita
    dall'indice il quarto punto direbbe le 10 invece delle 12.

    Mutazione ESEGUITA: in `_per_hour`, `"ora": points[0]["inizio"] + i * 3600`
    al posto di `p.get("inizio")` -- rossa.
    """
    bucata = [p for p in _ore([1.0, 2.0, 3.0, 9.0, 9.0, 4.0, 5.0], start=7 * 3600.0)
              if p["inizio"] not in (10 * 3600.0, 11 * 3600.0)]

    r = ops.REGISTRY["per_ora"].run(bucata, unit="kWh", expected_parts=24)

    assert r.value == [
        {"ora": 7 * 3600.0, "valore": 1.0},
        {"ora": 8 * 3600.0, "valore": 2.0},
        {"ora": 9 * 3600.0, "valore": 3.0},
        {"ora": 12 * 3600.0, "valore": 4.0},
        {"ora": 13 * 3600.0, "valore": 5.0},
    ]


# -- le operazioni sul grezzo: episodi, durate, conteggi --------------------
#
# ESTRATTE dal ciclo apri/chiudi di `mind/facts.aggregate_day`. Le letture sono
# `(istante, stato)` come le scrive `mind/watcher.watch_reading`. Delle sei di
# questa famiglia ne restano due, quelle che servono alla presenza (D7 del
# proprietario, 06/10/2026, piano degli attori strati 3-4); le altre quattro
# sono uscite con le sette domande dell'11/09/2026, che nessuno poneva piu'.

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


def test_LA_PRESENZA_quanto_tempo_qualcuno_e_stato_in_casa():
    """La domanda per cui `episodio` e `tempo_in_stato` restano (D7, 06/10/2026):
    *quanto tempo una persona e' stata in casa*, dagli stati di `person`.

    Lo stato di una `person` e' lo stato del `device_tracker` che la alimenta
    (`homeassistant/components/person/__init__.py`, `_parse_source_state`:
    `self._attr_state = state.state`, letto sul ramo `dev` il 06/10/2026), cioe'
    `home`, `not_home` o il nome di una zona: conta solo `home`, e una zona
    diversa da casa non e' casa.

    Mutazione ESEGUITA: togliere `tempo_in_stato` dal registro -- rossa con
    `KeyError: 'tempo_in_stato'`.
    """
    letture = [(0.0, "not_home"), (3600.0, "home"), (10800.0, "Lavoro"),
               (14400.0, "home")]

    in_casa = ops.REGISTRY["episodio"].run(
        letture, is_on=lambda s: s == "home", period_end=21600.0)
    quanto = ops.REGISTRY["tempo_in_stato"].run(in_casa.value)

    assert in_casa.value.windows == ((3600.0, 10800.0), (14400.0, 21600.0))
    assert quanto.value == 7200.0 + 7200.0
    assert quanto.unit == "s"


# -- confronti e relazioni fra serie ---------------------------------------
#
# `confronto_periodi` e `tendenza` nacquero dalla domanda 2 del proprietario
# («si puo' ottimizzare gestendo la diversa produzione per mese?»),
# `correlazione` dalla 3 (l'irrigazione contro il tempo che fa):
# `docs/design/2026-09-11-le-domande-del-proprietario.md`, oggi storia. Sono
# offribili alle ricette, e restano per questo.


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


# ── Le misure istantanee: 56 entita' che le ricette non vedevano ────────────
#
# Misurato sulla casa vera il 14/09/2026 chiedendo a Home Assistant:
#
#   statistiche con SOMMA (contatori):    74
#   statistiche con MEDIA (measurement):  56
#   campi di una measurement: start, end, min, max, mean, last_reset
#
# Le 56 non hanno un `change`: hanno `mean`, `min`, `max`. Il nostro client li
# legge e li traduce gia' (`media`/`minimo`/`massimo`), e poi `_punti_orari`
# teneva SOLO `cambio` e buttava gli altri tre. Le ricette ricevevano una serie
# di `None` e rifiutavano dicendo «la serie e' vuota»: 21 misure su 32, in un
# giorno solo, tutte su temperatura, umidita', CO2, rumore, segnale, potenza.
#
# E' la frase fondativa della spec che succede dentro il codice nuovo: «Home
# Assistant dichiara gia' tutto, e la copia lo butta».


def _ore_istantanee(valori):
    """Ore di una statistica `measurement`, come le manda Home Assistant: media,
    minimo e massimo, e NESSUN cambio."""
    return [{"inizio": float(h * 3600), "fine": float((h + 1) * 3600),
             "valore": None, "media": m, "minimo": mi, "massimo": ma}
            for h, (m, mi, ma) in enumerate(valori)]


def test_media_min_max_usa_i_VERI_estremi_dell_ora_non_il_minimo_delle_medie():
    """Home Assistant manda gia' il minimo e il massimo di ogni ora: il minimo
    del giorno e' il piu' piccolo di QUELLI, non il piu' piccolo delle medie.
    Una stanza che scende a 14 gradi alle sei del mattino ha una media oraria
    di 16: prendere il minimo delle medie direbbe 16, e nasconderebbe proprio
    cio' che si va a cercare -- il docstring dell'operazione lo dice gia'.

    Mutazione: calcolare `min`/`max` sulle medie -- rossa (18.0 invece di 14.0).
    """
    serie = _ore_istantanee([(16.0, 14.0, 18.0), (20.0, 19.0, 21.0)])
    r = ops.REGISTRY["media_min_max"].run(serie, unit="\u00b0C", expected_parts=2)
    assert r.computable, getattr(r, "reason", None)
    assert r.value == {"media": 18.0, "minimo": 14.0, "massimo": 21.0}
    assert r.coverage == 1.0


def test_media_min_max_su_un_CONTATORE_continua_a_leggere_il_cambio():
    """La media oraria di un consumo resta una domanda legittima: se l'ora non
    porta una media -- perche' e' un contatore -- si legge il cambio, come
    prima. Una cosa nuova non deve togliere quella vecchia.

    Mutazione: leggere solo `media` -- rossa.
    """
    serie = [{"inizio": 0.0, "fine": 3600.0, "valore": 2.0},
             {"inizio": 3600.0, "fine": 7200.0, "valore": 4.0}]
    r = ops.REGISTRY["media_min_max"].run(serie, unit="kWh", expected_parts=2)
    assert r.computable
    assert r.value == {"media": 3.0, "minimo": 2.0, "massimo": 4.0}


def test_tendenza_legge_le_medie_orarie_di_una_misura_istantanea():
    """«La temperatura sta salendo?» e' una domanda su una misura istantanea, e
    fino al 14/09/2026 rifiutava sempre con «servono almeno 3 punti, ce ne sono
    0».

    Mutazione: lasciare `tendenza` sul solo `valore` -- rossa.
    """
    serie = _ore_istantanee([(16.0, 15.0, 17.0), (18.0, 17.0, 19.0),
                             (20.0, 19.0, 21.0)])
    r = ops.REGISTRY["tendenza"].run(serie, unit="\u00b0C")
    assert r.computable, getattr(r, "reason", None)
    assert r.value["verso"] == "in salita", r.value
    assert r.value["punti"] == 3


def test_una_serie_di_NON_NUMERI_non_si_rifiuta_dicendo_che_e_vuota():
    """**«Non c'e' niente» e «c'e', ma non e' un numero» sono due cose.**

    Home Assistant omette le ore senza dato, ma una serie che porta punti
    senza valore non e' vuota: dirlo sarebbe falso, ed e' lo stesso rimedio
    gia' applicato alle misure istantanee poche righe piu' su.

    **Questa prova nasce da una diagnosi sbagliata, e la nota resta.** Il
    15/09/2026 le 28 misure rifiutate del 14 dicevano «la serie e' vuota», e
    nella STORIA di Home Assistant `light.abat_jour_sinistra` aveva cinque
    punti: ne avevo concluso che l'operazione li ricevesse. Non li riceve --
    le ricette leggono le STATISTICHE orarie, che esistono solo per le entita'
    con uno `state_class`: 130 sulla casa, tutte `sensor`. Il caso qui provato
    e' reale ma **non e' successo ancora**; la causa dei 18 rifiuti veri e'
    un'altra, ed e' scritta nel backlog.

    Mutazione ESEGUITA: tornare alla frase unica -- rossa.
    """
    serie = [{"inizio": "2026-09-14T08:00:00", "valore": None, "stato": "on"},
             {"inizio": "2026-09-14T09:00:00", "valore": None, "stato": "off"}]
    r = ops.REGISTRY["somma_periodo"].run(serie, unit="kWh", expected_parts=2)
    assert not r.computable
    assert "2 punti" in r.reason, r.reason
    assert "vuota" not in r.reason, (
        "la serie non e' vuota: e' piena di cose che non sono numeri")


def test_una_serie_DAVVERO_vuota_lo_dice_ancora():
    """Il confine dalla parte opposta: zero punti resta zero punti.

    Mutazione ESEGUITA: dire «non sono numeri» anche quando non c'e' niente
    -- rossa, si manderebbe a cercare dati che non sono mai arrivati.
    """
    r = ops.REGISTRY["somma_periodo"].run([], unit="kWh", expected_parts=24)
    assert not r.computable
    assert "vuota" in r.reason, r.reason


def test_somma_periodo_su_una_misura_istantanea_RIFIUTA_dicendo_perche():
    """Sommare le temperature di ventiquattro ore non e' un numero: e' un
    errore. Prima rifiutava con «la serie e' vuota» -- vero e inutile, perche'
    la serie non e' vuota affatto: e' di un ALTRO tipo. Il rifiuto lo dice, o
    il modello riscrive la stessa ricetta.

    Mutazione: togliere il ramo del rifiuto dedicato -- rossa.
    """
    serie = _ore_istantanee([(16.0, 15.0, 17.0), (18.0, 17.0, 19.0)])
    r = ops.REGISTRY["somma_periodo"].run(serie, unit="\u00b0C", expected_parts=2)
    assert not r.computable
    assert "ISTANTANEA" in r.reason, r.reason
    assert "contatore" in r.reason, r.reason

# ---------------------------------------------------------------------------
# Il cancello della versione del registro
# ---------------------------------------------------------------------------

#: L'impronta di CIO' CHE IL MODELLO PUO' CHIEDERE, per la versione qui sotto.
#: Nomi, ingressi, resa, parametri obbligatori, forme e rifiuti dichiarati --
#: delle sole operazioni offribili. Cambia con `REGISTRY_VERSION`, mai da sola.
CATALOGUE_FINGERPRINT = {2: "bc902cb7f8ce6c78"}


def _impronta() -> str:
    import hashlib
    import json as _json

    voci = []
    for nome in sorted(ops.REGISTRY):
        o = ops.REGISTRY[nome]
        if not o.offerable:
            continue
        voci.append([nome, list(o.inputs), o.returns, list(o.required_params),
                     list(o.takes or ()), list(o.refuses_when)])
    return hashlib.sha256(_json.dumps(voci, ensure_ascii=False,
                                      sort_keys=True).encode()).hexdigest()[:16]


def test_il_catalogo_che_CAMBIA_alza_la_versione_del_registro():
    """**La costante che nessuno faceva salire.**

    `REGISTRY_VERSION` decide se un rifiuto vale ancora
    (`recipe_turn._still_valid`): un dispositivo che il modello non ha saputo
    misurare torna una domanda aperta **il giorno in cui il registro cambia**.
    E' una decisione del proprietario del 13/09/2026.

    Misurato dalla revisione indipendente il 15/09/2026: il registro era
    cambiato **tre volte** nello sprint -- `in_recipes`, le forme separate, i
    rifiuti dichiarati -- e il numero era rimasto **1**. Quindi la decisione
    non era mai scattata, e i 21 rifiuti archiviati erano eterni.

    Un numero che si alza a mano si dimentica. Questa prova lega la versione
    all'**impronta di cio' che il modello puo' chiedere**: cambiare il
    catalogo senza alzare la versione la fa arrossire, e alzare la versione
    obbliga a scrivere l'impronta nuova -- cioe' a guardare cosa e' cambiato.

    Mutazione ESEGUITA: aggiungere un parametro obbligatorio a un'operazione
    offribile senza toccare la versione -- rossa.
    """
    attesa = CATALOGUE_FINGERPRINT.get(ops.REGISTRY_VERSION)
    assert attesa is not None, (
        f"REGISTRY_VERSION e' {ops.REGISTRY_VERSION} e nessuno ha scritto "
        "l'impronta del catalogo per quella versione: si aggiunge una riga a "
        "CATALOGUE_FINGERPRINT col valore che questa prova stampa quando "
        "fallisce")
    assert _impronta() == attesa, (
        f"il catalogo e' cambiato ma REGISTRY_VERSION e' ancora "
        f"{ops.REGISTRY_VERSION}: i rifiuti gia' archiviati resterebbero "
        f"validi contro un registro che non esiste piu'. Impronta nuova: "
        f"{_impronta()}")
