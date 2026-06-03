# FBI-API Hardening — Design & Implementation Spec

**Date:** 2026-06-03
**Author:** Jacob Kanfer
**Status:** Approved design, pending spec review
**Scope:** Harden and restructure `FBI.py` (FBI Most Wanted scraper → HTML) across 5 implementation buckets, derived from a repository investigation that produced 9 tasks (Project Hub project 88).

---

## 1. Background

`FBI.py` is a single flat script that pages through the FBI Most Wanted API
(`https://api.fbi.gov/wanted/v1/list`) and writes selected fields into an HTML
file. A repository investigation surfaced 9 issues spanning correctness,
robustness, resource handling, and output quality. This spec consolidates them
into 5 implementation buckets, resolves every design decision up front, and
defines the delivery process.

### Source tasks (Project Hub project 88)

| # | Task | Priority | Bucket |
|---|------|----------|--------|
| 1 | Off-by-one: loop fetches only 9 pages, not 10 | high | 2 |
| 2 | Add error handling and status check around requests.get | high | 1 |
| 3 | Guard against missing dict keys when reading API items | high | 3 |
| 4 | Use a context manager so the file closes on exceptions | medium | 4 |
| 5 | Specify UTF-8 encoding when opening the output file | medium | 4 |
| 6 | Add a timeout to the HTTP request to avoid hangs | medium | 1 |
| 7 | Derive page count from API total instead of hardcoding | medium | 2 |
| 8 | Wrap output in valid HTML document structure | low | 5 |
| 9 | Replace `!= None` with `is not None` | low | 3 (repurposed) |

---

## 2. Resolved Design Decisions

These were decided up front so no choices are made mid-implementation.

| Area | Decision |
|------|----------|
| Pagination | **Dynamic fetch-all** — derive page count from API `total`; optional `--max-pages` cap |
| Network failure | **Retry then skip** — failed page retried, then skipped (partial output allowed) |
| Code structure | **Refactor into functions** with `main()` + `argparse` |
| Output format | **Structured `<article>` blocks + light inline CSS**, valid HTML5 doc |
| Record filter | **Include all records** (drop the old `caution is not None` filter) |
| Retry config | **timeout=15s, 3 retries, exponential backoff (1s, 2s, 4s)** |
| Configuration | **argparse CLI**: `--output`, `--page-size`, `--max-pages`, `--delay`, `--verbose` |
| Tooling | `requirements.txt`, Python `logging`, pytest tests |
| README | **Out of scope** (not selected) |
| Target | Python 3.8+ |

---

## 3. Target Architecture

Refactor the flat script into a small, testable module with a `main()` entry
point and `argparse`.

### Module layout (`FBI.py`)

| Function | Responsibility | Depends on |
|----------|----------------|------------|
| `parse_args(argv)` | Parse `--output`, `--page-size`, `--max-pages`, `--delay`, `--verbose`; return config object | argparse |
| `fetch_page(session, page, page_size, timeout, retries)` | One HTTP GET with retry/backoff; returns parsed JSON dict or `None` | requests |
| `iter_all_items(session, cfg)` | Generator: fetch page 1, compute total pages, yield each item across all pages | `fetch_page` |
| `render_record(item)` | Turn one item dict into an HTML `<article>` string using safe `.get()` access | — |
| `build_document(articles)` | Wrap rendered records in a full HTML5 doc (doctype, charset, CSS) | `render_record` |
| `write_output(html, path)` | Write document with `with open(..., encoding='utf-8')` | — |
| `main(argv)` | Orchestrate: parse → iterate → render → write; logging + exit codes | all above |

**Data flow:** `main` → `iter_all_items` (resilient fetch loop) → `render_record`
per item → `build_document` → `write_output`. Network, parsing, rendering, and
I/O are isolated so each can be unit-tested with mocked inputs.

**Supporting files:** `requirements.txt` (pins `requests`), `tests/test_fbi.py`
(pytest), logging configured in `main`.

### Module constants

- `API_URL = "https://api.fbi.gov/wanted/v1/list"`
- `USER_AGENT = "FBI-API-scraper/1.0 (+https://github.com/Technical-1/FBI-API)"`
- Defaults: `DEFAULT_OUTPUT = "FBI.html"`, `DEFAULT_PAGE_SIZE = 20`,
  `DEFAULT_TIMEOUT = 15`, `DEFAULT_RETRIES = 3`, `DEFAULT_DELAY = 0.25`

---

## 4. Per-Bucket Implementation Plans

### Bucket 1 — Network Resilience
**Tasks:** 2 (error handling + status check, high), 6 (timeout, medium)
**Config:** timeout=15s, 3 retries, exponential backoff (1s, 2s, 4s).

**Plan — `fetch_page(session, page, page_size, timeout=15, retries=3)`:**
1. Use a shared `requests.Session` for connection reuse; set a descriptive `User-Agent` header.
2. Loop up to `retries + 1` attempts:
   - `resp = session.get(API_URL, params={'page': page, 'pageSize': page_size}, timeout=timeout)`
   - `resp.raise_for_status()`
   - `return resp.json()`
3. Catch `requests.exceptions.RequestException` and `ValueError` / `json.JSONDecodeError`; on each failure log a warning and `sleep(2 ** attempt)` before retrying.
4. After exhausting retries, log an error and `return None` → caller skips this page.

**Edge cases:** empty body; HTML error page (caught by `.json()` raising); 429/5xx (retried).
**Verification:** unit test with a mocked session that raises then succeeds; assert retry count and final result; assert returns `None` after exhausting retries.

---

### Bucket 2 — Pagination & Coverage
**Tasks:** 1 (off-by-one, high), 7 (derive from total, medium)
**Decision:** dynamic fetch-all, optional `--max-pages` cap.

**Plan — `iter_all_items(session, cfg)` (generator):**
1. Fetch page 1. If `None`, log error and stop (nothing to write).
2. Read `total = data.get('total', 0)`; compute `total_pages = ceil(total / cfg.page_size)`.
3. Apply cap: `pages = min(total_pages, cfg.max_pages)` when `--max-pages` is set.
4. Yield items from page 1, then loop pages `2..pages`:
   - `data = fetch_page(...)`; if `None`, log and `continue` (skip page).
   - If `data.get('items')` is empty, `break` (defensive early stop).
   - `sleep(cfg.delay)` between successful pages (politeness; default 0.25s).
5. The original `range(1, 10)` off-by-one is eliminated entirely.

**Edge cases:** `total` missing → fall back to "loop until empty items"; `total == 0` → no items.
**Verification:** unit test page-count math at `ceil` boundaries (999/20, 1000/20, 1001/20); test `--max-pages` cap honored; test early stop on empty items.

---

### Bucket 3 — Defensive Parsing & Record Rendering
**Tasks:** 3 (missing-key guards, high), 9 (`!= None` → `is not None`, low — repurposed)
**Decision:** include all records (no caution filter).

**Plan — `render_record(item)`:**
1. Access every field via `.get()`: `path`, `title`, `subjects`, `caution`, plus `description` / `details` if present.
2. Build an `<article>` with whatever is available; omit a sub-element when its field is missing/empty rather than printing `None` or `[]`.
3. Keep the existing `caution.replace('<p> </p>', '')` cleanup, guarded so it only runs when `caution` is a non-empty string.
4. No `!= None` comparisons remain; any residual null checks use `is not None`; empty-string/empty-list checks use truthiness.

**Edge cases:** item missing all fields → render a minimal stub (title or `path` only); skip only if literally empty (logged at debug).
**Verification:** unit tests for `render_record` with (a) full item, (b) missing `caution`, (c) missing `subjects`, (d) near-empty item.

---

### Bucket 4 — File Handling
**Tasks:** 4 (context manager, medium), 5 (UTF-8 encoding, medium)

**Plan — `write_output(html, path)`:**
1. `with open(path, 'w', encoding='utf-8') as f: f.write(html)` — single call, no manual `close()`.
2. `path` comes from `--output` (default `FBI.html`).
3. Any exception propagates to `main`, which logs it and exits non-zero; the `with` guarantees the handle closes even on a mid-write error.

**Edge cases:** unwritable path → caught/logged in `main` with non-zero exit.
**Verification:** test writes a temp file and reads back UTF-8 content including accented characters.

---

### Bucket 5 — HTML Output Quality
**Task:** 8 (valid HTML structure, low)
**Decision:** structured `<article>` blocks + light CSS.

**Plan — `build_document(articles)`:**
1. Emit `<!DOCTYPE html>`, `<html lang="en">`, `<head>` with `<meta charset="utf-8">`, viewport meta, `<title>FBI Most Wanted</title>`, and small inline `<style>` (readable max-width, spacing between articles, heading styles).
2. `<body>` contains a heading + the joined `<article>` strings.
3. `caution` / `subjects` from the API contain embedded HTML; intentionally injected as trusted markup (FBI .gov source) rather than escaped — documented as an accepted assumption.

**Verification:** generated file opens cleanly in a browser; basic well-formedness check; charset renders accents correctly.

---

## 5. Supporting Tasks (new — beyond the original 9)

- **`requirements.txt`** — pin `requests` (e.g., `requests>=2.31`).
- **`logging`** — configured in `main` (`--verbose` toggles DEBUG); INFO for progress, WARNING/ERROR for failures. No bare `print`.
- **`tests/test_fbi.py`** — pytest covering: `fetch_page` retry/backoff (mocked session), page-count math, `render_record` field variants, `write_output` round-trip.

These will be added to Project Hub before execution and woven into the relevant
buckets (`requirements.txt` first; logging during buckets 1–2; tests after each
function lands).

---

## 6. Delivery Process

### Branching — stacked branches
- Bucket 1 branches off `main`; its PR targets `main`.
- Bucket N (N>1) branches off bucket N-1's branch; its PR targets bucket N-1's branch.
- Because each bucket is merged after its reviewer passes, the stack collapses in
  order; later branches are retargeted to `main` as their base merges.

### Per-bucket cycle
1. Create the bucket branch (stacked on the previous).
2. **Implementer agent** applies the bucket's plan (one focused subagent).
3. **Reviewer agent** reviews the bucket diff for correctness, regressions, and plan adherence.
4. **Fix reviewer followups on the branch before opening the PR** (each PR opens already-clean). All followups recorded for the final summary.
5. Commit, push, open PR (targets the branch below).
6. **Merge after the reviewer passes** and followups are done; proceed to the next bucket.
7. **Resolve the bucket's Project Hub tasks** and log work.

### Subagent efficiency
- One implementer + one reviewer per bucket. Buckets are sequential (same file),
  so no parallel fan-out. Context (this spec + prior bucket results) is passed forward.

### Followups
- Blocking followups fixed before the PR opens.
- All followups (blocking and any deferred nits) are listed at the end of the run.

### Guardrails (from user global rules)
- Commit author email must be on the allowlist (`51518860+Technical-1@users.noreply.github.com` or `jacobrk2001@gmail.com`).
- **No** Claude/AI attribution in commits or PRs.
- Verify `git config user.email` before each commit.

---

## 7. Open Questions

None. All design and delivery decisions are resolved (Sections 2 and 6).

---

## 8. Build Order

Bucket 1 → 2 → 3 → 4 → 5, with supporting tooling woven in:
`requirements.txt` first, logging during buckets 1–2, tests after each function lands.
