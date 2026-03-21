from pydantic import BaseModel
from datetime import date


class TradeRecord(BaseModel):
    id: str
    symbol: str
    direction: str
    entry_price: float
    target_price: float
    stop_loss: float
    quantity: int
    timeframe_days: int
    entry_date: date
    expiry_date: date
    status: str = "OPEN"
    dm_confidence: float
    risk_notes: str


class ReviewResult(BaseModel):
    trade_id: str
    symbol: str
    direction: str
    entry_price: float
    target_price: float
    actual_high: float
    actual_low: float
    best_exit_price: float
    best_pnl_pct: float
    worst_pnl_pct: float
    target_hit: bool
    stop_hit: bool
    review_date: date
