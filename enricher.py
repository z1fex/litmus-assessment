import time
import requests
import logging
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class Enricher:
    """Handles data enrichment for firms."""

    def __init__(self, base_url: str, max_retries: int = 3, timeout: int = 30):
        """
        Initialize enricher with API configuration.

        Args:
            base_url: Base URL for enrichment API
            max_retries: Maximum number of retries for failed requests
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.timeout = timeout

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Internal method to make API requests with retries and exponential backoff.
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        retries = 0
        
        while retries <= self.max_retries:
            try:
                response = requests.request(method, url, timeout=self.timeout, **kwargs)
                
                # Handle Success
                if response.status_code == 200:
                    return response.json()
                
                # Handle Rate Limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 1))
                    logger.warning(f"Rate limited (429). Retrying after {retry_after}s...")
                    time.sleep(retry_after)
                    # Don't increment retry counter for rate limits, just retry
                    continue
                
                # Handle Server Errors (500)
                if response.status_code >= 500:
                    logger.warning(f"Server error ({response.status_code}) for {url}. Attempt {retries + 1}/{self.max_retries + 1}.")
                else:
                    logger.error(f"Request failed with status {response.status_code} for {url}")
                    return None
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Request exception for {url}: {str(e)}. Attempt {retries + 1}/{self.max_retries + 1}.")
            
            # Exponential backoff for non-429 errors
            retries += 1
            if retries <= self.max_retries:
                wait_time = 2 ** retries
                time.sleep(wait_time)
        
        logger.error(f"Max retries exceeded for {url}")
        return None

    def fetch_firmographic(self, firm_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch firmographic data for a firm.
        """
        endpoint = f"firms/{firm_id}/firmographic"
        data = self._make_request("GET", endpoint)
        
        if data:
            # Handle schema inconsistency: normalize "lawyer_count" to "num_lawyers"
            if "lawyer_count" in data and "num_lawyers" not in data:
                data["num_lawyers"] = data.pop("lawyer_count")
            
            # Basic validation/normalization
            if "num_lawyers" not in data:
                logger.debug(f"Firmographic data for {firm_id} missing num_lawyers")
                
        return data

    def fetch_contact(self, firm_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch contact information for a firm.
        """
        endpoint = f"firms/{firm_id}/contact"
        return self._make_request("GET", endpoint)