import logging

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

from config.settings import settings
from config.stock_universe import StockUniverse
from models.news import NewsBundle
from models.correlation import CorrelationResult

logger = logging.getLogger(__name__)


class CorrelatingAgent:
    """Maps news headlines to affected NSE 500 stocks using deep reasoning (Opus 4.6)."""

    def __init__(self):
        self.llm = ChatAnthropic(
            model=settings.OPUS_MODEL,
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=0.2,
            max_tokens=4096,
            model_kwargs={"betas": ["prompt-caching-2024-07-31"]},
        )
        self.universe = StockUniverse()
        # Cache the formatted NSE list once at init — static across all runs
        self._nse500_context = self.universe.get_formatted_list()

    def correlate(self, news: NewsBundle) -> CorrelationResult:
        logger.info(f"Correlating {news.count} news articles to NSE 500 stocks...")

        structured_llm = self.llm.with_structured_output(CorrelationResult)

        system_prompt_text = """You are a senior market analyst at an Indian trading firm.
Your task: read the news headlines and summaries below, then identify which
stocks from the NSE 500 universe are DIRECTLY or INDIRECTLY affected.

Consider:
- Direct mentions of companies or their subsidiaries
- Sector-level impacts (e.g., RBI rate decision affects all banks and NBFCs)
- Supply chain effects (e.g., crude oil price change affects paint, aviation, chemicals, OMCs)
- Regulatory changes affecting specific industries (SEBI, TRAI, FSSAI, etc.)
- Global macro events and their India-specific impact (US Fed, China data, etc.)
- Commodity price movements and downstream effects
- Government policy announcements (PLI, budget, GST changes)
- Earnings surprises or guidance changes from major companies

For each affected stock, provide:
- The stock symbol (EXACTLY as it appears in the NSE 500 list below)
- The company name
- The sector and industry
- A relevance score (0.0-1.0) - how directly is this stock affected?
- Clear reasoning for why this stock is affected
- Which specific headlines triggered this correlation

Also identify:
- Key market themes emerging from the news
- Overall market sentiment (bullish, bearish, or neutral)

IMPORTANT: Only include stocks with relevance_score >= 0.3.
Limit to the top 15 most affected stocks.
Use EXACT symbols from the NSE 500 list provided below."""

        nse_block_text = f"NSE 500 STOCK UNIVERSE (grouped by sector/industry):\n{self._nse500_context}"

        # NSE list is static — mark for Anthropic server-side caching
        system_message = SystemMessage(content=[
            {"type": "text", "text": system_prompt_text},
            {"type": "text", "text": nse_block_text, "cache_control": {"type": "ephemeral"}},
        ])

        news_text = self._format_news(news)

        human_msg = f"""TODAY'S NEWS HEADLINES AND SUMMARIES:

{news_text}

Identify all affected stocks from the NSE 500 universe above. Be thorough but precise."""

        result = structured_llm.invoke([
            system_message,
            HumanMessage(content=human_msg),
        ])

        # Validate symbols against universe
        valid_symbols = set(self.universe.get_all_symbols())
        result.affected_stocks = [
            stock for stock in result.affected_stocks
            if stock.symbol in valid_symbols
        ]

        logger.info(
            f"Found {len(result.affected_stocks)} affected stocks. "
            f"Themes: {result.market_themes}. Sentiment: {result.overall_sentiment}"
        )
        return result

    def _format_news(self, news: NewsBundle) -> str:
        parts = []
        for i, article in enumerate(news.articles, 1):
            parts.append(f"{i}. [{article.headline}]")
            if article.summary:
                parts.append(f"   Summary: {article.summary}")
            if article.body:
                # Truncate body to first 500 chars for context window efficiency
                body_preview = article.body[:500]
                parts.append(f"   Details: {body_preview}")
            parts.append("")
        return "\n".join(parts)
