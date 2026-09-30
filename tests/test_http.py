import json
import logging
from pathlib import Path

import pytest
import requests
from requests.adapters import HTTPAdapter

from film_etl.config import ScrapeSettings
from film_etl.http import FixtureClient, HttpClient, cache_key

SECRET = "s3cr3t-key-value"
FILM_URL = "https://letterboxd.com/film/parasite-2019/"
OMDB_URL = "https://www.omdbapi.com/"


class FakeAdapter(HTTPAdapter):
    """Stands in for the network: records each request and returns a canned response."""

    def __init__(self, status: int = 200, body: str = "ok", error: Exception | None = None):
        super().__init__()
        self.status = status
        self.body = body
        self.error = error
        self.sent: list[requests.PreparedRequest] = []

    def send(self, request: requests.PreparedRequest, **kwargs: object) -> requests.Response:
        self.sent.append(request)
        if self.error is not None:
            raise self.error
        response = requests.Response()
        response.status_code = self.status
        response._content = self.body.encode("utf-8")
        response.encoding = "utf-8"
        response.url = request.url or ""
        response.request = request
        return response


def make_client(cache_dir: Path, adapter: FakeAdapter, refresh: bool = False) -> HttpClient:
    scrape = ScrapeSettings(
        contact="https://example.test/contact",
        delay_min_s=0.0,
        delay_max_s=0.0,
        max_retries=0,
        reviews_per_film=12,
    )
    client = HttpClient(scrape, cache_dir, refresh=refresh)
    client.session.mount("https://", adapter)
    return client


def read_all_cache_files(cache_dir: Path) -> str:
    return "\n".join(
        f"{path.name}\n{path.read_text(encoding='utf-8')}"
        for path in cache_dir.rglob("*")
        if path.is_file()
    )


def test_cache_hit_skips_network(tmp_path: Path) -> None:
    adapter = FakeAdapter(body="<html>film</html>")
    client = make_client(tmp_path, adapter)

    first = client.get_text(FILM_URL)
    second = client.get_text(FILM_URL)

    assert first == second == "<html>film</html>"
    assert len(adapter.sent) == 1
    assert adapter.sent[0].headers["User-Agent"] == "film-etl/0.1 (+https://example.test/contact)"


def test_refresh_bypasses_cache_read_but_still_writes(tmp_path: Path) -> None:
    make_client(tmp_path, FakeAdapter(body="old")).get_text(FILM_URL)

    refreshed = make_client(tmp_path, FakeAdapter(body="new"), refresh=True)
    assert refreshed.get_text(FILM_URL) == "new"

    offline_adapter = FakeAdapter(body="should not be fetched")
    assert make_client(tmp_path, offline_adapter).get_text(FILM_URL) == "new"
    assert offline_adapter.sent == []


def test_secrets_stripped_from_key_meta_and_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    adapter = FakeAdapter(body='{"Title": "Parasite"}')
    client = make_client(tmp_path, adapter)
    params = {"i": "tt6751668", "apikey": SECRET}

    assert client.get_json(OMDB_URL, params=params) == {"Title": "Parasite"}

    assert SECRET in (adapter.sent[0].url or "")
    assert cache_key(OMDB_URL, params) == "GET https://www.omdbapi.com/?i=tt6751668"
    assert cache_key(OMDB_URL, {"api_key": SECRET}) == "GET https://www.omdbapi.com/"
    [meta_path] = tmp_path.rglob("*.meta.json")
    assert json.loads(meta_path.read_text(encoding="utf-8"))["url"] == (
        "https://www.omdbapi.com/?i=tt6751668"
    )
    assert SECRET not in read_all_cache_files(tmp_path)
    assert SECRET not in caplog.text


def test_404_returns_none_and_logs_once(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    client = make_client(tmp_path, FakeAdapter(status=404, body="not found"))

    with caplog.at_level(logging.WARNING):
        assert client.get_text(FILM_URL) is None

    assert len(caplog.records) == 1
    assert "404" in caplog.records[0].getMessage()


def test_connection_error_returns_none_without_leaking_secret(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    error = requests.ConnectionError(f"failed: {OMDB_URL}?apikey={SECRET}")
    client = make_client(tmp_path, FakeAdapter(error=error))

    assert client.get_json(OMDB_URL, params={"apikey": SECRET}) is None
    assert SECRET not in caplog.text


def test_fixture_client_reads_from_manifest(tmp_path: Path) -> None:
    (tmp_path / "omdb").mkdir()
    (tmp_path / "omdb" / "tt6751668.json").write_text('{"Title": "Parasite"}', encoding="utf-8")
    manifest = {cache_key(OMDB_URL, {"i": "tt6751668"}): "omdb/tt6751668.json"}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    client = FixtureClient(tmp_path)

    assert client.get_json(OMDB_URL, params={"i": "tt6751668", "apikey": SECRET}) == {
        "Title": "Parasite"
    }
    assert client.get_text("https://letterboxd.com/film/missing/") is None
