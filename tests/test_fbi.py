import argparse
from unittest.mock import MagicMock

import pytest
import requests

import FBI


def make_response(json_data=None, raise_status=False, bad_json=False):
    resp = MagicMock()
    if raise_status:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError("500")
    else:
        resp.raise_for_status.return_value = None
    if bad_json:
        resp.json.side_effect = ValueError("bad json")
    else:
        resp.json.return_value = json_data
    return resp


def test_fetch_page_success():
    session = MagicMock()
    session.get.return_value = make_response({"total": 1, "items": []})
    result = FBI.fetch_page(session, 1, 20)
    assert result == {"total": 1, "items": []}
    session.get.assert_called_once()


def test_fetch_page_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(FBI.time, "sleep", lambda _s: None)
    session = MagicMock()
    err = requests.exceptions.ConnectionError("boom")
    session.get.side_effect = [err, err, err, make_response({"items": []})]
    result = FBI.fetch_page(session, 1, 20, retries=3)
    assert result == {"items": []}
    assert session.get.call_count == 4  # 3 failed attempts + success on the 4th


def test_fetch_page_returns_none_after_retries(monkeypatch):
    monkeypatch.setattr(FBI.time, "sleep", lambda _s: None)
    session = MagicMock()
    session.get.side_effect = requests.exceptions.ConnectionError("boom")
    result = FBI.fetch_page(session, 1, 20, retries=2)
    assert result is None
    assert session.get.call_count == 3  # initial attempt + 2 retries


def test_fetch_page_skips_on_bad_json(monkeypatch):
    monkeypatch.setattr(FBI.time, "sleep", lambda _s: None)
    session = MagicMock()
    session.get.return_value = make_response(bad_json=True)
    result = FBI.fetch_page(session, 1, 20, retries=1)
    assert result is None
    assert session.get.call_count == 2


@pytest.mark.parametrize(
    "total,size,expected",
    [(999, 20, 50), (1000, 20, 50), (1001, 20, 51), (0, 20, 0), (1, 20, 1)],
)
def test_compute_total_pages(total, size, expected):
    assert FBI.compute_total_pages(total, size) == expected


def test_compute_total_pages_respects_cap():
    assert FBI.compute_total_pages(1000, 20, max_pages=5) == 5


def test_compute_total_pages_cap_above_total_is_ignored():
    assert FBI.compute_total_pages(40, 20, max_pages=10) == 2


def _cfg(**kw):
    base = dict(output="FBI.html", page_size=2, max_pages=None, delay=0, verbose=False)
    base.update(kw)
    return argparse.Namespace(**base)


def test_iter_all_items_spans_pages(monkeypatch):
    monkeypatch.setattr(FBI.time, "sleep", lambda _s: None)
    pages = {
        1: {"total": 3, "items": [{"title": "a"}, {"title": "b"}]},
        2: {"total": 3, "items": [{"title": "c"}]},
    }
    monkeypatch.setattr(FBI, "fetch_page", lambda s, page, ps, **k: pages.get(page))
    items = list(FBI.iter_all_items(None, _cfg(page_size=2)))
    assert [i["title"] for i in items] == ["a", "b", "c"]


def test_iter_all_items_stops_when_first_page_fails(monkeypatch):
    monkeypatch.setattr(FBI, "fetch_page", lambda s, page, ps, **k: None)
    items = list(FBI.iter_all_items(None, _cfg()))
    assert items == []


def test_iter_all_items_skips_failed_middle_page(monkeypatch):
    monkeypatch.setattr(FBI.time, "sleep", lambda _s: None)
    pages = {
        1: {"total": 6, "items": [{"title": "a"}, {"title": "b"}]},
        2: None,  # failed page -> skipped
        3: {"total": 6, "items": [{"title": "e"}, {"title": "f"}]},
    }
    monkeypatch.setattr(FBI, "fetch_page", lambda s, page, ps, **k: pages.get(page))
    items = list(FBI.iter_all_items(None, _cfg(page_size=2)))
    assert [i["title"] for i in items] == ["a", "b", "e", "f"]


def test_iter_all_items_respects_max_pages(monkeypatch):
    monkeypatch.setattr(FBI.time, "sleep", lambda _s: None)
    pages = {
        1: {"total": 100, "items": [{"title": "a"}]},
        2: {"total": 100, "items": [{"title": "b"}]},
    }
    monkeypatch.setattr(FBI, "fetch_page", lambda s, page, ps, **k: pages.get(page))
    items = list(FBI.iter_all_items(None, _cfg(page_size=1, max_pages=2)))
    assert [i["title"] for i in items] == ["a", "b"]


def test_compute_total_pages_rejects_nonpositive_page_size():
    with pytest.raises(ValueError):
        FBI.compute_total_pages(100, 0)


def test_iter_all_items_handles_total_zero(monkeypatch):
    monkeypatch.setattr(FBI.time, "sleep", lambda _s: None)
    monkeypatch.setattr(FBI, "fetch_page", lambda s, page, ps, **k: {"total": 0, "items": []})
    items = list(FBI.iter_all_items(None, _cfg()))
    assert items == []


def test_iter_all_items_handles_null_total(monkeypatch):
    monkeypatch.setattr(FBI.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        FBI,
        "fetch_page",
        lambda s, page, ps, **k: {"total": None, "items": [{"title": "a"}]} if page == 1 else None,
    )
    items = list(FBI.iter_all_items(None, _cfg()))
    assert [i["title"] for i in items] == ["a"]


def test_render_record_full():
    item = {
        "title": "John Doe",
        "path": "https://www.fbi.gov/wanted/x",
        "subjects": ["Murder"],
        "caution": "<p>Armed and dangerous</p>",
    }
    html = FBI.render_record(item)
    assert html.startswith("<article>")
    assert html.endswith("</article>")
    assert "John Doe" in html
    assert "https://www.fbi.gov/wanted/x" in html
    assert "Murder" in html
    assert "Armed and dangerous" in html
    assert "<h2>John Doe</h2>" in html
    assert 'href="https://www.fbi.gov/wanted/x"' in html


def test_render_record_missing_caution_has_no_none():
    item = {"title": "Jane", "path": "https://y", "subjects": ["Fraud"]}
    html = FBI.render_record(item)
    assert "Jane" in html
    assert "None" not in html


def test_render_record_missing_subjects_omits_section():
    item = {"title": "Sam", "path": "https://z"}
    html = FBI.render_record(item)
    assert "Sam" in html
    assert "Subjects" not in html
    assert "[]" not in html


def test_render_record_empty_returns_empty_string():
    assert FBI.render_record({}) == ""


def test_render_record_strips_empty_caution_paragraphs():
    item = {"title": "T", "caution": "<p>Real</p><p> </p>"}
    html = FBI.render_record(item)
    assert "Real" in html
    assert "<p> </p>" not in html


def test_render_record_escapes_title():
    out = FBI.render_record({"title": "John & <b>Jane</b>"})
    assert "&amp;" in out
    assert "<b>Jane</b>" not in out


def test_render_record_escapes_path_quote():
    out = FBI.render_record({"title": "T", "path": 'https://x"onmouseover=1'})
    assert "&quot;" in out
    assert '"onmouseover' not in out


def test_render_record_skips_none_subjects():
    out = FBI.render_record({"title": "T", "subjects": ["Murder", None, "Fraud"]})
    assert "Murder, Fraud" in out
    assert "None" not in out


def test_render_record_strips_empty_paragraphs_between_content():
    out = FBI.render_record({"title": "T", "caution": "<p>Real</p><p>  </p><p>More</p>"})
    assert "Real" in out
    assert "More" in out
    assert "<p>  </p>" not in out
