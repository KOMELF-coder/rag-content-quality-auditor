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
- **Apify Cloud validation not executed.** No Cloud run, published Store listing,
  real customer charge, platform cost or Cloud memory measurement is claimed.

The final offline test count and self-review record are in [REVIEW.md](REVIEW.md).
Generated local run files live under ignored `validation-output/`; synthetic public
examples are committed under `examples/` and are not live performance evidence.

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

## Apify Cloud validation still required

1. Connect the GitHub repository, build using `.actor/actor.json`, and select a modest
   memory allocation (start at 512 MB; measure before reducing it).
2. Check the Store/Console input form: website/dataset modes, eight-page prefill,
   advanced settings, required dataset ID runtime error and valid limits.
3. Run the suggested website input. Inspect live rows, report/diagnostic links and logs.
4. Create/read a controlled source dataset containing text, Markdown, HTML, duplicates,
   a missing URL, an unusable row and an empty dataset. Verify dataset access permissions
   and exact source-row identities. Also try an inaccessible dataset ID.
5. Configure only custom `page-audited` PPE events after pricing review. Use platform
   testing facilities to verify analyzed/failed/skipped counts, event ledger and a budget
   allowing exactly one result. Do not substitute a local simulated charge for this check.
6. Interrupt a run after publication; verify partial data remains and restart fails clearly
   instead of republishing old results. Test platform timeout/migration behavior.
7. Compare dataset count, DIAGNOSTICS length, report totals and actual billing ledger.
8. Record run/build IDs, runtime, peak memory and platform cost. Verify low-budget stopping
   does not silently omit rows that the report says were published.
9. Check GitHub Actions and Docker results before considering a public Store release.

## Benchmarks and known limits

Follow [BENCHMARK_PLAN.md](BENCHMARK_PLAN.md); no final price has been selected. The largest
supported input and pathological document sizes need Cloud memory/runtime measurement.
Core limitations: no rendering/auth/PDF extraction; exact-host crawling; heuristic lexical
deduplication/quality signals; approximate tokens; no semantic relevance test; no resumable
partial runs; one-row dataset pagination can add API overhead. Standard robots allow/disallow
rules are enforced; Crawl-delay/Request-rate scheduling is not implemented in V1.
