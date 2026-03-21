import logging
from datetime import datetime

from data.scraper import MarketNewsScraper
from data.yfinance_client import YFinanceClient
from data.index_data import IndexDataFetcher
from models.news import NewsBundle
from models.market_data import OHLCVData, Fundamentals, MarketContext
from config.settings import settings

logger = logging.getLogger(__name__)


class DataAgent:
    def __init__(self):
        self.scraper = MarketNewsScraper()
        self.yf_client = YFinanceClient()
        self.index_fetcher = IndexDataFetcher()

    def fetch_news(self) -> NewsBundle:
        """Fetch top Indian market news and their full article bodies."""
        logger.info("Fetching market news...")
        articles = self.scraper.get_latest_market_news(
            limit=settings.MAX_NEWS_ARTICLES
        )

        # Fetch full article body for each article
        for article in articles:
            try:
                body = self.scraper.get_article_body(article.url)
                if body:
                    article.body = body
                    logger.info(f"Fetched body ({len(body)} chars): {article.headline[:60]}")
            except Exception as e:
                logger.warning(f"Failed to fetch body for '{article.headline[:50]}': {e}")

        with_body = sum(1 for a in articles if a.body)
        logger.info(f"News fetch complete: {len(articles)} articles, {with_body} with full body")

        return NewsBundle(
            articles=articles,
            fetched_at=datetime.now(),
            count=len(articles),
        )

    def fetch_ohlcv_bulk(self, symbols: list[str]) -> dict[str, OHLCVData]:
        """Fetch 30-day OHLCV for each symbol."""
        logger.info(f"Fetching OHLCV data for {len(symbols)} stocks...")
        result = {}
        for symbol in symbols:
            try:
                result[symbol] = self.yf_client.get_ohlcv(symbol, period="1mo")
            except Exception as e:
                logger.error(f"Failed to fetch OHLCV for {symbol}: {e}")
        return result

    def fetch_fundamentals_bulk(self, symbols: list[str]) -> dict[str, Fundamentals]:
        """Fetch fundamentals for each symbol."""
        logger.info(f"Fetching fundamentals for {len(symbols)} stocks...")
        result = {}
        for symbol in symbols:
            try:
                result[symbol] = self.yf_client.get_fundamentals(symbol)
            except Exception as e:
                logger.error(f"Failed to fetch fundamentals for {symbol}: {e}")
        return result

    def fetch_market_context(self) -> MarketContext:
        """Fetch index data: Nifty 50, Bank Nifty, India VIX."""
        logger.info("Fetching market context (indices)...")
        return self.index_fetcher.get_market_context()
