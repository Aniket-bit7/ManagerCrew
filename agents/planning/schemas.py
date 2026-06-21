from pydantic import BaseModel, Field
from typing import List, Optional

class RawSubTask(BaseModel):
    title: str = Field(..., description="Action-oriented title of the subtask")
    description: str = Field(..., description="Detailed engineering requirements")
    acceptance_criteria: List[str] = Field(..., description="Concrete verification checklist items")
    # 3-point estimation (Working Days)
    optimistic_days: float = Field(..., description="O: Best case scenario")
    most_likely_days: float = Field(..., description="M: Most probable duration")
    pessimistic_days: float = Field(..., description="P: Worst case scenario")
    depends_on_titles: List[str] = Field(default_factory=list, description="Titles of other subtasks this depends on")

class RawFeature(BaseModel):
    feature_name: str
    subtasks: List[RawSubTask]

class PRDParsedPayload(BaseModel):
    features: List[RawFeature]

# Final Schema after Enrichment
class EnrichedSubTask(BaseModel):
    id: str
    feature_name: str
    title: str
    description: str
    acceptance_criteria: List[str]
    team_label: str  # FRONTEND, BACKEND, DEVOPS, QA, ARCHITECTURE
    moscow_tier: str  # MUST, SHOULD, COULD, WON'T
    o: float
    m: float
    p: float
    depends_on_ids: List[str] = Field(default_factory=list)