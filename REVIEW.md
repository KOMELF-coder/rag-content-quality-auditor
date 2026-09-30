# Final V1 self-review — 2026-09-30

## A. Engineering

Reviewed network policy, every redirect path, DNS rebinding protection, cookie replay,
body expansion, sitemap cycles, queue bounds, concurrency ordering, duplicate indexing,
budget checks and report reconciliation.

Corrections made during review:

- Preserve verified hostname/SNI while connecting to a validated numeric address; use
  system TLS roots for Windows compatibility. Certificate verification remains enabled.
- Explicitly suppress cookies on each request and remove the header at the real transport.
- Detect HTML supplied in text fields so invisible script bodies cannot be scored as text.
- Convert dataset parse failures to per-row diagnostics; keep storage errors fatal.
- Reject nonempty output datasets at Actor startup to prevent repeated publication on restart.
- Test deterministic result order when concurrent responses finish out of order.
- Add body-expansion, sitemap-cycle, duplicate-bucket, retry and budget boundary cases.
- Use shared Unicode word units for counts and SimHash so unspaced CJK documents do not
  collapse into empty fingerprints and false near-duplicate matches.
- Centralize request/DNS/body limits and pin the four direct runtime dependencies.

Known engineering risks: Cloud memory and billing remain unmeasured; one-row source
pagination can add latency; resumption is deliberately unsupported; SDK publication/charge
is not an atomic cross-service transaction. Near-duplicate candidate caps can reduce recall.
Only robots allow/disallow rules are enforced; directive-based request pacing is not included.

## B. Product

Reviewed first-run input, output table, zero-recommendation behavior, source joins and
actionability. The form suggests eight pages; ordinary API defaults remain documented.
The default table has eight useful columns. Successful analyses, unbilled diagnostics and
the aggregate report have separate links. Source identity remains available without a URL.
Explicit field descriptions distinguish score, RAG-value proxy, include decision, eligible
analysis events and actual platform charges. Canonical/llms metadata is not treated as truth.

The default public Python tutorial passed an eight-page live audit under the Actor's own
host, robots, TLS and network rules. Both modes exercised the real SDK's local storage.
No Cloud dataset access or Cloud UI validation is claimed.

## C. Store / commercial

Reviewed the buyer README, early output example, Store copy, FAQ and pricing language.
The positioning is consistently the quality gate before RAG ingestion. Output examples
come from synthetic fixtures and are labelled. No retrieval-improvement guarantee,
invented integrations, final price, testimonials or fabricated benchmark is included.
Limitations are explicit, including JavaScript/PDF support and approximate token estimates.
The benchmark plan identifies the data needed to set a price after Cloud testing.

## Executed local quality gate

```text
python -m pytest -q -p no:cacheprovider
183 passed, 1 warning in 1.15s

python -m compileall -q my_actor scripts
exit 0

python -m ruff check my_actor scripts tests
All checks passed!

python -m ruff format --check my_actor scripts tests
37 files already formatted

python scripts/validate_schemas.py --apify-schema-dir validation-output
Apify actor/input/dataset/output meta-schemas: valid
Local JSON schemas, default input and example rows: valid

python -m pip check
No broken requirements found.
```

The single pytest warning comes from Apify SDK 3.4.1 importing its deprecated
`apify-shared` transitive dependency; no project test failed. The application imports
the supported Apify SDK rather than using apify-shared directly. Track this upstream
dependency on SDK upgrades.

Core source was searched for TODO/FIXME/placeholder/pass. Remaining matches describe
input placeholders, legitimate prose, and synthetic URL credentials in a rejection test;
none is unfinished implementation or a real secret. `git diff --check` is part of the
pre-commit gate. Docker and Apify Cloud checks remain as documented in VALIDATION.md.
