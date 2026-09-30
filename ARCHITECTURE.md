# Architecture and decision log

## Product boundary and modules

The Actor audits collected content. It does not replace a full crawler or perform embeddings.
Business logic imports no Apify SDK. The SDK appears only in the entry point and storage adapter.

| Modules | Responsibility |
| --- | --- |
| `models`, `limits`, `input_validation` | Stable result contract and bounded, strict inputs |
| `url_policy`, `fetching` | URL normalization, DNS safety, IP-pinned HTTP, retries and body limits |
| `robots`, `sitemap`, `discovery` | Crawl rules, bounded XML discovery and deterministic URL frontier |
| `extraction`, `metadata` | Main text, structure, HTML metadata, probable JS shells, llms observations |
| `tokens`, `duplicates` | Local estimates, cryptographic hashes and bucketed SimHash |
| `scoring`, `chunking` | Pure deterministic formulas and starting recommendations |
| `dataset_input` | Field precedence and bounded row iteration |
| `engine` | Mode lifecycle, ordered analysis and streaming output callback |
| `aggregation`, `reporting` | Reconciled totals and structured diagnostics |
| `apify_io`, `main`, `__main__` | SDK storage, successful-result events and Actor entry point |

## Website lifecycle

1. Validate inputs, normalize start URL, require every DNS answer to be public.
2. Load origin-specific robots rules. Bootstrap robots requests do not recursively check themselves.
3. At depth >0, inspect robots sitemap declarations plus `/sitemap.xml`, through the same transport.
4. Optionally inspect two llms files once, subject to robots. HTML fallback pages do not count as llms files.
5. Process a breadth-first frontier in batches no larger than concurrency. Sitemap pages enter at depth 1.
6. Validate each page and redirect against network, hostname, patterns and robots; fetch bounded content.
7. Extract main content, then apply duplicate analysis, tokens, score and chunk guidance in queue order.
8. Stream successful analyses to the dataset and retain only compact page metrics/fingerprints.
9. Save diagnostics and the global report. A budget refusal stops publishing and further batches.

Concurrent responses are consumed in queue order, so scheduling does not select the duplicate
representative. The first matching content becomes the representative. Network failures/content
changes can naturally change later runs. Timestamps/runtime are observations, not deterministic scores.

## Dataset lifecycle

The SDK checks access to a source dataset, then requests at most 50 rows with only relevant
fields. Each request is capped by the remaining page limit. One response batch is retained
at a time, without prefetch; original row indexes advance by the actual response length.
An empty response ends iteration, including after a final partial batch. SDK source calls
go to the fixed Apify service, never to URLs in source rows.

Field precedence: `markdown`, `cleanText`, `text`, `content`, `html`. Prefer nonempty strings
with at least 40 characters; fallback to shorter nonempty strings. URL precedence: `loadedUrl`,
`url`, `canonicalUrl`. Records without a URL use `dataset:ID:zero-based-index` as identity.
HTML is parsed; cleaned text/Markdown gets observed structure but no invented HTML metadata.
Raw fields are discarded after extracting metrics and fingerprints. Unusable rows are skipped.
The source dataset should remain unchanged during a run; pagination is not a transactional snapshot.

## Security model

- Only HTTP(S), ports 80/443; no URL credentials, control characters, backslashes or IPv6 zone IDs.
- Reject all non-global addresses plus multicast/reserved ranges, IPv4-mapped private IPv6,
  transition tunnels and the well-known IPv6 translation prefix. Reject local-name suffixes.
- Resolve before fetching and require **all** answers to be safe. Resolve again at socket selection.
- Rewrite the transport URL to a validated numeric IP, preserving the original `Host` and
  TLS `sni_hostname`. Pools are separate by hostname to avoid cross-host TLS reuse.
- TLS verification remains enabled using the operating system trust store. No HTTP proxy
  environment variables are used. There is no custom CA or TLS-disable user input.
- Never automatically follow redirects. Every hop is normalized/resolved/checked; exact
  hostname only, even on the initial redirect. No `www` exception, no subdomain expansion.
  HTTPS→HTTP downgrades are rejected. HTTP→HTTPS on the same hostname is permitted.
- The numeric-address connection closes the usual check/second-DNS-lookup rebinding gap.
  Trust still depends on the OS, routing, TLS trust roots and HTTP stack; a public server can
  itself proxy private data. No application-level policy can prove remote data provenance.
- No secrets are printed. Normal progress logs avoid full source URLs; result URLs are user data
  and can contain query values. The Actor accepts no authentication/session-cookie inputs.
- XML DTD/entity declarations and NUL-containing encodings are rejected; no external entities.
- Streaming raw bytes are bounded before decompression. Only identity/gzip/zlib-deflate are
  supported; output expansion is capped, and concatenated/incomplete compressed streams fail.

The source dataset can contain nonpublic URL labels because they are never fetched. URL labels
still undergo syntax normalization; private addresses are not interpreted as crawl authorization.

## Central limits

| Limit | Value |
| --- | ---: |
| Page attempts/source rows | 1–1,000; default 50 |
| Link depth | 0–10; default 3 |
| Concurrent requests | 1–8; default 4 |
| Per-attempt deadline | 5–60 s; default 25 s |
| Redirects | 5 (6 HTTP hops maximum) |
| Retries | 2; 429/500/502/503/504/timeouts only |
| Retry-After/backoff wait | At most 10 s per retry |
| Raw and decoded response body | 2,000,000 bytes each |
| Parsed source document | 1,000,000 characters |
| Robots/llms bodies | 256,000 bytes |
| Sitemap files / nesting | 20 / 3 index levels |
| Sitemap URL count / URL frontier | 10,000 each |
| Per-page links inspected | 1,001 (1,000 retained) |
| Per-bucket / per-page near candidates | 128 / 128 |

Keepalive is enabled. DNS lookup has a five-second deadline. Retries use exponential delays
with a bounded numeric/date Retry-After value. Ordinary 4xx errors are not retried.
`max_pages` bounds page attempts, not robots/sitemap/llms auxiliary HTTP requests.

## Extraction decisions

Measure raw visible text after removing head/scripts/styles/noscript/templates/hidden content.
Remove navigation, footer, aside and form regions. Remove cookie dialogs only when semantic
dialog role, cookie label and consent words agree. CSS class names alone never remove content.
Select the largest `main`, `article` or `role=main`; otherwise use body/document text.

`boilerplate_ratio = clamp(1 - main_content_chars / max(raw_text_chars, 1), 0, 1)`.
Plain text/Markdown has no observed HTML boilerplate, so its ratio is zero and unavailable
metadata is explicitly marked. This does not prove the supplied text has no boilerplate.

Word units use Unicode word groups; CJK/Hiragana/Katakana characters are individual units.
A JS shell needs <30 words plus root/app+script, framework+two scripts, or ≥5 scripts and
>2,000 HTML characters. A short page without these signals is simply `too_short`.

Canonical is recorded and never fetched because of its canonical status. Invalid/off-host
canonicals generate issues. JSON-LD presence is an observable signal, not schema validation.

## Duplicate pipeline and complexity

1. SHA-256 of extracted main text detects exact equality.
2. SHA-256 of NFKC/casefolded/whitespace-collapsed text detects normalized exact equality.
3. For ≥80 word units and boilerplate ≤0.8, form normalized word-unit trigrams (including
   individual CJK units, matching extraction), weight frequencies
   up to 3, and hash with BLAKE2b into a 64-bit SimHash.
4. Four 16-bit bands retrieve candidates. Compare at most 128 stable prior candidates;
   retain at most 128 entries per band bucket. A warning marks truncation.
5. Hamming distance ≤3 plus word-length ratio ≥0.8 means near duplicate. Similarity is
   `1 - distance/64`; it is **not** semantic or Jaccard similarity.

Four bands guarantee a shared band at distance ≤3 before caps. Caps make worst-case
comparison work linear in document count at the cost of recall on pathological corpora.
Short/empty documents are not compared by SimHash; nonempty short exact matches are allowed.
Store hashes, SimHashes and source references, not all full source text. Disabled detection
returns `not_checked`, never a false assertion of uniqueness.

## Exact scoring formulas

Let W=word units, H=headings, P=paragraphs, E=lists+tables+code blocks, A=heading jumps,
B=boilerplate ratio; booleans are 0/1. Round each component to two decimals, then sum.

- **Content /30:** `30 * min(1, ln(1+W)/ln(601))`.
- **Structure /20:** `max(0, 4*title + 6*min(H/3,1) + 6*min(P/4,1) + 4*min(E/2,1) - min(A,2))`.
- **Cleanliness /15:** `15 * (1 - max(0,B-0.25)/0.75)`; normal chrome gets a 25% allowance.
- **Uniqueness /15:** unique=15, near=5, exact=0, not checked=7.5.
- **Metadata /10:** title=4; description=2; canonical=2; JSON-LD=2.
- **Accessibility /10:** ok=10, too_short=7, empty/likely-JS=2, other=0. Dataset content is
  scored for supplied parseability; it makes no claim of a successful source HTTP request.
- For empty/likely-JS content, cap content at 3 and cleanliness at 5.
- Failed/skipped records have six zero components and cannot be recommended or billed.

Profiles, in precedence order: FAQ title; navigation/index (<150 words and ≥15 internal
links); short (<80 words); documentation (code or /docs/ or /tutorial/); article (≥2
paragraphs and a heading); unknown. Value: high if ≥200 words and ≥2 headings; medium
if ≥60 words; otherwise low. Navigation, non-ok status and duplicates force low value.

Recommendation: audited AND score≥70 AND content=ok AND W≥60 AND unique/not_checked
AND not navigation/index. These explicit proxies do not infer topic relevance.

## Tokens and chunking

`estimated_tokens = ceil(len(extracted_unicode_text)/4)`; empty text=0. Not model-specific.
Chunk profile precedence: zero→0/0; ≤256 tokens→one chunk/no overlap; FAQ→256/32;
>2,000 tokens and ≥5 headings→768/96; ≤600 tokens→384/48; otherwise→512/64.
All numbers are starting recommendations requiring downstream retrieval evaluation.

## Robots and URL decisions

Protego evaluates observed user-agent rules. Missing 404/410 allows with warning;
unavailable/denied/malformed responses fail closed. Disabling checks returns null for
robots_allowed and false for robots_checked. Robots bootstrap redirects still undergo
network/host checks; applying rules to their own retrieval would be circular.

Normalize relative URLs, hostname/scheme case, IDNA, trailing DNS dot, default ports,
fragments and a documented tracking allowlist (`utm_*`, fbclid, gclid, dclid, msclkid,
mc_cid, mc_eid, _ga, _gl). Sort query keys stably; preserve repeated-key value order.
Preserve unknown parameters and path trailing slashes. Unusual signed/query-order-sensitive
resources can fail normalization; V1 favors ordinary public documentation/content URLs.

## Aggregation and reconciliation

- Discovered: distinct eligible URLs admitted to the bounded frontier; in dataset mode,
  source itemCount if supplied. Counts are observations, not total website size.
- Selected: URLs scheduled/source rows read, including unpublished work when budget stops.
- Processed: accepted successful dataset rows plus diagnostic KVS entries.
- `processed = audited + failed + skipped` exactly.
- `audited = unique + exact + near + not_checked`; recommended≤audited.
- Overall score: mean of audited unique/not_checked non-navigation pages. Null denominator
  gives null score. Mean component values may differ by a rounding cent from the overall mean.
- Corpus tokens: recommended pages only. Analyzed tokens: all successful analyses.
- Top issues: count each issue once per page, stable frequency/text ordering, top 10.
- Pattern suggestions remain empty rather than inventing coverage rules.
- `request_count` counts attempted website transport requests including auxiliary files,
  redirects and retries. Dataset SDK/storage API traffic is excluded and must be measured
  separately for benchmarks. No source HTTP traffic is performed in dataset mode.

## PPE semantics and failure handling

Only six-component successful analyses request `page-audited` through SDK `push_data`.
Duplicates, JS shells, empty fetched HTML and low-value content are valid diagnoses.
Unusable dataset HTML/text, blocked URLs, unsupported MIME and fetch errors are not.
Diagnostics go to KVS, avoiding synthetic dataset-item events for unbilled failures.

Before every successful push, the SDK computes affordability including any synthetic
dataset event configured on the platform. Publication is sequential. No final price lives
in code. Configure only the custom event to preserve the advertised contract. The report
separates eligible result count, event requests and SDK-reported charged count.

Apify's push/charge operation is not a transactional database commit across services. A
crash during publication can leave partial rows or uncertain charging. V1 rejects nonempty
output datasets at startup rather than resuming and charging analyses twice. A fresh run is
required. Completed output remains available; no exactly-once billing guarantee is claimed.

Fatal failures: invalid job input, unsafe starting URL, inaccessible source dataset or storage
failure. Per-resource failures become structured diagnostics. An empty accessible dataset
is a successful empty audit with a warning; it is not a nonexistent/inaccessible dataset.

## Dependencies and maintenance

Four direct runtime libraries: Apify for its platform contract, HTTPX for async transport,
Beautiful Soup for tolerant local parsing, Protego for robots. Standard library handles
SimHash, token estimates, XML, gzip and validation. The SDK transitively requires Crawlee;
no Crawlee crawler/browser is instantiated. Direct dependency versions are pinned to those
tested. Transitive updates require rerunning tests and Cloud validation before release.
