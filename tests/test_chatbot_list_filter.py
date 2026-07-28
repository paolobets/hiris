from pathlib import Path
BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def test_no_filter_on_nonexistent_type_field():
    """Chatbot non ha piu' il campo `type` (Slice 5): filtrarci svuota le liste."""
    for fname in ("index.html", "hiris-chat-card.js"):
        js = (BASE / fname).read_text(encoding="utf-8")
        assert "type === 'chat'" not in js, f"{fname} filtra su un campo inesistente"
        assert 'type === "chat"' not in js, f"{fname} filtra su un campo inesistente"
