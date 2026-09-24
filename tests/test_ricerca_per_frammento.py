"""«Accendi la luce della taverna» non trovava niente, e le luci c'erano.

Misurato sulla casa vera il 24/09/2026: `light.taverna_1_taverna_1` e
`light.taverna_2_taverna_2` esistono, sono vive, si chiamano «Taverna 1» e
«Taverna 2» e stanno nell'area Cantina -- nessuna area si chiama «taverna».
`search("taverna")` tornava `nulla_riconosciuto` e il modello rispondeva
«in Home Assistant non c'e' nessuna stanza ne' luce chiamata taverna»: la
frase che `queries.search` dichiara di non voler mai dire. Sia la catena
(qwen3.8-27b) sia il ponte (opus) si arrendevano allo stesso modo, quindi
non era il modello -- era la ricerca.

`Lookup.find()` cerca **i termini dell'indice dentro la frase**: i termini
sono «taverna 1» e «taverna 2», e la frase «taverna» non li contiene.

**Perche' non si allarga `find()`.** `find()` ancora i nomi dentro la
PROSA: «ho pulito la cucina» non deve agganciare le 22 entita' che portano
«cucina» nel nome (misurato sulla casa vera: 869 nomi vivi, «cucina» 22,
«giardino» 28, «luci» 21). Una domanda diretta -- «trovami le cose che si
chiamano taverna» -- e' l'operazione opposta, e fin qui le due
condividevano un meccanismo solo. Si separano alla fonte.
"""
import pytest

from hiris.app.home_space.queries import search
from hiris.app.memory.resolver import costruisci_indice

_CASA = {
    "aree": [{"id": "cantina", "nome": "Cantina", "alias": [], "piano_id": "interrato"},
             {"id": "sala_pranzo", "nome": "Sala da pranzo", "alias": [], "piano_id": "terra"}],
    "entita": [
        {"id": "light.taverna_1", "nome": "Taverna 1", "alias": [], "area_id": "cantina",
         "classe": None, "unita": None},
        {"id": "light.taverna_2", "nome": "Taverna 2", "alias": [], "area_id": "cantina",
         "classe": None, "unita": None},
    ],
    "dispositivi": [], "piani": [], "etichette": [], "categorie": [], "integrazioni": [],
}


@pytest.fixture
def lookup():
    return costruisci_indice(_CASA)


def _trovati(voci) -> set[str]:
    """I riferimenti di tutte le voci, qualunque sia il termine che le ha
    portate: i test qui guardano CHE COSA si trova, non da quale nome."""
    return {riferimento
            for candidati, _termine in voci for _tipo, riferimento in candidati}


def test_la_parola_intera_di_un_nome_composto_trova_le_entita(lookup):
    """Il caso vero, quello che il proprietario ha chiesto alla casa."""
    assert _trovati(lookup.names_containing("taverna")) == {
        "light.taverna_1", "light.taverna_2"}


def test_la_prosa_resta_stretta(lookup):
    """`find()` NON cambia: e' cio' che protegge l'ancoraggio dei ricordi.

    Se questa prova passasse anche con la ricerca larga dentro `find()`,
    «ho pulito la taverna» ancorerebbe un ricordo a due luci.
    """
    assert lookup.find("accendi la luce della taverna") == []


def test_un_pezzo_di_parola_non_e_una_parola(lookup):
    """«tav» non nomina niente: il confine di parola vale anche qui, se no
    la ricerca larga diventa una ricerca per sottostringa e «sala» troverebbe
    «salato»."""
    assert lookup.names_containing("tav") == []


def test_una_parola_in_mezzo_al_nome(lookup):
    """La parola cercata non deve stare all'inizio: «pranzo» e' l'ultima
    parola di «Sala da pranzo»."""
    assert _trovati(lookup.names_containing("pranzo")) == {"sala_pranzo"}


def test_il_nome_intero_non_passa_di_qui(lookup):
    """Un testo che E' gia' un termine intero lo trova `find()`: ripeterlo
    qui darebbe al chiamante la stessa voce due volte."""
    assert lookup.names_containing("cantina") == []


# --------------------------------------------------------------------------
# `search()`: il ripiego, il tetto, e cio' che il ripiego NON deve rubare
# --------------------------------------------------------------------------

def _casa_molte_luci(quante: int, nome: str) -> dict:
    """Una casa con `quante` entita' che portano tutte `nome` nel nome, per
    provare il tetto senza scrivere a mano venti voci."""
    return {
        "aree": [{"id": "a", "nome": "Area", "alias": [], "piano_id": None}],
        "entita": [{"id": f"light.{nome}_{i}", "nome": f"{nome.capitalize()} {i}",
                    "alias": [], "area_id": "a", "classe": None, "unita": None}
                   for i in range(quante)],
        "dispositivi": [], "piani": [], "etichette": [], "categorie": [],
        "integrazioni": [],
    }


def test_search_ripiega_sul_frammento_e_lo_dichiara(lookup):
    """Il caso del proprietario, dallo strumento che il modello chiama."""
    voci = search(lookup, "taverna")
    trovati = {c["riferimento"] for v in voci for c in v["candidati"]}
    assert trovati == {"light.taverna_1", "light.taverna_2"}
    # Il modello deve sapere che ha combaciato una PARTE di un nome, non il
    # nome: e' la differenza fra «si chiama cosi'» e «si chiama cosi' e
    # qualcos'altro», e da essa dipende se puo' agire senza chiedere.
    assert all(v["parte_di_un_nome"] for v in voci)
    # E il nome intero arriva: senza, il modello ha due identificatori e
    # nessun modo di dire al proprietario COSA ha trovato.
    assert {c["nome"] for v in voci for c in v["candidati"]} == {
        "Taverna 1", "Taverna 2"}


def test_il_nome_esatto_non_passa_dal_ripiego(lookup):
    """Quando `find()` trova, il ripiego non si accende: se si accendesse,
    «Cantina» tornerebbe l'area PIU' ogni nome che contiene quella parola,
    e una domanda con risposta esatta diventerebbe ambigua."""
    voci = search(lookup, "Cantina")
    assert [c["riferimento"] for v in voci for c in v["candidati"]] == ["cantina"]
    assert not any("parte_di_un_nome" in v for v in voci)


def test_il_ripiego_ha_un_tetto_e_dice_quando_taglia():
    """Sulla casa vera «reolink» sta in 166 nomi. Versarli tutti nel
    contesto del modello e' il difetto che le misure esistono per evitare;
    tagliare in silenzio sarebbe peggio, perche' il modello direbbe «ne ho
    trovati dodici» di una casa che ne ha 166."""
    lookup = costruisci_indice(_casa_molte_luci(40, "faretto"))
    voci = search(lookup, "faretto")
    tagli = [v for v in voci if "troppi_nomi" in v]
    assert len(tagli) == 1
    assert tagli[0]["troppi_nomi"]["in_tutto"] == 40
    assert tagli[0]["troppi_nomi"]["mostrati"] < 40
    assert tagli[0]["candidati"] == []


def test_senza_tetto_superato_nessuna_dichiarazione(lookup):
    """Una dichiarazione sempre presente smette di essere un segnale: due
    nomi non sono «troppi»."""
    assert not any("troppi_nomi" in v for v in search(lookup, "taverna"))
