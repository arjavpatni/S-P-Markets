from pydantic import BaseModel, Field


class AffectedStock(BaseModel):
    symbol: str
    company_name: str
    sector: str
    industry: str
    relevance_score: float = Field(ge=0.0, le=1.0)
    reasoning: str
    related_headlines: list[str]


class CorrelationResult(BaseModel):
    affected_stocks: list[AffectedStock]
    market_themes: list[str]
    overall_sentiment: str = Field(description="bullish, bearish, or neutral")
