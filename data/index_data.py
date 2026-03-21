import logging
from datetime import date

import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_fixed

from models.market_data import IndexSnapshot, MarketContext

logger = logging.getLogger(__name__)

INDICES = {
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "INDIA VIX": "^INDIAVIX",
}


class IndexDataFetcher:
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def _get_index_snapshot(self, name: str, yf_symbol: str) -> IndexSnapshot:
        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(period="5d")

        if hist.empty or len(hist) < 1:
            logger.warning(f"No data for index {name}")
            return IndexSnapshot(
                name=name, value=0.0, change_pct=0.0, date=date.today()
            )

        latest = hist.iloc[-1]
        value = round(latest["Close"], 2)

        if len(hist) >= 2:
            prev = hist.iloc[-2]["Close"]
            change_pct = round((value - prev) / prev * 100, 2)
        else:
            change_pct = 0.0

        return IndexSnapshot(
            name=name,
            value=value,
            change_pct=change_pct,
            date=hist.index[-1].date(),
        )

    def get_market_context(self) -> MarketContext:
        """Fetch Nifty 50, Bank Nifty, and India VIX snapshots."""
        snapshots = {}
        for name, yf_symbol in INDICES.items():
            try:
                snapshots[name] = self._get_index_snapshot(name, yf_symbol)
            except Exception as e:
                logger.error(f"Failed to fetch {name}: {e}")
                snapshots[name] = IndexSnapshot(
                    name=name, value=0.0, change_pct=0.0, date=date.today()
                )

        return MarketContext(
            nifty50=snapshots["NIFTY 50"],
            banknifty=snapshots["BANK NIFTY"],
            vix=snapshots["INDIA VIX"],
        )
