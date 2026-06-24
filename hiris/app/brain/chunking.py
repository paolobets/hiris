from __future__ import annotations


def chunk_text(text: str, *, size: int = 800, overlap: int = 100) -> list[str]:
    """Spezza `text` in finestre di `size` caratteri con `overlap` di sovrapposizione.
    Passo = max(1, size - overlap). Ritorna [] per testo vuoto/whitespace."""
    if not text or not text.strip():
        return []
    if size <= 0:
        return [text]
    step = max(1, size - max(0, overlap))
    chunks: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        chunks.append(text[i:i + size])
        if i + size >= n:
            break
        i += step
    return chunks
