from hiris.app.brain.chunking import chunk_text


def test_chunk_text_sizes_and_overlap():
    text = "abcdefghij"  # 10 char
    chunks = chunk_text(text, size=4, overlap=1)
    # passo = size-overlap = 3 → 0:4, 3:7, 6:10, 9:10
    assert chunks[0] == "abcd"
    assert chunks[1] == "defg"
    assert all(len(c) <= 4 for c in chunks)
    assert "".join(c[0] for c in chunks)  # non vuoto


def test_chunk_text_empty():
    assert chunk_text("", size=4, overlap=1) == []
    assert chunk_text("   ", size=4, overlap=1) == []
