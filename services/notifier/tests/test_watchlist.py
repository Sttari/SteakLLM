"""load_watch_list: the settings list by default; the table's `term` items when configured."""

from __future__ import annotations

from steakllm_common.settings import Settings

from steakllm_notifier.main import load_watch_list


def _settings(**kw) -> Settings:
    return Settings(documents_bucket="b", catalog_table="t", **kw)


class FakeTable:
    def __init__(self, pages):
        self.pages = list(pages)

    def scan(self, **kw):
        page = self.pages.pop(0)
        out = {"Items": [{"term": t} for t in page]}
        if self.pages:
            out["LastEvaluatedKey"] = {"term": page[-1]}
        return out


def test_without_a_table_the_settings_list_is_used():
    s = _settings(watch_list=["gpu", "steak"])
    assert load_watch_list(s) == ["gpu", "steak"]


def test_with_a_table_its_terms_replace_the_list_and_pages_are_followed():
    s = _settings(watch_list=["ignored"], watchlist_table="steakllm-watchlist")
    table = FakeTable([["steak", "gpu"], ["kafka", "steak"]])
    assert load_watch_list(s, table) == ["gpu", "kafka", "steak"]
