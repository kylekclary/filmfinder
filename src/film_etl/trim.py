"""Shrink captured Letterboxd HTML to the parts parsers need, so fixtures stay small."""

from bs4 import BeautifulSoup, Comment, Tag

# Kept from full pages, in document order. Everything else in <body> is dropped.
PAGE_SELECTORS = (
    "ul.poster-list",  # list poster grid (LazyPoster or legacy markup)
    "div.pagination",
    "p.text-footer",  # runtime plus the IMDb and TMDB links
    "[data-src$='/stats/']",  # placeholder that the stats fragment fills
    "section.ratings-histogram-chart",  # fans count plus the histogram placeholder
    "section.film-reviews",  # popular reviews, rendered inline
)
DROP_TAGS = (
    "script",
    "style",
    "noscript",
    "iframe",
    "img",
    "picture",
    "source",
    "form",
    "input",
    "button",
    "template",
    "link",
    "meta",
)
# Decorative wrappers with no data: poster frames, avatars, like/translate buttons.
# Legacy list markup puts the film id and slug on div.poster itself, so that one stays.
DROP_SELECTORS = ("div.poster:not([data-film-slug])", "a.avatar", ".viewing-actions")
# Poster markup carries ~1 KB of rendering JSON per film; only identity and text attributes stay.
KEEP_ATTRS = frozenset(
    {
        "class",
        "id",
        "href",
        "title",
        "datetime",
        "lang",
        "aria-label",
        "data-src",
        "data-type",
        "data-component-class",
        "data-item-name",
        "data-item-slug",
        "data-item-link",
        "data-list-index",
        "data-person",
        "data-viewing-id",
        "data-original-title",
        "data-track-action",
        "data-full-text-url",
    }
)
KEEP_ATTR_PREFIXES = ("data-film-", "data-tmdb-")


def trim_page(html: str) -> str:
    """Rebuild a full page from its JSON-LD scripts and the sections in PAGE_SELECTORS."""
    soup = BeautifulSoup(html, "lxml")
    out = BeautifulSoup("<!DOCTYPE html><html><head></head><body></body></html>", "lxml")
    assert out.head is not None and out.body is not None
    for script in soup.select('script[type="application/ld+json"]'):
        out.head.append(script.extract())
    if soup.body is not None:
        out.body.attrs = _kept_attrs(soup.body.attrs)
    for section in _outermost(soup.select(", ".join(PAGE_SELECTORS))):
        out.body.append(section.extract())
        out.body.append("\n")
    _clean(out.body)
    return str(out)


def clean_fragment(html: str) -> str:
    """Tidy a /csi/ fragment in place; fragments are already small and fully relevant."""
    soup = BeautifulSoup(html, "lxml")
    root = soup.body or soup
    _clean(root)
    return root.decode_contents().strip() + "\n"


def _outermost(tags: list[Tag]) -> list[Tag]:
    """Drop matches nested inside another match so nothing is kept twice."""
    chosen = {id(tag) for tag in tags}
    return [tag for tag in tags if not any(id(parent) in chosen for parent in tag.parents)]


def _clean(root: Tag) -> None:
    for comment in root.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()
    for tag in root.find_all(DROP_TAGS):
        tag.decompose()
    for tag in root.select(", ".join(DROP_SELECTORS)):
        tag.decompose()
    for svg in root.find_all("svg"):
        # Star ratings live in the <svg> aria-label/<title>; the path data is just drawing.
        for child in svg.find_all(lambda tag: tag.name != "title", recursive=False):
            child.decompose()
    for tag in root.find_all(True):
        tag.attrs = _kept_attrs(tag.attrs)
    for text in root.find_all(string=True):
        if not text.strip():
            text.replace_with(" ")


def _kept_attrs(attrs: dict[str, object]) -> dict[str, object]:
    return {
        name: value
        for name, value in attrs.items()
        if name in KEEP_ATTRS or name.startswith(KEEP_ATTR_PREFIXES)
    }
