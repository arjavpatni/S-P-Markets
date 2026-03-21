from datetime import date
from storage.json_store import JSONStore
from models.journal import TradeRecord, ReviewResult
from config.settings import settings


class TradeJournalStore:
    def __init__(self):
        self.store = JSONStore(settings.TRADES_DIR)

    def save_trade(self, trade: TradeRecord):
        filename = f"{trade.entry_date.isoformat()}_{trade.symbol}_{trade.id[:8]}.json"
        self.store.save(filename, trade.model_dump())

    def get_all_trades(self) -> list[TradeRecord]:
        trades = []
        for path in self.store.list_files():
            data = self.store.load(path.name)
            if data:
                trades.append(TradeRecord(**data))
        return trades

    def get_expired_trades(self) -> list[TradeRecord]:
        """Return all trades whose expiry_date <= today and status == OPEN."""
        today = date.today()
        trades = []
        for path in self.store.list_files():
            data = self.store.load(path.name)
            if data and data.get("status") == "OPEN":
                expiry = date.fromisoformat(data["expiry_date"])
                if expiry <= today:
                    trades.append(TradeRecord(**data))
        return trades

    def mark_reviewed(self, trade_id: str, review: ReviewResult):
        """Update trade status to REVIEWED and attach review data."""
        for path in self.store.list_files():
            data = self.store.load(path.name)
            if data and data.get("id") == trade_id:
                data["status"] = "REVIEWED"
                data["review"] = review.model_dump()
                self.store.save(path.name, data)
                return
