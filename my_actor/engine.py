"""End-to-end orchestration independent of Apify storage and charging."""

import asyncio
import logging
from time import monotonic
from urllib.parse import urlsplit, urlunsplit

from .aggregation import aggregate
from .dataset_input import adapt_row
from .discovery import Frontier, matches_patterns
from .duplicates import DuplicateIndex
from .extraction import extract_html, extract_text
from .fetching import Fetcher
from .metadata import check_ai_files
from .models import AuditError, AuditInput, Page, utc_now
from .reporting import diagnostic
from .robots import Robots
from .scoring import score
from .sitemap import discover_sitemaps
from .tokens import estimate_tokens
from .url_policy import URLPolicy

log = logging.getLogger(__name__)


class Auditor:
    def __init__(self, config: AuditInput, emit=None):
        self.config = config
        self.emit = emit
        self.pages: list[Page] = []
        self.duplicates = DuplicateIndex(config.detect_duplicates)
        self.warnings = []
        self.started_at = utc_now()
        self.started = monotonic()
        self.stopped = False

    async def accept(self, extracted=None, page=None) -> bool:
        if extracted is not None:
            page = extracted.page
            page.estimated_tokens = estimate_tokens(extracted.text)
            self.duplicates.apply(page, extracted.text)
            score(page)
        if self.emit is not None and not await self.emit(page):
            self.warnings.append(
                "Output budget reached; audit stopped. Some selected pages may not have been published."
            )
            self.stopped = True
            return False
        self.pages.append(page)
        if len(self.pages) % 25 == 0:
            log.info("Audit progress: %s processed documents", len(self.pages))
        return True

    def report(self, *, discovered, selected, request_count=0, ai_metadata=None):
        if self.duplicates.truncated:
            self.warnings.append(
                "Near-duplicate candidate limits reached; some matches may be missed."
            )
        if not self.config.detect_duplicates:
            self.warnings.append(
                "Duplicate detection disabled; uniqueness and corpus size may be overstated."
            )
        source = (
            urlsplit(self.config.start_url).hostname
            if self.config.mode == "website"
            else self.config.dataset_id
        )
        result = aggregate(
            self.pages,
            mode=self.config.mode,
            source=source,
            started_at=self.started_at,
            discovered=discovered,
            selected=selected,
            request_count=request_count,
            runtime_seconds=monotonic() - self.started,
            warnings=self.warnings,
            ai_metadata=ai_metadata,
        )
        log.info(
            "Audit complete: %s audited, %s failed, %s skipped, %s recommended",
            result["pages_successfully_audited"],
            result["pages_failed"],
            result["pages_skipped"],
            result["recommended_pages"],
        )
        return result

    async def dataset(self, rows, *, total: int | None = None) -> dict:
        selected = 0
        async for index, row in rows:
            if selected >= self.config.max_pages:
                break
            selected += 1
            try:
                extracted = adapt_row(row, index, self.config.dataset_id)
                if not await self.accept(extracted):
                    break
            except AuditError as exc:
                page = diagnostic(
                    "",
                    exc,
                    source_type="dataset",
                    source_id=f"dataset:{self.config.dataset_id}:{index}",
                )
                await self.accept(page=page)
            except (ValueError, RecursionError) as exc:
                log.warning("Dataset content parsing failed (%s)", type(exc).__name__)
                await self.accept(
                    page=diagnostic(
                        "",
                        AuditError("parse_error", "Dataset content could not be parsed."),
                        source_type="dataset",
                        source_id=f"dataset:{self.config.dataset_id}:{index}",
                    )
                )
        if total is not None and total > selected:
            self.warnings.append(
                "Dataset audit limited to selected source rows; remaining rows were not analyzed."
            )
        if not selected:
            self.warnings.append("Source dataset is empty; no documents were analyzed.")
        return self.report(discovered=total if total is not None else selected, selected=selected)

    async def website(self, fetcher=None) -> dict:
        if fetcher is None:
            async with Fetcher(
                URLPolicy(self.config.start_url),
                concurrency=self.config.max_concurrency,
                timeout=self.config.request_timeout_secs,
            ) as owned:
                return await self.website(owned)
        start, _ = await fetcher.policy.validate(self.config.start_url)
        log.info("Website source validated; hostname=%s", fetcher.policy.host)
        robots = Robots(fetcher, self.config.respect_robots_txt)
        rules = await robots.rules(start)
        frontier = Frontier(self.config, start)
        frontier.offer(start, 0)
        if self.config.max_depth > 0:
            parts = urlsplit(start)
            conventional = urlunsplit((parts.scheme, parts.netloc, "/sitemap.xml", "", ""))
            sitemap_urls, warnings = await discover_sitemaps(
                fetcher, robots, [*rules.sitemaps, conventional]
            )
            self.warnings.extend(warnings)
            log.info("Sitemap discovery: %s same-host page URLs", len(sitemap_urls))
            for url in sitemap_urls:
                frontier.offer(url, 1)
        ai_metadata = (
            await check_ai_files(fetcher, robots, start) if self.config.check_ai_metadata else {}
        )
        visited_final = set()
        selected = 0

        async def guard(url):
            if not matches_patterns(url, self.config):
                raise AuditError("excluded_by_pattern", "URL excluded by input patterns.")
            await robots.guard(url)

        async def collect(url):
            try:
                result = await fetcher.fetch(url, guard=guard)
                page = Page(
                    url=result.final_url,
                    requested_url=url,
                    final_url=result.final_url,
                    source_id=url,
                    http_status=result.status,
                )
                rule = await robots.rules(result.final_url)
                page.robots_checked = rule.checked
                page.robots_allowed = rule.allowed(result.final_url) if rule.checked else None
                page.robots_url = rule.url
                extracted = (
                    extract_html(result.text, page)
                    if result.mime in {"text/html", "application/xhtml+xml"}
                    else extract_text(result.text, page, markdown=result.mime == "text/markdown")
                )
                return extracted, None
            except AuditError as exc:
                page = diagnostic(url, exc, source_id=url)
                rule = await robots.rules(url)
                page.robots_checked = rule.checked
                page.robots_allowed = rule.allowed(url) if rule.checked else None
                page.robots_url = rule.url
                return None, page
            except (ValueError, RecursionError) as exc:
                log.warning("Content parsing failed (%s)", type(exc).__name__)
                return None, diagnostic(
                    url, AuditError("parse_error", "Document could not be parsed."), source_id=url
                )

        while frontier.queue and selected < self.config.max_pages and not self.stopped:
            batch = frontier.take(
                min(self.config.max_concurrency, self.config.max_pages - selected)
            )
            selected += len(batch)
            # gather preserves queue order despite differing response completion times.
            results = await asyncio.gather(*(collect(url) for url, _ in batch))
            for (url, depth), (extracted, page) in zip(batch, results):
                if extracted:
                    if extracted.page.final_url in visited_final:
                        page = diagnostic(
                            url,
                            AuditError(
                                "redirect_alias", "Final resource already analyzed in this run."
                            ),
                            source_id=url,
                        )
                        page.status = "skipped"
                        extracted = None
                    else:
                        visited_final.add(extracted.page.final_url)
                        for link in extracted.links:
                            frontier.offer(link, depth + 1)
                if not await self.accept(extracted, page):
                    break
        if frontier.queue or frontier.truncated:
            self.warnings.append("Crawl reached its page or discovery limit; coverage is partial.")
        if not selected:
            self.warnings.append("No URLs matched the configured selection patterns.")
        self.warnings.extend(robots.warnings)
        return self.report(
            discovered=len(frontier.seen),
            selected=selected,
            request_count=fetcher.request_count,
            ai_metadata=ai_metadata,
        )
