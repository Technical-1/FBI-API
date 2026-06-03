# Project Q&A

## Overview

FBI-API is a command-line tool that fetches the FBI's Most Wanted list from their public API and renders it as a single, self-contained HTML page. The interesting engineering angle is resilience: it streams through the entire (changing) dataset, tolerates per-page network failures and malformed records, and still produces valid, well-formed HTML.

## Problem Solved

The FBI Wanted API returns paginated JSON that isn't pleasant to read directly, and the dataset is large and changes over time. This tool consolidates the whole list into one browsable HTML page in a single command, without the caller needing to know how many records or pages exist.

## Target Users

- **Curious browsers** — anyone who wants to scan the full Most Wanted list offline in one page.
- **Developers** — a compact, well-tested reference for paging a public JSON API resiliently in Python.

## Key Features

### Complete, self-adjusting coverage
The tool asks the API how many records exist and pages through all of them, so it stays correct as the list grows or shrinks — no fixed page count to fall out of date.

### Resilient network handling
Each page request has a timeout and retries with exponential backoff. A page that ultimately fails is skipped so the rest of the run still completes, rather than the whole job dying on one hiccup.

### Defensive rendering
Records with missing or unusual fields are rendered with whatever data is present instead of throwing, and plain-text fields are HTML-escaped so the output stays well-formed.

## Technical Highlights

### Total-driven pagination with a graceful fallback
The original approach hardcoded a fixed page range and silently dropped everything beyond it. Now `iter_all_items()` reads the API's `total` from the first response and computes the exact page count via `compute_total_pages()` (ceil division, with an optional cap). If `total` is missing or `null`, it falls back to stopping when a page comes back empty — so a malformed first response can't cause either a crash or an infinite loop.

### Retry/backoff that distinguishes "skip" from "stop"
`fetch_page()` retries on any `requests` exception or JSON-decode error with exponential backoff, then returns `None` once retries are exhausted. The caller treats a `None` page as skippable and continues, but treats an *empty* page as the natural end of data and stops. This separation keeps a transient failure from being mistaken for the end of the list.

### Field access that can't `KeyError`
`render_record()` reads every field through `dict.get()` and builds the output from only the fields that are present, returning an empty string for a record with nothing usable. A single weird record from the API therefore can't abort a run that's already processed hundreds.

### Output written safely as UTF-8
Fugitive records routinely contain accented names and special punctuation. `write_output()` writes through a context manager with an explicit `encoding="utf-8"`, which both guarantees the file handle closes on error and avoids the platform-default encoding silently corrupting non-ASCII characters.

## Engineering Decisions

### Stream records instead of buffering them
- **Constraint**: The dataset is 1,000+ records across many pages.
- **Options**: Eagerly collect all items into a list, or yield them lazily.
- **Choice**: A generator (`iter_all_items`).
- **Why**: Memory stays flat and the rendering stage can start immediately; nothing in the pipeline needs the full set at once.

### Escape plain text, trust the API's HTML
- **Constraint**: API fields mix plain text (`title`, `subjects`) with pre-formatted HTML (`caution`).
- **Options**: Escape everything (breaks the intended caution markup) or escape nothing (risks malformed output from stray `&`/`<`).
- **Choice**: Escape the plain-text fields; render `caution` as the HTML it already is.
- **Why**: It keeps the document valid while preserving the formatting the API intends.

### Keep it one module
- **Constraint**: The program is under 200 lines.
- **Options**: Split into a package, or keep a single file of focused functions.
- **Choice**: One module, function-level separation.
- **Why**: Full unit-test coverage without the ceremony of a multi-file project.

## Frequently Asked Questions

### How does the tool know when to stop paging?
It reads the `total` count from the first API response and computes how many pages that implies. If `total` is absent or null, it keeps going until a page returns no items.

### What happens if one page fails to download?
That page is retried with exponential backoff; if it still fails, it's logged and skipped, and the run continues with the remaining pages. Only a failure on the very first page stops the run (since the total count is unknown).

### Why is the output a single HTML file?
So the whole list is browsable offline in one place. `build_document()` emits a complete HTML5 page with a UTF-8 charset and light styling, so it renders correctly in any browser.

### Can I fetch just a sample instead of the whole list?
Yes — `--max-pages 1` (optionally with `--output`) grabs just the first page, which is the quickest way to eyeball the format.

### Does it need an API key?
No. The FBI Wanted API is public and unauthenticated. The tool sends a descriptive `User-Agent` and throttles between requests (`--delay`) to be polite.

### How is it tested without hitting the network?
The `pytest` suite mocks the `requests` session and patches `time.sleep`, so retry/backoff, pagination, rendering, and file output are all verified offline and fast.
