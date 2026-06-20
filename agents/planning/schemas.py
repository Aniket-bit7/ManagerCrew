from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from uuid import UUID
from datetime import datetime

# ==========================================
# 1. Input Schemas (From Jira/RAG)
# ==========================================

class JiraTicket(BaseModel):
    ticket_id: str = Field(..., description="Jira ticket key, e.g., PROJ-123")
    summary: str
    description: Optional[str] = ""
    blocks: List[str] = Field(default_factory=list, description="List of ticket IDs this ticket blocks")
    story_points: Optional[float] = None

# ==========================================
# 2. Intermediate Computational Schemas
# ==========================================

class TaskNode(BaseModel):
    ticket_id: str
    moscow_tier: str  # Must, Should, Could, Won't
    depends_on: List[str] = Field(default_factory=list)
    
    # PERT Metrics
    optimistic_days: float = 0.0
    most_likely_days: float = 0.0
    pessimistic_days: float = 0.0
    expected_duration: float = 0.0  # E = (O + 4M + P) / 6
    variance: float = 0.0           # σ² = ((P - O) / 6)²

    # CPM Metrics (Computed via Forward/Backward Pass)
    es: float = 0.0  # Early Start
    ef: float = 0.0  # Early Finish
    ls: float = 0.0  # Late Start
    lf: float = 0.0  # Late Finish
    float_time: float = 0.0  # LF - EF or LS - ES

# ==========================================
# 3. Output Payload Schema
# ==========================================

class SprintPlan(BaseModel):
    plan_id: UUID
    timestamp: datetime
    ordered_tasks: List[TaskNode] = Field(..., description="Topologically sorted execution order")
    critical_path: List[str] = Field(..., description="Ticket IDs where float == 0")
    sprint_confidence: float = Field(..., description="P(on-time delivery) via normal CDF approximation")
    total_expected_days: float = Field(..., description="Sum of expected durations along the critical path")
    moscow_summary: Dict[str, List[str]] = Field(..., description="Tickets grouped by MoSCoW tier")
    policy_attestation: str = Field(..., description="HMAC-SHA256 signature of the payload")