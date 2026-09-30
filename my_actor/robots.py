import asyncio
import logging
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from protego import Protego

from .fetching import TEXT_MIMES
from .limits import MAX_AUXILIARY_BYTES, USER_AGENT
from .models import AuditError

log = logging.getLogger(__name__)


@dataclass
class RobotsRules:
    url: str
    checked: bool
    parser: Protego | None = None
    fallback_allowed: bool = False
    warning: str | None = None
    sitemaps: list[str] = field(default_factory=list)

    def allowed(self, url: str) -> bool:
        return self.parser.can_fetch(url, USER_AGENT) if self.parser else self.fallback_allowed


class Robots:
    def __init__(self, fetcher, enabled=True):
        self.fetcher = fetcher
        self.enabled = enabled
        self.cache: dict[str, RobotsRules] = {}
        self.lock = asyncio.Lock()

    async def rules(self, url: str) -> RobotsRules:
        p = urlsplit(url)
        robots_url = urlunsplit((p.scheme, p.netloc, "/robots.txt", "", ""))
        if not self.enabled:
            return RobotsRules(robots_url, False, fallback_allowed=True)
        async with self.lock:
            if robots_url not in self.cache:
                try:
                    result = await self.fetcher.fetch(
                        robots_url, allowed_mimes=TEXT_MIMES, limit=MAX_AUXILIARY_BYTES
                    )
                    text = result.text
                    if "<html" in text.lower() or "<!doctype" in text.lower():
                        raise AuditError(
                            "malformed_robots", "HTML received instead of robots rules."
                        )
                    parser = Protego.parse(text)
                    recognizable = not text.strip() or any(
                        line.strip().lower().startswith(("user-agent:", "sitemap:", "#"))
                        for line in text.splitlines()
                    )
                    if not recognizable:
                        raise AuditError("malformed_robots", "No recognizable robots directives.")
                    rules = RobotsRules(
                        robots_url, True, parser, sitemaps=list(parser.sitemaps)[:20]
                    )
                except AuditError as exc:
                    allow = exc.http_status in {404, 410}
                    rules = RobotsRules(
                        robots_url,
                        True,
                        fallback_allowed=allow,
                        warning=f"robots.txt unavailable ({exc.code}); {'allowing' if allow else 'skipping'} affected requests.",
                    )
                    log.warning(rules.warning)
                self.cache[robots_url] = rules
            return self.cache[robots_url]

    async def guard(self, url: str):
        rules = await self.rules(url)
        if not rules.allowed(url):
            raise AuditError(
                "robots_disallowed",
                "Blocked by robots rules or conservative unavailable-rules fallback.",
            )

    @property
    def warnings(self):
        return [r.warning for r in self.cache.values() if r.warning]
