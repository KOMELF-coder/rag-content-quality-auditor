# Validation

## Evidence recorded on 2026-09-30

Environment: Windows, Python 3.12.14, Apify SDK 3.4.1, HTTPX 0.28.1.

- Offline pytest suite covers input limits, SSRF/DNS/redirects, robots, sitemap recursion,
  body/decompression bounds, extraction, multilingual/SPA content, duplicates, scoring,
  chunks, dataset adapters, aggregation, billing and budget boundaries.
- Real Apify SDK local storage smoke runs completed in both modes. Website fixture:
  1 audited document. Dataset fixtures: 2 audited and 1 skipped. No customer charges.
- The actual `python -m my_actor` entry point completed with the supplied eight-page
  website input and persisted eight result rows plus AUDIT_REPORT and DIAGNOSTICS.
- Manual live audit of `https://docs.python.org/3/tutorial/` with `.actor/INPUT.json`:
  17 eligible URLs discovered, 8 selected/analyzed, 0 failed, 0 skipped, 0 duplicates,
  8 recommended, 12 website HTTP requests. Estimated retained tokens: 32,973.
  Mean score: 96.75; median: 98.0. Standalone observed runtime: 1.625 seconds.
  This is a single local functional check, **not** an Apify Cloud benchmark or cost claim.
- The initial live attempt failed certificate-chain validation. The transport now uses
  the OS trust store with TLS verification enabled; the successful run used that fix.
- All four Apify definition files were validated against downloaded official actor,
  input, dataset and output meta-schemas, in addition to local JSON Schema checks.
- **Docker build not executed in this environment.** No Docker executable/installation
  was found. CI includes a Linux Docker build but its result must be checked separately.
- **Apify Cloud validation executed on 2026-09-30.** The linked GitHub build succeeded
  and both website and existing-dataset modes completed under LIMITED_PERMISSIONS.
  Controlled dataset mode verified read-only dataset access, five successful analyses,
  one unusable-row skip, exact-duplicate detection and stable source IDs.
- Website Cloud benchmarks used 512 MB memory and concurrency 4 on public Python docs:
  10 selected / 10 successful (~7 s UI, displayed $0.000);
  50 / 43 (~1 min UI, $0.001);
  100 / 92 (1m56s UI, $0.003);
  500 / 491 (16m51s UI, $0.031). The 500-page run processed all 500 selected URLs,
  skipped 9, and reported 0 page-processing failures. These are single-target validation
  measurements, not general performance guarantees.
- A 500-page run with the previous 300-second run timeout timed out after producing
  189 rows; rerunning with a 1,200-second timeout completed successfully. V1 does not
  resume partial runs.

The initial V1 test count and self-review record are in [REVIEW.md](REVIEW.md).
Generated local run files live under ignored `validation-output/`; synthetic public
examples are committed under `examples/` and are not live performance evidence.

## Dataset pagination update — 2026-09-30

Source rows are fetched sequentially in batches of at most 50, requesting
`min(50, max_pages - offset)` items. The generator retains one response batch, releases
it before fetching the next, and performs no prefetch. Pagination retains at most 50
selected source rows alongside the current analysis; individual sizes still matter for Cloud sizing.
Offsets advance by the actual number of returned rows; an empty response ends iteration.
This also handles server responses shorter than requested without skipping indexes.

An unchanged dataset with at least 1,000 rows now needs 20 list-items calls to process
1,000 rows. A dataset ending before the page limit can require one final empty request.
Original zero-based source IDs, ordering, content precedence and billing rules are preserved.
Pagination tests cover small/multiple/partial batches, page-limit cuts, empty datasets,
source IDs, mixed usable/unusable rows, short server responses and early consumer stop.
The full suite completed with `192 passed, 1 warning in 1.19s`; the warning is the existing
Apify SDK transitive-dependency deprecation. `compileall` for my_actor/scripts/tests,
`ruff check`, `ruff format --check` (38 files), local schema validation and validation
against all four previously downloaded official Apify meta-schemas passed.
Docker and Apify Cloud were not run for this change.

## Offline quality gate

```bash
python -m venv .venv
# Activate the environment (Windows: .venv\Scripts\Activate.ps1)
python -m pip install -e ".[test]"
python -m pytest -q -p no:cacheprovider
python -m compileall -q my_actor scripts
python -m ruff check my_actor scripts tests
python -m ruff format --check my_actor scripts tests
python scripts/validate_schemas.py
python scripts/local_smoke.py --mode website
python scripts/local_smoke.py --mode dataset
```

The cache provider is disabled in the listed pytest command because OneDrive/Windows
occasionally denies cache writes in this workspace. Test execution does not need that cache.
No normal pytest test uses the live Internet. `local_smoke.py` uses real SDK/local storage
and mocked website responses; its dataset fixtures do not verify Cloud dataset permissions.

For optional official meta-schema validation, download `actor.json`, `input.json`,
`dataset.json` and `output.json` from the documented Apify schema site to files named
`actor-metaschema.json`, `input-metaschema.json`, `dataset-metaschema.json` and
`output-metaschema.json`, then run:

```bash
python scripts/validate_schemas.py --apify-schema-dir validation-output
```

Schema references: [Actor definition](https://docs.apify.com/actors/development/actor-definition/actor-json),
[input form](https://docs.apify.com/actors/development/actor-definition/input-schema),
[dataset schema](https://docs.apify.com/storage/dataset-schema),
[output schema](https://docs.apify.com/actors/development/actor-definition/output-schema).
The documented meta-schema base is `https://apify-projects.github.io/actor-json-schemas/`.

## Actual local entry point — PowerShell

Use a fresh output directory for each validation run:

```powershell
New-Item -ItemType Directory -Force storage/key_value_stores/default | Out-Null
Copy-Item .actor/INPUT.json storage/key_value_stores/default/INPUT.json
.\.venv\Scripts\python.exe -m my_actor
```

Input is the SDK INPUT record. Results are under `storage/datasets/default`; report and
diagnostics are key-value store records. The SDK may store JSON records without a `.json`
filename extension. V1 deliberately rejects an existing nonempty output dataset when
the SDK exposes it on startup; use a fresh run/storage directory after interruption.

## Docker validation procedure

```bash
docker build -t rag-content-quality-auditor .
docker run --rm rag-content-quality-auditor python -c "from my_actor.main import main; print('imports OK')"
```

Then run with a writable mounted `storage` directory containing the supplied INPUT
and verify successful output/report publication. On Apify, the platform supplies the
input/storage environment. The image has no browser packages or runtime model downloads.
Verify the Python slim system CA bundle and pinned dependency wheels on the target architecture.

## Live validation procedure

```bash
python scripts/live_validation.py --input .actor/INPUT.json
python scripts/live_validation.py --url https://YOUR-PUBLIC-HOST/docs/ --max-pages 5
```

The URL flag permits at most ten pages. An explicit input file can request larger limits;
review it before execution. Pick suitable documentation, SaaS, blog and ecommerce content
sections. Only the Python documentation scenario has been run here. Inspect robots,
extraction, request count, retained content and diagnostic reasons before increasing size.
Keep local output ignored; never commit source credentials or private content.

## Remaining pre-publication validation

1. Configure PPE with only the custom `page-audited` event at the launch price and include
   platform usage in the event price. Verify the live pricing screen before publication.
2. Use Apify's charging/budget controls to verify a budget that permits exactly one result,
   and reconcile the platform event ledger against `billable_result_count`.
3. Try an explicitly inaccessible dataset ID and confirm the permission error is clear.
4. After publication, interrupt a run and verify partial data remains; start a fresh run
   rather than resurrecting because V1 has no resume contract.
5. Record peak memory from platform metrics if available; current validation used 512 MB
   successfully but did not capture a formal peak-RSS figure.
6. Check GitHub Actions/Docker CI status and Actor quality checks before Store release.

## Benchmarks and known limits

Follow [BENCHMARK_PLAN.md](BENCHMARK_PLAN.md); no final price has been selected. The largest
supported input and pathological document sizes need Cloud memory/runtime measurement.
Core limitations: no rendering/auth/PDF extraction; exact-host crawling; heuristic lexical
deduplication/quality signals; approximate tokens; no semantic relevance test; no resumable
partial runs; batches of up to 50 source rows require Cloud memory sizing. Standard robots allow/disallow
rules are enforced; Crawl-delay/Request-rate scheduling is not implemented in V1.
