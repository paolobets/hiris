from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def test_picker_present():
    js = (BASE / "config" / "agentbot-route.js").read_text(encoding="utf-8")
    assert "api/entities" in js and "device_class=temperature" in js


def test_entity_search_consumers_read_canonical_shape():
    """I consumatori devono leggere data.entities/entity_id, non un array piatto.

    Regression per il bug SP-4 Fase B Task 1: chatbot-editor.js e permessi.js
    leggevano `items.length` su un oggetto `{entities: [...]}` -> undefined
    -> early-return -> il dropdown di ricerca entità non appariva mai.
    """
    for fname in ("config/chatbot-editor.js", "config/permessi.js", "config/agentbot-route.js"):
        js = (BASE / fname).read_text(encoding="utf-8")
        if "api/entities" not in js:
            continue
        assert "entities" in js, f"{fname} non legge data.entities"
        assert "entity_id" in js, f"{fname} non legge entity_id"
