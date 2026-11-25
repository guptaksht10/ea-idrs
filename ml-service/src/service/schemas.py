from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class ExperimentRunRequest(BaseModel):
    target_attack: str = Field(default="DDoS", description="Attack class to monitor for recall drop")
    shift_type: Literal["none", "covariate_benign", "class_conditional", "concept_proxy"] = "concept_proxy"
    shift_start_window: Optional[int] = Field(
        default=None,
        ge=1,
        description="Optional explicit shift start window; auto-anchors to target_attack wave if omitted.",
    )
    max_windows: int = Field(default=40, ge=5, le=200)
    recall_cutoff: float = Field(default=0.80, gt=0.0, lt=1.0)
    
class MonitorComparisonRow(BaseModel):
    monitor: str
    empirical_far_pct: float
    t_alarm: Optional[int]
    t_fail: Optional[int]
    lead_time_delta_t: Optional[int]
    missed_degradation: bool
    mean_score_post_shift: float


class ExperimentWindowPoint(BaseModel):
    window_id: int
    timestamp: Optional[str]
    m1_score: float
    m2_score: float
    m3_score: float
    m4_score: float
    m1_alert: bool
    m2_alert: bool
    m3_alert: bool
    m4_alert: bool
    target_recall: Optional[float]
    target_support: int


class ExperimentSummaryResponse(BaseModel):
    target_attack: str
    shift_type: str
    shift_start_window: int
    recall_cutoff: float
    t_fail: Optional[int]
    m4_minus_m3_margin_ci95: List[float]
    monitor_comparison: List[MonitorComparisonRow]
    windows: List[ExperimentWindowPoint]