import logging
from datetime import date, timedelta

import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_fixed

from models.market_data import OHLCVBar, OHLCVData, Fundamentals

logger = logging.getLogger(__name__)


class YFinanceClient:
    @staticmethod
    def _nse_symbol(symbol: str) -> str:
        """Convert plain symbol to yfinance NSE format."""
        if not symbol.endswith(".NS"):
            return f"{symbol}.NS"
        return symbol

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def get_ohlcv(
        self,
        symbol: str,
        period: str | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> OHLCVData:
        """Fetch OHLCV data for a symbol."""
        ticker = yf.Ticker(self._nse_symbol(symbol))

        if start and end:
            df = ticker.history(
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),
                auto_adjust=True,
            )
        else:
            df = ticker.history(period=period or "1mo", auto_adjust=True)

        bars = []
        for idx, row in df.iterrows():
            bars.append(OHLCVBar(
                date=idx.date(),
                open=round(row["Open"], 2),
                high=round(row["High"], 2),
                low=round(row["Low"], 2),
                close=round(row["Close"], 2),
                volume=int(row["Volume"]),
            ))

        return OHLCVData(symbol=symbol, bars=bars, period_days=len(bars))

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def get_fundamentals(self, symbol: str) -> Fundamentals:
        """Fetch fundamental data for a symbol."""
        ticker = yf.Ticker(self._nse_symbol(symbol))
        try:
            info = ticker.info
        except Exception as e:
            logger.warning(f"Failed to get info for {symbol}: {e}")
            info = {}

        return Fundamentals(
            symbol=symbol,
            market_cap=info.get("marketCap"),
            pe_ratio=info.get("trailingPE"),
            pb_ratio=info.get("priceToBook"),
            dividend_yield=info.get("dividendYield"),
            eps=info.get("trailingEps"),
            revenue_growth=info.get("revenueGrowth"),
            debt_to_equity=info.get("debtToEquity"),
            roe=info.get("returnOnEquity"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            current_price=info.get("currentPrice") or info.get("regularMarketPrice"),
            fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
            fifty_two_week_low=info.get("fiftyTwoWeekLow"),
        )
