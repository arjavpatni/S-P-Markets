import logging

from models.state import PipelineState
from agents.data_agent import DataAgent
from agents.correlating_agent import CorrelatingAgent
from agents.bull_analyst import BullAnalyst
from agents.bear_analyst import BearAnalyst
from agents.decision_maker import DecisionMaker
from agents.risk_manager import RiskManager
from agents.journal_agent import JournalAgent

logger = logging.getLogger(__name__)

# Agent instances (created once, reused across nodes)
data_agent = DataAgent()
correlating_agent = CorrelatingAgent()
bull_analyst = BullAnalyst()
bear_analyst = BearAnalyst()
decision_maker = DecisionMaker()
risk_manager = RiskManager()
journal_agent = JournalAgent()


def fetch_news_node(state: PipelineState) -> dict:
    """Node 1: Scrape top market news from Moneycontrol."""
    logger.info("=" * 60)
    logger.info("NODE: fetch_news")
    try:
        news_bundle = data_agent.fetch_news()
        logger.info(f"Fetched {news_bundle.count} news articles")
        return {"news": news_bundle}
    except Exception as e:
        logger.error(f"Failed to fetch news: {e}")
        return {"errors": [f"fetch_news: {str(e)}"]}


def correlate_news_node(state: PipelineState) -> dict:
    """Node 2: Identify affected stocks from news using Opus 4.6."""
    logger.info("=" * 60)
    logger.info("NODE: correlate_news")

    news = state.get("news")
    if not news or not news.articles:
        return {"errors": ["correlate_news: No news to correlate"]}

    try:
        result = correlating_agent.correlate(news)
        symbols = [s.symbol for s in result.affected_stocks]
        logger.info(f"Identified {len(symbols)} affected stocks: {symbols}")
        return {"correlation": result, "affected_symbols": symbols}
    except Exception as e:
        logger.error(f"Correlation failed: {e}")
        return {"errors": [f"correlate_news: {str(e)}"]}


def fetch_market_data_node(state: PipelineState) -> dict:
    """Node 3: Fetch OHLCV + fundamentals + index data for affected stocks."""
    logger.info("=" * 60)
    logger.info("NODE: fetch_market_data")

    symbols = state.get("affected_symbols", [])
    if not symbols:
        return {"errors": ["fetch_market_data: No symbols to fetch"]}

    try:
        ohlcv = data_agent.fetch_ohlcv_bulk(symbols)
        fundamentals = data_agent.fetch_fundamentals_bulk(symbols)
        market_ctx = data_agent.fetch_market_context()

        logger.info(
            f"Fetched data for {len(ohlcv)} stocks. "
            f"Market: Nifty={market_ctx.nifty50.value}, VIX={market_ctx.vix.value}"
        )
        return {
            "ohlcv_data": ohlcv,
            "fundamentals": fundamentals,
            "market_context": market_ctx,
        }
    except Exception as e:
        logger.error(f"Market data fetch failed: {e}")
        return {"errors": [f"fetch_market_data: {str(e)}"]}


def bull_analyst_node(state: PipelineState) -> dict:
    """Node 4a: Bull analyst makes the bullish case (runs parallel with bear)."""
    logger.info("=" * 60)
    logger.info("NODE: bull_analyst")

    try:
        analyses = bull_analyst.analyze_all(
            symbols=state.get("affected_symbols", []),
            news=state["news"],
            ohlcv=state.get("ohlcv_data", {}),
            fundamentals=state.get("fundamentals", {}),
            market_context=state["market_context"],
            correlation=state["correlation"],
        )
        logger.info(f"Bull analyst completed {len(analyses)} analyses")
        return {"analyses": analyses}
    except Exception as e:
        logger.error(f"Bull analyst failed: {e}")
        return {"errors": [f"bull_analyst: {str(e)}"]}


def bear_analyst_node(state: PipelineState) -> dict:
    """Node 4b: Bear analyst makes the bearish case (runs parallel with bull)."""
    logger.info("=" * 60)
    logger.info("NODE: bear_analyst")

    try:
        analyses = bear_analyst.analyze_all(
            symbols=state.get("affected_symbols", []),
            news=state["news"],
            ohlcv=state.get("ohlcv_data", {}),
            fundamentals=state.get("fundamentals", {}),
            market_context=state["market_context"],
            correlation=state["correlation"],
        )
        logger.info(f"Bear analyst completed {len(analyses)} analyses")
        return {"analyses": analyses}
    except Exception as e:
        logger.error(f"Bear analyst failed: {e}")
        return {"errors": [f"bear_analyst: {str(e)}"]}


def decision_maker_node(state: PipelineState) -> dict:
    """Node 5: Decision Maker weighs both cases and decides trades."""
    logger.info("=" * 60)
    logger.info("NODE: decision_maker")

    analyses = state.get("analyses", [])
    if not analyses:
        return {"errors": ["decision_maker: No analyses to decide on"]}

    try:
        memory = decision_maker.load_memory()
        output = decision_maker.decide(
            analyses=analyses,
            market_context=state["market_context"],
            memory=memory,
        )
        return {"dm_output": output}
    except Exception as e:
        logger.error(f"Decision maker failed: {e}")
        return {"errors": [f"decision_maker: {str(e)}"]}


def risk_manager_node(state: PipelineState) -> dict:
    """Node 6: Risk Manager sizes trades, sets stops, and can veto."""
    logger.info("=" * 60)
    logger.info("NODE: risk_manager")

    dm_output = state.get("dm_output")
    if not dm_output:
        return {"errors": ["risk_manager: No DM output to assess"]}

    try:
        memory = risk_manager.load_memory()
        output = risk_manager.assess(
            decisions=dm_output,
            market_context=state["market_context"],
            ohlcv=state.get("ohlcv_data", {}),
            memory=memory,
        )
        return {"rm_output": output}
    except Exception as e:
        logger.error(f"Risk manager failed: {e}")
        return {"errors": [f"risk_manager: {str(e)}"]}


def record_trades_node(state: PipelineState) -> dict:
    """Node 7: Journal records all approved trades to disk."""
    logger.info("=" * 60)
    logger.info("NODE: record_trades")

    rm_output = state.get("rm_output")
    dm_output = state.get("dm_output")
    if not rm_output or not dm_output:
        return {"errors": ["record_trades: Missing DM or RM output"]}

    if not rm_output.approved_trades:
        logger.info("No approved trades to record.")
        return {}

    try:
        journal_agent.record(
            dm_output=dm_output,
            rm_output=rm_output,
            news=state["news"],
            correlation=state["correlation"],
            run_id=state["run_id"],
        )
        return {}
    except Exception as e:
        logger.error(f"Journal recording failed: {e}")
        return {"errors": [f"record_trades: {str(e)}"]}
