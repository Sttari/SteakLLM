import json

from steakllm_common.logging import bound, configure, event_fields, get_logger


def lines(capsys) -> list[dict]:
    return [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]


def test_one_json_object_per_line_with_the_standard_keys(capsys):
    configure("tester")
    get_logger("x").info("hello", chunk_count=5)
    (line,) = lines(capsys)
    assert {"ts", "level", "service", "msg"} <= set(line)
    assert line["service"] == "tester" and line["level"] == "info" and line["msg"] == "hello"
    assert line["chunk_count"] == 5
    assert line["ts"].endswith("Z")


def test_bound_ids_ride_along_and_nest(capsys):
    configure("tester")
    log = get_logger("x")
    with bound(doc_id="d1", trace_id="t1"):
        log.info("outer")
        with bound(event_id="e1"):
            log.info("inner")
        log.info("outer again")
    log.info("outside")
    outer, inner, again, outside = lines(capsys)
    assert outer["doc_id"] == "d1" and "event_id" not in outer
    assert inner["event_id"] == "e1" and inner["trace_id"] == "t1"
    assert "event_id" not in again
    assert "doc_id" not in outside


def test_event_fields_picks_the_four_ids():
    ev = {"id": "e", "type": "SummaryReady", "doc_id": "d", "trace_id": "t", "data": {"x": 1}}
    assert event_fields(ev) == {
        "event_id": "e",
        "event_type": "SummaryReady",
        "doc_id": "d",
        "trace_id": "t",
    }


def test_exception_is_summarised_not_dumped(capsys):
    configure("tester")
    log = get_logger("x")
    try:
        raise ValueError("boom")
    except ValueError:
        log.error("failed", exc_info=True)
    (line,) = lines(capsys)
    assert line["exc"] == "ValueError: boom"
