"""Command-line entry point (`film-etl`): one command per pipeline stage plus `run`."""

import logging
from pathlib import Path
from typing import Annotated

import typer

from film_etl.capture import capture_fixtures, fixtures_size
from film_etl.config import DEFAULT_CONFIG_PATH, load_settings
from film_etl.http import HttpClient

logger = logging.getLogger(__name__)

app = typer.Typer(
    help="Scrape Letterboxd lists, enrich via OMDb/TMDB/Wikidata, load to SQLite.",
    no_args_is_help=True,
    add_completion=False,
)

ConfigOption = Annotated[Path, typer.Option("--config", help="Path to the lists/scrape YAML.")]
OfflineOption = Annotated[
    bool, typer.Option("--offline", help="Replay tests/fixtures instead of using the network.")
]
VerboseOption = Annotated[bool, typer.Option("--verbose", "-v", help="Log debug detail.")]


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _not_implemented(stage: str, config: Path, offline: bool, verbose: bool) -> None:
    _configure_logging(verbose)
    logger.info("%s: not implemented (config=%s, offline=%s)", stage, config, offline)


@app.command()
def run(
    config: ConfigOption = DEFAULT_CONFIG_PATH,
    offline: OfflineOption = False,
    verbose: VerboseOption = False,
) -> None:
    """Run extract, transform and load in order."""
    _not_implemented("run", config, offline, verbose)


@app.command()
def extract(
    config: ConfigOption = DEFAULT_CONFIG_PATH,
    offline: OfflineOption = False,
    verbose: VerboseOption = False,
) -> None:
    """Scrape Letterboxd and call the enrichment APIs into the raw cache."""
    _not_implemented("extract", config, offline, verbose)


@app.command()
def transform(
    config: ConfigOption = DEFAULT_CONFIG_PATH,
    offline: OfflineOption = False,
    verbose: VerboseOption = False,
) -> None:
    """Clean, join and derive columns from the raw cache."""
    _not_implemented("transform", config, offline, verbose)


@app.command()
def load(
    config: ConfigOption = DEFAULT_CONFIG_PATH,
    offline: OfflineOption = False,
    verbose: VerboseOption = False,
) -> None:
    """Write transformed tables to SQLite and Parquet/CSV."""
    _not_implemented("load", config, offline, verbose)


@app.command("capture-fixtures")
def capture_fixtures_command(
    list_url: Annotated[
        str | None,
        typer.Option(
            "--list-url", help="Letterboxd list to sample. Default: first list in config."
        ),
    ] = None,
    films: Annotated[int, typer.Option("--films", min=1, help="How many films to capture.")] = 10,
    config: ConfigOption = DEFAULT_CONFIG_PATH,
    verbose: VerboseOption = False,
) -> None:
    """Fetch a small live sample of every source into tests/fixtures/."""
    _configure_logging(verbose)
    settings = load_settings(config)
    client = HttpClient(settings.scrape, settings.paths.raw)
    writer = capture_fixtures(client, settings, list_url or settings.lists[0].url, films)
    total_kb = fixtures_size(settings.paths.fixtures) // 1000
    typer.echo(f"Wrote {len(writer.written)} fixtures; {settings.paths.fixtures} is {total_kb} KB.")
