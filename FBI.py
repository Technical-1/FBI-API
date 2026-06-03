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
            # ValueError also covers json.JSONDecodeError; a malformed body is treated
            # as a transient failure and retried like any other error.
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.warning("Page %d attempt %d/%d failed: %s", page, attempt + 1, retries + 1, exc)
            if attempt < retries:
                time.sleep(2 ** attempt)
    logger.error("Page %d failed after %d attempts; skipping", page, retries + 1)
    return None


def compute_total_pages(total, page_size, max_pages=None):
    """Number of pages needed for `total` items at `page_size`, optionally capped."""
    if page_size <= 0:
        raise ValueError("page_size must be positive, got {}".format(page_size))
    pages = math.ceil(total / page_size) if total > 0 else 0
    if max_pages is not None:
        pages = min(pages, max_pages)
    return pages


def iter_all_items(session, cfg):
    """Yield every item across all pages, deriving page count from the API total."""
    first = fetch_page(session, 1, cfg.page_size)
    if first is None:
        logger.error("Could not fetch first page; nothing to do")
        return

    # `or 0` guards against both a missing key and an explicit null total.
    total = first.get("total") or 0
    total_pages = compute_total_pages(total, cfg.page_size, cfg.max_pages)
    logger.info("Total records reported: %s across %d page(s)", total, total_pages)

    for item in first.get("items", []):
        yield item

    for page in range(2, total_pages + 1):
        time.sleep(cfg.delay)  # throttle before each subsequent fetch, success or not
        data = fetch_page(session, page, cfg.page_size)
        if data is None:
            continue
        items = data.get("items", [])
        if not items:
            logger.info("Page %d returned no items; stopping early", page)
            break
        for item in items:
            yield item


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
