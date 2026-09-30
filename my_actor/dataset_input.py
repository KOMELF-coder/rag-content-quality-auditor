"""Adapt crawler dataset rows; never fetch a URL found in a source row."""

import re

from .extraction import extract_html, extract_text
from .limits import MAX_SOURCE_CHARS
from .models import AuditError, Extracted, Page
from .url_policy import normalize_url

CONTENT_FIELDS = ("markdown", "cleanText", "text", "content", "html")
URL_FIELDS = ("loadedUrl", "url", "canonicalUrl")
SOURCE_FIELDS = list(CONTENT_FIELDS + URL_FIELDS + ("title",))


def adapt_row(row: object, index: int, dataset_id: str) -> Extracted:
    page = Page(source_type="dataset", source_id=f"dataset:{dataset_id}:{index}")
    if not isinstance(row, dict):
        raise AuditError("dataset_row_unusable", "Source row is not an object.")
    for field in URL_FIELDS:
        value = row.get(field)
        if isinstance(value, str) and value:
            try:
                page.url = page.requested_url = normalize_url(value)
                page.final_url = page.url
                break
            except AuditError:
                continue
    if not page.url:
        page.issues.append("Source URL missing or invalid; use source_id to locate the document.")
    if isinstance(row.get("title"), str):
        page.title = row["title"][:500]
    # Ignore tiny placeholder fields when a meaningful later candidate exists.
    candidates = [
        (name, row[name])
        for name in CONTENT_FIELDS
        if isinstance(row.get(name), str) and row[name].strip()
    ]
    if not candidates:
        raise AuditError("dataset_row_unusable", "Source row contains no usable content field.")
    meaningful = [(name, text) for name, text in candidates if len(text.strip()) >= 40]
    name, text = (meaningful or candidates)[0]
    if len(text) > MAX_SOURCE_CHARS:
        raise AuditError("too_large", "Dataset content exceeds the source character limit.")
    is_html = name == "html" or bool(
        re.search(
            r"<(?:!doctype|html|body|main|article|div|p|h[1-6]|script|style|nav|table|section|ul|ol)(?:\s|>)",
            text,
            re.IGNORECASE,
        )
    )
    if is_html:
        extracted = extract_html(text, page)
        if not extracted.text and page.content_status != "likely_requires_javascript":
            raise AuditError(
                "dataset_row_unusable", "HTML field contains no usable visible content."
            )
        return extracted
    return extract_text(text, page, markdown=name == "markdown")


async def source_rows(dataset_client, limit: int):
    """Single-row pagination limits response memory; no source HTML is retained."""
    for offset in range(limit):
        batch = await dataset_client.list_items(
            offset=offset, limit=1, fields=SOURCE_FIELDS, clean=False
        )
        if not batch.items:
            break
        yield offset, batch.items[0]
