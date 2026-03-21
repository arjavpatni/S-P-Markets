import logging
import time
import random
from datetime import datetime
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential
from googlenewsdecoder import new_decoderv1

from models.news import NewsArticle

logger = logging.getLogger(__name__)

# Prioritize Moneycontrol, then broaden to other Indian market sources
NEWS_QUERIES = [
    "site:moneycontrol.com stock market",
    "site:moneycontrol.com nifty sensex",
    "india stock market nifty sensex economy",
]

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


class MarketNewsScraper:
    """Fetches Indian market news via Google News RSS, preferring Moneycontrol.
    Resolves Google News redirect URLs and fetches full article bodies."""

    RSS_URL = "https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"

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
        """Fetch top Indian market news, preferring Moneycontrol sources.

        Steps:
        1. Fetch RSS feeds (fast, no URL decoding yet)
        2. Deduplicate and sort (Moneycontrol first, then recency)
        3. Limit to top N
        4. Decode Google News URLs concurrently (only for the top N)
        """
        raw_articles = []
        seen_titles = set()

        for query in NEWS_QUERIES:
            try:
                articles = self._fetch_rss(query)
                for article in articles:
                    if article.headline not in seen_titles:
                        seen_titles.add(article.headline)
                        raw_articles.append(article)
            except Exception as e:
                logger.warning(f"RSS fetch failed for '{query}': {e}")

        # Sort: Moneycontrol first, then by recency
        raw_articles.sort(
            key=lambda a: (
                0 if "moneycontrol" in a.source.lower() else 1,
                -(a.timestamp.timestamp() if a.timestamp else 0),
            )
        )

        # Limit BEFORE decoding URLs (decoding is slow)
        limited = raw_articles[:limit]

        # Decode Google News URLs concurrently
        logger.info(f"Decoding {len(limited)} article URLs...")
        self._decode_urls_concurrent(limited)

        mc_count = sum(1 for a in limited if "moneycontrol" in a.source.lower())
        logger.info(f"Fetched {len(limited)} articles ({mc_count} from Moneycontrol)")
        return limited

    def _fetch_rss(self, query: str) -> list[NewsArticle]:
        """Fetch and parse a Google News RSS feed (no URL decoding here)."""
        url = self.RSS_URL.format(query=query.replace(" ", "+"))
        response = requests.get(url, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml-xml")
        items = soup.find_all("item")

        articles = []
        for item in items:
            title_tag = item.find("title")
            link_tag = item.find("link")
            pub_date_tag = item.find("pubDate")
            source_tag = item.find("source")
            desc_tag = item.find("description")

            headline = title_tag.text.strip() if title_tag else ""
            if not headline:
                continue

            source_name = source_tag.text.strip() if source_tag else ""
            if source_name and headline.endswith(f" - {source_name}"):
                headline = headline[: -len(f" - {source_name}")].strip()

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

            google_link = link_tag.text.strip() if link_tag else ""

            articles.append(NewsArticle(
                headline=headline,
                summary=summary,
                url=google_link,  # Will be decoded later
                source=source_name or "Google News",
                timestamp=timestamp,
            ))

        return articles

    def _decode_urls_concurrent(self, articles: list[NewsArticle]):
        """Decode Google News redirect URLs concurrently."""
        def decode_one(article: NewsArticle) -> tuple[NewsArticle, str | None]:
            if "news.google.com" not in article.url:
                return article, article.url
            try:
                result = new_decoderv1(article.url)
                if result.get("status"):
                    return article, result["decoded_url"]
            except Exception as e:
                logger.debug(f"URL decode failed for '{article.headline[:40]}': {e}")
            return article, None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(decode_one, a): a for a in articles}
            for future in as_completed(futures):
                article, decoded_url = future.result()
                if decoded_url:
                    article.url = decoded_url

    def get_article_body(self, url: str) -> str:
        """Fetch the full article body text from the source URL."""
        if not url or "news.google.com" in url:
            return ""

        if "moneycontrol.com" in url:
            self._init_session()

        time.sleep(random.uniform(0.3, 1.0))

        try:
            response = self._session.get(
                url,
                timeout=15,
                headers={"Referer": "https://www.google.com/"},
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
        """Extract article body text using source-specific selectors."""
        if "moneycontrol.com" in url:
            selectors = [
                "div.content_wrapper",
                "div.arti-flow",
                "div.article_content",
                "div.artText",
            ]
        else:
            selectors = [
                "article",
                "div.article_content",
                "div.story-content",
                "div.content_wrapper",
                "div#contentdata",
                "main",
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
