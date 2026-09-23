"""Un segreto NUMERICO si oscura come uno testuale (reperto C-1, 23/09/2026).

**Riprodotto eseguendo il 21/09**, non dedotto:

    secrets.yaml:  codice_allarme: 1234  ·  password_nas: zxqw-7781-aab
    segreto TESTUALE -> <secret password_nas>     oscurato
    segreto NUMERICO -> 1234                      IN CHIARO

`from_file` calcolava l'impronta anche per gli interi e i decimali; `redact()`
sostituiva **solo** le stringhe. Un'impronta calcolata e mai confrontata.

**Lo scenario, e non è teorico su questa casa**: `codice_allarme: 1234` usato
con `alarm_control_panel.alarm_disarm`. Home Assistant restituisce il corpo
dell'automazione **già risolto**, quindi il codice di disarmo dell'allarme
arrivava al fornitore del modello.

## Il prezzo, dichiarato

Un `1234` che è una temperatura, una soglia o un numero di stanza **verrà
oscurato** se qualcuno ha dichiarato `1234` fra i segreti. È il prezzo di
riconoscere i segreti per valore invece che per nome, e il modulo lo dichiarava
già per le stringhe: qui vale uguale, e si paga volentieri — un numero oscurato
di troppo è leggibile come `<secret ...>`, un codice d'allarme in chiaro no.
"""
from hiris.app.home_space.redaction import SecretSeal, _fingerprint


def _sigillo(**segreti) -> SecretSeal:
    """Il sigillo VERO, con le impronte vere: una finta proverebbe che il
    confine chiama qualcosa, non che i segreti spariscano."""
    return SecretSeal({_fingerprint(str(v)): k for k, v in segreti.items()},
                      readable=True)


def test_un_segreto_NUMERICO_si_oscura():
    """**Il reperto C-1.** L'impronta si calcolava e non si confrontava mai.

    Mutazione ESEGUITA: sostituire solo le stringhe -- rossa (il `1234` torna
    in chiaro)."""
    sigillo = _sigillo(codice_allarme=1234)

    assert sigillo.redact(1234) == "<secret codice_allarme>"


def test_e_anche_un_DECIMALE():
    """`from_file` accetta `str | int | float`: se il confronto ne copre due su
    tre, il terzo e' un buco che nessuno vede finche' non ci passa.

    Mutazione: guardare solo gli interi -- rossa."""
    sigillo = _sigillo(soglia=12.5)

    assert sigillo.redact(12.5) == "<secret soglia>"


def test_un_numero_che_NON_e_un_segreto_resta_un_numero():
    """La contropartita, e conta: se ogni numero diventasse un segnaposto, il
    modello non leggerebbe piu' nessuna temperatura.

    Mutazione ESEGUITA: sostituire qualunque numero -- rossa."""
    sigillo = _sigillo(codice_allarme=1234)

    assert sigillo.redact(21) == 21
    assert sigillo.redact(21.5) == 21.5


def test_il_TIPO_di_cio_che_non_e_segreto_non_cambia():
    """Un `delay: 30` che diventasse `"30"` sarebbe un dato cambiato, non un
    dato protetto -- e il modello leggerebbe una configurazione che in casa non
    esiste.

    Mutazione ESEGUITA: passare tutto da `str()` prima di confrontare -- rossa."""
    sigillo = _sigillo(codice_allarme=1234)

    assert isinstance(sigillo.redact(30), int)
    assert isinstance(sigillo.redact(1.5), float)
    assert sigillo.redact(True) is True


def test_un_segreto_numerico_ANNIDATO_non_sfugge():
    """Il corpo di un'automazione annida: il codice sta dentro `data`, non al
    primo livello. E' esattamente la forma di `alarm_disarm`.

    Mutazione: fermarsi al primo livello -- rossa."""
    sigillo = _sigillo(codice_allarme=1234)

    pulito = sigillo.redact(
        {"actions": [{"action": "alarm_control_panel.alarm_disarm",
                      "data": {"code": 1234}}]})

    assert pulito["actions"][0]["data"]["code"] == "<secret codice_allarme>"


def test_il_segreto_TESTUALE_continua_a_funzionare():
    """La meta' che gia' andava: una correzione che la rompesse sarebbe un
    passo indietro travestito da passo avanti.

    Mutazione: sostituire i numeri e smettere con le stringhe -- rossa."""
    sigillo = _sigillo(password_nas="zxqw-7781-aab")

    assert sigillo.redact("zxqw-7781-aab") == "<secret password_nas>"


def test_un_numero_scritto_come_TESTO_si_oscura_lo_stesso():
    """`code: "1234"` e `code: 1234` sono la stessa cosa per chi disarma un
    allarme, e Home Assistant restituisce l'uno o l'altro a seconda di come e'
    scritta l'automazione.

    Mutazione ESEGUITA: confrontare il tipo oltre al valore -- rossa."""
    sigillo = _sigillo(codice_allarme=1234)

    assert sigillo.redact("1234") == "<secret codice_allarme>"


def test_il_PREZZO_e_scritto_accanto_alla_correzione():
    """Un numero innocente che vale quanto un segreto verra' oscurato. Il
    modulo lo dichiarava gia' per le stringhe; per i numeri capita piu' spesso,
    e chi legge deve trovarlo scritto invece di scoprirlo.

    Mutazione: togliere la dichiarazione -- rossa."""
    import inspect

    from hiris.app.home_space import redaction

    sorgente = inspect.getsource(redaction.SecretSeal.redact)

    assert "temperatura" in sorgente or "innocente" in sorgente, (
        "il prezzo di riconoscere i segreti per VALORE non e' dichiarato dove "
        "si paga")
