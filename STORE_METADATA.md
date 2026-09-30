# Apify Store metadata recommendations

**Display name:** RAG Content Quality Auditor

**Slug:** rag-content-quality-auditor

**Primary tagline:** The quality gate between crawling and RAG ingestion.

**Short description:** Audit websites before RAG ingestion. Score content quality, structure, duplication, boilerplate, token size and machine readability, then identify which pages to ingest or exclude.

**SEO title:** RAG Readiness Checker for AI Knowledge Bases

## Suggested discovery terms

RAG audit, RAG readiness, RAG content quality, AI knowledge base, website content audit,
dataset audit, duplicate content, boilerplate removal signals, chunking recommendations,
token estimation, embeddings preparation, knowledge base quality, llms.txt checks.

## Suggested Store categories

AI, Developer tools, and content/data quality categories if available in the publisher UI.
Confirm current category labels when publishing; these are recommendations, not assigned metadata.

## Promotional copy

Know which pages belong in your RAG knowledge base before you ingest them. Audit accessible
website content or an existing crawler dataset. Get explainable quality scores, duplicate
signals, estimated tokens and practical include/review recommendations without an LLM API.

## FAQ snippets

- **Use with my crawler?** Pass a dataset ID containing common text, Markdown or HTML fields.
- **Uses AI models?** No. Scores are deterministic local signals, not semantic retrieval tests.
- **JavaScript sites?** Probable shells are flagged; render upstream and audit the resulting dataset.
- **Paid results?** Successful analyses, including duplicate/low-value diagnoses. Failed or skipped resources do not request the custom event.
- **Exact token counts?** No; a transparent character-based approximation is returned.

## Before Store publication

Validate the Cloud form, output links, source dataset access and PPE budget boundaries.
Configure the `page-audited` event after measuring costs. Do not set a final price from the
local smoke run. Use the README's synthetic example as an illustration, labelled accordingly.
No user counts, measured retrieval gains, testimonials or performance guarantees are claimed.
