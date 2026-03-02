"""
Instrumented pipeline runner that tracks exact statistics per run.
Outputs a machine-readable STATS.json at the end.
"""
import json
import yaml
import logging
import requests
import time
from typing import Dict, Any, Optional, Set
from enricher import Enricher
from scorer import ICPScorer
from router import LeadRouter
from experiment import ExperimentAssigner
from webhook import WebhookClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class InstrumentedWebhookClient(WebhookClient):
    def __init__(self, config):
        super().__init__(config)
        self.stats = {
            "crm_fired": 0, "crm_succeeded": 0, "crm_failed": 0,
            "email_fired": 0, "email_succeeded": 0, "email_failed": 0,
        }

    def fire_crm(self, payload):
        self.stats["crm_fired"] += 1
        result = super().fire_crm(payload)
        if result:
            self.stats["crm_succeeded"] += 1
        else:
            self.stats["crm_failed"] += 1
        return result

    def fire_email(self, payload):
        self.stats["email_fired"] += 1
        result = super().fire_email(payload)
        if result:
            self.stats["email_succeeded"] += 1
        else:
            self.stats["email_failed"] += 1
        return result


class InstrumentedPipeline:
    def __init__(self, config_path: str):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.apis_config = self.config.get("apis", {})
        self.enrich_api = self.apis_config.get("enrichment", {})

        self.enricher = Enricher(
            base_url=self.enrich_api.get("base_url", "http://localhost:8000"),
            max_retries=self.enrich_api.get("max_retries", 3),
            timeout=self.enrich_api.get("timeout", 30)
        )
        self.scorer = ICPScorer(self.config)
        self.router = LeadRouter(self.config)
        self.assigner = ExperimentAssigner(self.config)
        self.webhook_client = InstrumentedWebhookClient(self.config)
        self.processed_domains: Set[str] = set()

        self.stats = {
            "pages_fetched": 0,
            "firms_fetched_total": 0,
            "duplicates_skipped": 0,
            "enrichment_failures": 0,
            "firms_scored": 0,
            "routes": {"high_priority": 0, "nurture": 0, "disqualified": 0},
            "errors": [],
        }

    def _fetch_firms(self, page: int = 1) -> Optional[Dict[str, Any]]:
        url = f"{self.enrich_api.get('base_url', 'http://localhost:8000').rstrip('/')}/firms"
        retries = 0
        while retries < 3:
            try:
                response = requests.get(url, params={"page": page, "per_page": 10}, timeout=10)
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 1))
                    logger.warning(f"Rate limited fetching firms page {page}. Waiting {retry_after}s...")
                    time.sleep(retry_after)
                    continue
                else:
                    err = f"Firms fetch status: {response.status_code} on page {page}"
                    logger.error(err)
                    self.stats["errors"].append(err)
            except Exception as e:
                err = f"Firms fetch exception on page {page}: {e}"
                logger.error(err)
                self.stats["errors"].append(err)
            retries += 1
            time.sleep(1)
        return None

    def run(self):
        logger.info("=== Starting Instrumented GTM Pipeline ===")
        page = 1

        while True:
            logger.info(f"Fetching page {page}...")
            data = self._fetch_firms(page=page)
            if not data:
                logger.warning(f"No data returned for page {page}. Stopping.")
                break

            firms = data.get("items", [])
            total_pages = data.get("total_pages", 1)
            self.stats["pages_fetched"] += 1
            self.stats["firms_fetched_total"] += len(firms)

            for firm in firms:
                firm_id = firm.get("id")
                domain = firm.get("domain", "").lower().strip()

                if domain in self.processed_domains:
                    logger.info(f"  [DEDUP] Skipping duplicate domain: {domain}")
                    self.stats["duplicates_skipped"] += 1
                    continue
                self.processed_domains.add(domain)

                logger.info(f"  [ENRICH] {firm.get('name')} ({domain})")
                firmographic = self.enricher.fetch_firmographic(firm_id)
                contact = self.enricher.fetch_contact(firm_id)

                if not firmographic:
                    logger.warning(f"  [SKIP] Enrichment failed for {firm_id}")
                    self.stats["enrichment_failures"] += 1
                    self.stats["errors"].append(f"Enrichment failure for {firm_id}")
                    continue

                score = self.scorer.score(firmographic)
                route = self.router.route(firmographic, score)
                self.stats["firms_scored"] += 1
                self.stats["routes"][route] = self.stats["routes"].get(route, 0) + 1

                logger.info(f"  [SCORE] {firm.get('name')}: score={score}, route={route}")

                if route == "disqualified":
                    continue

                lead_data = {
                    "firm_id": firm_id,
                    "name": firmographic.get("name"),
                    "domain": domain,
                    "score": score,
                    "route": route,
                    "contact_info": contact
                }
                variant = self.assigner.assign_variant(firm_id)
                lead_data["experiment_variant"] = variant

                if route == "high_priority":
                    self.webhook_client.fire_crm({"event": "new_lead", "priority": "high", "data": lead_data})

                self.webhook_client.fire_email({
                    "event": "assign_campaign",
                    "variant": variant,
                    "lead_email": contact.get("email") if contact else None,
                    "data": lead_data
                })

            if page >= total_pages:
                break
            page += 1

        self.stats["webhooks"] = self.webhook_client.stats

        logger.info("=== Pipeline Complete ===")
        logger.info(json.dumps(self.stats, indent=2))

        with open("STATS.json", "w") as f:
            json.dump(self.stats, f, indent=2)

        return self.stats


if __name__ == "__main__":
    p = InstrumentedPipeline("config.yaml")
    p.run()
