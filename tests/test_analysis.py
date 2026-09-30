import math

import pytest

from my_actor.chunking import recommend_chunking
from my_actor.duplicates import DuplicateIndex
from my_actor.extraction import extract_html
from my_actor.models import Page
from my_actor.scoring import score
from my_actor.tokens import estimate_tokens, word_units


@pytest.mark.parametrize(
    "text", ["", "hello", "abc " * 10000, "日本語の文書"], ids=["empty", "short", "long", "unicode"]
)
def test_tokens(text):
    assert estimate_tokens(text) == math.ceil(len(text) / 4)
    assert estimate_tokens(text) == estimate_tokens(text)


def test_duplicates():
    idx = DuplicateIndex()
    text = " ".join(f"instruction{i} configuration{i} reference{i}" for i in range(200))
    pages = [Page(source_id=str(i), word_count=600) for i in range(4)]
    idx.apply(pages[0], text)
    idx.apply(pages[1], text)
    idx.apply(pages[2], text.upper() + "  \n")
    idx.apply(pages[3], text + " additional instruction")
    assert pages[0].duplicate_status == "unique"
    assert pages[1].duplicate_match == "exact"
    assert pages[2].duplicate_match == "normalized_exact"
    assert pages[3].duplicate_status == "near_duplicate"
    assert pages[3].duplicate_of == "0"


def test_unrelated_and_short():
    idx = DuplicateIndex()
    for i, text in enumerate(("one short text", "one short item", "completely different words")):
        page = Page(source_id=str(i), word_count=3)
        idx.apply(page, text)
        assert page.duplicate_status == "unique"
    assert not idx.fingerprints


def test_unrelated_cjk_and_long_content():
    texts = [
        "文書の内容を確認して検索用の知識基盤を準備します。" * 10,
        "山川森林河流鳥魚花草天地日月星空。" * 10,
        " ".join(f"unrelated{i} astronomy{i} molecule{i}" for i in range(200)),
    ]
    idx = DuplicateIndex()
    for index, text in enumerate(texts):
        page = Page(source_id=str(index), word_count=len(word_units(text)))
        idx.apply(page, text)
        assert page.duplicate_status == "unique"
    assert all(fingerprint.bits != 0 for fingerprint in idx.fingerprints)


@pytest.mark.parametrize("words", [0, 1, 30, 60, 200, 600, 1000000])
@pytest.mark.parametrize(
    "duplicate", ["unique", "exact_duplicate", "near_duplicate", "not_checked"]
)
def test_score_invariants(words, duplicate):
    p = score(Page(word_count=words, duplicate_status=duplicate))
    assert 0 <= p.rag_readiness_score <= 100
    assert p.rag_readiness_score == pytest.approx(sum(p.score_breakdown.values()))
    if duplicate in {"exact_duplicate", "near_duplicate"}:
        assert not p.recommended_for_rag


def test_good_and_weak(fixture_text):
    good = score(
        extract_html(fixture_text("docs.html"), Page(url="https://example.com/docs/a")).page
    )
    weak = score(extract_html(fixture_text("spa.html"), Page()).page)
    assert good.rag_readiness_score >= 85 and good.recommended_for_rag
    assert weak.rag_readiness_score < 50 and not weak.recommended_for_rag
    assert good.score_breakdown["metadata"] == 10
    assert score(Page(word_count=200)).score_breakdown["metadata"] == 0


@pytest.mark.parametrize(
    "tokens,profile,headings,size,overlap",
    [
        (0, "unknown", 0, 0, 0),
        (100, "short_content", 0, 100, 0),
        (500, "article", 2, 384, 48),
        (1000, "documentation", 3, 512, 64),
        (3000, "documentation", 6, 768, 96),
        (1000, "faq", 6, 256, 32),
    ],
)
def test_chunking(tokens, profile, headings, size, overlap):
    p = Page(estimated_tokens=tokens, page_profile=profile, heading_count=headings)
    recommend_chunking(p)
    assert (p.recommended_chunk_size, p.recommended_chunk_overlap) == (size, overlap)
