# Test fixtures

**To recapture:** put `OMDB_API_KEY` and `TMDB_API_KEY` in `.env` (see `.env.example`), then run

```
uv run film-etl capture-fixtures              # demo list from config/lists.yaml, 10 films
uv run film-etl capture-fixtures --list-url https://letterboxd.com/<user>/list/<name>/ --films 5
```

This makes polite live requests (1–2 s apart for Letterboxd), trims the HTML, overwrites the
files below, and updates `manifest.json`. Raw responses are cached in `data/raw/`, so a
rerun only refetches what isn't cached; delete `data/raw/` for a fully fresh capture.
Afterwards, run `uv run pytest` to check that every fixture is in the manifest and the
total stays under 2 MB.

## How tests use these files

`FixtureClient` (used by tests and `--offline`) looks up each request in `manifest.json`:

```json
{"GET https://letterboxd.com/film/harakiri/": {"path": "letterboxd/film_harakiri.html", "synthetic": false}}
```

The key is `http.cache_key(url, params)`, the same key `HttpClient` uses for its disk cache,
with secret params (`apikey`, `api_key`) removed. A request with no entry returns `None`.

## Layout

| Path | Source |
|---|---|
| `letterboxd/list_page1.html`, `list_page2.html` | Demo list, first two pages (trimmed) |
| `letterboxd/film_<slug>.html` | Film pages (trimmed: JSON-LD, links, ratings, popular reviews) |
| `letterboxd/csi_<slug>_<name>.html` | `/csi/` fragments a film page loads (stats, rating histogram) |
| `letterboxd/list_legacy.html` | Hand-written pre-LazyPoster list markup (`data-film-slug`) |
| `omdb/<imdb_id>.json` | OMDb by IMDb id |
| `tmdb/find_<imdb_id>.json`, `tmdb/movie_<tmdb_id>.json` | TMDB find-by-IMDb, then details with keywords and reviews |
| `wikidata/money_batch.json` | One SPARQL batch: budget and box office, with currency units |

## Synthetic fixtures

Entries with `"synthetic": true` were written by hand, and their values are illustrative:

- `list_legacy.html`: live pages no longer use this markup.
- `csi_harakiri_stats.html`: Letterboxd returned 403 for `/csi/.../stats/` during capture.
  The rating-histogram fragment for the same film was captured live.
- `omdb/*.json` and `tmdb/*.json`: captured without API keys. `tt0000000` is OMDb's
  not-found shape. Harakiri has no box office and a zero TMDB budget; Shawshank has money data.

A live capture overwrites a synthetic entry with the same key and marks it `"synthetic": false`.
