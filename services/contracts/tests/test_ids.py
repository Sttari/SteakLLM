"""The idempotency rules hold, and their exact outputs are frozen (known-answer tests)."""

import io
import uuid

import pytest

from steakllm_contracts.ids import POINT_NAMESPACE, doc_id, doc_id_from_stream, point_id

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_same_bytes_same_doc_id():
    assert doc_id(b"hello steak") == doc_id(b"hello steak")


def test_different_bytes_different_doc_id():
    assert doc_id(b"hello steak") != doc_id(b"hello steaK")


def test_doc_id_known_answer():
    # sha256("") — a published constant; if this changes, the hash function changed.
    assert doc_id(b"") == EMPTY_SHA256


def test_stream_matches_bytes():
    data = bytes(range(256)) * 5000  # 1.28 MB, crosses the 1 MiB read boundary
    assert doc_id_from_stream(io.BytesIO(data), chunk_size=1 << 20) == doc_id(data)


def test_point_id_is_deterministic_and_a_uuid5():
    d = doc_id(b"a document")
    a, b = point_id(d, 7), point_id(d, 7)
    assert a == b
    assert uuid.UUID(a).version == 5


def test_point_id_differs_per_chunk_and_per_document():
    d1, d2 = doc_id(b"one"), doc_id(b"two")
    assert point_id(d1, 0) != point_id(d1, 1)
    assert point_id(d1, 0) != point_id(d2, 0)


def test_point_id_known_answer():
    # Frozen. If this fails, POINT_NAMESPACE or the name format changed: every stored vector
    # would be re-keyed. That is a v2 contract, not a refactor.
    assert POINT_NAMESPACE == uuid.UUID("f4e0d6a9-4c1d-5a7b-9e3f-2b8c1d0e5a67")
    assert point_id(EMPTY_SHA256, 0) == "3e9b3f98-b9d1-5349-93ac-43bb4a49edee"


@pytest.mark.parametrize("bad", ["", "abc", "A" * 64, "z" * 64])
def test_point_id_rejects_bad_doc_id(bad):
    with pytest.raises(ValueError, match="64 lowercase hex"):
        point_id(bad, 0)


def test_point_id_rejects_negative_chunk():
    with pytest.raises(ValueError, match=">= 0"):
        point_id(EMPTY_SHA256, -1)
