"""Ogni opzione dell'add-on ha un'etichetta e una descrizione, in entrambe le lingue.

Il Task 11 della fetta E5 aveva verificato la **parità it/en**, che era vera:
`claude_code_oauth_token` mancava in ENTRAMBE. Era in `config.yaml` fra le
`options` e nello `schema`, ma nel Supervisor si presentava **senza etichetta e
senza descrizione** — ed è il campo che accende il percorso dell'UAT
(abbonamento Claude, nessuna chiave API).

La lezione, e il motivo per cui questo file esiste: la copertura si controlla
**contro `config.yaml`**, non fra le due lingue. Confrontare it con en trova
solo le dimenticanze asimmetriche.
"""
from pathlib import Path

import pytest
import yaml

BASE = Path(__file__).resolve().parents[1] / "hiris"


def _chiavi(albero, prefisso=""):
    """I nomi delle opzioni, anche annidate (`memory.rag_k`)."""
    nomi = []
    for chiave, valore in albero.items():
        nomi.append(prefisso + chiave)
        if isinstance(valore, dict):
            nomi.extend(_chiavi(valore, prefisso + chiave + "."))
    return nomi


def _chiavi_tradotte(albero, prefisso=""):
    """Come sopra, saltando `name`/`description`, che sono i testi non i nomi."""
    nomi = []
    for chiave, valore in albero.items():
        if chiave in ("name", "description"):
            continue
        nomi.append(prefisso + chiave)
        if isinstance(valore, dict):
            nomi.extend(_chiavi_tradotte(valore, prefisso + chiave + "."))
    return nomi


def _opzioni():
    cfg = yaml.safe_load((BASE / "config.yaml").read_text(encoding="utf-8"))
    return set(_chiavi(cfg["options"])), set(_chiavi(cfg["schema"]))


def _traduzioni(lingua):
    testo = (BASE / "translations" / f"{lingua}.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(testo)["configuration"]


@pytest.mark.parametrize("lingua", ["it", "en"])
def test_ogni_opzione_ha_nome_e_descrizione(lingua):
    opzioni, _ = _opzioni()
    tradotte = set(_chiavi_tradotte(_traduzioni(lingua)))
    mancanti = sorted(opzioni - tradotte)
    assert not mancanti, (
        f"in translations/{lingua}.yaml queste opzioni non hanno voce e nel "
        f"Supervisor compaiono senza etichetta ne' descrizione: {mancanti}"
    )


@pytest.mark.parametrize("lingua", ["it", "en"])
def test_nessuna_traduzione_orfana(lingua):
    """Il difetto opposto: un'etichetta per un'opzione che non esiste più."""
    opzioni, _ = _opzioni()
    tradotte = set(_chiavi_tradotte(_traduzioni(lingua)))
    orfane = sorted(tradotte - opzioni)
    assert not orfane, (
        f"translations/{lingua}.yaml descrive opzioni assenti da config.yaml: {orfane}"
    )


def test_options_e_schema_coprono_le_stesse_opzioni():
    """Un'opzione senza schema il Supervisor non la mostra; uno schema senza
    opzione non ha default. Sono lo stesso elenco, e vanno mossi insieme."""
    opzioni, schema = _opzioni()
    assert opzioni == schema, (
        f"solo in options: {sorted(opzioni - schema)}; "
        f"solo in schema: {sorted(schema - opzioni)}"
    )


def test_il_token_dell_abbonamento_e_descritto_in_entrambe_le_lingue():
    """Il caso concreto che ha motivato questo file — il campo che accende
    il percorso UAT. Le due descrizioni devono restare semanticamente
    identiche: qui si pinna che ci siano e che dichiarino entrambe la cosa
    che l'utente deve sapere prima di attivarlo (i consumi non si misurano)."""
    for lingua, atteso in (("it", "non si misurano"), ("en", "not measured")):
        voce = _traduzioni(lingua)["claude_code_oauth_token"]
        assert voce["name"].strip()
        assert atteso.lower() in voce["description"].lower(), (
            f"{lingua}.yaml deve dichiarare che sul percorso abbonamento i "
            "consumi non si misurano: e' la conseguenza principale del campo"
        )


# **G2 della revisione finale, e la sua chiusura definitiva.**
#
# Le dodici opzioni che dalla fetta «la catena diventa l'unica verita'» non
# governavano piu' niente dopo il primo avvio portavano tutte, nella loro
# descrizione, il prefisso «NON HA PIU' EFFETTO»: erano rimaste nello schema un
# rilascio in piu' perche' toglierle subito avrebbe fatto perdere il valore --
# il Supervisor scarta le chiavi fuori schema PRIMA che /data/options.json
# esista -- e un campo che non fa niente e non lo dice e' il difetto 1 della
# specifica, sopravvissuto nel posto dove la fetta non era passata.
#
# Con la versione B (3.0.0) sono uscite TUTTE. La lista di parametri sarebbe
# vuota, e un `parametrize` vuoto non e' un test che passa: e' un test che non
# viene mai eseguito. Il test si e' quindi ROVESCIATO -- da «queste dodici lo
# dichiarano» a «nessuna lo dichiara piu', perche' non ce n'e' piu' nessuna» --
# ed e' un pin piu' forte del precedente: sorveglia anche le opzioni future.
# Il giorno in cui una descrizione tornasse a dire «NON HA PIU' EFFETTO»,
# sarebbe rientrata una decisione in una pagina che deve solo custodire, e
# saremmo daccapo.
_AVVISO = {"it": "NON HA PIU' EFFETTO", "en": "NO LONGER HAS ANY EFFECT"}


def _tutte_le_descrizioni(albero, prefisso=""):
    trovate = []
    for chiave, voce in albero.items():
        if chiave in ("name", "description") or not isinstance(voce, dict):
            continue
        if isinstance(voce.get("description"), str):
            trovate.append((prefisso + chiave, voce["description"]))
        trovate.extend(_tutte_le_descrizioni(voce, prefisso + chiave + "."))
    return trovate


@pytest.mark.parametrize("lingua", ["it", "en"])
def test_nessuna_opzione_rimasta_dichiara_di_non_avere_piu_effetto(lingua):
    """Cio' che resta in questa pagina MORDE.

    Le quattro credenziali, l'indirizzo di Ollama, il tema e le tre voci
    avanzate hanno tutte un effetto vero, e nessuna ha bisogno di scusarsi. Se
    questa formula ricompare, e' ricomparsa un'opzione che l'utente puo'
    cambiare senza che succeda niente -- e stavolta senza la scusa della
    migrazione, che e' finita."""
    colpevoli = [nome for nome, descrizione in _tutte_le_descrizioni(_traduzioni(lingua))
                 if _AVVISO[lingua] in descrizione]
    assert not colpevoli, (
        f"{lingua}.yaml: queste opzioni dichiarano di non avere piu' effetto, "
        f"ma sono ancora nello schema: {colpevoli}. Una decisione e' rientrata "
        "in una pagina che deve solo custodire, oppure un'opzione e' rimasta "
        "indietro rispetto al codice che la leggeva"
    )


@pytest.mark.parametrize("lingua", ["it", "en"])
def test_i_due_campi_inerti_rimasti_dichiarano_di_esserlo(lingua):
    """L'eccezione, e perche' e' un'eccezione e non una dimenticanza.

    I due campi `memory.*` non hanno nessun lettore che faccia qualcosa
    (nessun percorso di HIRIS chiama piu' `embed()`) e sono rimasti
    deliberatamente: toglierli avrebbe fatto perdere il valore salvato in
    cambio di niente, che e' il peggior rapporto costo/beneficio possibile per
    un campo che non fa nulla. Ma un campo inerte va DETTO, e lo dicono con le
    parole del loro caso -- «oggi non fanno niente» -- non con la formula della
    migrazione, che prometterebbe che la decisione si prende da un'altra parte:
    non si prende da nessuna parte."""
    atteso = "non fanno niente" if lingua == "it" else "do nothing today"
    voce = _traduzioni(lingua)["memory"]
    assert atteso in voce["description"].lower(), (
        f"{lingua}.yaml: il blocco degli embedding non dichiara piu' di essere "
        f"inerte. Trovato: {voce['description']!r}"
    )
