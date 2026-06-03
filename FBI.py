"""Fetch the FBI Most Wanted list and render it as an HTML page."""

import argparse
import html
import logging
import math
import re
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
        body.append("<h2>{}</h2>".format(html.escape(str(title))))

    path = item.get("path")
    if path:
        safe_path = html.escape(str(path), quote=True)
        body.append('<p><a href="{0}">{0}</a></p>'.format(safe_path))

    subjects = item.get("subjects")
    if subjects:
        names = ", ".join(html.escape(str(s)) for s in subjects if s)
        if names:
            body.append("<p>Subjects: {}</p>".format(names))

    caution = item.get("caution")
    if isinstance(caution, str) and caution.strip():
        body.append(re.sub(r"<p>(?:\s|&nbsp;)*</p>", "", caution))

    if not body:
        return ""
    return "<article>" + "".join(body) + "</article>"


def write_output(document, path):
    """Write the HTML document to `path` as UTF-8, closing the file even on error."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(document)


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
    document = build_document(rendered)
    try:
        write_output(document, cfg.output)
    except OSError as exc:
        logger.error("Failed to write %s: %s", cfg.output, exc)
        return 1
    logger.info("Wrote %s", cfg.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
