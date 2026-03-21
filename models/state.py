from typing import Annotated
from typing_extensions import TypedDict
from operator import add

from models.news import NewsBundle
from models.market_data import OHLCVData, Fundamentals, MarketContext
from models.correlation import CorrelationResult
from models.analysis import StockAnalysis
from models.decision import DMOutput
from models.risk import RMOutput


def merge_analyses(existing: list, new: list) -> list:
    """Custom reducer: merge Bull and Bear analyst outputs by symbol.

    Each analyst produces partial StockAnalysis objects (one with only bull_case,
    the other with only bear_case). This reducer merges them into complete objects.
    """
    combined = {a.symbol: a for a in existing}

    for analysis in new:
        if analysis.symbol in combined:
            existing_item = combined[analysis.symbol]
            # Merge: take non-None fields from the new analysis
            merged_bull = analysis.bull_case or existing_item.bull_case
            merged_bear = analysis.bear_case or existing_item.bear_case
            combined[analysis.symbol] = StockAnalysis(
                symbol=analysis.symbol,
                bull_case=merged_bull,
                bear_case=merged_bear,
            )
        else:
            combined[analysis.symbol] = analysis

    return list(combined.values())


class PipelineState(TypedDict):
    """LangGraph shared state flowing through the entire pipeline.

    Uses TypedDict (not Pydantic BaseModel) for LangGraph performance.
    Individual data objects within the state are Pydantic models.
    """

    # Phase 1: News
    news: NewsBundle | None

    # Phase 2: Correlation
    correlation: CorrelationResult | None
    affected_symbols: list[str]

    # Phase 3: Market data for affected stocks
    ohlcv_data: dict[str, OHLCVData]
    fundamentals: dict[str, Fundamentals]
    market_context: MarketContext | None

    # Phase 4: Analysis (custom reducer for parallel Bull/Bear merge)
    analyses: Annotated[list[StockAnalysis], merge_analyses]

    # Phase 5: Decisions
    dm_output: DMOutput | None

    # Phase 6: Risk
    rm_output: RMOutput | None

    # Metadata
    run_id: str
    errors: Annotated[list[str], add]
