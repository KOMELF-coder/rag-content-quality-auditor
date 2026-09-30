from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class AuditInput:
    mode: str = "website"
    start_url: str = "https://docs.python.org/3/tutorial/"
    dataset_id: str = ""
    max_pages: int = 50
    max_depth: int = 3
    include_patterns: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()
    respect_robots_txt: bool = True
    detect_duplicates: bool = True
    check_ai_metadata: bool = True
    max_concurrency: int = 4
    request_timeout_secs: int = 25


@dataclass
class Page:
    source_type: str = "website"
    source_id: str = ""
    url: str = ""
    requested_url: str = ""
    final_url: str | None = None
    canonical_url: str | None = None
    status: str = "audited"
    error_code: str | None = None
    http_status: int | None = None
    content_status: str = "ok"
    title: str = ""
    page_profile: str = "unknown"
    rag_readiness_score: float = 0
    rag_readiness_level: str = "poor"
    rag_value: str = "low"
    recommended_for_rag: bool = False
    estimated_tokens: int = 0
    token_estimation_method: str = "ceil(unicode_characters / 4); heuristic, not a tokenizer"
    raw_html_chars: int = 0
    raw_text_chars: int = 0
    main_content_chars: int = 0
    word_count: int = 0
    boilerplate_ratio: float = 0
    heading_count: int = 0
    h1_count: int = 0
    h2_count: int = 0
    h3_count: int = 0
    heading_hierarchy_anomalies: int = 0
    paragraph_count: int = 0
    list_count: int = 0
    table_count: int = 0
    code_block_count: int = 0
    internal_link_count: int = 0
    external_link_count: int = 0
    duplicate_status: str = "unique"
    duplicate_of: str | None = None
    similarity: float | None = None
    duplicate_match: str | None = None
    has_canonical: bool = False
    has_json_ld: bool = False
    has_meta_description: bool = False
    metadata_available: bool = True
    robots_checked: bool = False
    robots_allowed: bool | None = None
    robots_url: str | None = None
    recommended_chunk_size: int = 0
    recommended_chunk_overlap: int = 0
    chunking_reason: str = "No usable content."
    score_breakdown: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    collected_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Extracted:
    page: Page
    text: str
    links: list[str] = field(default_factory=list)


class AuditError(Exception):
    def __init__(self, code: str, message: str, http_status: int | None = None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
