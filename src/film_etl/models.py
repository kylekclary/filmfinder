"""Record types passed between extract, transform and load. Fields only, no behaviour."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class ListEntry:
    """One film's appearance on a Letterboxd list."""

    list_url: str
    position: int
    slug: str
    film_url: str
    title: str | None = None
    year: int | None = None


@dataclass(slots=True)
class Review:
    """A single review from Letterboxd or TMDB."""

    source: str  # "letterboxd" | "tmdb"
    author: str | None
    text: str
    rating: float | None = None


@dataclass(slots=True)
class FilmPage:
    """What a Letterboxd film page exposes: JSON-LD, stats and inline popular reviews."""

    slug: str
    url: str
    title: str
    year: int | None = None
    directors: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)
    average_rating: float | None = None
    rating_count: int | None = None
    watches: int | None = None
    likes: int | None = None
    fans: int | None = None
    lists: int | None = None
    review_count: int | None = None
    imdb_id: str | None = None
    tmdb_id: int | None = None
    reviews: list[Review] = field(default_factory=list)


@dataclass(slots=True)
class OmdbRecord:
    """OMDb ratings/plot layer. OMDb has no budget and BoxOffice is US-only."""

    imdb_id: str
    title: str | None = None
    year: int | None = None
    rated: str | None = None
    runtime_min: int | None = None
    plot: str | None = None
    awards: str | None = None
    imdb_rating: float | None = None
    imdb_votes: int | None = None
    rotten_tomatoes_pct: int | None = None
    metacritic: int | None = None
    box_office_us_usd: int | None = None


@dataclass(slots=True)
class TmdbRecord:
    """TMDB details with appended keywords and reviews."""

    tmdb_id: int
    imdb_id: str | None = None
    budget_usd: int | None = None
    revenue_usd: int | None = None
    popularity: float | None = None
    vote_average: float | None = None
    vote_count: int | None = None
    keywords: list[str] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)


@dataclass(slots=True)
class WikidataMoney:
    """Budget (P2130) and box office (P2142) for one film, keyed by IMDb id (P345)."""

    imdb_id: str
    wikidata_id: str
    budget_usd: int | None = None
    box_office_usd: int | None = None
