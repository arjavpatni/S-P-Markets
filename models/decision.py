from pydantic import BaseModel, Field
from enum import Enum
from datetime import date


class TradeDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    IGNORE = "IGNORE"


class TradeDecision(BaseModel):
    symbol: str
    direction: TradeDirection
    confidence: float = Field(ge=0.0, le=1.0)
    entry_price: float
    target_price: float
    timeframe_days: int = Field(ge=1, le=5)
    reasoning: str = Field(description="2 sentences max. State the direction rationale and primary supporting factor only.")
    bull_weight: float = Field(ge=0.0, le=1.0)
    bear_weight: float = Field(ge=0.0, le=1.0)


class DMOutput(BaseModel):
    decisions: list[TradeDecision]
    market_outlook: str
    current_date: date
    day_of_week: str
