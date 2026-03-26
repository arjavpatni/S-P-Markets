import logging
import re
import time
import random
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from models.news import NewsArticle

logger = logging.getLogger(__name__)

# Moneycontrol RSS feed for the markets section — no scraping blocks
MONEYCONTROL_MARKETS_RSS = "https://www.moneycontrol.com/rss/marketreports.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "DNT": "1",
    "Connection": "keep-alive",
}

# Keywords that indicate a headline is relevant to stock/financial markets.
# Kept broad — covers stocks, sectors, instruments, commodities, macro, etc.
_RELEVANT_KEYWORDS = re.compile(
    r"\b("
    # Indices & exchanges
    r"nifty|sensex|bse|nse|index|sgx nifty|bank nifty|fin nifty|"
    # General market terms
    r"stock|share|market|rally|crash|bull|bear|correction|"
    r"ipo|fii|dii|mutual fund|etf|smallcap|midcap|largecap|"
    r"trade|trading|investor|equity|portfolio|"
    # Price action (catches stock-specific headlines like "X surges 5%")
    r"surge|surges|plunge|plunges|jump|jumps|drop|drops|"
    r"rise|rises|fall|falls|gain|gains|slip|slips|"
    r"soar|soars|tank|tanks|tumble|tumbles|dip|dips|"
    r"climb|climbs|decline|declines|recover|recovers|"
    r"hit|hits|high|low|record|"
    # Corporate actions & financials
    r"earnings|results|profit|revenue|dividend|bonus|buyback|"
    r"listing|delist|merger|acquisition|stake|takeover|"
    r"q[1-4]|quarter|annual|guidance|outlook|forecast|"
    r"top gainer|top loser|most active|"
    # Sectors & industries
    r"sector|pharma|banking|it sector|auto|fmcg|metal|energy|realty|"
    r"infra|infrastructure|telecom|cement|steel|chemical|textile|"
    r"defence|defense|ev |electric vehicle|aviation|shipping|"
    r"hospitality|retail|insurance|nbfc|fintech|"
    # Instruments & derivatives
    r"futures|options|derivatives|call|put|expiry|contract|"
    r"warrant|debenture|"
    # Commodities & metals
    r"crude|oil|natural gas|gold|silver|copper|aluminium|aluminum|"
    r"zinc|nickel|lead|tin|iron ore|steel|platinum|palladium|"
    r"cotton|sugar|wheat|soybean|commodity|commodities|"
    # Currencies & bonds
    r"rupee|dollar|forex|currency|bond|yield|treasury|"
    # Macro & regulatory
    r"rbi|sebi|inflation|gdp|rate cut|repo rate|fiscal|monetary|"
    r"tariff|duty|tax|gst|budget|policy|reform|"
    # Technical
    r"support|resistance|breakout|technical|moving average|"
    r"volume|volatility|vix"
    r")\b",
    re.IGNORECASE,
)


def is_market_relevant(headline: str) -> bool:
    """Check if a headline is relevant to stock markets based on keywords."""
    return bool(_RELEVANT_KEYWORDS.search(headline))


class MarketNewsScraper:
    """Fetches Indian market news from Moneycontrol's markets RSS feed.
    Filters headlines for market relevance before fetching article bodies."""

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update(HEADERS)
        self._session_initialized = False

    def _init_session(self):
        """Visit Moneycontrol homepage once to establish cookies."""
        if self._session_initialized:
            return
        try:
            self._session.get("https://www.moneycontrol.com/", timeout=15)
            self._session_initialized = True
        except Exception as e:
            logger.warning(f"Failed to init Moneycontrol session: {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def get_latest_market_news(self, limit: int = 20) -> list[NewsArticle]:
        """Fetch market news from Moneycontrol markets RSS feed.

        Steps:
        1. Fetch RSS feed from Moneycontrol markets section
        2. Filter headlines for stock-market relevance by title
        3. Return top N relevant articles
        """
        raw_articles = self._fetch_moneycontrol_rss()

        # Filter for market-relevant headlines only
        relevant = [a for a in raw_articles if is_market_relevant(a.headline)]
        skipped = len(raw_articles) - len(relevant)
        if skipped:
            logger.info(
                f"Filtered out {skipped}/{len(raw_articles)} irrelevant headlines"
            )

        limited = relevant[:limit]
        logger.info(f"Fetched {len(limited)} relevant market articles from Moneycontrol")
        return limited

    def _fetch_moneycontrol_rss(self) -> list[NewsArticle]:
        """Fetch and parse the Moneycontrol markets RSS feed."""
        response = requests.get(
            MONEYCONTROL_MARKETS_RSS, headers=HEADERS, timeout=15
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml-xml")
        items = soup.find_all("item")

        articles = []
        seen_titles = set()

        for item in items:
            title_tag = item.find("title")
            link_tag = item.find("link")
            pub_date_tag = item.find("pubDate")
            desc_tag = item.find("description")

            headline = title_tag.text.strip() if title_tag else ""
            if not headline or headline in seen_titles:
                continue
            seen_titles.add(headline)

            url = link_tag.text.strip() if link_tag else ""
            if not url:
                continue

            summary = ""
            if desc_tag:
                desc_soup = BeautifulSoup(desc_tag.text, "html.parser")
                summary = desc_soup.get_text(strip=True)[:300]

            timestamp = None
            if pub_date_tag:
                try:
                    timestamp = parsedate_to_datetime(pub_date_tag.text)
                except Exception:
                    pass

            articles.append(
                NewsArticle(
                    headline=headline,
                    summary=summary,
                    url=url,
                    source="Moneycontrol",
                    timestamp=timestamp,
                )
            )

        logger.info(f"Parsed {len(articles)} articles from Moneycontrol RSS")
        return articles

    def get_article_body(self, url: str) -> str:
        """Fetch the full article body text from a Moneycontrol URL."""
        if not url:
            return ""

        self._init_session()
        time.sleep(random.uniform(0.3, 1.0))

        try:
            response = self._session.get(
                url,
                timeout=15,
                headers={"Referer": "https://www.moneycontrol.com/"},
            )
            if response.status_code != 200:
                logger.debug(f"Article fetch returned {response.status_code}: {url}")
                return ""

            soup = BeautifulSoup(response.text, "lxml")
            return self._extract_body(soup, url)

        except Exception as e:
            logger.debug(f"Failed to fetch article body: {e}")
            return ""

    def _extract_body(self, soup: BeautifulSoup, url: str) -> str:
        """Extract article body text from Moneycontrol article page."""
        selectors = [
            "div.content_wrapper",
            "div.arti-flow",
            "div.article_content",
            "div.artText",
        ]

        for selector in selectors:
            container = soup.select_one(selector)
            if container:
                paragraphs = container.find_all("p")
                body = " ".join(
                    p.get_text(strip=True)
                    for p in paragraphs
                    if len(p.get_text(strip=True)) > 30
                )
                if len(body) > 100:
                    return body[:3000]

        # Fallback: all <p> tags with substantial text
        all_p = soup.find_all("p")
        body = " ".join(
            p.get_text(strip=True)
            for p in all_p
            if len(p.get_text(strip=True)) > 40
        )
        return body[:3000] if body else ""
