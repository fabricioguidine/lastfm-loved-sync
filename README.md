# lastfm-loved-sync

[![CI](https://github.com/fabricioguidine/lastfm-loved-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/fabricioguidine/lastfm-loved-sync/actions/workflows/ci.yml) [![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Loves every Last.fm track at or above a scrobble threshold and unloves the ones below it, tags heavily-played artists and albums with a personal tag, and generates local `.m3u8` playlists from your library. Reads go through the official Last.fm API; writes run either through the authenticated API or a real browser session driven by Playwright. Dry-run by default.

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

### Bookmark artists and albums

Last.fm has no "love" for artists or albums — the closest equivalent is a personal tag. `bookmark` tags every artist at or above a scrobble threshold, and every album at or above a play threshold, with a tag of your choice (requires `auth`):

```bash
uv run lastfm-loved-sync bookmark --min-artist-plays 1000 --min-album-plays 1000   # preview
uv run lastfm-loved-sync bookmark --tag bookmarked --apply
```

Like `sync`, it re-checks each item after tagging and re-applies any tag the API dropped.

### Local playlists

Last.fm's API can't create playlists, so these are written as local `.m3u8` files (playable in VLC, foobar2000, etc.). Re-running is append-only: existing entries are kept and only new tracks are added.

```bash
uv run lastfm-loved-sync playlist artists                 # one playlist per "bookmarked" artist (their top tracks)
uv run lastfm-loved-sync playlist genres --min-plays 50   # one playlist per genre, for tracks with >=50 plays
```

`playlist artists` sources artists from a personal tag (default `bookmarked` — run `bookmark --apply` first). `playlist genres` groups your tracks by each artist's dominant Last.fm tag. Both write to `./playlists/` by default (`--out` to change).

## Architecture

```
src/lastfm_loved_sync/
  api/            Last.fm HTTP clients
    read.py       LastfmClient — top tracks/artists/albums, loved tracks, tags
    write.py      LastfmWriteClient — token auth, track.love/unlove, artist/album tagging
    sign.py       request signing;  resilience.py  retry on transport + 5xx errors
  analysis.py     build the two-way love/unlove plan from a threshold
  sync.py         fetch + plan + apply (browser or converging API path)
  bookmarks.py    fetch + tag artists/albums above a threshold
  playlists.py    generate local .m3u8 playlists (append-only on re-run)
  api_apply.py    token-authorize flow and API plan application
  browser.py      Playwright love-button automation
  cli.py          Typer commands;  tui.py  rich tables and prompts
  config.py       env-backed settings;  models.py  Track/Artist/Album;  normalize.py  identity keys
```

## Development

```bash
uv run ruff check .
uv run mypy
uv run pytest                 # unit + e2e
uv run pytest -m "not e2e"    # skip the browser tests
```

The e2e suite never touches a live account: the browser path runs against a mocked API and a local love-button fixture in a real Chromium, and the API path runs against a stateful in-memory Last.fm that deliberately drops the first write to prove the convergence and tag re-verify logic recovers.

## Notes

- `.env` and the saved session are gitignored.
- Last.fm's track-page markup changes over time; the love-button selectors live in `config.py` and are mirrored by the e2e fixture.

## License

MIT
