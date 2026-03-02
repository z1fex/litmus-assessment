# GTM Data Pipeline — Implementation Write-Up

## How to Run

### Prerequisites
- Python 3.9+
- Virtual environment with dependencies installed

```bash
# One-time setup (already done via litmus init)
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
```

### Start the Mock Server
Open a terminal in the project directory and run:

```bash
python mock_server.py
```

The server starts on `http://localhost:8000`. You can explore its API schema at `http://localhost:8000/docs`. Leave this terminal running.

### Run the Pipeline
In a second terminal:

```bash
.\venv\Scripts\python pipeline.py
```

### Expected Output
You will see timestamped log lines for every firm processed, including:
- `[INFO] Enriching Firm: Baker & Sterling LLP (bakersterling.com)` — enrichment started
- `[INFO] Firm: Baker & Sterling LLP, Score: 0.7, Route: high_priority` — score and route
- `[WARNING] Rate limited (429). Retrying after 60s...` — rate limit handling (expected)
- `[WARNING] Server error (500) for .../firmographic. Attempt 1/4.` — transient error backoff (expected)
- `[INFO] Webhook delivered successfully to http://localhost:8000/webhooks/crm` — delivery confirmation
- `[INFO] Pipeline Complete. Processed 46 firms.` — final summary

**A full run processes 55 firms, skips 5 duplicates, and takes approximately 15–25 minutes** due to the 20 req/min rate limit enforced by the mock server.

---

## Approach

### 1. Pipeline Orchestration (`pipeline.py`)

The `GTMPipeline` class in `pipeline.py` is the central orchestrator. Its `__init__` method (lines 17–36) reads `config.yaml` via `yaml.safe_load()` and instantiates each component — `Enricher`, `ICPScorer`, `LeadRouter`, `ExperimentAssigner`, and `WebhookClient` — passing the full config dict to each so they can read their own relevant sections.

The `run()` method (lines 59–140) drives a simple outer loop over paginated pages. On each iteration, it calls `_fetch_firms(page)`, walks the returned `items` list, and applies each processing stage in sequence: deduplicate → enrich → score → route → assign → fire webhooks. The loop terminates when the response's `page >= total_pages` (line 135) or when no items are returned.

I chose a sequential loop over each firm rather than concurrent batch processing. This is explained in the Trade-offs section below.

### 2. Resilient API Integration (`enricher.py`, `webhook.py`)

All API communication goes through two retry-aware classes.

In `enricher.py`, `_make_request()` (lines 26–66) is the single entry point for all enrichment calls. It runs a `while retries <= self.max_retries` loop (line 33). Two failure modes are handled distinctly:

- **429 Rate Limiting** (lines 42–47): When the server returns 429, the code reads the `Retry-After` response header (`response.headers.get("Retry-After", 1)` on line 43) and calls `time.sleep(retry_after)`. Critically, the loop uses `continue` rather than incrementing `retries` — 429s do not count against the retry budget, because they are not errors in the client.

- **500 Server Errors** (lines 50–63): A 500 logs a warning and falls through to the exponential backoff: `wait_time = 2 ** retries` on line 62. So the first retry waits 2s, the second 4s, the third 8s. After `max_retries` (3, from config) consecutive 500s, the method returns `None` (line 66).

- **Network Exceptions** (lines 56–57): `requests.exceptions.RequestException` is caught and logged without crashing the pipeline.

In `webhook.py`, `_post_with_retry()` (lines 21–59) applies the same pattern — 429s sleep and retry without consuming the retry budget (lines 39–43), 500s trigger exponential backoff (line 57: `time.sleep(2 ** retries)`), and non-retriable errors (4xx) return `False` immediately (line 50).

### 3. Data Enrichment and Schema Normalisation (`enricher.py`)

`fetch_firmographic()` (lines 68–84) fetches from `GET /firms/{id}/firmographic`. The mock server inconsistently returns either `num_lawyers` or `lawyer_count` for the same field (~25% of the time). After the request succeeds, lines 77–78 handle this:

```python
if "lawyer_count" in data and "num_lawyers" not in data:
    data["num_lawyers"] = data.pop("lawyer_count")
```

This normalises the field in-place before the dict is passed downstream to the scorer. The scorer then always reads `firm.get("num_lawyers")` safely.

`fetch_contact()` (lines 86–91) returns the raw contact dict. The mock server returns `null` for `email` or `linkedin_url` on ~30% of contacts. The pipeline does not skip firms with missing contact fields — the lead is still scored and routed, and the email webhook simply fires with `lead_email: null` (pipeline.py line 129). This is intentional: missing contact data is an enrichment gap, not a disqualification.

### 4. Deduplication (`pipeline.py`)

The `processed_domains` set is declared in `__init__` on line 36: `self.processed_domains: Set[str] = set()`. Inside `run()`, each firm's domain is normalised via `.lower().strip()` (line 76) before being checked against this set (line 79). If a match is found, the firm is logged and skipped. Otherwise it is added to the set (line 82) before any further processing.

The dataset contains 5 near-duplicate firm pairs (firm_051–055) that share domains with firm_001, 003, 039, 043, and 048. All 5 are correctly skipped on page 6 when they appear.

I chose domain as the deduplication key because it is stable, normalised, and always present in the `/firms` list response. Name-based matching would require fuzzy string comparison and threshold tuning — added complexity with diminishing returns for this dataset. This trade-off is discussed further below.

### 5. ICP Scoring (`scorer.py`)

`ICPScorer.score()` (lines 19–37) computes a weighted composite of three sub-scores, each independently returning a float in `[0.0, 1.0]`:

The weights are defined in the `__init__` method (lines 13–17):
```python
self.weights = {
    "firm_size": 0.4,
    "practice_areas": 0.4,
    "geography": 0.2
}
```

Firm size and practice area alignment are each weighted at 40% because they are the strongest signals of whether a firm needs, and can budget for, a legal AI product. Geography is 20% — it signals regulatory compatibility but is less decisive than the firm's size and work type.

Each sub-scorer degrades gracefully on missing data:
- `_score_firm_size()` (lines 39–55): returns `0.0` if `num_lawyers` is absent. Firms in the sweet spot (50–500 lawyers) score `1.0`; above 500 score `0.8` (large firms are slightly less ideal but not excluded); below 50 score proportionally via `(num_lawyers / min_lawyers) * 0.5`.
- `_score_practice_areas()` (lines 57–71): returns `0.0` if no practice areas returned, `1.0` if the preferred list is empty. Otherwise divides the number of matching areas by the number of preferred areas.
- `_score_geography()` (lines 73–85): binary — `1.0` if the firm's country is in `preferred_regions` from config, `0.0` otherwise.

### 6. Lead Routing (`router.py`)

`LeadRouter.route()` maps score to category using two thresholds:
- `score >= 0.7` → `"high_priority"` — these firms receive both a CRM webhook and an email campaign assignment.
- `0.4 <= score < 0.7` → `"nurture"` — email campaign only.
- `score < 0.4` → `"disqualified"` — skipped entirely from all downstream steps (pipeline.py line 99–100).

The thresholds 0.7 and 0.4 were chosen based on the scoring formula: a firm that qualifies on both firm size (0.4 weight) and at least one practice area (0.4 weight) will score ~0.8+, landing solidly in high priority. A firm scoring in the 0.4–0.7 band typically matches on one dimension only — worth warming up but not prioritising. Below 0.4 means the firm fails the two heaviest criteria simultaneously.

### 7. Experiment Assignment (`experiment.py`)

`ExperimentAssigner.assign_variant()` (lines 16–25) uses Python's `hashlib.md5` to compute a deterministic hash of the `firm_id` string:

```python
hasher = hashlib.md5(lead_id.encode('utf-8'))
hash_val = int(hasher.hexdigest(), 16)
variant_idx = hash_val % len(self.variants)
```

The variant list is read from `config.yaml` at `experiments.email_variants` (line 12). I chose MD5 hashing over random assignment for one specific reason: **idempotency**. If the pipeline is re-run against the same firm (e.g., a retry after a crash, or a scheduled re-sync), the firm will receive the same variant every time. This ensures A/B experiment integrity — a firm cannot be assigned to variant A on Monday and variant B on Wednesday.

### 8. Webhook Delivery (`webhook.py`, `pipeline.py`)

The `WebhookClient` exposes two explicit methods — `fire_crm()` (line 61) delegates to `_post_with_retry(self.crm_endpoint, payload)` and `fire_email()` (line 67) delegates to `_post_with_retry(self.email_endpoint, payload)`. This separation makes it clear at the call site in `pipeline.py` which system is being notified.

The routing logic in `pipeline.py` (lines 118–131) fires webhooks differentially:
- `high_priority` firms fire both CRM (lines 119–123) and email (lines 126–131).
- `nurture` firms fire email only.

Both endpoints are configured via `config.yaml` under `apis.webhooks.crm_endpoint` and `apis.webhooks.email_endpoint`. The `WebhookClient.__init__` reads these on lines 16–17.

---

## Trade-offs

### Synchronous vs. Asynchronous (`pipeline.py`)

The `run()` loop in `pipeline.py` processes one firm at a time, sequentially. This was a deliberate choice rather than an oversight.

The mock server enforces a hard rate limit of 20 requests/minute globally, shared across all endpoint types. Each firm requires at minimum 2 enrichment calls (`/firmographic` and `/contact`) plus up to 2 webhook calls — meaning a single firm can consume 4 rate-limit slots. At 50 firms, that is up to 200 requests, requiring at minimum 10 minutes at the enforced rate.

An `asyncio`-based approach with a semaphore would allow parallel enrichment of multiple firms, but it would hit the 429 ceiling sooner and more frequently, adding complexity for marginal gain at this scale. The synchronous model stays naturally under the rate limit without coordination overhead and produces simpler, more debuggable log output.

In production with 10,000+ firms (see Real-World Considerations), async would be essential.

### Domain-Based Deduplication (`pipeline.py`, line 36 and 76–82)

The `processed_domains: Set[str]` approach was chosen over name-similarity matching for two reasons:

1. **Reliability**: Domains are machine-readable identifiers — `bakersterling.com` is unambiguous in a way that "Baker & Sterling LLP" vs "Baker Sterling LLP" is not. String fuzzy matching requires tuning a similarity threshold and still produces false positives.

2. **Availability**: The `/firms` list endpoint returns `domain` for every firm. This avoids requiring an additional enrichment call just to get data needed for deduplication.

The trade-off is that firms with different domains that are the same legal entity (e.g., a firm re-branded or acquired) would not be deduplicated. For this dataset and assessment scope, domain exactly identifies duplicates.

### Deterministic Hashing for Experiments (`experiment.py`, lines 21–24)

Random assignment (`random.choice()`) would distribute variants evenly across a single run but would re-assign firms differently on each pipeline execution. This breaks the contract of A/B testing: you cannot attribute outcome differences to the variant if the treatment group changes between measurement periods.

MD5 hashing of `firm_id` guarantees that `firm_001` always maps to `variant_a` and `firm_002` always maps to `variant_b`, regardless of when or how many times the pipeline runs. The modulo operator (`% len(self.variants)`) naturally distributes across any number of variants without bias for large hash spaces.

### Weighted Scoring (`scorer.py`, lines 13–17)

A simple threshold filter (e.g., "must have >50 lawyers AND be in a preferred country") would produce binary pass/fail outcomes and lose gradient information. Weighted scoring allows partial-fit firms to be routed to nurture rather than discarded entirely — a firm that is the right size but in an unpreferred region is still a warm prospect worth a slow-burn email sequence.

Firm size and practice area are equally weighted at 0.4 each because they represent the two independent axes of product-market fit: operational scale (can they afford and deploy our product?) and workflow alignment (do they do the kinds of legal work our AI targets?). Geography is a softer constraint at 0.2 — it signals regulatory and language compatibility but doesn't override a strong product-market fit.

---

## Edge Cases Handled

### Missing Firmographic Data Entirely
If `Enricher.fetch_firmographic()` returns `None` after exhausting all retries (e.g., persistent 500s), the check on `pipeline.py` line 89 catches this: `if not firmographic: ... continue`. The firm is logged as a warning and skipped. No scoring, routing, or webhook delivery occurs. This prevents a `None` being passed to `ICPScorer.score()` which would raise an `AttributeError`.

### Missing `num_lawyers` in Firmographic Response
The mock server drops fields on ~20% of responses. If `num_lawyers` is missing and `lawyer_count` is also absent post-normalisation, `_score_firm_size()` in `scorer.py` (lines 40–42) returns `0.0` for the size dimension. The firm still receives scores for practice areas and geography, and will likely land in `disqualified` unless those remaining dimensions are very strong. It is not silently miscounted.

### Missing or Null Contact Email
`fetch_contact()` succeeds (returns a dict), but the `email` key may be `None`. When firing the email webhook (pipeline.py line 129), this propagates as `"lead_email": null` in the payload. The downstream system (mock or real) is expected to handle a null email. The pipeline does not skip or fail a firm because of missing contact data — routing and CRM delivery are unaffected.

### Webhook Failure After All Retries
`_post_with_retry()` in `webhook.py` returns `False` if all retries are exhausted (line 59). The pipeline does not check this return value — delivery failure is logged (line 47: `logger.warning(...)`) but the pipeline continues processing subsequent firms. The trade-off is that a failed webhook delivery is silently accepted without re-queuing. In production, this would feed into a dead-letter queue or alerting system.

### Rate Limit on Webhook Endpoint
The mock server also enforces rate limits on `POST /webhooks/*`. `_post_with_retry()` handles this on lines 39–43: it detects 429, reads `Retry-After`, sleeps, and retries without consuming the retry budget.

---

## Real-World Considerations

### Scaling from 55 to 10,000 Firms

The current synchronous design would become untenable at 10,000 firms. Two enrichment calls per firm = 20,000 API requests. At 20 req/min that is over 16 hours of wall-clock time. At scale I would:

1. **Switch to `asyncio` with a rate-limiter**: Use `asyncio.Semaphore` capped to the rate limit (or slightly below, to buffer for webhook calls sharing the same limit). Libraries like `aiohttp` or `httpx` with async support make this straightforward.

2. **Process enrichment in parallel batches**: Firms can be enriched concurrently since enrichment calls are independent. Only webhook delivery and deduplication require coordination.

3. **Replace in-memory deduplication with Redis**: `self.processed_domains: Set[str]` in `pipeline.py` is single-process and lost on restart. A Redis `SADD`/`SISMEMBER` call makes deduplication horizontally scalable and crash-safe.

4. **Introduce a job queue**: Instead of a monolithic script, break ingestion (fetching firm IDs) from enrichment (fetching firmographic/contact) and from delivery (webhooks) into separate queue workers. This allows independent scaling of each stage and clean retry semantics per stage.

### Rate Limiting Strategy at Scale

The current approach — react to 429s when they occur — is correct for a single sequential process but becomes wasteful at scale (you discover the limit by breaching it). At scale:

- **Proactive throttling**: Use a token bucket algorithm client-side. Pre-configure the bucket at 18 req/min (leaving a 10% buffer below the server limit of 20). This avoids 429s almost entirely.

- **Distributed rate limiter**: Use Redis with `INCR` + TTL to share the rate limit budget across multiple pipeline worker processes.

- **Respect `X-RateLimit-Remaining`**: The mock server returns this header on every response. Future implementations could read this header and slow down proactively when remaining drops below a threshold, rather than waiting for a hard 429.

### Monitoring and Alerting

In a production deployment I would add:

- **Prometheus metrics** exported from the pipeline: `pipeline_firms_processed_total`, `pipeline_enrichment_failures_total`, `pipeline_webhook_delivery_failures_total`, `pipeline_api_request_duration_seconds` (histogram). These map directly to the information currently written only to log lines.

- **Alerting rules**: Alert when `enrichment_failures_total` exceeds 5% of processed firms (indicates systemic API issues), or when `webhook_delivery_failures_total` exceeds 0 for CRM (every missed CRM delivery is a lost lead).

- **Structured logging**: Replace `logging.basicConfig` with `structlog` or JSON-formatted output so that log aggregators (Datadog, Splunk) can parse fields like `firm_id`, `score`, `route`, and `webhook_status` without regex.

- **Run summary**: Emit a structured summary event at pipeline completion (like the `STATS.json` written by `run_stats.py`) to a monitoring dashboard, so operators know the health of each run without reading raw logs.

---

## Known Limitations and What I'd Do Differently

1. **ICP weights and routing thresholds are hardcoded**: `scorer.py` lines 13–17 define weights that should be read from `config.yaml` (the config already has `# weight: set your own` comments that hint at this intent). Similarly, `router.py`'s thresholds (0.7 and 0.4) should be configurable. Given more time, I'd add `icp_criteria.weights` and `routing.thresholds` keys to `config.yaml` and read them in both classes.

2. **No name-based fuzzy deduplication**: The README mentions "name similarity" as a deduplication signal. With more time I'd add a secondary check using `difflib.SequenceMatcher` or `rapidfuzz` on normalised firm names after domain matching, to catch any cases where two entries share a name but have different domains.

3. **Synchronous `_fetch_firms` lacks exponential backoff**: Unlike `Enricher._make_request()`, the `_fetch_firms()` method in `pipeline.py` (lines 42–56) uses a flat `time.sleep(1)` on retries rather than exponential backoff. This is an inconsistency I'd correct by extracting the retry logic into a shared utility function used by both.

4. **No dead-letter queue for webhook failures**: Currently a webhook delivery failure is logged and the pipeline moves on. In production, failed deliveries would be written to a dead-letter queue (SQS, Redis List, or a database table) for manual review or automatic re-processing.
