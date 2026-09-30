# RAG Content Quality Auditor

Know which pages belong in your RAG knowledge base before you ingest them.

Audit a website or an existing Apify dataset. Identify useful pages, duplicates, boilerplate-heavy content, poor structure and ingestion risks, and receive an explainable RAG readiness score for every analyzed page.

**The quality gate between crawling and RAG ingestion.** Review what you collected before spending time and resources on chunking, embeddings and vector-database ingestion. The Actor provides deterministic signals to help prioritize content; it does not use an LLM or claim to measure retrieval accuracy.

## 1. What it does

- Recommends which accessible documents to include or review before ingestion.
- Flags exact and likely near-duplicate main content within the run.
- Measures content size, structure, boilerplate and machine readability.
- Identifies probable JavaScript shells that need a different upstream crawler.
- Estimates tokens and suggests starting chunk sizes.
- Produces page-level explanations and a reconciled global audit report.

## 2. Why audit before RAG ingestion

A crawler can collect pages that your AI knowledge base does not need: navigation pages, repeated content, empty shells or pages with little useful text. An audit makes those properties visible before you embed the corpus. Keep your existing crawler and use this Actor as a content quality check between collection and ingestion.

## 3. What you get

| Output | Where to find it | What to do next |
| --- | --- | --- |
| Page analyses | Default dataset / **Page analyses** | Filter `recommended_for_rag = true`, inspect reasons and join to your source data |
| `AUDIT_REPORT` | Default key-value store / **Global audit report** | Review corpus tokens, duplicate counts and top issues |
| `DIAGNOSTICS` | Default key-value store / **Skipped and failed resources** | Fix or exclude unprocessed resources; no successful-analysis event is requested |

Illustrative output from the repository's synthetic documentation fixture:

```json
{
  "url": "https://example.com/document-0",
  "rag_readiness_score": 91.46,
  "rag_readiness_level": "excellent",
  "rag_value": "medium",
  "recommended_for_rag": true,
  "estimated_tokens": 239,
  "duplicate_status": "unique",
  "content_status": "ok",
  "recommended_chunk_size": 239,
  "recommended_chunk_overlap": 0
}
```

This is an example, not a measured performance claim. [Full sample results](examples/page-results.json) include an exact duplicate and a JavaScript shell, with explanations for excluding both.

## 4. Quick start

In Apify, choose **Website**, enter your website URL and set **Maximum pages**. Run the Actor, then open **Page analyses** and **Global audit report**.

For a first run, the input form suggests eight pages from the public Python tutorial, link depth 1, and `include_patterns = ["https://docs.python.org/3/tutorial/*"]`, matching [the supplied example input](.actor/INPUT.json). Replace the pattern when auditing another section, or clear it to crawl the whole hostname within the configured limits. API calls that omit `max_pages` use 50 and omitted `include_patterns` remains unrestricted within the hostname. Start small and inspect results before expanding an audit.

## 5. Example website input

```json
{
  "mode": "website",
  "start_url": "https://docs.python.org/3/tutorial/",
  "max_pages": 8,
  "max_depth": 1,
  "include_patterns": ["https://docs.python.org/3/tutorial/*"]
}
```

Website mode visits only the exact starting hostname. It follows bounded sitemap and link discovery, respects robots.txt by default and fetches server-rendered content. It does not execute JavaScript.

## 6. Example dataset input

```json
{
  "mode": "dataset",
  "dataset_id": "YOUR_SOURCE_DATASET_ID",
  "max_pages": 100
}
```

Use the **Source dataset** picker in Apify Console to grant this limited-permissions Actor read-only access to the dataset you want to audit. API callers can still pass the dataset ID or unique name directly. This mode analyzes existing content without recrawling its URLs. Text-only records are supported even when their source URL is missing; use `source_id` to find the original zero-based row.

## 7. Example output: interpreting a recommendation

The sample documentation page receives these components:

```json
{
  "score_breakdown": {
    "content": 22.96,
    "structure": 18.5,
    "cleanliness": 15.0,
    "uniqueness": 15.0,
    "metadata": 10.0,
    "accessibility": 10.0
  }
}
```

A duplicate can still contain well-structured, readable information. Its uniqueness score and recommendation change because an earlier document already represents that content. `duplicate_of` identifies that source document. Review near-duplicates before discarding them: small differences can matter.

## 8. Global audit report

The report includes discovery/selection/processing counts, successful/failed/skipped totals, duplicate counts, recommended pages, top issues and estimated corpus tokens. It also records runtime, website HTTP request count and optional llms.txt observations.

`estimated_corpus_tokens` includes **recommended documents only**. `estimated_analyzed_tokens` includes every successfully analyzed document, including duplicates and low-value pages. `overall_score` averages unique or duplicate-unchecked documents while excluding navigation/index profiles; `score_denominator` makes the population explicit. It is null when no eligible document remains.

[Sample global report](examples/AUDIT_REPORT.json). Include/exclude pattern suggestions are empty in V1 because reliable path-level inference is not implemented; page-level recommendations remain actionable.

## 9. Use cases

- Prepare website content before embeddings.
- Clean documentation before RAG ingestion.
- Remove repeated pages from a crawler dataset.
- Estimate the size of an AI knowledge base.
- Identify low-value pages for manual review.
- Prepare a corpus for Pinecone, Qdrant, Weaviate or another vector database through your own pipeline. No direct database integrations are implemented.
- Give an AI agent a machine-readable quality gate before knowledge ingestion.

## 10. Scoring methodology

| Component | Maximum | Signals |
| --- | ---: | --- |
| Content usefulness | 30 | Logarithmic word-count signal, capped at 600 words |
| Structure | 20 | Title, headings, paragraphs, lists/tables/code; mild heading-jump penalty |
| Cleanliness | 15 | Main-content share with an allowance for ordinary navigation/footer text |
| Uniqueness | 15 | Unique: 15; near duplicate: 5; exact duplicate: 0; unchecked: 7.5 |
| Metadata | 10 | Title: 4; description, canonical and JSON-LD presence: 2 each |
| Machine accessibility | 10 | Meaningful parseable text: 10; short: 7; empty/JS shell: 2 |

Levels: **excellent ≥85**, **good ≥70**, **mixed ≥50**, **poor <50**.

`recommended_for_rag` is true only for a successful analysis with a score ≥70, `content_status = ok`, at least 60 word units, a unique or duplicate-unchecked status, and a profile other than navigation/index. Exact and near duplicates are excluded. Disabling duplicate detection explicitly marks uniqueness as unverified.

`rag_value` is a separate content/profile proxy, not a judgment of business relevance. No rule understands whether a document answers your specific questions. Missing llms.txt has **zero effect** on scoring. All formulas and thresholds are in [ARCHITECTURE.md](ARCHITECTURE.md).

## 11. Input reference

| Field | Default | Meaning / limits |
| --- | --- | --- |
| `mode` | `website` | `website` or `dataset` |
| `start_url` | Python tutorial | Public HTTP(S); required in website mode; no credentials, ports 80/443 only |
| `dataset_id` | empty | Required in dataset mode; Console uses an Apify dataset picker with read-only access; API callers may pass an ID or unique name |
| `max_pages` | 50 | 1–1,000 page attempts or source rows, including failures; form suggests 8 |
| `max_depth` | 3 | 0–10; form suggests 1; start=0, sitemap pages=1; 0 disables sitemap discovery |
| `include_patterns` | `[]` | Full normalized URL globs; form suggests `https://docs.python.org/3/tutorial/*`; empty includes all eligible same-host URLs |
| `exclude_patterns` | `[]` | Exclusions win, including on page redirects |
| `respect_robots_txt` | true | Crawl-rule checks for website requests |
| `detect_duplicates` | true | Main-content comparisons within this run |
| `check_ai_metadata` | true | Observe `/llms.txt` and `/llms-full.txt` in website mode |
| `max_concurrency` | 4 | 1–8 simultaneous page fetches |
| `request_timeout_secs` | 25 | 5–60 seconds per HTTP attempt |

Patterns use shell-style globs, not regular expressions. They are case-sensitive after URL normalization. At most 20 patterns of 200 characters per list. Robots/sitemap/llms discovery files are outside page include/exclude filters, but remain subject to network, host and applicable robots checks. Website-specific settings are ignored in dataset mode.

## 12. Output reference

| Fields | Purpose |
| --- | --- |
| `source_type`, `source_id` | Origin and stable join key |
| `url`, `requested_url`, `final_url`, `canonical_url` | Supplied/requested/final URLs; canonical is an untrusted signal |
| `status`, `http_status`, `content_status`, `error_code` | Analysis/HTTP/content diagnostics; unavailable HTTP values are null |
| `rag_readiness_score`, `rag_readiness_level`, `score_breakdown` | Explainable quality score |
| `rag_value`, `page_profile`, `recommended_for_rag` | Retrieval-potential proxy, content profile and include/review decision |
| `estimated_tokens`, `token_estimation_method` | Approximate token size |
| `raw_html_chars`, `raw_text_chars`, `main_content_chars`, `word_count`, `boilerplate_ratio` | Extraction measurements |
| Heading/paragraph/list/table/code/link counts | Structure signals; navigation links are counted for discovery |
| `duplicate_status`, `duplicate_of`, `similarity`, `duplicate_match` | Duplicate classification and representative |
| `has_canonical`, `has_json_ld`, `has_meta_description`, `metadata_available` | Observed HTML metadata availability |
| `robots_checked`, `robots_allowed`, `robots_url` | Factual crawl-policy decision, not legal consent |
| `recommended_chunk_size`, `recommended_chunk_overlap`, `chunking_reason` | Starting guidance in estimated tokens |
| `reasons`, `issues`, `recommendations`, `collected_at` | Short explanations and collection timestamp |

The [dataset schema](.actor/dataset_schema.json) is the complete field contract. Raw HTML and full document text are intentionally not included. Join analyses back to your source dataset to build the retained corpus. Diagnostics use the same shape but are saved in `DIAGNOSTICS`, with `recommended_for_rag = false`.

## 13. Using with Website Content Crawler / RAG Web Browser

Run your existing crawler, then pass its dataset ID to this Actor. Content precedence is `markdown` → `cleanText` → `text` → `content` → `html`. Nonempty strings with at least 40 characters are considered first; shorter fields are fallback candidates. HTML is parsed before scoring. URL precedence is `loadedUrl` → `url` → `canonicalUrl`.

HTML metadata is not inferred from cleaned text, and missing metadata is explicitly reported. Empty/unusable rows are diagnostic records, not paid analyses. These are field-compatible workflows, not claims of official integration or support for every upstream schema.

## 14. RAG / embeddings / vector database workflow

```text
Crawler or existing dataset
  → RAG Content Quality Auditor
  → join recommended source documents
  → review near-duplicates and domain relevance
  → chunk and embed in your own pipeline
  → vector database / retrieval augmented generation / AI agent
```

Chunk guidance ranges from a single short chunk to 768 tokens with 96-token overlap for long structured documents. FAQ guidance favors question/answer pairs. These are **starting recommendations**, not optimal chunking guarantees. This Actor does not chunk, embed or upload your documents to a vector database.

## 15. MCP / AI-agent usage

The same JSON inputs work through the Actor API and through Apify's Actor tooling where available. No custom MCP server is included. An agent can:

1. Submit website/dataset input with a small limit.
2. Read the dataset plus `AUDIT_REPORT` and `DIAGNOSTICS` output links.
3. Filter `recommended_for_rag`, join by source ID/URL and pass the retained original content to its ingestion tool.
4. Present uncertain or near-duplicate cases for review.

## 16. Pricing — pending benchmark

Intended pricing: **one `page-audited` event per successfully analyzed document**. No final price has been chosen. Check the Actor's current Pricing tab when it is published.

An analyzed duplicate, short page or JavaScript shell still represents analysis work and is eligible for this event. Invalid URLs, blocked requests, unsupported MIME types, network failures and unusable dataset rows are not. Diagnostics are stored separately from the dataset. The report distinguishes billable eligibility, requested events and actual platform event counts. Local/non-PPE runs do not charge customers.

Configure only the custom event for this commercial contract; adding platform synthetic pricing events can create additional charges. [BENCHMARK_PLAN.md](BENCHMARK_PLAN.md) describes the measurements needed before pricing.

## 17. Limitations

- Static public HTML, XHTML, plain text and Markdown only. No browser rendering, login, cookies, proxy rotation, CAPTCHA bypass, PDF extraction, OCR or multimedia analysis.
- Exact-host bounded discovery; no promise of exhaustive crawling, sitemap coverage or semantic relevance.
- Heuristic extraction can misidentify unusual templates. Markdown analysis covers common structure, not the full CommonMark specification.
- Near-duplicate detection is lexical, with bounded candidate comparisons. It can miss matches, especially short or boilerplate-heavy documents. Review version-specific content.
- Token estimates are Unicode characters divided by four and vary by language/model. CJK word units count characters; other word boundaries use Unicode word groups.
- Structured-data presence is measured; its semantic correctness is not validated. A canonical URL is not proof of the preferred source.
- Dataset mode analyzes content as supplied; it does not check whether the original site is currently accessible or whether its source metadata is accurate.
- V1 does not resume partial runs. A nonempty output dataset is rejected on startup to prevent accidental duplicate publication/charging. Start a fresh run after interruption; previously saved rows remain available.

## 18. Responsible crawling

Robots.txt is checked by default through the same protected transport. A missing file (404/410) allows crawling with a warning. Network/server errors, access denials or unrecognizable robots content cause conservative skipping. Parser decisions are recorded. These observations do not establish copyright rights, legal authorization or AI-training consent.

All resolved IP addresses must be public. Each redirect is revalidated, cross-host redirects and HTTPS downgrades are refused, and sockets connect to a validated numeric address while retaining hostname/TLS verification. Small request, body, retry and discovery limits constrain work. The implementation does not use environmental HTTP proxies.

## 19. Technical notes

Python 3.12, Apify SDK, HTTPX, Beautiful Soup and Protego. No external AI API or model download. Apify's SDK has transitive dependencies including Crawlee; this Actor does not use its crawling framework.

```bash
python -m venv .venv
# Activate the environment, then:
python -m pip install -e ".[test]"
python -m pytest -q
python scripts/local_smoke.py --mode website
python scripts/local_smoke.py --mode dataset
```

For the real entry point, place input at `storage/key_value_stores/default/INPUT.json`, then run `python -m my_actor`. [VALIDATION.md](VALIDATION.md) covers Windows commands, live tests, Docker and Cloud validation. [ARCHITECTURE.md](ARCHITECTURE.md) contains the security model and decision log.

## 20. FAQ

**What is RAG readiness?** A set of measurable ingestion-quality signals: useful extracted text, structure, cleanliness, uniqueness, metadata and machine readability. It is not measured answer accuracy.

**Does this Actor use an LLM?** No. Core analysis uses deterministic local rules.

**Does it crawl JavaScript websites?** It fetches the initial server response and diagnoses probable JS shells. Use a browser-capable crawler upstream when necessary.

**Can I use an existing Apify dataset?** Yes. Dataset mode supports common text, Markdown, HTML and URL fields without recrawling.

**Does it support Website Content Crawler outputs?** It supports common output fields. Verify your actual dataset's field mapping with a small run first.

**Are token counts exact?** No. They are estimates, not model-specific tokenizer results.

**Does a low score mean a page is bad?** No. A short answer, a product page or a specialized format may still be valuable for your application. Review the reasons and your retrieval requirements.

**Does llms.txt affect the score?** No. Availability is optional report metadata.

**Does it support PDFs?** No. Convert them upstream to cleaned text/Markdown, then audit that dataset.

**Does it respect robots.txt?** Yes, by default, using a real parser and a documented conservative fallback.

**What counts as a paid result?** One successfully analyzed page/document. Duplicate and low-value analyses count; failures, blocked resources and unusable rows do not request the custom billing event.

**Why are no pages recommended?** The corpus may be inaccessible, too short, duplicated or unsuitable under the explicit rules. Read the report and diagnostics. A valid audit with zero recommended pages is not automatically a failed run.
