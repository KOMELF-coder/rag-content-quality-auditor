from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from .limits import MAX_AUXILIARY_BYTES
from .models import AuditError, Page
from .url_policy import normalize_url


def extract_metadata(soup: BeautifulSoup, page: Page) -> None:
    title = soup.find("title")
    page.title = title.get_text(" ", strip=True)[:500] if title else ""
    description = soup.find(
        "meta", attrs={"name": lambda name: name and name.lower() == "description"}
    )
    page.has_meta_description = bool(description and str(description.get("content", "")).strip())
    page.has_json_ld = soup.find("script", attrs={"type": "application/ld+json"}) is not None
    canonical = soup.find("link", rel=lambda rel: rel and "canonical" in rel)
    if canonical and canonical.get("href"):
        try:
            page.canonical_url = normalize_url(str(canonical["href"]), page.final_url or page.url)
            page.has_canonical = True
            if urlsplit(page.canonical_url).hostname != urlsplit(page.url).hostname:
                page.issues.append("Canonical points to another hostname; it was not followed.")
        except AuditError:
            page.issues.append("Canonical URL is invalid.")


async def check_ai_files(fetcher, robots, start_url: str) -> dict:
    from urllib.parse import urlunsplit

    from .fetching import PAGE_MIMES

    p = urlsplit(start_url)
    result = {}
    for name in ("llms.txt", "llms-full.txt"):
        key = name.replace("-", "_").replace(".", "_")
        url = urlunsplit((p.scheme, p.netloc, "/" + name, "", ""))
        try:
            fetched = await fetcher.fetch(
                url, guard=robots.guard, allowed_mimes=PAGE_MIMES, limit=MAX_AUXILIARY_BYTES
            )
            looks_html = (
                fetched.mime in {"text/html", "application/xhtml+xml"}
                or "<html" in fetched.text.lower()
            )
            result[key + "_present"] = bool(fetched.body.strip()) and not looks_html
            result[key + "_status"] = fetched.status
            result[key + "_error"] = "html_response" if looks_html else None
        except AuditError as exc:
            result[key + "_present"] = False if exc.http_status in {404, 410} else None
            result[key + "_status"] = exc.http_status
            result[key + "_error"] = exc.code
    return result
