from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class CandidateScore:
    resource_id: str
    resource_name: str
    eligible: bool
    final_score: float
    breakdown: Dict[str, float] = field(default_factory=dict)
    positive_reasons: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)
