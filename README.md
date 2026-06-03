# FBI-API

A small command-line tool that pulls the FBI's Most Wanted list from their public API and renders it as a single, self-contained HTML page for easy browsing.

It walks every page of the [FBI Wanted API](https://api.fbi.gov/wanted/v1/list), handles flaky network conditions gracefully, and produces a valid, UTF-8 HTML document with one styled entry per fugitive. What started as a throwaway script is now a resilient, fully tested fetcher.

## Features

- **Complete coverage** — derives the total record count from the API and pages through all of it, rather than stopping at a fixed page limit.
- **Resilient fetching** — per-request timeout, automatic retry with exponential backoff, and graceful skip-and-continue when an individual page fails.
- **Safe rendering** — tolerates missing or malformed fields without crashing, and HTML-escapes plain-text fields to keep the output well-formed.
- **Valid HTML output** — emits a complete HTML5 document (`<!DOCTYPE html>`, UTF-8 charset, light inline styling) instead of bare fragments.
- **Configurable CLI** — output path, page size, page cap, inter-request delay, and verbosity are all flags.

## Tech Stack

- **Language**: Python 3.8+
- **HTTP**: `requests`
- **Testing**: `pytest`
- **Output**: self-contained HTML5

## Getting Started

### Prerequisites

- Python 3.8 or newer
- `pip`

### Installation

```bash
git clone https://github.com/Technical-1/FBI-API.git
cd FBI-API
pip install -r requirements.txt
```

### Usage

```bash
# Fetch the full list into FBI.html
python3 FBI.py

# Fetch just the first page into a custom file (handy for a quick look)
python3 FBI.py --max-pages 1 --output sample.html

# Larger pages, verbose logging
python3 FBI.py --page-size 50 --verbose
```

| Flag | Default | Description |
|------|---------|-------------|
| `--output` | `FBI.html` | Output HTML file path |
| `--page-size` | `20` | Records requested per API page |
| `--max-pages` | _(all)_ | Optional cap on pages fetched |
| `--delay` | `0.25` | Seconds to wait between page requests |
| `--verbose` | off | Enable DEBUG logging |

## Development

```bash
# Install dependencies (plus pytest)
pip install -r requirements.txt pytest

# Run the test suite
python3 -m pytest -v
```

## Project Structure

```
FBI-API/
├── FBI.py              # CLI entry point + all fetch/parse/render/write logic
├── tests/
│   └── test_fbi.py     # pytest suite (network mocked — no live calls)
├── requirements.txt    # runtime dependency (requests)
└── .gitignore
```

## License

Unlicensed (personal project).

## Author

Jacob Kanfer — [GitHub](https://github.com/Technical-1)
