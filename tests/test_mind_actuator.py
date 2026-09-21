"""L'attuatore, la parte che decide senza modello (spec 2026-09-21 §4).

**Il terzo attore del cervello** (25/08/2026), e la misura che ne ha deciso la
forma: delle otto osservazioni vere che l'analista ha scritto sulla casa il 15
e il 16/09, **cinque chiedono di indagare**, tre di riparare una ricetta di
HIRIS, una di cambiare un comportamento, e **zero di costruire
un'automazione**. Un attuatore che «crea le soluzioni» non avrebbe avuto
niente da creare.

Qui vive solo cio' che si decide **senza parlare col modello**: quali domande
sono ancora aperte, e quali sono gia' state decise dal proprietario con una
prova che non e' cambiata.
"""
from hiris.app.mind import actuator as act


def _osservazione(**extra):
    riga = {"soggetto": "dev1", "misura": "prelievo", "chiave": None,
            "innesco": 1, "base": 19, "quanti_scarti": 3,
            "cosa": "il prelievo si stacca dal comportamento tipico",
            "cosa_cambierebbe": "spostare i consumi nelle ore di sole"}
    riga.update(extra)
    return riga


def test_due_osservazioni_sulla_stessa_cosa_hanno_la_stessa_impronta():
    """L'impronta e' l'IDENTITA' della domanda -- chi, cosa si misura, quale
    chiave, con quale innesco -- e **non cambia se cambiano i numeri**: e'
    cosi' che una proposta gia' decisa non torna il giorno dopo con la stessa
    faccia.

    Mutazione: mettere `base` dentro l'impronta -- rossa (ogni giorno sarebbe
    una domanda nuova, e il rifiuto di ieri non varrebbe piu' niente)."""
    assert act.observation_key(_osservazione(base=3)) == \
        act.observation_key(_osservazione(base=19))


def test_un_INNESCO_diverso_e_una_domanda_diversa():
    """«E' cambiato e non e' spiegato» e «non c'e' piu'» sono due domande
    diverse sullo stesso dato, e meritano due risposte.

    Mutazione: togliere l'innesco dall'impronta -- rossa."""
    assert act.observation_key(_osservazione(innesco=1)) != \
        act.observation_key(_osservazione(innesco=3))


def test_un_osservazione_gia_decisa_si_SALTA():
    """Mutazione: ignorare `decided` -- rossa (la stessa cosa tornerebbe in
    coda ogni giorno, che e' il rumore che questa fetta esiste per evitare)."""
    osservazione = _osservazione()
    decise = {act.observation_key(osservazione): act.evidence_of(osservazione)}

    assert act.to_handle([osservazione], decise) == []


def test_una_PROVA_cambiata_riapre_la_domanda():
    """«Un rifiuto non e' definitivo: vale finche' vale il registro contro cui
    e' stato deciso» -- la regola che il sapere usa gia' per le ricette, qui
    applicata alle proposte. Una base che passa da 3 giorni a 19 e' una prova
    diversa, non la stessa detta due volte.

    Mutazione: confrontare la sola impronta -- rossa (il silenzio dopo un no
    diventerebbe definitivo anche quando il fondamento e' cambiato)."""
    vecchia = _osservazione(base=3)
    decise = {act.observation_key(vecchia): act.evidence_of(vecchia)}

    nuova = _osservazione(base=19)
    assert act.to_handle([nuova], decise) == [nuova]


def test_una_prova_UGUALE_non_riapre_niente():
    """La contropartita della prova qui sopra: senza di lei, un `to_handle`
    che torna sempre tutto la passerebbe.

    Mutazione: `return list(observations)` -- rossa."""
    osservazione = _osservazione()
    decise = {act.observation_key(osservazione): act.evidence_of(osservazione)}

    assert act.to_handle([osservazione], decise) == []


def test_senza_niente_di_deciso_si_prende_tutto_in_carico():
    """Il primo giorno non c'e' niente di deciso, e tutto e' una domanda
    aperta: una guardia che sbagliasse il verso lascerebbe l'attuatore muto
    per sempre, ed e' un difetto che nessuno noterebbe.

    Mutazione: invertire la condizione -- rossa."""
    osservazioni = [_osservazione(), _osservazione(soggetto="dev2")]

    assert act.to_handle(osservazioni, {}) == osservazioni


# ---------------------------------------------------------------------------
# Le ricette rotte: il gesto che nessun altro fara' mai.
# ---------------------------------------------------------------------------

def test_una_misura_che_NON_SI_CALCOLA_PIU_e_una_ricetta_rotta():
    """Misurato: 3 osservazioni su 8 dicono questo. `devices_to_ask` salta i
    dispositivi che una ricetta ce l'hanno gia', anche quando e' rotta --
    quindi nessuno la riscrive, e l'analista se ne lamenta ogni giorno.

    **`broken_recipes` e' stata scritta insieme al modulo, non dopo una prova
    rossa**: la sua tenuta e' stata provata con la mutazione qui sotto,
    eseguita e osservata rossa -- riconoscerle dalla prosa
    (`"non si calcola" in o["cosa"]`) invece che dall'innesco.
    """
    rotta = _osservazione(innesco=3, base=0,
                          spiegato="il registro non sa piu' eseguire primo_ultimo")
    sana = _osservazione(innesco=1)

    assert act.broken_recipes([rotta, sana]) == [rotta]


def test_un_TERZO_INNESCO_con_una_base_vera_non_e_una_ricetta_rotta():
    """«Non c'e' piu'» puo' anche voler dire «il dispositivo e' muto»: se la
    misura ha una storia dietro, la ricetta regge e il problema e' altrove.
    Riscrivere la ricetta li' sarebbe curare il sintomo sbagliato.

    Mutazione: togliere `and not o.get("base")` -- rossa."""
    muto = _osservazione(innesco=3, base=12)

    assert act.broken_recipes([muto]) == []
