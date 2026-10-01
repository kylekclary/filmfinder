"""Fetch a small live sample of every source and save it under tests/fixtures/ for offline use.

This is a thin fetch-and-save loop, not the extractors: it pulls only the ids needed to chain
one source to the next (slug -> IMDb id -> TMDB id) and leaves real parsing to extract/.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from film_etl.config import Settings
from film_etl.http import HttpClient, cache_key
from film_etl.trim import clean_fragment, trim_page

logger = logging.getLogger(__name__)

LETTERBOXD = "https://letterboxd.com"
OMDB_URL = "https://www.omdbapi.com/"
TMDB_API = "https://api.themoviedb.org/3"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"

SLUG_RE = re.compile(r'data-(?:item|film)-slug="([^"]+)"')
IMDB_RE = re.compile(r"imdb\.com/title/(tt\d+)")
CSI_NAMES = ("stats", "rating-histogram", "popular-reviews")
PAGE_BUDGET_BYTES = 40_000
TOTAL_BUDGET_BYTES = 2_000_000


class FixtureWriter:
    """Writes fixture files and keeps manifest.json in step with them."""

    def __init__(self, fixtures_dir: Path) -> None:
        self.fixtures_dir = fixtures_dir
        self.manifest_path = fixtures_dir / "manifest.json"
        self.manifest: dict[str, dict[str, Any]] = (
            json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if self.manifest_path.exists()
            else {}
        )
        self.written: list[str] = []

    def save(self, key: str, relative_path: str, content: str) -> None:
        path = self.fixtures_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.manifest[key] = {"path": relative_path, "synthetic": False}
        self.written.append(relative_path)
        size = len(content.encode("utf-8"))
        if relative_path.endswith(".html") and size > PAGE_BUDGET_BYTES:
            logger.warning("%s is %d KB, over the 40 KB target", relative_path, size // 1000)

    def write_manifest(self) -> None:
        ordered = dict(sorted(self.manifest.items()))
        self.manifest_path.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")


def capture_fixtures(
    client: HttpClient, settings: Settings, list_url: str, films: int
) -> FixtureWriter:
    writer = FixtureWriter(settings.paths.fixtures)
    slugs = _capture_list(client, writer, list_url)[:films]
    imdb_ids = [imdb_id for slug in slugs if (imdb_id := _capture_film(client, writer, slug))]

    if settings.omdb_api_key is None:
        logger.warning("OMDB_API_KEY not set; skipping OMDb capture")
    else:
        for imdb_id in imdb_ids:
            _capture_omdb(client, writer, settings.omdb_api_key, imdb_id)
    if settings.tmdb_api_key is None:
        logger.warning("TMDB_API_KEY not set; skipping TMDB capture")
    else:
        for imdb_id in imdb_ids:
            _capture_tmdb(client, writer, settings.tmdb_api_key, imdb_id)
    _capture_wikidata(client, writer, imdb_ids)

    writer.write_manifest()
    total = fixtures_size(settings.paths.fixtures)
    if total > TOTAL_BUDGET_BYTES:
        logger.warning("fixtures total %d KB, over the 2 MB budget", total // 1000)
    return writer


def fixtures_size(fixtures_dir: Path) -> int:
    return sum(path.stat().st_size for path in fixtures_dir.rglob("*") if path.is_file())


def tmdb_auth(api_key: str) -> tuple[dict[str, str], dict[str, str]]:
    """Split a TMDB credential into (query params, headers)."""
    # v4 read tokens are JWTs (dotted) and go in a header; v3 keys go in the query string.
    if "." in api_key:
        return {}, {"Authorization": f"Bearer {api_key}"}
    return {"api_key": api_key}, {}


def money_query(imdb_ids: list[str]) -> str:
    """SPARQL for budget (P2130) and box office (P2142) with their currency units."""
    values = " ".join(f'"{imdb_id}"' for imdb_id in imdb_ids)
    return (
        "SELECT ?item ?imdb ?budget ?budgetUnit ?boxOffice ?boxOfficeUnit WHERE {\n"
        f"  VALUES ?imdb {{ {values} }}\n"
        "  ?item wdt:P345 ?imdb .\n"
        "  OPTIONAL { ?item p:P2130/psv:P2130 [ wikibase:quantityAmount ?budget;"
        " wikibase:quantityUnit ?budgetUnit ] . }\n"
        "  OPTIONAL { ?item p:P2142/psv:P2142 [ wikibase:quantityAmount ?boxOffice;"
        " wikibase:quantityUnit ?boxOfficeUnit ] . }\n"
        "}"
    )


def _capture_list(client: HttpClient, writer: FixtureWriter, list_url: str) -> list[str]:
    page1 = client.get_text(list_url)
    if page1 is None:
        logger.warning("could not fetch list %s; nothing to capture", list_url)
        return []
    writer.save(cache_key(list_url), "letterboxd/list_page1.html", trim_page(page1))
    pages = [page1]
    page2_url = f"{list_url.rstrip('/')}/page/2/"
    if urlsplit(page2_url).path in page1 and (page2 := client.get_text(page2_url)):
        writer.save(cache_key(page2_url), "letterboxd/list_page2.html", trim_page(page2))
        pages.append(page2)
    return list(dict.fromkeys(slug for page in pages for slug in SLUG_RE.findall(page)))


def _capture_film(client: HttpClient, writer: FixtureWriter, slug: str) -> str | None:
    url = f"{LETTERBOXD}/film/{slug}/"
    html = client.get_text(url)
    if html is None:
        return None
    writer.save(cache_key(url), f"letterboxd/film_{slug}.html", trim_page(html))
    for name in CSI_NAMES:
        # Only fetch fragments this page actually references.
        if f'"/csi/film/{slug}/{name}/"' not in html:
            continue
        csi_url = f"{LETTERBOXD}/csi/film/{slug}/{name}/"
        if fragment := client.get_text(csi_url):
            path = f"letterboxd/csi_{slug}_{name}.html"
            writer.save(cache_key(csi_url), path, clean_fragment(fragment))
    match = IMDB_RE.search(html)
    return match.group(1) if match else None


def _capture_omdb(client: HttpClient, writer: FixtureWriter, api_key: str, imdb_id: str) -> None:
    params = {"i": imdb_id, "apikey": api_key}
    if (data := client.get_json(OMDB_URL, params)) is not None:
        writer.save(cache_key(OMDB_URL, params), f"omdb/{imdb_id}.json", _pretty(data))


def _capture_tmdb(client: HttpClient, writer: FixtureWriter, api_key: str, imdb_id: str) -> None:
    auth_params, headers = tmdb_auth(api_key)
    find_url = f"{TMDB_API}/find/{imdb_id}"
    find_params = {"external_source": "imdb_id", **auth_params}
    found = client.get_json(find_url, find_params, headers)
    if found is None:
        return
    writer.save(cache_key(find_url, find_params), f"tmdb/find_{imdb_id}.json", _pretty(found))
    results = found.get("movie_results") or []
    if not results:
        logger.info("TMDB has no movie for %s", imdb_id)
        return
    tmdb_id = results[0]["id"]
    movie_url = f"{TMDB_API}/movie/{tmdb_id}"
    movie_params = {"append_to_response": "keywords,reviews", **auth_params}
    if (movie := client.get_json(movie_url, movie_params, headers)) is not None:
        path = f"tmdb/movie_{tmdb_id}.json"
        writer.save(cache_key(movie_url, movie_params), path, _pretty(movie))


def _capture_wikidata(client: HttpClient, writer: FixtureWriter, imdb_ids: list[str]) -> None:
    if not imdb_ids:
        return
    params = {"query": money_query(imdb_ids), "format": "json"}
    headers = {"Accept": "application/sparql-results+json"}
    if (data := client.get_json(WIKIDATA_SPARQL_URL, params, headers)) is not None:
        writer.save(
            cache_key(WIKIDATA_SPARQL_URL, params), "wikidata/money_batch.json", _pretty(data)
        )


def _pretty(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"
