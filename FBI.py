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
