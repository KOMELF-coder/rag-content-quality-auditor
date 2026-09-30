"""Streaming exact hashes and candidate-bounded 64-bit SimHash matching."""

import hashlib
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass

from .limits import MAX_DUPLICATE_CANDIDATES, MIN_NEAR_WORDS
from .models import Page
from .tokens import word_units


def normalized_content(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def simhash(text: str) -> int:
    words = word_units(normalized_content(text))
    features = Counter(" ".join(words[i : i + 3]) for i in range(max(0, len(words) - 2)))
    weights = [0] * 64
    for feature, count in features.items():
        bits = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")
        weight = min(count, 3)
        for i in range(64):
            weights[i] += weight if bits & (1 << i) else -weight
    return sum(1 << i for i, value in enumerate(weights) if value > 0)


@dataclass(frozen=True)
class Fingerprint:
    reference: str
    bits: int
    words: int


class DuplicateIndex:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.exact: dict[str, str] = {}
        self.normalized: dict[str, str] = {}
        self.buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
        self.fingerprints: list[Fingerprint] = []
        self.truncated = False

    def apply(self, page: Page, text: str) -> None:
        if not self.enabled:
            page.duplicate_status = "not_checked"
            return
        if not text:
            return
        reference = page.source_id or page.url
        raw_hash = digest(text)
        normalized_hash = digest(normalized_content(text))
        match = self.exact.get(raw_hash) or self.normalized.get(normalized_hash)
        if match:
            page.duplicate_status = "exact_duplicate"
            page.duplicate_of = match
            page.similarity = 1.0
            page.duplicate_match = "exact" if raw_hash in self.exact else "normalized_exact"
            return
        self.exact[raw_hash] = reference
        self.normalized[normalized_hash] = reference
        if page.word_count < MIN_NEAR_WORDS or page.boilerplate_ratio > 0.8:
            return
        bits = simhash(text)
        # Four 16-bit bands guarantee a shared band for Hamming distance <= 3,
        # unless the explicit candidate/bucket caps truncate pathological inputs.
        candidates = set()
        keys = [(band, (bits >> (16 * band)) & 0xFFFF) for band in range(4)]
        for key in keys:
            candidates.update(self.buckets[key])
        if len(candidates) > MAX_DUPLICATE_CANDIDATES:
            self.truncated = True
        best = None
        for index in sorted(candidates)[:MAX_DUPLICATE_CANDIDATES]:
            prior = self.fingerprints[index]
            if min(prior.words, page.word_count) / max(prior.words, page.word_count) < 0.8:
                continue
            distance = (bits ^ prior.bits).bit_count()
            if distance <= 3 and (best is None or distance < best[0]):
                best = (distance, prior.reference)
        if best:
            page.duplicate_status = "near_duplicate"
            page.duplicate_of = best[1]
            page.similarity = round(1 - best[0] / 64, 6)
            page.duplicate_match = "simhash_64"
            self.exact[raw_hash] = best[1]
            self.normalized[normalized_hash] = best[1]
            return
        index = len(self.fingerprints)
        self.fingerprints.append(Fingerprint(reference, bits, page.word_count))
        for key in keys:
            if len(self.buckets[key]) < MAX_DUPLICATE_CANDIDATES:
                self.buckets[key].append(index)
            else:
                self.truncated = True
