from pathlib import Path

import pytest

from steakllm_common.text import chunk, extract_text

SAMPLE = Path(__file__).resolve().parents[3] / "compose" / "sample" / "quarterly-report.pdf"


def test_pdf_text_extracts():
    text = extract_text(SAMPLE.read_bytes(), "application/pdf")
    assert "Ferrous Foods" in text and "EMEA" in text


def test_markdown_and_plain_decode():
    assert extract_text(b"# hi\n", "text/markdown; charset=utf-8") == "# hi\n"
    assert extract_text(b"caf\xc3\xa9", "text/plain") == "café"


def test_unsupported_type_raises():
    with pytest.raises(ValueError, match="unsupported"):
        extract_text(b"MZ", "application/octet-stream")


def test_chunks_overlap_and_cover_everything():
    text = "".join(chr(97 + i % 26) for i in range(1000))  # abc…zabc…
    pieces = chunk(text, size=400, overlap=80)
    assert len(pieces) == 3
    assert pieces[0] == text[:400] and pieces[1] == text[320:720] and pieces[2] == text[640:]
    assert pieces[0][-80:] == pieces[1][:80]  # the overlap is shared text


def test_chunking_is_deterministic_and_drops_empties():
    text = "  hello world  \n\n" + " " * 500 + "tail"
    a, b = chunk(text, 10, 2), chunk(text, 10, 2)
    assert a == b and all(p.strip() == p and p for p in a)


def test_short_text_is_one_chunk_and_empty_is_none():
    assert chunk("short", 400, 80) == ["short"]
    assert chunk("   ", 400, 80) == []


def test_bad_parameters_raise():
    with pytest.raises(ValueError):
        chunk("x", 0, 0)
    with pytest.raises(ValueError):
        chunk("x", 10, 10)
