"""Il seme dei giudizi riproduce OGGI, esattamente (spec 2026-09-16 §5, §9.1).

**La prova di equivalenza con la regola vecchia e' uscita al Task 4** (17/09/2026):
`test_il_genere_del_seme_e_UGUALE_alla_regola_di_oggi` confrontava, su tutte le
76 righe, il genere dell'istantanea con `facts.genre_for(soggetto,
_reading_aspect(...))`. Il Task 4 ha cambiato la firma di `genre_for` (il secondo
argomento e' la `device_class`, non piu' la gamba) e tolto `_reading_aspect`:
la regola vecchia non si puo' piu' chiamare. La prova e' girata verde sul codice
del Task 2, con la sola eccezione dichiarata delle 4 righe `energia` (vecchia
`energia`, nuova nessun genere: D2). Resta la prova contro i valori ATTESI
scritti a mano qui sotto, che non derivano dal vocabolario."""
from hiris.app.home_space import type_vocabulary as tv
from hiris.app.home_space.type_judgments import TypeJudgments

ATTESI = {
    "person": "presenza", "device_tracker": "presenza",
    "climate": "funzionamento", "cover": "funzionamento", "switch": "funzionamento",
    "light": "funzionamento", "fan": "funzionamento", "water_heater": "funzionamento",
    "humidifier": "funzionamento", "vacuum": "funzionamento", "valve": "funzionamento",
    "lawn_mower": "funzionamento", "remote": "funzionamento", "media_player": "funzionamento",
    "lock": "sicurezza", "alarm_control_panel": "sicurezza", "siren": "sicurezza",
    "binary_sensor.smoke": "sicurezza", "binary_sensor.gas": "sicurezza",
    "binary_sensor.carbon_monoxide": "sicurezza", "binary_sensor.moisture": "sicurezza",
    "binary_sensor.safety": "sicurezza", "binary_sensor.tamper": "sicurezza",
    "binary_sensor.problem": "sicurezza", "binary_sensor.heat": "sicurezza",
    "binary_sensor.cold": "sicurezza",
}
# D2: `sensor.energy/power/gas/water` davano `energia`, un GENERE MORTO (spec
# §5: nessun ramo di `facts.build_episodes` lo tratta). Nel seme non hanno
# genere, quindi non stanno in `ATTESI`: la prova qui sotto li vuole `None`.


def test_il_genere_del_seme_su_TUTTE_le_76_righe_e_quello_scritto_a_mano():
    """Mutazione: cambiare `siren` in `funzionamento` nel letterale -- rossa.
    Seconda mutazione: dare `presenza` a `binary_sensor.occupancy` -- rossa
    (i sensori di presenza NON entrano nel seme: li scrive il proprietario).

    **Si contano le righe visitate e si esaurisce `ATTESI`** (giro di
    correzioni 1, punto 7): il ciclo da solo non asseriva ne' QUANTE righe
    fossero, ne' che ogni chiave scritta a mano qui sopra fosse stata davvero
    incontrata -- una riga cancellata dal letterale del vocabolario sarebbe
    passata in silenzio, perche' la prova avrebbe semplicemente girato su una
    riga in meno.

    Mutazione ESEGUITA: togliere `"motion"` da `_vocabulary.add_all(
    "binary_sensor", ("presence", "occupancy", "motion"))` -- **verde** col
    ciclo da solo (quella coppia non porta nessun genere: sparendo, non c'e'
    piu' niente da confrontare) e **rossa** sul conteggio, «il vocabolario
    dichiara 75 righe, non 76»; ripristinata con l'editor, sha256 identico.

    **Perche' la coppia e non un dominio.** Cancellare `_vocabulary.add(
    "person", ...)` -- eseguito -- lascia `person` fra le righe lo stesso: il
    ciclo delle tabelle degli attributi in fondo al modulo ricrea la riga
    (`_vocabulary.add(_domain, **_new_fields)`), spogliata dei suoi giudizi, e
    li' il ciclo di questa prova si accorge da solo («`assert None ==
    'presenza'`»). Le righe che possono sparire **davvero** sono le coppie, che
    nessun'altra tabella rivendica -- ed e' esattamente dove il ciclo era
    cieco."""
    j = tv.REPO_JUDGMENTS
    visitate = []
    for row in tv._vocabulary.rows():
        key = row.domain + (f".{row.device_class}" if row.device_class else "")
        atteso = ATTESI.get(key)
        assert j.genre_of(f"{row.domain}.x", row.device_class) == atteso, key
        visitate.append(key)
    assert len(visitate) == 76, f"il vocabolario dichiara {len(visitate)} righe, non 76"
    assert set(ATTESI) - set(visitate) == set(), (
        "ogni chiave di ATTESI deve essere stata visitata: una riga sparita dal "
        "letterale del vocabolario si vede solo cosi'")


def test_il_riposo_della_persona_e_casa():
    """Il ramo scritto a mano con `"home"` diventa una riga (spec §5).
    Mutazione: togliere `riposo` da `person` -- rossa."""
    assert tv.REPO_JUDGMENTS.resting_of("person") == frozenset({"home"})
    assert tv.REPO_JUDGMENTS.resting_of("device_tracker") == frozenset({"home"})


def test_i_fatti_di_HA_non_entrano_nel_seme():
    """Spec §2.

    **La mutazione del capitolato (aggiungere `CAPABILITY_NAMES` a
    `JUDGMENT_FIELDS`) e' risultata INERTE, eseguita ed osservata verde**:
    quel campo e' sempre `importato` (mai `nostro`), e `judgment_seed_rows()`
    filtra per provenienza PRIMA di guardare `JUDGMENT_FIELDS` -- nessuna riga
    nasce mai da li', a prescindere dalla mappa. Riscritta con una mutazione
    che discrimina davvero: **aggiungere `ASSUMABLE_ATTRIBUTES` (D1, `nostro`)
    a `JUDGMENT_FIELDS`** -- rossa: la costruzione dell'istantanea solleva
    `JudgmentError` (`attributi_assumibili` non e' un giudizio), eseguita e
    osservata."""
    campi = {field for _, _, field, _ in tv.judgment_seed_rows()}
    assert campi <= set(tv.JUDGMENT_FIELDS.values())
    assert "capability_names" not in campi and "state_attributes" not in campi
    assert "attributi_assumibili" not in campi  # D1: resta codice


def test_il_seme_conta_99_celle_campo_per_campo():
    """Contato eseguendo il 16/09/2026 sulla 3.48.1 (spec §2). Mutazione:
    dimenticare le due righe `home` -- rossa su `riposo`."""
    import collections
    per_campo = collections.Counter(field for _, _, field, _ in tv.judgment_seed_rows())
    assert per_campo == {"genere": 26, "notevole": 23, "riposo": 18, "accendibile": 13,
                         "limiti_parametri": 10, "lavoro": 9}
    assert sum(per_campo.values()) == 99


def test_il_seme_si_rilegge_in_un_istantanea_identica():
    """Mutazione ESEGUITA (non nel capitolato): costruire `REPO_JUDGMENTS` da
    `judgment_seed_rows()[:-1]` -- rossa (`REPO_JUDGMENTS` perde l'ultima
    riga, `rifatta` no).

    **Cosa sorveglia davvero, e cosa NO** (giro di correzioni 1, punto 7):
    `REPO_JUDGMENTS` nasce **dalla stessa chiamata** a `judgment_seed_rows()`
    che questa prova rifa', quindi l'uguaglianza e' in gran parte tautologica.
    Cio' che resta e' un fatto solo, e vale la pena: **`REPO_JUDGMENTS` e'
    costruita dal seme e non scritta a mano accanto a lui** -- il giorno in cui
    qualcuno le desse righe sue, o le passasse altri `genres`/`absent_forms`,
    le due divergerebbero. NON sorveglia il contenuto del seme (lo fanno le
    prove qui sopra, contro `ATTESI` e contro i conteggi scritti a mano) ne'
    la stabilita' del seme fra due letture: `judgment_seed_rows()` e'
    chiamata due volte, ma da un letterale immutabile."""
    rifatta = TypeJudgments.from_rows(tv.judgment_seed_rows(), genres=tv.CHRONICLE_GENRES,
                                      absent_forms=tv.ABSENT_STATE_FORMS.value)
    assert rifatta.rows() == tv.REPO_JUDGMENTS.rows()
