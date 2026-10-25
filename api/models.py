# api/models.py
from pydantic import BaseModel, Field
from typing import Optional, Any


class GraphStats(BaseModel):
    papers: int
    claims: int
    contradictions: int
    gaps: int
    experiments: int = 0


class ClaimModel(BaseModel):
    id: str
    text: str
    section: str
    confidence: float
    base_confidence: Optional[float] = None
    arxiv_id: str
    paper_year: Optional[int] = None
    paper_title: Optional[str] = None
    # Optional provenance. Present on contradiction detail payloads.
    evidence_span: Optional[str] = None
    subject: Optional[str] = None
    predicate: Optional[str] = None
    object_val: Optional[str] = None
    metric: Optional[str] = None
    direction: Optional[str] = None
    conditions: Optional[str] = None


class ClaimsResponse(BaseModel):
    total: int
    claims: list[ClaimModel]


class ContradictionModel(BaseModel):
    id: str
    claim_a: ClaimModel
    claim_b: ClaimModel
    paper_a: str
    paper_b: str
    explanation: str
    confidence: float
    has_experiment: bool = False


class ContradictionsResponse(BaseModel):
    # total = relationships matching the requested model-score threshold.
    total: int
    # corpus_total = every CONTRADICTS relationship in the graph.
    corpus_total: int = 0
    # shown = number returned in this response (the API caps the payload).
    shown: int = 0
    contradictions: list[ContradictionModel]


class ExperimentModel(BaseModel):
    contradiction_id: str
    title: str
    hypothesis_a: str
    hypothesis_b: str
    procedure: str
    dataset: str
    duration: str
    cost: str
    decision_rule: str
    caveats: list[str]
    design_confidence: float
    metric: Optional[str] = None



class GapClaimRef(BaseModel):
    id: str
    text: str
    section: Optional[str] = None
    confidence: Optional[float] = None
    arxiv_id: Optional[str] = None
    paper_title: Optional[str] = None


class GapModel(BaseModel):
    id: str
    text: str
    # Canonical source: cluster | future_work | legacy_import | unknown.
    source: str
    # The raw value stored in the graph, retained for provenance.
    source_raw: Optional[str] = None
    source_label: str
    source_description: str
    related_claims: list[str]
    related_claim_details: list[GapClaimRef] = Field(default_factory=list)
    confidence: Optional[float] = None


class GapsResponse(BaseModel):
    # total = gaps matching the requested source filter.
    total: int
    # corpus_total = every gap in the current graph.
    corpus_total: int
    source_counts: dict[str, int]
    gaps: list[GapModel]


class ReflectionStep(BaseModel):
    step: int
    observation: str
    reasoning: str
    action: str


class CoordinatorOutput(BaseModel):
    report: str
    raw: str
    iterations: int
    plan: list[str]
    reflection_log: list[ReflectionStep]
    confidence: float
    sources: list[str]


class IngestionSummary(BaseModel):
    new_papers: int
    new_claims: int
    last_run: Optional[str] = None
    running: bool = False
    error: Optional[str] = None


class ConfidenceDistribution(BaseModel):
    total: int
    average: float
    high: int
    medium: int
    low: int


class ChangedClaim(BaseModel):
    claim_id: str
    claim_text: str
    base_confidence: float
    current_confidence: float
    delta: float
    reason: str
    supports: int = 0
    contradictions: int = 0
    arxiv_id: Optional[str] = None
    paper_title: Optional[str] = None


class YearlyPosition(BaseModel):
    year: int
    position: str
    confidence: float = 0.0
    key_papers: list[str] = Field(default_factory=list)


class TemporalEvolution(BaseModel):
    topic: str
    yearly_positions: list[YearlyPosition]
    narrative: str
    current_status: str


class Dispute(BaseModel):
    id: str
    topic: str
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    resolved: bool
    status: str = "unknown"
    resolution: Optional[str] = None
    key_claims: list[str]


class DisputeTimeline(BaseModel):
    topic: str
    disputes: list[Dispute]
    summary: str = ""
    candidate_claim_count: int = 0
    contradiction_count: int = 0
    year_start: int = 2019
    year_end: int = 2026
