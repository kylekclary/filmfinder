from film_etl.trim import clean_fragment, trim_page

PAGE = """<!DOCTYPE html><html><head>
<title>Harakiri</title><link rel="stylesheet" href="/x.css">
<script>trackPageView()</script>
<script type="application/ld+json">{"@type": "Movie", "name": "Harakiri"}</script>
</head><body class="film" data-tmdb-id="14537" data-junk="x">
<nav>site navigation</nav>
<ul class="poster-list -grid">
  <li class="posteritem"><div class="react-component" data-component-class="LazyPoster"
      data-item-slug="harakiri" data-item-link="/film/harakiri/" data-item-name="Harakiri (1962)"
      data-postered-identifier='{"huge": "json"}'>
    <div class="poster film-poster"><img src="/poster.jpg" alt="Harakiri"></div>
  </div></li>
</ul>
<div class="pagination"><a class="next" href="/list/page/2/">Next</a></div>
<section class="film-reviews"><article data-person="ciaram">
  <svg aria-label="★★★★★" class="glyph -rating"><title>★★★★★</title><path d="M0 0"/></svg>
  <!-- a comment --><p>Magnificent.</p>
</article></section>
<footer>footer links</footer>
</body></html>"""


def test_trim_page_keeps_data_sections_and_drops_the_rest() -> None:
    trimmed = trim_page(PAGE)

    assert '"name": "Harakiri"' in trimmed
    assert 'data-tmdb-id="14537"' in trimmed
    assert 'data-item-slug="harakiri"' in trimmed
    assert 'href="/list/page/2/"' in trimmed
    assert 'data-person="ciaram"' in trimmed
    assert 'aria-label="★★★★★"' in trimmed
    assert "Magnificent." in trimmed
    for dropped in (
        "trackPageView",
        "site navigation",
        "footer links",
        "<img",
        "<path",
        "data-postered-identifier",
        "data-junk",
        "a comment",
        "film-poster",
    ):
        assert dropped not in trimmed


def test_trim_page_keeps_legacy_poster_markup() -> None:
    legacy = (
        '<html><body><ul class="poster-list"><li><div class="poster film-poster" '
        'data-film-id="51700" data-film-slug="12-angry-men"></div></li></ul></body></html>'
    )

    trimmed = trim_page(legacy)

    assert 'data-film-slug="12-angry-men"' in trimmed
    assert 'data-film-id="51700"' in trimmed


def test_clean_fragment_keeps_content_without_wrapping_it() -> None:
    fragment = '<div class="rating-histogram"><a title="503 ratings" style="x">4.7</a></div>'

    cleaned = clean_fragment(fragment)

    assert cleaned == '<div class="rating-histogram"><a title="503 ratings">4.7</a></div>\n'
