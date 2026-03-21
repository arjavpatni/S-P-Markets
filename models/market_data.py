from pydantic import BaseModel
from datetime import date


class OHLCVBar(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class OHLCVData(BaseModel):
    symbol: str
    bars: list[OHLCVBar]
    period_days: int = 30


class Fundamentals(BaseModel):
    symbol: str
    market_cap: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    dividend_yield: float | None = None
    eps: float | None = None
    revenue_growth: float | None = None
    debt_to_equity: float | None = None
    roe: float | None = None
    sector: str | None = None
    industry: str | None = None
    current_price: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None


class IndexSnapshot(BaseModel):
    name: str
    value: float
    change_pct: float
    date: date


class MarketContext(BaseModel):
    nifty50: IndexSnapshot
    banknifty: IndexSnapshot
    vix: IndexSnapshot
