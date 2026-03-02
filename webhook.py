import requests
import logging
import time
from typing import Dict, Any

logger = logging.getLogger(__name__)

class WebhookClient:
    """Handles webhook delivery to external systems with robust retries."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize webhook client with endpoint configuration.
        """
        self.config = config.get("apis", {}).get("webhooks", {})
        self.crm_endpoint = self.config.get("crm_endpoint")
        self.email_endpoint = self.config.get("email_endpoint")
        self.max_retries = self.config.get("max_retries", 3)
        self.timeout = self.config.get("timeout", 10)
    
    def _post_with_retry(self, url: str, payload: Dict[str, Any]) -> bool:
        """
        Execute POST with exponential backoff on server errors.
        """
        if not url:
            logger.warning(f"Webhook URL missing for delivery.")
            return False
            
        retries = 0
        while retries <= self.max_retries:
            try:
                response = requests.post(url, json=payload, timeout=self.timeout)
                
                if response.status_code == 200 or response.status_code == 201:
                    logger.info(f"Webhook delivered successfully to {url}")
                    return True
                
                # Handle Rate Limiting (429) explicitly if needed
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 1))
                    logger.warning(f"Rate limited (429) on webhook {url}, retrying in {retry_after}s...")
                    time.sleep(retry_after)
                    continue

                # Server Errors (500+)
                if response.status_code >= 500:
                    logger.warning(f"Server error on webhook ({response.status_code}), attempt {retries+1}/{self.max_retries+1}")
                else:
                    logger.error(f"Webhook failed with status {response.status_code}: {response.text}")
                    return False

            except requests.exceptions.RequestException as e:
                logger.error(f"Webhook delivery exception: {e}, attempt {retries+1}/{self.max_retries+1}")
            
            retries += 1
            if retries <= self.max_retries:
                time.sleep(2 ** retries)
                
        return False
    
    def fire_crm(self, payload: Dict[str, Any]) -> bool:
        """
        Send lead payload to CRM.
        """
        return self._post_with_retry(self.crm_endpoint, payload)
        
    def fire_email(self, payload: Dict[str, Any]) -> bool:
        """
        Send campaign payload to Email platform.
        """
        return self._post_with_retry(self.email_endpoint, payload)

    def fire(self, payload: Dict[str, Any]) -> bool:
        """
        Legacy fire method (broadcasts to both CRM and email if relevant).
        """
        success = True
        if self.crm_endpoint:
            success &= self.fire_crm(payload)
        if self.email_endpoint:
            success &= self.fire_email(payload)
        return success