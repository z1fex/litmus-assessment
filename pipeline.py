import yaml
import logging
import requests
import time
from typing import Dict, Any, List, Optional, Set
from enricher import Enricher
from scorer import ICPScorer
from router import LeadRouter
from experiment import ExperimentAssigner
from webhook import WebhookClient

# Initialize Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class GTMPipeline:
    def __init__(self, config_path: str):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
            
        self.apis_config = self.config.get("apis", {})
        self.enrich_api = self.apis_config.get("enrichment", {})
        
        # Initialize internal components
        self.enricher = Enricher(
            base_url=self.enrich_api.get("base_url", "http://localhost:8000"),
            max_retries=self.enrich_api.get("max_retries", 3),
            timeout=self.enrich_api.get("timeout", 30)
        )
        self.scorer = ICPScorer(self.config)
        self.router = LeadRouter(self.config)
        self.assigner = ExperimentAssigner(self.config)
        self.webhook_client = WebhookClient(self.config)
        
        # In-memory deduplication set: using domains for simplicity
        self.processed_domains: Set[str] = set()

    def _fetch_firms(self, page: int = 1) -> Optional[Dict[str, Any]]:
        """Paginated fetching with basic retries."""
        url = f"{self.enrich_api.get('base_url', 'http://localhost:8000').rstrip('/')}/firms"
        retries = 0
        while retries < 3:
            try:
                response = requests.get(url, params={"page": page}, timeout=10)
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 1))
                    time.sleep(retry_after)
                    continue
                else:
                    logger.error(f"Firms fetch status: {response.status_code}")
            except Exception as e:
                logger.error(f"Firms fetch exception: {e}")
            retries += 1
            time.sleep(1)
        return None

    def run(self):
        logger.info("Starting GTM Pipeline...")
        page = 1
        processed_count = 0
        
        while True:
            logger.info(f"Processing Page {page}...")
            data = self._fetch_firms(page=page)
            if not data:
                break
                
            firms = data.get("items", [])
            if not firms:
                break
                
            for firm in firms:
                firm_id = firm.get("id")
                domain = firm.get("domain", "").lower().strip()
                
                # Deduplication logic: Check domain
                if domain in self.processed_domains:
                    logger.info(f"Duplicate domain skipped: {domain}")
                    continue
                self.processed_domains.add(domain)
                
                # Start Enrichment
                logger.info(f"Enriching Firm: {firm.get('name')} ({domain})")
                firmographic = self.enricher.fetch_firmographic(firm_id)
                contact = self.enricher.fetch_contact(firm_id)
                
                if not firmographic:
                    logger.warning(f"Skipping firm {firm_id} due to enrichment failure.")
                    continue
                
                # Scoring
                score = self.scorer.score(firmographic)
                route = self.router.route(firmographic, score)
                
                logger.info(f"Firm: {firm.get('name')}, Score: {score}, Route: {route}")
                
                if route == "disqualified":
                    continue
                    
                # Prepare Lead Record
                lead_data = {
                    "firm_id": firm_id,
                    "name": firmographic.get("name"),
                    "domain": domain,
                    "score": score,
                    "route": route,
                    "contact_info": contact
                }
                
                # Experiment Assignment for all qualified (Nurture or High Priority)
                variant = self.assigner.assign_variant(firm_id)
                lead_data["experiment_variant"] = variant
                
                # Webhook delivery:
                # 1. High Priority goes to CRM immediately
                if route == "high_priority":
                    self.webhook_client.fire_crm({
                        "event": "new_lead",
                        "priority": "high",
                        "data": lead_data
                    })
                
                # 2. Assign campaign (all qualified)
                self.webhook_client.fire_email({
                    "event": "assign_campaign",
                    "variant": variant,
                    "lead_email": contact.get("email") if contact else None,
                    "data": lead_data
                })
                
                processed_count += 1
                
            if page >= data.get("total_pages", 1):
                break
            page += 1
            
        logger.info(f"Pipeline Complete. Processed {processed_count} firms.")
        return {"processed": processed_count}

def run_pipeline(config_path: str) -> Any:
    pipeline = GTMPipeline(config_path)
    return pipeline.run()

if __name__ == "__main__":
    run_pipeline("config.yaml")
