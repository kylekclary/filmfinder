from pathlib import Path

import pytest

from film_etl.config import load_settings

CONFIG_PATH = Path(__file__).parents[1] / "config" / "lists.yaml"


@pytest.fixture
def no_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMDB_API_KEY", raising=False)
    monkeypatch.delenv("TMDB_API_KEY", raising=False)


@pytest.mark.usefixtures("no_key_env")
def test_loads_yaml_with_api_keys_absent(tmp_path: Path) -> None:
    settings = load_settings(CONFIG_PATH, env_path=tmp_path / "missing.env")

    assert settings.omdb_api_key is None
    assert settings.tmdb_api_key is None
    assert not settings.has_omdb
    assert not settings.has_tmdb
    assert len(settings.lists) == 1
    assert settings.lists[0].max_films == 30
    assert settings.scrape.contact.startswith("https://")
    assert settings.scrape.delay_min_s == 1.0
    assert settings.scrape.delay_max_s == 2.0
    assert settings.scrape.max_retries == 4
    assert settings.scrape.reviews_per_film == 12
    assert settings.paths.raw == Path("data/raw")


@pytest.mark.usefixtures("no_key_env")
def test_blank_keys_from_env_example_count_as_absent(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("OMDB_API_KEY=\nTMDB_API_KEY=abc123\n", encoding="utf-8")

    settings = load_settings(CONFIG_PATH, env_path=env_path)

    assert not settings.has_omdb
    assert settings.has_tmdb
    assert settings.tmdb_api_key == "abc123"
