from .models import Page


def recommend_chunking(page: Page) -> None:
    tokens = page.estimated_tokens
    if tokens == 0:
        size, overlap, reason = 0, 0, "No usable text to chunk."
    elif tokens <= 256:
        size, overlap, reason = tokens, 0, "Keep this short document in one chunk."
    elif page.page_profile == "faq":
        size, overlap, reason = 256, 32, "Preserve question/answer pairs where possible."
    elif tokens > 2000 and page.heading_count >= 5:
        size, overlap, reason = (
            768,
            96,
            "Start with heading-aligned chunks; preserve code and tables.",
        )
    elif tokens <= 600:
        size, overlap, reason = 384, 48, "Start with small paragraph-aligned chunks."
    else:
        size, overlap, reason = 512, 64, "Start with section-aligned chunks and evaluate retrieval."
    page.recommended_chunk_size = size
    page.recommended_chunk_overlap = overlap
    page.chunking_reason = reason
