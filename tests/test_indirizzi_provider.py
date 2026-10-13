"""Gli indirizzi dei provider hanno una casa sola: `Provider.api_base` (F-09).

Fino alla Chiusura dello sprint (F5, 13/10/2026) l'indirizzo di ogni provider
era scritto in linea dove serviva -- tre volte in `api/handlers_models.py`, in
`backends/openrouter_runner.py`, nell'avvio -- accanto a un `Provider.host`
scritto a mano che doveva dire la stessa cosa. Adesso `host` si chiede
all'indirizzo, e l'indirizzo vive nella tabella dei provider.

Gli indirizzi da cercare si CHIEDONO alla tabella, non si ricopiano qui.
"""
import ast
import pathlib

from hiris.app import providers

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "hiris" / "app"

#: Lista di AMMISSIONE: i moduli che scrivono ancora un indirizzo di provider
#: fuori dalla tabella. Non sono di questa fetta (la tabella «Chi possiede
#: cosa» della Chiusura): la modifica e' in una patch per il loro padrone, e
#: la riga esce con lei.
AMMESSI: dict[str, str] = {
    "server.py": (
        "il `base_url` di OpenAI nell'avvio: `server.py` e' fermo fino a F8, "
        "patch in chiusura/f5-patch (F-09)"),
}


def _bases() -> set[str]:
    return {p.api_base for p in providers.all_providers() if p.api_base}


def literal_addresses() -> dict[str, list[str]]:
    """`{modulo: [letterali]}`: le stringhe del prodotto che cominciano con
    l'indirizzo di un provider, fuori da `providers.py`."""
    bases = _bases()
    found: dict[str, list[str]] = {}
    for path in sorted(APP.rglob("*.py")):
        module = path.relative_to(APP).as_posix()
        if module == "providers.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        hits = [node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
                and any(node.value.startswith(base) for base in bases)]
        if hits:
            found[module] = hits
    return found


def test_tre_provider_hanno_un_indirizzo_e_l_ospite_ne_discende():
    """La derivazione non e' vuota, e `host` dice il vero."""
    by_id = {p.id: p for p in providers.all_providers()}
    assert by_id["claude"].host == "api.anthropic.com"
    assert by_id["openai"].host == "api.openai.com"
    assert by_id["openrouter"].host == "openrouter.ai"
    assert len(_bases()) == 3


def test_nessun_indirizzo_di_provider_fuori_dalla_tabella():
    """Mutazione ESEGUITA (13/10/2026): rimesso in `api/handlers_models.py`
    l'indirizzo letterale `"https://api.openai.com/v1/models"` -- rossa, e
    nomina il modulo."""
    extra = sorted(set(literal_addresses()) - set(AMMESSI))
    assert not extra, (
        f"{extra} scrivono l'indirizzo di un provider: si chiede a "
        "`Provider.api_base`")


def test_ogni_ammissione_e_ancora_vera():
    stale = sorted(set(AMMESSI) - set(literal_addresses()))
    assert not stale, f"{stale} non scrivono piu' indirizzi: togli l'ammissione"


def test_i_modelli_che_hiris_prezza_da_se_hanno_un_listino():
    """I prezzi restano in `backends/pricing.PRICING`, per MODELLO e non per
    provider, e si legano alla tabella per identificatore (fondamenta 2). Il
    legame si prova: un modello che la tabella offre -- l'automatico o la
    riserva -- di un provider il cui costo HIRIS calcola dal listino (Claude
    API, OpenAI; OpenRouter dichiara il suo) ha il suo prezzo, o il suo costo
    uscirebbe `null`.

    Mutazione ESEGUITA (13/10/2026): `gpt-4.1-mini` tolto da `PRICING` --
    rossa, e nomina il modello."""
    from hiris.app.backends.pricing import prezzo_noto
    listino = (providers.get("claude"), providers.get("openai"))
    senza = sorted(m for p in listino for m in (p.auto_model, *p.reserve_models)
                   if m and not prezzo_noto(m))
    assert not senza, f"modelli offerti senza listino: {senza}"
