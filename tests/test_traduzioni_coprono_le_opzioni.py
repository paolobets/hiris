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
