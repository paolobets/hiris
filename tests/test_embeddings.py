"""I provider di embedding, e **cosa l'immagine si porta dentro per loro**.

Reperto D-2 del registro dei rischi (`docs/design/2026-09-21-sicurezza-esposizioni.md`),
chiuso il 22/09/2026.

**Il percorso degli embedding e' DICHIARATO INERTE** dalla fetta «esce il
documentale»: nessun codice di HIRIS chiama piu' `embed()`. I tre ultimi
chiamanti -- ingest documentale, digest storico, coda di approvazione della
conoscenza -- sono usciti insieme, e «se e quando accendere i vettori» e' una
decisione esplicitamente rimandata.

I provider restano, perche' quella decisione e' del proprietario e la pagina
Modelli li mostra gia'. **Le librerie no.** `model2vec` era una dipendenza di
produzione -- installata nell'immagine dell'add-on, a casa di chi usa HIRIS --
e si tirava dietro **quindici pacchetti su quarantanove**: `numpy`,
`tokenizers`, `safetensors`, `huggingface-hub`, `hf-xet`, `joblib`, `fsspec`,
`filelock`, `jinja2`, `markupsafe`, `tqdm`, `cloudpickle` e il resto del loro
albero. Quindici alberi da sorvegliare per le vulnerabilita', in cambio di zero
funzioni.

Misurato, non stimato: `pip-audit -r hiris/requirements.txt` risolveva
**49 pacchetti** con `model2vec`, **34** senza.

**La forma della decisione**: i due provider locali diventano tutti e due
opzionali, e degradano allo stesso modo -- `NullEmbedder` piu' una frase che
dice cosa fare. Era gia' cosi' per `fastembed`, importato e mai dichiarato;
adesso i due si somigliano invece di essere due casi diversi per caso.
"""
import pathlib
import re
import sys

import pytest

from hiris.app.backends import embeddings

RADICE = pathlib.Path(__file__).resolve().parents[1]


def _produzione() -> dict[str, str]:
    """I pacchetti che l'immagine installa — **letti, non ricopiati**."""
    righe = (RADICE / "hiris" / "requirements.txt").read_text(encoding="utf-8")
    return {re.split(r"[><=]", r.strip())[0].strip(): r.strip()
            for r in righe.splitlines()
            if r.strip() and not r.strip().startswith("#")}


# --- cosa l'immagine si porta dentro ----------------------------------------

def test_l_immagine_NON_si_porta_dentro_le_librerie_di_un_percorso_inerte():
    """**Il cancello di D-2.**

    Una dipendenza di produzione e' peso che gira a casa di chi usa HIRIS: si
    aggiorna, si sorveglia, e un suo difetto diventa un difetto nostro. Per un
    percorso che nessuno chiama, quel peso e' tutto costo.

    Mutazione ESEGUITA: rimesso `model2vec` in `requirements.txt` -- rossa.
    """
    dentro = _produzione()

    for libreria in ("model2vec", "fastembed"):
        assert libreria not in dentro, (
            f"«{libreria}» e' tornata fra le dipendenze di produzione. Il "
            "percorso degli embedding e' inerte: se si accende, la decisione "
            "si prende e si scrive -- non si reinstalla la libreria di "
            "nascosto")


def test_e_le_dipendenze_che_restano_sono_QUELLE_CHE_SERVONO():
    """La contropartita: togliere non e' la proprieta' che si vuole. Se
    domani sparisse `cryptography`, le firme dei servizi smetterebbero di
    funzionare e questo cancello resterebbe muto.

    Mutazione: togliere `cryptography` da `requirements.txt` -- rossa.
    """
    dentro = _produzione()

    for necessaria in ("aiohttp", "anthropic", "apscheduler", "cryptography",
                       "httpx", "openai", "pyyaml"):
        assert necessaria in dentro, f"manca «{necessaria}»"


def test_nessuna_dipendenza_di_SVILUPPO_finisce_nell_immagine():
    """Il Dockerfile installa solo `requirements.txt`: se una libreria di
    prova ci finisse dentro, l'add-on porterebbe a casa di qualcuno un albero
    che serve solo a noi.

    Mutazione: mettere `pytest` in `requirements.txt` -- rossa."""
    dentro = _produzione()

    for solo_nostra in ("pytest", "pytest-asyncio", "pytest-aiohttp", "ruff"):
        assert solo_nostra not in dentro, f"«{solo_nostra}» e' finita in produzione"


# --- e come degradano i due provider locali ---------------------------------

@pytest.mark.parametrize("provider,libreria", [("model2vec", "model2vec"),
                                               ("fastembed", "fastembed")])
def test_un_provider_locale_SENZA_la_sua_libreria_non_fa_cadere_l_avvio(
        provider, libreria, monkeypatch, caplog):
    """Chi ha scelto uno dei due provider nelle opzioni e aggiorna l'add-on si
    ritrova la libreria che non c'e' piu'. **Non deve trovarsi l'add-on che
    non parte**: si ripiega su `NullEmbedder`, che e' cio' che il percorso
    inerte faceva comunque.

    Mutazione ESEGUITA: lasciar propagare l'`ImportError` -- rossa (l'add-on
    non parte per un percorso che nessuno chiama)."""
    monkeypatch.setitem(sys.modules, libreria, None)

    with caplog.at_level("WARNING"):
        scelto = embeddings.build_embedding_provider(provider=provider, model="")

    assert isinstance(scelto, embeddings.NullEmbedder)


@pytest.mark.parametrize("provider", ["model2vec", "fastembed"])
def test_e_il_registro_dice_COSA_FARE_invece_di_dire_solo_che_manca(
        provider, monkeypatch, caplog):
    """Un avviso che dice «non installata» manda a cercare. Questo dice perche'
    non c'e' -- il percorso e' inerte -- e quali provider funzionano davvero.

    Mutazione: registrare «libreria mancante» e basta -- rossa."""
    monkeypatch.setitem(sys.modules, provider, None)

    with caplog.at_level("WARNING"):
        embeddings.build_embedding_provider(provider=provider, model="")

    detto = caplog.text.lower()
    assert "inerte" in detto or "nessun" in detto, (
        f"l'avviso non dice perche' la libreria non c'e': {caplog.text!r}")
    assert "openai" in detto and "ollama" in detto, (
        "l'avviso non dice quali provider funzionano davvero")


def test_i_due_provider_locali_degradano_allo_STESSO_modo():
    """Erano due casi diversi per caso: `fastembed` si difendeva
    dall'`ImportError`, `model2vec` no -- perche' l'uno era dichiarato e
    l'altro no. Adesso sono la stessa cosa, e la forma lo dice.

    Mutazione: difendere uno solo dei due -- rossa."""
    import inspect

    sorgente = inspect.getsource(embeddings.build_embedding_provider)

    assert sorgente.count("ImportError") == 2, (
        "i due provider locali non si difendono nello stesso modo: uno dei "
        "due fara' cadere l'avvio il giorno in cui la sua libreria non c'e'")


def test_i_provider_che_NON_hanno_bisogno_di_niente_restano_intatti():
    """`openai` e `ollama` parlano con un servizio, non con una libreria
    locale: non hanno niente da importare e non devono degradare.

    Mutazione: ripiegare su `NullEmbedder` anche per loro -- rossa (chi ha
    acceso i vettori con OpenAI li perderebbe in silenzio)."""
    via_openai = embeddings.build_embedding_provider(
        provider="openai", model="", openai_api_key="sk-finta")
    via_ollama = embeddings.build_embedding_provider(
        provider="ollama", model="",
        local_model_url="http://127.0.0.1:11434")

    assert not isinstance(via_openai, embeddings.NullEmbedder)
    assert not isinstance(via_ollama, embeddings.NullEmbedder)
