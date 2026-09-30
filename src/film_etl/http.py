"""The only module that touches the network: polite, disk-cached GETs, plus an offline twin."""

import hashlib
import json
import logging
import random
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from film_etl.config import ScrapeSettings, Settings

logger = logging.getLogger(__name__)

Params = dict[str, Any] | None

SECRET_PARAMS = frozenset({"api_key", "apikey"})
API_HOSTS = ("omdbapi.com", "themoviedb.org", "wikidata.org")
API_DELAY_S = 0.25
RETRY_STATUSES = (429, 500, 502, 503, 504)
# 404 is permanent, so caching it saves a request on every rerun. 403 and 5xx may be transient.
CACHEABLE_STATUSES = frozenset({200, 404})
TIMEOUT_S = 30


def redacted_url(url: str, params: Params = None) -> str:
    """URL plus sorted query params, with secret params removed."""
    safe = sorted((k, str(v)) for k, v in (params or {}).items() if k.lower() not in SECRET_PARAMS)
    return f"{url}?{urlencode(safe)}" if safe else url


def cache_key(url: str, params: Params = None, method: str = "GET") -> str:
    """Human-readable request identity; safe to log and to store in the fixture manifest."""
    return f"{method} {redacted_url(url, params)}"


class HttpClient:
    """Throttled, retrying, disk-caching GET client for public pages and APIs."""

    def __init__(self, scrape: ScrapeSettings, cache_dir: Path, refresh: bool = False) -> None:
        self._scrape = scrape
        self._cache_dir = cache_dir
        self._refresh = refresh
        self._last_request: dict[str, float] = {}
        self.session = _build_session(scrape)

    def get_text(self, url: str, params: Params = None) -> str | None:
        return self._get(url, params, headers=None)

    def get_json(
        self, url: str, params: Params = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any] | None:
        return _parse_json(self._get(url, params, headers), cache_key(url, params))

    def _get(self, url: str, params: Params, headers: dict[str, str] | None) -> str | None:
        key = cache_key(url, params)
        body_path, meta_path = self._cache_paths(url, key)
        if not self._refresh and meta_path.exists():
            logger.debug("cache hit: %s", key)
            return _read_cache(body_path, meta_path)

        response = self._send(url, params, headers, key)
        if response is None:
            return None
        if response.status_code in CACHEABLE_STATUSES:
            _write_cache(body_path, meta_path, redacted_url(url, params), response)
        if response.status_code != 200:
            logger.warning("HTTP %s, skipping: %s", response.status_code, key)
            return None
        return response.text

    def _send(
        self, url: str, params: Params, headers: dict[str, str] | None, key: str
    ) -> requests.Response | None:
        self._throttle(urlsplit(url).hostname or "")
        try:
            return self.session.get(url, params=params, headers=headers, timeout=TIMEOUT_S)
        except requests.RequestException as exc:
            # str(exc) can echo the full request URL, api keys included, so log the type only.
            logger.warning("request failed (%s), skipping: %s", type(exc).__name__, key)
            return None

    def _throttle(self, host: str) -> None:
        if _is_api_host(host):
            delay = API_DELAY_S
        else:
            delay = random.uniform(self._scrape.delay_min_s, self._scrape.delay_max_s)
        last = self._last_request.get(host)
        if last is not None:
            wait = delay - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_request[host] = time.monotonic()

    def _cache_paths(self, url: str, key: str) -> tuple[Path, Path]:
        host_dir = self._cache_dir / (urlsplit(url).hostname or "unknown-host")
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return host_dir / f"{digest}.body", host_dir / f"{digest}.meta.json"


class FixtureClient:
    """Offline stand-in for HttpClient: replays files listed in <fixtures>/manifest.json."""

    def __init__(self, fixtures_dir: Path) -> None:
        self._fixtures_dir = fixtures_dir
        manifest_path = fixtures_dir / "manifest.json"
        self._manifest: dict[str, str] = (
            json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        )

    def get_text(self, url: str, params: Params = None) -> str | None:
        key = cache_key(url, params)
        relative_path = self._manifest.get(key)
        if relative_path is None:
            logger.debug("no fixture for %s", key)
            return None
        return (self._fixtures_dir / relative_path).read_text(encoding="utf-8")

    def get_json(
        self, url: str, params: Params = None, headers: dict[str, str] | None = None
    ) -> dict[str, Any] | None:
        return _parse_json(self.get_text(url, params), cache_key(url, params))


def make_client(
    settings: Settings, offline: bool, refresh: bool = False
) -> HttpClient | FixtureClient:
    if offline:
        return FixtureClient(settings.paths.fixtures)
    return HttpClient(settings.scrape, settings.paths.raw, refresh=refresh)


def _build_session(scrape: ScrapeSettings) -> requests.Session:
    retry = Retry(
        total=scrape.max_retries,
        backoff_factor=1,
        status_forcelist=RETRY_STATUSES,
        respect_retry_after_header=True,
        # Hand back the final 5xx/429 response instead of raising, so callers just get None.
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers["User-Agent"] = f"film-etl/0.1 (+{scrape.contact})"
    return session


def _is_api_host(host: str) -> bool:
    return any(host == api or host.endswith(f".{api}") for api in API_HOSTS)


def _read_cache(body_path: Path, meta_path: Path) -> str | None:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta["status"] != 200:
        return None
    return body_path.read_text(encoding="utf-8")


def _write_cache(body_path: Path, meta_path: Path, url: str, response: requests.Response) -> None:
    body_path.parent.mkdir(parents=True, exist_ok=True)
    # Body first: a meta file is what marks an entry as complete, so a crash never leaves a
    # meta pointing at a missing body.
    body_path.write_text(response.text, encoding="utf-8")
    meta = {
        "url": url,
        "status": response.status_code,
        "fetched_at": datetime.now(UTC).isoformat(),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _parse_json(text: str | None, key: str) -> dict[str, Any] | None:
    if text is None:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("invalid JSON, skipping: %s", key)
        return None
    return data if isinstance(data, dict) else None
