import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent

# Load .env from project root (override=True ensures .env values take precedence)
load_dotenv(PROJECT_ROOT / ".env", override=True)


class Settings:
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Model selection
    OPUS_MODEL: str = "claude-opus-4-20250514"
    SONNET_MODEL: str = "claude-sonnet-4-20250514"

    # Data settings
    OHLCV_LOOKBACK_DAYS: int = 30
    MAX_NEWS_ARTICLES: int = 20
    MAX_AFFECTED_STOCKS: int = 15

    # Risk parameters
    DEFAULT_CAPITAL: float = 1_000_000.0
    MAX_SINGLE_TRADE_RISK_PCT: float = 2.0
    MAX_PORTFOLIO_RISK_PCT: float = 10.0
    VIX_HIGH_THRESHOLD: float = 20.0
    VIX_EXTREME_THRESHOLD: float = 30.0
    MIN_RISK_REWARD: float = 1.5
    ATR_MULTIPLIER: float = 1.5

    # Storage
    STORAGE_BASE: Path = PROJECT_ROOT / "storage_data"
    TRADES_DIR: Path = STORAGE_BASE / "trades"
    JOURNAL_DIR: Path = STORAGE_BASE / "journal"
    MEMORY_DIR: Path = STORAGE_BASE / "memory"

    # NSE 500
    NSE500_CSV: Path = PROJECT_ROOT / "config" / "nse500.csv"


settings = Settings()
