from pydantic import BaseModel, Field


class ArgumentPoint(BaseModel):
    factor: str  # "technical", "fundamental", "news", "macro", "sentiment"
    argument: str
    supporting_data: str
    weight: float = Field(ge=0.0, le=1.0)


class BullCase(BaseModel):
    symbol: str
    overall_confidence: float = Field(ge=0.0, le=1.0)
    arguments: list[ArgumentPoint]
    target_price: float | None = None
    catalyst: str
    summary: str


class BearCase(BaseModel):
    symbol: str
    overall_confidence: float = Field(ge=0.0, le=1.0)
    arguments: list[ArgumentPoint]
    downside_target: float | None = None
    risk_factor: str
    summary: str


class StockAnalysis(BaseModel):
    symbol: str
    bull_case: BullCase | None = None
    bear_case: BearCase | None = None
