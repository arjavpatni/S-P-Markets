import logging

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

from config.settings import settings
from models.news import NewsBundle
from models.market_data import OHLCVData, Fundamentals, MarketContext
from models.correlation import CorrelationResult
from models.analysis import BullCase, StockAnalysis

logger = logging.getLogger(__name__)


class BullAnalyst:
    """Makes the strongest possible bullish case for each stock."""

    def __init__(self):
        self.llm = ChatAnthropic(
            model=settings.SONNET_MODEL,
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=0.3,
            max_tokens=2048,
        )

    def analyze_all(
        self,
        symbols: list[str],
        news: NewsBundle,
        ohlcv: dict[str, OHLCVData],
        fundamentals: dict[str, Fundamentals],
        market_context: MarketContext,
        correlation: CorrelationResult,
    ) -> list[StockAnalysis]:
        results = []
        for symbol in symbols:
            if symbol not in ohlcv or symbol not in fundamentals:
                logger.warning(f"Skipping {symbol}: missing data")
                continue
            try:
                bull_case = self._analyze_single(
                    symbol, news, ohlcv[symbol], fundamentals[symbol],
                    market_context, correlation,
                )
                results.append(StockAnalysis(symbol=symbol, bull_case=bull_case))
            except Exception as e:
                logger.error(f"Bull analysis failed for {symbol}: {e}")
        return results

    def _analyze_single(
        self,
        symbol: str,
        news: NewsBundle,
        ohlcv: OHLCVData,
        fundamentals: Fundamentals,
        market_context: MarketContext,
        correlation: CorrelationResult,
    ) -> BullCase:
        structured_llm = self.llm.with_structured_output(BullCase)

        system_prompt = """You are a BULL analyst at a trading firm. Your job is to make the STRONGEST
possible bullish case for this stock. You MUST argue for a LONG position.

Build your case using ALL available data:
- Recent news and catalysts driving the stock
- Technical analysis: price action, volume trends, support/resistance from OHLCV data
- Fundamental metrics: PE, PB, ROE, revenue growth, debt levels
- Market sentiment: VIX levels, Nifty/BankNifty trend, sector rotation
- Macroeconomic tailwinds

For each argument, specify:
- The factor type (technical, fundamental, news, macro, sentiment)
- The specific argument with data points
- Supporting data (actual numbers)
- Weight (how important is this factor, 0.0-1.0)

Be specific. Reference actual numbers from the data provided.
Assign overall confidence honestly (0.0-1.0).
Set a realistic target_price based on the timeframe (1-5 trading days).
Identify the primary catalyst driving the bullish case."""

        ohlcv_text = self._format_ohlcv(ohlcv)
        news_text = self._format_relevant_news(symbol, news, correlation)

        human_msg = f"""STOCK: {symbol}

NEWS CONTEXT:
{news_text}

OHLCV (last {ohlcv.period_days} trading days):
{ohlcv_text}

FUNDAMENTALS:
{fundamentals.model_dump_json(indent=2)}

MARKET CONTEXT:
Nifty 50: {market_context.nifty50.value} ({market_context.nifty50.change_pct:+.2f}%)
Bank Nifty: {market_context.banknifty.value} ({market_context.banknifty.change_pct:+.2f}%)
India VIX: {market_context.vix.value} ({market_context.vix.change_pct:+.2f}%)

Make the strongest bullish case for {symbol}."""

        return structured_llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_msg),
        ])

    def _format_ohlcv(self, ohlcv: OHLCVData) -> str:
        if not ohlcv.bars:
            return "No OHLCV data available"
        lines = ["Date       | Open    | High    | Low     | Close   | Volume"]
        for bar in ohlcv.bars[-10:]:  # Last 10 days
            lines.append(
                f"{bar.date} | {bar.open:>7.2f} | {bar.high:>7.2f} | "
                f"{bar.low:>7.2f} | {bar.close:>7.2f} | {bar.volume:>10,}"
            )
        if len(ohlcv.bars) > 10:
            lines.insert(1, f"... (showing last 10 of {len(ohlcv.bars)} bars)")
        return "\n".join(lines)

    def _format_relevant_news(
        self, symbol: str, news: NewsBundle, correlation: CorrelationResult
    ) -> str:
        # Find which headlines are relevant to this stock
        relevant_headlines = set()
        for stock in correlation.affected_stocks:
            if stock.symbol == symbol:
                relevant_headlines.update(stock.related_headlines)
                break

        parts = []
        for article in news.articles:
            if article.headline in relevant_headlines or not relevant_headlines:
                parts.append(f"- {article.headline}")
                if article.summary:
                    parts.append(f"  {article.summary}")
        return "\n".join(parts) if parts else "No directly relevant news found"
