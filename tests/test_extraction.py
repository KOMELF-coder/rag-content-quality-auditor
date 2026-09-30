import pytest

from my_actor.extraction import extract_html, extract_text
from my_actor.models import Page


def test_docs(fixture_text):
    result = extract_html(fixture_text("docs.html"), Page(url="https://example.com/docs/setup"))
    p = result.page
    assert p.has_canonical and p.has_meta_description and p.has_json_ld
    assert p.canonical_url == "https://example.com/docs/setup"
    assert p.heading_count == 3 and p.h1_count == 1 and p.h2_count == 2
    assert p.table_count == p.code_block_count == p.list_count == 1
    assert p.word_count > 80 and 0 <= p.boilerplate_ratio <= 1
    assert "footer" not in result.text and "@type" not in result.text


@pytest.mark.parametrize(
    "name", ["article.html", "malformed.html", "multilingual.html", "faq.html"]
)
def test_content_fixtures(fixture_text, name):
    result = extract_html(fixture_text(name), Page(url="https://example.com/a"))
    assert result.text and result.page.word_count > 5


def test_shell(fixture_text):
    assert (
        extract_html(fixture_text("spa.html"), Page()).page.content_status
        == "likely_requires_javascript"
    )
    assert extract_html("<main>Short but useful</main>", Page()).page.content_status == "too_short"


def test_cookie(fixture_text):
    text = extract_html(fixture_text("cookie.html"), Page()).text
    assert "Accept cookies" not in text
    assert "Legitimate documentation" in text


def test_heavy_navigation():
    result = extract_html(
        "<nav>" + "Menus and navigation " * 100 + "</nav><main><p>Useful text</p></main>", Page()
    )
    assert result.page.boilerplate_ratio > 0.9


def test_markdown():
    result = extract_text(
        "# Guide\n\nThis [link](https://example.com) explains setup.\n\n```py\nprint(1)\n```",
        Page(),
        markdown=True,
    )
    assert result.page.title == "Guide"
    assert result.page.heading_count == result.page.code_block_count == 1
    assert not result.page.metadata_available
