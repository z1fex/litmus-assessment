# GTM Data Pipeline - Implementation Overvew

## Approach
The pipeline is designed to be a robust, fault-tolerant system for processing law firm leads. Key architectural decisions include:

1.  **Resilient API Integration**:
    *   Implemented an `Enricher` and `WebhookClient` with a shared `_make_request` (or similar) pattern that handles:
        *   **429 Rate Limiting**: Respects the `Retry-After` header sent by the mock server.
        *   **500 Server Errors**: Implements exponential backoff to recover from transient failures.
        *   **Timeouts**: Prevents the pipeline from hanging on unresponsive endpoints.
2.  **Smart Deduplication**:
    *   Firms are deduplicated based on their **normalized domain** (e.g., `bakersterling.com`). This ensures that near-duplicates like "Baker & Sterling LLP" and "Baker Sterling LLP" are only processed once.
3.  **Configurable ICP Scoring**:
    *   The `ICPScorer` uses weights for **Firm Size**, **Practice Areas**, and **Geography**.
    *   It handles schema inconsistencies (e.g., `num_lawyers` vs. `lawyer_count`) during the enrichment phase or scoring phase.
4.  **Deterministic A/B Testing**:
    *   `ExperimentAssigner` uses MD5 hashing of the `firm_id` to ensure that a lead is consistently assigned to the same variant, even if the pipeline is re-run.
5.  **Differentiated Routing**:
    *   **High Priority** leads are immediately synced to the CRM and assigned an email campaign.
    *   **Nurture** leads are assigned an email campaign for slower engagement.
    *   **Disqualified** leads are filtered out to save resources.

## Trade-offs & Challenges
*   **Synchronous vs Asynchronous**: I chose a synchronous, paginated approach for simplicity and to stay well within the 20 req/min rate limit without over-complexifying the concurrency logic. In a production environment, I'd use `asyncio` with an adaptive semaphore.
*   **In-Memory Deduplication**: Currently using a Python `set`. For a distributed system, this would move to Redis.

## Future Improvements
*   **Advanced Deduplication**: Use fuzzy matching on firm names (Levenshtein distance) for firms without domains.
*   **Database Persistence**: Store progress in a database so the pipeline can resume from the last processed page in case of a crash.
*   **Monitoring**: Add Prometheus metrics for monitoring success rates and latency across the different API components.
