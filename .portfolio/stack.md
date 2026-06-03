# Tech Stack

## Core Technologies

| Category | Technology | Version | Why this choice |
|----------|------------|---------|-----------------|
| Language | Python | 3.8+ | Batteries-included stdlib (argparse, logging, html, re) covers most of the work |
| HTTP client | `requests` | ≥ 2.31 | Simple session/retry ergonomics; the de facto standard for HTTP in Python |
| Testing | `pytest` | latest | Fixtures (`tmp_path`, `monkeypatch`) make mocking the network trivial |

## Backend

- **Runtime**: Python 3.8+ CLI program
- **API Style**: Consumes a REST/JSON API (FBI Wanted)
- **Auth**: None — the FBI Wanted API is public and unauthenticated

## Infrastructure

- **Hosting**: None — runs locally as a script
- **CI/CD**: None
- **Monitoring**: Structured `logging` to stderr (`--verbose` raises the level to DEBUG)

## Development Tools

- **Package Manager**: `pip` (`requirements.txt`)
- **Testing**: `pytest`, with `unittest.mock` and `monkeypatch`; the network is fully mocked so the suite runs offline
- **Formatting/Linting**: none configured — small enough to keep clean by hand

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `requests` | All HTTP communication with the FBI Wanted API (session reuse, timeouts, status handling) |

Everything else — argument parsing, logging, HTML escaping, regex cleanup, and ceil math — comes from the Python standard library (`argparse`, `logging`, `html`, `re`, `math`), keeping the dependency surface to a single package.
