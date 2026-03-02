from typing import Dict, Any, List

class ICPScorer:
    """Scores firms against ideal customer profile criteria."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize scorer with ICP configuration.
        """
        self.config = config.get("icp_criteria", {})
        
        # Define weights (can be made configurable in yaml, but hardcoding reasonable defaults here)
        self.weights = {
            "firm_size": 0.4,
            "practice_areas": 0.4,
            "geography": 0.2
        }
    
    def score(self, firm: Dict[str, Any]) -> float:
        """
        Calculate ICP score for a firm.
        """
        total_score = 0.0
        
        # 1. Firm Size Score (0.0 - 1.0)
        size_score = self._score_firm_size(firm)
        total_score += size_score * self.weights["firm_size"]
        
        # 2. Practice Area Score (0.0 - 1.0)
        practice_score = self._score_practice_areas(firm)
        total_score += practice_score * self.weights["practice_areas"]
        
        # 3. Geography Score (0.0 - 1.0)
        geo_score = self._score_geography(firm)
        total_score += geo_score * self.weights["geography"]
        
        return round(total_score, 2)

    def _score_firm_size(self, firm: Dict[str, Any]) -> float:
        num_lawyers = firm.get("num_lawyers")
        if num_lawyers is None:
            return 0.0
            
        cfg = self.config.get("firm_size", {})
        min_lawyers = cfg.get("min_lawyers", 50)
        max_lawyers = cfg.get("max_lawyers", 500)
        
        if min_lawyers <= num_lawyers <= max_lawyers:
            return 1.0
        elif num_lawyers > max_lawyers:
            # Still a large firm, maybe slightly less ideal but not bad
            return 0.8
        else:
            # Too small
            return (num_lawyers / min_lawyers) * 0.5

    def _score_practice_areas(self, firm: Dict[str, Any]) -> float:
        firm_areas = firm.get("practice_areas", [])
        if not firm_areas:
            return 0.0
            
        preferred = self.config.get("practice_areas", {}).get("preferred", [])
        if not preferred:
            return 1.0
            
        matches = [area for area in firm_areas if area in preferred]
        if not matches:
            return 0.0
            
        # Return percentage of matches (capped at 1.0)
        return min(1.0, len(matches) / len(preferred))

    def _score_geography(self, firm: Dict[str, Any]) -> float:
        country = firm.get("country")
        if not country:
            return 0.0
            
        preferred_regions = self.config.get("geography", {}).get("preferred_regions", [])
        if not preferred_regions:
            return 1.0
            
        if country in preferred_regions:
            return 1.0
        
        return 0.0