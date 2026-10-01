import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
NOT_FIXTURES = {"manifest.json", "README.md"}


def load_manifest() -> dict[str, dict[str, object]]:
    return json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))


def test_every_fixture_is_in_the_manifest_and_every_entry_exists() -> None:
    manifest = load_manifest()
    listed = {entry["path"] for entry in manifest.values()}
    on_disk = {
        path.relative_to(FIXTURES).as_posix()
        for path in FIXTURES.rglob("*")
        if path.is_file() and path.name not in NOT_FIXTURES
    }

    assert listed == on_disk
    assert all(isinstance(entry["synthetic"], bool) for entry in manifest.values())


def test_fixtures_contain_no_secrets() -> None:
    for key in load_manifest():
        assert "apikey=" not in key.lower()
        assert "api_key=" not in key.lower()


def test_fixtures_stay_small() -> None:
    total = sum(path.stat().st_size for path in FIXTURES.rglob("*") if path.is_file())

    assert total < 2_000_000
