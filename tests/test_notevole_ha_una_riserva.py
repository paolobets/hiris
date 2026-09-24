"""«Notevole adesso» non può sparire del tutto.

**Misurato sulla casa vera il 23/09/2026.** Il nucleo che il modello aveva
davanti chiudeva così:

    Il nucleo superava il tetto di 6800 caratteri:
    19 elementi notevoli non inclusi; 2 voci di comportamento non incluse.

E la sezione `## Notevole adesso` era **vuota**. Non un guasto: l'ordine di
taglio mette gli elementi notevoli per primi — «dal meno utile al più
prezioso» — e su una casa di quella taglia il tetto morde sempre. Quindi la
sezione che dovrebbe dire *cosa sta succedendo adesso* è vuota **per
costruzione**, e resta un'intestazione che promette una cosa che non arriva
mai.

**La riserva è dichiarata PROVVISORIA**, e il numero non è misurato: è scelto
piccolo apposta, perché costi poco e perché le misure che partono con questa
stessa fetta diranno se va alzato, abbassato, o tolto. La prova qui sotto
esiste per impedire che «provvisorio» diventi «permanente per dimenticanza» —
la stessa disciplina della soglia del freno di ritmo (reperto B-3).

Il meccanismo non è nuovo: la mappa ha già una riserva
(`_MIN_HOME_SPACE_LINES_RESERVE`) che il taglio non tocca. Si usa quello.
"""
from hiris.app.home_space import briefing
from hiris.app.home_space.briefing import compose

_CASA = {
    "piani": [{"id": "terra", "nome": "Terra"}],
    "aree": [{"id": "cucina", "nome": "Cucina", "piano_id": "terra"}],
    "entita": [{"id": f"light.l{n}", "nome": f"Luce {n}", "dominio": "light",
                "area_id": "cucina"} for n in range(40)],
}
_STATO = {f"light.l{n}": ("on" if n % 2 else "off") for n in range(40)}
_COMPORTAMENTO = [{"id": f"automation.a{n}", "nome": f"Automazione {n}",
                   "genere": "automazione"} for n in range(30)]
_RICORDI = [{"id": n, "testo": "x" * 200, "chi": "Paolo"} for n in range(10)]


def _sezione(testo: str, titolo: str) -> list[str]:
    """Le righe di una sezione, senza la sua intestazione."""
    dentro, righe = False, []
    for riga in testo.splitlines():
        if riga.startswith("## "):
            dentro = riga.strip() == titolo
            continue
        if dentro and riga.strip():
            righe.append(riga)
    return righe


def test_col_tetto_che_MORDE_la_sezione_non_resta_vuota():
    """**Il reperto.** Un tetto stretto su una casa piena: prima di oggi qui
    restava l'intestazione e basta.

    Mutazione ESEGUITA: rimettere la riserva a 0 -- rossa."""
    testo, riepilogo = compose(_CASA, _COMPORTAMENTO, _RICORDI, _STATO,
                               ceiling=1200)

    assert riepilogo["truncated"], "il tetto non ha morso: la prova non prova"
    assert _sezione(testo, "## Notevole adesso"), (
        "«Notevole adesso» è vuota: l'intestazione promette una cosa che non "
        "arriva mai")


def test_la_riserva_e_PICCOLA_e_non_mangia_la_mappa():
    """La mappa resta la cosa che costa meno per riga e serve di più per
    orientarsi: la riserva degli elementi notevoli non deve rubarle il posto.

    Mutazione ESEGUITA: alzare la riserva a venti righe -- rossa."""
    testo, _ = compose(_CASA, _COMPORTAMENTO, _RICORDI, _STATO, ceiling=1200)

    notevoli = _sezione(testo, "## Notevole adesso")
    mappa = _sezione(testo, "## La casa")

    # **Un numero, non la costante.** Confrontare con
    # `_MIN_HIGHLIGHT_LINES_RESERVE` renderebbe questa prova cieca proprio
    # sulla cosa che deve guardare: alzando la riserva si alzerebbe anche il
    # limite, e la prova passerebbe con una riserva di venti righe. Trovato
    # da una mutazione, non leggendo.
    assert briefing._MIN_HIGHLIGHT_LINES_RESERVE <= 5, (
        "la riserva non è più «piccola»: a questo punto è una sezione")
    assert len(notevoli) <= 5
    assert mappa, "la mappa è sparita: la riserva ha mangiato l'orientamento"


def test_la_riserva_si_dichiara_PROVVISORIA():
    """Il numero non è misurato — è scelto piccolo perché costi poco. Le
    misure che partono con questa stessa fetta diranno se va alzato,
    abbassato o tolto, e finché quella lettura non c'è il numero deve
    continuare a dire di sé che è provvisorio.

    **Questa prova non difende il codice: difende la dichiarazione.** È la
    stessa disciplina della soglia del freno di ritmo (B-3), e serve a
    impedire che «provvisorio» diventi «permanente per dimenticanza».

    Mutazione ESEGUITA: togliere la parola dal commento -- rossa."""
    import inspect

    sorgente = inspect.getsource(briefing)
    # Il commento che PRECEDE la costante, e solo quello: una finestra larga
    # prenderebbe la prosa della riserva della mappa, che parla d'altro, e la
    # prova direbbe di sì per una parola di qualcun altro. Trovato da una
    # mutazione.
    posizione = sorgente.index("_MIN_HIGHLIGHT_LINES_RESERVE = ")
    inizio = sorgente.rindex("_MIN_HOME_SPACE_LINES_RESERVE = 3", 0, posizione)
    intorno = sorgente[inizio:posizione]

    # **Si cerca l'AFFERMAZIONE, non la parola.** Cercare «provvisorio» da
    # solo non bastava: nella stessa finestra c'è anche la frase che cita
    # questa prova — «impedisce che «provvisorio» diventi «permanente per
    # dimenticanza»» — e quella sopravviveva alla cancellazione della
    # dichiarazione vera. La prova passava su un commento che non dichiarava
    # più niente. Trovato da una mutazione, non leggendo.
    dichiara = [riga for riga in intorno.splitlines()
                if "provvisori" in riga.lower() and "misurat" in riga.lower()]

    assert dichiara, (
        "la riserva non dichiara di essere provvisoria E non misurata: il "
        "giorno in cui le misure diranno quanto vale davvero, nessuno saprà "
        "che era da rivedere")


def test_la_riserva_tiene_un_POSTO_non_inventa_un_contenuto():
    """Una casa quieta — stato letto, e niente che meriti — deve continuare a
    dirlo. Una riserva che riempisse la sezione con un segnaposto sarebbe
    peggio di una sezione vuota: direbbe che qualcosa sta succedendo.

    **Attenzione a non confondere due cose**, ed è un comportamento che
    questo prodotto ha già scritto apposta: uno stato VUOTO non vuol dire
    «niente di notevole», vuol dire «non ho guardato», e lì la sezione porta
    una riga sola che lo dichiara. Sono due fatti diversi, e la prova
    guarda il secondo caso passando uno stato davvero letto.

    Mutazione ESEGUITA: riempire la sezione fino alla riserva con righe
    vuote -- rossa."""
    quieta = {f"light.l{n}": "off" for n in range(40)}

    testo, _ = compose(_CASA, _COMPORTAMENTO, _RICORDI, quieta, ceiling=6800)

    righe = _sezione(testo, "## Notevole adesso")
    assert not any(not r.strip() for r in righe), (
        "la riserva ha riempito la sezione con righe vuote")
