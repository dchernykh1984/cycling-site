from agent.chunk import split_source_text, split_text


def test_split_text_returns_whole_when_it_fits():
    assert split_text("aaa\nbbb\n", 100) == ["aaa\nbbb\n"]


def test_split_text_breaks_on_line_boundaries_and_is_lossless():
    text = "aaa\nbbb\nccc\n"  # 4 chars per line
    chunks = split_text(text, 8)
    assert chunks == ["aaa\nbbb\n", "ccc\n"]
    assert "".join(chunks) == text  # never loses or duplicates a row


def test_split_text_keeps_an_overlong_line_whole():
    assert split_text("x" * 30, 10) == ["x" * 30]  # no line boundary -> not cut mid-row


def test_split_source_text_repeats_links_block_in_every_chunk():
    text = "row1\nrow2\nrow3" + "\n\nLinks on the page:\n" + "https://a.kz/1\nhttps://a.kz/2"
    chunks = split_source_text(text, 6)  # ~one row per chunk
    assert len(chunks) >= 2
    assert all("Links on the page:" in c and "https://a.kz/1" in c for c in chunks)
    assert all(c.startswith("row") for c in chunks)  # each chunk still carries body rows


def test_split_source_text_without_links_just_chunks_the_body():
    assert split_source_text("aaa\nbbb\nccc\n", 8) == ["aaa\nbbb\n", "ccc\n"]
