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
    # `impalcatura` non viene dal vocabolario dei tipi -- e' la **seconda
    # sorgente** del seme, nata il 20/09/2026: righe il cui soggetto e'
    # un'integrazione, non un tipo (`SCAFFOLDING_INTEGRATIONS`). Dichiararla
    # qui e' il punto: la prova continua a dire «nessun fatto importato da
    # Home Assistant diventa un giudizio», e non «il seme ha una sorgente
    # sola», che dal 20/09 sarebbe falso.
    assert campi <= set(tv.JUDGMENT_FIELDS.values()) | {tv.SCAFFOLDING}
    assert "capability_names" not in campi and "state_attributes" not in campi
    assert "attributi_assumibili" not in campi  # D1: resta codice


def test_il_seme_conta_121_celle_campo_per_campo():
    """Contato ESEGUENDO, non a mano: 99 celle prima della fetta «da sapere
    subito», 16 righe nuove il 18/09/2026 (115), e **6 righe di `impalcatura`
    il 20/09** -- le integrazioni che sono Home Assistant che parla di se'.
    121.

    Le sei non sono di gusto: ognuna e' comparsa in primo piano nella
    settimana 13-19/09, e insieme hanno fatto 12 righe su 42.

    Mutazione: dimenticare una delle righe -- rossa sul suo campo e sul
    totale.
    """
    import collections
    per_campo = collections.Counter(field for _, _, field, _ in tv.judgment_seed_rows())
    assert per_campo == {"genere": 26, "notevole": 23, "riposo": 18, "accendibile": 13,
                         "limiti_parametri": 10, "lavoro": 9, "da_sapere_subito": 16,
                         "impalcatura": 6}
    assert sum(per_campo.values()) == 121


def test_l_impronta_del_seme_vero_e_QUESTA():
    """Fix round 1 (revisione Fable, MINOR 7). L'impronta della cronaca di
    `REPO_JUDGMENTS` -- il seme vero, non uno costruito per la prova -- e'
    stata misurata il 18/09/2026, dopo la fetta «da sapere subito» (Task 1):
    `9692e12830c90fd0`. Fissarla qui per VALORE, non solo per uguaglianza fra
    due istantanee (le prove sopra e in `test_type_judgments.py` lo fanno
    gia'): il giorno in cui qualcuno tocca un valore di `genere` o `riposo`
    del seme -- gli unici due campi in `CHRONICLE_FIELDS` -- questa riga grida
    in CI invece di lasciare che il rilascio lo scopra dal vivo rifacendo
    silenziosamente la cronaca.

    Se il valore che si misura ESEGUENDO differisse da quello scritto qui, la
    regola e' non scriverlo a mano: fermarsi e dirlo -- e' esattamente il
    controllo che questa prova costituisce.

    Mutazione: cambiare un valore di `riposo` di un tipo qualunque del seme
    (es. aggiungere uno stato al riposo di `light`) -- rossa, l'impronta si
    sposta."""
    assert tv.REPO_JUDGMENTS.chronicle_fingerprint() == "9692e12830c90fd0"


def test_i_sedici_tipi_da_sapere_subito_sono_QUESTI():
    """Decisione del proprietario, 18/09/2026 (spec §2): i dodici di genere
    `sicurezza` piu' i quattro sensori di apertura. L'elenco si fissa per NOME,
    non per numero: un conteggio giusto con un tipo sbagliato passerebbe.

    Mutazione ESEGUITA: messo `da_sapere_subito` anche su `light` -- rossa qui,
    sull'`assert soggetti == [...]` qui sotto (`'light' != 'lock'` nell'elenco
    ordinato), e sulla prova sorella
    `test_da_sapere_subito_NON_e_notevole_e_i_due_elenchi_DIVERGONO`, sulla sua
    asserzione `'light' in notevoli and 'light' not in subito`. Ripristinata
    con l'editor, verificato con `git diff`.

    **Citata per nome, non per numero di riga** (backlog, «Le citazioni per
    numero di riga marciscono»): le due righe indicate qui prima -- 124 e 142 --
    erano gia' scivolate il giorno dopo.
    """
    # **Non si filtra su `v == "si"`**: dal 18/09/2026 il valore ha TRE forme e
    # `lock` porta l'elenco `["jammed"]`. Un filtro sul solo `si` avrebbe fatto
    # sparire la serratura da questo elenco in silenzio -- cioe' avrebbe smesso
    # di sorvegliare proprio la riga piu' interessante. Si esclude `no`, che e'
    # l'unico valore che dice davvero «non va saputo subito».
    soggetti = sorted(s for _, s, f, v in tv.judgment_seed_rows()
                      if f == "da_sapere_subito" and v != "no")
    assert soggetti == sorted([
        "alarm_control_panel", "lock", "siren",
        "binary_sensor.carbon_monoxide", "binary_sensor.cold", "binary_sensor.door",
        "binary_sensor.garage_door", "binary_sensor.gas", "binary_sensor.heat",
        "binary_sensor.moisture", "binary_sensor.opening", "binary_sensor.problem",
        "binary_sensor.safety", "binary_sensor.smoke", "binary_sensor.tamper",
        "binary_sensor.window"])


def test_da_sapere_subito_NON_e_notevole_e_i_due_elenchi_DIVERGONO():
    """La ragione per cui questa fetta esiste, scritta come prova: `notevole`
    sta su 23 soggetti fra cui `light`, `switch`, `cover`, `media_player`;
    `da_sapere_subito` su 16, e una luce accesa non c'e'. Se i due elenchi
    coincidessero, il campo nuovo sarebbe un doppione -- ed e' esattamente cio'
    che questa prova sorveglia.
    """
    notevoli = {s for _, s, f, v in tv.judgment_seed_rows() if f == "notevole" and v == "si"}
    # `v != "no"` e non `v == "si"`: `lock` porta l'elenco `["jammed"]` (vedi la
    # prova sopra), e con un filtro sul solo `si` questo confronto avrebbe
    # taciuto su di lei.
    subito = {s for _, s, f, v in tv.judgment_seed_rows()
              if f == "da_sapere_subito" and v != "no"}
    assert "light" in notevoli and "light" not in subito
    assert "switch" in notevoli and "switch" not in subito
    assert "alarm_control_panel" in subito and "alarm_control_panel" not in notevoli
    assert notevoli != subito


def test_OGNI_tipo_da_sapere_subito_HA_un_riposo_O_un_lavoro():
    """Ruling del controller (giro di correzioni 1, IMPORTANT 2b). Un tipo
    `da_sapere_subito: si` SENZA `riposo` ne' `lavoro` e' un caso **indecidibile**
    per `stato_da_sapere_subito` (spec `2026-09-18-da-sapere-subito.md` §3): non
    c'e' modo di dire quando una cosa esce da un riposo che nessuno ha
    dichiarato.

    Chi lo protegge, oggi, sono TRE cose diverse, e vale la pena non
    confonderle:

    - **la regola** risponde `no` ("indecidibile vale no", revisione finale,
      I-1): e' la sola garanzia, perche' e' l'unica che regge anche su un `si`
      orfano gia' scritto nell'archivio;
    - **la porta** (`mind/judgments._check`) rifiuta di scriverlo, spiegando
      perche': una cortesia a chi scrive, non una garanzia -- il `si` orfano si
      ottiene comunque scrivendo prima il riposo e togliendolo dopo;
    - **questa prova** sorveglia che il SEME non lo semini mai. Oggi le
      **quindici** righe `si` ce l'hanno tutte; la sedicesima, `lock`, porta un
      elenco di stati e questa domanda non la riguarda (l'elenco dice gia' cosa
      conta).

    Mutazione ESEGUITA: tolto `resting_states=...` dalla `_vocabulary.add` di
    `alarm_control_panel` e la sua riga `_vocabulary.extend` che da'
    `working_states` (entrambe in `home_space/type_vocabulary.py`, citate per
    soggetto e non per numero di riga: vedi la voce di backlog «Le citazioni per
    numero di riga marciscono»). Prima provato su `siren`, ma `siren` e'
    dichiarato accendibile (`operable=Ours(True)`) e un'altra guardia del
    modulo (`_verify_operable_types_bring_their_rest`) rifiuta l'import prima
    ancora che questa prova giri; `alarm_control_panel` non e' accendibile e
    arriva alla prova. Rossa su questo file: `assert ['alarm_control_panel']
    == []`. Ripristinate entrambe le righe con l'editor, verificato con
    `git diff` che il file torna identico a prima.
    """
    # Solo le righe `si`: per un ELENCO di stati la domanda non si pone -- e'
    # l'elenco stesso a dire cosa conta, e non c'e' niente da decidere (vedi
    # `stato_da_sapere_subito`, primo ramo).
    subito = sorted(s for _, s, f, v in tv.judgment_seed_rows()
                    if f == "da_sapere_subito" and v == "si")
    senza = []
    for soggetto in subito:
        dominio, _, classe = soggetto.partition(".")
        classe = classe or None
        if not tv.REPO_JUDGMENTS.resting_of(dominio, classe) and not dict(
                tv.REPO_JUDGMENTS.working_of(dominio, classe)):
            senza.append(soggetto)
    assert senza == []


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


def test_la_SERRATURA_porta_un_ELENCO_e_le_altre_quindici_un_SI():
    """Decisione del proprietario, 18/09/2026 (spec §2, terza forma del
    valore). Fissato per NOME e per VALORE: un conteggio giusto con la riga
    sbagliata passerebbe.

    **Perche' proprio `lock`, e nessun'altra delle sedici.** Misurato: l'allarme
    ha un `lavoro` di UN solo stato (`triggered`), i tredici `binary_sensor` e
    la sirena non dichiarano nessun `lavoro` e la regola usa il loro riposo.
    Per `lock`, `lavoro` vuol dire «sta operando» (`locking`, `opening`,
    `unlocking`, `unlocked`, `open`) e `jammed` non e' ne' lavoro ne' riposo:
    col solo `si` sarebbe entrato in banda ogni sblocco e non l'inceppamento.

    Mutazione ESEGUITA: rimesso `Ours(True)` su `lock` in
    `type_vocabulary.py` -- rossa su questo file (`'si' != '["jammed"]'`) e su
    `test_type_judgments.py::test_una_SERRATURA_INCEPPATA_va_saputa_subito_e_una_SBLOCCATA_no`
    (`unlocked` torna in banda, `jammed` ne esce). Ripristinata con l'editor,
    verificato che il conteggio del seme resta 115 e l'impronta
    `9692e12830c90fd0`.
    """
    valori = {s: v for _, s, f, v in tv.judgment_seed_rows() if f == "da_sapere_subito"}
    assert valori["lock"] == '["jammed"]'
    altri = sorted(s for s, v in valori.items() if s != "lock")
    assert len(altri) == 15
    assert {valori[s] for s in altri} == {"si"}
    # E l'elenco si legge come un insieme, non come testo.
    assert tv.REPO_JUDGMENTS.da_sapere_subito("lock") == frozenset({"jammed"})
