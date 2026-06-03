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
