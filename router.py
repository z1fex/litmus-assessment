from typing import Dict, Any

class LeadRouter:
    """Routes qualified leads to appropriate categories."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize router with routing configuration.
        """
        self.config = config

    def route(self, firm: Dict[str, Any], score: float) -> str:
        """
        Route a lead based on score and firm data.
        
        Thresholds can be adjusted via config but defaults are:
        - high_priority: score >= 0.7
        - nurture: 0.4 <= score < 0.7
        - disqualified: score < 0.4
        """
        if score >= 0.7:
            return "high_priority"
        elif score >= 0.4:
            return "nurture"
        else:
            return "disqualified"
