"""Load config/lists.yaml and .env into one immutable Settings object."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

DEFAULT_CONFIG_PATH = Path("config/lists.yaml")
DEFAULT_ENV_PATH = Path(".env")


@dataclass(frozen=True, slots=True)
class ListSource:
    url: str
    name: str
    max_films: int


@dataclass(frozen=True, slots=True)
class ScrapeSettings:
    delay_min_s: float
    delay_max_s: float
    max_retries: int
    reviews_per_film: int


@dataclass(frozen=True, slots=True)
class PathSettings:
    raw: Path
    processed: Path
    fixtures: Path


@dataclass(frozen=True, slots=True)
class Settings:
    lists: tuple[ListSource, ...]
    scrape: ScrapeSettings
    paths: PathSettings
    omdb_api_key: str | None = None
    tmdb_api_key: str | None = None

    @property
    def has_omdb(self) -> bool:
        return self.omdb_api_key is not None

    @property
    def has_tmdb(self) -> bool:
        return self.tmdb_api_key is not None


def load_settings(
    config_path: Path = DEFAULT_CONFIG_PATH,
    env_path: Path = DEFAULT_ENV_PATH,
) -> Settings:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    env_file = dotenv_values(env_path) if env_path.exists() else {}
    return Settings(
        lists=_parse_lists(raw.get("lists", [])),
        scrape=_parse_scrape(raw["scrape"]),
        paths=_parse_paths(raw["paths"]),
        omdb_api_key=_read_key("OMDB_API_KEY", env_file),
        tmdb_api_key=_read_key("TMDB_API_KEY", env_file),
    )


def _parse_lists(items: list[dict[str, Any]]) -> tuple[ListSource, ...]:
    return tuple(
        ListSource(url=item["url"], name=item["name"], max_films=int(item["max_films"]))
        for item in items
    )


def _parse_scrape(section: dict[str, Any]) -> ScrapeSettings:
    return ScrapeSettings(
        delay_min_s=float(section["delay_min_s"]),
        delay_max_s=float(section["delay_max_s"]),
        max_retries=int(section["max_retries"]),
        reviews_per_film=int(section["reviews_per_film"]),
    )


def _parse_paths(section: dict[str, Any]) -> PathSettings:
    return PathSettings(
        raw=Path(section["raw"]),
        processed=Path(section["processed"]),
        fixtures=Path(section["fixtures"]),
    )


def _read_key(name: str, env_file: dict[str, str | None]) -> str | None:
    # The shell environment wins over .env so a one-off override needs no file edit.
    # Blank values (as copied from .env.example) count as absent.
    value = os.environ.get(name) or env_file.get(name) or ""
    return value.strip() or None
