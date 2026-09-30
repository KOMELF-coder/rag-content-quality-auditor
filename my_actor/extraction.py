import re
from itertools import pairwise
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from .limits import MAX_LINKS_PER_PAGE, MAX_SOURCE_CHARS
from .metadata import extract_metadata
from .models import AuditError, Extracted, Page
from .tokens import word_units
from .url_policy import normalize_url


def clean_text(text: str) -> str:
    return "\n".join(
        line for line in (" ".join(line.split()) for line in text.splitlines()) if line
    )


def count_words(text: str) -> int:
    # Han/Hiragana/Katakana characters count as units where spaces are absent.
    return len(word_units(text))


def finish_metrics(page: Page, text: str, *, js_shell=False) -> None:
    page.main_content_chars = len(text)
    page.word_count = count_words(text)
    page.boilerplate_ratio = round(
        max(0.0, min(1.0, 1 - len(text) / max(page.raw_text_chars, 1))), 4
    )
    page.content_status = (
        "likely_requires_javascript"
        if js_shell
        else "empty"
        if not text
        else "too_short"
        if page.word_count < 30
        else "ok"
    )


def extract_html(html: str, page: Page) -> Extracted:
    if len(html) > MAX_SOURCE_CHARS:
        raise AuditError("too_large", "Document exceeds the source character limit.")
    page.raw_html_chars = len(html)
    soup = BeautifulSoup(html, "html.parser")
    extract_metadata(soup, page)
    scripts = len(soup.find_all("script"))
    shell_marker = bool(soup.find(id=re.compile(r"^(root|app|__next|__nuxt)$", re.IGNORECASE)))
    framework = any(
        marker in html for marker in ("__NEXT_DATA__", "ng-version=", "data-reactroot", "__NUXT__")
    )
    links = {}
    for link in soup.find_all("a", href=True, limit=MAX_LINKS_PER_PAGE + 1):
        try:
            target = normalize_url(str(link["href"]), page.final_url or page.url)
            if urlsplit(target).hostname == urlsplit(page.url).hostname:
                page.internal_link_count += 1
                if len(links) < MAX_LINKS_PER_PAGE:
                    links.setdefault(target, None)
            else:
                page.external_link_count += 1
        except AuditError:
            continue
    if page.internal_link_count + page.external_link_count > MAX_LINKS_PER_PAGE:
        page.issues.append("Link discovery truncated at the per-page limit.")
    for tag in soup.find_all(["script", "style", "noscript", "template", "head"]):
        tag.decompose()
    for tag in soup.select('[hidden], [aria-hidden="true"]'):
        if tag.parent:
            tag.decompose()
    page.raw_text_chars = len(clean_text(soup.get_text("\n", strip=True)))
    for tag in soup.find_all(["nav", "footer", "aside", "form"]):
        tag.decompose()
    for tag in soup.select('[role="dialog"], [role="alertdialog"]'):
        label = str(tag.get("aria-label", "")).lower()
        if "cookie" in label and re.search(r"accept|consent|reject", tag.get_text(" ").lower()):
            tag.decompose()
    candidates = soup.select('main, article, [role="main"]')
    main = max(candidates, key=lambda node: len(node.get_text()), default=soup.body or soup)
    text = clean_text(main.get_text("\n", strip=True))
    headings = main.find_all(re.compile(r"^h[1-6]$"))
    page.heading_count = len(headings)
    for level in (1, 2, 3):
        setattr(page, f"h{level}_count", sum(h.name == f"h{level}" for h in headings))
    levels = [int(h.name[1]) for h in headings]
    page.heading_hierarchy_anomalies = sum(b > a + 1 for a, b in pairwise(levels))
    page.paragraph_count = len(main.find_all("p"))
    page.list_count = len(main.find_all(["ul", "ol"]))
    page.table_count = len(main.find_all("table"))
    page.code_block_count = len(main.find_all("pre"))
    shell = count_words(text) < 30 and (
        (shell_marker and scripts >= 1)
        or (framework and scripts >= 2)
        or (scripts >= 5 and len(html) > 2000)
    )
    finish_metrics(page, text, js_shell=shell)
    return Extracted(page, text, list(links))


def extract_text(text: str, page: Page, *, markdown=False) -> Extracted:
    if len(text) > MAX_SOURCE_CHARS:
        raise AuditError("too_large", "Document exceeds the source character limit.")
    page.metadata_available = False
    page.issues.append("HTML metadata unavailable; score uses only supplied content signals.")
    if markdown:
        headings = re.findall(r"^ {0,3}(#{1,6})\s+(.+)$", text, flags=re.MULTILINE)
        page.heading_count = len(headings)
        for level in (1, 2, 3):
            setattr(page, f"h{level}_count", sum(len(h[0]) == level for h in headings))
        if not page.title and headings:
            page.title = headings[0][1][:500]
        page.list_count = len(re.findall(r"(?:\A|\n\s*\n)\s*(?:[-*+] |\d+\. )", text))
        page.code_block_count = len(re.findall(r"^\s*```", text, re.MULTILINE)) // 2
        page.table_count = len(re.findall(r"^\s*\|?\s*:?-{3,}.*\|", text, re.MULTILINE))
        text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"^ {0,3}#{1,6}\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*```[^\n]*$", "", text, flags=re.MULTILINE)
    page.paragraph_count = len([p for p in re.split(r"\n\s*\n", text) if p.strip()])
    text = clean_text(text)
    page.raw_text_chars = len(text)
    finish_metrics(page, text)
    return Extracted(page, text)
