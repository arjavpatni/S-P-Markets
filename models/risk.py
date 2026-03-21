from pydantic import BaseModel, Field
from enum import Enum


class RiskVerdict(str, Enum):
    APPROVED = "APPROVED"
    RESIZED = "RESIZED"
    REJECTED = "REJECTED"


class ApprovedTrade(BaseModel):
    symbol: str
    direction: str
    entry_price: float
    target_price: float
    stop_loss: float
    quantity: int
    risk_reward_ratio: float
    max_loss_amount: float
    timeframe_days: int
    verdict: RiskVerdict
    risk_notes: str


class RMOutput(BaseModel):
    approved_trades: list[ApprovedTrade]
    rejected_trades: list[dict]
    portfolio_risk_score: float
    vix_assessment: str
    total_capital_at_risk_pct: float
