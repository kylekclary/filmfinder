Letterboxd film ETL pipeline

A complete, locally runnable Python pipeline: scrape public Letterboxd lists, enrich with REST APIs, transform in Pandas, load to SQLite/Parquet, and browse results in Streamlit.

What each source actually provides

OMDb does not include budget. US box office is a formatted string (BoxOffice) and is often N/A. The pipeline will treat OMDb as the ratings/plot/IMDb-id layer and fill financials elsewhere.





Letterboxd (scrape, no public API): list membership, title/year/slug, film-page JSON-LD (director, genres, average rating), engagement counts when present in HTML (watches, likes, fans, lists, reviews), and the ~12 popular reviews inline on the film page.



OMDb: imdbID, plot, runtime, rated, awards, IMDb/RT/Metacritic scores, imdbVotes, US BoxOffice.



TMDB: budget, worldwide revenue, popularity, vote_average/vote_count, official catalog keywords, user reviews. Resolve via GET /3/find/{imdb_id}?external_source=imdb_id, then GET /3/movie/{id}?append_to_response=keywords,reviews.



Wikidata SPARQL (no key): P2130 budget and P2142 box office keyed by IMDb P345, used only when TMDB budget/revenue is missing or zero.

Audience sentiment keywords are not a single API field. Official TMDB keywords are catalog tags (e.g. "time travel"), not opinion. Sentiment terms will be extracted from Letterboxd + TMDB review text.

flowchart LR
  lists[Letterboxd lists] --> films[Film pages]
  films --> staging[Raw cache]
  omdb[OMDb API] --> staging
  tmdb[TMDB API] --> staging
  wiki[Wikidata SPARQL] --> staging
  staging --> pandas[Pandas transform]
  pandas --> warehouse[SQLite and Parquet]
  warehouse --> ui[Streamlit explorer]

Project layout

Python package via uv init / pyproject.toml, runnable as uv run film-etl ....





[src/film_etl/extract/letterboxd.py](src/film_etl/extract/letterboxd.py) — list + film HTML parsers



[src/film_etl/extract/omdb.py](src/film_etl/extract/omdb.py)



[src/film_etl/extract/tmdb.py](src/film_etl/extract/tmdb.py)



[src/film_etl/extract/wikidata.py](src/film_etl/extract/wikidata.py)



[src/film_etl/transform/clean.py](src/film_etl/transform/clean.py) — types, money parsing, joins, ROI



[src/film_etl/transform/sentiment.py](src/film_etl/transform/sentiment.py)



[src/film_etl/load/warehouse.py](src/film_etl/load/warehouse.py)



[src/film_etl/cli.py](src/film_etl/cli.py) — run, extract, transform, load



[config/lists.yaml](config/lists.yaml) — list URLs, max films, rate limits



[app/streamlit_app.py](app/streamlit_app.py)



[tests/fixtures/](tests/fixtures/) — saved HTML/JSON so tests and --offline never hit the network



[data/raw/](data/raw/) and [data/processed/](data/processed/) gitignored except a tiny sample

Extract

Letterboxd lists. Parse current LazyPoster markup (data-item-slug, data-item-link, data-item-name) and keep a legacy fallback (data-film-id / data-film-slug). Paginate /page/N/ and /detail/page/N/. Stop on 404 or a page with no new canonical https://letterboxd.com/film/<slug>/ URLs. Primary key is the film slug/URL, never title.

Letterboxd film pages. Parse JSON-LD Movie + visible stats + inline popular reviews. Cap reviews (default 12 per film from the film page). Do not crawl the full /reviews/ pagination wall (403s and a 256-page cap).

Polite scrape, not a bypass. requests + BeautifulSoup, identifiable User-Agent, 1–2s jittered delay, exponential backoff on 429/5xx, disk cache of raw HTML keyed by URL. If a public list page returns 403, try Jina Reader (https://r.jina.ai/http://letterboxd.com/...) as a read-only fallback and parse film links from markdown. No Cloudflare circumvention, no login, public lists only.

APIs. Session with retries. OMDb by title+year, then by imdbID once known. TMDB find-by-IMDb then details. Wikidata batched SPARQL for films still missing money. Missing keys: skip that source, log it, continue (do not crash the run).

Offline/demo mode. --offline (or missing keys) replays fixtures so the pipeline is fully runnable in this environment. Default demo list: a short public list (e.g. 25–50 films) in config/lists.yaml.

Transform (Pandas)

Join on letterboxd_slug / imdb_id. Coerce money ("$292,576,195" / "N/A" → numeric), ratings, and counts. Deduplicate films that appear on multiple lists (keep source_lists as a list column).

Derived columns:





budget_usd, revenue_worldwide_usd, box_office_us_usd with budget_source / revenue_source (tmdb | wikidata | omdb)



roi = revenue / budget when budget > 0



Engagement: Letterboxd watches/likes/fans/reviews + OMDb imdbVotes + TMDB popularity/vote_count



match_quality (imdb_id | title_year | unmatched)

Sentiment keywords. Combine Letterboxd + TMDB review text per film. VADER sentence polarity, then TF-IDF / n-grams (1–2) within positive vs negative sentences. Persist top keywords with polarity and score. Keep TMDB catalog keywords in a separate table so tags and opinions are not mixed.

Load

SQLite warehouse at data/processed/films.db:





films — one row per film (identity, money, ratings, engagement)



list_membership — list_url, position, slug



reviews — source, author, rating, text



keywords_catalog — TMDB tags



keywords_sentiment — extracted terms + polarity



etl_runs — timestamps, film counts, source errors

Also write films.parquet / films.csv for spreadsheet use. Loads are replace-or-upsert by slug so reruns are idempotent.

Explorer

Streamlit on an uncommon port (e.g. 8517): searchable film table, money vs rating scatter, keyword cloud/table filtered by polarity, empty/error states when the warehouse is missing. This is how you inspect a run; the CLI is the pipeline.

Secrets and local run

.env.example with OMDB_API_KEY and TMDB_API_KEY (TMDB v4 read token or v3 key). No keys required for --offline. README: get a free OMDb key at omdbapi.com and TMDB token at themoviedb.org.

uv sync
cp .env.example .env   # optional
uv run film-etl run --config config/lists.yaml
uv run streamlit run app/streamlit_app.py --server.port 8517

Tests

Fixture-based parsers for LazyPoster lists, JSON-LD film pages, OMDb/TMDB payloads, money parsing, joins, and sentiment keyword extraction. One CLI smoke test in --offline mode that produces a non-empty SQLite file.

Out of scope

Login-walled Letterboxd pages, full-history review crawls, Box Office Mojo scraping, paid LLM keyword extraction, Docker/Postgres, auth.

