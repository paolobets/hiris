from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "hiris" / "app" / "static"


def test_no_filter_on_nonexistent_type_field():
    """Chatbot non ha piu' il campo `type` (Slice 5): filtrarci svuota le liste."""
    # fetta E5 Task 5: la card Lovelace e' uscita dal prodotto, quindi
    # `hiris-chat-card.js` non e' piu' fra i file da guardare -- il test
    # falliva per costruzione (FileNotFoundError), verificato prima di
    # potarlo. Resta `index.html`: il soggetto e' vivo.
    for fname in ("index.html",):
        js = (BASE / fname).read_text(encoding="utf-8")
        assert "type === 'chat'" not in js, f"{fname} filtra su un campo inesistente"
        assert 'type === "chat"' not in js, f"{fname} filtra su un campo inesistente"
