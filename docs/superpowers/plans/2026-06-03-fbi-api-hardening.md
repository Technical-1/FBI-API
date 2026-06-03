# FBI-API Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor `FBI.py` from a fragile flat script into a resilient, testable module that reliably fetches the full FBI Most Wanted list and renders it as valid, structured HTML.

**Architecture:** Decompose into pure, independently-testable functions (`parse_args`, `fetch_page`, `compute_total_pages`, `iter_all_items`, `render_record`, `build_document`, `write_output`, `main`). Network access is isolated in `fetch_page`/`iter_all_items` with retry/backoff; parsing and rendering are pure functions over dicts; I/O is a single `with`-managed write. A pytest suite mocks the HTTP session so no test hits the network.

**Tech Stack:** Python 3.8+, `requests`, `argparse`, `logging`, `pytest` (with `unittest.mock` + `monkeypatch`).

**Spec:** `docs/superpowers/specs/2026-06-03-fbi-api-hardening-design.md`

---

## Delivery Model (applies to every bucket)

Each bucket is a **stacked branch**:

- Bucket 1 branches off `main`; PR targets `main`.
- Bucket N (N>1) branches off bucket N-1's branch; PR targets bucket N-1's branch (retargeted to `main` as bases merge).

Per-bucket cycle:
1. Create the bucket branch (stacked on previous).
2. Implementer agent executes the bucket's tasks (TDD steps below).
3. **Reviewer agent** reviews the bucket diff.
4. **Fix all reviewer followups on the branch before opening the PR.**
5. Push, open PR (base = branch below).
6. Merge after reviewer passes + followups done.
7. Resolve the bucket's Project Hub tasks (project 88) and log work.

**Guardrails:** Before every commit, confirm `git config user.email` is `51518860+Technical-1@users.noreply.github.com` or `jacobrk2001@gmail.com`. **No** Claude/AI attribution anywhere in commits or PRs.

**File structure (final state):**

| File | Responsibility |
|------|----------------|
| `FBI.py` | The module: CLI, fetch, pagination, rendering, output, `main` |
| `requirements.txt` | Pin `requests` |
| `tests/test_fbi.py` | Pytest suite (mocked session, pure-function tests) |
| `docs/superpowers/specs/2026-06-03-fbi-api-hardening-design.md` | Design spec (committed on Bucket 1 branch) |

> **Note on the current file:** `FBI.py` will be substantially rewritten. The first implementation step replaces the flat top-level code with the module skeleton. Do not preserve the old top-level `for` loop.

---

## Bucket 1 — Network Resilience

**Hub tasks:** #2 (error handling + status check), #6 (timeout), plus supporting: `requirements.txt`, logging setup.
**Branch:** `bucket-1-network-resilience` off `main`.

### Task 1.1: Branch setup, requirements.txt, commit spec

**Files:**
- Create: `requirements.txt`
- Commit (already in tree): `docs/superpowers/specs/2026-06-03-fbi-api-hardening-design.md`

- [ ] **Step 1: Create the branch**

```bash
git checkout main && git pull --ff-only 2>/dev/null; git checkout -b bucket-1-network-resilience
```

- [ ] **Step 2: Verify commit identity**

Run: `git config user.email`
Expected: `51518860+Technical-1@users.noreply.github.com` or `jacobrk2001@gmail.com`. If not, `git config user.email 51518860+Technical-1@users.noreply.github.com`.

- [ ] **Step 3: Create requirements.txt**

```
requests>=2.31
```

- [ ] **Step 4: Commit spec + requirements**

```bash
git add docs/superpowers/specs/2026-06-03-fbi-api-hardening-design.md requirements.txt
git commit -m "chore: add hardening spec and requirements.txt"
```

### Task 1.2: Module skeleton + `fetch_page`

**Files:**
- Modify (full rewrite of top-level): `FBI.py`
- Create: `tests/test_fbi.py`

- [ ] **Step 1: Write the failing tests for fetch_page**

Create `tests/test_fbi.py`:

```python
from unittest.mock import MagicMock

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
    session.get.side_effect = [err, err, make_response({"items": []})]
    result = FBI.fetch_page(session, 1, 20, retries=3)
    assert result == {"items": []}
    assert session.get.call_count == 3


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fbi.py -v`
Expected: FAIL — `AttributeError: module 'FBI' has no attribute 'fetch_page'` (and no `FBI.time`).

- [ ] **Step 3: Write the module skeleton + fetch_page**

Replace the entire contents of `FBI.py` with:

```python
"""Fetch the FBI Most Wanted list and render it as an HTML page."""

import argparse
import logging
import math
import sys
import time

import requests

API_URL = "https://api.fbi.gov/wanted/v1/list"
USER_AGENT = "FBI-API-scraper/1.0 (+https://github.com/Technical-1/FBI-API)"
DEFAULT_OUTPUT = "FBI.html"
DEFAULT_PAGE_SIZE = 20
DEFAULT_TIMEOUT = 15
DEFAULT_RETRIES = 3
DEFAULT_DELAY = 0.25

logger = logging.getLogger("fbi")


def fetch_page(session, page, page_size, timeout=DEFAULT_TIMEOUT, retries=DEFAULT_RETRIES):
    """Fetch one page of results, retrying on failure. Returns parsed JSON or None."""
    for attempt in range(retries + 1):
        try:
            resp = session.get(
                API_URL,
                params={"page": page, "pageSize": page_size},
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.warning("Page %d attempt %d/%d failed: %s", page, attempt + 1, retries + 1, exc)
            if attempt < retries:
                time.sleep(2 ** attempt)
    logger.error("Page %d failed after %d attempts; skipping", page, retries + 1)
    return None
```

Note: `json.JSONDecodeError` subclasses `ValueError`, so the `ValueError` catch covers malformed-JSON bodies.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fbi.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add FBI.py tests/test_fbi.py
git commit -m "feat: add resilient fetch_page with timeout and retry/backoff"
```

### Bucket 1 completion

- [ ] Run reviewer agent on the `bucket-1-network-resilience` diff.
- [ ] Fix all reviewer followups on the branch; record them for the final summary.
- [ ] `git push -u origin bucket-1-network-resilience` and open PR (base `main`).
- [ ] After reviewer passes: merge PR.
- [ ] Resolve Hub tasks #2, #6, and the `requirements.txt` task; log work.

---

## Bucket 2 — Pagination & Coverage

**Hub tasks:** #1 (off-by-one), #7 (derive page count from total), plus logging woven into the fetch loop.
**Branch:** `bucket-2-pagination` off `bucket-1-network-resilience`.

### Task 2.1: `compute_total_pages`

**Files:**
- Modify: `FBI.py`
- Modify: `tests/test_fbi.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fbi.py`:

```python
import pytest


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fbi.py -k compute_total_pages -v`
Expected: FAIL — `AttributeError: module 'FBI' has no attribute 'compute_total_pages'`.

- [ ] **Step 3: Implement compute_total_pages**

Add to `FBI.py` after `fetch_page`:

```python
def compute_total_pages(total, page_size, max_pages=None):
    """Number of pages needed for `total` items at `page_size`, optionally capped."""
    pages = math.ceil(total / page_size) if total > 0 else 0
    if max_pages is not None:
        pages = min(pages, max_pages)
    return pages
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fbi.py -k compute_total_pages -v`
Expected: PASS (7 passed — 5 parametrized + 2).

- [ ] **Step 5: Commit**

```bash
git add FBI.py tests/test_fbi.py
git commit -m "feat: add compute_total_pages with cap support"
```

### Task 2.2: `iter_all_items`

**Files:**
- Modify: `FBI.py`
- Modify: `tests/test_fbi.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fbi.py`:

```python
import argparse


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fbi.py -k iter_all_items -v`
Expected: FAIL — `AttributeError: module 'FBI' has no attribute 'iter_all_items'`.

- [ ] **Step 3: Implement iter_all_items**

Add to `FBI.py` after `compute_total_pages`:

```python
def iter_all_items(session, cfg):
    """Yield every item across all pages, deriving page count from the API total."""
    first = fetch_page(session, 1, cfg.page_size)
    if first is None:
        logger.error("Could not fetch first page; nothing to do")
        return
    for item in first.get("items", []):
        yield item

    total = first.get("total", 0)
    total_pages = compute_total_pages(total, cfg.page_size, cfg.max_pages)
    logger.info("Total records reported: %s across %d page(s)", total, total_pages)

    for page in range(2, total_pages + 1):
        data = fetch_page(session, page, cfg.page_size)
        if data is None:
            continue
        items = data.get("items", [])
        if not items:
            logger.info("Page %d returned no items; stopping early", page)
            break
        for item in items:
            yield item
        time.sleep(cfg.delay)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fbi.py -k iter_all_items -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add FBI.py tests/test_fbi.py
git commit -m "feat: fetch all pages dynamically from API total with cap and skip"
```

### Bucket 2 completion

- [ ] Run reviewer agent on the `bucket-2-pagination` diff.
- [ ] Fix all reviewer followups on the branch; record for final summary.
- [ ] Push and open PR (base `bucket-1-network-resilience`, retarget to `main` once it merges).
- [ ] After reviewer passes: merge.
- [ ] Resolve Hub tasks #1, #7, and the logging task; log work.

---

## Bucket 3 — Defensive Parsing & Record Rendering

**Hub tasks:** #3 (missing-key guards), #9 (`!= None` → `is not None`, repurposed to safe access).
**Branch:** `bucket-3-parsing` off `bucket-2-pagination`.

### Task 3.1: `render_record`

**Files:**
- Modify: `FBI.py`
- Modify: `tests/test_fbi.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fbi.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fbi.py -k render_record -v`
Expected: FAIL — `AttributeError: module 'FBI' has no attribute 'render_record'`.

- [ ] **Step 3: Implement render_record**

Add to `FBI.py` after `iter_all_items`:

```python
def render_record(item):
    """Render one wanted item as an HTML <article>. Returns "" if no usable fields."""
    body = []

    title = item.get("title")
    if title:
        body.append("<h2>{}</h2>".format(title))

    path = item.get("path")
    if path:
        body.append('<p><a href="{0}">{0}</a></p>'.format(path))

    subjects = item.get("subjects")
    if subjects:
        names = ", ".join(str(s) for s in subjects)
        body.append("<p>Subjects: {}</p>".format(names))

    caution = item.get("caution")
    if isinstance(caution, str) and caution.strip():
        body.append(caution.replace("<p> </p>", ""))

    if not body:
        return ""
    return "<article>" + "".join(body) + "</article>"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fbi.py -k render_record -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add FBI.py tests/test_fbi.py
git commit -m "feat: render records defensively, including all non-empty items"
```

### Bucket 3 completion

- [ ] Run reviewer agent on the `bucket-3-parsing` diff.
- [ ] Fix all reviewer followups on the branch; record for final summary.
- [ ] Push and open PR (base `bucket-2-pagination`, retarget to `main` as bases merge).
- [ ] After reviewer passes: merge.
- [ ] Resolve Hub tasks #3, #9; log work.

---

## Bucket 4 — File Handling

**Hub tasks:** #4 (context manager), #5 (UTF-8 encoding).
**Branch:** `bucket-4-file-io` off `bucket-3-parsing`.

### Task 4.1: `write_output`

**Files:**
- Modify: `FBI.py`
- Modify: `tests/test_fbi.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fbi.py`:

```python
def test_write_output_roundtrip_utf8(tmp_path):
    p = tmp_path / "out.html"
    FBI.write_output("<p>José Peña — café</p>", str(p))
    assert p.read_text(encoding="utf-8") == "<p>José Peña — café</p>"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fbi.py -k write_output -v`
Expected: FAIL — `AttributeError: module 'FBI' has no attribute 'write_output'`.

- [ ] **Step 3: Implement write_output**

Add to `FBI.py` after `render_record`:

```python
def write_output(html, path):
    """Write the HTML document to `path` as UTF-8, closing the file even on error."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_fbi.py -k write_output -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add FBI.py tests/test_fbi.py
git commit -m "feat: write output via context manager with UTF-8 encoding"
```

### Bucket 4 completion

- [ ] Run reviewer agent on the `bucket-4-file-io` diff.
- [ ] Fix all reviewer followups on the branch; record for final summary.
- [ ] Push and open PR (base `bucket-3-parsing`, retarget to `main` as bases merge).
- [ ] After reviewer passes: merge.
- [ ] Resolve Hub tasks #4, #5; log work.

---

## Bucket 5 — HTML Output Quality + Final Assembly

**Hub tasks:** #8 (valid HTML structure), plus the pytest suite task (suite completed here), plus CLI/`main` assembly.
**Branch:** `bucket-5-output` off `bucket-4-file-io`.

### Task 5.1: `build_document`

**Files:**
- Modify: `FBI.py`
- Modify: `tests/test_fbi.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fbi.py`:

```python
def test_build_document_structure():
    doc = FBI.build_document(["<article>x</article>"])
    assert doc.startswith("<!DOCTYPE html>")
    assert 'charset="utf-8"' in doc
    assert "<title>FBI Most Wanted</title>" in doc
    assert "<article>x</article>" in doc
    assert doc.rstrip().endswith("</html>")


def test_build_document_filters_empty_articles():
    doc = FBI.build_document(["", "<article>y</article>", ""])
    assert "<article>y</article>" in doc
    assert "<article></article>" not in doc
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fbi.py -k build_document -v`
Expected: FAIL — `AttributeError: module 'FBI' has no attribute 'build_document'`.

- [ ] **Step 3: Implement build_document**

Add to `FBI.py` after `write_output`:

```python
def build_document(articles):
    """Wrap rendered <article> strings in a complete, valid HTML5 document."""
    body = "\n".join(a for a in articles if a)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>FBI Most Wanted</title>\n"
        "<style>\n"
        "body { font-family: system-ui, sans-serif; max-width: 800px;"
        " margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }\n"
        "article { border-bottom: 1px solid #ccc; padding: 1rem 0; }\n"
        "h1 { font-size: 1.6rem; }\n"
        "h2 { font-size: 1.2rem; margin: 0 0 .5rem; }\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        "<h1>FBI Most Wanted</h1>\n"
        + body
        + "\n</body>\n</html>\n"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fbi.py -k build_document -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add FBI.py tests/test_fbi.py
git commit -m "feat: build valid, structured HTML5 document with light styling"
```

### Task 5.2: `parse_args` + `main` assembly

**Files:**
- Modify: `FBI.py`
- Modify: `tests/test_fbi.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fbi.py`:

```python
def test_parse_args_defaults():
    cfg = FBI.parse_args([])
    assert cfg.output == "FBI.html"
    assert cfg.page_size == 20
    assert cfg.max_pages is None
    assert cfg.verbose is False


def test_parse_args_overrides():
    cfg = FBI.parse_args(["--output", "o.html", "--page-size", "50", "--max-pages", "3", "--verbose"])
    assert cfg.output == "o.html"
    assert cfg.page_size == 50
    assert cfg.max_pages == 3
    assert cfg.verbose is True


def test_main_writes_document(monkeypatch, tmp_path):
    out = tmp_path / "FBI.html"
    monkeypatch.setattr(
        FBI, "iter_all_items",
        lambda session, cfg: iter([{"title": "Target", "path": "https://p"}]),
    )
    rc = FBI.main(["--output", str(out)])
    assert rc == 0
    content = out.read_text(encoding="utf-8")
    assert content.startswith("<!DOCTYPE html>")
    assert "Target" in content


def test_main_returns_nonzero_on_write_error(monkeypatch):
    monkeypatch.setattr(FBI, "iter_all_items", lambda session, cfg: iter([{"title": "T"}]))
    def boom(html, path):
        raise OSError("disk full")
    monkeypatch.setattr(FBI, "write_output", boom)
    rc = FBI.main(["--output", "/nonexistent/dir/out.html"])
    assert rc == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_fbi.py -k "parse_args or main" -v`
Expected: FAIL — `AttributeError: module 'FBI' has no attribute 'parse_args'`.

- [ ] **Step 3: Implement parse_args + main + entrypoint**

Add to `FBI.py` after `build_document`:

```python
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Fetch the FBI Most Wanted list and write it to an HTML file."
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output HTML path.")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="Items per page.")
    parser.add_argument("--max-pages", type=int, default=None, help="Optional cap on pages fetched.")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Seconds between pages.")
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG logging.")
    return parser.parse_args(argv)


def main(argv=None):
    cfg = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if cfg.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    articles = [render_record(item) for item in iter_all_items(session, cfg)]
    rendered = [a for a in articles if a]
    logger.info("Rendered %d record(s)", len(rendered))
    html = build_document(rendered)
    try:
        write_output(html, cfg.output)
    except OSError as exc:
        logger.error("Failed to write %s: %s", cfg.output, exc)
        return 1
    logger.info("Wrote %s", cfg.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the full suite to verify everything passes**

Run: `python -m pytest tests/test_fbi.py -v`
Expected: PASS (all tests — fetch, pagination, parsing, file I/O, document, CLI, main).

- [ ] **Step 5: Commit**

```bash
git add FBI.py tests/test_fbi.py
git commit -m "feat: add argparse CLI and main orchestration with logging"
```

### Task 5.3: End-to-end smoke (manual, optional network)

- [ ] **Step 1: Run the script for real (requires network)**

Run: `python FBI.py --max-pages 1 --output /tmp/fbi-smoke.html`
Expected: log line `Wrote /tmp/fbi-smoke.html`, exit 0. Open the file in a browser; confirm valid structure, readable styling, and correctly-rendered accented characters.

> If no network is available in the execution environment, skip this step and note it in the final summary; the mocked suite already covers all logic paths.

### Bucket 5 completion

- [ ] Run reviewer agent on the `bucket-5-output` diff.
- [ ] Fix all reviewer followups on the branch; record for final summary.
- [ ] Push and open PR (base `bucket-4-file-io`, retarget to `main` as bases merge).
- [ ] After reviewer passes: merge.
- [ ] Resolve Hub tasks #8 and the pytest-suite task; log work.

---

## Final Summary (produced at end of run)

After all 5 buckets merge, produce a summary containing:
- One line per bucket: branch, PR link, merge status.
- The complete list of reviewer followups found and how each was resolved.
- Any deferred/non-blocking items (if any).
- Result of the end-to-end smoke step (run or skipped + why).
- Confirmation that all 12 Project Hub tasks are resolved.

---

## Self-Review (plan vs. spec)

**Spec coverage:**
- §4 Bucket 1 (tasks 2, 6) → Task 1.2 (`fetch_page` timeout + retry). `requirements.txt` → Task 1.1. ✓
- §4 Bucket 2 (tasks 1, 7) → Tasks 2.1 (`compute_total_pages`) + 2.2 (`iter_all_items` dynamic). ✓
- §4 Bucket 3 (tasks 3, 9) → Task 3.1 (`render_record` safe `.get()`, include-all, no `!= None`). ✓
- §4 Bucket 4 (tasks 4, 5) → Task 4.1 (`write_output` context manager + UTF-8). ✓
- §4 Bucket 5 (task 8) → Task 5.1 (`build_document`). ✓
- §5 logging → woven into `fetch_page`/`iter_all_items`/`main`; configured in Task 5.2. ✓
- §5 tests → suite built incrementally across every task; full run in Task 5.2 Step 4. ✓
- §6 delivery (stacked branches, reviewer-gated merge, followups before PR, Hub resolve) → per-bucket completion sections. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every command shows expected output. The only "optional" step (5.3) has an explicit skip condition. ✓

**Type/signature consistency:** `cfg` is an `argparse.Namespace` with `output`, `page_size`, `max_pages`, `delay`, `verbose` — used identically in `iter_all_items`, `parse_args`, `main`, and the `_cfg` test helper. `fetch_page(session, page, page_size, timeout, retries)` signature matches all call sites and mocks. `compute_total_pages(total, page_size, max_pages)` matches its use in `iter_all_items`. `render_record(item) -> str`, `build_document(articles) -> str`, `write_output(html, path)` consistent across tasks and tests. ✓
