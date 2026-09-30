from collections import deque
from fnmatch import fnmatchcase
from urllib.parse import urlsplit

from .limits import MAX_QUEUE_URLS
from .models import AuditError, AuditInput
from .url_policy import normalize_url


def matches_patterns(url: str, config: AuditInput) -> bool:
    return (
        not config.include_patterns or any(fnmatchcase(url, p) for p in config.include_patterns)
    ) and not any(fnmatchcase(url, p) for p in config.exclude_patterns)


class Frontier:
    def __init__(self, config: AuditInput, start: str):
        self.config = config
        self.host = urlsplit(start).hostname
        self.queue = deque()
        self.seen = set()
        self.truncated = False

    def offer(self, url: str, depth: int):
        if depth > self.config.max_depth:
            return
        try:
            url = normalize_url(url)
        except AuditError:
            return
        if urlsplit(url).hostname != self.host or not matches_patterns(url, self.config):
            return
        if url in self.seen:
            return
        if len(self.seen) >= MAX_QUEUE_URLS:
            self.truncated = True
            return
        self.seen.add(url)
        self.queue.append((url, depth))

    def take(self, count: int) -> list[tuple[str, int]]:
        return [self.queue.popleft() for _ in range(min(count, len(self.queue)))]
