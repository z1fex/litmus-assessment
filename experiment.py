import hashlib
from typing import Dict, Any

class ExperimentAssigner:
    """Assigns leads to experiment variants using consistent hashing."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize experiment assigner with configuration.
        """
        self.config = config.get("experiments", {})
        self.variants = list(self.config.get("email_variants", {}).keys())
        if not self.variants:
            self.variants = ["variant_a", "variant_b"]

    def assign_variant(self, lead_id: str) -> str:
        """
        Assign a lead to an experiment variant based on deterministic hashing.
        """
        # Using lead_id + deterministic hash ensures that a lead always gets the same variant
        hasher = hashlib.md5(lead_id.encode('utf-8'))
        hash_val = int(hasher.hexdigest(), 16)
        
        variant_idx = hash_val % len(self.variants)
        return self.variants[variant_idx]
