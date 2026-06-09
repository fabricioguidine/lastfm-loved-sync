# lastfm-loved-sync

[![CI](https://github.com/fabricioguidine/lastfm-loved-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/fabricioguidine/lastfm-loved-sync/actions/workflows/ci.yml) [![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Loves every Last.fm track at or above a scrobble threshold and unloves the ones below it. Play counts and loved tracks are read through the official Last.fm API; the love/unlove actions run through a real browser session driven by Playwright. Dry-run by default.

## How it works

1. Read `user.getTopTracks` (ranked by play count) and `user.getLovedTracks`. With a threshold set, pagination stops once play counts drop below it.
2. Build a two-way plan: tracks at or above the threshold that are not loved get loved; loved tracks below the threshold get unloved.
3. Apply through Playwright using a saved login: each track page is opened and its love control toggled. Actions are idempotent — a click happens only when the state differs.

## Setup

```bash
uv sync --dev
uv run playwright install chromium
cp .env.example .env   # set LASTFM_API_KEY and LASTFM_USER
```

Create a read API key at https://www.last.fm/api/account/create.

## Usage

```bash
uv run lastfm-loved-sync login                 # save a browser session once
uv run lastfm-loved-sync sync --min-plays 100  # preview (dry-run)
uv run lastfm-loved-sync sync --min-plays 100 --apply
```

`--min-plays` is inclusive (100 means 100 or more). Run `sync` with no flag to be prompted. Dry-run prints the full love/unlove list and changes nothing.

### Apply via the official API (no browser)

Instead of the Playwright session, you can love/unlove through the authenticated Last.fm API. Set `LASTFM_SHARED_SECRET` in `.env`, then authorize once:

```bash
uv run lastfm-loved-sync auth                  # opens a token URL; click "Yes, allow access"
uv run lastfm-loved-sync sync --min-plays 100 --apply
```

`auth` saves a `LASTFM_SESSION_KEY` to `.env`. When that key is present, `sync --apply` uses signed `track.love`/`track.unlove` calls instead of the browser, and re-fetches and re-applies until the loved set actually matches the target — so a write that the API drops under load gets retried on the next round.

When you're done, remove the saved credentials:

```bash
uv run lastfm-loved-sync logout            # delete the session key from .env
uv run lastfm-loved-sync logout --purge    # also delete the API key and shared secret
```

To delete the API application itself, go to https://www.last.fm/api/accounts.

## Development

```bash
uv run ruff check .
uv run mypy
uv run pytest                 # unit + e2e
uv run pytest -m "not e2e"    # skip the browser tests
```

The e2e suite runs the read-plan-write path against a mocked API and a local love-button fixture in a real Chromium; it never touches a live account.

## Notes

- `.env` and the saved session are gitignored.
- Last.fm's track-page markup changes over time; the love-button selectors live in `config.py` and are mirrored by the e2e fixture.

## License

MIT
