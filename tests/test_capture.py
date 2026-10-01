import json
from pathlib import Path
from typing import Any

from film_etl.capture import OMDB_URL, TMDB_API, capture_fixtures, tmdb_auth
from film_etl.config import PathSettings, ScrapeSettings, Settings
from film_etl.http import cache_key

LIST_URL = "https://letterboxd.com/someone/list/demo/"
LIST_HTML = (
    '<html><body><ul class="poster-list"><li><div class="react-component" '
    'data-item-slug="harakiri" data-item-link="/film/harakiri/"></div></li></ul></body></html>'
)
FILM_HTML = (
    '<html><body data-tmdb-id="14537"><div class="csi" data-src="/csi/film/harakiri/stats/">'
    '</div><p class="text-footer"><a href="http://www.imdb.com/title/tt0056058/maindetails">'
    "IMDb</a></p></body></html>"
)


class StubClient:
    """Answers from a dict keyed by cache key and records what was asked for."""

    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.requested: list[str] = []

    def get_text(self, url: str, params: dict[str, Any] | None = None) -> str | None:
        key = cache_key(url, params)
        self.requested.append(key)
        return self.responses.get(key)

    def get_json(
        self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any] | None:
        return self.get_text(url, params)


def make_settings(fixtures_dir: Path, omdb: str | None, tmdb: str | None) -> Settings:
    return Settings(
        lists=(),
        scrape=ScrapeSettings("https://example.test", 0.0, 0.0, 0, 12),
        paths=PathSettings(raw=fixtures_dir / "raw", processed=fixtures_dir, fixtures=fixtures_dir),
        omdb_api_key=omdb,
        tmdb_api_key=tmdb,
    )


def test_capture_chains_list_to_film_to_apis_and_writes_manifest(tmp_path: Path) -> None:
    client = StubClient(
        {
            cache_key(LIST_URL): LIST_HTML,
            cache_key("https://letterboxd.com/film/harakiri/"): FILM_HTML,
            cache_key("https://letterboxd.com/csi/film/harakiri/stats/"): "<div>stats</div>",
            cache_key(OMDB_URL, {"i": "tt0056058"}): {"imdbID": "tt0056058"},
            cache_key(f"{TMDB_API}/find/tt0056058", {"external_source": "imdb_id"}): {
                "movie_results": [{"id": 14537}]
            },
            cache_key(f"{TMDB_API}/movie/14537", {"append_to_response": "keywords,reviews"}): {
                "id": 14537
            },
        }
    )
    settings = make_settings(tmp_path, omdb="omdb-secret", tmdb="tmdb-secret")

    capture_fixtures(client, settings, LIST_URL, films=5)

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    paths = {entry["path"] for entry in manifest.values()}
    assert paths == {
        "letterboxd/list_page1.html",
        "letterboxd/film_harakiri.html",
        "letterboxd/csi_harakiri_stats.html",
        "omdb/tt0056058.json",
        "tmdb/find_tt0056058.json",
        "tmdb/movie_14537.json",
    }
    assert "secret" not in (tmp_path / "manifest.json").read_text(encoding="utf-8")
    # No next-page link and no rating-histogram reference, so neither is requested.
    assert not any("page/2" in key or "rating-histogram" in key for key in client.requested)


def test_capture_skips_apis_without_keys(tmp_path: Path) -> None:
    client = StubClient(
        {
            cache_key(LIST_URL): LIST_HTML,
            cache_key("https://letterboxd.com/film/harakiri/"): FILM_HTML,
        }
    )

    capture_fixtures(client, make_settings(tmp_path, None, None), LIST_URL, films=5)

    assert not any("omdbapi" in key or "themoviedb" in key for key in client.requested)


def test_tmdb_auth_uses_header_for_v4_token_and_param_for_v3_key() -> None:
    assert tmdb_auth("eyJhbGciOi.payload.sig") == (
        {},
        {"Authorization": "Bearer eyJhbGciOi.payload.sig"},
    )
    assert tmdb_auth("abc123") == ({"api_key": "abc123"}, {})
